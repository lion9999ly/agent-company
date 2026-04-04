# Phase 2.1 — 长任务进度心跳集成指引

## 新模块位置: `src/utils/progress_heartbeat.py`

---

## 集成模式

### 模式 A：已有 progress_callback 参数的脚本

`daily_learning.py`、`tonight_deep_research.py` 等已经有 `progress_callback` 参数，
只需在循环中替换为 ProgressHeartbeat：

```python
# 原
def run_daily_learning(progress_callback=None):
    for i, topic in enumerate(topics):
        result = search_and_learn(topic)
        if progress_callback:
            progress_callback(f"[{i+1}/{len(topics)}] {topic['query']}")

# 改
def run_daily_learning(progress_callback=None):
    from src.utils.progress_heartbeat import ProgressHeartbeat
    hb = ProgressHeartbeat(
        "每日学习",
        total=len(topics),
        feishu_callback=progress_callback,
        log_interval=5,
        feishu_interval=10,       # 每 10 个主题推一次飞书
        feishu_time_interval=180  # 或至少每 3 分钟推一次
    )
    for i, topic in enumerate(topics):
        try:
            result = search_and_learn(topic)
            hb.tick(detail=topic['query'], success=bool(result))
        except Exception as e:
            hb.tick(detail=f"失败: {topic['query']}: {e}", success=False)
    hb.finish(f"新增 {new_count} 条知识")
```

### 模式 B：批量处理脚本

`overnight_kb_overhaul.py` 的各 Phase 都是批量处理：

```python
# 在每个 Phase 的循环中
hb = ProgressHeartbeat(
    f"大修 Phase {phase_num}: {phase_name}",
    total=len(items),
    feishu_callback=feishu_notify,
    log_interval=10,
    feishu_interval=50,
)
for item in items:
    process(item)
    hb.tick(detail=item.get("title", "")[:40])
hb.finish()
```

### 模式 C：知识图谱扩展（嵌套循环）

`knowledge_graph_expander.py` 有"家族→节点→搜索"的嵌套结构：

```python
# 外层：家族级进度
hb_family = ProgressHeartbeat("知识图谱", total=len(families), feishu_callback=cb,
                               feishu_interval=3)  # 每 3 个家族推一次
for family in families:
    # 内层：节点级进度（只打日志不推飞书）
    hb_node = ProgressHeartbeat(f"  {family['name']}", total=len(family['nodes']),
                                 feishu_callback=None, log_interval=5)
    for node in family['nodes']:
        search_and_store(node)
        hb_node.tick(detail=node['query'][:40])
    hb_node.finish()
    hb_family.tick(detail=family['name'])
hb_family.finish()
```

---

## CC 执行指引

```
请将 src/utils/progress_heartbeat.py 集成到以下脚本中：

1. scripts/daily_learning.py — run_daily_learning() 和 run_night_deep_learning() 的主循环
2. scripts/knowledge_graph_expander.py — run_autonomous_deep_dive() 和内部搜索循环
3. scripts/overnight_kb_overhaul.py — 各 Phase 的处理循环
4. scripts/tonight_deep_research.py — deep_research_one() 的搜索循环

使用模式参考 phase_2.1_heartbeat_guidance.md。
核心要求：
- 每条处理打日志（hb.tick）
- 每 50 条或每 5 分钟推飞书
- 异常时调用 hb.error()
- 不要改变函数签名和返回值
```

---

## 飞书新指令（可选）

在 handle_message 中加一个"长任务状态"指令：

```python
elif text.strip() in ("长任务", "任务状态", "task status"):
    hb_file = Path(__file__).parent.parent / ".ai-state" / "long_task_heartbeat.json"
    if hb_file.exists():
        data = json.loads(hb_file.read_text(encoding="utf-8"))
        status = data.get("status", "unknown")
        name = data.get("task_name", "?")
        current = data.get("current", 0)
        total = data.get("total", 0)
        elapsed = data.get("elapsed_sec", 0)
        pct = f" ({current*100//total}%)" if total > 0 else ""
        send_reply(reply_target,
            f"📊 长任务状态: {name}\n"
            f"状态: {status} | 进度: {current}/{total}{pct}\n"
            f"耗时: {elapsed//60}分钟 | 错误: {data.get('errors', 0)}")
    else:
        send_reply(reply_target, "当前没有运行中的长任务")
```
