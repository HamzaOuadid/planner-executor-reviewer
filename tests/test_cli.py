from typer.testing import CliRunner

from peer_loop.cli import app

runner = CliRunner()


def test_list_tasks_lists_every_task():
    result = runner.invoke(app, ["list-tasks"])
    assert result.exit_code == 0
    assert "word_count" in result.output
    assert "fibonacci" in result.output


def test_demo_runs_and_reports_success():
    result = runner.invoke(app, ["demo"])
    assert result.exit_code == 0
    assert "FINAL STATUS: success" in result.output
    assert '"event": "run_start"' in result.output
    assert '"event": "run_end"' in result.output


def test_eval_command_prints_comparison_table():
    result = runner.invoke(app, ["eval"])
    assert result.exit_code == 0
    assert "with reviewer" in result.output
    assert "baseline" in result.output


def test_run_command_succeeds_for_a_one_shot_task(tmp_path):
    db_path = tmp_path / "runs.db"
    result = runner.invoke(app, ["run", "fibonacci", "--db", str(db_path)])
    assert result.exit_code == 0
    assert "FINAL STATUS: success" in result.output
    assert db_path.exists()


def test_run_then_trace_roundtrips_a_real_multi_round_run(tmp_path):
    """End-to-end: `run` persists the loop to SQLite, `trace` reads it back
    -- this is the "developer debugging a failed task" workflow made
    concrete: inspect a past run's rejection reasons after the fact."""
    db_path = tmp_path / "runs.db"
    run_result = runner.invoke(app, ["run", "word_count", "--db", str(db_path)])
    assert run_result.exit_code == 0

    from peer_loop.storage import Storage

    storage = Storage(db_path)
    runs = storage.list_runs()
    assert len(runs) == 1
    run_id = runs[0]["id"]
    storage.close()

    trace_result = runner.invoke(app, ["trace", str(run_id), "--db", str(db_path)])
    assert trace_result.exit_code == 0
    assert "punctuation" in trace_result.output
    assert '"review_verdict": "rejected"' in trace_result.output
    assert '"review_verdict": "accepted"' in trace_result.output


def test_run_command_reviewer_error_demo_flag():
    result = runner.invoke(app, ["run", "dedupe_preserve_order", "--reviewer-error-demo"])
    assert result.exit_code == 0
    assert "reviewer_disagreed_with_tests\": true" in result.output


def test_run_command_exits_nonzero_on_unknown_task():
    result = runner.invoke(app, ["run", "no-such-task"])
    assert result.exit_code != 0


def test_trace_command_reports_missing_run(tmp_path):
    db_path = tmp_path / "empty.db"
    from peer_loop.storage import Storage

    Storage(db_path).close()
    result = runner.invoke(app, ["trace", "999", "--db", str(db_path)])
    assert result.exit_code == 1
