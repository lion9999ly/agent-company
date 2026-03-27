"""
@description: Agent 工具注册表 - 统一管理外部工具调用，支持扩展
@dependencies: src.utils.model_gateway
@last_modified: 2026-03-19
"""
from typing import Dict, Any, Callable, Optional
from src.utils.model_gateway import get_model_gateway


class ToolRegistry:
    """轻量级工具注册表，Agent 通过统一接口调用外部工具"""

    def __init__(self):
        self._tools: Dict[str, Dict[str, Any]] = {}
        self._register_defaults()

    def _register_defaults(self):
        """注册默认工具"""
        self.register("deep_research", self._tool_deep_research,
                      "深度搜索：竞品调研、市场数据、技术趋势")

    def register(self, name: str, func: Callable, description: str):
        self._tools[name] = {"func": func, "description": description}

    def list_tools(self) -> list:
        return [{"name": k, "description": v["description"]} for k, v in self._tools.items()]

    def call(self, tool_name: str, query: str) -> Dict[str, Any]:
        tool = self._tools.get(tool_name)
        if not tool:
            return {"success": False, "error": f"Tool '{tool_name}' not found"}
        try:
            return tool["func"](query)
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _tool_deep_research(self, query: str) -> Dict[str, Any]:
        """使用 Gemini Deep Research 做深度搜索"""
        gateway = get_model_gateway()
        system_prompt = "你是一个研究助手。请对以下问题进行深入调研，提供数据和事实支撑。"
        # 优先 Gemini deep research，降级到 gemini_2_5_flash
        result = gateway.call_gemini("gemini_deep_research", query, system_prompt, "research")
        if result.get("success"):
            return {"success": True, "tool": "gemini_deep_research", "data": result["response"]}
        result = gateway.call_gemini("gemini_2_5_flash", query, system_prompt, "research")
        if result.get("success"):
            return {"success": True, "tool": "gemini_2_5_flash(fallback)", "data": result["response"]}
        return {"success": False, "error": "All research models failed"}


_registry: Optional[ToolRegistry] = None


def get_tool_registry() -> ToolRegistry:
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry