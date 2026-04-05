"""降级链验证器 — 确保所有模型最终落到可用模型
@description: 遍历 FALLBACK_MAP，验证每条链的终点是可用模型
@dependencies: tonight_deep_research.FALLBACK_MAP
@last_modified: 2026-04-05
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# 可用模型列表（终点）
AVAILABLE_TERMINALS = [
    "gpt_5_4",
    "gpt_4o_norway",
    "o3_deep_research",
    "doubao_seed_pro",
    "doubao_seed_lite",
    "deepseek_v3_volcengine",
    "deepseek_r1_volcengine",
    "glm_4_7",
    "doubao_vision_pro",
    "seedream_3_0",
]

# 从 tonight_deep_research 导入
try:
    from scripts.tonight_deep_research import FALLBACK_MAP
except ImportError:
    # 直接定义备用
    FALLBACK_MAP = {
        "gpt_5_4": "gpt_4o_norway",
        "gpt_4o_norway": "doubao_seed_pro",
        "o3_deep_research": "gpt_5_4",
        "doubao_seed_pro": "doubao_seed_lite",
        "doubao_seed_lite": "gpt_4o_norway",
        "deepseek_v3_volcengine": "deepseek_r1_volcengine",
        "deepseek_r1_volcengine": "gpt_5_4",
        "glm_4_7": "doubao_seed_pro",
        "doubao_vision_pro": "gpt_5_4",
        "gpt_5_3": "gpt_4o_norway",
        "o3": "deepseek_r1_volcengine",
        "o3_mini": "doubao_seed_lite",
        "grok_4": "gpt_4o_norway",
        "gemini_deep_research": "o3_deep_research",
        "gemini_3_1_pro": "gpt_5_4",
        "gemini_3_pro": "gpt_5_4",
        "gemini_2_5_pro": "gpt_5_4",
        "gemini_2_5_flash": "gpt_4o_norway",
        "qwen_3_32b": "doubao_seed_pro",
        "llama_4_maverick": "gpt_4o_norway",
        "deepseek_v3_2": "deepseek_v3_volcengine",
        "deepseek_r1": "deepseek_r1_volcengine",
    }


def trace_fallback_chain(model: str, max_depth: int = 10) -> tuple:
    """追踪降级链，返回 (终点模型, 链路, 是否有效)

    Returns:
        (terminal, chain, is_valid)
        terminal: 最终落到的模型
        chain: 降级路径 ["model1", "model2", ...]
        is_valid: 终点是否在可用列表中
    """
    chain = [model]
    current = model

    for _ in range(max_depth):
        if current in AVAILABLE_TERMINALS:
            return current, chain, True

        fallback = FALLBACK_MAP.get(current)
        if not fallback:
            # 没有降级路径，检查是否在可用列表
            return current, chain, current in AVAILABLE_TERMINALS

        chain.append(fallback)
        current = fallback

        # 防止循环
        if len(chain) > 5 and chain[-1] == chain[-3]:
            return current, chain, False

    return current, chain, False


def verify_all_chains():
    """验证所有降级链"""
    print("=== 降级链验证 ===\n")

    all_models = list(FALLBACK_MAP.keys()) + AVAILABLE_TERMINALS
    all_models = sorted(set(all_models))

    results = {
        "valid": [],
        "invalid": [],
        "terminal": [],
    }

    for model in all_models:
        terminal, chain, is_valid = trace_fallback_chain(model)

        if model in AVAILABLE_TERMINALS and len(chain) == 1:
            results["terminal"].append(model)
            print(f"  [OK] {model} -- 终点模型")
        elif is_valid:
            results["valid"].append(model)
            print(f"  [OK] {model} -> {terminal} ({len(chain)-1} 步)")
        else:
            results["invalid"].append(model)
            print(f"  [FAIL] {model} -> {terminal} [无效终点]")
            print(f"     链路: {' -> '.join(chain)}")

    print(f"\n=== 统计 ===")
    print(f"  终点模型: {len(results['terminal'])}")
    print(f"  有效链路: {len(results['valid'])}")
    print(f"  无效链路: {len(results['invalid'])}")

    if results["invalid"]:
        print(f"\n[WARN] 发现无效链路!")
        return False

    print(f"\n[OK] 所有降级链验证通过!")
    return True


if __name__ == "__main__":
    success = verify_all_chains()
    sys.exit(0 if success else 1)