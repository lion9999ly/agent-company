"""
模型网关 — 配置与数据类型
从 model_gateway.py 提取的公共定义
"""
import os
import yaml
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from enum import Enum


# ============================================================
# Timeout 配置：按任务类型分级
# ============================================================
TIMEOUT_BY_TASK = {
    "intent_classify": 30, "auto_research_quality": 30,
    "failure_analysis": 30, "success_analysis": 30,
    "to_csv": 30, "translate": 30, "smart_chat": 30,
    "kb_answer": 60, "proactive_advice": 60, "tavily_fallback": 60,
    "quick_qa": 60, "quick_summary": 60, "search_augmented": 60, "kg_retry": 60,
    "planning": 120, "review": 120, "completeness_check": 120,
    "gap_fill": 120, "auto_discover_domains": 120, "research_summary": 120,
    "general": 120, "health_check": 30, "night_watch_diagnose": 60,
    "image_generation": 120,
    "synthesis": 180, "kg_refine": 180, "kb_deepen": 180, "kb_enrich": 180,
    "rebuild_decision_tree": 180, "doc_deepen": 180, "deep_research": 180,
    "competitive_research": 180, "market_analysis": 180,
    "code_generation": 180, "architecture_design": 180, "structured_doc": 180,
}


class ModelProvider(Enum):
    GOOGLE = "google"
    OPENAI = "openai"
    AZURE_OPENAI = "azure_openai"
    ALIBABA = "alibaba"
    ANTHROPIC = "anthropic"
    ZHIPU = "zhipu"
    DEEPSEEK = "deepseek"
    VOLCENGINE = "volcengine"


class TaskType(Enum):
    CODE_REVIEW = "code_review"
    CODE_GENERATION = "code_generation"
    CODE_DEBUG = "code_debug"
    ARCHITECTURE_DESIGN = "architecture_design"
    SYSTEM_DESIGN = "system_design"
    QUICK_QA = "quick_qa"
    QUICK_SUMMARY = "quick_summary"
    SEARCH_AUGMENTED = "search_augmented"
    DATA_ANALYSIS = "data_analysis"
    COMPETITIVE_RESEARCH = "competitive_research"
    MARKET_ANALYSIS = "market_analysis"
    CREATIVE_WRITING = "creative_writing"
    CONTENT_GENERATION = "content_generation"
    MULTILINGUAL = "multilingual"
    CHINESE_TASK = "chinese_task"
    HARDWARE_REVIEW = "hardware_review"
    COMPLEX_REASONING = "complex_reasoning"
    MATH_PROBLEM = "math_problem"
    LOGIC_ANALYSIS = "logic_analysis"
    GENERAL = "general"


@dataclass
class ModelConfig:
    provider: str
    model: str
    api_key: str
    purpose: str
    max_tokens: int
    temperature: float
    enabled: bool = True
    endpoint: Optional[str] = None
    deployment: Optional[str] = None
    api_version: Optional[str] = None
    capabilities: List[str] = field(default_factory=list)
    cost_tier: str = "$$"
    performance: int = 3


# Token tracker (optional dependency)
try:
    from src.utils.token_usage_tracker import get_tracker
    HAS_TRACKER = True
except ImportError:
    HAS_TRACKER = False


def record_usage(model: str, provider: str, prompt_tokens: int, completion_tokens: int,
                 task_type: str, success: bool, latency_ms: int):
    """统一的 token 使用记录"""
    if HAS_TRACKER:
        get_tracker().record(
            model=model, provider=provider,
            prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
            task_type=task_type, success=success, latency_ms=latency_ms
        )
