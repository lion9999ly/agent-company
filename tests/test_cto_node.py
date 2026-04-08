"""
@description: CTO节点独立测试脚本
@dependencies: src.graph.router
@last_modified: 2026-03-18
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.graph.router import cto_coder_node


def test_cto_node():
    """测试CTO节点的真实LLM调用"""
    print("=" * 60)
    print("[CTO Node Test]")
    print("=" * 60)

    # 构造测试状态
    test_state = {
        "current_task_id": "test_task_001",
        "sub_tasks": {
            "test_task_001": {
                "subtask_id": "test_task_001",
                "task_description": "为智能骑行头盔设计实时导航HUD的显示方案",
                "target_role": "cto",
                "requirements": [
                    "支持实时导航箭头显示",
                    "支持速度、距离等关键信息",
                    "阳光下可视",
                    "低功耗设计"
                ]
            }
        },
        "metadata": {
            "project_name": "智能骑行头盔",
            "global_status": "executing"
        }
    }

    print(f"\n[输入] 任务: {test_state['sub_tasks']['test_task_001']['task_description']}")
    print("\n[调用] cto_coder_node...")
    print("-" * 60)

    # 调用CTO节点
    result = cto_coder_node(test_state)

    print("-" * 60)
    print("\n[输出结果]")

    # 提取并打印protocol_code
    cto_output = result.get("execution", {}).get("cto_output", {})
    protocol_code = cto_output.get("protocol_code", "[无输出]")

    print(f"\n{protocol_code}")
    print("\n" + "=" * 60)
    print("[测试完成]")


if __name__ == "__main__":
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")
    test_cto_node()