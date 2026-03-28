"""
@description: 飞书精确指令处理 - 评价/目标/进化/审批/学习触发
@refactored_from: feishu_sdk_client.py
@last_modified: 2026-03-28
"""
import json
import threading
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# 记录最近一次研发任务的 ID 和经验卡片路径，用于关联用户评价
_last_task_memory = {"task_id": None, "memory_dir": None}


def set_last_task_memory(task_id: str, memory_dir: str):
    """设置最近任务记忆"""
    _last_task_memory["task_id"] = task_id
    _last_task_memory["memory_dir"] = memory_dir


def handle_command(text: str, reply_target: str, reply_type: str, open_id: str, chat_id: str, send_reply) -> bool:
    """
    处理精确指令。返回 True 表示已处理，False 表示不是精确指令。

    支持的指令：
    - A/B/C/D 评价
    - 设置目标 XXX
    - 进化记录
    - 审批 fix_XXX
    - 触发学习
    - 知识库统计
    - 系统状态
    """
    text_stripped = text.strip()
    text_lower = text_stripped.lower()

    # === 评价处理 ===
    if _handle_rating(text_stripped, reply_target, send_reply):
        return True

    # === 审批处理 ===
    if _handle_fix_command(text_stripped, reply_target, send_reply):
        return True

    # === 设置目标 ===
    if text_stripped.startswith("设置目标"):
        _handle_set_goal(text_stripped, reply_target, reply_type, send_reply)
        return True

    # === 进化记录 ===
    if text_stripped in ("进化记录", "evolution", "进化"):
        _handle_evolution_log(reply_target, send_reply)
        return True

    # === 知识库统计 ===
    if text_stripped in ("知识库统计", "kb stats", "统计"):
        _handle_kb_stats(reply_target, send_reply)
        return True

    # === 系统状态 ===
    if text_stripped in ("系统状态", "status", "状态"):
        _handle_system_status(reply_target, send_reply)
        return True

    # === 热更新：重载模块 ===
    if text_stripped in ("重载模块", "reload", "热更新"):
        _handle_reload_modules(reply_target, reply_type, send_reply)
        return True

    # 不是精确指令
    return False


def _handle_rating(text: str, reply_target: str, send_reply) -> bool:
    """处理用户评价"""
    rating_map = {"a": "A", "b": "B", "c": "C", "d": "D",
                  "A": "A", "B": "B", "C": "C", "D": "D"}

    first_char = text[0] if text else ""
    if first_char not in rating_map:
        return False

    # 必须是单字母 或 字母+空格+理由
    if len(text) > 1 and not text[1].isspace() and text[1] not in "。，、，.":
        # 不是评价，比如 "AR1和AR2"
        return False

    rating = rating_map[first_char]
    feedback = text[1:].strip().lstrip(".").lstrip("。").lstrip("、").lstrip(",").strip() if len(text) > 1 else ""

    if not _last_task_memory.get("memory_dir"):
        send_reply(reply_target, f"📝 收到评价 {rating}，但没有找到最近的任务记录")
        return True

    memory_dir = Path(_last_task_memory["memory_dir"])
    if not memory_dir.exists():
        send_reply(reply_target, f"📝 收到评价 {rating}，记忆目录不存在")
        return True

    # 找到最近的经验卡片
    files = sorted(memory_dir.glob("*.json"), reverse=True)
    if not files:
        send_reply(reply_target, f"📝 收到评价 {rating}，但没有经验卡片")
        return True

    latest = files[0]
    try:
        data = json.loads(latest.read_text(encoding="utf-8"))
        data["user_rating"] = rating
        if feedback:
            data["user_feedback"] = feedback
        latest.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

        rating_labels = {"A": "可直接使用", "B": "需要小改", "C": "方向对但不够深", "D": "方向有问题"}
        msg = f"📝 评价已记录：{rating} ({rating_labels.get(rating, '')})"
        if feedback:
            msg += f"\n反馈：{feedback}"
        send_reply(reply_target, msg)

        # 评价驱动进化（后台线程）
        if rating in ("C", "D"):
            threading.Thread(target=_analyze_failure, args=(data, feedback, rating), daemon=True).start()
        elif rating == "A":
            threading.Thread(target=_analyze_success, args=(data,), daemon=True).start()

    except Exception as e:
        send_reply(reply_target, f"📝 评价记录失败：{e}")

    return True


def _handle_fix_command(text: str, reply_target: str, send_reply) -> bool:
    """处理修复审批指令"""
    try:
        from src.tools.fix_executor import get_pending_proposals, approve_and_execute, reject_proposal, format_proposal_for_feishu
    except ImportError:
        return False

    text_lower = text.strip().lower()

    if text_lower.startswith("批准 fix_") or text_lower.startswith("approve fix_"):
        fix_id = text_lower.split()[-1]
        result = approve_and_execute(fix_id)
        if result["success"]:
            send_reply(reply_target, f"✅ 修复 {fix_id} 已执行\n文件: {result['file']}")
        else:
            send_reply(reply_target, f"❌ 执行失败: {result['error']}")
        return True

    elif text_lower.startswith("驳回 fix_") or text_lower.startswith("reject fix_"):
        parts = text_lower.split(maxsplit=2)
        fix_id = parts[1] if len(parts) > 1 else ""
        reason = parts[2] if len(parts) > 2 else ""
        result = reject_proposal(fix_id, reason)
        if result["success"]:
            send_reply(reply_target, f"🚫 修复 {fix_id} 已驳回")
        else:
            send_reply(reply_target, f"❌ 驳回失败: {result['error']}")
        return True

    elif text_lower in ("待审批", "pending", "审批列表"):
        proposals = get_pending_proposals()
        if not proposals:
            send_reply(reply_target, "📋 当前无待审批的修复提案")
        else:
            for p in proposals:
                send_reply(reply_target, format_proposal_for_feishu(p))
        return True

    return False


def _handle_set_goal(text: str, reply_target: str, reply_type: str, send_reply):
    """处理设置目标指令"""
    goal_content = text.replace("设置目标", "").strip()
    if len(goal_content) < 20:
        send_reply(reply_target, "请提供更详细的目标描述，至少 20 字。例如：\n设置目标 V1 目标2026年Q4量产，核心卖点HUD导航+4K黑匣子+SOS，面向高端摩旅用户，定价5000-8000元")
        return

    goal_file = PROJECT_ROOT / ".ai-state" / "product_goal.json"
    from datetime import datetime
    goal_data = {
        "goal": goal_content,
        "updated_at": datetime.now().isoformat(),
        "updated_by": "feishu_command"
    }
    try:
        import json
        goal_file.parent.mkdir(parents=True, exist_ok=True)
        goal_file.write_text(json.dumps(goal_data, ensure_ascii=False, indent=2), encoding="utf-8")
        send_reply(reply_target, f"✅ 产品目标已更新：\n{goal_content}")
    except Exception as e:
        send_reply(reply_target, f"❌ 设置失败：{e}")


def _handle_evolution_log(reply_target: str, send_reply):
    """处理进化记录查询"""
    evolution_dir = PROJECT_ROOT / ".ai-state" / "evolution"
    if not evolution_dir.exists():
        send_reply(reply_target, "📊 暂无进化记录。给研发任务打 A 或 D 评价后，系统会自动分析并记录。")
        return

    files = sorted(evolution_dir.glob("*.json"), reverse=True)[:10]
    if not files:
        send_reply(reply_target, "📊 暂无进化记录。")
        return

    lines = ["📊 Agent 进化记录\n"]
    for f in files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            ts = data.get("timestamp", "")[:10]
            goal = data.get("task_goal", "")[:40]
            rating = data.get("user_rating", "?")
            typ = "教训" if rating in ("C", "D") else "成功"
            lines.append(f"- [{ts}] [{typ}] {goal}... (评价:{rating})")
        except:
            continue

    send_reply(reply_target, "\n".join(lines))


def _handle_kb_stats(reply_target: str, send_reply):
    """处理知识库统计"""
    try:
        from src.tools.knowledge_base import get_knowledge_stats
        stats = get_knowledge_stats()
        total = sum(stats.values())
        msg = f"📊 知识库统计\n总数: {total} 条\n\n"
        for domain, count in stats.items():
            msg += f"- {domain}: {count} 条\n"
        send_reply(reply_target, msg)
    except Exception as e:
        send_reply(reply_target, f"❌ 获取统计失败: {e}")


def _handle_system_status(reply_target: str, send_reply):
    """处理系统状态查询"""
    import threading
    try:
        from src.tools.knowledge_base import get_knowledge_stats
        stats = get_knowledge_stats()
        total = sum(stats.values())
    except:
        stats = {}
        total = 0

    msg = (
        f"📊 系统状态\n"
        f"- 知识库: {total} 条\n"
        f"- 活跃线程: {threading.active_count()}\n"
        f"- 最近任务: {_last_task_memory.get('task_id', '无')}\n"
    )
    send_reply(reply_target, msg)


def _handle_reload_modules(reply_target: str, reply_type: str, send_reply):
    """处理模块热更新"""
    import importlib
    import scripts.feishu_handlers.chat_helpers as _m1
    import scripts.feishu_handlers.file_sender as _m2
    import scripts.feishu_handlers.commands as _m3
    import scripts.feishu_handlers.image_handler as _m4
    import scripts.feishu_handlers.rd_task as _m5
    import scripts.feishu_handlers.text_router as _m6
    import scripts.feishu_handlers.structured_doc as _m7

    errors = []
    modules = [
        ("chat_helpers", _m1),
        ("file_sender", _m2),
        ("commands", _m3),
        ("image_handler", _m4),
        ("rd_task", _m5),
        ("text_router", _m6),
        ("structured_doc", _m7),
    ]

    for name, mod in modules:
        try:
            importlib.reload(mod)
            print(f"  [OK] reload {name}")
        except Exception as e:
            errors.append(f"{name}: {e}")
            print(f"  [X] reload {name}: {e}")

    if errors:
        send_reply(reply_target, f"模块重载完成，{len(errors)} 个失败:\n" + "\n".join(errors))
    else:
        send_reply(reply_target, f"7 个模块全部重载成功，无需重启服务")


def _analyze_failure(data: dict, feedback: str, rating: str):
    """分析失败原因（后台线程）"""
    print(f"[Evolution] _analyze_failure 线程已启动")
    try:
        from src.utils.model_gateway import get_model_gateway
        from src.tools.knowledge_base import add_knowledge

        gw = get_model_gateway()
        task_goal = data.get("task_goal", "")
        synthesis = data.get("synthesis_output", "")
        user_feedback = feedback if feedback else f"用户评价{rating}"

        analysis_prompt = (
            f"一个研发任务收到了差评（{rating}）。请分析失败原因并提取教训。\n\n"
            f"## 任务目标\n{task_goal}\n\n"
            f"## Agent 输出（摘要）\n{synthesis[:2000]}\n\n"
            f"## 用户反馈\n{user_feedback}\n\n"
            f"请输出：\n1. 失败根因（一句话）\n2. Agent 哪个环节出了问题\n3. 下次遇到类似任务应该怎么做\n"
        )

        result = gw.call_azure_openai("cpo", analysis_prompt, "简洁输出，不超过 500 字。", "evolution")
        if result.get("success"):
            lesson = result["response"]
            add_knowledge(
                title=f"[教训] {task_goal[:40]}（评价{rating}）",
                domain="lessons",
                content=lesson,
                tags=["evolution", "failure", f"rating_{rating}"],
                source="evolution",
                confidence="medium"
            )
            print(f"[Evolution] 教训已入库")
    except Exception as e:
        print(f"[Evolution] 分析失败: {e}")


def _analyze_success(data: dict):
    """分析成功模式（后台线程）"""
    print(f"[Evolution] _analyze_success 线程已启动")
    try:
        from src.utils.model_gateway import get_model_gateway
        from src.tools.knowledge_base import add_knowledge

        gw = get_model_gateway()
        task_goal = data.get("task_goal", "")
        synthesis = data.get("synthesis_output", "")

        analysis_prompt = (
            f"一个研发任务收到了满分评价（A）。请提取成功模式。\n\n"
            f"## 任务目标\n{task_goal}\n\n"
            f"## Agent 输出（摘要）\n{synthesis[:2000]}\n\n"
            f"请输出：\n1. 成功关键因素\n2. 哪些做法值得保持\n3. 可以复用到其他任务的点\n"
        )

        result = gw.call_azure_openai("cpo", analysis_prompt, "简洁输出，不超过 500 字。", "evolution")
        if result.get("success"):
            pattern = result["response"]
            add_knowledge(
                title=f"[成功模式] {task_goal[:40]}",
                domain="lessons",
                content=pattern,
                tags=["evolution", "success", "rating_A"],
                source="evolution",
                confidence="high"
            )
            print(f"[Evolution] 成功模式已入库")
    except Exception as e:
        print(f"[Evolution] 分析失败: {e}")


# === 导出接口 ===
__all__ = [
    "handle_command",
    "set_last_task_memory",
    "_last_task_memory",
]