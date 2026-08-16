"""peer_loop: a planner -> executor -> reviewer multi-agent loop.

The reviewer can reject the executor's output and send it back to the
planner with a specific reason; the loop controller caps total iterations
to prevent infinite revision loops.
"""

__version__ = "0.1.0"
