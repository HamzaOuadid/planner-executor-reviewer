"""End-to-end tests of the plan -> execute -> review -> (revise|accept)
loop, driven entirely through FakeLLMClient. This is where the spec's
edge cases (section 9) and testing plan (section 10) are actually proven:
multi-round revision, the max-iteration cap, malformed LLM output at
either stage, executor crashes, and the reviewer being wrong.
"""

import json

import pytest

from peer_loop.demo_fixtures import build_always_reject_llm, build_reviewer_error_llm, build_scripted_llm
from peer_loop.executor import Executor
from peer_loop.llm.fake import FakeLLMClient
from peer_loop.loop_controller import LoopController
from peer_loop.planner import Planner
from peer_loop.reviewer import Reviewer
from peer_loop.task_suite.tasks import get_task


def _controller(llm, **executor_kwargs):
    executor_kwargs.setdefault("sleep_fn", lambda s: None)
    return LoopController(Planner(llm), Executor(**executor_kwargs), Reviewer(llm))


def test_single_shot_success_when_first_attempt_is_correct(tmp_path):
    task = get_task("fibonacci")
    llm = build_scripted_llm("fibonacci")
    result = _controller(llm).run_task(task, tmp_path, max_iterations=5)
    assert result.status == "success"
    assert result.iteration_count == 1
    assert result.iterations[0].review_verdict.accepted is True


def test_multi_round_revision_flawed_first_attempt_corrected_second(tmp_path):
    """The flagship acceptance-criterion case (spec section 4, story 1):
    the reviewer catches a real bad plan/execution and the loop corrects
    itself on revision."""
    task = get_task("word_count")
    llm = build_scripted_llm("word_count")
    result = _controller(llm).run_task(task, tmp_path, max_iterations=5)

    assert result.status == "success"
    assert result.iteration_count == 2

    first, second = result.iterations
    assert first.review_verdict.accepted is False
    assert "punctuation" in first.review_verdict.reason
    assert first.execution_result.tests_passed is False

    assert second.review_verdict.accepted is True
    assert second.execution_result.tests_passed is True


def test_rejection_reason_is_specific_and_visible_in_the_log(tmp_path):
    """Story 2 acceptance criterion: every rejection includes a specific,
    non-generic reason, visible in the log."""
    task = get_task("safe_divide")
    llm = build_scripted_llm("safe_divide")
    result = _controller(llm).run_task(task, tmp_path, max_iterations=5)

    rejected = [it for it in result.iterations if not it.review_verdict.accepted]
    assert len(rejected) == 1
    reason = rejected[0].review_verdict.reason
    # non-generic: names the specific failing test and what actually happened
    assert "test_division_by_zero_returns_default_none" in reason
    assert "ZeroDivisionError" in reason


def test_max_iteration_cap_triggers_cleanly_not_an_exception(tmp_path):
    llm = build_always_reject_llm()
    task = get_task("fibonacci")
    result = _controller(llm).run_task(task, tmp_path, max_iterations=3)

    assert result.status == "failed"
    assert result.iteration_count == 3
    assert "could not complete" in result.result
    assert "3 iteration" in result.result
    # every single one of the 3 attempts still has a specific reason logged
    for iteration in result.iterations:
        assert iteration.review_verdict.reason.strip() != ""


def test_max_iteration_cap_is_exact_never_one_more_or_less(tmp_path):
    llm = build_always_reject_llm()
    task = get_task("fibonacci")
    for cap in (1, 2, 4):
        result = _controller(llm).run_task(task, tmp_path, max_iterations=cap)
        assert result.iteration_count == cap
        assert result.status == "failed"


def test_planner_malformed_output_is_recovered_not_fatal(tmp_path):
    task = get_task("fibonacci")
    good_plan = json.dumps(
        {
            "rationale": "fix base case",
            "steps": [
                {"tool": "write_file", "description": "fix", "path": "solution.py", "content": task.reference_fix},
                {"tool": "run_tests", "description": "verify", "path": "test_solution.py"},
            ],
        }
    )
    good_review = json.dumps({"accepted": True, "reason": "all 6 tests passed"})
    llm = FakeLLMClient(script={"planner": ["not valid json {{{", good_plan], "reviewer": [good_review]})

    result = _controller(llm).run_task(task, tmp_path, max_iterations=5)

    assert result.status == "success"
    assert result.iteration_count == 2
    assert result.iterations[0].planner_malformed_output is True
    assert "malformed" in result.iterations[0].review_verdict.reason
    assert result.iterations[0].execution_result is None  # never got to execute


def test_reviewer_malformed_output_is_recovered_not_fatal(tmp_path):
    task = get_task("fibonacci")
    plan = json.dumps(
        {
            "rationale": "fix base case",
            "steps": [
                {"tool": "write_file", "description": "fix", "path": "solution.py", "content": task.reference_fix},
                {"tool": "run_tests", "description": "verify", "path": "test_solution.py"},
            ],
        }
    )
    good_review = json.dumps({"accepted": True, "reason": "all 6 tests passed"})
    llm = FakeLLMClient(script={"planner": [plan, plan], "reviewer": ["garbage, not json", good_review]})

    result = _controller(llm).run_task(task, tmp_path, max_iterations=5)

    assert result.status == "success"
    assert result.iteration_count == 2
    assert "malformed" in result.iterations[0].review_verdict.reason
    # the execution DID happen for iteration 1 (only the reviewer's response was malformed)
    assert result.iterations[0].execution_result is not None


def test_executor_step_error_recovers_as_a_normal_rejection(tmp_path):
    """A tool-level problem (here: a plan step pointing at a test file that
    doesn't exist) is handled entirely inside Executor.execute -- it comes
    back as a normal 'failed' step in the ExecutionResult, not an
    exception. The loop must still recover on the next iteration."""
    task = get_task("fibonacci")
    plan = json.dumps(
        {
            "rationale": "fix base case",
            "steps": [{"tool": "run_tests", "description": "verify", "path": "no_such_test_file.py"}],
        }
    )
    good_plan = json.dumps(
        {
            "rationale": "fix base case, second try",
            "steps": [
                {"tool": "write_file", "description": "fix", "path": "solution.py", "content": task.reference_fix},
                {"tool": "run_tests", "description": "verify", "path": "test_solution.py"},
            ],
        }
    )
    reject_review = json.dumps(
        {"accepted": False, "reason": "run_tests step failed: no_such_test_file.py does not exist"}
    )
    good_review = json.dumps({"accepted": True, "reason": "all 6 tests passed"})
    llm = FakeLLMClient(script={"planner": [plan, good_plan], "reviewer": [reject_review, good_review]})

    result = _controller(llm).run_task(task, tmp_path, max_iterations=5)

    assert result.status == "success"
    assert result.iteration_count == 2
    assert result.iterations[0].execution_result.overall_status == "failed"
    assert "FileNotFoundError" in result.iterations[0].execution_result.step_results[0].output


class _CrashingExecutor:
    """Simulates a genuine bug/crash inside the executor itself (as
    opposed to a well-handled tool failure), to prove the loop controller's
    own safety net around ``executor.execute(...)`` actually works."""

    def execute(self, task, plan, workdir):
        raise RuntimeError("simulated executor bug")


def test_executor_crash_is_caught_and_fed_back_as_rejection(tmp_path):
    task = get_task("fibonacci")
    llm = build_always_reject_llm()  # planner side just needs to keep producing valid plans
    controller = LoopController(Planner(llm), _CrashingExecutor(), Reviewer(llm))

    result = controller.run_task(task, tmp_path, max_iterations=2)

    assert result.status == "failed"
    assert result.iteration_count == 2
    for iteration in result.iterations:
        assert iteration.execution_result.overall_status == "error"
        assert "simulated executor bug" in iteration.review_verdict.reason
        assert iteration.review_verdict.accepted is False


def test_reviewer_disagreement_with_ground_truth_is_tracked_not_hidden(tmp_path):
    """Spec section 9/13: when the reviewer rejects a result that actually
    passed its tests, that must be tracked as a known failure mode, not
    silently absorbed into the log."""
    task = get_task("dedupe_preserve_order")
    llm = build_reviewer_error_llm()
    result = _controller(llm).run_task(task, tmp_path, max_iterations=5)

    assert result.status == "success"
    assert result.iteration_count == 2

    first = result.iterations[0]
    assert first.execution_result.tests_passed is True
    assert first.review_verdict.accepted is False
    assert first.reviewer_disagreed_with_tests is True

    second = result.iterations[1]
    assert second.reviewer_disagreed_with_tests is False


def test_full_trace_is_logged_for_every_iteration(tmp_path):
    task = get_task("word_count")
    llm = build_scripted_llm("word_count")
    controller = _controller(llm)
    result = controller.run_task(task, tmp_path, max_iterations=5)

    entries = controller.logger.entries
    events = [e["event"] for e in entries]
    assert events[0] == "run_start"
    assert events[-1] == "run_end"
    assert events.count("iteration") == result.iteration_count

    for entry in entries:
        if entry["event"] == "iteration":
            assert entry["review_reason"]  # never blank


def test_zero_max_iterations_rejected():
    llm = build_scripted_llm("fibonacci")
    controller = _controller(llm)
    with pytest.raises(ValueError):
        controller.run_task(get_task("fibonacci"), None, max_iterations=0)
