# tests/test_llm.py
import os
from unittest.mock import patch, MagicMock

STUB_PROVIDER = {
    "type": "openai",
    "model": "openrouter/auto",
    "base_url": "https://openrouter.ai/api/v1",
    "api_key": "${OPENROUTER_API_KEY}",
}

STUB_CONFIG = {
    "llm": {
        "active_provider": "openrouter",
        "temperature": 0.7,
        "providers": {"openrouter": STUB_PROVIDER},
    }
}


def _mock_openai_response(content="response"):
    resp = MagicMock()
    resp.choices = [MagicMock(message=MagicMock(content=content))]
    return resp


def test_chat_returns_string():
    """chat() should return a string response."""
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _mock_openai_response("Good morning, sir.")
    with patch("jarvis.llm._load_config", return_value=STUB_CONFIG), \
         patch("openai.OpenAI", return_value=mock_client), \
         patch.dict(os.environ, {"OPENROUTER_API_KEY": "test"}):
        from jarvis.llm import chat
        result = chat([{"role": "user", "content": "Hello"}])
        assert isinstance(result, str)
        assert "Good morning" in result


def test_resolve_api_key_expands_env():
    from jarvis.llm import _resolve_api_key
    with patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-or-test"}):
        assert _resolve_api_key(STUB_PROVIDER) == "sk-or-test"


def test_resolve_api_key_passes_value():
    from jarvis.llm import _resolve_api_key
    assert _resolve_api_key({"api_key": "real-key-123"}) == "real-key-123"


def test_chat_returns_error_on_llm_failure():
    with patch("jarvis.llm._load_config", return_value=STUB_CONFIG), \
         patch("openai.OpenAI", side_effect=Exception("connection refused")):
        from jarvis.llm import chat
        result = chat([{"role": "user", "content": "hi"}])
        assert "LLM error" in result
