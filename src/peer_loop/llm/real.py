"""A real LLM client backed by the Anthropic or OpenAI API.

Not exercised by the test suite (no API key is configured in CI or in this
dev environment) -- ``tests/`` covers the orchestration logic exclusively
through ``FakeLLMClient``. This module is still real, working code: it is
constructed the same way the fake is (implements the same ``LLMClient``
protocol via structural typing, no inheritance needed) and will work as
soon as a key is present in the environment or a ``.env`` file.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

Provider = Literal["anthropic", "openai"]

DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-4-5-20250929"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"


class RealLLMClient:
    """Calls a real hosted LLM. Construct via :meth:`from_env`."""

    def __init__(self, provider: Provider, api_key: str, model: str) -> None:
        self.provider = provider
        self.api_key = api_key
        self.model = model

    @classmethod
    def from_env(cls, env_path: str | Path | None = None) -> "RealLLMClient":
        """Load ``.env`` (if present) and pick a provider.

        Anthropic wins if both ``ANTHROPIC_API_KEY`` and ``OPENAI_API_KEY``
        are set. Raises ``RuntimeError`` with an actionable message if
        neither is configured -- the intended fallback for local dev and
        tests is ``FakeLLMClient``, not a crash deep inside the loop.
        """
        try:
            from dotenv import load_dotenv

            load_dotenv(env_path)
        except ImportError:
            pass  # python-dotenv not installed; fall back to real env vars only

        anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
        if anthropic_key:
            model = os.environ.get("PEER_LOOP_ANTHROPIC_MODEL", DEFAULT_ANTHROPIC_MODEL)
            return cls("anthropic", anthropic_key, model)

        openai_key = os.environ.get("OPENAI_API_KEY")
        if openai_key:
            model = os.environ.get("PEER_LOOP_OPENAI_MODEL", DEFAULT_OPENAI_MODEL)
            return cls("openai", openai_key, model)

        raise RuntimeError(
            "No ANTHROPIC_API_KEY or OPENAI_API_KEY found (checked process "
            "env and .env). RealLLMClient needs one of these to make actual "
            "API calls. For tests and local dev without a key, use "
            "peer_loop.llm.fake.FakeLLMClient instead."
        )

    def complete(self, *, role: str, system: str, user: str) -> str:
        if self.provider == "anthropic":
            return self._complete_anthropic(system, user)
        return self._complete_openai(system, user)

    def _complete_anthropic(self, system: str, user: str) -> str:
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover - exercised only without the dep
            raise RuntimeError(
                "The 'anthropic' package is not installed. Run: "
                "pip install -e '.[anthropic]'"
            ) from exc

        client = anthropic.Anthropic(api_key=self.api_key)
        response = client.messages.create(
            model=self.model,
            max_tokens=2048,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(
            block.text for block in response.content if getattr(block, "type", None) == "text"
        )

    def _complete_openai(self, system: str, user: str) -> str:
        try:
            import openai
        except ImportError as exc:  # pragma: no cover - exercised only without the dep
            raise RuntimeError(
                "The 'openai' package is not installed. Run: pip install -e '.[openai]'"
            ) from exc

        client = openai.OpenAI(api_key=self.api_key)
        response = client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return response.choices[0].message.content or ""
