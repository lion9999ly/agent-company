"""
@description: CMO节点独立测试脚本
@dependencies: src.graph.router
@last_modified: 2026-03-18
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.graph.router import cmo_strategist


def test_cmo_node():
    """测试CMO节点的真实LLM调用"""
    print("=" * 60)
    print("[CMO Node Test]")
    print("=" * 60)

    # 构造测试状态
    test_state = {
        "current_task_id": "test_task_002",
        "sub_tasks": {
            "test_task_002": {
                "subtask_id": "test_task_002",
                "task_description": "为智能骑行头盔制定进入中国骑行运动市场的GTM策略",
                "target_role": "cmo",
                "requirements": [
                    "目标用户分析",
                    "竞品定位",
                    "差异化卖点",
                    "GTM策略",
                    "风险评估"
                ]
            }
        },
        "metadata": {
            "project_name": "智能骑行头盔",
            "global_status": "executing"
        }
    }

    print(f"\n[输入] 任务: {test_state['sub_tasks']['test_task_002']['task_description']}")
    print("\n[调用] cmo_strategist...")
    print("-" * 60)

    # 调用CMO节点
    result = cmo_strategist(test_state)

    print("-" * 60)
    print("\n[输出结果]")

    # 提取并打印market_strategy
    cmo_output = result.get("execution", {}).get("cmo_output", {})
    market_strategy = cmo_output.get("market_strategy", "[无输出]")

    print(f"\n{market_strategy}")
    print("\n" + "=" * 60)
    print("[测试完成]")


if __name__ == "__main__":
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")
    test_cmo_node()