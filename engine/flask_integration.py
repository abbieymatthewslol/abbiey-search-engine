from __future__ import annotations

from engine.engine import ZeroClickEngine
from engine.renderers.jinja_helpers import render_zero_click_html


zero_click_engine = ZeroClickEngine()


def build_zero_click_block(query: str, search_results: list[dict], weather_payload: dict | None = None):
    answer = zero_click_engine.answer(
        query=query,
        search_results=search_results,
        weather_payload=weather_payload,
        locale="en-AU",
        region="AU",
    )
    if not zero_click_engine.should_show(answer, threshold=0.82):
        return None, None

    return answer, render_zero_click_html(answer)
