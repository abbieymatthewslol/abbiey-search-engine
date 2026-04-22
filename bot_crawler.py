"""Chunked, serverless-safe crawler for user-defined search bots.

Why this module exists
----------------------
The synchronous ``crawl_bot_pages`` path in ``search_bots.py`` can crawl up to
30 pages with a 6s per-page timeout. On Vercel that's well past the default
10s function timeout (and even the 60s max tier), so ``POST /api/user/search-
bots/<id>/crawl`` was known to time out mid-crawl.

This module replaces the "one long request" model with a checkpointed queue
stored in ``user_search_bot_crawl_jobs`` (see migration). Each invocation
pulls **at most 3 pages**, persists the remaining queue + seen URLs, and
returns. A GitHub Actions cron ticks ``POST /admin/api/bot-crawl-step`` every
few minutes so jobs drain without the user keeping a tab open.

Public surface:
    ensure_jobs_schema()     - idempotent CREATE TABLE used at startup + per
                               request (SQLite fallback has no migrations).
    enqueue_job(...)         - start/reset a job for a bot.
    step_job(...)            - fetch up to ``pages_per_invocation`` pages for
                               one bot, persist state, return progress.
    step_next_job(...)       - pick the oldest queued/running job and run one
                               step (used by /admin/api/bot-crawl-step).
    get_job_status(...)      - read current progress for the UI.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Callable, Iterable, Optional

from search_bots import (
    DEFAULT_PAGES_PER_INVOCATION,
    crawl_bot_pages_step,
    normalize_http_seed,
    parse_json_list,
)

logger = logging.getLogger(__name__)

# Hard cap per bot - mirrors the user-facing UI cap.
MAX_BOT_HOSTS = 20
MAX_BOT_SEEDS = 20


@dataclass
class JobStatus:
    bot_id: int
    state: str  # queued | running | done | failed
    pages_done: int
    pages_total: int
    error: Optional[str]
    updated_at: Optional[str]

    def to_dict(self) -> dict:
        return {
            "bot_id": self.bot_id,
            "state": self.state,
            "pages_done": self.pages_done,
            "pages_total": self.pages_total,
            "error": self.error,
            "updated_at": self.updated_at,
        }


# The exec callable matches ``_users_execute(sql, args, return_id=False)`` in
# app.py. Kept as a parameter to avoid a circular import.
ExecFn = Callable[..., list]


def ensure_jobs_schema(execute: ExecFn) -> None:
    """Create the job table if missing. Safe to call on every request."""
    execute(
        """
        CREATE TABLE IF NOT EXISTS user_search_bot_crawl_jobs (
            bot_id INTEGER PRIMARY KEY,
            state TEXT NOT NULL DEFAULT 'queued',
            queue_json TEXT NOT NULL DEFAULT '[]',
            seen_json TEXT NOT NULL DEFAULT '[]',
            pages_done INTEGER NOT NULL DEFAULT 0,
            pages_total INTEGER NOT NULL DEFAULT 30,
            max_depth INTEGER NOT NULL DEFAULT 1,
            allow_hosts_json TEXT NOT NULL DEFAULT '[]',
            error TEXT,
            created_at TEXT,
            updated_at TEXT
        )
        """
    )


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def enqueue_job(
    execute: ExecFn,
    *,
    bot_id: int,
    seed_urls: Iterable[str],
    allow_hosts: list[str],
    max_depth: int,
    max_pages: int,
) -> JobStatus:
    """Create or reset a crawl job for ``bot_id``. Returns current status."""
    ensure_jobs_schema(execute)

    seeds: list[tuple[str, int]] = []
    for s in seed_urls or []:
        n = normalize_http_seed(s, allow_hosts)
        if n:
            seeds.append([n, 0])

    if not seeds:
        _upsert_job(
            execute,
            bot_id=bot_id,
            state="failed",
            queue=[],
            seen=[],
            allow_hosts=allow_hosts,
            max_depth=max_depth,
            max_pages=max_pages,
            pages_done=0,
            error="No valid seed URLs for the allowed hosts.",
        )
        return JobStatus(bot_id, "failed", 0, max_pages, "No valid seed URLs for the allowed hosts.", _now())

    _upsert_job(
        execute,
        bot_id=bot_id,
        state="queued",
        queue=seeds,
        seen=[],
        allow_hosts=allow_hosts,
        max_depth=max_depth,
        max_pages=max_pages,
        pages_done=0,
        error=None,
    )
    return JobStatus(bot_id, "queued", 0, max_pages, None, _now())


def step_job(
    execute: ExecFn,
    *,
    bot_id: int,
    persist_page: Callable[[int, dict], None],
    clear_pages: Callable[[int], None],
    pages_per_invocation: int = DEFAULT_PAGES_PER_INVOCATION,
) -> JobStatus:
    """Run a single crawl chunk for ``bot_id``.

    ``persist_page`` is called once per new page (caller writes to
    ``user_search_bot_pages``). ``clear_pages`` is called the first time a job
    transitions from queued -> running so stale results for the bot don't
    linger.
    """
    ensure_jobs_schema(execute)
    rows = execute(
        "SELECT bot_id, state, queue_json, seen_json, pages_done, pages_total, max_depth, allow_hosts_json, error "
        "FROM user_search_bot_crawl_jobs WHERE bot_id=? LIMIT 1",
        [bot_id],
    )
    if not rows:
        return JobStatus(bot_id, "failed", 0, 0, "No job queued for this bot.", _now())

    row = rows[0]
    state = (row.get("state") or "queued").strip()
    if state in {"done", "failed"}:
        return JobStatus(
            bot_id,
            state,
            int(row.get("pages_done") or 0),
            int(row.get("pages_total") or 0),
            row.get("error"),
            None,
        )

    queue_raw = row.get("queue_json") or "[]"
    seen_raw = row.get("seen_json") or "[]"
    try:
        queue = [tuple(x) for x in json.loads(queue_raw)]
    except Exception:
        queue = []
    try:
        seen = list(json.loads(seen_raw))
    except Exception:
        seen = []

    allow_hosts = parse_json_list(row.get("allow_hosts_json"), max_items=MAX_BOT_HOSTS, max_len_each=120)
    max_depth = int(row.get("max_depth") or 1)
    max_pages = int(row.get("pages_total") or 30)
    pages_done = int(row.get("pages_done") or 0)

    if state == "queued":
        # First tick: wipe any previous corpus so the UI shows the fresh crawl.
        try:
            clear_pages(bot_id)
        except Exception:
            logger.exception("bot_crawler_clear_pages_failed bot_id=%s", bot_id)

    started = time.time()
    new_pages, remaining_queue, new_seen, err = crawl_bot_pages_step(
        queue=queue,
        seen=seen,
        allow_hosts=allow_hosts,
        max_depth=max_depth,
        max_pages=max_pages,
        pages_per_invocation=pages_per_invocation,
    )
    elapsed = time.time() - started

    for p in new_pages:
        try:
            persist_page(bot_id, p)
        except Exception:
            logger.exception("bot_crawler_persist_page_failed bot_id=%s url=%s", bot_id, p.get("url"))

    pages_done += len(new_pages)

    if err:
        new_state = "failed"
    elif not remaining_queue or pages_done >= max_pages:
        new_state = "done"
    else:
        new_state = "running"

    final_error = err or (None if new_state != "failed" else "Crawl step failed.")
    _upsert_job(
        execute,
        bot_id=bot_id,
        state=new_state,
        queue=remaining_queue,
        seen=new_seen,
        allow_hosts=allow_hosts,
        max_depth=max_depth,
        max_pages=max_pages,
        pages_done=pages_done,
        error=final_error,
    )

    logger.info(
        "bot_crawler_step bot_id=%s state=%s pages_done=%s elapsed=%.2fs",
        bot_id,
        new_state,
        pages_done,
        elapsed,
    )
    return JobStatus(bot_id, new_state, pages_done, max_pages, final_error, _now())


def step_next_job(
    execute: ExecFn,
    *,
    persist_page: Callable[[int, dict], None],
    clear_pages: Callable[[int], None],
    pages_per_invocation: int = DEFAULT_PAGES_PER_INVOCATION,
) -> Optional[JobStatus]:
    """Pick the oldest pending job and run a step for it. Returns None if idle."""
    ensure_jobs_schema(execute)
    rows = execute(
        "SELECT bot_id FROM user_search_bot_crawl_jobs "
        "WHERE state IN ('queued', 'running') ORDER BY updated_at ASC LIMIT 1"
    )
    if not rows:
        return None
    bid = int(rows[0].get("bot_id"))
    return step_job(
        execute,
        bot_id=bid,
        persist_page=persist_page,
        clear_pages=clear_pages,
        pages_per_invocation=pages_per_invocation,
    )


def get_job_status(execute: ExecFn, *, bot_id: int) -> Optional[JobStatus]:
    ensure_jobs_schema(execute)
    rows = execute(
        "SELECT bot_id, state, pages_done, pages_total, error, updated_at "
        "FROM user_search_bot_crawl_jobs WHERE bot_id=? LIMIT 1",
        [bot_id],
    )
    if not rows:
        return None
    r = rows[0]
    return JobStatus(
        int(r.get("bot_id")),
        r.get("state") or "queued",
        int(r.get("pages_done") or 0),
        int(r.get("pages_total") or 0),
        r.get("error"),
        r.get("updated_at"),
    )


def _upsert_job(
    execute: ExecFn,
    *,
    bot_id: int,
    state: str,
    queue: list,
    seen: list,
    allow_hosts: list[str],
    max_depth: int,
    max_pages: int,
    pages_done: int,
    error: Optional[str],
) -> None:
    now = _now()
    qs = json.dumps([list(x) for x in queue], ensure_ascii=False)
    ss = json.dumps(list(seen), ensure_ascii=False)
    ah = json.dumps(allow_hosts, ensure_ascii=False)

    existing = execute(
        "SELECT bot_id FROM user_search_bot_crawl_jobs WHERE bot_id=? LIMIT 1", [bot_id]
    )
    if existing:
        execute(
            "UPDATE user_search_bot_crawl_jobs SET state=?, queue_json=?, seen_json=?, "
            "pages_done=?, pages_total=?, max_depth=?, allow_hosts_json=?, error=?, updated_at=? "
            "WHERE bot_id=?",
            [state, qs, ss, pages_done, max_pages, max_depth, ah, error, now, bot_id],
        )
    else:
        execute(
            "INSERT INTO user_search_bot_crawl_jobs "
            "(bot_id, state, queue_json, seen_json, pages_done, pages_total, max_depth, allow_hosts_json, error, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            [bot_id, state, qs, ss, pages_done, max_pages, max_depth, ah, error, now, now],
        )
