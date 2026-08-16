import json

import pytest

from peer_loop.exceptions import MalformedResponseError
from peer_loop.llm.fake import FakeLLMClient
from peer_loop.models import ExecutionResult, Plan, PlanStep, StepResult
from peer_loop.reviewer import Reviewer


def _plan():
    return Plan(rationale="fix it", steps=[PlanStep(tool="run_tests", description="verify", path="test_solution.py")])


def _execution_result(tests_passed: bool):
    return ExecutionResult(
        step_results=[
            StepResult(tool="run_tests", description="verify", status="success", output="...", duration_ms=10.0)
        ],
        tests_passed=tests_passed,
        tests_output="1 failed" if not tests_passed else "4 passed",
        overall_status="success",
    )


def test_accepts_with_specific_reason():
    reason = "all 4 tests passed"
    llm = FakeLLMClient(script={"reviewer": [json.dumps({"accepted": True, "reason": reason})]})
    verdict = Reviewer(llm).review("task", _plan(), _execution_result(True))
    assert verdict.accepted is True
    assert verdict.reason == reason


def test_rejects_with_specific_reason():
    reason = "test_zero failed: fibonacci(0) returned 1 instead of 0"
    llm = FakeLLMClient(script={"reviewer": [json.dumps({"accepted": False, "reason": reason})]})
    verdict = Reviewer(llm).review("task", _plan(), _execution_result(False))
    assert verdict.accepted is False
    assert "test_zero" in verdict.reason


def test_malformed_json_raises_typed_error():
    llm = FakeLLMClient(script={"reviewer": ["not json"]})
    with pytest.raises(MalformedResponseError):
        Reviewer(llm).review("task", _plan(), _execution_result(False))


def test_missing_required_field_raises():
    bad = json.dumps({"accepted": False})  # missing "reason"
    llm = FakeLLMClient(script={"reviewer": [bad]})
    with pytest.raises(MalformedResponseError):
        Reviewer(llm).review("task", _plan(), _execution_result(False))


def test_empty_reason_raises():
    bad = json.dumps({"accepted": False, "reason": "   "})
    llm = FakeLLMClient(script={"reviewer": [bad]})
    with pytest.raises(MalformedResponseError):
        Reviewer(llm).review("task", _plan(), _execution_result(False))


@pytest.mark.parametrize("generic_reason", ["bad", "wrong", "Not good enough", "Incorrect.", "FAILED"])
def test_generic_rejection_reason_raises_malformed(generic_reason):
    bad = json.dumps({"accepted": False, "reason": generic_reason})
    llm = FakeLLMClient(script={"reviewer": [bad]})
    with pytest.raises(MalformedResponseError, match="non-specific"):
        Reviewer(llm).review("task", _plan(), _execution_result(False))


def test_specific_but_wrong_reason_is_accepted_as_well_formed():
    # The reviewer being *factually* wrong is a different failure mode from
    # being *vague* -- only vagueness is treated as malformed output. A
    # confidently wrong but specific-sounding critique still parses fine;
    # catching that it's wrong is the loop controller's job (see
    # reviewer_disagreed_with_tests), not the parser's.
    reason = "test_strings failed: expected alphabetically sorted order"
    llm = FakeLLMClient(script={"reviewer": [json.dumps({"accepted": False, "reason": reason})]})
    verdict = Reviewer(llm).review("task", _plan(), _execution_result(True))
    assert verdict.accepted is False
    assert verdict.reason == reason
