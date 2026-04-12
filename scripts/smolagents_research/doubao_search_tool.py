"""
@description: 豆包搜索工具 - smolagents Tool 实现
@dependencies: smolagents, openai, os
@last_modified: 2026-04-12
"""

import os
from smolagents import Tool


class DoubaoSearchTool(Tool):
    """豆包搜索引擎工具

    使用火山引擎 ARK API 进行搜索，适合中文查询。
    使用 OpenAI SDK 调用，更稳定且支持更长 timeout。
    """

    name = "doubao_search"
    description = "使用豆包搜索引擎搜索信息，适合中文查询。返回搜索结果的详细摘要。"

    inputs = {
        "query": {
            "type": "string",
            "description": "搜索查询关键词"
        },
        "num_results": {
            "type": "integer",
            "description": "返回结果数量（用于提示词参考），默认5",
            "nullable": True
        }
    }

    output_type = "string"

    def __init__(self):
        super().__init__()
        self.api_key = None
        self.api_base = "https://ark.cn-beijing.volces.com/api/v3"
        self.model = "doubao-seed-2-0-pro-260215"

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
            num_results: 返回结果数量（用于提示词参考）

        Returns:
            搜索结果详细摘要（格式化的字符串）
        """
        if not self.is_initialized:
            self.setup()

        # 使用 OpenAI SDK 调用（与旧管道一致，更稳定）
        try:
            from openai import OpenAI
            client = OpenAI(api_key=self.api_key, base_url=self.api_base)

            # prompt 设计：要求详细内容，与旧管道一致
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "你是一个搜索助手。请搜索并返回相关信息。返回内容要详细、结构化，包含关键数据、技术参数、市场信息、供应商信息等。"
                    },
                    {
                        "role": "user",
                        "content": f"请详细搜索关于「{query}」的相关信息。要求：\n"
                                   f"1. 提供详细的技术规格、产品参数、市场数据等具体信息\n"
                                   f"2. 列出相关的公司、品牌、供应商\n"
                                   f"3. 包含行业趋势、竞品对比等分析内容\n"
                                   f"4. 内容要丰富，至少1000字以上\n"
                                   f"5. 使用结构化格式（标题、列表等）输出"
                    }
                ],
                max_tokens=4096,
                temperature=0.1,
                timeout=180,  # 增加到 180 秒，足够生成长内容
            )

            content = response.choices[0].message.content
            return content

        except Exception as e:
            return f"搜索出错: {str(e)}"


# 导出
__all__ = ["DoubaoSearchTool"]