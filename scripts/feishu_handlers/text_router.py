"""
@description: 文本消息路由 - 精确指令 → 快速通道 → 意图识别 → R&D → 智能对话
@refactored_from: feishu_sdk_client.py
@last_modified: 2026-03-28
"""
import re
import json
import threading
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# 深度学习待确认状态：{open_id: True} 或 {open_id_confirmed: hours}
_deep_learn_pending = {}

# 教练模式状态：{open_id: True}
_coach_mode = {}

# 知识滴灌开关
_drip_enabled = True

# Demo 会话状态：{open_id: {"type": "hud", "html_path": "...", "design_spec": {...}, "version": 1}}
_demo_sessions = {}

# Demo 待确认问题：{open_id: {"question": "...", "options": [...], "callback": func}}
_demo_pending_questions = {}


def _safe_reply_error(send_reply, reply_target, task_name, error):
    """统一错误处理：记录详细日志，返回友好提示"""
    import traceback
    print(f"[ERROR] {task_name}: {traceback.format_exc()}")
    send_reply(reply_target, f"⚠️ {task_name} 遇到问题，已记录日志。请稍后重试。")


def _check_permission(open_id: str, required_role: str) -> bool:
    """检查用户权限"""
    roles_file = PROJECT_ROOT / ".ai-state" / "access_control.yaml"
    if not roles_file.exists():
        return True  # 无权限文件时默认允许

    try:
        import yaml as _yaml
        roles_data = _yaml.safe_load(roles_file.read_text(encoding='utf-8')) or {"roles": {}}
        user_role = roles_data.get("roles", {}).get(open_id or "default", {}).get("role", "viewer")

        role_hierarchy = {"viewer": 0, "member": 1, "manager": 2, "admin": 3}
        return role_hierarchy.get(user_role, 0) >= role_hierarchy.get(required_role, 0)
    except:
        return True


def _check_first_time_user(open_id: str, reply_target: str, send_reply):
    """检查是否首次用户，发送引导消息"""
    known_users_file = PROJECT_ROOT / ".ai-state" / "known_users.json"
    user_key = open_id or "default"

    try:
        known_users = {}
        if known_users_file.exists():
            known_users = json.loads(known_users_file.read_text(encoding='utf-8'))

        if user_key not in known_users:
            # 首次用户，发送引导
            known_users[user_key] = {"first_seen": datetime.now().strftime("%Y-%m-%d")}
            known_users_file.parent.mkdir(parents=True, exist_ok=True)
            known_users_file.write_text(json.dumps(known_users, ensure_ascii=False, indent=2), encoding='utf-8')

            # 发送引导消息
            send_reply(reply_target,
                "👋 欢迎使用智能骑行头盔研发助手！\n\n"
                "我可以帮你：\n"
                "• 竞品分析、技术方案、市场策略\n"
                "• 每日早报、决策简报、谈判准备\n"
                "• 深度学习（夜间批量研究）\n\n"
                "试试发送：帮助 或 早报"
            )
    except:
        pass


def route_text_message(text: str, reply_target: str, reply_type: str, open_id: str, chat_id: str,
                       send_reply, session_id: str = None, mem=None):
    """
    文本消息路由主入口。

    路由优先级（从高到低）：
    1. 精确指令（评价/设置目标/进化记录/审批等）
    2. 结构化文档快速通道（PRD/清单/表格）
    3. URL 分享处理
    4. 长文章导入知识库
    5. 研发任务（LangGraph 多 Agent）
    6. 意图识别 → 智能路由
    7. 兜底：智能对话（GPT 直连 + 知识库上下文）
    """
    from scripts.feishu_handlers.chat_helpers import log
    from scripts.feishu_handlers.commands import handle_command
    from scripts.feishu_handlers.rd_task import is_rd_task, run_rd_task_background, is_rd_task_running

    text_stripped = text.strip()
    text_upper = text_stripped.upper()

    log(f"text 路由, 长度={len(text)}")

    # === 0. 新手引导 ===
    _check_first_time_user(open_id, reply_target, send_reply)

    # === 1. 精确指令 ===
    if handle_command(text_stripped, reply_target, reply_type, open_id, chat_id, send_reply):
        return

    # === 2. 帮助 ===
    if text_stripped in ("帮助", "help", "?", "？", "能力", "你能做什么"):
        try:
            from src.utils.capability_registry import get_capabilities_summary
            send_reply(reply_target, get_capabilities_summary())
        except:
            send_reply(reply_target, "我是智能骑行头盔研发助手，可以帮你做竞品分析、技术方案、市场策略等。")
        return

    # === 2.4 深度学习时长回复 ===
    pending_key = open_id or "default"
    if _deep_learn_pending.get(pending_key):
        try:
            hours = float(text_stripped)
            if hours < 0.5:
                send_reply(reply_target, "⚠️ 最少 0.5 小时")
                return
            if hours > 12 and not _deep_learn_pending.get(pending_key + "_confirmed"):
                # 超过 12h，二次确认
                _deep_learn_pending[pending_key + "_confirmed"] = hours
                send_reply(reply_target, f"⚠️ {hours}h 是一次较长的运行，确定吗？回复 Y 确认，其他取消")
                return

            # 检查是否是二次确认回复
            confirmed_hours = _deep_learn_pending.pop(pending_key + "_confirmed", None)
            if text_stripped.upper() == "Y" and confirmed_hours:
                hours = confirmed_hours

            # 清除 pending 状态并启动
            if pending_key in _deep_learn_pending:
                del _deep_learn_pending[pending_key]
            send_reply(reply_target, f"🎓 启动深度学习（{hours}h 窗口）...")

            def _run():
                try:
                    from scripts.tonight_deep_research import run_deep_learning
                    completed = run_deep_learning(max_hours=hours, progress_callback=lambda msg: send_reply(reply_target, msg))
                    send_reply(reply_target, f"✅ 深度学习完成: {len(completed) if completed else 0} 个任务")
                except Exception as e:
                    _safe_reply_error(send_reply, reply_target, "深度学习", e)

            threading.Thread(target=_run, daemon=True).start()
            return
        except ValueError:
            # 不是数字，清除 pending 状态，继续正常路由
            if pending_key in _deep_learn_pending:
                del _deep_learn_pending[pending_key]
            # 不 return，让后续路由继续处理这条消息

    # === 2.5 校准回复处理 ===
    if text_stripped and all(c in "0123" for c in text_stripped) and len(text_stripped) <= 10:
        _handle_calibration_reply(text_stripped, reply_target, send_reply)
        return

    # === 2.5.5 回答反馈处理 ===
    if text_stripped in ("👍", "👎", "👍👍", "👎👎"):
        _handle_answer_feedback(text_stripped, open_id, reply_target, send_reply)
        return

    # === 2.6 早报 ===
    if text_stripped in ("早报", "morning", "日报", "daily"):
        _handle_morning_brief(reply_target, send_reply)
        return

    # === 2.7 状态仪表盘 ===
    if text_stripped in ("状态", "dashboard", "仪表盘", "status"):
        _handle_dashboard(reply_target, send_reply)
        return

    # === 2.8 产品 One-Pager ===
    if text_stripped in ("产品简介", "one pager", "产品概要", "产品介绍"):
        _handle_one_pager(reply_target, send_reply)
        return

    # === 2.9 决策简报 ===
    if text_stripped.startswith("决策简报") or text_stripped.startswith("decision brief"):
        decision_id = text_stripped.replace("决策简报", "").replace("decision brief", "").strip().strip(":：")
        _handle_decision_brief(decision_id, reply_target, send_reply)
        return

    # === 2.10 谈判准备简报 ===
    if text_stripped.startswith("谈判准备") or text_stripped.startswith("negotiation"):
        target_name = text_stripped.replace("谈判准备", "").replace("negotiation", "").strip().strip(":：")
        _handle_negotiation_brief(target_name, reply_target, send_reply)
        return

    # === 2.11 注意力管理（关注焦点） ===
    if text_stripped.startswith("关注焦点") or text_stripped.startswith("focus"):
        focus_text = text_stripped.replace("关注焦点", "").replace("focus", "").strip().strip(":：")
        _handle_set_focus(focus_text, reply_target, send_reply)
        return

    # === 2.12 决策复盘 ===
    if text_stripped.startswith("决策复盘") or text_stripped.startswith("decision replay"):
        decision_id = text_stripped.replace("决策复盘", "").replace("decision replay", "").strip().strip(":：")
        _handle_decision_replay(decision_id, reply_target, send_reply)
        return

    # === 2.13 反事实推演 ===
    if text_stripped.startswith("假如") or text_stripped.startswith("what if"):
        scenario = text_stripped.replace("假如", "").replace("what if", "").strip().strip(":：")
        _handle_counterfactual(scenario, reply_target, send_reply)
        return

    # === 2.14 入职知识包 ===
    if text_stripped.startswith("入职包") or text_stripped.startswith("onboarding"):
        role = text_stripped.replace("入职包", "").replace("onboarding", "").strip().strip(":：")
        _handle_onboarding_pack(role, reply_target, send_reply)
        return

    # === 2.15 多角色支持 ===
    if text_stripped.startswith("设置角色") or text_stripped.startswith("set role"):
        role = text_stripped.replace("设置角色", "").replace("set role", "").strip().strip(":：")
        _handle_set_role(role, open_id, reply_target, send_reply)
        return

    # === 2.16 教练模式 ===
    if text_stripped in ("教练模式", "帮我理清思路", "coach", "coaching"):
        _coach_mode[open_id or "default"] = True
        send_reply(reply_target, "已进入教练模式。我只问问题，不给答案。\n说\"退出教练\"结束。\n\n你目前最纠结的决策是什么？")
        return

    if text_stripped in ("退出教练", "exit coach"):
        _coach_mode.pop(open_id or "default", None)
        send_reply(reply_target, "✅ 已退出教练模式。")
        return

    # === 2.17 竞品战争推演 ===
    if text_stripped.startswith("竞品推演") or text_stripped.startswith("competitor war game"):
        competitor = text_stripped.replace("竞品推演", "").replace("competitor war game", "").strip().strip(":：")
        _handle_competitor_wargame(competitor, reply_target, send_reply)
        return

    # === 2.18 知识滴灌 ===
    if text_stripped in ("滴灌", "knowledge drip"):
        _handle_drip_knowledge(reply_target, send_reply)
        return
    if text_stripped in ("关闭滴灌", "stop drip"):
        _drip_enabled = False
        send_reply(reply_target, "✅ 已关闭知识滴灌")
        return
    if text_stripped in ("开启滴灌", "start drip"):
        _drip_enabled = True
        send_reply(reply_target, "✅ 已开启知识滴灌")
        return

    # === 2.19 行动清单 ===
    if text_stripped in ("待办", "todo", "行动清单", "action items"):
        _handle_action_items(reply_target, send_reply)
        return

    # === 2.20 应知清单 ===
    if text_stripped.startswith("应知清单") or text_stripped.startswith("due diligence"):
        decision_id = text_stripped.replace("应知清单", "").replace("due diligence", "").strip().strip(":：")
        _handle_due_diligence(decision_id, reply_target, send_reply)
        return

    # === 2.21 产出版本 Diff ===
    if text_stripped.startswith("简报diff") or text_stripped.startswith("brief diff"):
        output_id = text_stripped.replace("简报diff", "").replace("brief diff", "").strip().strip(":：")
        _handle_output_diff(output_id, reply_target, send_reply)
        return

    # === 2.22 HUD 设计规范 ===
    if text_stripped in ("HUD设计规范", "hud design spec", "HUD规范"):
        _handle_hud_design_spec(reply_target, send_reply)
        return

    # === 2.23 Demo 场景脚本 ===
    if text_stripped in ("Demo脚本", "demo script", "demo场景"):
        _handle_demo_script(reply_target, send_reply)
        return

    # === 2.24 设置截止日 ===
    if text_stripped.startswith("设置截止日") or text_stripped.startswith("set deadline"):
        parts = text_stripped.replace("设置截止日", "").replace("set deadline", "").strip().split()
        if len(parts) >= 2:
            decision_id = parts[0].strip(":：")
            deadline = parts[1]
            _handle_set_deadline(decision_id, deadline, reply_target, send_reply)
        else:
            send_reply(reply_target, "格式: 设置截止日 decision_id 2026-04-30")
        return

    # === 2.25 自检指令 ===
    if text_stripped in ("自检", "self check", "health check", "测试", "自愈"):
        _handle_self_check(reply_target, send_reply)
        return

    # === 2.25.5 深钻模式 ===
    if text_stripped.startswith("深钻 ") or text_stripped.startswith("deep drill "):
        topic = text_stripped.replace("深钻 ", "").replace("deep drill ", "").strip()
        _handle_deep_drill(topic, reply_target, send_reply)
        return

    # === 2.25.6 沙盘推演 ===
    if text_stripped.startswith("沙盘 ") or text_stripped.startswith("sandbox ") or text_stripped.startswith("what if "):
        scenario = text_stripped.replace("沙盘 ", "").replace("sandbox ", "").replace("what if ", "").strip()
        _handle_sandbox_what_if(scenario, reply_target, send_reply)
        return

    # === 2.25.7 压力测试 ===
    if text_stripped.startswith("压力测试") or text_stripped.startswith("stress test"):
        _handle_stress_test(reply_target, send_reply)
        return

    # === 2.26 Demo 生成 ===
    if text_stripped in ("生成 HUD Demo", "HUD Demo", "hud demo"):
        _handle_generate_demo("hud", reply_target, reply_type, open_id, send_reply)
        return

    if text_stripped in ("生成 App Demo", "App Demo", "app demo"):
        _handle_generate_demo("app", reply_target, reply_type, open_id, send_reply)
        return

    if text_stripped in ("退出Demo", "exit demo"):
        if open_id in _demo_sessions:
            session = _demo_sessions.pop(open_id)
            send_reply(reply_target, f"✅ 已退出 Demo 迭代模式。最终版本: v{session.get('version', 1)}")
        else:
            send_reply(reply_target, "⚠️ 没有正在进行的 Demo")
        return

    # === 2.27 Demo 迭代修改 ===
    if open_id in _demo_sessions:
        demo_keywords = ["改", "调", "大一点", "小一点", "换", "移", "加", "删", "颜色", "位置", "字体", "动画"]
        if any(kw in text_stripped for kw in demo_keywords):
            _handle_demo_iteration(text_stripped, open_id, reply_target, send_reply)
            return

    # === 3. 学习相关指令 ===
    if text_stripped in ("学习", "每日学习", "daily learning"):
        _handle_daily_learning(reply_target, send_reply)
        return

    if text_stripped in ("重置学习", "reset learning", "重学"):
        _handle_reset_learning(reply_target, send_reply)
        return

    if text_stripped in ("深度学习", "夜间学习", "night learning", "deep learning"):
        if not _check_permission(open_id, "manager"):
            send_reply(reply_target, "⚠️ 此操作需要 manager 及以上权限")
        else:
            _handle_night_learning(reply_target, send_reply, open_id)
        return

    if text_stripped in ("自学习", "auto learn", "自动学习"):
        _handle_auto_learn(reply_target, send_reply)
        return

    if text_stripped in ("KB治理", "kb治理", "知识库治理"):
        _handle_kb_governance(reply_target, send_reply)
        return

    if text_stripped in ("对齐", "对齐报告", "alignment"):
        _handle_alignment(reply_target, send_reply)
        return

    # === 4. 关注主题 ===
    if text_stripped.startswith("关注 ") or text_stripped.startswith("关注："):
        _handle_add_topic(text_stripped, reply_target, send_reply)
        return

    # === 5. 导入文档 ===
    if text_stripped in ("导入文档", "导入", "import"):
        _handle_import_docs(reply_target, send_reply)
        return

    # === 6. 参考文件（多文件研究任务） ===
    if "参考文件：" in text_stripped or "reference file:" in text_stripped.lower():
        _handle_reference_files(text_stripped, reply_target, send_reply)
        return

    # === 7. 结构化文档快速通道 ===
    try:
        from scripts.feishu_handlers.structured_doc import try_structured_doc_fast_track
        if try_structured_doc_fast_track(text_stripped, reply_target, reply_type, open_id, chat_id, send_reply):
            return
    except ImportError:
        pass

    # === 7. 研发任务 ===
    if is_rd_task(text_stripped):
        if is_rd_task_running():
            send_reply(reply_target, "⏳ 上一个研发任务还在执行中，请稍后再试")
        else:
            send_reply(reply_target, "🚀 检测到研发任务，启动多Agent工作流...")
            threading.Thread(
                target=run_rd_task_background,
                args=(text_stripped, reply_target, reply_type, open_id, chat_id, send_reply),
                daemon=True
            ).start()
        return

    # === 8. URL 分享处理 ===
    if _has_shareable_url(text_stripped):
        _handle_share_url(text_stripped, open_id, reply_target, reply_type, send_reply)
        return

    # === 9. 长文章导入 ===
    if _is_likely_article(text_stripped):
        _handle_article_import(text_stripped, open_id, reply_target, send_reply)
        return

    # === 9.5 教练模式处理 ===
    if _coach_mode.get(open_id or "default"):
        _handle_coach_response(text_stripped, reply_target, send_reply)
        return

    # === 9.6 意图智能路由 ===
    intent = _classify_intent(text_stripped)
    if intent == "decision_brief":
        _handle_decision_brief("", reply_target, send_reply)
        return
    elif intent == "negotiation":
        _handle_negotiation_brief("", reply_target, send_reply)
        return
    elif intent == "knowledge_query":
        _handle_fast_query(text_stripped, reply_target, send_reply)
        return
    elif intent == "coach":
        _coach_mode[open_id or "default"] = True
        send_reply(reply_target, "🧠 已进入教练模式。你目前最纠结的决策是什么？")
        return
    elif intent == "status":
        _handle_dashboard(reply_target, send_reply)
        return

    # === 10. 兜底：智能对话 ===
    _smart_route_and_reply(text_stripped, open_id, chat_id, reply_target, reply_type, send_reply, session_id, mem)


def _has_shareable_url(text: str) -> bool:
    """检查文本中是否包含可分享的 URL"""
    url_patterns = [
        r'https?://[^\s]+',
    ]
    return bool(re.search('|'.join(url_patterns), text))


def _is_likely_article(text: str) -> bool:
    """判断是否为应该导入知识库的长文章"""
    text_len = len(text.strip())

    command_prefixes = ["研究", "分析一下", "帮我", "请", "设计", "方案", "@dev"]
    has_command = any(text.strip().startswith(p) for p in command_prefixes)

    if text_len < 500 or has_command:
        return False

    if text_len > 800:
        return True

    return False


def _handle_daily_learning(reply_target: str, send_reply):
    """处理每日学习指令"""
    topics_path = PROJECT_ROOT / ".ai-state" / "knowledge" / "learning_topics.json"
    topic_count = 10
    if topics_path.exists():
        try:
            data = json.loads(topics_path.read_text(encoding="utf-8"))
            topic_count = len(data.get("topics", []))
        except:
            pass

    send_reply(reply_target, f"📚 正在执行每日学习（{topic_count}个主题，预计3-5分钟）...")

    def _run():
        try:
            from scripts.daily_learning import run_daily_learning
            report = run_daily_learning(progress_callback=lambda msg: send_reply(reply_target, msg))
            send_reply(reply_target, report)
        except Exception as e:
            _safe_reply_error(send_reply, reply_target, "每日学习", e)

    threading.Thread(target=_run, daemon=True).start()


def _handle_reset_learning(reply_target: str, send_reply):
    """重置学习覆盖记录"""
    try:
        covered_file = PROJECT_ROOT / ".ai-state" / "covered_topics.json"
        if covered_file.exists():
            covered_file.unlink()
        send_reply(reply_target, "✅ 已重置学习覆盖记录，下次学习将重新搜索所有固定主题")
    except Exception as e:
        _safe_reply_error(send_reply, reply_target, "重置学习", e)


def _handle_night_learning(reply_target: str, send_reply, open_id: str = ""):
    """处理深度学习指令 — 先询问时长"""
    pending_key = open_id or "default"
    _deep_learn_pending[pending_key] = True
    send_reply(reply_target, "🎓 深度学习 — 请问跑几个小时？\n\n直接回复数字，如：1.5、3、7")


def _handle_kb_governance(reply_target: str, send_reply):
    """处理 KB 治理"""
    send_reply(reply_target, "🗄️ 正在运行知识库治理...")

    def _run():
        try:
            from scripts.kb_governance import run_governance
            report = run_governance()
            send_reply(reply_target, f"✅ KB 治理完成: {report}")
        except Exception as e:
            _safe_reply_error(send_reply, reply_target, "KB治理", e)

    threading.Thread(target=_run, daemon=True).start()


def _handle_auto_learn(reply_target: str, send_reply):
    """处理自学习（30min 周期）"""
    send_reply(reply_target, "📚 启动自学习（KB 缺口补充）...")

    def _run():
        try:
            from scripts.auto_learn import auto_learn_cycle
            result = auto_learn_cycle(progress_callback=lambda msg: send_reply(reply_target, msg))
            send_reply(reply_target, f"✅ 自学习完成: {result}")
        except Exception as e:
            _safe_reply_error(send_reply, reply_target, "自学习", e)

    threading.Thread(target=_run, daemon=True).start()


def _handle_alignment(reply_target: str, send_reply):
    """处理对齐报告"""
    send_reply(reply_target, "📊 正在生成对齐报告...")

    def _run():
        try:
            from scripts.daily_learning import generate_alignment_report
            report = generate_alignment_report()
            send_reply(reply_target, report)
        except Exception as e:
            _safe_reply_error(send_reply, reply_target, "对齐报告", e)

    threading.Thread(target=_run, daemon=True).start()


def _handle_calibration_reply(text: str, reply_target: str, send_reply):
    """处理 Critic 校准回复

    支持两种格式:
    - 单字符: "1"/"2"/"3"/"0" → 标注最新一个样本（向后兼容）
    - 批量字符串: "11213" → 依次标注多个样本
    """
    try:
        from scripts.critic_calibration import record_label, _load_pending_samples

        pending = _load_pending_samples()
        if not pending:
            send_reply(reply_target, "⚠️ 没有待校准的样本")
            return

        label_map = {"1": "accurate", "2": "too_loose", "3": "too_strict", "0": "skip"}

        # 检查是否全部是 1/2/3/0 字符
        if not all(c in "0123" for c in text):
            send_reply(reply_target, f"⚠️ 无效格式，请只使用 0/1/2/3")
            return

        if len(text) == 1:
            # 单字符：标注最新一个（向后兼容）
            latest = pending[-1]
            label = label_map[text]
            success = record_label(latest.get("sample_id", ""), label)
            if success:
                desc = {"accurate": "✅准确", "too_loose": "⬆️偏松", "too_strict": "⬇️偏紧", "skip": "⏭️跳过"}
                send_reply(reply_target, f"✅ 已记录: {desc.get(label, label)}")
            else:
                send_reply(reply_target, "❌ 记录失败")
        else:
            # 批量：依次标注最近 N 个样本
            batch = pending[-len(text):]
            if len(text) != len(batch):
                send_reply(reply_target,
                    f"⚠️ 样本数不匹配: 你回复了 {len(text)} 个，但只有 {len(batch)} 个待校准")
                return

            results = []
            desc_map = {"accurate": "✅", "too_loose": "⬆️", "too_strict": "⬇️", "skip": "⏭️"}
            for i, (char, sample) in enumerate(zip(text, batch)):
                label = label_map.get(char, "skip")
                success = record_label(sample.get("sample_id", ""), label)
                results.append(f"{i+1}. {desc_map.get(label, '?')} {sample.get('level', '?')}: {sample.get('issue', '')[:30]}")

            send_reply(reply_target,
                f"✅ 批量校准完成 ({len(results)} 条)\n" + "\n".join(results))

    except ImportError:
        send_reply(reply_target, "⚠️ 校准模块未安装")
    except Exception as e:
        _safe_reply_error(send_reply, reply_target, "校准处理", e)


def _handle_add_topic(text: str, reply_target: str, send_reply):
    """添加关注主题"""
    topic_text = text.replace("关注 ", "").replace("关注：", "").strip()
    if not topic_text:
        send_reply(reply_target, "请输入关注的主题，如：关注 骑行头盔 AR导航")
        return

    topics_path = PROJECT_ROOT / ".ai-state" / "knowledge" / "learning_topics.json"
    if topics_path.exists():
        data = json.loads(topics_path.read_text(encoding="utf-8"))
    else:
        data = {"version": "1.0", "topics": []}

    data["topics"].append({"query": topic_text, "domain": "lessons", "tags": ["用户关注"]})
    data["updated_at"] = datetime.now().strftime("%Y-%m-%d")
    topics_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    send_reply(reply_target, f"✅ 已添加学习关注：{topic_text}\n下次学习时会搜索此主题")


def _handle_import_docs(reply_target: str, send_reply):
    """处理导入文档"""
    send_reply(reply_target, "📂 正在扫描文档收件箱...")

    try:
        from scripts.doc_importer import scan_and_import
        report = scan_and_import(progress_callback=lambda msg: send_reply(reply_target, msg))
        if report:
            send_reply(reply_target, report)
        else:
            send_reply(reply_target, "[Info] 收件箱为空，无文件需要处理。\n请把文件放入 .ai-state/inbox/ 目录")
    except Exception as e:
        _safe_reply_error(send_reply, reply_target, "导入文档", e)


def _handle_share_url(text: str, open_id: str, reply_target: str, reply_type: str, send_reply):
    """处理 URL 分享"""
    try:
        from scripts.feishu_sdk_client import handle_share_content
        handle_share_content(open_id, text=text, reply_target=reply_target, reply_type=reply_type)
    except:
        send_reply(reply_target, "🔗 检测到链接，但分享处理功能暂未导入。")


def _handle_article_import(text: str, open_id: str, reply_target: str, send_reply):
    """处理长文章导入"""
    send_reply(reply_target, f"📄 检测到长文（{len(text)}字），正在导入知识库...")

    try:
        from src.tools.knowledge_base import add_knowledge
        from src.utils.model_gateway import get_model_gateway

        gateway = get_model_gateway()
        summary_result = gateway.call_azure_openai(
            "cpo",
            f"请为以下文章生成标题和摘要（JSON格式）：\n{text[:3000]}\n\n输出: {{\"title\": \"标题\", \"summary\": \"200字摘要\"}}",
            "只输出 JSON。",
            "article_summary"
        )

        if summary_result.get("success"):
            import re
            resp = summary_result["response"].strip()
            resp = re.sub(r'^```json\s*', '', resp)
            resp = re.sub(r'\s*```$', '', resp)
            data = json.loads(resp)
            title = data.get("title", "用户分享文章")
            summary = data.get("summary", text[:500])
        else:
            title = "用户分享文章"
            summary = text[:500]

        add_knowledge(
            title=title,
            domain="lessons",
            content=summary,
            tags=["user_share", "article"],
            source="user_share:text",
            confidence="medium"
        )

        send_reply(reply_target, f"✅ 文章已入库：{title}")
    except Exception as e:
        _safe_reply_error(send_reply, reply_target, "导入文档", e)


def _handle_reference_files(text: str, reply_target: str, send_reply):
    """处理参考文件（多文件研究任务）

    支持格式：
    - 单行：参考文件：docs/tasks/xxx.md
    - 多行：参考文件：\n  A. docs/tasks/xxx.md\n  B. docs/specs/yyy.md
    """
    import time

    # 提取所有 .md 文件路径（支持各种排版格式）
    matches = re.findall(r'[\w./\\-]+\.md', text)
    if not matches:
        send_reply(reply_target, "格式错误。正确格式：参考文件：docs/tasks/xxx.md")
        return

    # 区分参考文件(docs/tasks/)和约束文件(docs/specs/)
    task_files = []
    constraint_files = []
    for raw_path in matches:
        # 支持相对路径和绝对路径
        if not raw_path.startswith('/') and not raw_path.startswith('D:'):
            full_path = str(PROJECT_ROOT / raw_path)
        else:
            full_path = raw_path

        if Path(full_path).exists():
            if 'docs/tasks/' in raw_path or 'docs\\tasks' in raw_path:
                task_files.append((raw_path, full_path))
            elif 'docs/specs/' in raw_path or 'docs\\specs' in raw_path:
                constraint_files.append((raw_path, full_path))
            else:
                # 其他位置的 .md 默认作为参考文件
                task_files.append((raw_path, full_path))
        else:
            send_reply(reply_target, f"[Research] 文件不存在: {raw_path}")

    if not task_files:
        if constraint_files:
            send_reply(reply_target, "[Research] 仅收到约束文件，缺少研究任务文件(docs/tasks/)")
        return

    # 后台执行多文件研究
    def _run_multi_files():
        global _long_task_running
        _long_task_running = True
        try:
            from scripts.tonight_deep_research import run_research_from_file

            # 读取约束文件内容作为上下文注入
            constraint_context = ""
            for raw_path, full_path in constraint_files:
                constraint_context += f"\n\n---\n## 约束文件: {raw_path}\n\n"
                constraint_context += Path(full_path).read_text(encoding='utf-8')

            # 每个参考文件独立执行
            for idx, (raw_path, full_path) in enumerate(task_files, 1):
                send_reply(reply_target, f"🔍 [{idx}/{len(task_files)}] 开始研究: {Path(full_path).name}")
                report_path = run_research_from_file(
                    full_path,
                    progress_callback=lambda msg: send_reply(reply_target, msg),
                    constraint_context=constraint_context if constraint_context else None
                )
                if report_path:
                    send_reply(reply_target, f"✅ [{idx}/{len(task_files)}] 完成: {Path(full_path).name}\n报告: {report_path}")
                else:
                    send_reply(reply_target, f"[Research] {Path(full_path).name} 未解析到有效任务")
                time.sleep(2)
        except Exception as e:
            _safe_reply_error(send_reply, reply_target, "Research任务", e)
        finally:
            _long_task_running = False

    # 启动后台线程
    threading.Thread(target=_run_multi_files, daemon=True).start()
    msg = f"[Research] 启动 {len(task_files)} 个研究任务"
    if constraint_files:
        msg += f"，附带 {len(constraint_files)} 个约束文件"
    send_reply(reply_target, msg)


# 全局任务运行状态（防止并发）
_long_task_running = False


def _handle_morning_brief(reply_target: str, send_reply):
    """生成并推送每日早报（决策视角）"""
    send_reply(reply_target, "🌅 正在生成早报...")

    def _run():
        try:
            brief = _generate_morning_brief()
            send_reply(reply_target, brief)
        except Exception as e:
            _safe_reply_error(send_reply, reply_target, "早报生成", e)

    threading.Thread(target=_run, daemon=True).start()


def _generate_morning_brief() -> str:
    """生成每日早报"""
    lines = [f"🌅 早报 {datetime.now().strftime('%Y-%m-%d')}\n"]

    # 1. 决策进展
    dt_path = PROJECT_ROOT / ".ai-state" / "product_decision_tree.yaml"
    if dt_path.exists():
        try:
            import yaml as _yaml
            dt = _yaml.safe_load(dt_path.read_text(encoding='utf-8'))
            lines.append("📌 决策进展")
            for d in dt.get("decisions", []):
                if d.get("status") == "open":
                    total = len(d.get("blocking_knowledge", []))
                    resolved = len(d.get("resolved_knowledge", []))
                    icon = "🟢" if resolved >= total * 0.8 else "🟡" if resolved >= total * 0.5 else "🔴"
                    lines.append(f"  {icon} {d['question'][:50]} ({resolved}/{total})")
        except:
            pass

    # 2. 最近报告摘要
    reports_dir = PROJECT_ROOT / ".ai-state" / "reports"
    if reports_dir.exists():
        recent = sorted(reports_dir.glob("*.summary.json"), reverse=True)[:3]
        if recent:
            lines.append("\n📝 最新研究")
            for f in recent:
                try:
                    s = json.loads(f.read_text(encoding='utf-8'))
                    lines.append(f"  • {s.get('task_title', '?')[:30]}")
                    lines.append(f"    → {s.get('core_finding', '')[:60]}")
                except:
                    continue

    # 3. KB 统计
    try:
        from src.tools.knowledge_base import get_knowledge_stats
        stats = get_knowledge_stats()
        total = sum(stats.values())
        lines.append(f"\n📚 知识库: {total} 条")
    except:
        pass

    # 4. Critic 统计
    drift_path = PROJECT_ROOT / ".ai-state" / "critic_drift_log.jsonl"
    if drift_path.exists():
        try:
            last_lines = drift_path.read_text(encoding='utf-8').strip().split('\n')[-5:]
            p0_rates = [json.loads(l).get("p0_rate", 0) for l in last_lines]
            avg_p0 = sum(p0_rates) / len(p0_rates) if p0_rates else 0
            lines.append(f"🔍 Critic P0 率: {avg_p0:.0%}（最近 {len(p0_rates)} 次）")
        except:
            pass

    return "\n".join(lines)


def _handle_dashboard(reply_target: str, send_reply):
    """生成系统状态仪表盘"""
    lines = [f"📊 agent_company 状态\n"]

    # KB
    try:
        from src.tools.knowledge_base import get_knowledge_stats
        stats = get_knowledge_stats()
        total = sum(stats.values())
        detail = " | ".join([f"{k}: {v}" for k, v in stats.items()])
        lines.append(f"🧠 知识库: {total} 条 ({detail})")
    except:
        pass

    # 任务
    try:
        tracker_path = PROJECT_ROOT / ".ai-state" / "task_tracker.jsonl"
        if tracker_path.exists():
            today = datetime.now().strftime('%Y-%m-%d')
            today_tasks = sum(1 for l in tracker_path.read_text(encoding='utf-8').strip().split('\n')
                             if today in l and '"completed"' in l)
            lines.append(f"📝 今日任务: {today_tasks} 个完成")
    except:
        pass

    # 元能力
    try:
        reg_path = PROJECT_ROOT / ".ai-state" / "tool_registry.json"
        if reg_path.exists():
            reg = json.loads(reg_path.read_text(encoding='utf-8'))
            tools = [t for t in reg.get("tools", []) if t.get("status") == "active"]
            if tools:
                names = ", ".join([t["name"] for t in tools[:5]])
                lines.append(f"🧬 元能力: {len(tools)} 个工具 ({names})")
    except:
        pass

    # API 用量
    try:
        from src.utils.token_usage_tracker import get_tracker
        tracker = get_tracker()
        if hasattr(tracker, 'generate_daily_report'):
            lines.append(f"💰 {tracker.generate_daily_report()}")
    except:
        pass

    # Critic
    try:
        drift_path = PROJECT_ROOT / ".ai-state" / "critic_drift_log.jsonl"
        if drift_path.exists():
            last_lines = drift_path.read_text(encoding='utf-8').strip().split('\n')[-5:]
            p0_rates = [json.loads(l).get("p0_rate", 0) for l in last_lines]
            avg_p0 = sum(p0_rates) / len(p0_rates) if p0_rates else 0
            lines.append(f"🔍 Critic: P0 率 {avg_p0:.0%}（最近 {len(p0_rates)} 次）")
    except:
        pass

    # 校准
    try:
        cal_path = PROJECT_ROOT / ".ai-state" / "critic_calibration.jsonl"
        if cal_path.exists():
            count = sum(1 for _ in open(cal_path, encoding='utf-8'))
            lines.append(f"🎯 校准: {count} 条已标注")
    except:
        pass

    send_reply(reply_target, "\n".join(lines))


def _handle_one_pager(reply_target: str, send_reply):
    """生成产品 One-Pager"""
    send_reply(reply_target, "📄 正在生成产品简介...")

    def _run():
        try:
            from src.utils.model_gateway import get_model_gateway
            from src.tools.knowledge_base import search_knowledge, get_knowledge_stats
            gw = get_model_gateway()

            # 收集 KB 精华
            highlights = search_knowledge("智能骑行头盔 V1 核心功能 HUD 导航", limit=10)
            kb_text = "\n".join([f"- {h.get('title','')}: {h.get('content','')[:200]}" for h in highlights])

            prompt = (
                f"基于以下知识库信息，生成一份智能骑行头盔的产品 One-Pager。\n\n"
                f"## 知识库精华\n{kb_text}\n\n"
                f"## 要求\n"
                f"1. 标题 + 一句话副标题\n"
                f"2. 3-4 个核心功能亮点（每个一句话）\n"
                f"3. 目标用户和市场定位\n"
                f"4. 技术差异化（和竞品比有什么独特的）\n"
                f"5. V1 上市时间线\n\n"
                f"语言要有感染力，像给投资人看的 pitch deck 第一页。"
            )

            result = gw.call("gpt_5_4", prompt, "你是产品营销专家。", "content_generation")
            if result.get("success"):
                send_reply(reply_target, result["response"])
            else:
                send_reply(reply_target, f"生成失败: {result.get('error', '')[:200]}")
        except Exception as e:
            _safe_reply_error(send_reply, reply_target, "内容生成", e)

    threading.Thread(target=_run, daemon=True).start()


def _handle_decision_brief(decision_id: str, reply_target: str, send_reply):
    """生成决策简报"""
    send_reply(reply_target, f"📋 正在生成决策简报: {decision_id}...")

    def _run():
        try:
            import yaml as _yaml
            from src.utils.model_gateway import get_model_gateway
            from src.tools.knowledge_base import search_knowledge
            gw = get_model_gateway()

            # 读决策树
            dt_path = PROJECT_ROOT / ".ai-state" / "product_decision_tree.yaml"
            decision = None
            if dt_path.exists():
                dt = _yaml.safe_load(dt_path.read_text(encoding='utf-8'))
                for d in dt.get("decisions", []):
                    if decision_id.lower() in d.get("id", "").lower() or decision_id in d.get("question", ""):
                        decision = d
                        break

            if not decision:
                send_reply(reply_target, f"⚠️ 未找到决策: {decision_id}\n可用决策ID: " +
                    ", ".join([d["id"] for d in dt.get("decisions", [])]))
                return

            # 搜索相关 KB
            kb_results = search_knowledge(decision["question"], limit=15)
            kb_text = "\n".join([f"- [{r.get('confidence','')}] {r.get('title','')}: {r.get('content','')[:200]}"
                                for r in kb_results])

            # 读 resolved_knowledge
            resolved = decision.get("resolved_knowledge", [])
            resolved_text = "\n".join([f"- {r.get('knowledge','')}" for r in resolved]) if resolved else "暂无"

            prompt = (
                f"生成决策简报。\n\n"
                f"## 决策问题\n{decision['question']}\n\n"
                f"## 已确认的知识\n{resolved_text}\n\n"
                f"## 相关知识库条目\n{kb_text}\n\n"
                f"## 仍缺的知识\n" +
                "\n".join([f"- {bk}" for bk in decision.get("blocking_knowledge", [])]) +
                f"\n\n## 要求\n"
                f"1. 列出所有可选方案（每个方案的优势/劣势/BOM/供应商/风险）\n"
                f"2. 标注数据来源的 confidence\n"
                f"3. 标注仍缺的关键信息\n"
                f"4. 如果数据足够，给出推荐\n"
                f"5. 如果数据不足，说明还需要什么信息才能做决定"
            )

            result = gw.call("gpt_5_4", prompt, "你是产品决策顾问，输出结构化的决策简报。", "synthesis")
            if result.get("success"):
                send_reply(reply_target, result["response"])
            else:
                send_reply(reply_target, f"生成失败: {result.get('error', '')[:200]}")
        except Exception as e:
            _safe_reply_error(send_reply, reply_target, "内容生成", e)

    threading.Thread(target=_run, daemon=True).start()


def _handle_negotiation_brief(target_name: str, reply_target: str, send_reply):
    """生成谈判准备简报"""
    send_reply(reply_target, f"📋 正在生成谈判准备: {target_name}...")

    def _run():
        try:
            import yaml as _yaml
            from src.utils.model_gateway import get_model_gateway
            from src.tools.knowledge_base import search_knowledge
            gw = get_model_gateway()

            # 搜索相关 KB（对方产能/报价/竞品对比）
            kb_results = search_knowledge(f"{target_name} 产能 报价 供应商", limit=15)
            kb_text = "\n".join([f"- [{r.get('confidence','')}] {r.get('title','')}: {r.get('content','')[:200]}"
                                for r in kb_results])

            # 搜索竞品信息
            competitor_results = search_knowledge(f"{target_name} 竞品 替代供应商", limit=10)
            competitor_text = "\n".join([f"- {r.get('title','')}: {r.get('content','')[:150]}"
                                        for r in competitor_results])

            prompt = (
                f"生成谈判准备简报。\n\n"
                f"## 谈判对象\n{target_name}\n\n"
                f"## 对方信息（产能/报价/历史合作）\n{kb_text}\n\n"
                f"## 竞品/替代方案\n{competitor_text}\n\n"
                f"## 要求\n"
                f"1. 对方产能和报价分析（如果有数据）\n"
                f"2. 竞品对比（至少 2-3 个替代方案）\n"
                f"3. BATNA（我们的最佳替代方案）\n"
                f"4. 谈判筹码分析（我们有什么对方想要的）\n"
                f"5. 谈判策略建议（开局报价、让步节奏、底线）\n"
            )

            result = gw.call("gpt_5_4", prompt, "你是采购谈判顾问，输出结构化的谈判准备简报。", "synthesis")
            if result.get("success"):
                send_reply(reply_target, result["response"])
            else:
                send_reply(reply_target, f"生成失败: {result.get('error', '')[:200]}")
        except Exception as e:
            _safe_reply_error(send_reply, reply_target, "内容生成", e)

    threading.Thread(target=_run, daemon=True).start()


def _handle_set_focus(focus_text: str, reply_target: str, send_reply):
    """设置关注焦点"""
    if not focus_text:
        send_reply(reply_target, "请输入关注焦点，如：关注焦点 HUD显示方案决策")
        return

    focus_file = PROJECT_ROOT / ".ai-state" / "focus.yaml"
    try:
        import yaml as _yaml
        focus_data = {"focus": focus_text, "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M")}
        focus_file.parent.mkdir(parents=True, exist_ok=True)
        focus_file.write_text(_yaml.dump(focus_data, allow_unicode=True), encoding="utf-8")
        send_reply(reply_target, f"🎯 关注焦点已设置：{focus_text}\n早报和汇总报告将优先展示相关内容")
    except Exception as e:
        _safe_reply_error(send_reply, reply_target, "设置操作", e)


def _handle_decision_replay(decision_id: str, reply_target: str, send_reply):
    """决策复盘 — 重建决策时间线"""
    send_reply(reply_target, f"📊 正在复盘决策: {decision_id}...")

    def _run():
        try:
            import yaml as _yaml
            from src.utils.model_gateway import get_model_gateway
            from src.tools.knowledge_base import search_knowledge
            gw = get_model_gateway()

            # 读决策树
            dt_path = PROJECT_ROOT / ".ai-state" / "product_decision_tree.yaml"
            decision = None
            if dt_path.exists():
                dt = _yaml.safe_load(dt_path.read_text(encoding='utf-8'))
                for d in dt.get("decisions", []):
                    if decision_id.lower() in d.get("id", "").lower() or decision_id in d.get("question", ""):
                        decision = d
                        break

            if not decision:
                send_reply(reply_target, f"⚠️ 未找到决策: {decision_id}")
                return

            # 收集决策历史（resolved_knowledge + 相关报告）
            resolved = decision.get("resolved_knowledge", [])
            history_text = "\n".join([f"- [{r.get('timestamp','')}] {r.get('knowledge','')}" for r in resolved])

            # 搜索相关研究报告
            reports_dir = PROJECT_ROOT / ".ai-state" / "reports"
            if reports_dir.exists():
                for f in reports_dir.glob("*.summary.json"):
                    try:
                        s = json.loads(f.read_text(encoding='utf-8'))
                        if decision_id.lower() in s.get("task_title", "").lower():
                            history_text += f"\n- [{s.get('timestamp','')}] 报告: {s.get('core_finding','')[:100]}"
                    except:
                        continue

            prompt = (
                f"重建决策时间线。\n\n"
                f"## 决策问题\n{decision.get('question', '')}\n\n"
                f"## 决策历史\n{history_text}\n\n"
                f"## 要求\n"
                f"1. 按时间顺序列出关键信息节点\n"
                f"2. 标注每个节点对决策的影响\n"
                f"3. 分析决策过程的质量（信息是否充分、时机是否合适）\n"
                f"4. 提取可复用的经验教训\n"
            )

            result = gw.call("gpt_5_4", prompt, "你是决策分析师。", "synthesis")
            if result.get("success"):
                send_reply(reply_target, result["response"])
            else:
                send_reply(reply_target, f"生成失败: {result.get('error', '')[:200]}")
        except Exception as e:
            _safe_reply_error(send_reply, reply_target, "复盘", e)

    threading.Thread(target=_run, daemon=True).start()


def _handle_counterfactual(scenario: str, reply_target: str, send_reply):
    """反事实推演 — What-If 分析"""
    send_reply(reply_target, f"🔮 正在推演: {scenario}...")

    def _run():
        try:
            from src.utils.model_gateway import get_model_gateway
            from src.tools.knowledge_base import search_knowledge
            gw = get_model_gateway()

            # 搜索相关 KB
            kb_results = search_knowledge(scenario, limit=10)
            kb_text = "\n".join([f"- {r.get('title','')}: {r.get('content','')[:150]}" for r in kb_results])

            prompt = (
                f"反事实推演：假设 '{scenario}'，会发生什么？\n\n"
                f"## 相关背景知识\n{kb_text}\n\n"
                f"## 要求\n"
                f"1. 列出直接后果（1-3 步）\n"
                f"2. 列出间接后果（3-5 步的连锁反应）\n"
                f"3. 评估每个后果的概率和影响\n"
                f"4. 给出应对建议\n"
            )

            result = gw.call("o3_mini", prompt, "你是战略分析师，擅长推演因果链条。", "reasoning")
            if result.get("success"):
                send_reply(reply_target, result["response"])
            else:
                send_reply(reply_target, f"推演失败: {result.get('error', '')[:200]}")
        except Exception as e:
            _safe_reply_error(send_reply, reply_target, "推演", e)

    threading.Thread(target=_run, daemon=True).start()


def _handle_onboarding_pack(role: str, reply_target: str, send_reply):
    """生成入职知识包"""
    send_reply(reply_target, f"📚 正在生成入职包: {role}...")

    def _run():
        try:
            from src.utils.model_gateway import get_model_gateway
            from src.tools.knowledge_base import search_knowledge, get_knowledge_stats
            gw = get_model_gateway()

            # 根据角色收集不同领域的知识
            role_domains = {
                "技术": ["components", "technology", "supplier"],
                "产品": ["market", "competitor", "user"],
                "市场": ["market", "competitor", "brand"],
                "供应链": ["supplier", "components", "cost"],
            }
            domains = role_domains.get(role, ["market", "components"])

            kb_text = ""
            for domain in domains:
                results = search_knowledge(f"{domain} 智能头盔", limit=5)
                kb_text += f"\n## {domain}\n"
                kb_text += "\n".join([f"- {r.get('title','')}: {r.get('content','')[:200]}" for r in results])

            prompt = (
                f"为新员工生成入职知识包（角色：{role}）。\n\n"
                f"## 相关知识\n{kb_text}\n\n"
                f"## 要求\n"
                f"1. 角色背景（这个角色在团队中的定位）\n"
                f"2. 必读知识（5-8 条最重要的条目）\n"
                f"3. 建议阅读顺序（按重要性排序）\n"
                f"4. 试用期目标（30天内应该了解什么）\n"
            )

            result = gw.call("gpt_5_3", prompt, "你是团队导师。", "content_generation")
            if result.get("success"):
                send_reply(reply_target, result["response"])
            else:
                send_reply(reply_target, f"生成失败: {result.get('error', '')[:200]}")
        except Exception as e:
            _safe_reply_error(send_reply, reply_target, "内容生成", e)

    threading.Thread(target=_run, daemon=True).start()


def _handle_set_role(role: str, open_id: str, reply_target: str, send_reply):
    """设置用户角色"""
    valid_roles = ["技术", "产品", "市场", "供应链", "管理", "默认"]
    if role not in valid_roles:
        send_reply(reply_target, f"⚠️ 无效角色。可选: {', '.join(valid_roles)}")
        return

    roles_file = PROJECT_ROOT / ".ai-state" / "user_roles.yaml"
    try:
        import yaml as _yaml
        roles_data = {"roles": {}}
        if roles_file.exists():
            roles_data = _yaml.safe_load(roles_file.read_text(encoding='utf-8')) or {"roles": {}}
        roles_data["roles"][open_id or "default"] = {"role": role, "updated_at": datetime.now().strftime("%Y-%m-%d")}
        roles_file.parent.mkdir(parents=True, exist_ok=True)
        roles_file.write_text(_yaml.dump(roles_data, allow_unicode=True), encoding="utf-8")
        send_reply(reply_target, f"✅ 已设置角色: {role}\n系统将根据角色调整回答深度和视角")
    except Exception as e:
        _safe_reply_error(send_reply, reply_target, "设置操作", e)


def _handle_coach_response(text: str, reply_target: str, send_reply):
    """教练模式回复——只问问题，不给答案"""
    from src.utils.model_gateway import get_model_gateway
    from src.tools.knowledge_base import search_knowledge
    gw = get_model_gateway()

    # 注入 KB 上下文，让教练的问题有数据支撑
    kb = search_knowledge(text, limit=5)
    kb_text = "\n".join([f"- {r.get('title','')}: {r.get('content','')[:150]}" for r in kb])

    result = gw.call("gpt_5_4",
        f"用户说: {text}\n\n"
        f"相关知识:\n{kb_text}\n\n"
        f"你是一个苏格拉底式教练。规则:\n"
        f"1. 绝对不给答案或建议\n"
        f"2. 只问一个尖锐的问题，挑战用户的假设或暴露盲区\n"
        f"3. 问题要基于数据（引用知识库中的信息）\n"
        f"4. 保持友善但犀利",
        "你是产品教练，只问问题不给答案。", "coach")
    if result.get("success"):
        send_reply(reply_target, result["response"])
    else:
        send_reply(reply_target, "你这个问题很有意思——你觉得最大的风险是什么？")


def _handle_competitor_wargame(competitor: str, reply_target: str, send_reply):
    """竞品战争推演"""
    send_reply(reply_target, f"⚔️ 正在推演竞品: {competitor}...")

    def _run():
        try:
            from src.utils.model_gateway import get_model_gateway
            from src.tools.knowledge_base import search_knowledge
            gw = get_model_gateway()

            # 搜索 KB 中该竞品的全部数据
            kb_results = search_knowledge(competitor, limit=20)
            kb_text = "\n".join([f"- [{r.get('confidence','')}] {r.get('title','')}: {r.get('content','')[:200]}"
                                for r in kb_results])

            prompt = (
                f"竞品战争推演：{competitor}\n\n"
                f"## 竞品信息\n{kb_text}\n\n"
                f"## 要求\n"
                f"1. 竞品现状分析（产品/技术/市场/供应链）\n"
                f"2. 推演未来 12 个月可能的动向（3-5 个场景）\n"
                f"3. 每个场景对我们的威胁评估\n"
                f"4. 我们的应对策略（进攻/防守/合作）\n"
            )

            result = gw.call("gpt_5_4", prompt, "你是战略分析师。", "synthesis")
            if result.get("success"):
                send_reply(reply_target, result["response"])
            else:
                send_reply(reply_target, f"推演失败: {result.get('error', '')[:200]}")
        except Exception as e:
            _safe_reply_error(send_reply, reply_target, "推演", e)

    threading.Thread(target=_run, daemon=True).start()


def _classify_intent(text: str) -> str:
    """用 o3-mini 分类用户意图"""
    from src.utils.model_gateway import get_model_gateway
    gw = get_model_gateway()
    result = gw.call("o3_mini",
        f"用户说: {text}\n\n"
        f"判断意图类别（只输出类别名，不要解释）:\n"
        f"research_task — 需要多Agent协作的研发分析\n"
        f"decision_brief — 想看某个决策的简报\n"
        f"negotiation — 谈判准备\n"
        f"knowledge_query — 查询知识库（简单问题）\n"
        f"deep_drill — 想深入研究某个话题\n"
        f"coach — 想理清思路，需要教练式提问\n"
        f"product_vision — 想看产品愿景或场景描述\n"
        f"status — 想看系统状态\n"
        f"chat — 普通闲聊或简单问题\n",
        task_type="intent_classify")
    if result.get("success"):
        return result["response"].strip().split("\n")[0].strip()
    return "chat"


def _handle_fast_query(text: str, reply_target: str, send_reply):
    """简单问答快速通道 — KB + 单模型，跳过多Agent"""
    try:
        from src.utils.model_gateway import get_model_gateway
        from src.tools.knowledge_base import search_knowledge, format_knowledge_for_prompt
        gw = get_model_gateway()

        # 搜索知识库
        kb_entries = search_knowledge(text, limit=5)
        kb_context = format_knowledge_for_prompt(kb_entries) if kb_entries else ""

        prompt = text
        if kb_context:
            prompt = f"相关知识：\n{kb_context[:1500]}\n\n用户问题：{text}"

        # 用 gemini-2.5-flash 做简单问答（快速+便宜）
        result = gw.call("gemini_2_5_flash", prompt, "", "chat")
        if result.get("success"):
            send_reply(reply_target, result["response"])
        else:
            send_reply(reply_target, "抱歉，我暂时无法回答这个问题。")
    except Exception as e:
        _safe_reply_error(send_reply, reply_target, "智能对话", e)


def _handle_drip_knowledge(reply_target: str, send_reply):
    """推送一条高价值知识滴灌"""
    from src.tools.knowledge_base import KB_ROOT
    from datetime import timedelta
    import random

    # 筛选：最近 7 天入库 + high confidence + 未被滴灌过
    candidates = []
    dripped_path = PROJECT_ROOT / ".ai-state" / "dripped_ids.json"
    dripped = set()
    if dripped_path.exists():
        try:
            dripped = set(json.loads(dripped_path.read_text(encoding='utf-8')))
        except:
            pass

    for f in KB_ROOT.rglob("*.json"):
        try:
            data = json.loads(f.read_text(encoding='utf-8'))
            if (data.get("confidence") in ("high", "authoritative") and
                str(f) not in dripped and
                data.get("created_at", "") >= (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")):
                candidates.append((f, data))
        except:
            continue

    if not candidates:
        send_reply(reply_target, "暂无新的高价值知识可滴灌")
        return

    path, entry = random.choice(candidates)
    # 用 Flash 生成一句话摘要
    from src.utils.model_gateway import get_model_gateway
    gw = get_model_gateway()
    result = gw.call("gemini_2_5_flash",
        f"用一句话总结这条知识的核心价值（30字以内）:\n{entry.get('title','')}: {entry.get('content','')[:300]}",
        task_type="quick_summary")
    if result.get("success"):
        send_reply(reply_target, f"💡 你知道吗：{result['response'].strip()}")
        dripped.add(str(path))
        dripped_path.write_text(json.dumps(list(dripped)[-500:], ensure_ascii=False), encoding='utf-8')
    else:
        send_reply(reply_target, f"💡 你知道吗：{entry.get('title','')}")


def _handle_action_items(reply_target: str, send_reply):
    """显示待办事项"""
    items_path = PROJECT_ROOT / ".ai-state" / "action_items.jsonl"
    if not items_path.exists():
        send_reply(reply_target, "📋 暂无待办事项")
        return

    try:
        items = []
        for line in items_path.read_text(encoding='utf-8').strip().split('\n')[-10:]:
            if line.strip():
                items.append(json.loads(line))

        if not items:
            send_reply(reply_target, "📋 暂无待办事项")
            return

        lines = ["📋 待办事项\n"]
        for i, item in enumerate(items, 1):
            status = "✅" if item.get("done") else "⬜"
            lines.append(f"{i}. {status} {item.get('action', '')[:50]}")
        send_reply(reply_target, "\n".join(lines))
    except Exception as e:
        _safe_reply_error(send_reply, reply_target, "读取", e)


def _handle_due_diligence(decision_id: str, reply_target: str, send_reply):
    """应知清单 — 检查决策所需知识是否完备"""
    send_reply(reply_target, f"📋 正在检查应知清单: {decision_id}...")

    def _run():
        try:
            import yaml as _yaml
            from src.tools.knowledge_base import search_knowledge
            gw = get_model_gateway()

            # 标准 checklist 维度
            checklist = [
                ("技术可行性", "技术方案 实现 验证"),
                ("供应链可靠性", "供应商 产能 交期"),
                ("BOM成本", "BOM 成本 报价"),
                ("专利风险", "专利 IP 授权"),
                ("用户接受度", "用户 调研 需求"),
                ("安全认证", "认证 标准 合规"),
                ("售后维修", "售后 维修 保修"),
                ("竞品应对", "竞品 对比 策略"),
            ]

            results = []
            for dimension, keywords in checklist:
                kb = search_knowledge(f"{decision_id} {keywords}", limit=3)
                status = "✅" if len(kb) >= 2 else "❌"
                results.append(f"{status} {dimension}: {len(kb)} 条知识")

            send_reply(reply_target, f"📋 应知清单\n\n" + "\n".join(results))
        except Exception as e:
            _safe_reply_error(send_reply, reply_target, "应知清单检查", e)

    threading.Thread(target=_run, daemon=True).start()


def _handle_output_diff(output_id: str, reply_target: str, send_reply):
    """产出版本 Diff"""
    versions_dir = PROJECT_ROOT / ".ai-state" / "output_versions"
    if not versions_dir.exists():
        send_reply(reply_target, "暂无版本记录")
        return

    # 找到相关版本文件
    files = sorted(versions_dir.glob(f"*{output_id}*.md"))[-2:]
    if len(files) < 2:
        send_reply(reply_target, f"版本记录不足（只有 {len(files)} 个版本）")
        return

    try:
        v1 = files[-2].read_text(encoding='utf-8')
        v2 = files[-1].read_text(encoding='utf-8')

        from src.utils.model_gateway import get_model_gateway
        gw = get_model_gateway()
        result = gw.call("gemini_2_5_flash",
            f"对比两个版本的核心差异（简洁列出 3-5 点）:\n\n版本1:\n{v1[:2000]}\n\n版本2:\n{v2[:2000]}",
            task_type="compare")
        if result.get("success"):
            send_reply(reply_target, f"📊 版本差异\n\n{result['response']}")
        else:
            send_reply(reply_target, "对比失败")
    except Exception as e:
        _safe_reply_error(send_reply, reply_target, "Diff对比", e)


def _handle_hud_design_spec(reply_target: str, send_reply):
    """HUD 设计规范生成器"""
    send_reply(reply_target, "📐 正在生成 HUD 设计规范...")

    def _run():
        try:
            from src.utils.model_gateway import get_model_gateway
            from src.tools.knowledge_base import search_knowledge
            gw = get_model_gateway()

            # 搜索相关约束
            kb_results = search_knowledge("HUD 显示 布局 人因 视野", limit=15)
            kb_text = "\n".join([f"- {r.get('title','')}: {r.get('content','')[:200]}" for r in kb_results])

            prompt = (
                f"基于以下知识，生成 HUD 显示设计规范。\n\n"
                f"## 相关知识\n{kb_text}\n\n"
                f"## 要求\n"
                f"1. 信息布局规范（各信息位置）\n"
                f"2. 色彩方案（日间/夜间）\n"
                f"3. 字体大小规范（基于视距）\n"
                f"4. 动画规范（过渡时间）\n"
                f"5. 信息优先级\n"
            )

            result = gw.call("gpt_5_4", prompt, "你是 HUD 设计专家。", "content_generation")
            if result.get("success"):
                send_reply(reply_target, result["response"])
            else:
                send_reply(reply_target, f"生成失败: {result.get('error', '')[:200]}")
        except Exception as e:
            _safe_reply_error(send_reply, reply_target, "内容生成", e)

    threading.Thread(target=_run, daemon=True).start()


def _handle_demo_script(reply_target: str, send_reply):
    """Demo 场景脚本生成器"""
    send_reply(reply_target, "🎬 正在生成 Demo 场景脚本...")

    def _run():
        try:
            from src.utils.model_gateway import get_model_gateway
            from src.tools.knowledge_base import search_knowledge
            gw = get_model_gateway()

            # 从 KB 搜索 PRD 和场景信息
            kb_results = search_knowledge("PRD 功能 场景 用户", limit=10)
            kb_text = "\n".join([f"- {r.get('title','')}: {r.get('content','')[:200]}" for r in kb_results])

            prompt = (
                f"基于以下产品知识，生成 Demo 场景脚本。\n\n"
                f"## 产品知识\n{kb_text}\n\n"
                f"## 要求\n"
                f"1. 提取 5-8 个核心场景\n"
                f"2. 每个场景：场景名称 + 用户动作 + 系统响应 + 预期效果\n"
                f"3. 场景间有逻辑连贯性\n"
                f"4. 适合 Demo 演示（每个场景 30-60 秒）\n"
            )

            result = gw.call("gpt_5_4", prompt, "你是产品演示专家。", "content_generation")
            if result.get("success"):
                send_reply(reply_target, result["response"])
            else:
                send_reply(reply_target, f"生成失败: {result.get('error', '')[:200]}")
        except Exception as e:
            _safe_reply_error(send_reply, reply_target, "内容生成", e)

    threading.Thread(target=_run, daemon=True).start()


def _handle_set_deadline(decision_id: str, deadline: str, reply_target: str, send_reply):
    """设置决策截止日"""
    try:
        import yaml as _yaml
        dt_path = PROJECT_ROOT / ".ai-state" / "product_decision_tree.yaml"
        if not dt_path.exists():
            send_reply(reply_target, "决策树文件不存在")
            return

        dt = _yaml.safe_load(dt_path.read_text(encoding='utf-8'))
        for d in dt.get("decisions", []):
            if decision_id.lower() in d.get("id", "").lower():
                d["deadline"] = deadline
                dt_path.write_text(_yaml.dump(dt, allow_unicode=True), encoding='utf-8')
                send_reply(reply_target, f"✅ 已设置截止日: {d.get('question', '')[:30]} → {deadline}")
                return

        send_reply(reply_target, f"未找到决策: {decision_id}")
    except Exception as e:
        _safe_reply_error(send_reply, reply_target, "设置操作", e)


def _handle_self_check(reply_target: str, send_reply):
    """系统自检"""
    send_reply(reply_target, "🔍 开始系统自检...")

    def _run():
        try:
            from scripts.self_heal import run_self_heal_cycle
            run_self_heal_cycle(send_reply=send_reply, reply_target=reply_target)
        except ImportError:
            # 如果 self_heal 不存在，做基础检查
            results = ["🔍 系统自检结果\n"]

            # KB 检查
            try:
                from src.tools.knowledge_base import get_knowledge_stats
                stats = get_knowledge_stats()
                total = sum(stats.values())
                results.append(f"✅ 知识库: {total} 条")
            except:
                results.append("❌ 知识库异常")

            # 模型网关检查
            try:
                from src.utils.model_gateway import get_model_gateway
                gw = get_model_gateway()
                results.append("✅ 模型网关正常")
            except:
                results.append("❌ 模型网关异常")

            # 目录结构检查
            required_dirs = [".ai-state", "knowledge_base"]
            for d in required_dirs:
                if (PROJECT_ROOT / d).exists():
                    results.append(f"✅ {d}/ 存在")
                else:
                    results.append(f"❌ {d}/ 缺失")

            send_reply(reply_target, "\n".join(results))
        except Exception as e:
            _safe_reply_error(send_reply, reply_target, "自检", e)

    threading.Thread(target=_run, daemon=True).start()


def _handle_deep_drill(topic: str, reply_target: str, send_reply):
    """深钻模式 — 对单个主题多轮深入研究"""
    if not topic:
        send_reply(reply_target, "请指定研究主题，如：深钻 歌尔产能")
        return

    send_reply(reply_target, f"🔬 开始深钻研究：{topic}\n预计 5-15 分钟...")

    def _run():
        try:
            from scripts.tonight_deep_research import deep_drill
            result = deep_drill(topic, progress_callback=lambda msg: send_reply(reply_target, msg))
            send_reply(reply_target, f"✅ 深钻完成\n\n{result[:500]}...")
        except Exception as e:
            _safe_reply_error(send_reply, reply_target, "深钻研究", e)

    threading.Thread(target=_run, daemon=True).start()


def _handle_sandbox_what_if(scenario: str, reply_target: str, send_reply):
    """沙盘推演 — 参数变更影响分析"""
    if not scenario:
        send_reply(reply_target, "请指定推演场景，如：沙盘 电池改成1500mAh")
        return

    send_reply(reply_target, f"🎯 沙盘推演：{scenario[:50]}...")

    def _run():
        try:
            from scripts.tonight_deep_research import sandbox_what_if
            from src.tools.knowledge_base import format_knowledge_for_prompt, search_knowledge
            # 获取 KB 上下文
            kb_entries = search_knowledge(scenario, limit=5)
            kb_context = format_knowledge_for_prompt(kb_entries) if kb_entries else ""
            result = sandbox_what_if(scenario, kb_context)
            send_reply(reply_target, result[:1500] if result else "推演失败")
        except Exception as e:
            _safe_reply_error(send_reply, reply_target, "沙盘推演", e)

    threading.Thread(target=_run, daemon=True).start()


def _handle_stress_test(reply_target: str, send_reply):
    """产品方案压力测试"""
    send_reply(reply_target, "💪 开始产品方案压力测试...")

    def _run():
        try:
            from scripts.tonight_deep_research import stress_test_product
            # 读取产品定义
            product_def_path = PROJECT_ROOT / ".ai-state" / "product_definition.md"
            plan = ""
            if product_def_path.exists():
                plan = product_def_path.read_text(encoding="utf-8")
            if not plan:
                send_reply(reply_target, "⚠️ 未找到产品定义文件，请先上传产品方案")
                return
            result = stress_test_product(plan)
            send_reply(reply_target, result[:2000] if result else "压力测试失败")
        except Exception as e:
            _safe_reply_error(send_reply, reply_target, "压力测试", e)

    threading.Thread(target=_run, daemon=True).start()


def _handle_generate_demo(demo_type: str, reply_target: str, reply_type: str, open_id: str, send_reply):
    """Demo 全自主生成流水线"""
    send_reply(reply_target, f"🚀 开始自主生成 {demo_type.upper()} Demo...\n预计 5-10 分钟")

    def _run():
        try:
            from src.utils.model_gateway import get_model_gateway
            from src.tools.knowledge_base import search_knowledge
            gw = get_model_gateway()

            # Step 1: 检查前置信息
            send_reply(reply_target, "📚 检查设计信息...")
            prerequisites = _ensure_demo_prerequisites(demo_type, gw)

            # Step 2: 生成设计规范
            send_reply(reply_target, "📐 生成设计规范...")
            design_spec = _generate_demo_design_spec(demo_type, prerequisites, gw)

            # Step 3: 生成 Demo 代码
            send_reply(reply_target, "💻 生成 Demo 代码...")
            html_code = _generate_demo_code(demo_type, design_spec, gw)

            # Step 4: 保存 Demo 文件
            demo_dir = PROJECT_ROOT / ".ai-state" / "demos"
            demo_dir.mkdir(parents=True, exist_ok=True)
            import time
            timestamp = int(time.time())
            html_path = demo_dir / f"{demo_type}_demo_{timestamp}.html"
            html_path.write_text(html_code, encoding='utf-8')

            # Step 5: 发送结果
            send_reply(reply_target, f"✅ Demo 生成完成\n文件: {html_path}")

            # Step 6: 进入迭代模式
            _demo_sessions[open_id] = {
                "type": demo_type,
                "html_path": str(html_path),
                "design_spec_text": str(design_spec),
                "version": 1,
            }
            send_reply(reply_target, "Demo 已进入迭代模式。你可以直接说修改意见，如\"导航箭头改大一点\"。说\"退出Demo\"结束。")

        except Exception as e:
            _safe_reply_error(send_reply, reply_target, "Demo生成", e)

    threading.Thread(target=_run, daemon=True).start()


def _ensure_demo_prerequisites(demo_type: str, gw) -> dict:
    """检查并补齐 Demo 生成所需的前置信息"""
    from src.tools.knowledge_base import search_knowledge, add_knowledge

    required_knowledge = {
        "hud": [
            ("HUD 信息布局规范", "HUD layout specification display position"),
            ("HUD 色彩方案", "HUD color scheme helmet visor daylight night"),
            ("HUD 信息优先级", "HUD information priority navigation speed call"),
        ],
        "app": [
            ("App 配对流程", "smart helmet app pairing bluetooth flow"),
            ("App 骑行仪表盘", "motorcycle riding dashboard UI speedometer"),
        ],
    }

    results = {}
    for topic, search_query in required_knowledge.get(demo_type, []):
        kb_results = search_knowledge(topic, limit=3)
        if len(kb_results) >= 2:
            results[topic] = kb_results
        else:
            # 自动补齐
            quick_result = gw.call("gemini_2_5_flash", f"快速搜索: {search_query}", task_type="quick_search")
            if quick_result.get("success"):
                add_knowledge(title=f"[Demo准备] {topic}", domain="components",
                             content=quick_result["response"], tags=["demo_prep"],
                             source="auto_demo_prep", confidence="medium")
                results[topic] = [{"content": quick_result["response"]}]

    return results


def _generate_demo_design_spec(demo_type: str, prerequisites: dict, gw) -> dict:
    """生成 Demo 设计规范"""
    kb_text = "\n".join([f"- {k}: {str(v)[:300]}" for k, v in prerequisites.items()])

    result = gw.call("gpt_5_4",
        f"为 {demo_type.upper()} Demo 生成设计规范。\n\n"
        f"## 相关知识\n{kb_text}\n\n"
        f"## 要求\n"
        f"输出 JSON 格式的设计规范，包含:\n"
        f"- layout: 布局结构\n"
        f"- colors: 色彩方案\n"
        f"- fonts: 字体规范\n"
        f"- animations: 动画规范\n"
        f"- components: 组件列表\n",
        "输出纯 JSON，不要其他内容。", "content_generation")

    if result.get("success"):
        import re
        resp = result["response"].strip()
        resp = re.sub(r'^```json\s*', '', resp)
        resp = re.sub(r'\s*```$', '', resp)
        try:
            return json.loads(resp)
        except:
            return {"raw": resp}
    return {}


def _generate_demo_code(demo_type: str, design_spec: dict, gw) -> str:
    """生成 Demo HTML 代码"""
    spec_text = json.dumps(design_spec, ensure_ascii=False, indent=2) if isinstance(design_spec, dict) else str(design_spec)

    result = gw.call("gpt_5_4",
        f"生成 {demo_type.upper()} Demo 的完整 HTML 代码。\n\n"
        f"## 设计规范\n{spec_text}\n\n"
        f"## 要求\n"
        f"1. 单文件 HTML，内嵌 CSS 和 JS\n"
        f"2. 响应式设计\n"
        f"3. 动画流畅\n"
        f"4. 适合演示\n\n"
        f"只输出 HTML 代码，不要其他内容。",
        "你是前端工程师。", "code_generation")

    if result.get("success"):
        code = result["response"].strip()
        # 提取 HTML
        if "<html" in code.lower():
            import re
            match = re.search(r'<html[^>]*>[\s\S]*</html>', code, re.IGNORECASE)
            if match:
                return match.group()
        return code
    return "<html><body>Demo generation failed</body></html>"


def _handle_demo_iteration(text: str, open_id: str, reply_target: str, send_reply):
    """处理 Demo 迭代修改请求"""
    session = _demo_sessions.get(open_id)
    if not session:
        send_reply(reply_target, "⚠️ 没有正在进行的 Demo")
        return

    html_path = Path(session["html_path"])
    if not html_path.exists():
        send_reply(reply_target, "⚠️ Demo 文件不存在")
        return

    current_code = html_path.read_text(encoding='utf-8')
    send_reply(reply_target, f"🔄 修改 Demo v{session['version']}...")

    def _run():
        try:
            from src.utils.model_gateway import get_model_gateway
            gw = get_model_gateway()

            result = gw.call("gpt_5_4",
                f"以下是当前 Demo 的 HTML 代码:\n\n```html\n{current_code[:10000]}\n```\n\n"
                f"用户要求修改: {text}\n\n"
                f"请输出修改后的完整 HTML 代码。只改用户要求的部分，保持其他不变。",
                "你是前端工程师，精确修改 UI。", "code_generation")

            if result.get("success"):
                import re
                new_code = result["response"]
                if "<html" in new_code.lower():
                    match = re.search(r'<html[^>]*>[\s\S]*</html>', new_code, re.IGNORECASE)
                    if match:
                        new_code = match.group()

                # 保存新版本
                new_version = session["version"] + 1
                new_path = html_path.parent / f"{session['type']}_demo_v{new_version}.html"
                new_path.write_text(new_code, encoding='utf-8')

                # 更新 session
                session["html_path"] = str(new_path)
                session["version"] = new_version

                send_reply(reply_target, f"✅ Demo v{new_version} 已更新（基于你的修改: {text[:30]}）")
            else:
                send_reply(reply_target, f"修改失败: {result.get('error', '')[:200]}")
        except Exception as e:
            _safe_reply_error(send_reply, reply_target, "Demo修改", e)

    threading.Thread(target=_run, daemon=True).start()


def _smart_route_and_reply(text: str, open_id: str, chat_id: str, reply_target: str, reply_type: str,
                           send_reply, session_id: str = None, mem=None):
    """智能路由和回复"""
    try:
        from src.utils.model_gateway import get_model_gateway
        from src.tools.knowledge_base import search_knowledge, format_knowledge_for_prompt

        # 搜索知识库
        kb_entries = search_knowledge(text, limit=5)
        kb_context = format_knowledge_for_prompt(kb_entries) if kb_entries else ""
        kb_used = bool(kb_context)  # 标记是否使用了 KB 数据

        # 构建 prompt
        prompt = text
        if kb_context:
            prompt = f"相关知识：\n{kb_context[:1500]}\n\n用户问题：{text}"

        gateway = get_model_gateway()
        result = gateway.call_azure_openai("cpo", prompt, "", "chat")

        if result.get("success"):
            reply_text = result["response"]
            # 如果使用了 KB 数据，追加反馈提示
            if kb_used:
                reply_text += "\n\n📊 这个回答准确吗？回复 👍 或 👎"
            send_reply(reply_target, reply_text)
            # 记录本次回答供反馈使用
            _last_kb_answer[open_id or "default"] = {
                "question": text[:100],
                "kb_entries": [e.get("id", "") for e in (kb_entries or [])],
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M")
            }
        else:
            send_reply(reply_target, "抱歉，我暂时无法回答这个问题。")

    except Exception as e:
        _safe_reply_error(send_reply, reply_target, "智能对话", e)


# 记录最近一次 KB 回答（用于反馈）
_last_kb_answer = {}


def _handle_answer_feedback(text: str, open_id: str, reply_target: str, send_reply):
    """处理回答反馈（👍/👎）"""
    last_answer = _last_kb_answer.get(open_id or "default")
    if not last_answer:
        send_reply(reply_target, "⚠️ 没有可评价的回答")
        return

    feedback = "positive" if "👍" in text else "negative" if "👎" in text else None
    if not feedback:
        return  # 不是反馈

    try:
        from src.tools.knowledge_base import record_answer_feedback
        record_answer_feedback(
            question=last_answer.get("question", ""),
            kb_entry_ids=last_answer.get("kb_entries", []),
            feedback=feedback,
            user_id=open_id
        )
        del _last_kb_answer[open_id or "default"]

        # 更新信任指数（D模块集成）
        try:
            from scripts.trust_tracker import update_trust
            domain = "知识问答"  # 默认领域
            update_trust(domain, feedback == "positive")
        except ImportError:
            pass

        if feedback == "positive":
            send_reply(reply_target, "✅ 感谢反馈！这条知识已标记为有帮助")
        else:
            send_reply(reply_target, "📝 感谢反馈！我会改进这条知识的质量")
    except Exception as e:
        print(f"[Feedback] 记录失败: {e}")
        send_reply(reply_target, "反馈记录失败，但感谢你的意见！")


# === 导出接口 ===
__all__ = [
    "route_text_message",
]