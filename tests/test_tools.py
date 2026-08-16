import pytest

from peer_loop import tools
from peer_loop.exceptions import ToolTimeoutError


def test_write_then_read_file(tmp_path):
    tools.write_file(tmp_path, "solution.py", "x = 1\n")
    assert tools.read_file(tmp_path, "solution.py") == "x = 1\n"


def test_write_file_creates_parent_directories(tmp_path):
    tools.write_file(tmp_path, "nested/dir/solution.py", "x = 1\n")
    assert (tmp_path / "nested" / "dir" / "solution.py").read_text() == "x = 1\n"


def test_read_missing_file_raises_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        tools.read_file(tmp_path, "does_not_exist.py")


def test_list_files_lists_everything_recursively(tmp_path):
    tools.write_file(tmp_path, "a.py", "1")
    tools.write_file(tmp_path, "sub/b.py", "2")
    listing = tools.list_files(tmp_path)
    assert "a.py" in listing
    assert "sub/b.py" in listing.replace("\\", "/")


def test_path_cannot_escape_sandbox(tmp_path):
    with pytest.raises(ValueError, match="escapes the sandbox"):
        tools.read_file(tmp_path, "../../etc/passwd")


def test_run_tests_real_pass(tmp_path):
    (tmp_path / "solution.py").write_text("def add(a, b):\n    return a + b\n")
    (tmp_path / "test_solution.py").write_text(
        "from solution import add\n\ndef test_add():\n    assert add(1, 2) == 3\n"
    )
    passed, output = tools.run_tests(tmp_path, "test_solution.py")
    assert passed is True
    assert "1 passed" in output


def test_run_tests_real_fail(tmp_path):
    (tmp_path / "solution.py").write_text("def add(a, b):\n    return a - b\n")
    (tmp_path / "test_solution.py").write_text(
        "from solution import add\n\ndef test_add():\n    assert add(1, 2) == 3\n"
    )
    passed, output = tools.run_tests(tmp_path, "test_solution.py")
    assert passed is False
    assert "1 failed" in output


def test_run_tests_missing_test_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        tools.run_tests(tmp_path, "test_missing.py")


def test_run_tests_timeout_raises_typed_error_distinct_from_failure(tmp_path):
    (tmp_path / "solution.py").write_text("")
    (tmp_path / "test_solution.py").write_text(
        "import time\n\ndef test_slow():\n    time.sleep(5)\n    assert True\n"
    )
    with pytest.raises(ToolTimeoutError):
        tools.run_tests(tmp_path, "test_solution.py", timeout_seconds=0.5)
