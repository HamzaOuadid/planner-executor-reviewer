"""A deterministic, scriptable fake LLM client.

This is the backbone of the test suite: every planner/reviewer/loop test
in this repo drives the orchestration logic through ``FakeLLMClient``
instead of a real API, so the tests are fast, free, and 100% reproducible.
Program it with a queue of canned responses per role (or per a custom
key), and it hands them out in order, recording every call it received so
tests can assert on what the planner/reviewer actually sent.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class RecordedCall:
    role: str
    system: str
    user: str


class FakeLLMClient:
    """Program with ``script={"planner": [resp1, resp2], "reviewer": [...]}``.

    Each call to ``complete(role=...)`` pops the next response off the
    queue for that role (or for whatever ``key_fn`` computes -- defaults to
    just the role, which is enough for "first attempt is flawed, second
    attempt is correct" style scripts used throughout this repo).

    If the queue for a key is empty, falls back to ``default`` if one was
    given, otherwise raises ``AssertionError`` -- fail loudly rather than
    silently returning something misleading.
    """

    def __init__(
        self,
        script: dict[str, list[str]] | None = None,
        default: str | None = None,
        key_fn: Callable[[str, str, str], str] | None = None,
    ) -> None:
        self._script: dict[str, list[str]] = {k: list(v) for k, v in (script or {}).items()}
        self._default = default
        self._key_fn = key_fn or (lambda role, system, user: role)
        self.calls: list[RecordedCall] = []

    def program(self, key: str, responses: list[str]) -> None:
        """Append canned responses to the queue for ``key`` (e.g. a role)."""
        self._script.setdefault(key, []).extend(responses)

    def complete(self, *, role: str, system: str, user: str) -> str:
        self.calls.append(RecordedCall(role=role, system=system, user=user))
        key = self._key_fn(role, system, user)
        queue = self._script.get(key)
        if queue:
            return queue.pop(0)
        if self._default is not None:
            return self._default
        raise AssertionError(
            f"FakeLLMClient: no scripted response left for key={key!r} "
            f"(role={role!r}). Program it with FakeLLMClient(script={{...}}) "
            f"or .program(key, [...])."
        )

    def calls_for(self, role: str) -> list[RecordedCall]:
        return [c for c in self.calls if c.role == role]
