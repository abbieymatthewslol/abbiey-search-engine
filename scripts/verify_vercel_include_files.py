"""Ensure first-party code reachable from app.py is covered in vercel.json includeFiles.

Policy (see .cursor/rules/vercel-include-files.mdc)
--------------------------------------------------
Only code under these paths is exempt (no includeFiles line required):
  app.py, engine/**, retrieval/**, osint/**, api/**

Any other first-party module (e.g. root ``billing.py``) MUST appear in
``vercel.json`` ``builds[0].config.includeFiles`` as that file or a single
``pkg/**`` for a new package. Do not replace the list with a repo-wide ``**``
wildcard.

Exits 0 on success, 1 with actionable errors.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import re
import sys
from importlib.machinery import ModuleSpec
from importlib._bootstrap import _resolve_name
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
VERCEL_JSON = ROOT / "vercel.json"
APP_PY = ROOT / "app.py"
# Parse imports from these trees (plus BFS follow) so includeFiles matches the full app graph.
_SCAN_SEED_DIRS = ("engine", "retrieval", "osint", "api")

EXEMPT_EXACT = frozenset({"app.py"})
EXEMPT_PREFIXES = ("engine/", "retrieval/", "osint/", "api/")

# Top-level third-party and tooling — not resolved as repo modules.
_TOP_SKIP = frozenset(
    {
        "conftest",
        "tests",
        "scripts",
        "fix_parens",
        "find_parens",
    }
)
_STDLIB_TOP: set[str] | None = None


def _stdlib_top() -> set[str]:
    global _STDLIB_TOP
    if _STDLIB_TOP is None:
        m = getattr(sys, "stdlib_module_names", set())
        _STDLIB_TOP = {x.split(".", 1)[0] for x in m} if m else set()
    return _STDLIB_TOP


def _relposix(p: Path) -> str:
    return p.resolve().relative_to(ROOT).as_posix().replace("\\", "/")


def _is_exempt_path(rel: str) -> bool:
    if rel in EXEMPT_EXACT:
        return True
    for pref in EXEMPT_PREFIXES:
        p = pref.rstrip("/")
        if rel == p or rel.startswith(f"{p}/"):
            return True
    return False


def _load_include_patterns() -> list[str]:
    with open(VERCEL_JSON, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    return list(cfg["builds"][0]["config"]["includeFiles"])


def _pattern_covers_path(pattern: str, rel: str) -> bool:
    if not pattern or pattern.startswith("!"):
        return False
    if pattern.endswith("/**"):
        base = pattern[:-3].rstrip("/")
        if not base:
            return True
        return rel == base or rel.startswith(f"{base}/")
    if "**" in pattern and not pattern.endswith("/**"):
        return bool(
            re.match(
                re.escape(pattern).replace(r"\*\*", ".*").replace(r"\*", "[^/]*"),
                rel,
            )
        )
    return pattern == rel


def _covered_by_includefiles(rel: str, patterns: list[str]) -> bool:
    return any(_pattern_covers_path(pat, rel) for pat in patterns)


def _infer___package__(path: Path) -> str:
    """Best-effort __package__ for a source file, for _resolve_name."""
    relp = path.resolve().relative_to(ROOT)
    if relp.name == "__init__.py":
        if not relp.parent.parts:
            return ""
        return ".".join(relp.parent.parts)
    if relp.suffix != ".py" or relp.name == "app.py":
        return ""
    parts = relp.with_suffix("").parts
    if len(parts) < 2:
        return ""  # top-level module, no package
    *parents, _s = parts
    if not (ROOT / parents[0] / "__init__.py").exists() and not (
        (ROOT / "__init__.py").exists() and not parents[0:1]
    ):
        return ""
    return ".".join(parents)


def _ast_module_strings(path: Path, w: list[str]) -> set[str]:
    """Dotted import targets to hand to find_spec (e.g. ``retrieval.pipeline``)."""
    try:
        tree = ast.parse(
            path.read_text(encoding="utf-8-sig", errors="replace"),
            filename=str(path),
        )
    except (OSError, SyntaxError) as e:
        w.append(f"Could not parse {path}: {e}")
        return set()

    pkg = _infer___package__(path)
    out: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                out.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            lvl = int(node.level or 0)
            try:
                if lvl and node.module is None and node.names:
                    base = _resolve_name("", pkg, lvl)
                    for al in node.names:
                        out.add(f"{base}.{al.name}")
                elif lvl and node.module is not None:
                    out.add(_resolve_name(node.module, pkg, lvl))
                elif not lvl and node.module is not None:
                    out.add(node.module)
            except (ImportError, ValueError) as e:
                w.append(f"{path}: {type(node).__name__}: {e}")
    return out


def _with_sys_path():
    r = str(ROOT)
    old = list(sys.path)
    if r not in sys.path:
        sys.path.insert(0, r)
    return old


def _spec_origin_paths(name: str) -> list[Path]:
    old = _with_sys_path()
    try:
        spec = importlib.util.find_spec(name)
    except (ImportError, ValueError, ModuleNotFoundError):
        return []
    finally:
        sys.path[:] = old

    if spec is None or not isinstance(spec, ModuleSpec):
        return []
    if spec.has_location and spec.origin and str(spec.origin).endswith(".py"):
        p = Path(spec.origin).resolve()
        if p.is_file():
            try:
                p.relative_to(ROOT)
            except ValueError:
                return []
            return [p]
    if spec.submodule_search_locations:
        for loc in spec.submodule_search_locations:
            initp = Path(loc) / "__init__.py"
            if initp.is_file() and not spec.has_location:
                try:
                    initp.resolve().relative_to(ROOT)
                except ValueError:
                    continue
                return [initp.resolve()]
    return []


def _is_skip_top(name: str) -> bool:
    top = name.split(".", 1)[0]
    if not top or top in _TOP_SKIP:
        return True
    if top in _stdlib_top():
        return True
    return False


def _scan_seed_py_files() -> list[Path]:
    out: list[Path] = []
    if APP_PY.is_file():
        out.append(APP_PY)
    for d in _SCAN_SEED_DIRS:
        base = ROOT / d
        if base.is_dir():
            out.extend(sorted(base.rglob("*.py")))
    return out


def _discover_files(warn: list[str]) -> set[Path]:
    """BFS: module name -> .py under ROOT -> parse imports, repeat.

    Seeds imports from ``app.py`` and every ``*.py`` under engine/, retrieval/,
    osint/, and api/ (per project policy).
    """
    from collections import deque

    seen_m: set[str] = set()
    seen_f: set[Path] = set()
    out_f: set[Path] = set()
    q_m: deque[str] = deque()
    for path in _scan_seed_py_files():
        for m in _ast_module_strings(path, warn):
            if m and not _is_skip_top(m):
                q_m.append(m)

    while q_m:
        mod = q_m.popleft()
        if mod in seen_m:
            continue
        seen_m.add(mod)
        for f in _spec_origin_paths(mod):
            try:
                rel = _relposix(f)
            except ValueError:
                continue
            if rel.startswith("tests/"):
                continue
            if f in seen_f:
                continue
            seen_f.add(f)
            out_f.add(f)
            for m2 in _ast_module_strings(f, warn):
                if m2 and not _is_skip_top(m2) and m2 not in seen_m:
                    q_m.append(m2)
    return out_f


def verify() -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warn: list[str] = []
    if not APP_PY.is_file():
        return [f"Missing {APP_PY}"], []
    if not VERCEL_JSON.is_file():
        return [f"Missing {VERCEL_JSON}"], []

    try:
        patterns = _load_include_patterns()
    except (OSError, json.JSONDecodeError, KeyError, IndexError) as e:
        return [f"Could not read vercel.json includeFiles: {e}"], []

    try:
        local_files = _discover_files(warn)
    except Exception as e:  # pragma: no cover
        return [f"Discovery failed: {e!r}"], warn

    for f in sorted(local_files, key=_relposix):
        rel = _relposix(f)
        if _is_exempt_path(rel) or rel == "app.py":
            continue
        if not _covered_by_includefiles(rel, patterns):
            errors.append(
                f"Not in vercel.json includeFiles: {rel} - add a minimal line "
                f"like {json.dumps(rel)} or a single package glob if you added a new directory."
            )
    return errors, warn


def main() -> int:
    errors, warn = verify()
    for w in warn:
        print("warning:", w, file=sys.stderr)
    if errors:
        print("Vercel includeFiles check failed:\n", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    print("vercel includeFiles: ok (all non-exempt first-party files covered).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
