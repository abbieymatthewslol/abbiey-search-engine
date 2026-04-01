"""Privacy-local text vectors (hashing trick) + cosine similarity — no network."""

from __future__ import annotations

import hashlib
import math
import re
from functools import lru_cache

_DIM = 256


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _bucket(s: str) -> int:
    return int(hashlib.md5(s.encode("utf-8")).hexdigest(), 16) % _DIM


@lru_cache(maxsize=4096)
def embed_text(text: str) -> tuple[float, ...]:
    """Fixed-size sparse-ish vector from hashed word n-grams (local, deterministic)."""
    if not text:
        return tuple(0.0 for _ in range(_DIM))
    vec = [0.0] * _DIM
    toks = _tokens(text)[:200]
    for i, w in enumerate(toks):
        h = _bucket(w)
        vec[h] += 1.0
        if i + 1 < len(toks):
            bg = f"{w}_{toks[i + 1]}"
            h2 = _bucket(bg)
            vec[h2] += 0.5
    # L2 normalize
    norm = math.sqrt(sum(x * x for x in vec))
    if norm > 0:
        vec = [x / norm for x in vec]
    return tuple(vec)


def cosine_similarity(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    if len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(a, b))
