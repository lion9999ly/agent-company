"""
深度研究 — 认知闭环（深度学习后自动执行）
职责: 评估本轮研究对决策树的贡献、发现数据缺口、追加下一轮任务、推送飞书
被调用方: runner.py（run_deep_learning 收尾阶段）
依赖: models.py
"""
import json
import re
import time
import yaml
from pathlib import Path
from typing import List, Optional

from scripts.deep_research.models import call_model

AI_STATE = Path(__file__).resolve().parent.parent.parent / ".ai-state"
TASK_POOL_PATH = AI_STATE / "research_task_pool.yaml"
DECISION_TREE_PATH = AI_STATE / "product_decision_tree.yaml"
REPORT_DIR = AI_STATE / "reports"
REVIEW_LOG_PATH = AI_STATE / "post_learning_reviews.jsonl"


def run_post_learning_review(completed_tasks: list,
                              progress_callback=None) -> dict:
    """深度学习完成后的认知闭环

    输入: completed_tasks — runner.py 返回的任务完成列表
    输出: {"decisions_ready": [...], "next_priorities": [...], "gaps": [...]}
    """
    if not completed_tasks:
        return {}

    print(f"\n  [PostReview] 开始认知闭环，评估 {len(completed_tasks)} 个任务...")

    # 1. 收集本轮报告摘要
    report_summaries = _collect_report_summaries(completed_tasks)

    # 2. 读取决策树当前状态
    decision_tree_status = _get_decision_tree_status()

    # 3. 读取待决策清单（来自 product_anchor）
    pending_decisions = _get_pending_decisions()

    # 4. 构建结构化 prompt（约束式判断题，不是开放对话）
    review_prompt = (
        f"你是智能骑行头盔项目的研究总监。以下是本轮深度学习的成果，"
        f"请判断这些研究对决策推进的贡献。\n\n"
        f"## 本轮完成的研究\n{report_summaries}\n\n"
        f"## 决策树当前状态\n{decision_tree_status}\n\n"
        f"## 待决策清单\n{pending_decisions}\n\n"
        f"请严格按以下 JSON 格式回答：\n"
        f"{{\n"
        f'  "decisions_ready": [\n'
        f'    {{"decision_id": "v1_xxx", "reason": "数据已充分的理由（一句话）"}}\n'
        f"  ],\n"
        f'  "decisions_almost_ready": [\n'
        f'    {{"decision_id": "v1_xxx", "missing": "还缺什么（具体一条）",\n'
        f'     "suggested_research": "建议的研究课题"}}\n'
        f"  ],\n"
        f'  "key_findings_for_founder": [\n'
        f'    "需要创始人注意的关键发现（最多3条，每条一句话）"\n'
        f"  ],\n"
        f'  "next_priority_tasks": [\n'
        f'    {{"title": "下一轮应该优先研究的课题",\n'
        f'     "goal": "研究目标", "priority": 1,\n'
        f'     "searches": ["搜索词1", "搜索词2"]}}\n'
        f"  ]\n"
        f"}}\n\n"
        f"规则：\n"
        f"1. decisions_ready: 只有当该决策的所有 blocking_knowledge 都被研究覆盖时才列入\n"
        f"2. key_findings_for_founder: 只写会影响决策方向的重大发现，不写泛泛总结\n"
        f"3. next_priority_tasks: 优先填补 decisions_almost_ready 的缺口\n"
        f"4. 只输出 JSON，不要其他内容\n"
    )

    result = call_model("glm_4_7", review_prompt,
                        "你是研究总监，严格按 JSON 格式回答。",
                        "post_learning_review")

    if not result.get("success"):
        print(f"  [PostReview] GLM 调用失败: {result.get('error', '')[:100]}")
        return {}

    # 解析结果
    try:
        resp = result["response"].strip()
        resp = re.sub(r'^```json\s*', '', resp)
        resp = re.sub(r'\s*```$', '', resp)
        review = json.loads(resp)
    except Exception as e:
        print(f"  [PostReview] 解析失败: {e}")
        return {}

    # 5. 执行结果
    _apply_review_results(review, progress_callback)

    # 6. 记录日志
    _log_review(review, completed_tasks)

    return review


def _collect_report_summaries(completed_tasks: list) -> str:
    """从已完成任务中收集报告摘要"""
    summaries = []
    for task in completed_tasks[:10]:
        title = task.get("title", "")
        report_len = task.get("report_len", 0)

        # 尝试从报告文件中读取前 500 字
        excerpt = ""
        if REPORT_DIR.exists():
            for f in sorted(REPORT_DIR.glob("*.md"), reverse=True):
                if title[:15] in f.stem or title[:15] in f.read_text(encoding="utf-8")[:200]:
                    content = f.read_text(encoding="utf-8")
                    excerpt = content[:500]
                    break

        summaries.append(
            f"- **{title}** ({report_len}字)\n"
            f"  摘要: {excerpt[:300]}..." if excerpt else
            f"- **{title}** ({report_len}字)"
        )

    return "\n".join(summaries)


def _get_decision_tree_status() -> str:
    """读取决策树并格式化为状态文本"""
    if not DECISION_TREE_PATH.exists():
        return "决策树文件不存在"

    try:
        with open(DECISION_TREE_PATH, 'r', encoding='utf-8') as f:
            tree = yaml.safe_load(f)

        lines = []
        for d in tree.get("decisions", []):
            resolved = d.get("resolved_knowledge", 0)
            needed = d.get("total_needed", 3)
            question = d.get("question", "")
            blocking = d.get("blocking_knowledge", [])
            status = "就绪" if resolved >= needed else f"进度 {resolved}/{needed}"

            lines.append(f"- [{d.get('id', '?')}] {question[:50]} — {status}")
            if blocking and resolved < needed:
                for b in blocking[:3]:
                    lines.append(f"    缺: {b}")

        return "\n".join(lines) if lines else "决策树为空"
    except Exception as e:
        return f"决策树读取失败: {e}"


def _get_pending_decisions() -> str:
    """从 product_anchor 读取待决策清单"""
    anchor_path = AI_STATE / "product_anchor.md"
    if not anchor_path.exists():
        return "无 product_anchor.md"

    content = anchor_path.read_text(encoding="utf-8")

    # 提取"未决决策"部分
    match = re.search(r'##\s*未决决策\s*\n([\s\S]*?)(?=\n##|\Z)', content)
    if match:
        return match.group(1).strip()

    return "未找到未决决策章节"


def _apply_review_results(review: dict, progress_callback=None):
    """执行认知闭环的结果"""

    # A: 更新决策树的 resolved 状态
    decisions_ready = review.get("decisions_ready", [])
    if decisions_ready and DECISION_TREE_PATH.exists():
        try:
            with open(DECISION_TREE_PATH, 'r', encoding='utf-8') as f:
                tree = yaml.safe_load(f)
            for dr in decisions_ready:
                did = dr.get("decision_id", "")
                for d in tree.get("decisions", []):
                    if d.get("id") == did:
                        d["resolved_knowledge"] = d.get("total_needed", 3)
                        d["ready_at"] = time.strftime('%Y-%m-%d %H:%M')
                        print(f"  [PostReview] 决策 {did} 标记为就绪")
            with open(DECISION_TREE_PATH, 'w', encoding='utf-8') as f:
                yaml.dump(tree, f, allow_unicode=True, default_flow_style=False)
        except Exception as e:
            print(f"  [PostReview] 更新决策树失败: {e}")

    # B: 追加下一轮任务到任务池
    next_tasks = review.get("next_priority_tasks", [])
    if next_tasks:
        try:
            existing_pool = []
            if TASK_POOL_PATH.exists():
                with open(TASK_POOL_PATH, 'r', encoding='utf-8') as f:
                    existing_pool = yaml.safe_load(f) or []

            for task in next_tasks:
                task["id"] = f"review_{int(time.time())}_{task.get('priority', 9)}"
                task["source"] = "post_learning_review"
                task["discovered_at"] = time.strftime('%Y-%m-%d %H:%M')
                # 确保 searches 是 list
                if not isinstance(task.get("searches"), list):
                    task["searches"] = [task.get("title", "unknown") + " 2026"]
                existing_pool.append(task)
                print(f"  [PostReview] 追加任务: {task.get('title', '')}")

            with open(TASK_POOL_PATH, 'w', encoding='utf-8') as f:
                yaml.dump(existing_pool, f, allow_unicode=True)
        except Exception as e:
            print(f"  [PostReview] 追加任务失败: {e}")

    # C: 推送飞书通知
    if progress_callback:
        msg_parts = ["🧠 认知闭环完成"]

        if decisions_ready:
            msg_parts.append(f"\n✅ 以下决策数据已充分，可以做决定了:")
            for dr in decisions_ready:
                msg_parts.append(f"  • {dr.get('decision_id', '')}: {dr.get('reason', '')}")

        almost_ready = review.get("decisions_almost_ready", [])
        if almost_ready:
            msg_parts.append(f"\n🔜 以下决策接近就绪，还差:")
            for ar in almost_ready:
                msg_parts.append(
                    f"  • {ar.get('decision_id', '')}: 缺 {ar.get('missing', '')}"
                )

        findings = review.get("key_findings_for_founder", [])
        if findings:
            msg_parts.append(f"\n💡 需要你关注的发现:")
            for f in findings[:3]:
                msg_parts.append(f"  • {f}")

        if next_tasks:
            msg_parts.append(f"\n📋 已自动追加 {len(next_tasks)} 个研究任务到下一轮")

        progress_callback("\n".join(msg_parts))


def _log_review(review: dict, completed_tasks: list):
    """记录认知闭环日志"""
    entry = {
        "timestamp": time.strftime('%Y-%m-%d %H:%M'),
        "tasks_reviewed": len(completed_tasks),
        "decisions_ready": len(review.get("decisions_ready", [])),
        "decisions_almost": len(review.get("decisions_almost_ready", [])),
        "next_tasks_added": len(review.get("next_priority_tasks", [])),
        "key_findings": review.get("key_findings_for_founder", []),
    }

    REVIEW_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REVIEW_LOG_PATH, 'a', encoding='utf-8') as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    print(f"  [PostReview] 日志已记录")
