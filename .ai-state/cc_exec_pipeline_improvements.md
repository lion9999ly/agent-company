# CC 执行文档: 深度学习管道改进（基于首次实跑观察）

> 日期: 2026-04-01
> 依赖: 所有之前的改造已完成
> 涉及文件:
>   - `scripts/tonight_deep_research.py`（任务去重 + CMO 角色分配 + 汇总报告）
>   - `scripts/critic_calibration.py`（校准方式改为批量摘要卡片）
>   - `scripts/feishu_handlers/text_router.py`（校准回复格式适配）
> 提交: `git add -A && git commit -m "improve: task dedup, batch calibration, CMO assignment, session summary"` + `git push origin main`
> **不要重启服务，Leo 手动重启。**

---

## 改进 1: 任务自主发现去重

### 问题
首次深度学习中，任务 1（HUD显示技术集成与户外性能评估）和任务 5（HUD显示技术选型与头盔集成可行性研究）高度重叠。`_discover_new_tasks()` 没有检查已完成和进行中的任务。

### 修复
在 `_discover_new_tasks()` 的 prompt 中注入已完成任务列表，并在返回结果后做标题相似度去重。

在 `tonight_deep_research.py` 中找到 `_discover_new_tasks()` 函数：

**Step A:** 在 discover_prompt 中，注入已完成和任务池中的任务标题：

```python
    # 收集已有任务标题（用于去重）
    pool = _load_task_pool()
    existing_titles = [t.get("title", "") for t in pool]

    # 已完成的任务（从报告目录扫描）
    reports_dir = Path(__file__).parent.parent / ".ai-state" / "reports"
    if reports_dir.exists():
        for f in reports_dir.glob("*.md"):
            existing_titles.append(f.stem.replace("_", " "))

    existing_titles_text = "\n".join(f"- {t}" for t in existing_titles[-30:])
```

然后在 discover_prompt 中加入：

```
## 已有任务（避免重复）
以下任务已经存在或已完成，不要生成与它们高度重叠的新任务：
{existing_titles_text}

如果你要研究的方向与已有任务重叠超过 50%，请换一个角度或跳过。
```

**Step B:** 在 `_discover_new_tasks()` 返回前，做标题相似度过滤：

```python
    # 去重：新任务标题不能与已有任务过于相似
    deduped = []
    for task in tasks:
        new_title = task.get("title", "")
        is_duplicate = False
        for existing in existing_titles:
            # 简单去重：超过 3 个相同的中文双字词
            new_words = set(re.findall(r'[\u4e00-\u9fff]{2,4}', new_title))
            old_words = set(re.findall(r'[\u4e00-\u9fff]{2,4}', existing))
            overlap = new_words & old_words
            if len(overlap) >= 3 and len(overlap) / max(len(new_words), 1) > 0.5:
                print(f"  [Discover] 去重: '{new_title}' 与 '{existing}' 重叠")
                is_duplicate = True
                break
        if not is_duplicate:
            deduped.append(task)

    print(f"  [Discover] 去重后: {len(tasks)} → {len(deduped)}")
    return deduped
```

---

## 改进 2: Critic 校准改为批量摘要

### 问题
当前每个校准样本单独推送飞书消息，回复 1/2/3 只标注最后一个样本。不方便且容易错位。

### 修复
改为深度学习结束后一次性推送批量摘要卡片，用类似 `11213` 的格式一次性回复。

**Step A:** 在 `scripts/critic_calibration.py` 中，修改 `push_calibration_to_feishu()`：

替换整个函数为：

```python
def push_calibration_to_feishu(samples: list, reply_func=None):
    """推送校准批量摘要到飞书（不再逐条推送）

    改为只保存到 pending，等 push_batch_calibration_summary() 统一推送。
    """
    if not samples:
        return
    save_pending_samples(samples)
    # 不再逐条推送，等深度学习结束后统一推送


def push_batch_calibration_summary(reply_func=None):
    """深度学习结束后，一次性推送批量校准摘要

    格式:
    🎯 今晚 Critic 校准（N 个样本）
    1⃣ [P0] 任务名: 挑战摘要
    2⃣ [P1] 任务名: 挑战摘要
    ...
    回复格式: 11213（依次对应每个样本，1=准确 2=偏松 3=偏紧 0=跳过）
    """
    pending = _load_pending_samples()
    if not pending or not reply_func:
        return

    # 只取最近一批（最多 10 个）
    batch = pending[-10:]

    lines = [f"🎯 Critic 校准（{len(batch)} 个样本）\n"]
    emojis = ["1⃣", "2⃣", "3⃣", "4⃣", "5⃣", "6⃣", "7⃣", "8⃣", "9⃣", "🔟"]

    for i, s in enumerate(batch):
        emoji = emojis[i] if i < len(emojis) else f"({i+1})"
        issue_short = s.get("issue", "")[:60]
        task_short = s.get("task_title", "")[:20]
        lines.append(f"{emoji} [{s.get('level', '?')}] {task_short}: {issue_short}")

    lines.append("")
    lines.append("回复格式: " + "x" * len(batch) + "（依次对应每个样本）")
    lines.append("1=✅准确  2=⬆️偏松  3=⬇️偏紧  0=跳过")
    lines.append(f"例如: {'1' * len(batch)} 表示全部准确")
    lines.append(f"\n[batch_cal:{len(batch)}]")  # 标记供 text_router 识别

    msg = "\n".join(lines)
    try:
        reply_func(msg)
    except Exception as e:
        print(f"  [Calibration] 批量摘要推送失败: {e}")
```

**Step B:** 在 `scripts/feishu_handlers/text_router.py` 中，修改 `_handle_calibration_reply()`：

替换整个函数为：

```python
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
```

**Step C:** 修改 text_router.py 中校准入口的判断条件：

找到：
```python
    if text_stripped in ("1", "2", "3", "0"):
```

替换为：
```python
    if text_stripped and all(c in "0123" for c in text_stripped) and len(text_stripped) <= 10:
```

---

## 改进 3: CMO 角色分配

### 问题
5 个任务中有 3 个只分配了 CTO+CDO，没有 CMO。CMO 用的是 doubao_seed_pro，擅长中文市场信息。

### 修复
在角色分配逻辑中，确保 CMO 在大多数任务中被包含。找到角色分配相关代码（搜索 `Participants` 或 `_assign_roles` 或 roles 赋值的位置），确保：

```python
# CMO 应该在以下情况都参与:
# - 任务涉及市场、供应链、竞品、成本、商业模式
# - 任务涉及中文信息源（小红书、B站、知乎）
# - 默认 3 Agent（CTO+CMO+CDO）全参与，除非任务明确是纯技术或纯设计

# 如果当前逻辑是 LLM 判断角色分配，在 prompt 中强调：
# "默认分配 CTO+CMO+CDO 全部三个角色，除非任务内容与某个角色完全无关。
#  CMO 擅长中文互联网搜索和市场分析，大部分任务都应该包含 CMO。"
```

CC 需要先搜索角色分配的具体实现位置（grep `roles` 和 `Participants` 和 `assign`），然后在分配逻辑中强化 CMO 的默认参与。

---

## 改进 4: 深度学习结束汇总报告

### 问题
跑完一夜，飞书上只有零散进度消息，没有整体汇总。

### 修复
在 `run_deep_learning()` 的收尾部分，`_run_post_session()` 或等效位置，生成并推送汇总报告：

```python
    # === 深度学习汇总报告 ===
    from src.tools.knowledge_base import get_knowledge_stats

    kb_stats_after = get_knowledge_stats()
    kb_total_after = sum(kb_stats_after.values())

    summary_lines = [
        f"📊 深度学习完成报告",
        f"",
        f"⏱️ 耗时: {total_hours:.1f}h / {max_hours}h",
        f"📝 任务: {len(completed)} 个完成",
    ]

    for c in completed:
        summary_lines.append(f"  • {c['title']} ({c.get('duration_min', '?')}min)")

    summary_lines.append(f"")
    summary_lines.append(f"📚 KB 变化: {kb_total_before} → {kb_total_after} (+{kb_total_after - kb_total_before})")

    # Critic 统计
    p0_total = sum(1 for c in completed if c.get("p0_count", 0) > 0)
    summary_lines.append(f"🔍 Critic: {p0_total}/{len(completed)} 个任务触发 P0")

    # 元能力层统计
    try:
        from scripts.meta_capability import load_registry
        reg = load_registry()
        new_tools = [t for t in reg.get("tools", [])
                     if t.get("installed_at", "").startswith(time.strftime('%Y-%m-%d'))]
        if new_tools:
            summary_lines.append(f"🧬 元能力进化: +{len(new_tools)} 个新工具")
            for t in new_tools:
                summary_lines.append(f"  • {t['name']}: {t.get('description', '')[:40]}")
    except:
        pass

    # KB 治理
    if gov_report:
        summary_lines.append(f"🗄️ KB 治理: {gov_report}")

    summary = "\n".join(summary_lines)

    if progress_callback:
        progress_callback(summary)

    # 推送批量校准摘要
    try:
        from scripts.critic_calibration import push_batch_calibration_summary
        push_batch_calibration_summary(reply_func=progress_callback)
    except:
        pass
```

注意：需要在 `run_deep_learning()` 开头记录 KB 初始状态：

```python
    from src.tools.knowledge_base import get_knowledge_stats
    kb_stats_before = get_knowledge_stats()
    kb_total_before = sum(kb_stats_before.values())
```

同时，`completed` 列表中的每个条目需要记录 `p0_count`。在每个任务完成后，从 Critic 结果中提取 P0 数量：

```python
    completed.append({
        "title": task["title"],
        "duration_min": round(task_duration, 1),
        "report_len": len(report),
        "p0_count": task.get("_p0_count", 0),  # 从 Critic 结果传入
    })
```

---

## 改进 5: 元能力层触发通知

### 问题
元能力层自主创建了 `windnoise_hud_power_gap_filler` 工具，但飞书没有任何通知。

### 修复
在 `scripts/meta_capability.py` 的 `resolve_capability_gap()` 函数中，成功注册工具后，如果有飞书回调，推送通知。

找到 `register_tool(...)` 调用的位置，在之后添加：

```python
    # 推送飞书通知（如果有回调）
    if verified and hasattr(resolve_capability_gap, '_feishu_callback'):
        callback = resolve_capability_gap._feishu_callback
        if callback:
            try:
                callback(f"🧬 元能力进化: 新增工具 [{plan.get('tool_name', '')}] — {plan.get('description', '')[:60]}")
            except:
                pass
```

同时在 `tonight_deep_research.py` 调用 `resolve_capability_gap` 之前设置回调：

```python
    from scripts.meta_capability import resolve_capability_gap
    resolve_capability_gap._feishu_callback = progress_callback
```

---

## 执行顺序

1. 改进 1: 任务去重（tonight_deep_research.py）
2. 改进 2: 批量校准（critic_calibration.py + text_router.py）
3. 改进 3: CMO 角色分配（tonight_deep_research.py）
4. 改进 4: 汇总报告（tonight_deep_research.py）
5. 改进 5: 元能力通知（meta_capability.py + tonight_deep_research.py）

```bash
git add -A && git commit -m "improve: task dedup, batch calibration, CMO assignment, session summary, meta-cap notification" && git push origin main
```

**不要重启服务。**
