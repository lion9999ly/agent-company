"""产品愿景生成 — 基于数据的创造性产品描述
@description: 用 GPT-5.4 生成有画面感的产品使用场景描述
@dependencies: model_gateway
@last_modified: 2026-04-04
"""
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent


def generate_vision(gateway, kb_context: str = "") -> str:
    """生成产品愿景描述

    Args:
        gateway: 模型网关实例
        kb_context: 知识库上下文（可选）

    Returns:
        产品愿景场景描述
    """
    prompt = (
        f"你是一个极具想象力的产品设计师。\n\n"
        f"基于以下知识，描绘智能骑行头盔的使用场景。\n"
        f"不是列功能，而是讲故事——让读者'看到'用户在用这个产品。\n\n"
        f"{kb_context[:3000]}\n\n"
        f"场景 1: 用户第一次开箱并戴上头盔的前 60 秒\n"
        f"场景 2: 周末三个骑友组队穿越山路\n"
        f"场景 3: 暴雨中的长途骑行\n"
        f"场景 4: 深夜独骑回家\n\n"
        f"每个场景 150-200 字，有画面感，有情感，有细节。"
    )
    result = gateway.call("gpt_5_4", prompt,
                          "你是产品愿景设计师，用文字创造画面感。不要分析，只要想象。",
                          "creative_writing")
    return result.get("response", "") if result.get("success") else "生成失败"


def save_vision(vision_text: str) -> str:
    """保存愿景到文件"""
    import time
    output_path = PROJECT_ROOT / ".ai-state" / "exports" / "product_vision.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    content = f"""# 产品愿景场景

> 生成时间: {time.strftime('%Y-%m-%d %H:%M')}

{vision_text}
"""
    output_path.write_text(content, encoding='utf-8')
    return str(output_path)


def get_kb_context_for_vision() -> str:
    """获取用于愿景生成的 KB 上下文"""
    try:
        from src.tools.knowledge_base import search_knowledge
        # 搜索产品相关内容
        queries = ["产品功能", "HUD 显示", "骑行体验", "智能头盔"]
        context_parts = []
        for q in queries:
            results = search_knowledge(q, limit=3)
            for r in results:
                context_parts.append(r.get("content", "")[:500])
        return "\n".join(context_parts)
    except ImportError:
        return ""


if __name__ == "__main__":
    print("产品愿景生成器已就绪")