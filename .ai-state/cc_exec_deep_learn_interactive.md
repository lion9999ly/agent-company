# CC 执行文档: 深度学习交互式触发

> 日期: 2026-04-01
> 涉及文件: `scripts/feishu_handlers/text_router.py`
> 与 P0-3 / P1 合并 commit 即可

---

## 需求

1. 飞书发"深度学习"后，不直接启动 7h 窗口，而是先问"深度学习几个小时？"
2. 用户回复数字（如 "1.5" 或 "3"）后，用该时长启动深度学习
3. 任务主题避免重复（已有任务去重逻辑，确认它在此流程中生效）

---

## 修改 text_router.py

### Step 1: 添加"等待时长回复"的状态

在文件顶部的全局变量区域，添加：

```python
# 深度学习待确认状态：{open_id: True}
_deep_learn_pending = {}
```

### Step 2: 修改 `_handle_night_learning()`

替换整个函数为：

```python
def _handle_night_learning(reply_target: str, send_reply, open_id: str = ""):
    """处理深度学习指令 — 先询问时长"""
    _deep_learn_pending[open_id or "default"] = True
    send_reply(reply_target, "🎓 深度学习 — 请问跑几个小时？\n\n直接回复数字，如：1.5、3、7")
```

注意：函数签名新增了 `open_id` 参数。

### Step 3: 修改调用处传入 open_id

在 `route_text_message()` 中，找到调用 `_handle_night_learning` 的位置：

```python
    if text_stripped in ("深度学习", "夜间学习", "night learning", "deep learning"):
        _handle_night_learning(reply_target, send_reply, open_id)
        return
```

### Step 4: 在路由入口处拦截时长回复

在 `route_text_message()` 函数中，**校准回复判断之前**（即 `if text_stripped and all(c in "0123" ...` 之前），插入深度学习时长回复的处理：

```python
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

            del _deep_learn_pending[pending_key]
            send_reply(reply_target, f"🎓 启动深度学习（{hours}h 窗口）...")

            def _run():
                try:
                    from scripts.tonight_deep_research import run_deep_learning
                    run_deep_learning(
                        max_hours=hours,
                        progress_callback=lambda msg: send_reply(reply_target, msg)
                    )
                except Exception as e:
                    send_reply(reply_target, f"深度学习执行失败: {e}")

            threading.Thread(target=_run, daemon=True).start()
            return
        except ValueError:
            # 不是数字，清除 pending 状态，继续正常路由
            del _deep_learn_pending[pending_key]
            # 不 return，让后续路由继续处理这条消息
```

### Step 5: 确认任务去重在此流程中生效

`run_deep_learning()` 内部调用 `_discover_new_tasks()`，其中已有任务去重逻辑（commit 8d50cec）。确认 `_discover_new_tasks()` 中的去重代码包含：
- 检查已完成任务标题（从 reports 目录）
- 检查任务池中已有标题
- 标题相似度过滤（中文双字词重叠 > 50% 判定为重复）

如果这些逻辑存在，不需要额外修改。如果不存在（CC 检查确认），按 `cc_exec_pipeline_improvements.md` 中改进 1 的方案补上。

---

## 验证

重启后在飞书测试：
1. 发送"深度学习" → 应回复"请问跑几个小时？"
2. 回复"1.5" → 应直接回复"启动深度学习（1.5h 窗口）..."
3. 回复"24" → 应回复"24h 是一次较长的运行，确定吗？回复 Y 确认"
4. 回复"Y" → 应启动 24h 深度学习
5. 回复"abc" → 应清除等待状态，正常路由
6. 回复"0.1" → 应提示"最少 0.5 小时"

---

## 提交

```bash
git add -A && git commit -m "improve: deep learning interactive trigger with duration prompt" && git push origin main
```

**不要重启服务。**
