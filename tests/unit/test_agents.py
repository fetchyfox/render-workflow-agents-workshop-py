"""Tests for agent definitions and reviewer selection."""

from workshop_agent import (
    has_frontend_files,
    select_reviewers,
    REVIEWERS,
    AGENTS,
    security_reviewer,
    performance_reviewer,
    ux_reviewer,
    judge,
)


def test_has_frontend_files_detects_tsx():
    patches = [{"file": "src/Button.tsx", "diff": "+code"}]
    assert has_frontend_files(patches) is True


def test_has_frontend_files_ignores_backend():
    patches = [{"file": "src/api.ts", "diff": "+code"}]
    assert has_frontend_files(patches) is False


def test_select_reviewers_always_includes_security_and_performance():
    patches = [{"file": "src/api.ts", "diff": "+code"}]
    reviewers = select_reviewers(patches)
    names = {r.name for r in reviewers}
    assert "security" in names
    assert "performance" in names
    assert "ux" not in names


def test_select_reviewers_adds_ux_for_frontend():
    patches = [{"file": "src/Button.tsx", "diff": "+code"}]
    reviewers = select_reviewers(patches)
    names = {r.name for r in reviewers}
    assert "ux" in names
    assert len(reviewers) == 3


def test_reviewers_list():
    assert len(REVIEWERS) == 2
    assert REVIEWERS[0].name == "security"
    assert REVIEWERS[1].name == "performance"


def test_agents_dict():
    assert set(AGENTS.keys()) == {"security", "performance", "ux", "judge"}


def test_agent_has_tools():
    assert "scan_for_secrets" in security_reviewer.tools
    assert "diff_stats" in performance_reviewer.tools
    assert "contrast_ratio" in ux_reviewer.tools
    assert judge.tools == []
