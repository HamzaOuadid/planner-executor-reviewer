"""The executor's real tools.

These are genuine, working operations against a sandbox directory on disk
-- not stubs. ``run_tests`` really shells out to ``pytest`` in a
subprocess and returns its real pass/fail outcome, which is what gives the
reviewer an objective, non-LLM-opinion signal to check the executor's work
against for every task in the suite.

Fault injection (simulated transient failures / timeouts, used by the
executor's retry-with-backoff logic and its tests) lives in executor.py,
not here -- these functions always do the real thing.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from peer_loop.exceptions import ToolTimeoutError


def _resolve(sandbox: Path, rel_path: str) -> Path:
    """Resolve ``rel_path`` inside ``sandbox``, refusing to escape it."""
    target = (sandbox / rel_path).resolve()
    sandbox_resolved = sandbox.resolve()
    if sandbox_resolved not in target.parents and target != sandbox_resolved:
        raise ValueError(f"path {rel_path!r} escapes the sandbox directory")
    return target


def read_file(sandbox: Path, path: str) -> str:
    """Read a text file from the sandbox. Raises FileNotFoundError if absent."""
    target = _resolve(sandbox, path)
    return target.read_text(encoding="utf-8")


def write_file(sandbox: Path, path: str, content: str) -> str:
    """Write ``content`` to ``path`` inside the sandbox, creating parents."""
    target = _resolve(sandbox, path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content or "", encoding="utf-8")
    return f"wrote {len(content or '')} bytes to {path}"


def list_files(sandbox: Path) -> str:
    """Return a newline-separated listing of every file in the sandbox."""
    files = sorted(str(p.relative_to(sandbox)) for p in sandbox.rglob("*") if p.is_file())
    return "\n".join(files)


def run_tests(sandbox: Path, test_path: str, timeout_seconds: float = 15.0) -> tuple[bool, str]:
    """Run ``pytest`` against ``test_path`` inside the sandbox, for real.

    Returns ``(passed, combined_output)``. Raises ``ToolTimeoutError`` (not
    a generic TimeoutError) if the process exceeds ``timeout_seconds`` --
    this must stay distinguishable in the log from a run that completed
    but failed its assertions.
    """
    target = _resolve(sandbox, test_path)
    if not target.exists():
        raise FileNotFoundError(f"test file not found: {test_path}")

    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", str(target), "-q", "--no-header"],
            cwd=str(sandbox),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        partial = (exc.stdout or "") + (exc.stderr or "")
        raise ToolTimeoutError(
            f"pytest on {test_path} exceeded {timeout_seconds}s timeout. Partial output:\n{partial}"
        ) from exc

    output = proc.stdout + proc.stderr
    return proc.returncode == 0, output
