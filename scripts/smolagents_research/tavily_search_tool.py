"""
@description: Tavily 搜索工具 - smolagents Tool 实现
@dependencies: smolagents, requests, os
@last_modified: 2026-04-12
"""

import os
import json
import requests
from smolagents import Tool


class TavilySearchTool(Tool):
    """Tavily 搜索引擎工具

    使用 Tavily API 进行专业搜索，适合技术/产品规格查询。
    """

    name = "tavily_search"
    description = "使用 Tavily 搜索引擎进行专业搜索，适合技术规格、产品参数查询。返回结构化搜索结果。"

    inputs = {
        "query": {
            "type": "string",
            "description": "搜索查询"
        },
        "search_depth": {
            "type": "string",
            "description": "搜索深度：basic（快速）或 advanced（深度）",
            "nullable": True
        },
        "max_results": {
            "type": "integer",
            "description": "最大结果数，默认5",
            "nullable": True
        },
        "include_raw_content": {
            "type": "boolean",
            "description": "是否包含原始内容，默认False",
            "nullable": True
        }
    }

    output_type = "string"

    def __init__(self):
        super().__init__()
        self.api_key = None
        self.api_base = "https://api.tavily.com"

    def setup(self):
        """延迟初始化 - 加载 API Key"""
        self.api_key = os.getenv("TAVILY_API_KEY")
        if not self.api_key:
            # 尝试从其他环境变量获取
            self.api_key = os.getenv("TAVILY_API_KEY")
        if not self.api_key:
            raise ValueError("TAVILY_API_KEY environment variable not set")
        self.is_initialized = True

    def forward(
        self,
        query: str,
        search_depth: str = "basic",
        max_results: int = 5,
        include_raw_content: bool = False
    ) -> str:
        """执行搜索

        Args:
            query: 搜索查询
            search_depth: 搜索深度 (basic/advanced)
            max_results: 最大结果数
            include_raw_content: 是否包含原始内容

        Returns:
            格式化的搜索结果字符串
        """
        if not self.is_initialized:
            self.setup()

        try:
            response = requests.post(
                f"{self.api_base}/search",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "query": query,
                    "search_depth": search_depth,
                    "max_results": max_results,
                    "include_raw_content": include_raw_content,
                    "include_answer": True,
                    "include_images": False,
                },
                timeout=60
            )

            if response.status_code == 200:
                data = response.json()

                # 格式化输出
                result_text = []

                # 添加 AI 答案
                if data.get("answer"):
                    result_text.append(f"## AI Summary\n{data['answer']}\n")

                # 添加搜索结果
                results = data.get("results", [])
                if results:
                    result_text.append(f"## Search Results ({len(results)} items)\n")
                    for i, r in enumerate(results, 1):
                        title = r.get("title", "N/A")
                        url = r.get("url", "N/A")
                        content = r.get("content", "N/A")
                        score = r.get("score", 0)

                        result_text.append(f"{i}. **{title}** (Score: {score:.2f})")
                        result_text.append(f"   URL: {url}")
                        result_text.append(f"   Content: {content[:500]}...")
                        result_text.append("")

                return "\n".join(result_text)

            else:
                return f"搜索失败: HTTP {response.status_code} - {response.text[:200]}"

        except Exception as e:
            return f"搜索出错: {str(e)}"


# 导出
__all__ = ["TavilySearchTool"]