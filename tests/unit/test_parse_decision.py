"""Tests for parseDecision — judge output parsing."""

from workshop_agent import parse_decision


def test_parses_clean_json():
    raw = '{"verdict": "approve", "reason": "looks good", "findings": []}'
    d = parse_decision(raw)
    assert d.verdict == "approve"
    assert d.reason == "looks good"
    assert d.findings == []
    assert d.raw == raw


def test_extracts_json_from_prose():
    raw = 'Here is my verdict:\n{"verdict": "request-changes", "reason": "security issue", "findings": [{"agent": "security", "severity": "block", "note": "SQL injection"}]}\nEnd.'
    d = parse_decision(raw)
    assert d.verdict == "request-changes"
    assert d.reason == "security issue"
    assert len(d.findings) == 1


def test_degrades_on_non_json():
    raw = "This is just plain text with no JSON"
    d = parse_decision(raw)
    assert d.verdict == "unknown"
    assert d.reason == raw
    assert d.findings == []


def test_handles_missing_fields():
    raw = '{"verdict": "approve"}'
    d = parse_decision(raw)
    assert d.verdict == "approve"
    assert d.reason == ""
    assert d.findings == []


def test_handles_non_string_verdict():
    raw = '{"verdict": 123, "reason": "x"}'
    d = parse_decision(raw)
    assert d.verdict == "unknown"
