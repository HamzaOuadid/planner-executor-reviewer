"""The reviewer: given the task, the plan, and the executor's output,
decides whether the output actually satisfies the task -- and if not,
must give a specific, non-generic reason (never just "it's wrong").
"""

from __future__ import annotations

from pydantic import ValidationError

from peer_loop.exceptions import MalformedResponseError
from peer_loop.json_utils import extract_json
from peer_loop.llm.base import LLMClient
from peer_loop.models import ExecutionResult, Plan, ReviewVerdict

SYSTEM_PROMPT = """You are the Reviewer in a planner/executor/reviewer coding agent loop.

You are given the original task, the plan that was executed, and the real
result of executing it (including actual pytest output). Decide whether
the task is genuinely satisfied.

Respond with ONLY a JSON object of this exact shape, no prose, no markdown fences:
{"accepted": true|false, "reason": "<specific reason, quoting the failing assertion or test name if rejecting>"}

Rules:
- If the test output shows failures, you MUST reject and name the specific failing test(s).
- If all tests passed, you should normally accept.
- Never give a generic reason like "it's wrong" or "not good enough" -- always cite specifics
  (which test failed, what the assertion expected vs got, or what step errored).
"""

# Reasons this generic are rejected as malformed reviewer output -- the
# acceptance criteria for "I can see exactly why the loop rejected an
# attempt" requires a *specific* reason, not a rubber stamp.
_GENERIC_REASONS = {
    "bad",
    "wrong",
    "no good",
    "not good",
    "incorrect",
    "it's wrong",
    "its wrong",
    "not good enough",
    "fail",
    "failed",
}


class Reviewer:
    """Produces a :class:`~peer_loop.models.ReviewVerdict` via an LLM call."""

    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    def review(self, task_description: str, plan: Plan, result: ExecutionResult) -> ReviewVerdict:
        step_lines = "\n".join(
            f"  - {s.tool}({s.description}): status={s.status}, output={s.output[:400]!r}"
            for s in result.step_results
        )
        user_prompt = (
            f"Task:\n{task_description}\n\n"
            f"Plan rationale: {plan.rationale}\n\n"
            f"Execution steps:\n{step_lines}\n\n"
            f"tests_passed: {result.tests_passed}\n"
            f"overall_status: {result.overall_status}\n"
            f"tests_output:\n{result.tests_output[:2000]}\n"
        )

        raw = self.llm.complete(role="reviewer", system=SYSTEM_PROMPT, user=user_prompt)
        data = extract_json(raw)

        try:
            verdict = ReviewVerdict.model_validate(data)
        except ValidationError as exc:
            raise MalformedResponseError(f"reviewer JSON did not match the ReviewVerdict schema: {exc}") from exc

        reason_normalized = verdict.reason.strip().lower().rstrip(".")
        if not verdict.reason.strip():
            raise MalformedResponseError("reviewer gave an empty reason")
        if not verdict.accepted and reason_normalized in _GENERIC_REASONS:
            raise MalformedResponseError(
                f"reviewer rejected with a non-specific, generic reason: {verdict.reason!r}"
            )

        return verdict
