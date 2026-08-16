"""The loop controller: wires planner -> executor -> reviewer together,
sends rejection reasons back to the planner for a revised plan, and caps
total iterations so a run can never loop forever.
"""

from __future__ import annotations

import time
from pathlib import Path

from peer_loop.exceptions import MalformedResponseError
from peer_loop.executor import Executor
from peer_loop.logging_utils import LoopLogger
from peer_loop.models import ExecutionResult, Iteration, ReviewVerdict, RunResult
from peer_loop.planner import Planner
from peer_loop.storage import Storage
from peer_loop.task_suite.tasks import Task


class LoopController:
    """Runs the plan -> execute -> review cycle for one task.

    ``reviewer`` only needs a ``.review(task_description, plan, result) ->
    ReviewVerdict`` method -- both the real ``Reviewer`` and the
    ``AlwaysAcceptReviewer`` baseline stub (used for the M4 single-shot
    comparison) satisfy this via structural typing, so the controller
    doesn't need to know which one it has.
    """

    def __init__(
        self,
        planner: Planner,
        executor: Executor,
        reviewer,
        logger: LoopLogger | None = None,
        storage: Storage | None = None,
    ) -> None:
        self.planner = planner
        self.executor = executor
        self.reviewer = reviewer
        self.logger = logger or LoopLogger()
        self.storage = storage

    def run_task(self, task: Task, workdir: Path, max_iterations: int = 5) -> RunResult:
        if max_iterations < 1:
            raise ValueError("max_iterations must be >= 1")

        run_start = time.monotonic()
        iterations: list[Iteration] = []
        prior_feedback: str | None = None
        run_id = self.logger.start_run(task.id, task.description)

        for i in range(1, max_iterations + 1):
            iter_start = time.monotonic()

            # --- Plan ---
            try:
                plan = self.planner.plan(task.description, prior_feedback)
            except MalformedResponseError as exc:
                reason = f"planner produced malformed output: {exc}"
                iteration = Iteration(
                    iteration_number=i,
                    plan=None,
                    execution_result=None,
                    review_verdict=ReviewVerdict(accepted=False, reason=reason),
                    planner_malformed_output=True,
                    duration_ms=(time.monotonic() - iter_start) * 1000,
                )
                iterations.append(iteration)
                self.logger.log_iteration(run_id, iteration)
                prior_feedback = reason + " Respond with ONLY valid JSON matching the required schema."
                continue

            # --- Execute ---
            try:
                execution_result = self.executor.execute(task, plan, workdir)
            except Exception as exc:  # noqa: BLE001 - executor crash must not kill the whole run
                execution_result = ExecutionResult(
                    step_results=[], tests_passed=None, tests_output="", overall_status="error"
                )
                reason = f"executor crashed unexpectedly: {type(exc).__name__}: {exc}"
                iteration = Iteration(
                    iteration_number=i,
                    plan=plan,
                    execution_result=execution_result,
                    review_verdict=ReviewVerdict(accepted=False, reason=reason),
                    duration_ms=(time.monotonic() - iter_start) * 1000,
                )
                iterations.append(iteration)
                self.logger.log_iteration(run_id, iteration)
                prior_feedback = reason
                continue

            # --- Review ---
            try:
                verdict = self.reviewer.review(task.description, plan, execution_result)
            except MalformedResponseError as exc:
                reason = f"reviewer produced malformed output: {exc}"
                iteration = Iteration(
                    iteration_number=i,
                    plan=plan,
                    execution_result=execution_result,
                    review_verdict=ReviewVerdict(accepted=False, reason=reason),
                    duration_ms=(time.monotonic() - iter_start) * 1000,
                )
                iterations.append(iteration)
                self.logger.log_iteration(run_id, iteration)
                prior_feedback = reason
                continue

            disagreed = (
                execution_result.tests_passed is not None
                and execution_result.tests_passed != verdict.accepted
            )
            iteration = Iteration(
                iteration_number=i,
                plan=plan,
                execution_result=execution_result,
                review_verdict=verdict,
                reviewer_disagreed_with_tests=disagreed,
                duration_ms=(time.monotonic() - iter_start) * 1000,
            )
            iterations.append(iteration)
            self.logger.log_iteration(run_id, iteration)

            if verdict.accepted:
                result = RunResult(
                    status="success",
                    task_text=task.description,
                    result=f"accepted after {i} iteration(s): {verdict.reason}",
                    iterations=iterations,
                    iteration_count=i,
                    total_duration_ms=(time.monotonic() - run_start) * 1000,
                )
                self.logger.finish_run(run_id, result)
                if self.storage:
                    self.storage.save_run(result, task_id=task.id)
                return result

            prior_feedback = verdict.reason

        # Exhausted max_iterations without an accept -- fail gracefully,
        # never raise, and say exactly why (spec section 9, first bullet).
        result = RunResult(
            status="failed",
            task_text=task.description,
            result=(
                f"could not complete within {max_iterations} iteration(s); "
                f"last reviewer reason: {prior_feedback}"
            ),
            iterations=iterations,
            iteration_count=len(iterations),
            total_duration_ms=(time.monotonic() - run_start) * 1000,
        )
        self.logger.finish_run(run_id, result)
        if self.storage:
            self.storage.save_run(result, task_id=task.id)
        return result
