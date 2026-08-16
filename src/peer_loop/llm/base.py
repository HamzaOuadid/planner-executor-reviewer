"""The provider-abstraction every LLM-backed role talks to.

Planner and Reviewer never call an SDK directly -- they hold an
``LLMClient`` and call ``.complete(role=..., system=..., user=...)``.
That's what makes it possible to swap in ``FakeLLMClient`` for tests/local
dev and ``RealLLMClient`` for production without touching planner/reviewer
code at all.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class LLMClient(Protocol):
    """A single request/response completion call, role-tagged for logging
    and for fixture-keying in FakeLLMClient."""

    def complete(self, *, role: str, system: str, user: str) -> str:
        """Return the raw text completion for the given system/user prompt.

        ``role`` is one of "planner" or "reviewer" (informational -- real
        clients may ignore it; FakeLLMClient uses it as the default lookup
        key for scripted responses).
        """
        ...
