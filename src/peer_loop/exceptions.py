"""Shared exception types used across the loop.

Keeping these distinct (rather than reusing generic ``ValueError``/
``RuntimeError``) is what lets the loop controller and tests tell apart
"the LLM gave us garbage" from "a tool genuinely failed" from
"a tool is being slow/flaky" -- each edge case in the spec's section 9
needs to be distinguishable, not just caught.
"""


class MalformedResponseError(Exception):
    """Raised when an LLM response cannot be parsed into the expected
    structured shape (e.g. invalid JSON, or valid JSON missing required
    fields). Callers should treat this as a soft failure for that
    iteration, not a crash."""


class TransientToolError(Exception):
    """A tool call failed in a way that is worth retrying (e.g. a simulated
    flaky I/O error). Distinct from a tool that ran fine but produced a
    wrong/failing result."""


class ToolTimeoutError(Exception):
    """A tool call (e.g. running the test suite) exceeded its time budget.
    Must be distinguishable in the log from a tool that completed but
    produced a wrong result (spec section 9)."""


class UnknownToolError(Exception):
    """A plan step named a tool the executor doesn't recognize."""
