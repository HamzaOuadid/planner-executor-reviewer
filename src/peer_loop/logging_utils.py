"""Structured, line-oriented (JSONL) logging of every loop step.

This is what makes the "As a developer debugging a failed task" story
concrete: every plan, execution result, and review verdict -- accepted or
rejected -- is recorded as a self-contained JSON record, in order, with
the reviewer's specific reason always included.
"""

from __future__ import annotations

import json
import time
from typing import TextIO

from peer_loop.models import Iteration, RunResult


class LoopLogger:
    """Emits one JSON object per line to ``sink`` (if given) and always
    keeps an in-memory copy in ``self.entries`` for tests/CLI inspection."""

    def __init__(self, sink: TextIO | None = None, also_print: bool = False) -> None:
        self.sink = sink
        self.also_print = also_print
        self.entries: list[dict] = []
        self._run_counter = 0

    def start_run(self, task_id: str, task_text: str) -> str:
        run_id = f"{task_id}-{int(time.time() * 1000)}-{self._run_counter}"
        self._run_counter += 1
        self._emit(
            {
                "event": "run_start",
                "run_id": run_id,
                "task_id": task_id,
                "task_text": task_text,
            }
        )
        return run_id

    def log_iteration(self, run_id: str, iteration: Iteration) -> None:
        self._emit(
            {
                "event": "iteration",
                "run_id": run_id,
                "iteration_number": iteration.iteration_number,
                "planner_malformed_output": iteration.planner_malformed_output,
                "plan_rationale": iteration.plan.rationale if iteration.plan else None,
                "plan_steps": (
                    [s.tool for s in iteration.plan.steps] if iteration.plan else []
                ),
                "execution_overall_status": (
                    iteration.execution_result.overall_status if iteration.execution_result else None
                ),
                "tests_passed": (
                    iteration.execution_result.tests_passed if iteration.execution_result else None
                ),
                "step_statuses": (
                    [
                        {"tool": s.tool, "status": s.status, "attempts": s.attempts}
                        for s in iteration.execution_result.step_results
                    ]
                    if iteration.execution_result
                    else []
                ),
                "review_accepted": iteration.review_verdict.accepted,
                "review_reason": iteration.review_verdict.reason,
                "reviewer_disagreed_with_tests": iteration.reviewer_disagreed_with_tests,
                "duration_ms": round(iteration.duration_ms, 2),
            }
        )

    def finish_run(self, run_id: str, result: RunResult) -> None:
        self._emit(
            {
                "event": "run_end",
                "run_id": run_id,
                "status": result.status,
                "iteration_count": result.iteration_count,
                "result": result.result,
                "total_duration_ms": round(result.total_duration_ms, 2),
            }
        )

    def _emit(self, record: dict) -> None:
        self.entries.append(record)
        line = json.dumps(record, default=str)
        if self.sink is not None:
            self.sink.write(line + "\n")
            self.sink.flush()
        if self.also_print:
            print(line)
