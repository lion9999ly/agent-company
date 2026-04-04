"""品牌层 — 统一系统回复的语气和风格
@description: 统一系统回复的品牌形象和语气
@dependencies: 无
@last_modified: 2026-04-04
"""
import yaml
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
BRAND_PATH = PROJECT_ROOT / ".ai-state" / "brand.yaml"


def get_brand() -> dict:
    """获取品牌配置"""
    if BRAND_PATH.exists():
        return yaml.safe_load(BRAND_PATH.read_text(encoding='utf-8'))
    return {"name": "助手", "tone": "专业", "greeting": "你好！", "self_reference": "我"}


def apply_brand(text: str) -> str:
    """对回复文本应用品牌层（暂时只做轻量处理）

    Args:
        text: 原始回复文本

    Returns:
        应用品牌后的文本
    """
    brand = get_brand()

    # 检查风格规则
    style_rules = brand.get("style_rules", [])

    # 目前只做简单检查，不做实际修改
    # 未来可以做更多：统一语气、添加签名等

    return text


def get_greeting() -> str:
    """获取系统问候语"""
    brand = get_brand()
    return brand.get("greeting", "你好！")


def get_self_reference() -> str:
    """获取自称方式"""
    brand = get_brand()
    return brand.get("self_reference", "我")


def format_response_with_brand(content: str, include_greeting: bool = False) -> str:
    """格式化回复内容"""
    brand = get_brand()
    name = brand.get("name", "助手")

    if include_greeting:
        greeting = brand.get("greeting", "")
        content = f"{greeting}\n\n{content}"

    # 添加签名（如果有）
    sign_off = brand.get("sign_off", "")
    if sign_off:
        content = f"{content}\n\n{sign_off}"

    return content


if __name__ == "__main__":
    brand = get_brand()
    print(f"系统名称: {brand.get('name')}")
    print(f"问候语: {brand.get('greeting')}")