import os
import hashlib
import json
from pathlib import Path
from typing import Literal
from langgraph.graph import StateGraph, END
from langgraph.types import Send

# 导入刚刚定义的强类型状态字典
from src.schema.state import AgentGlobalState


# ==========================================
# 0. 物理安全防线配置
# ==========================================
class SecurityError(Exception):
    """自定义安全阻断异常"""
    pass


# 定义项目根目录与受保护的目录
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
ARCH_DIR = ROOT_DIR / ".ai-architecture"
CONFIG_DIR = ROOT_DIR / "src" / "config"
HASH_FILE = ROOT_DIR / ".ai-state" / "snapshot_hashes.json"
LOCK_FILE = ROOT_DIR / ".ai-state" / ".SYSTEM_HALTED.lock"


def compute_directory_hash() -> dict:
    """实时计算受保护文件的物理 SHA-256 哈希值"""
    current_hashes = {}
    if ARCH_DIR.exists():
        for md_file in ARCH_DIR.glob("*.md"):
            content = md_file.read_bytes()
            current_hashes[md_file.name] = hashlib.sha256(content).hexdigest()
    if CONFIG_DIR.exists():
        for yaml_file in CONFIG_DIR.glob("*.yaml"):
            content = yaml_file.read_bytes()
            current_hashes[yaml_file.name] = hashlib.sha256(content).hexdigest()
    return current_hashes


# ==========================================
# 1. 节点逻辑存根 (Nodes)
# ==========================================
def hash_check_node(state: AgentGlobalState) -> dict:
    """【节点级】全目录架构哈希校验。"""
    print("\n[SECURITY] 初始化系统，正在执行底座防篡改哈希核对...")

    if not HASH_FILE.exists():
        err_msg = "致命错误：找不到 snapshot_hashes.json 基准快照文件！系统拒绝启动。"
        print(f"\033[91m{err_msg}\033[0m")
        LOCK_FILE.write_text(f"HALTED_BY_HASH_CHECK_NODE: {err_msg}", encoding='utf-8')
        raise PermissionError(err_msg)

    try:
        baseline_hashes = json.loads(HASH_FILE.read_text(encoding='utf-8'))
    except json.JSONDecodeError:
        raise ValueError("快照哈希文件损坏，无法解析为 JSON。")

    runtime_hashes = compute_directory_hash()
    mismatched_files = []
    for filename, baseline_hash in baseline_hashes.items():
        if filename not in runtime_hashes:
            mismatched_files.append(f"{filename} (文件丢失)")
        elif runtime_hashes[filename] != baseline_hash:
            mismatched_files.append(f"{filename} (哈希不匹配/遭篡改)")

    if mismatched_files:
        err_msg = f"致命安全阻断：检测到以下底层架构文件被非法篡改或未同步哈希：\n" + "\n".join(mismatched_files)
        print(f"\033[91m{err_msg}\033[0m")
        LOCK_FILE.write_text(f"HALTED_BY_HASH_CHECK_NODE: {err_msg}", encoding='utf-8')
        raise SecurityError(err_msg)

    print("\033[92m[SECURITY PASS] 架构哈希校验一致，信任根稳固，允许放行。\033[0m")
    return {"metadata": {"global_status": "planning"}}


# --- 新增：文档代码同构校验节点 ---
def doc_code_sync_check_node(state: AgentGlobalState) -> dict:
    """
    文档与代码同构物理校验节点。
    在启动大模型规划前，确保知识库没有腐化。
    """
    print("\n[SYNC CHECK] 正在执行全量文档-代码同构校验...")

    src_dir = ROOT_DIR / "src"
    desync_issues = []

    # 遍历 src 目录下的核心 Python 文件
    for py_file in src_dir.rglob("*.py"):
        # 忽略空文件或 init
        if py_file.name == "__init__.py" or py_file.stat().st_size == 0:
            continue

        content = py_file.read_text(encoding="utf-8")

        # 1. 物理检查头部 Docstring 是否存在
        if not content.lstrip().startswith('"""') and not content.lstrip().startswith("'''"):
            desync_issues.append(f"{py_file.name}: 缺失标准化头部注释 (Docstring)。")
            continue

        # 2. 检查对应目录是否有 README.md
        module_readme = py_file.parent / "README.md"
        if not module_readme.exists():
            desync_issues.append(f"{py_file.parent.name}/ 模块: 缺失模块级 README.md。")

    if desync_issues:
        err_msg = "致命阻断：检测到代码与文档严重脱节！\n" + "\n".join(desync_issues)
        print(f"\033[91m{err_msg}\033[0m")
        # 写入物理锁，直接挂起，不消耗任何 API Token
        LOCK_FILE.write_text(err_msg, encoding='utf-8')
        raise EnvironmentError("文档体系腐化，拒绝启动智能体规划流转。请人类修复知识库。")

    print("\033[92m[SYNC PASS] 文档代码同构校验通过，知识库未腐化。\033[0m")
    return state


def cpo_plan_node(state: AgentGlobalState): return state


def cpo_critic_node(state: AgentGlobalState): return state


def prototype_decision_node(state: AgentGlobalState): return state


def parallel_dispatch_node(state: AgentGlobalState): return state


def proto_lofi(state: AgentGlobalState): return state


def proto_hifi(state: AgentGlobalState): return state


def proto_reviewer(state: AgentGlobalState): return state


# --- 升级：CTO 节点加入上下文切片 ---
def cto_coder_node(state: AgentGlobalState) -> dict:
    """CTO 研发节点：严格执行上下文切片，杜绝信息污染"""

    # 1. 提取当前任务 ID (假设通过 Send API 传递)
    task_id = state.get("current_task_id")

    # 2. 【核心】只加载自己的任务契约，绝对不看 CMO 的营销文案需求
    my_contract = state.get("sub_tasks", {}).get(task_id)
    if not my_contract:
        # 为了防止本地测试报错，加入容错：如果没有传 task_id，先随便建一个空骨架
        my_contract = {"task_description": "待分配的具体任务"}

    # 3. 构建极简的 LLM 专属上下文 (Slicing)
    llm_context = {
        "global_goal": state.get("task_contract", {}).get("task_goal", ""),
        "my_strict_contract": my_contract,
        "previous_errors": state.get("control", {}).get("error_traceback", []),
    }

    # 4. 调用阿里云 API (伪代码)
    # response = call_aliyun_qwen_api(prompt=llm_context)
    print(f"[CTO Slicing] 已隔离上下文，仅专注当前任务: {task_id}")

    # 5. 状态回写：利用 Reducer 机制，绝不覆盖其他节点的产出
    return {
        "execution": {
            "cto_output": {"protocol_code": "..."}
        }
    }


def cto_hook(state: AgentGlobalState): return state


def cto_demo_verifier(state: AgentGlobalState): return state


def cto_reviewer(state: AgentGlobalState): return state


def cto_acceptance(state: AgentGlobalState): return state


def cmo_strategist(state: AgentGlobalState): return state


def cmo_fact_check(state: AgentGlobalState): return state


def cmo_acceptance(state: AgentGlobalState): return state


def hitl_handler(state: AgentGlobalState):
    return {"metadata": {"global_status": "halted"}}


def state_merge(state: AgentGlobalState): return state


def consensus_log_trigger(state: AgentGlobalState): return state


# ==========================================
# 2. 核心流转与并行路由控制 (Conditional Edges)
# ==========================================
def critic_router(state: AgentGlobalState) -> Literal["prototype_decision_node", "hitl_handler", "cpo_plan"]:
    decision = state.get("execution", {}).get("critic_decision", "REJECT")
    retry_count = state.get("control", {}).get("retry_counts", {}).get("cpo_plan", 0)
    if decision == "PASS":
        return "prototype_decision_node"
    elif retry_count >= 3:
        return "hitl_handler"
    else:
        return "cpo_plan"


def prototype_router(state: AgentGlobalState) -> Literal["proto_lofi", "proto_hifi", "parallel_dispatch_node"]:
    decision = state.get("prototype_evaluation", {}).get("decision_result", "NO_PROTOTYPE")
    if decision == "PROTOTYPING_LO_FI":
        return "proto_lofi"
    elif decision == "PROTOTYPING_HI_FI":
        return "proto_hifi"
    return "parallel_dispatch_node"


def proto_review_router(state: AgentGlobalState) -> Literal["proto_lofi", "proto_hifi", "parallel_dispatch_node"]:
    return "parallel_dispatch_node"


def map_reduce_dispatcher(state: AgentGlobalState) -> list[Send]:
    sends = []
    sub_tasks = state.get("sub_tasks", {})
    for task_id, task in sub_tasks.items():
        role = task.get("target_role")
        if role == "cto":
            sends.append(Send("cto_coder", {"current_task_id": task_id}))
        elif role == "cmo":
            sends.append(Send("cmo_strategist", {"current_task_id": task_id}))
    return sends


# ==========================================
# 3. 组装强类型全局状态机 (The LangGraph Blueprint)
# ==========================================
workflow = StateGraph(AgentGlobalState)

workflow.add_node("hash_check", hash_check_node)
workflow.add_node("doc_code_sync_check", doc_code_sync_check_node)  # 新增节点注册
workflow.add_node("cpo_plan", cpo_plan_node)
workflow.add_node("cpo_critic", cpo_critic_node)
workflow.add_node("prototype_decision_node", prototype_decision_node)
workflow.add_node("parallel_dispatch_node", parallel_dispatch_node)
workflow.add_node("proto_lofi", proto_lofi)
workflow.add_node("proto_hifi", proto_hifi)
workflow.add_node("proto_reviewer", proto_reviewer)
workflow.add_node("cto_coder", cto_coder_node)  # 替换为带切片的正式节点
workflow.add_node("cto_hook", cto_hook)
workflow.add_node("cto_demo_verifier", cto_demo_verifier)
workflow.add_node("cto_reviewer", cto_reviewer)
workflow.add_node("cto_acceptance", cto_acceptance)
workflow.add_node("cmo_strategist", cmo_strategist)
workflow.add_node("cmo_fact_check", cmo_fact_check)
workflow.add_node("cmo_acceptance", cmo_acceptance)
workflow.add_node("state_merge", state_merge)
workflow.add_node("consensus_log_trigger", consensus_log_trigger)
workflow.add_node("hitl_handler", hitl_handler)

# --- 连线拓扑 ---
workflow.set_entry_point("hash_check")
workflow.add_edge("hash_check", "doc_code_sync_check")  # 哈希检查后，进入文档同步检查
workflow.add_edge("doc_code_sync_check", "cpo_plan")  # 文档没问题，才允许 CPO 规划

workflow.add_edge("cpo_plan", "cpo_critic")
workflow.add_conditional_edges("cpo_critic", critic_router)

workflow.add_conditional_edges("prototype_decision_node", prototype_router)
workflow.add_edge("proto_lofi", "proto_reviewer")
workflow.add_edge("proto_hifi", "proto_reviewer")
workflow.add_conditional_edges("proto_reviewer", proto_review_router)

workflow.add_conditional_edges("parallel_dispatch_node", map_reduce_dispatcher)

workflow.add_edge("cto_coder", "cto_hook")
workflow.add_edge("cto_hook", "cto_demo_verifier")
workflow.add_edge("cto_demo_verifier", "cto_reviewer")
workflow.add_edge("cto_reviewer", "cto_acceptance")
workflow.add_edge("cto_acceptance", "state_merge")

workflow.add_edge("cmo_strategist", "cmo_fact_check")
workflow.add_edge("cmo_fact_check", "cmo_acceptance")
workflow.add_edge("cmo_acceptance", "state_merge")

workflow.add_edge("state_merge", "consensus_log_trigger")
workflow.add_edge("consensus_log_trigger", END)

app = workflow.compile()