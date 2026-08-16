import io
import json

from peer_loop.logging_utils import LoopLogger
from peer_loop.models import ExecutionResult, Iteration, Plan, PlanStep, ReviewVerdict, RunResult, StepResult


def test_start_run_returns_unique_ids():
    logger = LoopLogger()
    id1 = logger.start_run("task-a", "do a thing")
    id2 = logger.start_run("task-a", "do a thing")
    assert id1 != id2


def test_writes_valid_jsonl_to_sink():
    sink = io.StringIO()
    logger = LoopLogger(sink=sink)
    run_id = logger.start_run("fibonacci", "fix fibonacci")
    plan = Plan(rationale="r", steps=[PlanStep(tool="run_tests", description="d", path="test_solution.py")])
    execution_result = ExecutionResult(
        step_results=[StepResult(tool="run_tests", description="d", status="success", output="ok", duration_ms=5.0)],
        tests_passed=False,
        tests_output="1 failed",
        overall_status="success",
    )
    verdict = ReviewVerdict(accepted=False, reason="test_zero failed: expected 0, got 1")
    iteration = Iteration(iteration_number=1, plan=plan, execution_result=execution_result, review_verdict=verdict)
    logger.log_iteration(run_id, iteration)
    result = RunResult(status="failed", task_text="fix fibonacci", result="could not complete", iteration_count=1)
    logger.finish_run(run_id, result)

    lines = sink.getvalue().strip().splitlines()
    assert len(lines) == 3
    for line in lines:
        json.loads(line)  # must be valid JSON, one object per line


def test_rejection_reason_present_and_specific_in_logged_iteration():
    logger = LoopLogger()
    run_id = logger.start_run("fibonacci", "fix fibonacci")
    verdict = ReviewVerdict(accepted=False, reason="test_zero failed: fibonacci(0) returned 1 instead of 0")
    iteration = Iteration(iteration_number=1, plan=None, execution_result=None, review_verdict=verdict)
    logger.log_iteration(run_id, iteration)

    logged = logger.entries[-1]
    assert logged["review_accepted"] is False
    assert logged["review_reason"] == verdict.reason
    assert "test_zero" in logged["review_reason"]


def test_reviewer_disagreement_flag_is_logged():
    logger = LoopLogger()
    run_id = logger.start_run("t", "d")
    verdict = ReviewVerdict(accepted=False, reason="a specific but wrong critique")
    iteration = Iteration(
        iteration_number=1,
        plan=None,
        execution_result=None,
        review_verdict=verdict,
        reviewer_disagreed_with_tests=True,
    )
    logger.log_iteration(run_id, iteration)
    assert logger.entries[-1]["reviewer_disagreed_with_tests"] is True


def test_malformed_planner_output_flag_is_logged():
    logger = LoopLogger()
    run_id = logger.start_run("t", "d")
    verdict = ReviewVerdict(accepted=False, reason="planner produced malformed output: bad json")
    iteration = Iteration(
        iteration_number=1, plan=None, execution_result=None, review_verdict=verdict, planner_malformed_output=True
    )
    logger.log_iteration(run_id, iteration)
    assert logger.entries[-1]["planner_malformed_output"] is True
    assert logger.entries[-1]["plan_steps"] == []
