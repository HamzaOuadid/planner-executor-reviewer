import pytest

from peer_loop.llm.fake import FakeLLMClient


def test_pops_responses_in_order_per_role():
    llm = FakeLLMClient(script={"planner": ["p1", "p2"], "reviewer": ["r1"]})
    assert llm.complete(role="planner", system="s", user="u") == "p1"
    assert llm.complete(role="planner", system="s", user="u") == "p2"
    assert llm.complete(role="reviewer", system="s", user="u") == "r1"


def test_records_every_call():
    llm = FakeLLMClient(script={"planner": ["p1"]})
    llm.complete(role="planner", system="sys-prompt", user="user-prompt")
    assert len(llm.calls) == 1
    assert llm.calls[0].role == "planner"
    assert llm.calls[0].system == "sys-prompt"
    assert llm.calls[0].user == "user-prompt"


def test_calls_for_filters_by_role():
    llm = FakeLLMClient(script={"planner": ["p1", "p2"], "reviewer": ["r1"]})
    llm.complete(role="planner", system="s", user="u")
    llm.complete(role="reviewer", system="s", user="u")
    llm.complete(role="planner", system="s", user="u")
    assert len(llm.calls_for("planner")) == 2
    assert len(llm.calls_for("reviewer")) == 1


def test_default_fallback_used_when_queue_empty():
    llm = FakeLLMClient(script={"planner": ["p1"]}, default="fallback")
    assert llm.complete(role="planner", system="s", user="u") == "p1"
    assert llm.complete(role="planner", system="s", user="u") == "fallback"
    assert llm.complete(role="reviewer", system="s", user="u") == "fallback"


def test_raises_loudly_with_no_script_and_no_default():
    llm = FakeLLMClient()
    with pytest.raises(AssertionError, match="no scripted response"):
        llm.complete(role="planner", system="s", user="u")


def test_program_appends_to_existing_queue():
    llm = FakeLLMClient(script={"planner": ["p1"]})
    llm.program("planner", ["p2", "p3"])
    assert [llm.complete(role="planner", system="s", user="u") for _ in range(3)] == ["p1", "p2", "p3"]


def test_custom_key_fn():
    llm = FakeLLMClient(
        script={"planner:task-a": ["for-a"], "planner:task-b": ["for-b"]},
        key_fn=lambda role, system, user: f"{role}:{user}",
    )
    assert llm.complete(role="planner", system="s", user="task-a") == "for-a"
    assert llm.complete(role="planner", system="s", user="task-b") == "for-b"
