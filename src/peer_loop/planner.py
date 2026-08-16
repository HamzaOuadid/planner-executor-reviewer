"""The planner: given a task (and, on revision, the reviewer's feedback),
produces a step-by-step Plan naming a tool and expected outcome per step.
"""

from __future__ import annotations

from pydantic import ValidationError

from peer_loop.exceptions import MalformedResponseError
from peer_loop.json_utils import extract_json
from peer_loop.llm.base import LLMClient
from peer_loop.models import Plan, VALID_TOOLS

SYSTEM_PROMPT = """You are the Planner in a planner/executor/reviewer coding agent loop.

Given a coding task, produce a JSON plan with this exact shape:
{
  "rationale": "<one or two sentences on your approach>",
  "steps": [
    {"tool": "write_file", "description": "<why>", "path": "solution.py", "content": "<full file content>"},
    {"tool": "run_tests", "description": "<why>", "path": "test_solution.py"}
  ]
}

Valid tool names: read_file, write_file, run_tests, list_files.
A "write_file" step must include the COMPLETE new file content in "content" (not a diff).
Always end the plan with a "run_tests" step so the fix can be verified.
Respond with ONLY the JSON object, no prose, no markdown fences.
"""


class Planner:
    """Produces a :class:`~peer_loop.models.Plan` via an LLM call."""

    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    def plan(self, task_description: str, prior_feedback: str | None = None) -> Plan:
        user_prompt = f"Task:\n{task_description}\n"
        if prior_feedback:
            user_prompt += (
                "\nYour previous attempt was REJECTED by the reviewer for this reason:\n"
                f"{prior_feedback}\n"
                "Produce a revised plan that specifically addresses this feedback."
            )

        raw = self.llm.complete(role="planner", system=SYSTEM_PROMPT, user=user_prompt)
        data = extract_json(raw)

        try:
            plan = Plan.model_validate(data)
        except ValidationError as exc:
            raise MalformedResponseError(f"planner JSON did not match the Plan schema: {exc}") from exc

        if not plan.steps:
            raise MalformedResponseError("planner produced a plan with zero steps")

        for step in plan.steps:
            if step.tool not in VALID_TOOLS:
                raise MalformedResponseError(
                    f"planner named an unknown tool {step.tool!r}; valid tools are {VALID_TOOLS}"
                )

        return plan
