"""Lightweight LLM chat function for internal tasks (context summarization, etc.)."""
from pathlib import Path
import os
import re
import yaml

_CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"


def _load_config():
    with open(_CONFIG_PATH) as f:
        return yaml.safe_load(f)


def _resolve_api_key(provider: dict) -> str:
    """Resolve the provider api_key, expanding ${ENV_VAR} and honoring
    common environment variables (OPENROUTER_API_KEY, OPENAI_API_KEY, ...)."""
    raw = provider.get("api_key", "")
    if not raw:
        return ""
    m = re.fullmatch(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}", raw.strip())
    if m:
        return os.environ.get(m.group(1), "")
    # If it still looks like an env var name (all caps/no spaces), try it
    return os.environ.get(raw, raw) if raw.isupper() else raw


def chat(messages: list[dict]) -> str:
    """Send messages to the active LLM provider and return response text.

    Uses the same provider system as main.py — reads active_provider from config.
    Used for internal tasks like context summarization.
    """
    cfg = _load_config()
    llm_cfg = cfg.get("llm", {})
    temperature = llm_cfg.get("temperature", 0.7)
    active = llm_cfg.get("active_provider", "openrouter")
    providers = llm_cfg.get("providers", {})
    provider = providers.get(active, {})
    ptype = provider.get("type", "openai")

    if ptype == "openai":
        try:
            from openai import OpenAI
            client = OpenAI(
                base_url=provider["base_url"],
                api_key=_resolve_api_key(provider),
                timeout=15.0,
            )
            resp = client.chat.completions.create(
                model=provider["model"],
                messages=messages,
                temperature=temperature,
            )
            return resp.choices[0].message.content or ""
        except Exception as e:
            return f"[LLM error: {e}]"

    return "[LLM error: non-openai provider]"
