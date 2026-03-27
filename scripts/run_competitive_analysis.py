"""
@description: 竞品分析任务状态初始化脚本
@dependencies: src.schema.state, src.graph.router
@last_modified: 2026-03-16
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.schema.state import (
    AgentGlobalState, TaskMetadata, TaskContract, ContractMetadata,
    PrototypeEvaluation, GlobalStatus, TargetRole, SubTaskContract
)
from src.graph.router import app


def create_competitive_analysis_state() -> AgentGlobalState:
    """创建竞品分析任务的初始状态"""

    # 任务元数据
    metadata: TaskMetadata = {
        "task_id": "inmo_air3_competitive_analysis",
        "global_status": GlobalStatus.PENDING,
        "max_retry_threshold": 3
    }

    # 契约元数据
    contract_metadata: ContractMetadata = {
        "contract_version": "1.0",
        "generated_at": "2026-03-16T17:45:00",
        "operator_role_applied": "product_manager"
    }

    # 任务契约
    task_contract: TaskContract = {
        "task_goal": "执行影目Air3 AR眼镜完整竞品分析，涵盖30个维度",
        "_sys_enforced_hash": "pending_hash_verification"
    }

    # 原型评估
    prototype_evaluation: PrototypeEvaluation = {
        "has_hardware_ui": True,
        "has_new_interaction_logic": True,
        "is_existing_product_iteration": False,
        "decision_result": "NO_PROTOTYPE"  # 竞品分析不需要原型
    }

    # 子任务定义 - 分配给CTO和CMO
    sub_tasks: dict[str, SubTaskContract] = {
        # CTO: 技术规格分析
        "tech_specs": {
            "subtask_id": "tech_specs",
            "target_role": TargetRole.CTO,
            "task_description": "分析影目Air3技术规格：芯片、算力、显示模组、传感器、电池",
            "depends_on": [],
            "is_core_dependency": True,
            "dependency_timeout_sec": 300,
            "output_schema": {
                "chipset": "str",
                "display_specs": "dict",
                "sensors": "list",
                "battery": "dict"
            },
            "acceptance_criteria": {
                "completeness": {"threshold": "80%", "mandatory": True},
                "accuracy": {"threshold": "verified", "mandatory": False}
            },
            "tool_white_list": ["web_search", "doc_read"]
        },

        # CMO: 市场分析
        "market_analysis": {
            "subtask_id": "market_analysis",
            "target_role": TargetRole.CMO,
            "task_description": "分析影目Air3市场表现：售价、渠道、目标人群、用户反馈",
            "depends_on": [],
            "is_core_dependency": True,
            "dependency_timeout_sec": 300,
            "output_schema": {
                "pricing": "dict",
                "channels": "list",
                "target_audience": "dict",
                "user_feedback": "dict"
            },
            "acceptance_criteria": {
                "data_sources": {"min_count": 3, "mandatory": True},
                "coverage": {"dimensions": 10, "mandatory": True}
            },
            "tool_white_list": ["web_search", "social_media_analyze"]
        },

        # CTO: 供应链分析
        "supply_chain": {
            "subtask_id": "supply_chain",
            "target_role": TargetRole.CTO,
            "task_description": "分析影目Air3供应链：主要供应商、代工厂、成本结构",
            "depends_on": ["tech_specs"],
            "is_core_dependency": False,
            "dependency_timeout_sec": 200,
            "output_schema": {
                "suppliers": "list",
                "manufacturing": "dict",
                "cost_breakdown": "dict"
            },
            "acceptance_criteria": {
                "supplier_identified": {"count": 5, "mandatory": False}
            },
            "tool_white_list": ["web_search", "database_query"]
        }
    }

    # 组装完整状态
    state: AgentGlobalState = {
        "metadata": metadata,
        "contract_metadata": contract_metadata,
        "prototype_evaluation": prototype_evaluation,
        "task_contract": task_contract,
        "sub_tasks": sub_tasks,
        "execution": {
            "prototype_output": None,
            "cto_output": None,
            "cmo_output": None,
            "review_reports": []
        },
        "control": {
            "current_node": "hash_check",
            "retry_counts": {},
            "error_traceback": [],
            "human_approval_status": "pending",
            "resume_from_node": None,
            "node_execution_logs": []
        }
    }

    return state


def run_analysis():
    """执行竞品分析工作流"""
    print("=" * 60)
    print("[INMO Air3 Competitive Analysis]")
    print("Multi-Agent Virtual R&D Center")
    print("=" * 60)

    # 1. 创建初始状态
    state = create_competitive_analysis_state()
    print(f"\n[INIT] Task ID: {state['metadata']['task_id']}")
    print(f"[INIT] Task Goal: {state['task_contract']['task_goal']}")
    print(f"[INIT] Sub-tasks: {list(state['sub_tasks'].keys())}")

    # 2. 验证状态机
    print(f"\n[GRAPH] Nodes: {list(app.nodes.keys())[:5]}...")
    print(f"[GRAPH] Entry: hash_check")

    # 3. 执行状态机（需要配置API Key才能完整运行）
    print("\n[INFO] 状态机已就绪，完整执行需要配置模型API Key")
    print("[INFO] 当前报告已生成: .ai-state/competitive_analysis/inmo_air3_report.md")

    return state


if __name__ == "__main__":
    state = run_analysis()
    print("\n[DONE] 竞品分析任务初始化完成")