import pytest

from peer_loop.llm.real import RealLLMClient


def test_from_env_raises_clear_error_without_any_key(monkeypatch, tmp_path):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    # point at an empty .env so a real developer .env on the machine can't leak in
    empty_env = tmp_path / ".env"
    empty_env.write_text("", encoding="utf-8")
    with pytest.raises(RuntimeError, match="FakeLLMClient"):
        RealLLMClient.from_env(env_path=empty_env)


def test_from_env_prefers_anthropic_when_both_set(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-key")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    empty_env = tmp_path / ".env"
    empty_env.write_text("", encoding="utf-8")
    client = RealLLMClient.from_env(env_path=empty_env)
    assert client.provider == "anthropic"
    assert client.api_key == "test-anthropic-key"


def test_from_env_falls_back_to_openai(monkeypatch, tmp_path):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    empty_env = tmp_path / ".env"
    empty_env.write_text("", encoding="utf-8")
    client = RealLLMClient.from_env(env_path=empty_env)
    assert client.provider == "openai"
    assert client.model  # a default model name is set


def test_complete_raises_actionable_error_when_sdk_not_installed():
    client = RealLLMClient(provider="anthropic", api_key="fake-key", model="fake-model")
    # The anthropic package isn't a base dependency of this project, so this
    # should raise a clear, actionable RuntimeError rather than an ImportError
    # bubbling up raw -- unless it happens to be installed in this environment,
    # in which case we can't assert the ImportError path (skip cleanly instead).
    try:
        import anthropic  # noqa: F401

        pytest.skip("anthropic package is installed in this environment")
    except ImportError:
        pass
    with pytest.raises(RuntimeError, match="anthropic"):
        client.complete(role="planner", system="s", user="u")
