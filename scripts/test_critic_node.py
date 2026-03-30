"""
@description: 测试 CPO Critic 节点的真实双模型评审功能
@dependencies: src.graph.router
@last_modified: 2026-03-18
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from src.graph.router import cpo_critic_node


def test_case_a_should_pass():
    """测试用例 A：合理的蓝牙模块设计，期望 PASS"""
    print("=" * 60)
    print("[测试用例 A] 合理方案 - 期望 PASS")
    print("=" * 60)

    state = {
        "metadata": {"task_id": "test_a", "global_status": "executing", "max_retry_threshold": 3},
        "task_contract": {"task_goal": "评估nRF5340芯片是否适合用于骑行头盔蓝牙通信模块"},
        "execution": {
            "cto_output": {
                "protocol_code": "经评估，nRF5340双核SoC适合本项目。理由：1)支持BLE 5.3，满足低功耗通信需求；2)双核架构可分离应用与射频；3)Nordic生态成熟，开发工具链完善；4)内置安全启动，支持OTA。建议下一步进行原型板设计验证。"
            },
            "cmo_output": {
                "market_strategy": "初步市场调研显示蓝牙骑行头盔市场年增长15%，主要竞品为Sena和Cardo。建议先完成技术验证后再制定详细定价和GTM策略，避免技术风险传导到市场承诺。"
            }
        },
        "control": {"current_node": "cpo_critic", "retry_counts": {}, "error_traceback": []}
    }

    result = cpo_critic_node(state)
    decision = result.get("execution", {}).get("critic_decision", "UNKNOWN")
    feedback = result.get("execution", {}).get("critic_feedback", "")

    print(f"[Decision] {decision}")
    print(f"[Feedback] {feedback[:300]}...")
    print(f"[期望] PASS | [实际] {decision} | {'✅ PASS' if decision == 'PASS' else '❌ FAIL'}")
    return decision == "PASS"


def test_case_b_should_reject():
    """测试用例 B：荒谬的纸板方案，期望 REJECT"""
    print("\n" + "=" * 60)
    print("[测试用例 B] 荒谬方案 - 期望 REJECT")
    print("=" * 60)

    state = {
        "metadata": {"task_id": "test_b", "global_status": "executing", "max_retry_threshold": 3},
        "task_contract": {"task_goal": "用纸板做头盔导航HUD"},
        "execution": {
            "cto_output": {
                "protocol_code": "用纸板折一个头盔形状，在前面贴一张手机屏幕保护膜当显示器。"
            },
            "cmo_output": {
                "market_strategy": "目标用户：所有人。价格：5元。渠道：路边摊。"
            }
        },
        "control": {"current_node": "cpo_critic", "retry_counts": {}, "error_traceback": []}
    }

    result = cpo_critic_node(state)
    decision = result.get("execution", {}).get("critic_decision", "UNKNOWN")
    feedback = result.get("execution", {}).get("critic_feedback", "")

    print(f"[Decision] {decision}")
    print(f"[Feedback] {feedback[:300]}...")
    print(f"[期望] REJECT | [实际] {decision} | {'✅ PASS' if decision == 'REJECT' else '❌ FAIL'}")
    return decision == "REJECT"


def main():
    print("\n" + "=" * 60)
    print("CPO Critic Node 双模型评审测试")
    print("=" * 60 + "\n")

    results = []

    # 用例 A
    try:
        results.append(("Case A", test_case_a_should_pass()))
    except Exception as e:
        print(f"[Case A ERROR] {e}")
        results.append(("Case A", False))

    # 用例 B
    try:
        results.append(("Case B", test_case_b_should_reject()))
    except Exception as e:
        print(f"[Case B ERROR] {e}")
        results.append(("Case B", False))

    # 汇总
    print("\n" + "=" * 60)
    print("测试汇总")
    print("=" * 60)
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{name}: {status}")

    all_passed = all(r[1] for r in results)
    print(f"\n总体结果: {'✅ 全部通过' if all_passed else '❌ 存在失败'}")
    return all_passed


if __name__ == "__main__":
    main()