from pathlib import Path


def test_dark_theme_search_input_keeps_explicit_text_color_contract():
    css = Path("static/style.css").read_text(encoding="utf-8")
    assert "[data-theme=\"dark\"] #search-input" in css
    assert "color: var(--search-input-color, #111827) !important;" in css
    assert "-webkit-text-fill-color: var(--search-input-color, #111827) !important;" in css


def test_search_input_autofill_keeps_search_bar_colors():
    css = Path("static/style.css").read_text(encoding="utf-8")
    assert "[data-theme=\"dark\"] #search-input:-webkit-autofill" in css
    assert "[data-theme=\"light\"] #search-input:-webkit-autofill" in css
    assert "-webkit-box-shadow: 0 0 0 1000px var(--search-surface-focus, #ffffff) inset !important;" in css
