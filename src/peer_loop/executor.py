"""The executor: runs each planned step for real against a sandbox
directory, with exponential-backoff retry for transient tool failures and
a hard timeout distinction for tool calls that hang.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

from peer_loop import tools
from peer_loop.exceptions import ToolTimeoutError, TransientToolError, UnknownToolError
from peer_loop.models import ExecutionResult, Plan, PlanStep, StepResult, VALID_TOOLS
from peer_loop.task_suite.tasks import Task, materialize_sandbox

# A fault injector lets tests deterministically simulate a transient failure
# or a timeout for a given step/attempt without touching real subprocess/IO
# code. Returning None means "let the real tool run normally".
FaultInjector = Callable[[PlanStep, int], Exception | None]


class Executor:
    def __init__(
        self,
        max_retries: int = 2,
        base_delay_seconds: float = 0.05,
        run_tests_timeout_seconds: float = 15.0,
        sleep_fn: Callable[[float], None] = time.sleep,
        fault_injector: FaultInjector | None = None,
    ) -> None:
        self.max_retries = max_retries
        self.base_delay_seconds = base_delay_seconds
        self.run_tests_timeout_seconds = run_tests_timeout_seconds
        self.sleep_fn = sleep_fn
        self.fault_injector = fault_injector

    def execute(self, task: Task, plan: Plan, workdir: Path) -> ExecutionResult:
        """Reset ``workdir`` to the task's buggy baseline, then run every
        step in ``plan`` against it in order.

        Each iteration starts fresh from the original starter code (not
        the previous iteration's edits) -- the planner is expected to
        supply the complete corrected file content each time. This keeps
        iterations independent and avoids compounding state bugs; see the
        README for the tradeoff this implies.
        """
        workdir.mkdir(parents=True, exist_ok=True)
        materialize_sandbox(task, workdir)

        step_results: list[StepResult] = []
        tests_passed: bool | None = None
        tests_output = ""
        timed_out = False
        tool_error = False

        for step in plan.steps:
            start = time.monotonic()
            try:
                output, attempts = self._run_step_with_retry(step, workdir)
                duration_ms = (time.monotonic() - start) * 1000
                step_results.append(
                    StepResult(
                        tool=step.tool,
                        description=step.description,
                        status="success",
                        output=output,
                        duration_ms=duration_ms,
                        attempts=attempts,
                    )
                )
                if step.tool == "run_tests":
                    # output is "PASSED\n<pytest output>" or "FAILED\n<pytest output>"
                    passed_marker, _, rest = output.partition("\n")
                    tests_passed = passed_marker == "PASSED"
                    tests_output = rest
            except ToolTimeoutError as exc:
                duration_ms = (time.monotonic() - start) * 1000
                step_results.append(
                    StepResult(
                        tool=step.tool,
                        description=step.description,
                        status="timeout",
                        output=str(exc),
                        duration_ms=duration_ms,
                        attempts=self.max_retries + 1,
                    )
                )
                timed_out = True
                break
            except Exception as exc:  # noqa: BLE001 - genuinely any tool error lands here
                duration_ms = (time.monotonic() - start) * 1000
                step_results.append(
                    StepResult(
                        tool=step.tool,
                        description=step.description,
                        status="failed",
                        output=f"{type(exc).__name__}: {exc}",
                        duration_ms=duration_ms,
                        attempts=self.max_retries + 1,
                    )
                )
                tool_error = True
                break

        if timed_out:
            overall_status = "timeout"
        elif tool_error:
            overall_status = "failed"
        else:
            overall_status = "success"

        return ExecutionResult(
            step_results=step_results,
            tests_passed=tests_passed,
            tests_output=tests_output,
            overall_status=overall_status,
        )

    def _run_step_with_retry(self, step: PlanStep, workdir: Path) -> tuple[str, int]:
        """Run one step, retrying TransientToolError with exponential
        backoff. Returns (output_text, attempts_used). Lets
        ToolTimeoutError and any other exception propagate immediately
        (a timeout or a genuine error is never worth blindly retrying)."""
        attempt = 0
        while True:
            attempt += 1
            try:
                if self.fault_injector is not None:
                    injected = self.fault_injector(step, attempt)
                    if injected is not None:
                        raise injected
                return self._dispatch(step, workdir), attempt
            except TransientToolError:
                if attempt > self.max_retries:
                    raise
                delay = self.base_delay_seconds * (2 ** (attempt - 1))
                self.sleep_fn(delay)
                continue

    def _dispatch(self, step: PlanStep, workdir: Path) -> str:
        if step.tool not in VALID_TOOLS:
            raise UnknownToolError(f"executor received an unknown tool {step.tool!r}")

        if step.tool == "read_file":
            if not step.path:
                raise ValueError("read_file step is missing 'path'")
            return tools.read_file(workdir, step.path)

        if step.tool == "write_file":
            if not step.path:
                raise ValueError("write_file step is missing 'path'")
            return tools.write_file(workdir, step.path, step.content or "")

        if step.tool == "list_files":
            return tools.list_files(workdir)

        if step.tool == "run_tests":
            if not step.path:
                raise ValueError("run_tests step is missing 'path'")
            passed, output = tools.run_tests(workdir, step.path, self.run_tests_timeout_seconds)
            marker = "PASSED" if passed else "FAILED"
            return f"{marker}\n{output}"

        raise UnknownToolError(f"executor received an unknown tool {step.tool!r}")  # pragma: no cover
