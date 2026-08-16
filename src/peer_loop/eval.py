"""M4: task success rate with vs. without the reviewer stage.

"Success" here is graded against ground truth (the real pytest outcome of
the LAST attempt actually made), never against the reviewer's own verdict
-- otherwise the baseline (which stubs the reviewer to always accept)
would trivially "succeed" 100% of the time by definition. That would
hide exactly the thing this comparison exists to show.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

from peer_loop.demo_fixtures import build_scripted_llm
from peer_loop.executor import Executor
from peer_loop.loop_controller import LoopController
from peer_loop.models import ReviewVerdict
from peer_loop.planner import Planner
from peer_loop.reviewer import Reviewer
from peer_loop.task_suite.tasks import TASKS, Task


class AlwaysAcceptReviewer:
    """The M4 single-shot baseline: same interface as Reviewer, but never
    actually checks anything. Because the loop controller accepts any
    object with a ``.review(...)`` method (structural typing, not
    inheritance), this drops in without changing LoopController at all."""

    def review(self, task_description, plan, result):  # noqa: D102
        return ReviewVerdict(
            accepted=True,
            reason="single-shot baseline: reviewer stage stubbed to always-accept",
        )


@dataclass
class TaskEvalResult:
    task_id: str
    with_reviewer_ground_truth_success: bool
    with_reviewer_iterations: int
    with_reviewer_status: str
    baseline_ground_truth_success: bool
    baseline_iterations: int


def _ground_truth_success(iterations) -> bool:
    if not iterations:
        return False
    last = iterations[-1]
    return bool(last.execution_result and last.execution_result.tests_passed)


def evaluate_task(task: Task, max_iterations: int = 5) -> TaskEvalResult:
    with tempfile.TemporaryDirectory() as d1:
        llm = build_scripted_llm(task.id)
        controller = LoopController(
            Planner(llm), Executor(sleep_fn=lambda s: None), Reviewer(llm)
        )
        result = controller.run_task(task, Path(d1), max_iterations=max_iterations)
        with_gt = _ground_truth_success(result.iterations)
        with_iters = result.iteration_count
        with_status = result.status

    with tempfile.TemporaryDirectory() as d2:
        llm2 = build_scripted_llm(task.id)
        controller2 = LoopController(Planner(llm2), Executor(sleep_fn=lambda s: None), AlwaysAcceptReviewer())
        result2 = controller2.run_task(task, Path(d2), max_iterations=max_iterations)
        baseline_gt = _ground_truth_success(result2.iterations)
        baseline_iters = result2.iteration_count

    return TaskEvalResult(
        task_id=task.id,
        with_reviewer_ground_truth_success=with_gt,
        with_reviewer_iterations=with_iters,
        with_reviewer_status=with_status,
        baseline_ground_truth_success=baseline_gt,
        baseline_iterations=baseline_iters,
    )


def run_full_eval(max_iterations: int = 5) -> list[TaskEvalResult]:
    return [evaluate_task(t, max_iterations) for t in TASKS]


def format_eval_report(results: list[TaskEvalResult]) -> str:
    lines = []
    lines.append(f"{'task':<24}{'with reviewer':<18}{'iters':<8}{'baseline':<18}{'iters':<8}")
    with_success = 0
    baseline_success = 0
    for r in results:
        with_mark = "PASS" if r.with_reviewer_ground_truth_success else "FAIL"
        baseline_mark = "PASS" if r.baseline_ground_truth_success else "FAIL"
        with_success += r.with_reviewer_ground_truth_success
        baseline_success += r.baseline_ground_truth_success
        lines.append(
            f"{r.task_id:<24}{with_mark:<18}{r.with_reviewer_iterations:<8}"
            f"{baseline_mark:<18}{r.baseline_iterations:<8}"
        )
    n = len(results)
    lines.append("")
    lines.append(
        f"with reviewer:  {with_success}/{n} tasks correct "
        f"({100 * with_success / n:.0f}% success rate)"
    )
    lines.append(
        f"baseline (no reviewer, single-shot): {baseline_success}/{n} tasks correct "
        f"({100 * baseline_success / n:.0f}% success rate)"
    )
    return "\n".join(lines)
