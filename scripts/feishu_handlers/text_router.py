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
                    send_reply(reply_target, f"深度学习执行失败: {e}")

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

    # === 3. 学习相关指令 ===
    if text_stripped in ("学习", "每日学习", "daily learning"):
        _handle_daily_learning(reply_target, send_reply)
        return

    if text_stripped in ("重置学习", "reset learning", "重学"):
        _handle_reset_learning(reply_target, send_reply)
        return

    if text_stripped in ("深度学习", "夜间学习", "night learning", "deep learning"):
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
            send_reply(reply_target, f"学习执行失败: {e}")

    threading.Thread(target=_run, daemon=True).start()


def _handle_reset_learning(reply_target: str, send_reply):
    """重置学习覆盖记录"""
    try:
        covered_file = PROJECT_ROOT / ".ai-state" / "covered_topics.json"
        if covered_file.exists():
            covered_file.unlink()
        send_reply(reply_target, "✅ 已重置学习覆盖记录，下次学习将重新搜索所有固定主题")
    except Exception as e:
        send_reply(reply_target, f"重置失败: {e}")


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
            send_reply(reply_target, f"KB 治理失败: {e}")

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
            send_reply(reply_target, f"自学习执行失败: {e}")

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
            send_reply(reply_target, f"对齐报告生成失败: {e}")

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
        send_reply(reply_target, f"❌ 校准异常: {e}")


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
        send_reply(reply_target, f"导入失败: {e}")


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
        send_reply(reply_target, f"导入失败: {e}")


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
            send_reply(reply_target, f"[Research] 执行失败: {e}")
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
            send_reply(reply_target, f"早报生成失败: {e}")

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
            send_reply(reply_target, f"生成失败: {e}")

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

        # 构建 prompt
        prompt = text
        if kb_context:
            prompt = f"相关知识：\n{kb_context[:1500]}\n\n用户问题：{text}"

        gateway = get_model_gateway()
        result = gateway.call_azure_openai("cpo", prompt, "", "chat")

        if result.get("success"):
            send_reply(reply_target, result["response"])
        else:
            send_reply(reply_target, "抱歉，我暂时无法回答这个问题。")

    except Exception as e:
        send_reply(reply_target, f"处理异常: {str(e)[:200]}")


# === 导出接口 ===
__all__ = [
    "route_text_message",
]