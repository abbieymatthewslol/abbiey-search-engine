"""Static checks for environment variable usage, drift, and dangerous defaults.

- Scans first-party Python (same roots as the Vercel check + root helpers).
- Optionally validates values in .env and .env.example (format only, no network).
- Flags likely hardcoded secrets in source (heuristic).

Exits 0 on success, 1 if any *error* is reported. Warnings do not change exit code
unless the caller passes --strict.

Stdlib only.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PY_SCAN_ROOTS = (
    "app.py",
    "api_v1.py",
    "billing.py",
    "entity_parser.py",
    "query_understanding.py",
    "search_bots.py",
    "search_protocol.py",
    "bot_crawler.py",
    "reverse_image.py",
    "reverse_image_storage.py",
    "startup_checks.py",
)
PY_SCAN_DIRS = ("retrieval", "osint", "api")
ENV_FILES = (".env.example", ".env")

# All env var names referenced in app code
_ENV_PATTERNS = (
    re.compile(
        r"""os\.environ\.get\(\s*["']([A-Z][A-Z0-9_]*)["']""",
        re.MULTILINE,
    ),
    re.compile(
        r"""os\.environ\[\s*["']([A-Z][A-Z0-9_]*)["']\s*]""",
        re.MULTILINE,
    ),
    re.compile(
        r"""os\.getenv\(\s*["']([A-Z][A-Z0-9_]*)["']""",
        re.MULTILINE,
    ),
    re.compile(
        r"""os\.environ\.setdefault\(\s*["']([A-Z][A-Z0-9_]*)["']""",
        re.MULTILINE,
    ),
)

# likely embedded secrets
_SECRET_ASSIGN_PATTERNS = [
    re.compile(
        r"""=\s*["']([a-z0-9_-]*(?:key|token|secret|password|bearer|api)[a-z0-9_-]*|whsec_[a-zA-Z0-9]{10,}|sk_(?:live|test)_[a-zA-Z0-9]{10,}|re_[a-zA-Z0-9]{10,})["']""",
        re.IGNORECASE,
    ),
    re.compile(
        r"""=\s*["'](eyJ[a-zA-Z0-9_-]{20,}\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+)["']""",  # JWT shape
    ),
    re.compile(
        r"""["']postgresql://(?:postgres\.)?[^:]+:[^"'\s@]{3,}@[^"']+["']""",  # password in url string
    ),
]

_SUPA_URL = re.compile(
    r"^https://[a-z0-9-]+\.supabase\.co/?$", re.IGNORECASE
)
_DB_POOL = re.compile(
    r"postgres\.[a-z0-9-]+@.*:6543/", re.IGNORECASE
)
_DB_POOL_ALT = re.compile(
    r":6543/|:6543\?", re.IGNORECASE
)


def _list_py_files() -> list[Path]:
    out: list[Path] = []
    for name in PY_SCAN_ROOTS:
        p = ROOT / name
        if p.is_file():
            out.append(p)
    for d in PY_SCAN_DIRS:
        base = ROOT / d
        if base.is_dir():
            out.extend(sorted(base.rglob("*.py")))
    return out


def _read_env_key_values(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    data: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            m = re.match(
                r"^#\s*([A-Z][A-Z0-9_]*)(?:\s*=\s*)(.*)$", s
            )
            if m and path.name == ".env.example":
                k, v = m.group(1), m.group(2).split("#", 1)[0].strip()
                data[k] = data.get(k, v)
            continue
        m = re.match(
            r"^([A-Z][A-Z0-9_]*)(?:\s*=\s*)(.*)$", s, re.DOTALL
        )
        if not m:
            continue
        k, v = m.group(1), m.group(2).strip()
        if v.startswith("#"):
            v = ""
        data[k] = v
    return data


def _code_env_names() -> set[str]:
    names: set[str] = set()
    for f in _list_py_files():
        if "test" in str(f) and f.parts[0:1] == ("tests",):
            continue
        try:
            text = f.read_text(encoding="utf-8-sig", errors="replace")
        except OSError:
            continue
        for pat in _ENV_PATTERNS:
            for m in pat.finditer(text):
                names.add(m.group(1))
    return names


def _scan_hardcoded_secrets() -> list[str]:
    err: list[str] = []
    for f in _list_py_files():
        if f.name in ("conftest.py",):
            continue
        try:
            text = f.read_text(encoding="utf-8-sig", errors="replace")
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if line.strip().startswith("#"):
                continue
            for pat in _SECRET_ASSIGN_PATTERNS:
                if pat.search(line) and "os.environ" not in line and "getenv" not in line:
                    if "G-FG3G7DRBW1" in line:  # known GA4 doc default in this repo; skip
                        continue
                    if "0.0.0.0" in line or "localhost" in line:
                        continue
                    err.append(f"{_rel(f)}:{i}: possible hardcoded secret or credential in source")
                    break
    return err


def _rel(f: Path) -> str:
    return f.resolve().relative_to(ROOT).as_posix().replace("\\", "/")


def _validate_env_file(
    path: Path, label: str, errors: list[str], warnings: list[str]
) -> None:
    if not path.is_file():
        return
    d = _read_env_key_values(path)
    s_url = (d.get("SUPABASE_URL") or "").strip().rstrip("/")
    if s_url and not _SUPA_URL.match(s_url):
        errors.append(
            f"{label} SUPABASE_URL must be https://<project-ref>.supabase.co (got: {s_url!r})"
        )
    np_url = (d.get("NEXT_PUBLIC_SUPABASE_URL") or "").strip().rstrip("/")
    if np_url and s_url and np_url != s_url:
        errors.append(
            f"{label}: NEXT_PUBLIC_SUPABASE_URL ({np_url!r}) != SUPABASE_URL ({s_url!r})"
        )
    db = (d.get("SUPABASE_DB_URL") or d.get("DATABASE_URL") or "").strip()
    if db:
        if "6543" not in db and "pooler" in db.lower():
            warnings.append(
                f"{label} SUPABASE_DB_URL should use port 6543 (transaction pooler) for Vercel/serverless"
            )
        if "postgres." not in db.split("@", 1)[0]:
            if "supabase" in db.lower() and "pooler" in db.lower():
                warnings.append(
                    f"{label} SUPABASE_DB_URL user should be postgres.<project-ref> (pooler)"
                )
        if re.search(
            r":(5432)(/|\?|\"|$)", db
        ) and "supabase" in db.lower() and "pooler" not in db.lower():
            warnings.append(
                f"{label} SUPABASE_DB_URL uses direct port 5432; app expects pooler 6543 on Vercel"
            )

    p_ref = (d.get("ABBIEY_SUPABASE_PROJECT_REF") or "").strip()
    if (
        s_url
        and p_ref
        and not p_ref.startswith("<")
        and "placeholder" not in p_ref.lower()
        and p_ref not in s_url
        and f"https://{p_ref}.supabase.co" not in s_url
    ):
        warnings.append(
            f"{label} ABBIEY_SUPABASE_PROJECT_REF ({p_ref!r}) may not match SUPABASE_URL host"
        )


def verify(*, strict: bool = False) -> tuple[list[str], list[str], int]:
    """Return (errors, warnings, exit_code)."""
    errors: list[str] = []
    warnings: list[str] = []

    code_names = _code_env_names()
    example_path = ROOT / ".env.example"
    example_keys = set(_read_env_key_values(example_path).keys()) if example_path.is_file() else set()

    # .env values (optional)
    for ep in (ROOT / ".env",):
        _validate_env_file(ep, str(ep.name), errors, warnings)
    if example_path.is_file():
        _validate_env_file(example_path, ".env.example (sample block)", errors, warnings)

    # code vars not listed in .env.example (advisory)
    if example_keys:
        undocumented = sorted(
            n
            for n in code_names
            if n not in example_keys
            and not n.startswith("RUNNING_")
            and n not in ("VERCEL", "AWS_LAMBDA_FUNCTION_NAME", "K_SERVICE", "RENDER")
        )
        if undocumented:
            head = ", ".join(undocumented[:15])
            tail = f" ... (+{len(undocumented) - 15} more)" if len(undocumented) > 15 else ""
            warnings.append(
                f"{len(undocumented)} code-referenced env var(s) not in .env.example key list: {head}{tail}"
            )

    # Heuristic secret scan
    for msg in _scan_hardcoded_secrets():
        errors.append(msg)

    ex = 0
    if errors:
        ex = 1
    if strict and warnings:
        ex = 1
    return errors, warnings, ex


def main() -> int:
    strict = "--strict" in sys.argv
    err, warn, ex = verify(strict=strict)
    for w in warn:
        print("warning:", w, file=sys.stderr)
    if err:
        print("Env / secret scan failed:\n", file=sys.stderr)
        for e in err:
            print(f"  - {e}", file=sys.stderr)
    else:
        print("env drift / secret scan: ok.")
    return ex


if __name__ == "__main__":
    raise SystemExit(main())
