"""Subagent — delegate subtasks to the same OpenAI-compatible provider."""
from __future__ import annotations
import re
from pathlib import Path
import yaml

_CONFIG_PATH = Path(__file__).parent.parent.parent / "config.yaml"


def _load_config():
    with open(_CONFIG_PATH) as f:
        return yaml.safe_load(f)


def _active_provider():
    cfg = _load_config()
    llm_cfg = cfg.get("llm", {})
    active = llm_cfg.get("active_provider", "openrouter")
    providers = llm_cfg.get("providers", {})
    return providers.get(active, {}), llm_cfg


def delegate_task(task: str, context: str = "") -> str:
    """Send a subtask to the active cloud provider and return its response."""
    provider, llm_cfg = _active_provider()
    ptype = provider.get("type", "openai")
    if ptype != "openai":
        return "delegate_task only supports an OpenAI-compatible provider."

    from openai import OpenAI
    from jarvis.llm import _resolve_api_key
    client = OpenAI(
        base_url=provider.get("base_url", ""),
        api_key=_resolve_api_key(provider),
        timeout=30.0,
    )
    messages = []
    if context:
        messages.append({
            "role": "system",
            "content": f"You are a helper agent. Complete the task using this context:\n\n{context}",
        })
    messages.append({"role": "user", "content": task})

    try:
        resp = client.chat.completions.create(
            model=provider.get("model", "openrouter/auto"),
            messages=messages,
            temperature=llm_cfg.get("temperature", 0.7),
        )
        text = resp.choices[0].message.content or ""
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
        return text if text else "Subtask completed (no output)."
    except Exception as e:
        return f"Subagent failed: {e}"
