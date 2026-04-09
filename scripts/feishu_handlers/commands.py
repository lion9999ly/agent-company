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

    # === Token 统计 ===
    if text_lower in ("token", "tokens", "用量", "token统计", "api用量", "api统计"):
        _handle_token_stats(reply_target, send_reply)
        return True

    # === 日志查看 ===
    if text_lower in ("日志", "最近日志", "log", "logs", "运行日志"):
        _handle_view_logs(reply_target, send_reply)
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

        # 输出格式学习（后台线程）
        threading.Thread(target=_learn_output_preferences, args=(rating, feedback, data), daemon=True).start()

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


def _handle_view_logs(reply_target: str, send_reply):
    """处理日志查看"""
    log_file = PROJECT_ROOT / ".ai-state" / "feishu_debug.log"

    if not log_file.exists():
        send_reply(reply_target, "📝 暂无日志文件")
        return

    try:
        content = log_file.read_text(encoding='utf-8')
        lines = content.strip().split('\n')

        if not lines:
            send_reply(reply_target, "📝 日志文件为空")
            return

        # 取最后 50 行
        recent_lines = lines[-50:] if len(lines) > 50 else lines
        log_text = '\n'.join(recent_lines)

        # 飞书单条消息限制约 4000 字符，截取最后 2000
        if len(log_text) > 2000:
            log_text = log_text[-2000:]
            log_text = "...(已截取最后2000字符)\n" + log_text

        # 添加标题
        msg = f"📋 最近运行日志\n（共 {len(lines)} 行，显示最后 {len(recent_lines)} 行）\n\n{log_text}"
        send_reply(reply_target, msg)

    except Exception as e:
        send_reply(reply_target, f"❌ 读取日志失败: {e}")


def _handle_token_stats(reply_target: str, send_reply):
    """处理 Token 统计"""
    try:
        from src.utils.token_usage_tracker import get_tracker
        tracker = get_tracker()

        # 获取最近 7 天统计
        stats = tracker.get_stats(days=7)

        # 构建报告
        lines = ["💰 API Token 使用统计\n"]

        # 总体统计
        lines.append(f"**统计周期**: {stats['period']} ({stats['start_date']} ~ {stats['end_date']})")
        lines.append(f"**总调用**: {stats['total_calls']} 次 (成功 {stats['success_calls']}, 失败 {stats['failed_calls']})")
        lines.append(f"**总Token**: {stats['total_tokens']:,}")
        lines.append(f"**估算成本**: ${stats['total_cost']:.4f}")
        lines.append("")

        # 模型排名（前 10）
        model_ranking = tracker.get_model_ranking(days=7)
        if model_ranking:
            lines.append("**模型使用排名**:")
            for i, m in enumerate(model_ranking[:10], 1):
                lines.append(f"  {i}. {m['model']}: {m['calls']} 次, {m['tokens']:,} tokens, ${m['cost']:.4f}")
            lines.append("")

        # 今日统计
        today_stats = tracker.get_today_stats()
        if today_stats['total_calls'] > 0:
            lines.append("**今日统计**:")
            lines.append(f"  调用: {today_stats['total_calls']} 次")
            lines.append(f"  Token: {today_stats['total_tokens']:,}")
            lines.append(f"  成本: ${today_stats['total_cost']:.4f}")

        send_reply(reply_target, "\n".join(lines))

    except Exception as e:
        import traceback
        print(f"[TokenStats] Error: {traceback.format_exc()}")
        send_reply(reply_target, f"❌ Token统计失败: {e}")


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


def _learn_output_preferences(rating: str, feedback: str, task_data: dict):
    """从用户评价中学习输出格式偏好"""
    print(f"[OutputLearning] 分析评价偏好: {rating}")
    try:
        import yaml as _yaml
        from datetime import datetime

        prefs_file = PROJECT_ROOT / ".ai-state" / "output_preferences.yaml"

        # 加载现有偏好
        prefs = {"report": {}, "learnings": []}
        if prefs_file.exists():
            try:
                prefs = _yaml.safe_load(prefs_file.read_text(encoding='utf-8')) or prefs
            except:
                pass

        # 从反馈中提取偏好线索
        synthesis = task_data.get("synthesis_output", "")
        synthesis_len = len(synthesis) if synthesis else 0

        # 根据评价推断偏好
        learning = {
            "rating": rating,
            "feedback": feedback[:100] if feedback else "",
            "output_length": synthesis_len,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }

        # 从反馈文本中提取偏好信号
        if feedback:
            fb_lower = feedback.lower()
            if "太长" in fb_lower or "冗余" in fb_lower:
                prefs["report"]["preferred_length"] = "short"
                learning["preference_signal"] = "prefers_shorter"
            elif "太短" in fb_lower or "不够详细" in fb_lower or "深入" in fb_lower:
                prefs["report"]["preferred_length"] = "long"
                learning["preference_signal"] = "prefers_longer"
            elif "数据" in fb_lower or "具体" in fb_lower:
                prefs["report"]["data_density"] = "high"
                learning["preference_signal"] = "wants_more_data"
            elif "结论" in fb_lower or "先说" in fb_lower:
                prefs["report"]["structure"] = "conclusion_first"
                learning["preference_signal"] = "wants_conclusion_first"

        # 根据评价级别推断
        if rating == "A" and synthesis_len > 0:
            # A 评价说明当前长度/格式可以接受
            prefs["report"]["good_length_example"] = synthesis_len
        elif rating in ("C", "D"):
            # 差评，记录问题
            prefs["report"]["last_bad_rating"] = rating
            if feedback:
                prefs.setdefault("avoid", []).append(feedback[:50])

        # 保存学习记录
        prefs.setdefault("learnings", []).append(learning)
        # 只保留最近 50 条学习记录
        if len(prefs.get("learnings", [])) > 50:
            prefs["learnings"] = prefs["learnings"][-50:]

        prefs_file.parent.mkdir(parents=True, exist_ok=True)
        prefs_file.write_text(_yaml.dump(prefs, allow_unicode=True), encoding='utf-8')
        print(f"[OutputLearning] 偏好已更新")
    except Exception as e:
        print(f"[OutputLearning] 学习失败: {e}")


# === 导出接口 ===
__all__ = [
    "handle_command",
    "set_last_task_memory",
    "_last_task_memory",
]