# -*- coding: utf-8 -*-
"""
Compact, deploy-shipped product facts for chatbots: intent hints, fallbacks, and escalation.
Update when the public UI (templates/static) gains major features.
"""

from __future__ import annotations

import hashlib
import re

# Appended to every /api/chatbot-chat system prompt so the model disambiguates product vs generic.
PRODUCT_CHATBOT_SYSTEM_SUFFIX = (

    "\n\n---\n**abbiey.search product context (ground truth for user questions about this site):**\n"
    "- **Voice / mic input:** the search box has a microphone button for **browser speech-to-text** "
    "(Web Speech API). It fills the query field; it is not a separate 'voice search mode'.\n"
    "- **Drag to reorder results:** on results pages, use the **grip handle** on each result to "
    "drag and reorder. Order can be stored (see settings / result prefs).\n"
    "- **Resizable UI:** drag the **gutter** between the result list and the preview panel; "
    "the **research chat** panel can be resized from its top/left edge (double-click edge to reset).\n"
    "- **Tabs:** All, Images, News, Videos, Code, Deep Web — Deep Web uses Ahmia + fallbacks; "
    "read the on-page notices.\n"
    "- **Personalization vs voice:** 'personalization' means themes, density, region, accounts/bookmarks; "
    "'mic' / 'voice' means the speech input button next to the search field.\n"
    "- If the user mixes topics, **ask one short clarifying question** before a long answer.\n"
    "- **Transparency:** abbiey.search does not run third-party ad trackers; prefer describing "
    "on-device or stated behavior over claiming other sites' practices.\n"
    "---\n"
)

# When the LLM is unavailable, we still answer common product questions without 503 loops.
# Avoid bare substring "mic" (matches unrelated words) — use word boundary for short tokens.
def _w(m: str, *words: str) -> bool:
    s = m.lower()
    for w in words:
        if len(w) <= 3:
            if re.search(rf"(?i)\b{re.escape(w)}\b", s):
                return True
        elif w in s:
            return True
    return False


def _voice_intent(m: str) -> bool:
    s = m.lower()
    if _w(s, "mic", "stt"):
        return True
    for ph in (
        "voice", "microphone", "speech", "dictat", "speak to", "talk to",
        "audio input", "transcri", "web speech", "webkit",
    ):
        if ph in s:
            return True
    return False


def _reorder_intent(m: str) -> bool:
    s = m.lower()
    if "reorder" in s or "grip" in s or "result order" in s or "order of results" in s:
        return True
    if "sort" in s and "result" in s:
        return True
    if "move" in s and "result" in s:
        return True
    if "drag" in s and ("result" in s or "hit" in s or "listing" in s or "grip" in s):
        return True
    return False
PERSONALIZE_KEYWORDS = (
    "personaliz", "preference", "setting", "theme", "accent", "density", "region",
    "account", "bookmark", "signed in", "sign in", "login",
)
CHAT_KEYWORDS = (
    "chat", "assistant", "research assistant", "side panel", "ai panel", "ask about results",
)
DEEP_KEYWORDS = (
    "onion", "deep web", "tor", "ahmia", ".onion", "dark web",
)
GENERIC_FALLBACKS = [
    (
        "I am not sure which part of abbiey.search you mean. "
        "Are you asking about **voice (mic) search**, **drag-to-reorder results**, **themes/settings**, "
        "or the **research assistant** panel? A few words of context helps."
    ),
    (
        "Did you mean: **using the mic** next to the search box, **reordering** results with the drag handle, "
        "or **personalization** (theme/region)? Tell me which and I will go into detail."
    ),
    (
        "To give a precise answer: is this about **voice input**, **result order / drag-to-reorder**, "
        "or **appearance / account** settings?"
    ),
    (
        "abbiey.search has several UIs: **mic button** (speech to text), **grip = drag to reorder** on results, "
        "and **resizable** preview and chat. Which one should we focus on?"
    ),
    (
        "If something feels broken, say whether it is **microphone / voice**, **reordering** hit lists, "
        "or the **chat** panel on the right — I will address that path first."
    ),
]

ESCALATION_MESSAGE = (
    "I still may not be matching your intent. "
    "Try running a **web search in the main box** first, then use the **research assistant** for follow-ups, "
    "or rephrase with one feature name (e.g. *mic button*, *drag results*, *Deep Web tab*). "
    "The site is **unfiltered** by default: results are from external sources, not a curated 'safe list'."
)


def _norm(s: str) -> str:
    return " ".join((s or "").lower().split())


def _hash_pick(seed: str, n: int) -> int:
    h = int(hashlib.sha256(seed.encode("utf-8")).hexdigest()[:8], 16)
    return h % n


def product_chatbot_fallback_reply(message: str, history: list) -> str:
    """
    Rule-based product help when Ollama is down. Rotates phrasing; escalates after repeated generic help.
    """
    m = _norm(message)
    if not m:
        return GENERIC_FALLBACKS[0]

    last_asst = ""
    for h in reversed(history or []):
        if isinstance(h, dict) and h.get("role") == "assistant":
            c = h.get("content", "")
            if isinstance(c, str):
                last_asst = c
            break
    escalate = any(
        x in last_asst
        for x in (
            "I am not sure which part of abbiey.search",
            "Did you mean:",
            "To give a precise answer:",
            "abbiey.search has several UIs",
            "If something feels broken",
        )
    )
    if escalate and len(m) < 200:
        return ESCALATION_MESSAGE

    if _voice_intent(m):
        return (
            "**Voice / mic in abbiey.search:** use the **microphone button** in the search bar. "
            "The browser (Chrome/Edge/Safari where supported) turns speech into **text in the query field** — "
            "it is the same as typing, not a special voice-only mode. "
            "If the button is missing, the browser may not support Web Speech, or the feature flag may be off."
        )
    if _reorder_intent(m):
        return (
            "**Reordering results:** on a results page, use the **drag handle** (grip) on each result. "
            "Drag up or down to **change the order**; preferences can persist depending on your settings. "
            "This is separate from the **preview** panel — the vertical bar between list and preview only **resizes** them."
        )
    if _w(m, *DEEP_KEYWORDS) and not _voice_intent(m):
        return (
            "**Deep Web tab** searches .onion-related pages via **Ahmia** (and fallbacks if needed). "
            "Read the **warning banner** — open only links you understand; the site does not require Tor in "
            "the browser for the clearnet index, but .onion links need Tor to visit."
        )
    if any(k in m for k in CHAT_KEYWORDS) and not _reorder_intent(m):
        return (
            "**Research assistant:** open it from the results UI; it uses your **current search** as context. "
            "Run a search first, then ask follow-up questions. You can **resize** the panel from the top or left edge."
        )
    if any(k in m for k in PERSONALIZE_KEYWORDS) and not _voice_intent(m):
        return (
            "**Personalization** here means **theme** (light/dark), **accent colors**, **density**, "
            "**region**, and (when signed in) **bookmarks** and related preferences. "
            "It is not the same as the **mic button** — that only converts speech to your query text."
        )

    seed = f"{m}|{len(history or [])}"
    return GENERIC_FALLBACKS[_hash_pick(seed, len(GENERIC_FALLBACKS))]
