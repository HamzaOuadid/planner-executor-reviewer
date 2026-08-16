"""Scripted FakeLLMClient fixtures for the task suite.

These give each task a realistic, hand-authored planner/reviewer script:
some tasks are solved correctly on the first attempt, others deliberately
start with a flawed fix (missing a case, an unhandled exception, a
one-level-only recursion) that fails real pytest, gets a specific
rejection from the reviewer, and is corrected on the second attempt. This
is what makes the eval comparison (M4) and the demo trace (README)
reproducible without a live LLM: the "intelligence" is hand-scripted here,
the orchestration around it (loop control, retries, logging, persistence)
is exercised for real.

``build_reviewer_error_llm`` scripts the one deliberately-seeded case
where the reviewer itself is wrong (rejects a result that actually passed
its tests) -- tracked, not hidden, per spec section 9/13.
"""

from __future__ import annotations

import json

from peer_loop.llm.fake import FakeLLMClient
from peer_loop.task_suite.tasks import get_task


def _plan_json(content: str, rationale: str) -> str:
    return json.dumps(
        {
            "rationale": rationale,
            "steps": [
                {
                    "tool": "write_file",
                    "description": "apply the fix to solution.py",
                    "path": "solution.py",
                    "content": content,
                },
                {
                    "tool": "run_tests",
                    "description": "run the test suite to verify the fix",
                    "path": "test_solution.py",
                },
            ],
        }
    )


def _review_json(accepted: bool, reason: str) -> str:
    return json.dumps({"accepted": accepted, "reason": reason})


# task_id -> list of (planner_content, planner_rationale, reviewer_accepted, reviewer_reason)
# one tuple per iteration/round, in order.
_SCRIPTS: dict[str, list[tuple[str, str, bool, str]]] = {
    "is_palindrome": [
        (
            get_task("is_palindrome").reference_fix,
            "normalize the string (lowercase, strip non-alphanumeric characters) before comparing it to its reverse",
            True,
            "all 5 tests passed, including the case/punctuation-insensitive palindrome checks",
        ),
    ],
    "fibonacci": [
        (
            get_task("fibonacci").reference_fix,
            "add an explicit base case for n == 0 to the recursive definition",
            True,
            "all 6 tests passed, including the n=0 edge case",
        ),
    ],
    "flatten_list": [
        (
            get_task("flatten_list").starter_code,
            "use list.extend() to merge each nested list into the result",
            False,
            "test_deeply_nested failed: flatten([1, [2, [3, 4], 5], 6]) returned "
            "[1, 2, [3, 4], 5, 6] instead of [1, 2, 3, 4, 5, 6] -- extend() only merges "
            "one level of nesting, the function needs to recurse into nested items",
        ),
        (
            get_task("flatten_list").reference_fix,
            "recurse into nested list items instead of only extending one level, per reviewer feedback",
            True,
            "all 5 tests passed, including the deeply-nested case that failed last round",
        ),
    ],
    "word_count": [
        (
            "def word_count(text: str) -> dict:\n"
            "    counts = {}\n"
            "    for word in text.split():\n"
            "        word = word.lower()\n"
            "        counts[word] = counts.get(word, 0) + 1\n"
            "    return counts\n",
            "lowercase each word before counting so case differences collapse together",
            False,
            "test_strips_punctuation failed: word_count('Cat, cat. dog!') returned "
            "{'cat,': 1, 'cat.': 1, 'dog!': 1} instead of {'cat': 2, 'dog': 1} -- "
            "punctuation attached to words is never stripped",
        ),
        (
            get_task("word_count").reference_fix,
            "strip surrounding punctuation with str.strip(string.punctuation) in addition to lowercasing, per reviewer feedback",
            True,
            "all 4 tests passed, including punctuation stripping",
        ),
    ],
    "dedupe_preserve_order": [
        (
            get_task("dedupe_preserve_order").reference_fix,
            "track seen items in a set while appending each new item to the result list in its original order",
            True,
            "all 5 tests passed, including order preservation and the strings case",
        ),
    ],
    "safe_divide": [
        (
            get_task("safe_divide").starter_code,
            "the division itself is already correct for the normal case",
            False,
            "test_division_by_zero_returns_default_none failed: safe_divide(10, 0) raised "
            "ZeroDivisionError instead of returning None -- the function never catches the exception",
        ),
        (
            get_task("safe_divide").reference_fix,
            "wrap the division in try/except ZeroDivisionError and return 'default' on failure, per reviewer feedback",
            True,
            "all 4 tests passed, including both zero-division cases",
        ),
    ],
}


def build_scripted_llm(task_id: str) -> FakeLLMClient:
    """A FakeLLMClient programmed with the realistic, deterministic
    planner/reviewer script for ``task_id`` (see ``_SCRIPTS`` above)."""
    rounds = _SCRIPTS[task_id]
    planner_responses = [_plan_json(content, rationale) for content, rationale, _, _ in rounds]
    reviewer_responses = [_review_json(accepted, reason) for _, _, accepted, reason in rounds]
    return FakeLLMClient(script={"planner": planner_responses, "reviewer": reviewer_responses})


def build_reviewer_error_llm() -> FakeLLMClient:
    """Seeds the one deliberate 'the reviewer is wrong' case (spec section
    9/13): the executor's first attempt is actually CORRECT (passes every
    test), but the reviewer hallucinates a plausible-sounding but factually
    wrong rejection anyway. The identical content is resubmitted and
    accepted on the second round. LoopController flags this via
    ``Iteration.reviewer_disagreed_with_tests`` so it shows up in logs/eval
    instead of being silently absorbed."""
    task = get_task("dedupe_preserve_order")
    correct = task.reference_fix
    planner_responses = [
        _plan_json(correct, "track seen items in a set while preserving original order"),
        _plan_json(correct, "resubmitting the same fix; the reviewer's rejection was a misread of the spec"),
    ]
    reviewer_responses = [
        _review_json(
            False,
            "test_strings failed: dedupe(['b', 'a', 'b', 'c']) returned ['b', 'a', 'c'] but "
            "order-preserving dedup should sort remaining items alphabetically, expected ['a', 'b', 'c']",
        ),
        _review_json(
            True,
            "all 5 tests passed; correcting my earlier misreading of the order-preservation requirement "
            "-- 'preserve order' means first-occurrence order, not alphabetical",
        ),
    ]
    return FakeLLMClient(script={"planner": planner_responses, "reviewer": reviewer_responses})


def build_always_reject_llm(max_calls: int = 50) -> FakeLLMClient:
    """A reviewer that rejects every attempt with a specific (non-generic)
    reason, ``max_calls`` times over -- used to test that the loop
    controller's max-iteration cap is what stops the loop (not the fixture
    running dry), i.e. that it fails gracefully rather than looping
    forever or raising an unhandled exception.
    """
    task = get_task("fibonacci")
    plan_response = _plan_json(task.starter_code, "attempt to fix the base case")
    reject_response = _review_json(
        False,
        "test_zero failed: fibonacci(0) returned 1 instead of 0 -- the base case is still missing",
    )
    return FakeLLMClient(
        script={
            "planner": [plan_response] * max_calls,
            "reviewer": [reject_response] * max_calls,
        }
    )
