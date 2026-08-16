"""M4: success-rate comparison with vs. without the reviewer stage.

This is the proof metric (spec section 14): a measured success rate with
the reviewer active vs. the reviewer stubbed to always-accept, graded
against real ground truth (pytest), not against either reviewer's own
verdict.
"""

from peer_loop.eval import evaluate_task, format_eval_report, run_full_eval
from peer_loop.task_suite.tasks import TASKS, get_task


def test_task_with_flawed_first_attempt_recovers_with_reviewer_but_not_baseline():
    result = evaluate_task(get_task("word_count"))
    assert result.with_reviewer_ground_truth_success is True
    assert result.with_reviewer_iterations == 2
    assert result.baseline_ground_truth_success is False
    assert result.baseline_iterations == 1


def test_task_correct_on_first_try_succeeds_both_ways():
    result = evaluate_task(get_task("fibonacci"))
    assert result.with_reviewer_ground_truth_success is True
    assert result.baseline_ground_truth_success is True
    assert result.with_reviewer_iterations == 1
    assert result.baseline_iterations == 1


def test_full_eval_covers_every_task():
    results = run_full_eval()
    assert {r.task_id for r in results} == {t.id for t in TASKS}


def test_with_reviewer_success_rate_strictly_beats_baseline():
    results = run_full_eval()
    with_rate = sum(r.with_reviewer_ground_truth_success for r in results) / len(results)
    baseline_rate = sum(r.baseline_ground_truth_success for r in results) / len(results)
    assert with_rate == 1.0  # every scripted task suite entry is eventually solved
    assert baseline_rate < with_rate  # the whole point of the comparison


def test_format_eval_report_includes_both_rates_and_every_task():
    results = run_full_eval()
    report = format_eval_report(results)
    assert "with reviewer" in report
    assert "baseline" in report
    for task in TASKS:
        assert task.id in report
