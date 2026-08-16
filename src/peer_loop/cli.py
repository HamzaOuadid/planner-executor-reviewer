"""Command-line interface for the planner-executor-reviewer loop.

Everything here defaults to the deterministic FakeLLMClient fixtures in
``demo_fixtures.py`` so it runs with no API key and no network access.
Pass ``--real`` to route through ``RealLLMClient`` instead (requires
ANTHROPIC_API_KEY or OPENAI_API_KEY in the environment or a ``.env`` file).
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import typer

from peer_loop.demo_fixtures import build_reviewer_error_llm, build_scripted_llm
from peer_loop.eval import format_eval_report, run_full_eval
from peer_loop.executor import Executor
from peer_loop.loop_controller import LoopController
from peer_loop.logging_utils import LoopLogger
from peer_loop.planner import Planner
from peer_loop.reviewer import Reviewer
from peer_loop.storage import Storage
from peer_loop.task_suite.tasks import TASKS, get_task

app = typer.Typer(help="Planner -> Executor -> Reviewer multi-agent loop.", add_completion=False)


def _build_llm(real: bool):
    if real:
        from peer_loop.llm.real import RealLLMClient

        return RealLLMClient.from_env()
    return None  # caller picks a fixture


@app.command("list-tasks")
def list_tasks() -> None:
    """List every task in the built-in task suite."""
    for task in TASKS:
        typer.echo(f"{task.id:24s} {task.description}")


@app.command("run")
def run(
    task_id: str = typer.Argument(..., help="Task id, e.g. 'word_count'. See list-tasks."),
    max_iterations: int = typer.Option(5, help="Max plan/execute/review iterations."),
    db: str | None = typer.Option(None, help="SQLite path to persist the run (optional)."),
    trace_file: str | None = typer.Option(None, help="Path to write the JSONL trace log (optional)."),
    real: bool = typer.Option(False, "--real", help="Use a real LLM (needs an API key) instead of the fake."),
    reviewer_error_demo: bool = typer.Option(
        False, "--reviewer-error-demo", help="Use the seeded 'reviewer is wrong' fixture instead of task_id's script."
    ),
) -> None:
    """Run a single task through the full loop and print its trace."""
    task = get_task(task_id)

    if real:
        llm = _build_llm(real=True)
        planner, reviewer = Planner(llm), Reviewer(llm)
    elif reviewer_error_demo:
        llm = build_reviewer_error_llm()
        planner, reviewer = Planner(llm), Reviewer(llm)
    else:
        llm = build_scripted_llm(task_id)
        planner, reviewer = Planner(llm), Reviewer(llm)

    sink = open(trace_file, "w", encoding="utf-8") if trace_file else None
    logger = LoopLogger(sink=sink, also_print=True)
    storage = Storage(db) if db else None

    with tempfile.TemporaryDirectory() as workdir:
        controller = LoopController(planner, Executor(), reviewer, logger=logger, storage=storage)
        result = controller.run_task(task, Path(workdir), max_iterations=max_iterations)

    if sink:
        sink.close()

    typer.echo("")
    typer.echo(f"FINAL STATUS: {result.status} after {result.iteration_count} iteration(s)")
    typer.echo(result.result or "")
    if storage:
        storage.close()
    raise typer.Exit(0 if result.status == "success" else 1)


@app.command("demo")
def demo() -> None:
    """Run the flagship 'reviewer catches a real bad plan' demo (word_count
    task: first attempt fails on punctuation stripping, gets a specific
    rejection, second attempt is accepted) and print the full trace."""
    task = get_task("word_count")
    llm = build_scripted_llm("word_count")
    logger = LoopLogger(also_print=True)
    with tempfile.TemporaryDirectory() as workdir:
        controller = LoopController(Planner(llm), Executor(), Reviewer(llm), logger=logger)
        result = controller.run_task(task, Path(workdir), max_iterations=5)
    typer.echo("")
    typer.echo(f"FINAL STATUS: {result.status} after {result.iteration_count} iteration(s)")
    typer.echo(result.result or "")


@app.command("eval")
def eval_cmd(max_iterations: int = typer.Option(5, help="Max iterations per task.")) -> None:
    """Run the full task suite with the reviewer active, and again with it
    stubbed to always-accept (M4 comparison)."""
    results = run_full_eval(max_iterations=max_iterations)
    typer.echo(format_eval_report(results))


@app.command("trace")
def trace(run_id: int, db: str = typer.Option(..., help="SQLite path the run was saved to.")) -> None:
    """Print the stored trace for a run id (debugging story: see exactly
    why the loop rejected an attempt, after the fact)."""
    storage = Storage(db)
    record = storage.get_run(run_id)
    storage.close()
    if record is None:
        typer.echo(f"no run with id {run_id} in {db}", err=True)
        raise typer.Exit(1)
    typer.echo(json.dumps(record, indent=2, default=str))


if __name__ == "__main__":
    app()
