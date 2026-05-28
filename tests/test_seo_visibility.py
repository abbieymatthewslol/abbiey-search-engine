import re


def _get_home_response(client):
    return client.get("/", follow_redirects=True)


def _get_home_html(client):
    return _get_home_response(client).get_data(as_text=True)


def test_home_has_canonical_and_indexable(client):
    resp = _get_home_response(client)
    html = resp.get_data(as_text=True)

    assert resp.status_code == 200
    assert 'rel="canonical"' in html
    assert "noindex" not in html.lower()


def test_home_has_single_canonical_tag(client):
    html = _get_home_html(client)

    canonical_tags = re.findall(
        r"<link[^>]*rel=[\"']canonical[\"'][^>]*>",
        html,
        flags=re.IGNORECASE,
    )

    assert len(canonical_tags) == 1


def test_home_canonical_href_is_absolute_url(client):
    html = _get_home_html(client)

    match = re.search(
        r"<link[^>]*rel=[\"']canonical[\"'][^>]*href=[\"']([^\"']+)[\"'][^>]*>",
        html,
        flags=re.IGNORECASE,
    )

    assert match is not None
    href = match.group(1)
    assert href.startswith(("https://", "http://"))
    assert "/search" in href


def test_home_robots_meta_does_not_use_noindex(client):
    html = _get_home_html(client)

    robots_tag = re.search(
        r"<meta[^>]*name=[\"']robots[\"'][^>]*>",
        html,
        flags=re.IGNORECASE,
    )

    if robots_tag is not None:
        assert "noindex" not in robots_tag.group(0).lower()


def test_home_seo_tags_render_in_head(client):
    html = _get_home_html(client).lower()

    head_close_idx = html.find("</head>")
    canonical_idx = html.find('rel="canonical"')
    robots_idx = html.find('name="robots"')

    assert head_close_idx != -1
    assert canonical_idx != -1
    assert canonical_idx < head_close_idx
    if robots_idx != -1:
        assert robots_idx < head_close_idx


def test_home_returns_html_content_type(client):
    resp = _get_home_response(client)

    assert resp.status_code == 200
    assert "text/html" in (resp.content_type or "").lower()