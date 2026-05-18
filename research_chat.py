"""Research assistant: image understanding, saved chats, Ollama message assembly."""

from __future__ import annotations

import base64
import json
import logging
import os
import re
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

MAX_CHAT_IMAGE_BYTES = 4 * 1024 * 1024
ALLOWED_IMAGE_MIMES = frozenset({"image/jpeg", "image/png", "image/webp", "image/gif"})
MAX_SAVED_CHATS_PER_USER = 40
MAX_MESSAGES_PER_CHAT = 80
MAX_STORED_IMAGE_CHARS = 120_000

_DATA_URL_RE = re.compile(
    r"^data:(image/(?:jpeg|png|webp|gif));base64,([A-Za-z0-9+/=\s]+)$",
    re.I,
)

PG_RESEARCH_CHATS_DDL = """
CREATE TABLE IF NOT EXISTS research_chats (
    id            SERIAL PRIMARY KEY,
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    search_query  TEXT NOT NULL,
    title         TEXT DEFAULT '',
    messages_json TEXT NOT NULL,
    updated_at    TIMESTAMPTZ DEFAULT NOW(),
    created_at    TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_research_chats_user ON research_chats(user_id, updated_at DESC);
"""

SQLITE_RESEARCH_CHATS_DDL = """
CREATE TABLE IF NOT EXISTS research_chats (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL,
    search_query  TEXT NOT NULL,
    title         TEXT DEFAULT '',
    messages_json TEXT NOT NULL,
    updated_at    TEXT DEFAULT (datetime('now')),
    created_at    TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_research_chats_user ON research_chats(user_id, updated_at);
"""


def install_pg_schema(pg_execute: Callable) -> None:
    pg_execute(PG_RESEARCH_CHATS_DDL)


def install_sqlite_schema(sqlite_executescript: Callable) -> None:
    sqlite_executescript(SQLITE_RESEARCH_CHATS_DDL)


def parse_chat_image(raw: Any) -> tuple[str, str] | tuple[None, str]:
    """Return (base64_payload, mime) or (None, error_message)."""
    if raw is None:
        return None, ""
    if isinstance(raw, dict):
        mime = (raw.get("mime") or raw.get("type") or "").strip().lower()
        data = raw.get("data") or raw.get("base64") or ""
        if isinstance(data, str) and data.startswith("data:"):
            return parse_chat_image(data)
        if not isinstance(data, str) or not data.strip():
            return None, "Image data is missing."
        if mime not in ALLOWED_IMAGE_MIMES:
            return None, "Unsupported image type. Use JPEG, PNG, WebP, or GIF."
        try:
            raw_bytes = base64.b64decode(data, validate=True)
        except Exception:
            return None, "Could not read that image. Try another file."
        if len(raw_bytes) > MAX_CHAT_IMAGE_BYTES:
            return None, "Image is too large. Please use a file under 4 MB."
        return data.strip(), mime

    if not isinstance(raw, str) or not raw.strip():
        return None, ""
    s = raw.strip()
    m = _DATA_URL_RE.match(s)
    if not m:
        return None, "Invalid image format."
    mime = m.group(1).lower()
    b64 = re.sub(r"\s+", "", m.group(2))
    try:
        raw_bytes = base64.b64decode(b64, validate=True)
    except Exception:
        return None, "Could not read that image. Try another file."
    if len(raw_bytes) > MAX_CHAT_IMAGE_BYTES:
        return None, "Image is too large. Please use a file under 4 MB."
    return b64, mime


def image_to_data_url(b64: str, mime: str) -> str:
    return f"data:{mime};base64,{b64}"


def normalize_history(
    history: list,
    *,
    max_turns: int,
    max_message_len: int,
) -> tuple[list[dict], str | None]:
    if not isinstance(history, list):
        return [], "history"
    if len(history) > max_turns * 2:
        history = history[-(max_turns * 2) :]
    out: list[dict] = []
    for h in history:
        if not isinstance(h, dict):
            return [], "history"
        role = h.get("role", "")
        content = h.get("content", "")
        if role not in ("user", "assistant"):
            return [], "history"
        if not isinstance(content, str) or len(content) > max_message_len:
            return [], "history"
        entry: dict[str, Any] = {"role": role, "content": content}
        if role == "user" and h.get("image"):
            img_b64, img_mime = parse_chat_image(h.get("image"))
            if img_b64 and img_mime:
                entry["image"] = image_to_data_url(img_b64, img_mime)
        out.append(entry)
    return out, None


def _ollama_user_message(content: str, image_b64: str | None = None) -> dict:
    msg: dict[str, Any] = {"role": "user", "content": content}
    if image_b64:
        msg["images"] = [image_b64]
    return msg


def build_ollama_messages(
    *,
    query: str,
    context: str,
    history: list[dict],
    message: str,
    image_b64: str | None,
    image_mime: str | None,
) -> list[dict]:
    vision_note = ""
    if image_b64:
        vision_note = (
            " The user may attach images — describe what you see and relate it to the search topic when relevant."
        )
    system_context = (
        "You are a thoughtful research assistant for abbiey.search. "
        "Write in clear, flowing prose with short paragraphs. "
        "Lead with a direct answer, then supporting detail. "
        "Cite sources by number [1], [2]. Avoid filler, hype, or rushed phrasing."
        f"{vision_note}\n\n{context}"
    )
    messages: list[dict] = [{"role": "system", "content": system_context}]
    messages.append(
        {
            "role": "assistant",
            "content": f"I've reviewed the search results about '{query}'. What would you like to know?",
        }
    )
    for h in history[-6:]:
        role = h.get("role", "user")
        content = h.get("content", "")
        if role not in ("user", "assistant"):
            continue
        if role == "user" and h.get("image"):
            img_b64, img_mime = parse_chat_image(h.get("image"))
            if img_b64 and img_mime:
                user_text = content or "Please describe this image in the context of my search."
                messages.append(_ollama_user_message(user_text, img_b64))
                continue
        messages.append({"role": role, "content": content})

    user_text = message
    if not user_text and image_b64:
        user_text = "What can you tell me about this image in relation to my search?"
    messages.append(_ollama_user_message(user_text, image_b64 if image_b64 else None))
    return messages


def messages_have_images(messages: list[dict]) -> bool:
    return any(isinstance(m, dict) and m.get("images") for m in messages)


def call_ollama_chat(
    messages: list[dict],
    *,
    http_post: Callable,
    base_url: str,
    model: str,
    vision_model: str,
    timeout: float,
) -> str:
    use_vision = messages_have_images(messages)
    chosen = (vision_model or model).strip() if use_vision else model
    ollama_url = f"{(base_url or 'http://localhost:11434').rstrip('/')}/api/chat"
    resp = http_post(
        ollama_url,
        json={"model": chosen, "messages": messages, "stream": False},
        timeout=timeout,
    )
    resp.raise_for_status()
    body = resp.json()
    content = (body.get("message") or {}).get("content") or ""
    if not content.strip():
        raise RuntimeError("Empty AI response")
    return content


def trim_messages_for_storage(messages: list[dict]) -> list[dict]:
    """Keep chat JSON bounded for DB / localStorage."""
    trimmed = messages[-MAX_MESSAGES_PER_CHAT:]
    out = []
    for m in trimmed:
        if not isinstance(m, dict):
            continue
        role = m.get("role")
        if role not in ("user", "assistant"):
            continue
        entry: dict[str, Any] = {"role": role, "content": str(m.get("content") or "")[:12_000]}
        img = m.get("image")
        if role == "user" and isinstance(img, str) and img.startswith("data:image/"):
            if len(img) <= MAX_STORED_IMAGE_CHARS:
                entry["image"] = img
        out.append(entry)
    return out


def default_chat_title(messages: list[dict], search_query: str) -> str:
    for m in messages:
        if m.get("role") == "user" and (m.get("content") or "").strip():
            text = str(m["content"]).strip()
            if m.get("image") and not text:
                return f"Image · {search_query}"[:120]
            return text[:120]
    return search_query[:120]


def list_saved_chats(user_id: int, execute_fn: Callable, *, search_query: str = "") -> list[dict]:
    q = (search_query or "").strip()
    if q:
        rows = execute_fn(
            "SELECT id, search_query, title, updated_at, created_at, messages_json "
            "FROM research_chats WHERE user_id=? AND search_query=? "
            "ORDER BY updated_at DESC LIMIT ?",
            [user_id, q[:500], MAX_SAVED_CHATS_PER_USER],
        )
    else:
        rows = execute_fn(
            "SELECT id, search_query, title, updated_at, created_at, messages_json "
            "FROM research_chats WHERE user_id=? ORDER BY updated_at DESC LIMIT ?",
            [user_id, MAX_SAVED_CHATS_PER_USER],
        )
    out = []
    for r in rows or []:
        msgs = []
        try:
            msgs = json.loads(r.get("messages_json") or "[]")
        except json.JSONDecodeError:
            msgs = []
        out.append(
            {
                "id": r.get("id"),
                "query": r.get("search_query") or "",
                "title": (r.get("title") or "").strip() or default_chat_title(msgs, r.get("search_query") or ""),
                "updated_at": r.get("updated_at"),
                "message_count": len(msgs),
            }
        )
    return out


def get_saved_chat(user_id: int, chat_id: int, execute_fn: Callable) -> dict | None:
    rows = execute_fn(
        "SELECT id, search_query, title, updated_at, created_at, messages_json "
        "FROM research_chats WHERE id=? AND user_id=? LIMIT 1",
        [chat_id, user_id],
    )
    if not rows:
        return None
    r = rows[0]
    try:
        messages = json.loads(r.get("messages_json") or "[]")
    except json.JSONDecodeError:
        messages = []
    return {
        "id": r.get("id"),
        "query": r.get("search_query") or "",
        "title": (r.get("title") or "").strip() or default_chat_title(messages, r.get("search_query") or ""),
        "updated_at": r.get("updated_at"),
        "messages": messages,
    }


def save_chat(
    user_id: int,
    execute_fn: Callable,
    *,
    search_query: str,
    messages: list[dict],
    chat_id: int | None = None,
    title: str = "",
) -> dict:
    q = (search_query or "").strip()[:500]
    if not q:
        raise ValueError("query_required")
    stored = trim_messages_for_storage(messages)
    if not stored:
        raise ValueError("messages_required")
    payload = json.dumps(stored, ensure_ascii=False)
    t = (title or "").strip()[:200] or default_chat_title(stored, q)

    if chat_id:
        execute_fn(
            "UPDATE research_chats SET search_query=?, title=?, messages_json=?, updated_at=CURRENT_TIMESTAMP "
            "WHERE id=? AND user_id=?",
            [q, t, payload, int(chat_id), user_id],
        )
        return {"id": int(chat_id), "title": t}

    rows = execute_fn(
        "INSERT INTO research_chats (user_id, search_query, title, messages_json) VALUES (?,?,?,?)",
        [user_id, q, t, payload],
        return_id=True,
    )
    new_id = int(rows[0]["id"]) if rows else None
    _prune_old_chats(user_id, execute_fn)
    return {"id": new_id, "title": t}


def delete_saved_chat(user_id: int, chat_id: int, execute_fn: Callable) -> bool:
    before = execute_fn(
        "SELECT id FROM research_chats WHERE id=? AND user_id=? LIMIT 1",
        [chat_id, user_id],
    )
    if not before:
        return False
    execute_fn("DELETE FROM research_chats WHERE id=? AND user_id=?", [chat_id, user_id])
    return True


def _prune_old_chats(user_id: int, execute_fn: Callable) -> None:
    rows = execute_fn(
        "SELECT id FROM research_chats WHERE user_id=? ORDER BY updated_at DESC",
        [user_id],
    )
    if len(rows or []) <= MAX_SAVED_CHATS_PER_USER:
        return
    for r in rows[MAX_SAVED_CHATS_PER_USER :]:
        execute_fn("DELETE FROM research_chats WHERE id=? AND user_id=?", [r["id"], user_id])


def vision_model_name() -> str:
    return (os.getenv("OLLAMA_VISION_MODEL") or os.getenv("OLLAMA_MODEL") or "llava:7b").strip()
