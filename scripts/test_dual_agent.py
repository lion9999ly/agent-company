"""
@description: 端到端双Agent测试脚本 - CTO + CMO 并行执行 + StateMerge
@dependencies: src.graph.router
@last_modified: 2026-03-18
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.graph.router import cto_coder_node, cmo_strategist, state_merge


def test_dual_agent():
    """端到端测试：CTO + CMO 双Agent并行执行，然后汇聚"""
    print("=" * 70)
    print("[Dual Agent E2E Test] CTO + CMO + StateMerge")
    print("=" * 70)

    # 初始状态（包含两个子任务）
    initial_state = {
        "current_task_id": "dual_task_001",
        "sub_tasks": {
            "cto_task": {
                "subtask_id": "cto_task",
                "task_description": "为智能骑行头盔设计核心传感器融合方案",
                "target_role": "cto",
                "requirements": [
                    "多传感器数据融合",
                    "实时性要求",
                    "低功耗设计"
                ]
            },
            "cmo_task": {
                "subtask_id": "cmo_task",
                "task_description": "为智能骑行头盔制定差异化定价策略",
                "target_role": "cmo",
                "requirements": [
                    "目标用户分群",
                    "竞品价格带分析",
                    "价值定价逻辑"
                ]
            }
        },
        "metadata": {
            "project_name": "智能骑行头盔",
            "global_status": "executing"
        }
    }

    print("\n" + "-" * 70)
    print("[Step 1] 调用 CTO 节点...")
    print("-" * 70)
    cto_state = cto_coder_node(initial_state)
    cto_output = cto_state.get("execution", {}).get("cto_output", {})
    protocol_code = cto_output.get("protocol_code", "[无输出]")
    print(f"\n[CTO 输出预览] {protocol_code[:200]}...")

    print("\n" + "-" * 70)
    print("[Step 2] 调用 CMO 节点...")
    print("-" * 70)
    # 将 CTO 输出合并到状态中，供 CMO 使用
    state_after_cto = {**initial_state, "execution": cto_state.get("execution", {})}
    cmo_state = cmo_strategist(state_after_cto)
    cmo_output = cmo_state.get("execution", {}).get("cmo_output", {})
    market_strategy = cmo_output.get("market_strategy", "[无输出]")
    print(f"\n[CMO 输出预览] {market_strategy[:200]}...")

    print("\n" + "-" * 70)
    print("[Step 3] 调用 StateMerge 节点...")
    print("-" * 70)
    # 合并两个 Agent 的输出
    merged_execution = {
        **cto_state.get("execution", {}),
        **cmo_state.get("execution", {})
    }
    state_before_merge = {**initial_state, "execution": merged_execution}
    final_state = state_merge(state_before_merge)

    print("\n" + "=" * 70)
    print("[最终汇聚结果]")
    print("=" * 70)
    merge_summary = final_state.get("execution", {}).get("merge_summary", "[无汇聚结果]")
    print(merge_summary)

    print("\n" + "=" * 70)
    print("[测试完成]")
    print("=" * 70)


if __name__ == "__main__":
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")
    test_dual_agent()