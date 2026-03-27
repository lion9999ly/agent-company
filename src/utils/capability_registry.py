"""
@description: Agent 能力注册表 - 机器人知道自己能干什么
@dependencies: None
@last_modified: 2026-03-25
"""

# 机器人的所有能力，用于意图识别和自我介绍
CAPABILITIES = {
    "image_generation": {
        "name": "AI 图像生成",
        "description": "根据文字描述生成概念渲染图、产品效果图",
        "trigger_keywords": ["出图", "生成图", "画", "渲染", "效果图", "概念图", "imagen"],
        "usage": "发送图片描述文字，我会生成图片",
        "tool": "image_generation",
        "needs_input": "图片描述文字（prompt）",
    },
    "image_understanding": {
        "name": "图片理解",
        "description": "识别和分析图片内容，包括产品图、技术图纸、竞品照片",
        "trigger_keywords": ["识别", "看图", "分析图片", "这是什么"],
        "usage": "直接发图片给我",
        "tool": "gemini_vision",
        "needs_input": "图片",
    },
    "knowledge_search": {
        "name": "知识库查询",
        "description": "搜索项目知识库，当前有 2400+ 条技术档案、竞品分析、标准法规",
        "trigger_keywords": ["知识库", "查一下", "找一下", "有没有关于"],
        "usage": "直接问技术问题，我会从知识库找答案",
        "tool": "knowledge_search",
        "needs_input": "查询问题",
    },
    "deep_research": {
        "name": "深度研究",
        "description": "多 Agent 协作的深度研究，CTO+CMO+CDO 三个视角分析",
        "trigger_keywords": ["研究", "深入分析", "研发任务", "方案评估"],
        "usage": "发送研究问题，如'研究 AR1 vs AR2 在头盔场景的对比'",
        "tool": "langgraph",
        "needs_input": "研究问题",
    },
    "deep_dive": {
        "name": "知识图谱深挖",
        "description": "对某个技术领域进行系统性深挖，发现完整产品家族",
        "trigger_keywords": ["深挖", "知识图谱", "展开", "系统性"],
        "usage": "发送'深挖'自动选择薄弱方向，或'深挖 电池BMS方案'指定方向",
        "tool": "kg_expand",
        "needs_input": "可选的方向指定",
    },
    "document_import": {
        "name": "文档导入",
        "description": "导入 PPT/PDF/Word/Excel 到知识库，支持图片理解",
        "trigger_keywords": ["导入", "学习这个", "导入文档"],
        "usage": "发送文件或长文，自动导入知识库",
        "tool": "doc_import",
        "needs_input": "文档文件或长文本",
    },
    "daily_report": {
        "name": "日报与审计",
        "description": "查看知识库状态、学习进度、Token 用量、质量审计",
        "trigger_keywords": ["日报", "审计", "token", "用量", "知识库"],
        "usage": "发送'日报'、'审计'、'知识库'等指令",
        "tool": "report",
        "needs_input": "无",
    },
}


def get_capabilities_summary() -> str:
    """生成能力摘要，用于注入 LLM prompt"""
    lines = ["## 我的能力清单\n"]
    for key, cap in CAPABILITIES.items():
        lines.append(f"- **{cap['name']}**: {cap['description']}")
        lines.append(f"  用法: {cap['usage']}")
    return "\n".join(lines)


def get_capabilities_for_intent() -> str:
    """生成用于意图识别的能力描述（更精简）"""
    items = []
    for key, cap in CAPABILITIES.items():
        items.append(f"{key}: {cap['name']} - {cap['description'][:50]}")
    return "\n".join(items)