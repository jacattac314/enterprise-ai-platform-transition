import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from security.role_prompts import build_system_prompt, get_template, SessionContext


def _ctx(role: str) -> SessionContext:
    return SessionContext(
        user_id="u1",
        role=role,
        session_id="sess_test",
        approved_datasets=["ds_financials"],
        approved_tools=["search_tool"],
    )


@pytest.mark.parametrize("role", ["VIEWER", "ANALYST", "DEVELOPER", "PLATFORM_ADMIN", "SUPER_ADMIN"])
def test_all_roles_produce_prompt(role):
    prompt = build_system_prompt(_ctx(role))
    assert isinstance(prompt, str)
    assert len(prompt) > 0


def test_analyst_prompt_contains_datasets():
    ctx = _ctx("ANALYST")
    prompt = build_system_prompt(ctx)
    assert "ds_financials" in prompt


def test_developer_prompt_contains_tools():
    ctx = _ctx("DEVELOPER")
    prompt = build_system_prompt(ctx)
    assert "search_tool" in prompt


def test_invalid_role_raises():
    ctx = SessionContext(
        user_id="u1",
        role="HACKER",
        session_id="sess_x",
        approved_datasets=[],
        approved_tools=[],
    )
    with pytest.raises(ValueError, match="Unknown role"):
        build_system_prompt(ctx)


def test_get_template_returns_none_for_unknown():
    assert get_template("UNKNOWN_ROLE") is None


def test_viewer_prompt_states_no_llm_access():
    prompt = build_system_prompt(_ctx("VIEWER"))
    assert "not permitted" in prompt.lower() or "not enabled" in prompt.lower()
