"""SQLite persistence matching the spec's data model (section 6):

  agent_runs (id, task_text, final_status, iteration_count, total_duration_ms)
  agent_iterations (run_id, iteration_number, plan_json, execution_result_json,
                     review_verdict, review_reason)

Kept as a thin wrapper over stdlib ``sqlite3`` -- no ORM, no server, works
anywhere Python runs (this environment has no Postgres/Docker available).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from peer_loop.models import RunResult

_SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT,
    task_text TEXT NOT NULL,
    final_status TEXT NOT NULL,
    result_summary TEXT,
    iteration_count INTEGER NOT NULL,
    total_duration_ms REAL NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS agent_iterations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES agent_runs(id),
    iteration_number INTEGER NOT NULL,
    plan_json TEXT,
    execution_result_json TEXT,
    review_verdict TEXT NOT NULL,
    review_reason TEXT NOT NULL,
    reviewer_disagreed_with_tests INTEGER NOT NULL DEFAULT 0,
    planner_malformed_output INTEGER NOT NULL DEFAULT 0
);
"""


class Storage:
    """Opens (and creates if needed) a SQLite database at ``db_path``."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = str(db_path)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def save_run(self, result: RunResult, task_id: str | None = None) -> int:
        cur = self._conn.execute(
            "INSERT INTO agent_runs (task_id, task_text, final_status, result_summary, "
            "iteration_count, total_duration_ms) VALUES (?, ?, ?, ?, ?, ?)",
            (
                task_id,
                result.task_text,
                result.status,
                result.result,
                result.iteration_count,
                result.total_duration_ms,
            ),
        )
        run_id = cur.lastrowid
        assert run_id is not None

        for iteration in result.iterations:
            self._conn.execute(
                "INSERT INTO agent_iterations (run_id, iteration_number, plan_json, "
                "execution_result_json, review_verdict, review_reason, "
                "reviewer_disagreed_with_tests, planner_malformed_output) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    run_id,
                    iteration.iteration_number,
                    iteration.plan.model_dump_json() if iteration.plan else None,
                    iteration.execution_result.model_dump_json() if iteration.execution_result else None,
                    "accepted" if iteration.review_verdict.accepted else "rejected",
                    iteration.review_verdict.reason,
                    int(iteration.reviewer_disagreed_with_tests),
                    int(iteration.planner_malformed_output),
                ),
            )
        self._conn.commit()
        return run_id

    def get_run(self, run_id: int) -> dict | None:
        run_row = self._conn.execute("SELECT * FROM agent_runs WHERE id = ?", (run_id,)).fetchone()
        if run_row is None:
            return None
        iter_rows = self._conn.execute(
            "SELECT * FROM agent_iterations WHERE run_id = ? ORDER BY iteration_number", (run_id,)
        ).fetchall()
        return {"run": dict(run_row), "iterations": [dict(r) for r in iter_rows]}

    def list_runs(self, limit: int = 20) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM agent_runs ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
