"""
@description: 文本消息路由 - 精确指令路由 + Handler 模块分发
@refactored: 2026-04-08 v2 - 拆分为多个 handler 模块
@last_modified: 2026-04-08
"""
import re
import sys
import json
import threading
from pathlib import Path
from datetime import datetime
from typing import Callable

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# 深度学习待确认状态
_deep_learn_pending = {}

# 知识滴灌开关
_drip_enabled = True


def route_text_message(text: str, reply_target: str, reply_type: str, open_id: str, chat_id: str,
                       send_reply: Callable, session_id: str = None, mem=None):
    """
    文本消息路由主入口。

    路由优先级：
    1. 精确指令（commands.py）
    2. Handler 模块（learning/roundtable/import/smart_chat）
    3. 结构化文档快速通道
    4. 智能对话兜底
    """
    from scripts.feishu_handlers.chat_helpers import log
    from scripts.feishu_handlers.commands import handle_command
    from scripts.feishu_handlers import learning_handlers, roundtable_handler, import_handlers, smart_chat

    text_stripped = text.strip()
    log(f"text 路由, 长度={len(text)}")

    # === 1. 新手引导 ===
    _check_first_time_user(open_id, reply_target, send_reply)

    # === 2. 精确指令 ===
    if handle_command(text_stripped, reply_target, reply_type, open_id, chat_id, send_reply):
        return

    # === 3. 帮助 ===
    if text_stripped in ("帮助", "help", "?", "？", "能力", "你能做什么"):
        send_reply(reply_target, _get_full_help_text())
        return

    # === 4. 深度学习时长回复 ===
    if _handle_deep_learning_hours(text_stripped, open_id, reply_target, send_reply):
        return

    # === 5. 校准回复 ===
    if text_stripped and all(c in "0123" for c in text_stripped) and len(text_stripped) <= 10:
        _handle_calibration_reply(text_stripped, reply_target, send_reply)
        return

    # === 6. 回答反馈 ===
    if text_stripped in ("👍", "👎", "👍👍", "👎👎"):
        smart_chat.handle_answer_feedback(text_stripped, open_id, reply_target, send_reply)
        return

    # === 7. Handler 模块分发 ===
    # 7.1 学习相关
    if learning_handlers.try_handle(text_stripped, reply_target, reply_type, open_id, chat_id, send_reply):
        return

    # 7.2 圆桌系统
    if roundtable_handler.try_handle(text_stripped, reply_target, reply_type, open_id, chat_id, send_reply):
        return

    # 7.3 导入相关
    if import_handlers.try_handle(text_stripped, reply_target, reply_type, open_id, chat_id, send_reply):
        return

    # 7.4 智能对话（教练/研发任务）
    if smart_chat.try_handle(text_stripped, reply_target, reply_type, open_id, chat_id, send_reply):
        return

    # === 8. 精确指令（保留核心功能） ===
    # 早报
    if text_stripped in ("早报", "morning", "日报", "daily"):
        _handle_morning_brief(reply_target, send_reply)
        return

    # 状态仪表盘
    if text_stripped in ("状态", "dashboard", "仪表盘", "status"):
        _handle_dashboard(reply_target, send_reply)
        return

    # 产品简介
    if text_stripped in ("产品简介", "one pager", "产品概要"):
        _handle_one_pager(reply_target, send_reply)
        return

    # 决策简报
    if text_stripped.startswith("决策简报") or text_stripped.startswith("decision brief"):
        decision_id = text_stripped.replace("决策简报", "").replace("decision brief", "").strip()
        smart_chat._handle_decision_brief(decision_id, reply_target, send_reply)
        return

    # 谈判准备
    if text_stripped.startswith("谈判准备") or text_stripped.startswith("negotiation"):
        target_name = text_stripped.replace("谈判准备", "").replace("negotiation", "").strip()
        smart_chat._handle_negotiation_brief(target_name, reply_target, send_reply)
        return

    # 知识滴灌
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

    # 知识库统计
    if text_stripped in ("知识库", "kb", "知识库 详细", "kb detailed"):
        detailed = "详细" in text_stripped or "detailed" in text_stripped.lower()
        _handle_kb_stats(reply_target, send_reply, detailed=detailed)
        return

    # KB 治理
    if text_stripped in ("KB治理", "kb治理", "知识库治理"):
        learning_handlers._handle_kb_governance(reply_target, send_reply)
        return

    # 监控范围
    if text_stripped in ("监控范围", "monitor scope", "竞品监控"):
        _handle_monitor_scope(reply_target, send_reply)
        return

    # 自检/验证
    if text_stripped in ("自检", "验证", "self check", "verify"):
        _handle_self_verify(reply_target, send_reply)
        return

    # === 9. 结构化文档快速通道 ===
    try:
        from scripts.feishu_handlers.structured_doc import try_structured_doc_fast_track
        if try_structured_doc_fast_track(text_stripped, reply_target, reply_type, open_id, chat_id, send_reply):
            return
    except ImportError:
        pass

    # === 10. URL 分享处理 ===
    if import_handlers.handle_url_share(text_stripped, open_id, reply_target, reply_type, send_reply):
        return

    # === 11. 长文章导入 ===
    if import_handlers.handle_article_import(text_stripped, open_id, reply_target, send_reply):
        return

    # === 12. 兜底：意图智能路由 ===
    smart_chat.handle_intent_route(text_stripped, open_id, chat_id, reply_target, reply_type, send_reply, session_id, mem)


def _check_first_time_user(open_id: str, reply_target: str, send_reply: Callable):
    """检查是否首次用户，发送引导消息"""
    known_users_file = PROJECT_ROOT / ".ai-state" / "known_users.json"
    user_key = open_id or "default"

    try:
        known_users = {}
        if known_users_file.exists():
            known_users = json.loads(known_users_file.read_text(encoding='utf-8'))

        if user_key not in known_users:
            known_users[user_key] = {"first_seen": datetime.now().strftime("%Y-%m-%d")}
            known_users_file.parent.mkdir(parents=True, exist_ok=True)
            known_users_file.write_text(json.dumps(known_users, ensure_ascii=False, indent=2), encoding='utf-8')
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


def _handle_deep_learning_hours(text_stripped: str, open_id: str, reply_target: str, send_reply: Callable) -> bool:
    """处理深度学习时长回复"""
    pending_key = open_id or "default"
    if not _deep_learn_pending.get(pending_key):
        return False

    try:
        hours = float(text_stripped)
        if hours < 0.5:
            send_reply(reply_target, "⚠️ 最少 0.5 小时")
            return True
        if hours > 12 and not _deep_learn_pending.get(pending_key + "_confirmed"):
            _deep_learn_pending[pending_key + "_confirmed"] = hours
            send_reply(reply_target, f"⚠️ {hours}h 是一次较长的运行，确定吗？回复 Y 确认，其他取消")
            return True

        confirmed_hours = _deep_learn_pending.pop(pending_key + "_confirmed", None)
        if text_stripped.upper() == "Y" and confirmed_hours:
            hours = confirmed_hours

        if pending_key in _deep_learn_pending:
            del _deep_learn_pending[pending_key]

        send_reply(reply_target, f"🎓 启动深度学习（{hours}h 窗口）...")

        def _run():
            try:
                from scripts.tonight_deep_research import run_deep_learning
                completed = run_deep_learning(max_hours=hours, progress_callback=lambda msg: send_reply(reply_target, msg))
                send_reply(reply_target, f"✅ 深度学习完成: {len(completed) if completed else 0} 个任务")
            except Exception as e:
                from scripts.feishu_handlers.chat_helpers import _safe_reply_error
                _safe_reply_error(send_reply, reply_target, "深度学习", e)

        threading.Thread(target=_run, daemon=True).start()
        return True
    except ValueError:
        if pending_key in _deep_learn_pending:
            del _deep_learn_pending[pending_key]
        return False


def _handle_calibration_reply(text: str, reply_target: str, send_reply: Callable):
    """处理 Critic 校准回复"""
    try:
        from scripts.critic_calibration import record_label, _load_pending_samples
        pending = _load_pending_samples()
        if not pending:
            send_reply(reply_target, "⚠️ 没有待校准的样本")
            return

        label_map = {"1": "accurate", "2": "too_loose", "3": "too_strict", "0": "skip"}
        if not all(c in "0123" for c in text):
            send_reply(reply_target, "⚠️ 无效格式，请只使用 0/1/2/3")
            return

        if len(text) == 1:
            latest = pending[-1]
            label = label_map[text]
            success = record_label(latest.get("sample_id", ""), label)
            if success:
                desc = {"accurate": "✅准确", "too_loose": "⬆️偏松", "too_strict": "⬇️偏紧", "skip": "⏭️跳过"}
                send_reply(reply_target, f"✅ 已记录: {desc.get(label, label)}")
            else:
                send_reply(reply_target, "❌ 记录失败")
        else:
            batch = pending[-len(text):]
            if len(text) != len(batch):
                send_reply(reply_target, f"⚠️ 样本数不匹配: 你回复了 {len(text)} 个，但只有 {len(batch)} 个待校准")
                return

            results = []
            desc_map = {"accurate": "✅", "too_loose": "⬆️", "too_strict": "⬇️", "skip": "⏭️"}
            for i, (char, sample) in enumerate(zip(text, batch)):
                label = label_map.get(char, "skip")
                success = record_label(sample.get("sample_id", ""), label)
                results.append(f"{i+1}. {desc_map.get(label, '?')} {sample.get('level', '?')}: {sample.get('issue', '')[:30]}")
            send_reply(reply_target, f"✅ 批量校准完成 ({len(results)} 条)\n" + "\n".join(results))

    except ImportError:
        send_reply(reply_target, "⚠️ 校准模块未安装")
    except Exception as e:
        from scripts.feishu_handlers.chat_helpers import _safe_reply_error
        _safe_reply_error(send_reply, reply_target, "校准处理", e)


def _handle_morning_brief(reply_target: str, send_reply: Callable):
    """生成早报"""
    send_reply(reply_target, "🌅 正在生成早报...")

    def _run():
        try:
            brief = _generate_morning_brief()
            send_reply(reply_target, brief)
        except Exception as e:
            from scripts.feishu_handlers.chat_helpers import _safe_reply_error
            _safe_reply_error(send_reply, reply_target, "早报生成", e)

    threading.Thread(target=_run, daemon=True).start()


def _generate_morning_brief() -> str:
    """生成每日早报"""
    lines = [f"🌅 早报 {datetime.now().strftime('%Y-%m-%d')}\n"]

    # 决策进展
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

    # KB 统计
    try:
        from src.tools.knowledge_base import get_knowledge_stats
        stats = get_knowledge_stats()
        total = sum(stats.values())
        lines.append(f"\n📚 知识库: {total} 条")
    except:
        pass

    return "\n".join(lines)


def _handle_dashboard(reply_target: str, send_reply: Callable):
    """生成系统状态仪表盘（v3: 飞书云文档输出）"""
    status_path = PROJECT_ROOT / ".ai-state" / "system_status.md"

    from scripts.feishu_output import update_doc

    # v3: 优先更新飞书云文档，返回链接
    if status_path.exists():
        try:
            content = status_path.read_text(encoding="utf-8")
            # 去掉 YAML frontmatter（如果有）
            if content.startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    content = parts[2].strip()
            # 更新飞书云文档
            doc_url = update_doc("系统状态", content)
            if doc_url:
                send_reply(reply_target, f"📊 系统状态已更新\n🔗 {doc_url}")
                return
        except Exception as e:
            from scripts.feishu_handlers.chat_helpers import log
            log(f"[状态] 云文档更新失败: {e}")

    # 回退：简化信息（直接消息）
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

    # 今日任务
    try:
        tracker_path = PROJECT_ROOT / ".ai-state" / "task_tracker.jsonl"
        if tracker_path.exists():
            today = datetime.now().strftime('%Y-%m-%d')
            today_tasks = sum(1 for l in tracker_path.read_text(encoding='utf-8').strip().split('\n')
                             if today in l and '"completed"' in l)
            lines.append(f"📝 今日任务: {today_tasks} 个完成")
    except:
        pass

    send_reply(reply_target, "\n".join(lines))


def _handle_one_pager(reply_target: str, send_reply: Callable):
    """生成产品 One-Pager"""
    send_reply(reply_target, "📄 正在生成产品简介...")

    def _run():
        try:
            from scripts.litellm_gateway import get_model_gateway
            from src.tools.knowledge_base import search_knowledge
            gw = get_model_gateway()

            highlights = search_knowledge("智能骑行头盔 V1 核心功能 HUD 导航", limit=10)
            kb_text = "\n".join([f"- {h.get('title','')}: {h.get('content','')[:200]}" for h in highlights])

            prompt = (
                f"基于以下知识库信息，生成一份智能骑行头盔的产品 One-Pager。\n\n"
                f"## 知识库精华\n{kb_text}\n\n"
                f"## 要求\n"
                f"1. 标题 + 一句话副标题\n"
                f"2. 3-4 个核心功能亮点\n"
                f"3. 目标用户和市场定位\n"
            )

            result = gw.call("gpt_5_4", prompt, "你是产品营销专家。", "content_generation")
            if result.get("success"):
                send_reply(reply_target, result["response"])
            else:
                send_reply(reply_target, f"生成失败: {result.get('error', '')[:200]}")
        except Exception as e:
            from scripts.feishu_handlers.chat_helpers import _safe_reply_error
            _safe_reply_error(send_reply, reply_target, "内容生成", e)

    threading.Thread(target=_run, daemon=True).start()


def _handle_drip_knowledge(reply_target: str, send_reply: Callable):
    """推送一条高价值知识滴灌"""
    from src.tools.knowledge_base import KB_ROOT
    import random

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
                str(f) not in dripped):
                candidates.append((f, data))
        except:
            continue

    if not candidates:
        send_reply(reply_target, "暂无新的高价值知识可滴灌")
        return

    path, entry = random.choice(candidates)
    send_reply(reply_target, f"💡 你知道吗：{entry.get('title','')}")
    dripped.add(str(path))
    dripped_path.write_text(json.dumps(list(dripped)[-500:], ensure_ascii=False), encoding='utf-8')


def _handle_kb_stats(reply_target: str, send_reply: Callable, detailed: bool = False):
    """KB 统计"""
    try:
        from src.tools.knowledge_base import get_knowledge_stats
        stats = get_knowledge_stats()
        total = sum(stats.values())
        if detailed:
            lines = [f"📚 知识库统计: {total} 条\n"]
            for domain, count in stats.items():
                lines.append(f"  {domain}: {count}")
            send_reply(reply_target, "\n".join(lines))
        else:
            send_reply(reply_target, f"📚 知识库: {total} 条")
    except Exception as e:
        send_reply(reply_target, f"❌ KB 统计失败: {str(e)[:50]}")


def _handle_monitor_scope(reply_target: str, send_reply: Callable):
    """展示竞品监控 6 层范围"""
    config_path = PROJECT_ROOT / ".ai-state" / "competitor_monitor_config.json"

    if not config_path.exists():
        send_reply(reply_target, "⚠️ 监控配置文件不存在")
        return

    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
        lines = ["🔍 竞品监控范围（6 层）\n"]

        layers = data.get("monitor_layers", {})
        for layer_key, layer_info in layers.items():
            desc = layer_info.get("description", layer_key)
            lines.append(f"\n【{desc}】")

            # 品牌或主题
            if "brands" in layer_info:
                brands = layer_info["brands"]
                lines.append(f"  品牌: {', '.join(brands[:5])}" + ("..." if len(brands) > 5 else ""))
            if "topics" in layer_info:
                topics = layer_info["topics"]
                lines.append(f"  主题: {', '.join(topics[:5])}" + ("..." if len(topics) > 5 else ""))

            # 搜索关键词（取前2个）
            keywords = layer_info.get("search_keywords", [])[:2]
            if keywords:
                lines.append(f"  关键词: {'; '.join(keywords)}")

        # 输出规则
        output_rules = data.get("output_rules", {})
        if output_rules.get("no_update_no_push"):
            lines.append("\n📌 规则: 无更新不推送")
        if output_rules.get("require_substantial_content"):
            lines.append("📌 规则: 需实质性内容")

        send_reply(reply_target, "\n".join(lines))
    except Exception as e:
        send_reply(reply_target, f"❌ 读取监控配置失败: {str(e)[:50]}")


def _handle_self_verify(reply_target: str, send_reply: Callable):
    """触发自动验证（重启 SDK + 发送测试消息）"""
    send_reply(reply_target, "🔄 启动自动验证...\n将重启 SDK 并发送测试消息，预计 30 秒完成。")

    def _run():
        try:
            import subprocess
            verify_script = PROJECT_ROOT / "scripts" / "auto_restart_and_verify.py"
            result = subprocess.run(
                [sys.executable, str(verify_script)],
                cwd=str(PROJECT_ROOT),
                capture_output=True,
                text=True,
                timeout=120
            )
            # 验证脚本会自己发送报告
        except Exception as e:
            send_reply(reply_target, f"❌ 自动验证失败: {str(e)[:100]}")

    threading.Thread(target=_run, daemon=True).start()


def _get_full_help_text() -> str:
    """生成完整指令列表"""
    return """【智能骑行头盔研发助手 - 指令手册】

━━━ 研发类 ━━━
• 深钻 <主题> - 多轮深挖
• 沙盘 <场景> - 场景推演
• 决策简报 <ID> - 决策报告

━━━ 研究类 ━━━
• 深度学习 - 夜间批量研究
• 自学习 - 30分钟探索
• KB治理 - 知识库清洗

━━━ Demo类 ━━━
• 生成 HUD Demo - HUD原型
• 生成 App Demo - App原型

━━━ 知识类 ━━━
• 知识库 - KB统计
• 日报 - 系统日报
• 导入 - 导入知识库

━━━ 系统类 ━━━
• 状态 - 系统状态
• 帮助 - 本指令列表
• 校准 - Critic校准

━━━ 反馈类 ━━━
• 👍 / 👎 - 对回答点赞/踩

提示：直接发送技术问题，我会自动路由到合适的Agent。"""


# 导出接口
__all__ = ["route_text_message", "_handle_morning_brief", "_handle_dashboard"]