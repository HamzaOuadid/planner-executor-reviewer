"""Verifies the ground truth the whole system is graded against: every
task's starter code must genuinely fail pytest, and its reference fix
must genuinely pass. If this file doesn't pass, nothing downstream can be
trusted."""

import subprocess
import sys

import pytest

from peer_loop.task_suite.tasks import TASKS, get_task, materialize_sandbox


@pytest.mark.parametrize("task", TASKS, ids=[t.id for t in TASKS])
def test_starter_code_fails_its_own_tests(task, tmp_path):
    materialize_sandbox(task, tmp_path)
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", str(tmp_path / task.test_filename), "-q"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
    )
    assert proc.returncode != 0, f"starter code for {task.id} unexpectedly passed all tests"


@pytest.mark.parametrize("task", TASKS, ids=[t.id for t in TASKS])
def test_reference_fix_passes_its_own_tests(task, tmp_path):
    materialize_sandbox(task, tmp_path, use_fix=task.reference_fix)
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", str(tmp_path / task.test_filename), "-q"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"reference fix for {task.id} unexpectedly failed:\n{proc.stdout}"


def test_get_task_returns_known_task():
    task = get_task("fibonacci")
    assert task.id == "fibonacci"


def test_get_task_raises_clear_error_for_unknown_id():
    with pytest.raises(KeyError, match="unknown task id"):
        get_task("does-not-exist")


def test_task_suite_has_at_least_five_tasks():
    # spec M1: "Define 5-8 real multi-step tasks with known-correct outcomes"
    assert 5 <= len(TASKS) <= 8


def test_task_ids_are_unique():
    ids = [t.id for t in TASKS]
    assert len(ids) == len(set(ids))
