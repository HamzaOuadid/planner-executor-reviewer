import json

import pytest

from peer_loop.exceptions import MalformedResponseError
from peer_loop.llm.fake import FakeLLMClient
from peer_loop.planner import Planner


def _valid_plan_json():
    return json.dumps(
        {
            "rationale": "fix the base case",
            "steps": [
                {"tool": "write_file", "description": "apply fix", "path": "solution.py", "content": "x = 1"},
                {"tool": "run_tests", "description": "verify", "path": "test_solution.py"},
            ],
        }
    )


def test_produces_reasonable_plan_from_valid_json():
    llm = FakeLLMClient(script={"planner": [_valid_plan_json()]})
    plan = Planner(llm).plan("fix fibonacci")
    assert plan.rationale == "fix the base case"
    assert [s.tool for s in plan.steps] == ["write_file", "run_tests"]


def test_includes_prior_feedback_in_prompt_when_revising():
    llm = FakeLLMClient(script={"planner": [_valid_plan_json()]})
    Planner(llm).plan("fix fibonacci", prior_feedback="test_zero failed: expected 0, got 1")
    sent = llm.calls[0].user
    assert "test_zero failed" in sent
    assert "REJECTED" in sent


def test_malformed_json_raises_typed_error():
    llm = FakeLLMClient(script={"planner": ["not json {{{"]})
    with pytest.raises(MalformedResponseError):
        Planner(llm).plan("fix fibonacci")


def test_valid_json_missing_required_field_raises():
    bad = json.dumps({"steps": []})  # missing "rationale"
    llm = FakeLLMClient(script={"planner": [bad]})
    with pytest.raises(MalformedResponseError):
        Planner(llm).plan("fix fibonacci")


def test_empty_steps_list_raises():
    bad = json.dumps({"rationale": "no steps needed", "steps": []})
    llm = FakeLLMClient(script={"planner": [bad]})
    with pytest.raises(MalformedResponseError):
        Planner(llm).plan("fix fibonacci")


def test_unknown_tool_name_raises():
    bad = json.dumps(
        {
            "rationale": "hallucinated a tool",
            "steps": [{"tool": "delete_universe", "description": "oops", "path": "x"}],
        }
    )
    llm = FakeLLMClient(script={"planner": [bad]})
    with pytest.raises(MalformedResponseError, match="unknown tool"):
        Planner(llm).plan("fix fibonacci")


def test_json_wrapped_in_markdown_fence_is_still_parsed():
    fenced = "```json\n" + _valid_plan_json() + "\n```"
    llm = FakeLLMClient(script={"planner": [fenced]})
    plan = Planner(llm).plan("fix fibonacci")
    assert plan.rationale == "fix the base case"
