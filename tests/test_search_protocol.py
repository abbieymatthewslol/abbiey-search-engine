from unittest.mock import patch


def test_protocol_answer_returns_markdown(client, mock_ddg):
    with patch(
        "app._ollama_chat",
        return_value="## DIRECT\nTest answer [1]. (Confidence: 0.70)\n\n## CONTEXT\nContext [2].",
    ):
        resp = client.get("/api/protocol-answer?q=what+is+python&depth=standard")
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        assert "## Source Triage" in body
        assert "## DIRECT" in body
        assert "## CONTEXT" in body
        assert "<sup>[1](#source-1)</sup>" in body
        assert "## Evidence Hierarchy" in body


def test_protocol_answer_quick_only_direct_block(client, mock_ddg):
    with patch(
        "app._ollama_chat",
        return_value="## DIRECT\nOne sentence [1]. (Confidence: 0.55)",
    ):
        resp = client.get("/api/protocol-answer?q=test&depth=quick")
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        assert "## DIRECT" in body
        assert "## CONTEXT" not in body
        assert "## DISSENT" not in body


def test_protocol_answer_deep_includes_related_section(client, mock_ddg):
    with patch(
        "app._ollama_chat",
        return_value=(
            "## DIRECT\nAnswer [1]. (Confidence: 0.60)\n\n"
            "## CONTEXT\nMore [1].\n\n"
            "## DISSENT\nAlt [2].\n\n"
            "## RELATED\n- q1\n- q2\n"
        ),
    ):
        resp = client.get("/api/protocol-answer?q=test&depth=deep")
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        assert "## RELATED" in body


def test_protocol_answer_safety_sanitizes_numbered_steps(client, mock_ddg):
    with patch(
        "app._ollama_chat",
        return_value=(
            "## DIRECT\nHigh-level overview [1]. (Confidence: 0.40)\n\n"
            "1. Do a thing\n"
            "2. Do another thing\n"
        ),
    ):
        resp = client.get("/api/protocol-answer?q=how+to+hack+a+credit+card&depth=standard")
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        assert "Context warning" in body
        assert "1. Do a thing" not in body
        assert "Procedural instructions were removed" in body

