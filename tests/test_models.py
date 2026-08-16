from peer_loop.models import (
    ExecutionResult,
    Iteration,
    Plan,
    PlanStep,
    ReviewVerdict,
    RunResult,
    StepResult,
    VALID_TOOLS,
)


def test_plan_step_defaults():
    step = PlanStep(tool="write_file", description="write it")
    assert step.path is None
    assert step.content is None


def test_plan_roundtrip_json():
    plan = Plan(
        rationale="fix the bug",
        steps=[
            PlanStep(tool="write_file", description="apply fix", path="solution.py", content="x = 1"),
            PlanStep(tool="run_tests", description="verify", path="test_solution.py"),
        ],
    )
    dumped = plan.model_dump_json()
    restored = Plan.model_validate_json(dumped)
    assert restored == plan


def test_valid_tools_are_closed_set():
    assert set(VALID_TOOLS) == {"read_file", "write_file", "run_tests", "list_files"}


def test_execution_result_defaults():
    result = ExecutionResult(overall_status="success")
    assert result.step_results == []
    assert result.tests_passed is None
    assert result.tests_output == ""


def test_review_verdict_requires_reason_field():
    verdict = ReviewVerdict(accepted=False, reason="test_x failed: expected 1, got 2")
    assert verdict.accepted is False
    assert "test_x" in verdict.reason


def test_iteration_default_flags():
    verdict = ReviewVerdict(accepted=True, reason="all tests passed")
    iteration = Iteration(iteration_number=1, plan=None, execution_result=None, review_verdict=verdict)
    assert iteration.planner_malformed_output is False
    assert iteration.reviewer_disagreed_with_tests is False


def test_run_result_defaults():
    result = RunResult(status="success", task_text="do the thing", result="done")
    assert result.iterations == []
    assert result.iteration_count == 0


def test_step_result_attempts_default_is_one():
    step_result = StepResult(tool="run_tests", description="run", status="success", output="ok", duration_ms=1.0)
    assert step_result.attempts == 1
