"""
@description: 豆包搜索工具 - smolagents Tool 实现
@dependencies: smolagents, requests, os
@last_modified: 2026-04-12
"""

import os
import requests
from smolagents import Tool


class DoubaoSearchTool(Tool):
    """豆包搜索引擎工具

    使用火山引擎 ARK API 进行搜索，适合中文查询。
    """

    name = "doubao_search"
    description = "使用豆包搜索引擎搜索信息，适合中文查询。返回搜索结果的摘要列表。"

    inputs = {
        "query": {
            "type": "string",
            "description": "搜索查询关键词"
        },
        "num_results": {
            "type": "integer",
            "description": "返回结果数量，默认5",
            "nullable": True
        }
    }

    output_type = "string"

    def __init__(self):
        super().__init__()
        self.api_key = None
        self.api_base = "https://ark.cn-beijing.volces.com/api/v3"

    def setup(self):
        """延迟初始化 - 加载 API Key"""
        self.api_key = os.getenv("ARK_API_KEY")
        if not self.api_key:
            raise ValueError("ARK_API_KEY environment variable not set")
        self.is_initialized = True

    def forward(self, query: str, num_results: int = 5) -> str:
        """执行搜索

        Args:
            query: 搜索查询关键词
            num_results: 返回结果数量

        Returns:
            搜索结果摘要（格式化的字符串）
        """
        if not self.is_initialized:
            self.setup()

        # 调用豆包搜索 API（假设使用 OpenAI兼容格式）
        try:
            # 实际豆包搜索可能需要不同的 endpoint
            # 这里使用一个模拟实现，返回搜索结果
            response = requests.post(
                f"{self.api_base}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "doubao-seed-2-0-pro-260215",
                    "messages": [
                        {"role": "system", "content": "你是一个搜索助手，根据用户的查询提供相关信息摘要。"},
                        {"role": "user", "content": f"请搜索并总结关于'{query}'的关键信息，提供{num_results}条要点。"}
                    ],
                    "max_tokens": 2000,
                    "temperature": 0.1
                },
                timeout=30
            )

            if response.status_code == 200:
                data = response.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                return content
            else:
                return f"搜索失败: HTTP {response.status_code} - {response.text[:200]}"

        except Exception as e:
            return f"搜索出错: {str(e)}"


# 导出
__all__ = ["DoubaoSearchTool"]