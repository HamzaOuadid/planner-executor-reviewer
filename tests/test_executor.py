from pathlib import Path

from peer_loop.executor import Executor
from peer_loop.exceptions import ToolTimeoutError, TransientToolError
from peer_loop.models import Plan, PlanStep
from peer_loop.task_suite.tasks import get_task


def _write_and_test_plan(content: str) -> Plan:
    return Plan(
        rationale="apply fix",
        steps=[
            PlanStep(tool="write_file", description="apply fix", path="solution.py", content=content),
            PlanStep(tool="run_tests", description="verify", path="test_solution.py"),
        ],
    )


def test_happy_path_runs_real_tests_and_reports_pass(tmp_path):
    task = get_task("fibonacci")
    plan = _write_and_test_plan(task.reference_fix)
    result = Executor(sleep_fn=lambda s: None).execute(task, plan, tmp_path)
    assert result.overall_status == "success"
    assert result.tests_passed is True
    assert result.step_results[0].status == "success"
    assert result.step_results[1].status == "success"


def test_wrong_fix_runs_to_completion_but_tests_fail(tmp_path):
    task = get_task("fibonacci")
    plan = _write_and_test_plan(task.starter_code)  # still buggy
    result = Executor(sleep_fn=lambda s: None).execute(task, plan, tmp_path)
    assert result.overall_status == "success"  # the tool calls themselves succeeded
    assert result.tests_passed is False  # but the code under test is wrong
    assert "test_zero" in result.tests_output


def test_each_execute_call_resets_sandbox_to_starter_baseline(tmp_path):
    task = get_task("fibonacci")
    executor = Executor(sleep_fn=lambda s: None)
    # First call applies a correct fix.
    executor.execute(task, _write_and_test_plan(task.reference_fix), tmp_path)
    assert "n == 0" in (tmp_path / "solution.py").read_text()
    # Second call's plan doesn't touch solution.py at all -- if the sandbox
    # weren't reset, the previous (correct) file would still be there and
    # tests would pass. It must start from the buggy baseline again.
    run_only_plan = Plan(
        rationale="just re-run tests",
        steps=[PlanStep(tool="run_tests", description="verify", path="test_solution.py")],
    )
    result = executor.execute(task, run_only_plan, tmp_path)
    assert result.tests_passed is False
    assert "n == 0" not in (tmp_path / "solution.py").read_text()


def test_transient_failure_then_success_is_retried_and_recorded(tmp_path):
    task = get_task("fibonacci")
    plan = _write_and_test_plan(task.reference_fix)
    calls = {"count": 0}

    def fault_injector(step, attempt):
        if step.tool == "write_file" and attempt == 1:
            return TransientToolError("simulated flaky disk write")
        return None

    executor = Executor(max_retries=2, sleep_fn=lambda s: None, fault_injector=fault_injector)
    result = executor.execute(task, plan, tmp_path)
    write_step = result.step_results[0]
    assert write_step.status == "success"
    assert write_step.attempts == 2  # failed once, succeeded on retry


def test_retries_exhausted_marks_step_failed_not_a_crash(tmp_path):
    task = get_task("fibonacci")
    plan = _write_and_test_plan(task.reference_fix)

    def always_transient(step, attempt):
        if step.tool == "write_file":
            return TransientToolError("simulated persistent flakiness")
        return None

    executor = Executor(max_retries=2, sleep_fn=lambda s: None, fault_injector=always_transient)
    result = executor.execute(task, plan, tmp_path)
    assert result.overall_status == "failed"
    write_step = result.step_results[0]
    assert write_step.status == "failed"
    assert write_step.attempts == 3  # 1 initial + 2 retries
    # the run_tests step must never have been reached
    assert len(result.step_results) == 1


def test_timeout_is_distinguishable_from_a_wrong_but_successful_result(tmp_path):
    task = get_task("fibonacci")
    plan = _write_and_test_plan(task.reference_fix)

    def timeout_injector(step, attempt):
        if step.tool == "run_tests":
            return ToolTimeoutError("simulated hang")
        return None

    executor = Executor(sleep_fn=lambda s: None, fault_injector=timeout_injector)
    result = executor.execute(task, plan, tmp_path)
    assert result.overall_status == "timeout"
    assert result.step_results[-1].status == "timeout"
    # tests_passed must stay None (we genuinely don't know), never False --
    # False would conflate "ran and failed" with "never finished running".
    assert result.tests_passed is None


def test_unknown_tool_in_plan_fails_the_step_without_crashing(tmp_path):
    task = get_task("fibonacci")
    plan = Plan(
        rationale="hallucinated tool",
        steps=[PlanStep(tool="delete_everything", description="oops", path="x")],
    )
    result = Executor(sleep_fn=lambda s: None).execute(task, plan, tmp_path)
    assert result.overall_status == "failed"
    assert result.step_results[0].status == "failed"
    assert "UnknownToolError" in result.step_results[0].output


def test_read_file_and_list_files_steps_work(tmp_path):
    task = get_task("fibonacci")
    plan = Plan(
        rationale="inspect before fixing",
        steps=[
            PlanStep(tool="list_files", description="see what's there"),
            PlanStep(tool="read_file", description="read starter", path="solution.py"),
        ],
    )
    result = Executor(sleep_fn=lambda s: None).execute(task, plan, tmp_path)
    assert result.overall_status == "success"
    assert "solution.py" in result.step_results[0].output
    assert "fibonacci" in result.step_results[1].output
