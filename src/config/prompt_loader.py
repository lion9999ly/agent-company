"""
@description: Agent prompt 集中加载器，从 agent_prompts.yaml 读取并组装 prompt
@dependencies: yaml, pathlib
@last_modified: 2026-03-21
"""
import yaml
from pathlib import Path
from typing import Optional

_CONFIG_PATH = Path(__file__).parent / "agent_prompts.yaml"
_cache: Optional[dict] = None


def _load_config() -> dict:
    global _cache
    if _cache is None:
        _cache = yaml.safe_load(_CONFIG_PATH.read_text(encoding="utf-8"))
    return _cache


def get_agent_prompt(role: str, extra_context: str = "") -> str:
    """加载 Agent prompt = shared_base + role_prompt + extra_context"""
    config = _load_config()
    base = config.get("shared_base", "")
    role_config = config.get("roles", {}).get(role, {})
    role_prompt = role_config.get("prompt", "")
    parts = [base.strip(), role_prompt.strip()]
    if extra_context:
        parts.append(extra_context.strip())
    return "\n\n".join(p for p in parts if p)


def reload_prompts():
    """强制重新加载（用于 prompt 自进化后刷新）"""
    global _cache
    _cache = None