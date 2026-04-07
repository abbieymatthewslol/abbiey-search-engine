from __future__ import annotations

from markupsafe import Markup, escape

from engine.models import ZeroClickAnswer


def render_zero_click_html(answer: ZeroClickAnswer) -> Markup:
    facts_html = ""
    if answer.facts:
        items = "".join(f"<li>{escape(item)}</li>" for item in answer.facts[:4])
        facts_html = f'<ul class="zc-facts">{items}</ul>'

    warnings_html = ""
    if answer.warnings:
        warnings_html = "".join(f'<div class="zc-warning">{escape(item)}</div>' for item in answer.warnings[:2])

    sources_html = ""
    if answer.sources:
        links = []
        for source in answer.sources[:4]:
            links.append(
                f'<a href="{escape(source.url)}" target="_blank" rel="noopener noreferrer">{escape(source.label)}</a>'
            )
        sources_html = '<div class="zc-sources">' + " · ".join(links) + "</div>"

    html = f"""
<section class="zero-click-card" data-answer-type="{escape(answer.answer_type)}">
    <div class="zero-click-label">Direct answer</div>
    <h2 class="zero-click-title">{escape(answer.title)}</h2>
    <p class="zero-click-body">{escape(answer.summary)}</p>
    {facts_html}
    {warnings_html}
    {sources_html}
    <div class="zero-click-meta">
        Confidence: {answer.confidence:.0%}
        <span class="zc-confidence-explainer">{escape(answer.confidence_explanation)}</span>
    </div>
</section>
""".strip()

    return Markup(html)
