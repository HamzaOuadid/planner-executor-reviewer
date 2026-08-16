"""Tolerant JSON extraction from raw LLM text.

Real LLMs routinely wrap JSON in markdown code fences or add a stray
sentence before/after it. This is deliberately forgiving about that but
still raises a clear, typed error (never a bare ``json.JSONDecodeError``)
when the text truly isn't parseable JSON -- that's the "malformed
structured output from an LLM" edge case from the spec.
"""

from __future__ import annotations

import json
import re

from peer_loop.exceptions import MalformedResponseError

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def extract_json(text: str) -> dict:
    """Parse ``text`` as JSON, stripping a single markdown code fence if present.

    Raises ``MalformedResponseError`` (never a raw exception type) if the
    text cannot be parsed into a JSON object.
    """
    if text is None:
        raise MalformedResponseError("LLM response was empty (None)")

    candidate = text.strip()
    fence_match = _FENCE_RE.search(candidate)
    if fence_match:
        candidate = fence_match.group(1).strip()

    if not candidate:
        raise MalformedResponseError("LLM response was empty after stripping whitespace/fences")

    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError as exc:
        snippet = text[:300]
        raise MalformedResponseError(
            f"could not parse LLM response as JSON: {exc}. Raw text (first 300 chars): {snippet!r}"
        ) from exc

    if not isinstance(parsed, dict):
        raise MalformedResponseError(
            f"expected a JSON object at the top level, got {type(parsed).__name__}"
        )
    return parsed
