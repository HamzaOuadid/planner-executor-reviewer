"""The task suite: real, known-correct coding tasks with a ground-truth
pytest check (spec M1: "Define 5-8 real multi-step tasks with known-correct
outcomes").

Each task ships:
  - ``starter_code``: a deliberately buggy implementation
  - ``test_code``: a real pytest file that fails against ``starter_code``
    and passes against ``reference_fix``
  - ``reference_fix``: the known-correct implementation (used only by the
    demo/eval scripts to script a FakeLLMClient's canned "correct attempt"
    response -- the grading itself is always a real ``pytest`` subprocess
    run against whatever the executor actually wrote, never a string
    comparison against this field)

Tests never live under ``src/`` as real ``test_*.py`` files on disk (that
would make the project's own ``pytest`` collection try to import them).
Instead they're plain string constants materialized into a throwaway
sandbox directory at run time by :func:`materialize_sandbox`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Task:
    id: str
    description: str
    solution_filename: str
    test_filename: str
    starter_code: str
    test_code: str
    reference_fix: str


def materialize_sandbox(task: "Task", sandbox_dir: Path, *, use_fix: str | None = None) -> None:
    """Write the task's starter (or ``use_fix``) code and its tests into
    ``sandbox_dir``, which must already exist."""
    (sandbox_dir / task.solution_filename).write_text(
        use_fix if use_fix is not None else task.starter_code, encoding="utf-8"
    )
    (sandbox_dir / task.test_filename).write_text(task.test_code, encoding="utf-8")


TASKS: list[Task] = [
    Task(
        id="is_palindrome",
        description=(
            "Fix is_palindrome(s) in solution.py so it correctly reports whether a "
            "string is a palindrome, ignoring case, spaces, and punctuation."
        ),
        solution_filename="solution.py",
        test_filename="test_solution.py",
        starter_code='''\
def is_palindrome(s: str) -> bool:
    return s == s[::-1]
''',
        test_code='''\
from solution import is_palindrome


def test_simple_palindrome():
    assert is_palindrome("racecar") is True


def test_simple_non_palindrome():
    assert is_palindrome("hello") is False


def test_ignores_case_and_punctuation():
    assert is_palindrome("A man, a plan, a canal: Panama") is True


def test_ignores_spaces():
    assert is_palindrome("No lemon, no melon") is True


def test_empty_string():
    assert is_palindrome("") is True
''',
        reference_fix='''\
def is_palindrome(s: str) -> bool:
    cleaned = "".join(ch.lower() for ch in s if ch.isalnum())
    return cleaned == cleaned[::-1]
''',
    ),
    Task(
        id="fibonacci",
        description=(
            "Fix fibonacci(n) in solution.py so it returns the correct nth "
            "Fibonacci number for all n >= 0, including the n=0 base case."
        ),
        solution_filename="solution.py",
        test_filename="test_solution.py",
        starter_code='''\
def fibonacci(n: int) -> int:
    if n <= 2:
        return 1
    return fibonacci(n - 1) + fibonacci(n - 2)
''',
        test_code='''\
from solution import fibonacci


def test_zero():
    assert fibonacci(0) == 0


def test_one():
    assert fibonacci(1) == 1


def test_two():
    assert fibonacci(2) == 1


def test_small_values():
    assert fibonacci(3) == 2
    assert fibonacci(5) == 5


def test_ten():
    assert fibonacci(10) == 55
''',
        reference_fix='''\
def fibonacci(n: int) -> int:
    if n == 0:
        return 0
    if n <= 2:
        return 1
    return fibonacci(n - 1) + fibonacci(n - 2)
''',
    ),
    Task(
        id="flatten_list",
        description=(
            "Fix flatten(nested) in solution.py so it fully flattens an "
            "arbitrarily deeply nested list, not just one level."
        ),
        solution_filename="solution.py",
        test_filename="test_solution.py",
        starter_code='''\
def flatten(nested: list) -> list:
    result = []
    for item in nested:
        if isinstance(item, list):
            result.extend(item)
        else:
            result.append(item)
    return result
''',
        test_code='''\
from solution import flatten


def test_flat_already():
    assert flatten([1, 2, 3]) == [1, 2, 3]


def test_one_level():
    assert flatten([1, [2, 3], 4]) == [1, 2, 3, 4]


def test_deeply_nested():
    assert flatten([1, [2, [3, 4], 5], 6]) == [1, 2, 3, 4, 5, 6]


def test_empty():
    assert flatten([]) == []


def test_very_deep():
    assert flatten([[[[1]]], 2]) == [1, 2]
''',
        reference_fix='''\
def flatten(nested: list) -> list:
    result = []
    for item in nested:
        if isinstance(item, list):
            result.extend(flatten(item))
        else:
            result.append(item)
    return result
''',
    ),
    Task(
        id="word_count",
        description=(
            "Fix word_count(text) in solution.py so it returns a dict of "
            "word -> frequency that is case-insensitive and ignores "
            "surrounding punctuation."
        ),
        solution_filename="solution.py",
        test_filename="test_solution.py",
        starter_code='''\
def word_count(text: str) -> dict:
    counts = {}
    for word in text.split():
        counts[word] = counts.get(word, 0) + 1
    return counts
''',
        test_code='''\
from solution import word_count


def test_case_insensitive():
    assert word_count("The the THE") == {"the": 3}


def test_strips_punctuation():
    assert word_count("Cat, cat. dog!") == {"cat": 2, "dog": 1}


def test_empty_string():
    assert word_count("") == {}


def test_mixed():
    assert word_count("Hello World hello") == {"hello": 2, "world": 1}
''',
        reference_fix='''\
import string


def word_count(text: str) -> dict:
    counts = {}
    for raw in text.split():
        word = raw.strip(string.punctuation).lower()
        if not word:
            continue
        counts[word] = counts.get(word, 0) + 1
    return counts
''',
    ),
    Task(
        id="dedupe_preserve_order",
        description=(
            "Fix dedupe(items) in solution.py so it removes duplicate "
            "elements while preserving the first occurrence and original "
            "order (it must not drop items that merely repeat)."
        ),
        solution_filename="solution.py",
        test_filename="test_solution.py",
        starter_code='''\
def dedupe(items: list) -> list:
    return [item for item in items if items.count(item) == 1]
''',
        test_code='''\
from solution import dedupe


def test_removes_duplicates_preserves_order():
    assert dedupe([1, 2, 2, 3, 1, 4]) == [1, 2, 3, 4]


def test_empty():
    assert dedupe([]) == []


def test_single():
    assert dedupe([5]) == [5]


def test_strings():
    assert dedupe(["b", "a", "b", "c"]) == ["b", "a", "c"]


def test_no_duplicates():
    assert dedupe([1, 2, 3]) == [1, 2, 3]
''',
        reference_fix='''\
def dedupe(items: list) -> list:
    seen = set()
    result = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result
''',
    ),
    Task(
        id="safe_divide",
        description=(
            "Fix safe_divide(a, b, default=None) in solution.py so it "
            "returns 'default' instead of raising when dividing by zero."
        ),
        solution_filename="solution.py",
        test_filename="test_solution.py",
        starter_code='''\
def safe_divide(a, b, default=None):
    return a / b
''',
        test_code='''\
from solution import safe_divide


def test_normal_division():
    assert safe_divide(10, 2) == 5


def test_division_by_zero_returns_default_none():
    assert safe_divide(10, 0) is None


def test_division_by_zero_returns_custom_default():
    assert safe_divide(10, 0, default=-1) == -1


def test_float_division():
    assert safe_divide(7, 2) == 3.5
''',
        reference_fix='''\
def safe_divide(a, b, default=None):
    try:
        return a / b
    except ZeroDivisionError:
        return default
''',
    ),
]

_TASKS_BY_ID: dict[str, Task] = {t.id: t for t in TASKS}


def get_task(task_id: str) -> Task:
    try:
        return _TASKS_BY_ID[task_id]
    except KeyError as exc:
        raise KeyError(
            f"unknown task id {task_id!r}. Known tasks: {sorted(_TASKS_BY_ID)}"
        ) from exc
