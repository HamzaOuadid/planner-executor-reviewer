"""Pydantic data models shared across the planner/executor/reviewer loop.

These mirror the API contract in the spec (section 7) and the persisted
data model (section 6): agent_runs / agent_iterations map onto
``RunResult`` / ``Iteration`` below (see storage.py for the SQLite schema).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

StepStatus = Literal["success", "failed", "timeout"]
OverallStatus = Literal["success", "failed", "timeout", "error"]
RunStatus = Literal["success", "failed"]

# Tools the executor knows how to run. Kept as a closed set so a malformed
# plan step (e.g. an LLM hallucinating a tool name) fails fast and visibly
# rather than doing something unexpected.
VALID_TOOLS = ("read_file", "write_file", "run_tests", "list_files")


class PlanStep(BaseModel):
    """One step of a plan: a tool to call, why, and the arguments for it."""

    tool: str
    description: str
    path: str | None = None
    content: str | None = None


class Plan(BaseModel):
    """A step-by-step plan produced by the planner for one iteration."""

    rationale: str
    steps: list[PlanStep] = Field(default_factory=list)


class StepResult(BaseModel):
    """The outcome of executing a single :class:`PlanStep`."""

    tool: str
    description: str
    status: StepStatus
    output: str
    duration_ms: float
    attempts: int = 1


class ExecutionResult(BaseModel):
    """The outcome of executing an entire :class:`Plan`."""

    step_results: list[StepResult] = Field(default_factory=list)
    tests_passed: bool | None = None
    tests_output: str = ""
    overall_status: OverallStatus


class ReviewVerdict(BaseModel):
    """The reviewer's accept/reject decision plus a specific reason.

    ``reason`` must always be filled in -- even on accept -- so the log is
    equally informative in both directions (acceptance criteria for the
    "developer debugging a failed task" story: every rejection has a
    specific, non-generic reason visible in the log).
    """

    accepted: bool
    reason: str


class Iteration(BaseModel):
    """One full plan -> execute -> review cycle, as persisted/logged."""

    iteration_number: int
    plan: Plan | None
    execution_result: ExecutionResult | None
    review_verdict: ReviewVerdict
    planner_malformed_output: bool = False
    reviewer_disagreed_with_tests: bool = False
    duration_ms: float = 0.0


class RunResult(BaseModel):
    """The return value of ``run_task`` per the API contract (section 7)."""

    status: RunStatus
    task_text: str
    result: str | None
    iterations: list[Iteration] = Field(default_factory=list)
    iteration_count: int = 0
    total_duration_ms: float = 0.0
