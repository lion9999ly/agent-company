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

    # 1. 扫描架构宪法文件
    if ARCH_DIR.exists():
        for md_file in ARCH_DIR.glob("*.md"):
            content = md_file.read_bytes()
            current_hashes[md_file.name] = hashlib.sha256(content).hexdigest()

    # 2. 扫描核心配置文件 (模型智商与工具能力)
    if CONFIG_DIR.exists():
        for yaml_file in CONFIG_DIR.glob("*.yaml"):
            content = yaml_file.read_bytes()
            current_hashes[yaml_file.name] = hashlib.sha256(content).hexdigest()

    return current_hashes


# ==========================================
# 1. 节点逻辑存根 (Nodes)
# ==========================================
def hash_check_node(state: AgentGlobalState) -> dict:
    """
    【节点级】全目录架构哈希校验。
    在 LangGraph 每次启动流转时，作为 Entry Point 第一时间被触发。
    """
    print("\n[SECURITY] 初始化系统，正在执行底座防篡改哈希核对...")

    # 1. 如果连快照文件都不存在，说明系统处于未初始化或被破坏状态
    if not HASH_FILE.exists():
        err_msg = "致命错误：找不到 snapshot_hashes.json 基准快照文件！系统拒绝启动。"
        print(f"\033[91m{err_msg}\033[0m")
        # 物理锁死
        LOCK_FILE.write_text(f"HALTED_BY_HASH_CHECK_NODE: {err_msg}", encoding='utf-8')
        raise PermissionError(err_msg)

    try:
        baseline_hashes = json.loads(HASH_FILE.read_text(encoding='utf-8'))
    except json.JSONDecodeError:
        raise ValueError("快照哈希文件损坏，无法解析为 JSON。")

    # 2. 实时计算当前硬盘物理文件的哈希
    runtime_hashes = compute_directory_hash()

    # 3. 严格比准
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
        # 在图结构入口直接抛出异常，切断执行流
        raise SecurityError(err_msg)

    print("\033[92m[SECURITY PASS] 架构哈希校验一致，信任根稳固，允许放行。\033[0m")

    # 状态无异常，向前推进状态机
    return {"metadata": {"global_status": "planning"}}


def cpo_plan_node(state: AgentGlobalState):
    """【待实现】CPO 拆解中枢"""
    return state


def cpo_critic_node(state: AgentGlobalState):
    """【待实现】CPO 漏洞嗅探器"""
    return state


def prototype_decision_node(state: AgentGlobalState):
    """承接 Critic PASS 状态的中间节点，用于触发原型路由"""
    return state


def parallel_dispatch_node(state: AgentGlobalState):
    """承接原型全量通过后的中间节点，准备 Map-Reduce"""
    return state


# 原型、CTO、CMO 与人类介入的存根节点
def proto_lofi(state: AgentGlobalState): return state


def proto_hifi(state: AgentGlobalState): return state


def proto_reviewer(state: AgentGlobalState): return state


def cto_coder(state: AgentGlobalState): return state


def cto_hook(state: AgentGlobalState): return state


def cto_demo_verifier(state: AgentGlobalState): return state


def cto_reviewer(state: AgentGlobalState): return state


def cto_acceptance(state: AgentGlobalState): return state


def cmo_strategist(state: AgentGlobalState): return state


def cmo_fact_check(state: AgentGlobalState): return state


def cmo_acceptance(state: AgentGlobalState): return state


def hitl_handler(state: AgentGlobalState):
    # 触发物理挂起机制
    return {"metadata": {"global_status": "halted"}}


def state_merge(state: AgentGlobalState): return state


def consensus_log_trigger(state: AgentGlobalState): return state


# ==========================================
# 2. 核心流转与并行路由控制 (Conditional Edges)
# ==========================================
def critic_router(state: AgentGlobalState) -> Literal["prototype_decision_node", "hitl_handler", "cpo_plan"]:
    """单源决策：Critic 对审后的死循环与熔断路由"""
    decision = state.get("execution", {}).get("critic_decision", "REJECT")
    retry_count = state.get("control", {}).get("retry_counts", {}).get("cpo_plan", 0)

    if decision == "PASS":
        return "prototype_decision_node"  # 流向中间节点
    elif retry_count >= 3:
        return "hitl_handler"
    else:
        return "cpo_plan"


def prototype_router(state: AgentGlobalState) -> Literal["proto_lofi", "proto_hifi", "parallel_dispatch_node"]:
    """原型决策树分发"""
    decision = state.get("prototype_evaluation", {}).get("decision_result", "NO_PROTOTYPE")
    if decision == "PROTOTYPING_LO_FI":
        return "proto_lofi"
    elif decision == "PROTOTYPING_HI_FI":
        return "proto_hifi"
    return "parallel_dispatch_node"


def proto_review_router(state: AgentGlobalState) -> Literal["proto_lofi", "proto_hifi", "parallel_dispatch_node"]:
    """原型评审后的闭环流转"""
    # 【待实现】基于评审结果判断回退、晋级高保真或全量通过
    return "parallel_dispatch_node"


def map_reduce_dispatcher(state: AgentGlobalState) -> list[Send]:
    """LangGraph 原生 Send API：动态扇出并行任务"""
    sends = []
    sub_tasks = state.get("sub_tasks", {})

    for task_id, task in sub_tasks.items():
        role = task.get("target_role")
        depends_on = task.get("depends_on", [])

        # 【待实现】依赖死锁防线逻辑 (轮询超时/等待)

        # 发送特定切片给下游节点，实现隔离沙盒并行
        if role == "cto":
            sends.append(Send("cto_coder", {"current_task_id": task_id}))
        elif role == "cmo":
            sends.append(Send("cmo_strategist", {"current_task_id": task_id}))

    return sends


# ==========================================
# 3. 组装强类型全局状态机 (The LangGraph Blueprint)
# ==========================================
workflow = StateGraph(AgentGlobalState)

# 注册所有节点
workflow.add_node("hash_check", hash_check_node)
workflow.add_node("cpo_plan", cpo_plan_node)
workflow.add_node("cpo_critic", cpo_critic_node)
workflow.add_node("prototype_decision_node", prototype_decision_node)
workflow.add_node("parallel_dispatch_node", parallel_dispatch_node)
workflow.add_node("proto_lofi", proto_lofi)
workflow.add_node("proto_hifi", proto_hifi)
workflow.add_node("proto_reviewer", proto_reviewer)
workflow.add_node("cto_coder", cto_coder)
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
workflow.add_edge("hash_check", "cpo_plan")
workflow.add_edge("cpo_plan", "cpo_critic")

# 修复：单源决策挂载
workflow.add_conditional_edges("cpo_critic", critic_router)

# 原型流转与闭环
workflow.add_conditional_edges("prototype_decision_node", prototype_router)
workflow.add_edge("proto_lofi", "proto_reviewer")
workflow.add_edge("proto_hifi", "proto_reviewer")
workflow.add_conditional_edges("proto_reviewer", proto_review_router)

# 修复：真正的 Map-Reduce 并行扇出
workflow.add_conditional_edges("parallel_dispatch_node", map_reduce_dispatcher)

# 补全：CTO 内部验收自愈环 (线性流转，后续可加条件回退)
workflow.add_edge("cto_coder", "cto_hook")
workflow.add_edge("cto_hook", "cto_demo_verifier")
workflow.add_edge("cto_demo_verifier", "cto_reviewer")
workflow.add_edge("cto_reviewer", "cto_acceptance")
workflow.add_edge("cto_acceptance", "state_merge")

# 补全：CMO 内部验收自愈环
workflow.add_edge("cmo_strategist", "cmo_fact_check")
workflow.add_edge("cmo_fact_check", "cmo_acceptance")
workflow.add_edge("cmo_acceptance", "state_merge")

# 尾部收口
workflow.add_edge("state_merge", "consensus_log_trigger")
workflow.add_edge("consensus_log_trigger", END)

# 编译
app = workflow.compile()