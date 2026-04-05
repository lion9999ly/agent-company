"""
@description: LangGraph状态机流转拓扑，定义Multi-Agent工作流节点与连线
@dependencies: langgraph.graph, langgraph.types, src.schema.state, src.graph.context_slicer, src.utils.model_gateway, src.config.prompt_loader, scripts.doc_sync_validator, uuid
@last_modified: 2026-03-21
"""
import os
import hashlib
import json
from pathlib import Path
from typing import Literal
from datetime import datetime
from langgraph.graph import StateGraph, END
from langgraph.types import Send

# 导入刚刚定义的强类型状态字典
from src.schema.state import AgentGlobalState
# 导入上下文切片管理器
from src.graph.context_slicer import get_context_slicer, ContextSlice
# 导入模型网关
from src.utils.model_gateway import get_model_gateway
# 导入工具注册表
from src.tools.tool_registry import get_tool_registry
# 导入 prompt 加载器
from src.config.prompt_loader import get_agent_prompt
# 导入知识库
from src.tools.knowledge_base import search_knowledge, format_knowledge_for_prompt


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

# 导入文档同构校验器
import sys
sys.path.insert(0, str(ROOT_DIR))
from scripts.doc_sync_validator import DocCodeSyncValidator, SyncSeverity

# Checkpoint 持久化
try:
    from langgraph.checkpoint.sqlite import SqliteSaver
    import sqlite3
    _checkpoint_db = ROOT_DIR / ".ai-state" / "langgraph_checkpoints.db"
    _checkpoint_db.parent.mkdir(parents=True, exist_ok=True)
    _checkpoint_conn = sqlite3.connect(str(_checkpoint_db), check_same_thread=False)
    _checkpointer = SqliteSaver(_checkpoint_conn)
    HAS_CHECKPOINT = True
    print(f"[Checkpoint] SQLite 持久化已启用: {_checkpoint_db}")
except ImportError:
    _checkpointer = None
    HAS_CHECKPOINT = False
    print("[Checkpoint] langgraph-checkpoint-sqlite 未安装，checkpoint 禁用")
except Exception as e:
    _checkpointer = None
    HAS_CHECKPOINT = False
    print(f"[Checkpoint] 初始化失败: {e}，checkpoint 禁用")


# ==========================================
# 三原则：所有 Agent 必须遵循的思维准则
# ==========================================
THINKING_PRINCIPLES = """
## 思维准则（所有分析必须遵循）

1. **第一性原理**：拒绝经验主义和路径盲从。从原始需求和本质问题出发。若目标模糊，先澄清再行动。若路径不是最优，直接建议更短、更低成本的办法。

2. **奥卡姆剃刀**：如无必要，勿增实体。砍掉所有不影响核心交付的冗余——多余的功能、步骤、复杂度。

3. **苏格拉底追问**：对每个方案连续追问——这是真正的问题还是 XY 问题？路径有什么弊端？有没有更优替代方案？失败最可能的原因是什么？
"""


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
    # 保留完整状态，只更新 metadata
    return {**state, "metadata": {**state.get("metadata", {}), "global_status": "planning"}}


# --- 新增：文档代码同构校验节点 ---
def doc_code_sync_check_node(state: AgentGlobalState) -> dict:
    """
    文档与代码同构物理校验节点。
    在启动大模型规划前，确保知识库没有腐化。

    增强版本：
    1. 检查Docstring格式（@description, @dependencies, @last_modified）
    2. 检查模块README.md存在性和内容结构
    3. 检查依赖声明与实际import一致性
    4. 生成详细报告到 .ai-state/sync_report.json
    """
    print("\n[SYNC CHECK] 正在执行全量文档-代码同构校验...")

    # 使用增强校验器
    validator = DocCodeSyncValidator(src_dir=ROOT_DIR / "src")
    report = validator.validate_all()

    # 输出格式化报告
    print(validator.format_report(report))

    # 根据严重程度决定行为
    critical_errors = report.critical_issues
    errors = report.error_issues

    if critical_errors > 0:
        err_msg = f"致命阻断：检测到 {critical_errors} 个严重文档腐化问题！"
        print(f"\033[91m{err_msg}\033[0m")
        LOCK_FILE.write_text(err_msg, encoding='utf-8')
        raise EnvironmentError("文档体系严重腐化，拒绝启动智能体规划流转。")

    if errors > 50:
        # 允许少量错误通过（警告级别），但超过阈值则阻断
        err_msg = f"阻断：文档同构错误超过阈值 ({errors} > 50)，请修复后再启动。"
        print(f"\033[91m{err_msg}\033[0m")
        LOCK_FILE.write_text(err_msg, encoding='utf-8')
        raise EnvironmentError("文档同构错误过多，请修复知识库。")

    if errors > 0:
        print(f"\033[93m[SYNC WARNING] 存在 {errors} 个文档问题，但允许通过。建议尽快修复。\033[0m")
    else:
        print("\033[92m[SYNC PASS] 文档代码同构校验通过，知识库未腐化。\033[0m")

    return state


def _load_recent_memories(limit: int = 5) -> str:
    """读取最近 N 条任务记忆，返回格式化的摘要文本"""
    memory_dir = ROOT_DIR / ".ai-state" / "memory"
    if not memory_dir.exists():
        return ""
    files = sorted(memory_dir.glob("*.json"), reverse=True)[:limit]
    if not files:
        return ""
    summaries = []
    for f in files:
        try:
            record = json.loads(f.read_text(encoding="utf-8"))
            goal = record.get("task_goal", "")
            critic = record.get("critic_decision", "N/A")
            rating = record.get("user_rating", "")
            feedback = record.get("user_feedback", "")
            line = f"- [{record.get('timestamp','')}] {goal} (评审:{critic})"
            if rating:
                line += f" [用户评价:{rating}]"
            if rating in ("C", "D") and feedback:
                line += f" [反馈:{feedback}]"
            summaries.append(line)
        except Exception:
            continue
    return "\n".join(summaries) if summaries else ""


def _search_knowledge_for_task(task_goal: str, max_items: int = 15) -> str:
    """按任务目标检索知识库，返回注入文本

    优先级：内部产品定义 > 研究报告 > 普通条目
    """
    from src.tools.knowledge_base import KB_ROOT
    import re

    MAX_CHARS = 15000  # 注入上限

    # 提取关键词：中文按字，英文按词
    keywords = re.findall(r'[\u4e00-\u9fff]+|[a-zA-Z]{2,}', task_goal.lower())
    keywords = [k for k in keywords if len(k) > 1][:8]

    if not keywords:
        return ""

    candidates = []
    if KB_ROOT.exists():
        for json_file in KB_ROOT.rglob("*.json"):
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
                title = data.get("title", "")
                content = data.get("content", "")
                source = data.get("source", "")
                tags = data.get("tags", [])
                confidence = data.get("confidence", "")

                # 计算匹配分数
                score = 0
                searchable = f"{title} {content}".lower()
                for kw in keywords:
                    if kw in searchable:
                        score += 1

                if score == 0:
                    continue

                # 判断文档类型
                is_report = data.get("type") == "report" or "REPORT_" in json_file.name
                is_internal = (
                    "internal" in tags
                    or "prd" in tags
                    or "product_definition" in tags
                    or "anchor" in tags
                    or "user_upload" in source
                    or confidence == "authoritative"
                )

                # 决策树型知识加权
                is_decision_tree = "decision_tree" in tags or "knowledge_graph" in tags

                # 推测性内容降权
                is_speculative = "speculative" in tags
                if is_speculative:
                    score -= 5

                # 内部文档强制加权（按类型分级）
                if is_internal:
                    score += 20
                    # PRD 和用户旅程图额外加权
                    if any(kw in title.lower() for kw in ["prd", "用户旅程", "user journey", "功能清单", "需求", "规格"]):
                        score += 30  # PRD 类文档最高优先级
                    elif any(kw in title.lower() for kw in ["设计", "原型", "wireframe", "ui", "ux"]):
                        score += 15  # 设计类文档次优先级
                elif is_decision_tree:
                    score += 10  # 决策树次于内部文档，但高于普通条目

                candidates.append({
                    "title": title,
                    "content": content,
                    "is_report": is_report,
                    "is_internal": is_internal,
                    "score": score
                })
            except Exception:
                continue

    if not candidates:
        return ""

    # 排序：内部文档 > 报告 > 普通条目，同级别按分数
    candidates.sort(key=lambda x: (-x["is_internal"], -x["is_report"], -x["score"]))
    top_candidates = candidates[:max_items]

    # 构建注入文本
    parts = ["## 项目知识库参考"]
    total_chars = 0
    internal_count = 0

    for item in top_candidates:
        if item["is_internal"]:
            # 内部文档取前 4000 字，明确标注优先级
            text = f"\n\n### [内部产品定义 - 最高优先级] {item['title']}\n{item['content'][:4000]}"
            internal_count += 1
        elif item["is_report"]:
            text = f"\n\n### [研究报告] {item['title']}\n{item['content'][:2000]}"
        else:
            text = f"\n\n### {item['title']}\n{item['content'][:400]}"

        if total_chars + len(text) > MAX_CHARS:
            break
        parts.append(text)
        total_chars += len(text)

    result = "".join(parts)
    print(f"[CPO_KB] 检索到 {len(top_candidates)} 条知识（内部文档 {internal_count} 条，报告 {sum(1 for x in top_candidates if x['is_report'])} 条）")
    return result


def _cpo_generate_plan(task_goal: str, memories: str, critic_feedback: str, retry_count: int) -> dict:
    """CPO 真实规划：根据任务目标、历史记忆和评审反馈生成任务分配"""
    from src.tools.knowledge_base import KB_ROOT
    gateway = get_model_gateway()

    # 读取产品定义锚点
    product_anchor = ""
    if KB_ROOT.exists():
        for f in KB_ROOT.rglob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                tags = data.get("tags", [])
                if "internal" in tags and ("prd" in tags or "product_definition" in tags):
                    product_anchor = data.get("content", "")[:2000]
                    break
            except:
                continue

    anchor_text = ""
    if product_anchor:
        anchor_text = (
            "\n\n## 产品定义锚点（不可违背）\n"
            "以下是用户已确定的产品定义。你的分析必须在此框架内进行。\n"
            "你可以建议分阶段实现（V1/V2），但不能替用户更换产品品类或核心方向。\n"
            f"{product_anchor[:1500]}\n"
        )

    # === 注入产品目标（用户的战略意图，必须驱动规划） ===
    goal_file = ROOT_DIR / ".ai-state" / "product_goal.json"
    goal_text = ""
    if goal_file.exists():
        try:
            goal_data = json.loads(goal_file.read_text(encoding="utf-8"))
            goal_text = goal_data.get("goal", "")
        except:
            pass

    goal_inject = ""
    if goal_text:
        goal_inject = (
            f"\n\n## 产品目标（必须对齐，所有分析围绕此目标展开）\n"
            f"以下是用户明确的产品目标。你的分析和建议必须帮助实现这个目标，而不只是按难易排序。\n"
            f"如果当前任务和目标有冲突，指出来并给出解决方案。\n"
            f"如果当前任务是目标的子任务，说明它在目标中的位置和紧迫度。\n"
            f"{goal_text}\n"
        )

    parts = [f"## 当前任务\n{task_goal}"]
    if anchor_text:
        parts.append(anchor_text)
    if goal_inject:
        parts.append(goal_inject)
    # 注入思维准则
    parts.append(THINKING_PRINCIPLES)

    # === 注入经验教训：过去失败和成功的经验 ===
    from src.tools.knowledge_base import search_knowledge
    evolution_entries = search_knowledge("教训 成功模式 evolution", limit=5)
    if evolution_entries:
        evolution_text = "\n## 经验教训（过去任务的反馈总结）\n"
        for entry in evolution_entries:
            if "evolution" in entry.get("tags", []):
                evolution_text += f"\n- **{entry['title']}**: {entry['content'][:300]}\n"
        if len(evolution_text) > 50:
            parts.append(evolution_text)
            print(f"[CPO_Plan] 注入 {len(evolution_entries)} 条经验教训")

    if memories:
        parts.append(f"## 历史任务经验\n{memories}")
    # 知识库检索（提升到15条）
    kb_text = _search_knowledge_for_task(task_goal, max_items=15)
    if kb_text:
        parts.append(kb_text)
    if critic_feedback and retry_count > 1:
        parts.append(f"## 上轮评审反馈\n{critic_feedback[:1500]}")
    prompt = "\n\n".join(parts)
    sys_prompt = get_agent_prompt("cpo_plan")
    result = gateway.call_azure_openai("cpo", prompt, sys_prompt, "planning")
    if not result.get("success"):
        return {"roles": ["cto"], "tasks": {"cto": task_goal}}
    roles, tasks = [], {}
    for line in result["response"].split("\n"):
        line = line.strip()
        if line.startswith("ROLES:"):
            roles = [r.strip() for r in line[6:].split(",") if r.strip() in ("cto", "cmo", "cdo")]
        elif line.startswith("CTO_TASK:"):
            tasks["cto"] = line[9:].strip()
        elif line.startswith("CMO_TASK:"):
            tasks["cmo"] = line[9:].strip()
        elif line.startswith("CDO_TASK:"):
            tasks["cdo"] = line[9:].strip()
    if not roles:
        roles = ["cto"]
    if not tasks:
        tasks = {r: task_goal for r in roles}
    return {"roles": roles, "tasks": tasks}


def cpo_plan_node(state: AgentGlobalState) -> dict:
    """CPO 规划节点：真实 LLM 调用，带记忆和评审反馈"""
    import uuid
    control = state.get("control", {})
    retry_counts = control.get("retry_counts", {})
    retry_counts["cpo_plan"] = retry_counts.get("cpo_plan", 0) + 1
    retry_count = retry_counts["cpo_plan"]

    # 【全局计数】每次进入 cpo_plan 都增加总迭代次数
    total_iterations = control.get("total_iterations", 0) + 1
    print(f"[CPO_PLAN] 总迭代次数: {total_iterations}, 本次规划轮次: {retry_count}")

    # 【关键修复】重新规划时清除上一轮的评审状态，避免幂等性检查卡死
    execution = state.get("execution", {})
    if retry_count > 1:
        print(f"[CPO_PLAN] 第 {retry_count} 次规划，清除上一轮 critic 状态")
        execution = {k: v for k, v in execution.items()
                     if k not in ("critic_decision", "critic_feedback", "merge_summary", "synthesis_output")}

    task_goal = state.get("task_contract", {}).get("task_goal", "")
    memories = _load_recent_memories(5)
    critic_feedback = state.get("execution", {}).get("critic_feedback", "")
    plan = _cpo_generate_plan(task_goal, memories, critic_feedback, retry_count)
    print(f"[CPO_PLAN] 第 {retry_count} 次规划，角色: {plan['roles']}，记忆: {bool(memories)}")
    task_id = state.get("metadata", {}).get("task_id", f"task_{uuid.uuid4().hex[:8]}")
    sub_tasks = {}
    for role in plan["roles"]:
        sub_id = f"{role}_{task_id}"
        sub_tasks[sub_id] = {
            "subtask_id": sub_id, "target_role": role,
            "task_description": plan["tasks"].get(role, task_goal),
            "depends_on": [], "is_core_dependency": False,
            "dependency_timeout_sec": 120, "output_schema": {},
            "acceptance_criteria": {}, "tool_white_list": []
        }
    return {
        **state, "sub_tasks": sub_tasks,
        "control": {**control, "retry_counts": retry_counts, "total_iterations": total_iterations},
        "execution": execution,
        "memory_context": memories
    }


def _run_critic_review(task_goal: str, cto_output: str, cmo_output: str, cdo_output: str = "",
                       rules_text: str = "", kb_verification_text: str = "") -> dict:
    """执行主从评审逻辑，返回 {"decision": "PASS"/"REJECT", "feedback": str}

    Phase 1 升级：三层评审体系
    1. 结构化规则检查（rules_text）
    2. 知识库数据交叉校验（kb_verification_text）
    3. LLM 自由评审（原有逻辑）
    """
    gateway = get_model_gateway()

    # === 构建评审 prompt ===
    review_input = (
        f"## 原始任务\n{task_goal}\n\n"
        f"## CTO技术方案\n{cto_output[:3000]}\n\n"
        f"## CMO市场策略\n{cmo_output[:3000]}\n\n"
    )
    if cdo_output:
        review_input += f"## CDO设计方案\n{cdo_output[:3000]}\n\n"

    # === Layer 1: 结构化规则检查 ===
    if rules_text:
        review_input += f"{rules_text}\n\n"

    # === Layer 2: 知识库数据交叉校验 ===
    if kb_verification_text:
        review_input += (
            f"## 知识库参考数据（用于交叉校验）\n"
            f"以下是项目知识库中与本任务相关的技术档案。请用这些数据交叉验证 Agent 输出中的关键声明。\n"
            f"如果 Agent 声明的参数（芯片型号、功耗、价格、性能指标）与知识库数据矛盾，必须指出。\n"
            f"如果知识库中没有相关数据可验证，标记为 [UNVERIFIED]。\n\n"
            f"{kb_verification_text}\n\n"
        )

    # === Layer 3: 自由评审 ===
    review_input += (
        "## 评审要求\n"
        "请按以下顺序输出评审结论：\n\n"
    )

    if rules_text:
        review_input += (
            "### 一、规则检查\n"
            "逐项检查上面的规则清单，每条给出 ✅ PASS / ❌ FAIL / ⚠️ UNVERIFIED + 理由\n\n"
        )

    if kb_verification_text:
        review_input += (
            "### 二、数据校验\n"
            "对比 Agent 输出中的关键数据与知识库参考数据，列出：\n"
            "- [VERIFIED] 与知识库一致的数据点\n"
            "- [CONFLICT] 与知识库矛盾的数据点（必须具体说明差异）\n"
            "- [UNVERIFIED] 知识库中无法验证的数据点\n\n"
        )

    review_input += (
        "### 三、综合评审\n"
        "评审方案的可行性、完整性和风险。\n"
        "特别关注：技术方案与设计方案之间是否存在冲突（如散热空间、天线布局、重量预算）。\n"
        "第一行只写 PASS 或 REJECT。\n"
        "如果 REJECT，用 <Modify_Action> 标签包裹具体修改指令。"
    )

    system_prompt = get_agent_prompt("critic")

    # === 主从评审（原有逻辑不变） ===
    primary = gateway.call_gemini("critic_gemini", review_input, system_prompt, "review")
    if primary.get("success") and "PASS" in primary["response"].upper():
        return {"decision": "PASS", "feedback": primary["response"]}

    secondary = gateway.call_azure_openai("cpo", review_input, system_prompt, "review")
    if not primary.get("success") and secondary.get("success"):
        decision = "PASS" if "PASS" in secondary["response"].upper() else "REJECT"
        return {"decision": decision, "feedback": secondary.get("response", "")}

    if secondary.get("success") and "PASS" in secondary["response"].upper():
        return {"decision": "PASS", "feedback": f"[有条件通过]\n主评审建议:\n{primary.get('response', '')[:2000]}"}

    feedback = primary.get("response", "") + "\n---\n" + secondary.get("response", "")
    return {"decision": "REJECT", "feedback": feedback[:4000]}


def cpo_critic_node(state: AgentGlobalState) -> dict:
    """CPO 评审节点：结构化规则检查 + 知识库数据校验 + 主从双模型评审

    Phase 1 升级：三层评审体系
    幂等性保护：确保只执行一次评审
    """
    execution = state.get("execution", {})

    # 【幂等性检查】如果已经评审过，直接返回
    if execution.get("critic_decision"):
        print(f"[CPO_Critic] 已评审过: {execution.get('critic_decision')}")
        return {}

    # 【保险】在评审前检查 retry_count 是否超限
    retry_count = state.get("control", {}).get("retry_counts", {}).get("cpo_plan", 0)
    if retry_count >= 2:
        print(f"[CPO_Critic] 重试已达上限 ({retry_count} 次)，强制 PASS")
        synthesis_output = execution.get("synthesis_output", "")
        return {"execution": {**execution,
            "critic_decision": "PASS",
            "critic_feedback": "[重试上限，自动通过]"}}

    task_goal = state.get("task_contract", {}).get("task_goal", "未知任务")
    cto_output = execution.get("cto_output", {})
    cmo_output = execution.get("cmo_output", {})
    cdo_output = execution.get("cdo_output", {})

    # 尝试多种字段名获取输出
    cto_text = cto_output.get("protocol_code") or cto_output.get("output") or cto_output.get("result") or ""
    cmo_text = cmo_output.get("market_strategy") or cmo_output.get("output") or cmo_output.get("result") or ""
    cdo_text = cdo_output.get("design_proposal") or cdo_output.get("output") or cdo_output.get("result") or ""

    if not cto_text and not cmo_text and not cdo_text:
        print("[CPO_Critic] 无输出可评审，直接 PASS")
        return {"execution": {**execution, "critic_decision": "PASS"}}

    # === Phase 1.3: 获取相关检查规则 ===
    rules_text = ""
    try:
        from src.utils.critic_rules import get_relevant_rules, format_rules_for_critic
        relevant_rules = get_relevant_rules(task_goal)
        if relevant_rules:
            rules_text = format_rules_for_critic(relevant_rules)
            print(f"[CPO_Critic] 注入 {len(relevant_rules)} 条检查规则")
        else:
            print(f"[CPO_Critic] 无相关检查规则")
    except Exception as e:
        print(f"[CPO_Critic] 规则加载失败: {e}")

    # === Phase 1.4: 知识库数据校验 ===
    kb_verification_text = ""
    try:
        # === 新增：从待审内容中提取技术术语进行精准搜索 ===
        review_text = str(cto_text) + "\n" + str(cmo_text) + "\n" + str(cdo_text)
        import re
        tech_terms = re.findall(r'[A-Z]{2,}\d{2,}|AR[12]|QCC\d|BES\d|IMX\d|ECE|DOT|GB\s*\d+', review_text)
        tech_terms = list(set(tech_terms))[:5]  # 去重，最多 5 个

        kb_queries = tech_terms.copy()
        # 通用查询
        kb_queries.extend(["BOM 成本", "功耗预算 续航", "认证 标准"])

        critic_kb_context = ""
        for q in kb_queries[:8]:
            entries = search_knowledge(q, limit=2)
            for entry in entries:
                title = entry.get("title", "")
                content = entry.get("content", "")
                critic_kb_context += f"### {title}\n{content[:1000]}\n\n"

        # 原有检索逻辑（保留）
        kb_entries = search_knowledge(task_goal, limit=10)
        if kb_entries:
            parts = []
            for entry in kb_entries:
                title = entry.get("title", "")
                content = entry.get("content", "")
                confidence = entry.get("confidence", "")
                tags = entry.get("tags", [])

                # 优先选择有硬数据的条目（anchor、internal、decision_tree）
                is_high_value = (
                    "anchor" in tags or "internal" in tags or
                    "decision_tree" in tags or confidence == "authoritative"
                )

                # 跳过 speculative 条目（不适合做数据校验基准）
                if "speculative" in tags:
                    continue

                if is_high_value:
                    parts.append(f"### [高可信] {title}\n{content[:1500]}")
                elif len(content) > 200:
                    parts.append(f"### {title}\n{content[:800]}")

            if parts:
                critic_kb_context += "\n\n".join(parts[:8])  # 最多 8 条

        kb_verification_text = critic_kb_context[:4000]
        if kb_verification_text:
            print(f"[CPO_Critic] 知识库数据校验: 技术术语 {tech_terms}，共 {len(kb_queries)} 条查询")
        else:
            print(f"[CPO_Critic] 知识库无高质量参考数据")
    except Exception as e:
        print(f"[CPO_Critic] 知识库检索失败: {e}")

    print(f"[CPO_Critic] 启动三层评审... (CTO:{bool(cto_text)}, CMO:{bool(cmo_text)}, CDO:{bool(cdo_text)}, Rules:{bool(rules_text)}, KB:{bool(kb_verification_text)})")
    review = _run_critic_review(task_goal, str(cto_text), str(cmo_text), str(cdo_text),
                                 rules_text=rules_text, kb_verification_text=kb_verification_text)
    print(f"[CPO_Critic] 结果: {review['decision']}")
    return {"execution": {**execution,
        "critic_decision": review["decision"],
        "critic_feedback": review["feedback"][:4000]}}


def prototype_decision_node(state: AgentGlobalState): return state


def parallel_dispatch_node(state: AgentGlobalState): return state


def proto_lofi(state: AgentGlobalState): return state


def proto_hifi(state: AgentGlobalState): return state


def proto_reviewer(state: AgentGlobalState): return state


def _cto_research(task_desc: str) -> str:
    """CTO 技术调研：对技术相关任务搜索芯片规格、行业标准、参考设计"""
    registry = get_tool_registry()
    gateway = get_model_gateway()
    tech_data = ""
    keywords = ["芯片", "传感器", "协议", "标准", "选型", "BOM", "驱动", "模组",
                "电池", "充电", "无线", "蓝牙", "MCU", "LED", "IMU", "PCB"]
    matched = [kw for kw in keywords if kw in task_desc]
    if matched:
        query = f"{task_desc} 具体芯片型号 参数对比 价格 推荐方案 {' '.join(matched)}"
        result = registry.call("technical_research", query)
        if result.get("success"):
            raw_data = result.get("data", "")
            if len(raw_data) > 5000:
                # 用轻模型摘要，保留关键数据
                summary_prompt = (
                    f"以下是一份技术调研的原始结果（{len(raw_data)}字）。\n"
                    f"请提炼其中与「{task_desc}」最相关的内容，保留所有具体数据（型号、参数、价格、供应商）。\n"
                    f"输出 5000-8000 字的精华摘要。\n\n{raw_data[:15000]}"
                )
                summary_result = gateway.call_azure_openai("cpo", summary_prompt, "你是技术调研专家。", "research_summary")
                if summary_result.get("success"):
                    tech_data = summary_result["response"][:8000]
                    print(f"[CTO] 调研摘要: {len(raw_data)} -> {len(tech_data)} 字")
                else:
                    tech_data = raw_data[:5000]
            else:
                tech_data = raw_data

        # 如果 deep_research 返回不够，用 multi_engine_search 补充
        if tech_data and len(tech_data) < 500:
            multi_result = registry.call("multi_engine_search", task_desc[:100])
            if multi_result.get("success"):
                tech_data += "\n\n[多引擎补充]\n" + multi_result["data"][:2000]
                print(f"[CTO] 多引擎补充成功")
    return tech_data


# --- 升级：CTO 节点加入上下文切片 ---
def cto_coder_node(state: AgentGlobalState) -> dict:
    """
    CTO 研发节点：严格执行上下文切片，杜绝信息污染

    核心原则：
    1. 禁止读取 AgentGlobalState 全量数据
    2. 只通过 ContextSlicer 获取白名单字段
    3. 所有访问行为记录到审计日志
    """
    slicer = get_context_slicer()

    # 1. 提取当前任务 ID (通过 Send API 传递)
    task_id = state.get("current_task_id", "default_task")

    # 2. 获取对应的任务契约
    my_contract = state.get("sub_tasks", {}).get(task_id, {
        "subtask_id": task_id,
        "task_description": "待分配的具体任务"
    })

    # 3. 【核心】通过切片器创建隔离上下文
    slice_obj = slicer.create_cto_slice(
        task_id=task_id,
        global_state=dict(state),  # 转换为普通dict
        task_contract=my_contract
    )

    # 4. 仅使用切片数据，不访问全局状态
    llm_context = slice_obj.data
    print(f"[CTO Slicing] Slice ID: {slice_obj.slice_id}")
    print(f"[CTO Slicing] 已隔离上下文，仅专注当前任务: {task_id}")
    print(f"[CTO Slicing] 可访问字段: {list(llm_context.keys())}")

    # 5. 技术调研
    task_desc = my_contract.get("task_description", "")
    tech_research = _cto_research(task_desc)

    # 6. 调用 Azure OpenAI
    gateway = get_model_gateway()
    system_prompt = get_agent_prompt("cto")
    if tech_research:
        system_prompt += f"\n\n## 技术调研数据（来自工具搜索，请参考真实数据）\n{tech_research}"
    api_result = gateway.call_azure_openai("cto", str(llm_context), system_prompt)

    # 6. 更新切片产出
    if api_result.get("success"):
        protocol_code = api_result["response"]
    else:
        protocol_code = f"[CTO节点调用失败: {api_result.get('error', '未知错误')}]"
    output = {"protocol_code": protocol_code, "slice_checksum": slice_obj.checksum}
    slicer.update_slice_output(slice_obj.slice_id, "cto", output)

    # 7. 状态回写：利用 Reducer 机制，绝不覆盖其他节点的产出
    return {
        "execution": {
            "cto_output": output
        }
    }


def cto_hook(state: AgentGlobalState): return state


def cto_demo_verifier(state: AgentGlobalState): return state


def cto_reviewer(state: AgentGlobalState): return state


def cto_acceptance(state: AgentGlobalState): return state


def _cmo_research(task_desc: str) -> str:
    """CMO 工具调研：对市场相关任务进行深度搜索"""
    registry = get_tool_registry()
    research_data = ""
    if any(kw in task_desc for kw in ["竞品", "市场", "用户", "定价", "GTM", "调研"]):
        result = registry.call("deep_research", f"骑行头盔市场调研：{task_desc}")
        if result.get("success"):
            research_data = result["data"][:2000]
            print(f"[CMO] 工具调研成功，数据 {len(research_data)} 字")

    # 行业数据搜索（市场规模、份额、增长率）
    if any(kw in task_desc for kw in ["市场", "份额", "增长", "规模", "趋势", "出货量", "定价", "行业"]):
        industry_result = registry.call("industry_data_search",
            f"motorcycle smart helmet market size growth forecast 2024 2025 2026 2027")
        if industry_result.get("success"):
            research_data += "\n\n[行业数据]\n" + industry_result["data"][:2000]
            print(f"[CMO] 行业数据搜索成功")

    return research_data


def cmo_strategist(state: AgentGlobalState) -> dict:
    """
    CMO 市场节点：严格执行上下文切片，杜绝信息污染

    核心原则：
    1. 禁止读取 AgentGlobalState 全量数据
    2. 只通过 ContextSlicer 获取白名单字段
    3. 所有访问行为记录到审计日志
    """
    slicer = get_context_slicer()

    # 1. 提取当前任务 ID
    task_id = state.get("current_task_id", "default_task")

    # 2. 获取对应的任务契约
    my_contract = state.get("sub_tasks", {}).get(task_id, {
        "subtask_id": task_id,
        "task_description": "待分配的市场任务"
    })

    # 3. 【核心】通过切片器创建隔离上下文
    slice_obj = slicer.create_cmo_slice(
        task_id=task_id,
        global_state=dict(state),
        task_contract=my_contract
    )

    # 4. 仅使用切片数据
    llm_context = slice_obj.data
    print(f"[CMO Slicing] Slice ID: {slice_obj.slice_id}")
    print(f"[CMO Slicing] 已隔离上下文，任务: {task_id}")
    print(f"[CMO Slicing] 依赖: {slice_obj.dependencies}")

    # 4.5 使用工具做市场调研（如果有相关工具）
    task_desc = my_contract.get("task_description", "")
    research_data = _cmo_research(task_desc)

    # 5. 调用 Azure OpenAI (CMO) - 带 retry 机制
    gateway = get_model_gateway()
    system_prompt = get_agent_prompt("cmo")
    # 如果有调研数据，追加到 system_prompt
    if research_data:
        system_prompt += f"\n\n## 市场调研数据（来自工具）\n{research_data}"
    api_result = {"success": False, "error": "未初始化"}
    for attempt in range(3):
        api_result = gateway.call_azure_openai("cmo", str(llm_context), system_prompt)
        if api_result.get("success"):
            break
        print(f"[CMO] 第{attempt+1}次调用失败，{'重试中...' if attempt < 2 else '已放弃'}")
        if attempt < 2:
            import time; time.sleep(3)

    # 6. 更新切片产出
    if api_result.get("success"):
        market_strategy = api_result["response"]
    else:
        market_strategy = f"[CMO节点调用失败: {api_result.get('error', '未知错误')}]"
    output = {"market_strategy": market_strategy, "slice_checksum": slice_obj.checksum}
    slicer.update_slice_output(slice_obj.slice_id, "cmo", output)

    return {
        "execution": {
            "cmo_output": output
        }
    }


def cmo_fact_check(state: AgentGlobalState): return state


def cmo_acceptance(state: AgentGlobalState): return state


def _cdo_research(task_desc: str) -> str:
    """CDO 工具调研：对设计相关任务进行视觉趋势分析"""
    registry = get_tool_registry()
    design_data = ""
    if any(kw in task_desc for kw in ["设计", "外观", "造型", "UI", "UX", "配色", "材质", "灯效"]):
        result = registry.call("design_vision_analysis", f"骑行头盔设计趋势分析：{task_desc}")
        if result.get("success"):
            design_data = result["data"][:2000]
            print(f"[CDO] 设计调研成功，原始 {len(result["data"])} 字，截断到 {len(design_data)} 字")
    return design_data


def cdo_designer_node(state: AgentGlobalState) -> dict:
    """CDO(Carl) 设计节点：工业设计、外观造型、用户体验

    支持多模态：如果有图片输入，使用 doubao_vision_pro 进行图片分析
    """
    slicer = get_context_slicer()
    task_id = state.get("current_task_id", "default_task")
    my_contract = state.get("sub_tasks", {}).get(task_id,
        {"subtask_id": task_id, "task_description": "待分配的设计任务"})
    slice_obj = slicer.create_cdo_slice(task_id=task_id, global_state=dict(state), task_contract=my_contract)
    llm_context = slice_obj.data
    print(f"[CDO Slicing] Slice: {slice_obj.slice_id}, Task: {task_id}")
    task_desc = my_contract.get("task_description", "")
    design_research = _cdo_research(task_desc)
    gateway = get_model_gateway()
    system_prompt = get_agent_prompt("cdo")
    if design_research:
        system_prompt += f"\n\n## 设计趋势调研数据\n{design_research}"

    # 检查是否有图片输入（多模态支持）
    image_url = state.get("image_url") or my_contract.get("image_url")

    if image_url:
        # 有图片，使用 doubao_vision_pro 进行多模态分析
        print(f"[CDO] 检测到图片输入，使用 doubao_vision_pro 进行分析")
        api_result = gateway.call_volcengine(
            "doubao_vision_pro",
            str(llm_context),
            system_prompt,
            task_type="design_analysis",
            image_url=image_url
        )
    else:
        # 无图片，使用常规 Azure OpenAI
        api_result = gateway.call_azure_openai("cdo", str(llm_context), system_prompt)

    if api_result.get("success"):
        design_output = api_result["response"]
    else:
        design_output = f"[CDO节点调用失败: {api_result.get('error', '未知错误')}]"
    output = {"design_proposal": design_output, "slice_checksum": slice_obj.checksum}
    slicer.update_slice_output(slice_obj.slice_id, "cdo", output)
    return {"execution": {"cdo_output": output}}


def hitl_handler(state: AgentGlobalState):
    return {"metadata": {"global_status": "halted"}}


def state_merge(state: AgentGlobalState) -> dict:
    """汇聚 CTO、CMO、CDO 的输出，生成综合结论

    幂等性保护：确保只在所有预期输出就绪时执行一次
    """
    execution = state.get("execution", {})

    # 【幂等性检查】如果已经生成过 merge_summary，直接返回
    if execution.get("merge_summary"):
        return {}

    # 检查各角色输出是否就绪
    cto_output = execution.get("cto_output", {})
    cmo_output = execution.get("cmo_output", {})
    cdo_output = execution.get("cdo_output", {})

    protocol_code = cto_output.get("protocol_code", "")
    market_strategy = cmo_output.get("market_strategy", "")
    design_proposal = cdo_output.get("design_proposal", "")

    # 【就绪检查】如果所有输出都为空，说明还在等待其他分支
    if not protocol_code and not market_strategy and not design_proposal:
        return {}

    # 拼装各角色输出
    parts = []
    has_output = False

    if protocol_code:
        parts.append(f"=== CTO 技术方案 ===\n{protocol_code[:4000]}...")
        has_output = True
    if market_strategy:
        parts.append(f"=== CMO 市场策略 ===\n{market_strategy[:4000]}...")
        has_output = True
    if design_proposal:
        parts.append(f"=== CDO 设计方案 ===\n{design_proposal[:4000]}...")
        has_output = True

    if has_output:
        parts.append("=== 汇聚状态 ===\n多Agent输出完整，可进入评审环节。")
        summary = "\n\n".join(parts)
        print(f"[StateMerge] [OK] 输出汇聚完成，{len(parts)-1} 个角色参与")
    else:
        summary = "[StateMerge] 所有节点均无输出"
        print(f"[StateMerge] [FAIL] 所有节点均无输出")

    return {
        "execution": {
            **execution,
            "merge_summary": summary
        }
    }


def cpo_synthesis(state: AgentGlobalState) -> dict:
    """CPO 方案整合：交叉引用各 Agent 输出，消除矛盾，生成统一方案"""
    execution = state.get("execution", {})
    merge_summary = execution.get("merge_summary", "")

    # 如果没有 merge_summary，直接返回
    if not merge_summary or len(merge_summary) < 100:
        print("[CPO_Synthesis] 跳过整合：无有效输入")
        return {}

    gateway = get_model_gateway()
    system_prompt = get_agent_prompt("cpo_synthesis")

    # === 强制规则：必须尊重用户框架 ===
    framework_rule = (
        "\n\n## 输出规则（必须遵守）\n"
        "1. 如果用户在任务描述中给出了具体的功能框架、模块结构、Tab结构或一级功能列表，你必须以用户的框架为骨架展开，不能替换、不能重新归类、不能砍掉用户列出的模块。\n"
        "2. 你可以在用户框架基础上补充用户遗漏的功能，但必须标注为[补充]。\n"
        "3. 你可以对用户框架中某些功能提出优先级调整建议，但必须保留原始功能不删除。\n"
        "4. 如果用户要求'二级三级功能'，你必须在每个一级功能下展开至少3个二级功能，每个二级功能下展开至少2个三级功能。\n"
        "5. 不要替用户做'砍功能'的决策——用户列了社区/商城，你就按社区/商城展开，哪怕你觉得V1不需要。可以标注优先级P2/P3，但不能删。\n"
    )
    system_prompt += framework_rule

    # === 输出内容判断：区分内部决策和对外交付 ===
    output_rule = (
        "\n\n## 输出内容判断\n"
        "如果用户任务是面向外部交付的（给设计公司、给研发团队、给供应商），只输出最终结论，不输出内部决策过程。\n"
        "具体来说：\n"
        "- 不输出'共识'、'裁决'、'CTO核心要点'、'CMO核心要点'等内部讨论\n"
        "- 直接输出用户要求的格式（清单/表格/报告）\n"
        "- 内部决策过程可以保存到经验卡片，但不发给用户\n\n"
        "判断依据：如果任务描述中出现'用于给XX沟通'、'发给XX'、'交付给XX'等面向他人的表述，就按对外交付格式输出。\n"
    )
    system_prompt += output_rule

    # === 注入产品目标（整合时对齐） ===
    goal_file = ROOT_DIR / ".ai-state" / "product_goal.json"
    if goal_file.exists():
        try:
            goal_data = json.loads(goal_file.read_text(encoding="utf-8"))
            goal_text = goal_data.get("goal", "")
            if goal_text:
                system_prompt += f"\n\n## 产品目标（整合时对齐）\n{goal_text}\n"
        except:
            pass

    # === 检测用户指定的输出格式 ===
    task_goal = state.get("task_contract", {}).get("task_goal", "")
    format_hint = ""
    needs_structured_json = False  # 标记是否需要结构化 JSON 输出

    # 检测是否需要结构化输出（清单/表格/excel）
    structured_keywords = ["清单", "表格", "excel", "Excel", "PRD", "列表"]
    if any(kw in task_goal for kw in structured_keywords):
        needs_structured_json = True

        # === 关键改动：完全替换 prompt，不是追加 ===
        structured_system = (
            "你是智能摩托车全盔项目的 CPO。你必须输出一个 JSON 数组，不要输出任何其他内容。\n"
            "不要输出 markdown、不要输出解释文字、不要输出表格、不要输出标题。\n"
            "只输出一个以 [ 开头、以 ] 结尾的 JSON 数组。\n\n"
            "每个元素格式：\n"
            '{"module":"模块名","level":"L1或L2或L3","parent":"父功能名(L1填空字符串)","name":"功能名称","priority":"P0或P1或P2或P3","interaction":"交互方式(HUD/语音/按键/App/灯光)","description":"一句话描述","acceptance":"可测试的验收标准(含具体数字)","dependencies":"关联功能","note":"备注"}\n\n'
            "规则：\n"
            "1. 如果用户给了功能框架，以用户的一级功能作为 L1，不能重新归类\n"
            "2. 每个 L1 下至少 3 个 L2，每个 L2 至少 2 个 L3\n"
            "3. 用户列出的所有功能必须出现，不能删除\n"
            "4. 优先级统一用 P0/P1/P2/P3\n"
            "5. 验收标准必须可测试（含数字，如'成功率≥95%'、'响应时间≤3秒'）\n"
            "6. 你补充的功能在 note 中标注[补充]\n"
            "7. 合并三个 Agent 的分析，去重后统一输出，不暴露内部讨论\n"
        )

        structured_user = (
            f"以下是三个 Agent 的分析结果，请合并去重后输出 JSON 数组。\n\n"
            f"用户原始需求：\n{task_goal}\n\n"
            f"Agent 分析：\n{merge_summary[:12000]}\n\n"
            f"只输出 JSON 数组，不要有任何其他文字。以 [ 开头，以 ] 结尾。"
        )

        # 使用更高的 max_tokens 确保完整输出
        result = gateway.call_azure_openai("cpo", structured_user, structured_system, "synthesis", max_tokens=16384)

        if result.get("success"):
            synthesis = result["response"]
            # 确保输出是 JSON
            import re
            json_match = re.search(r'\[[\s\S]*\]', synthesis)
            if json_match:
                synthesis = json_match.group()  # 只保留 JSON 部分
                print(f"[CPO_Synthesis] 结构化 JSON 输出: {len(synthesis)} 字")
            else:
                print(f"[CPO_Synthesis] 警告：未检测到 JSON 数组，输出前100字符: {synthesis[:100]}")
        else:
            # 降级到普通整合
            synthesis = merge_summary
            print(f"[CPO_Synthesis] 结构化调用失败，降级到普通整合")
    else:
        # 非清单类任务，走原有整合逻辑
        # 其他格式的提示
        format_keywords = {
            "思维导图": "请以层级缩进格式输出（适合导入思维导图工具）：\n一级：模块名\n  二级：功能名\n    三级：子功能/描述",
            "prd": "请按 PRD 标准格式输出：功能编号、功能名称、用户故事、验收标准、优先级、依赖项。",
        }
        for keyword, hint in format_keywords.items():
            if keyword in task_goal:
                format_hint = f"\n\n## 输出格式要求（用户明确指定）\n{hint}\n"
                system_prompt += format_hint
                break

        if format_hint:
            system_prompt += format_hint

        result = gateway.call_azure_openai("cpo", merge_summary[:8000], system_prompt, "synthesis")
        synthesis = result["response"] if result.get("success") else merge_summary
        print(f"[CPO_Synthesis] {'整合完成' if result.get('success') else '调用失败，保留原始'}，{len(synthesis)} 字")

    # === Agent 主动建议：不只回答问题，还要提出用户没想到的方向 ===
    proactive_advice = ""
    if result.get("success") and len(synthesis) > 500:
        task_goal = state.get("task_contract", {}).get("task_goal", "")

        advice_prompt = (
            f"你是智能摩托车全盔项目的产品 VP（CPO），刚刚完成了一个研发任务的整合。\n\n"
            f"## 用户的原始任务\n{task_goal}\n\n"
            f"## 你的整合结论（摘要）\n{synthesis[:2000]}\n\n"
            f"## 你的任务\n"
            f"基于这次研究的结论，作为合伙人级别的 CPO，你需要主动提出 2-3 条用户可能没想到但确实值得关注的建议。\n\n"
            f"要求：\n"
            f"1. 每条建议要具体可执行（不要泛泛而谈'建议深入研究'）\n"
            f"2. 至少一条是跨领域关联（例如：'这个方案的散热问题会影响电池寿命，建议同步评估'）\n"
            f"3. 如果发现知识库在某个方向信息不够，直接说'我今晚会自动补充 XXX 方面的研究'\n"
            f"4. 如果某个结论和之前的研究有矛盾，指出来\n"
            f"5. 控制在 200 字以内\n\n"
            f"输出格式：\n"
            f"💡 合伙人建议：\n"
            f"1. ...\n"
            f"2. ...\n"
            f"3. ..."
        )

        advice_result = gateway.call_azure_openai("cpo", advice_prompt,
            "你是产品VP，输出简洁的主动建议。", "proactive_advice")

        if advice_result.get("success"):
            proactive_advice = advice_result["response"].strip()
            print(f"[CPO_Synthesis] 主动建议: {len(proactive_advice)} 字")

    # 将主动建议附加到 synthesis 末尾
    if proactive_advice:
        synthesis = synthesis + "\n\n---\n" + proactive_advice

    # === 主动建议中的知识缺口 → 写入待研究队列 ===
    if proactive_advice and ("今晚" in proactive_advice or "补充" in proactive_advice or "研究" in proactive_advice):
        try:
            gap_file = ROOT_DIR / ".ai-state" / "auto_research_queue.json"
            existing = []
            if gap_file.exists():
                existing = json.loads(gap_file.read_text(encoding="utf-8"))

            existing.append({
                "source": "proactive_advice",
                "task_goal": task_goal[:100],
                "advice": proactive_advice[:500],
                "created": datetime.now().isoformat()
            })

            # 只保留最近 20 条
            gap_file.write_text(json.dumps(existing[-20:], ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"[CPO_Synthesis] 知识缺口已加入研究队列")
        except Exception as e:
            print(f"[CPO_Synthesis] 队列写入失败: {e}")

    # 不在 router 层清理，由飞书发送端处理
    # 确保 synthesis_output 保留完整内容

    # 始终覆盖，确保有输出
    return {"execution": {**execution, "synthesis_output": synthesis, "needs_structured_json": needs_structured_json}}


def memory_writer_node(state: AgentGlobalState) -> dict:
    """将任务产出持久化到本地磁盘，构建经验卡片（幂等）"""
    memory_dir = ROOT_DIR / ".ai-state" / "memory"
    memory_dir.mkdir(parents=True, exist_ok=True)
    metadata, execution = state.get("metadata", {}), state.get("execution", {})
    task_id = metadata.get("task_id", "unknown")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # 【幂等性检查】同一任务记忆已存在则跳过
    if list(memory_dir.glob(f"*_{task_id}.json")):
        print(f"[Memory] 任务 {task_id} 记忆已存在，跳过")
        return {}

    # 【保底】如果 synthesis_output 不存在，从 Agent 输出拼接
    synthesis_output = execution.get("synthesis_output", "")
    if not synthesis_output:
        parts = []
        cto_output = execution.get("cto_output", {})
        cmo_output = execution.get("cmo_output", {})
        cdo_output = execution.get("cdo_output", {})
        cto_text = cto_output.get("protocol_code") or cto_output.get("output") or ""
        cmo_text = cmo_output.get("market_strategy") or cmo_output.get("output") or ""
        cdo_text = cdo_output.get("design_proposal") or cdo_output.get("output") or ""
        if cto_text:
            parts.append(f"=== CTO 技术方案 ===\n{cto_text[:2000]}")
        if cmo_text:
            parts.append(f"=== CMO 市场策略 ===\n{cmo_text[:2000]}")
        if cdo_text:
            parts.append(f"=== CDO 设计方案 ===\n{cdo_text[:2000]}")
        if parts:
            synthesis_output = "\n\n---\n\n".join(parts)
            print(f"[Memory] 保底拼接 synthesis_output: {len(parts)} 个角色")

    record = {
        "task_id": task_id, "timestamp": timestamp,
        "task_goal": state.get("task_contract", {}).get("task_goal", ""),
        "roles_assigned": [t.get("target_role", "") for t in state.get("sub_tasks", {}).values()],
        "critic_rounds": state.get("control", {}).get("retry_counts", {}).get("cpo_plan", 1),
        "critic_decision": execution.get("critic_decision", ""),
        "synthesis_output": synthesis_output[:4000] if synthesis_output else "",
        "synthesis_conflicts": synthesis_output.count("矛盾") if synthesis_output else 0,
        "user_rating": None, "user_feedback": None, "knowledge_gaps": [], "new_knowledge": []
    }
    filepath = memory_dir / f"{timestamp}_{task_id}.json"
    filepath.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[Memory] 已保存经验卡片: {filepath.name}")

    # 检查是否触发自进化复盘
    try:
        card_count = len(list(memory_dir.glob("*.json")))
        from scripts.self_evolution import check_and_trigger
        if check_and_trigger(card_count):
            print(f"[Evolution] 已积累 {card_count} 个经验卡片，触发自动复盘")
            import threading
            from scripts.self_evolution import run_review
            threading.Thread(target=run_review, daemon=True).start()
    except Exception as e:
        print(f"[Evolution] 触发检查失败: {e}")

    return {}


def consensus_log_trigger(state: AgentGlobalState): return state


# ==========================================
# 2. 核心流转与并行路由控制 (Conditional Edges)
# ==========================================
MAX_TOTAL_ITERATIONS = 3  # 全局硬限制：最多 3 轮 CPO规划→Agent→整合→Critic

def critic_router_v2(state: AgentGlobalState) -> Literal["memory_writer", "hitl_handler", "cpo_plan"]:
    """评审后路由：PASS→记忆写入，REJECT→重新规划，超限→强制输出

    流程位置：state_merge 之后
    全局兜底：MAX_TOTAL_ITERATIONS 次后强制 PASS
    """
    decision = state.get("execution", {}).get("critic_decision", "PASS")
    retry_count = state.get("control", {}).get("retry_counts", {}).get("cpo_plan", 0)
    total_iterations = state.get("control", {}).get("total_iterations", 0) + 1
    print(f"[Critic_Router] decision={decision}, retry_count={retry_count}, total_iterations={total_iterations}")

    # 【全局兜底】超过全局限制，强制输出
    if total_iterations >= MAX_TOTAL_ITERATIONS:
        print(f"[Critic_Router] 达到全局上限 {total_iterations} 轮，强制输出")
        # 保底：确保 synthesis_output 有内容
        _ensure_synthesis_output(state)
        return "memory_writer"

    # 更新全局计数器
    if decision == "PASS":
        return "memory_writer"
    elif retry_count >= 2:
        # 超过重试次数，强制 PASS 并走 memory_writer
        print(f"[Critic_Router] 重试超限，强制 PASS 并保存")
        _ensure_synthesis_output(state)
        return "memory_writer"
    else:
        # 返回重新规划前，更新总迭代计数
        # 注意：这里不能直接修改 state，需要在 cpo_plan_node 中处理
        return "cpo_plan"


def _ensure_synthesis_output(state: AgentGlobalState) -> str:
    """检查 synthesis_output 是否存在，返回保底内容（不修改 state）"""
    execution = state.get("execution", {})
    if execution.get("synthesis_output"):
        return ""

    parts = []
    cto_output = execution.get("cto_output", {})
    cmo_output = execution.get("cmo_output", {})
    cdo_output = execution.get("cdo_output", {})

    cto_text = cto_output.get("protocol_code") or cto_output.get("output") or ""
    cmo_text = cmo_output.get("market_strategy") or cmo_output.get("output") or ""
    cdo_text = cdo_output.get("design_proposal") or cdo_output.get("output") or ""

    if cto_text:
        parts.append(f"=== CTO 技术方案 ===\n{cto_text[:2000]}")
    if cmo_text:
        parts.append(f"=== CMO 市场策略 ===\n{cmo_text[:2000]}")
    if cdo_text:
        parts.append(f"=== CDO 设计方案 ===\n{cdo_text[:2000]}")

    if parts:
        fallback = "\n\n---\n\n".join(parts)
        print(f"[Critic_Router] 需要保底内容: {len(parts)} 个角色")
        return fallback
    return ""


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
        # 【修复】传递完整状态，确保 CTO/CMO/CDO 节点能访问 task_contract 和 sub_tasks
        branch_state = {**state, "current_task_id": task_id}
        if role == "cto":
            sends.append(Send("cto_coder", branch_state))
        elif role == "cmo":
            sends.append(Send("cmo_strategist", branch_state))
        elif role == "cdo":
            sends.append(Send("cdo_designer", branch_state))
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
workflow.add_node("cdo_designer", cdo_designer_node)
workflow.add_node("state_merge", state_merge)
workflow.add_node("cpo_synthesis", cpo_synthesis)
workflow.add_node("memory_writer", memory_writer_node)
workflow.add_node("consensus_log_trigger", consensus_log_trigger)
workflow.add_node("hitl_handler", hitl_handler)

# --- 连线拓扑 ---
workflow.set_entry_point("hash_check")
workflow.add_edge("hash_check", "doc_code_sync_check")  # 哈希检查后，进入文档同步检查
workflow.add_edge("doc_code_sync_check", "cpo_plan")  # 文档没问题，才允许 CPO 规划

# 【修改】CPO 规划后直接进入原型决策，不再先评审
workflow.add_edge("cpo_plan", "prototype_decision_node")

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

workflow.add_edge("cdo_designer", "state_merge")

# 【修改】state_merge 后进入 CPO 整合，整合后进入评审
workflow.add_edge("state_merge", "cpo_synthesis")
workflow.add_edge("cpo_synthesis", "cpo_critic")
workflow.add_conditional_edges("cpo_critic", critic_router_v2)

workflow.add_edge("memory_writer", "consensus_log_trigger")
workflow.add_edge("consensus_log_trigger", END)
workflow.add_edge("hitl_handler", END)  # 修复：HITL 处理后结束流程

if HAS_CHECKPOINT and _checkpointer:
    app = workflow.compile(checkpointer=_checkpointer)
    print("[LangGraph] 编译完成（带 checkpoint）")
else:
    app = workflow.compile()
    print("[LangGraph] 编译完成（无 checkpoint）")