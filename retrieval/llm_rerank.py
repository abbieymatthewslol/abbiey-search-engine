"""Optional LLM re-ordering of text search hits (titles + snippets only)."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable

logger = logging.getLogger(__name__)

_MAX_ITEMS = 12
_MAX_PROMPT_CHARS = 6000


def rerank_text_hits_with_llm(
    query: str,
    results: list[dict[str, Any]],
    *,
    chat_fn: Callable[..., str],
    max_items: int = _MAX_ITEMS,
) -> list[dict[str, Any]]:
    """Re-order first *max_items* results using *chat_fn* (e.g. ``_ollama_chat``).

    On any failure, returns *results* unchanged.
    """
    if not query or not results or len(results) < 2:
        return results
    n = min(max(2, int(max_items)), len(results), _MAX_ITEMS)
    head = results[:n]
    tail = results[n:]

    lines: list[str] = []
    for i, r in enumerate(head):
        title = (r.get("title") or "")[:180]
        snippet = (r.get("body") or r.get("description") or r.get("snippet") or "")[:240]
        lines.append(f"{i + 1}. {title} | {snippet}")

    blob = "\n".join(lines)
    if len(blob) > _MAX_PROMPT_CHARS:
        blob = blob[:_MAX_PROMPT_CHARS]

    messages = [
        {
            "role": "system",
            "content": (
                "You reorder web search results by relevance to the user's query. "
                "Output ONLY a JSON array of integers — the new order of line numbers "
                "(1-based), most relevant first. Include every number exactly once. "
                "No markdown, no explanation."
            ),
        },
        {
            "role": "user",
            "content": f"Query: {query.strip()[:400]}\n\nResults (one per line):\n{blob}",
        },
    ]
    try:
        raw = chat_fn(messages, timeout=12.0)
    except Exception:
        logger.exception("llm_rerank_chat_failed")
        return results

    order = _parse_order_array(raw, n)
    if order is None:
        return results

    reordered = [head[j] for j in order]
    return reordered + tail


def _parse_order_array(raw: str, n: int) -> list[int] | None:
    s = (raw or "").strip()
    if not s:
        return None
    # Strip markdown code fence if present
    s = re.sub(r"^```(?:json)?\s*", "", s, flags=re.I)
    s = re.sub(r"\s*```\s*$", "", s)
    try:
        arr = json.loads(s)
    except json.JSONDecodeError:
        m = re.search(r"\[[\d,\s]+\]", s)
        if not m:
            return None
        try:
            arr = json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    if not isinstance(arr, list) or len(arr) != n:
        return None
    wanted = set(range(1, n + 1))
    try:
        nums = [int(x) for x in arr]
    except (TypeError, ValueError):
        return None
    if set(nums) != wanted:
        return None
    return [i - 1 for i in nums]
