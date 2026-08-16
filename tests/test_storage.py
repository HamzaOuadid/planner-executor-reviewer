"""Unit tests for the SQLite persistence layer in isolation, using
synthetic RunResult/Iteration objects -- no planner/executor/reviewer
loop involved. (End-to-end persistence of a real loop run is covered
separately by tests/test_cli.py's ``--db`` flag test.)
"""

from peer_loop.models import ExecutionResult, Iteration, Plan, PlanStep, ReviewVerdict, RunResult, StepResult
from peer_loop.storage import Storage


def _synthetic_run(status: str = "success", iteration_count: int = 2) -> RunResult:
    plan = Plan(rationale="fix it", steps=[PlanStep(tool="run_tests", description="verify", path="test_solution.py")])
    failing_exec = ExecutionResult(
        step_results=[StepResult(tool="run_tests", description="verify", status="success", output="1 failed", duration_ms=5.0)],
        tests_passed=False,
        tests_output="1 failed",
        overall_status="success",
    )
    passing_exec = ExecutionResult(
        step_results=[StepResult(tool="run_tests", description="verify", status="success", output="4 passed", duration_ms=5.0)],
        tests_passed=True,
        tests_output="4 passed",
        overall_status="success",
    )
    iterations = [
        Iteration(
            iteration_number=1,
            plan=plan,
            execution_result=failing_exec,
            review_verdict=ReviewVerdict(accepted=False, reason="test_strips_punctuation failed: specifics here"),
        ),
        Iteration(
            iteration_number=2,
            plan=plan,
            execution_result=passing_exec,
            review_verdict=ReviewVerdict(accepted=True, reason="all 4 tests passed"),
        ),
    ][:iteration_count]
    return RunResult(
        status=status,
        task_text="Fix word_count so it is case/punctuation insensitive.",
        result="accepted after 2 iteration(s): all 4 tests passed",
        iterations=iterations,
        iteration_count=iteration_count,
        total_duration_ms=42.0,
    )


def test_save_and_get_run_roundtrip(tmp_path):
    db_path = tmp_path / "runs.db"
    storage = Storage(db_path)
    result = _synthetic_run()
    run_id = storage.save_run(result, task_id="word_count")
    storage.close()

    storage2 = Storage(db_path)
    runs = storage2.list_runs()
    assert len(runs) == 1
    assert runs[0]["id"] == run_id
    assert runs[0]["final_status"] == "success"
    assert runs[0]["iteration_count"] == 2
    assert runs[0]["task_id"] == "word_count"

    full = storage2.get_run(run_id)
    assert full is not None
    assert len(full["iterations"]) == 2
    assert full["iterations"][0]["review_verdict"] == "rejected"
    assert full["iterations"][1]["review_verdict"] == "accepted"
    assert "test_strips_punctuation" in full["iterations"][0]["review_reason"]
    storage2.close()


def test_get_run_returns_none_for_unknown_id(tmp_path):
    storage = Storage(tmp_path / "runs.db")
    assert storage.get_run(999) is None
    storage.close()


def test_list_runs_respects_limit_and_orders_newest_first(tmp_path):
    db_path = tmp_path / "runs.db"
    storage = Storage(db_path)
    for task_id in ["fibonacci", "is_palindrome", "dedupe_preserve_order"]:
        storage.save_run(_synthetic_run(iteration_count=1), task_id=task_id)

    runs = storage.list_runs(limit=2)
    assert len(runs) == 2
    assert runs[0]["task_id"] == "dedupe_preserve_order"  # most recent first
    storage.close()


def test_reviewer_disagreement_and_malformed_flags_persisted(tmp_path):
    storage = Storage(tmp_path / "runs.db")
    plan = Plan(rationale="r", steps=[PlanStep(tool="run_tests", description="d", path="test_solution.py")])
    exec_result = ExecutionResult(overall_status="success", tests_passed=True, tests_output="ok")
    iteration = Iteration(
        iteration_number=1,
        plan=plan,
        execution_result=exec_result,
        review_verdict=ReviewVerdict(accepted=False, reason="a specific but wrong critique"),
        reviewer_disagreed_with_tests=True,
        planner_malformed_output=False,
    )
    result = RunResult(status="failed", task_text="t", result="r", iterations=[iteration], iteration_count=1)
    run_id = storage.save_run(result, task_id="t")

    full = storage.get_run(run_id)
    assert full["iterations"][0]["reviewer_disagreed_with_tests"] == 1
    storage.close()
