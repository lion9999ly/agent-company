# CC 执行文档: 五层诊断 P1 改进

> 日期: 2026-04-01
> 依赖: P0 改进先完成
> 涉及: 6 项 P1 改进
> 提交: 合成一次 commit + push

---

## P1-1: 任务状态统一管理

新建 `scripts/deep_research/task_tracker.py`：

```python
"""任务生命周期追踪"""
import json, time
from pathlib import Path

TRACKER_PATH = Path(__file__).parent.parent.parent / ".ai-state" / "task_tracker.jsonl"

def track_event(task_id: str, event: str, **kwargs):
    entry = {"task_id": task_id, "event": event, "timestamp": time.strftime('%Y-%m-%d %H:%M'), **kwargs}
    TRACKER_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(TRACKER_PATH, 'a', encoding='utf-8') as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

def get_recent_tasks(limit: int = 20) -> list:
    if not TRACKER_PATH.exists(): return []
    events = {}
    for line in TRACKER_PATH.read_text(encoding='utf-8').strip().split('\n'):
        try:
            e = json.loads(line)
            tid = e["task_id"]
            if tid not in events: events[tid] = {}
            events[tid][e["event"]] = e
        except: continue
    tasks = []
    for tid, evts in list(events.items())[-limit:]:
        tasks.append({
            "id": tid,
            "title": evts.get("created", evts.get("started", {})).get("title", "?"),
            "status": "completed" if "completed" in evts else "started" if "started" in evts else "created",
            "duration": evts.get("completed", {}).get("duration_min"),
            "p0_count": evts.get("completed", {}).get("p0_count"),
        })
    return tasks
```

在 `run_deep_learning()` 和 `deep_research_one()` 中调用 `track_event()`：
- 任务开始时: `track_event(task_id, "started", title=...)`
- 任务完成时: `track_event(task_id, "completed", duration_min=..., p0_count=..., kb_added=...)`

在 `text_router.py` 中注册"任务状态"指令：
```python
if text_stripped in ("任务状态", "task status"):
    from scripts.deep_research.task_tracker import get_recent_tasks
    tasks = get_recent_tasks(10)
    # 格式化输出
```

---

## P1-2: 连接池

在 `model_gateway.py` 的 `ModelGateway.__init__()` 中：

```python
self._sessions = {
    "azure": requests.Session(),
    "google": requests.Session(),
    "volcengine": requests.Session(),
}
```

在 `call_azure_openai()`、`call_azure_responses()`、`call_gemini()`、`call_volcengine()` 中，把 `requests.post(...)` 替换为 `self._sessions[provider].post(...)`。

---

## P1-3: 分类时效性阈值

在 `scripts/kb_governance.py` 的 `_mark_stale()` 中，替换固定的 `stale_days = 60` 为分类阈值：

```python
STALE_DAYS_BY_TAG = {
    "price": 30, "cost": 30, "BOM": 30, "报价": 30,
    "market_share": 60, "市场": 60,
    "tech_spec": 180, "参数": 180, "spec": 180,
    "standard": 365, "认证": 365, "certification": 365,
    "lesson": 365, "经验": 365,
}

def _get_stale_days(entry: dict) -> int:
    tags = entry.get("tags", [])
    for tag in tags:
        for key, days in STALE_DAYS_BY_TAG.items():
            if key in tag.lower():
                return days
    return 90  # 默认 90 天
```

---

## P1-4: 自动 confidence 评估

在 `scripts/deep_research/distill.py`（或 `tonight_deep_research.py` 中 `_extract_structured_data` 所在位置），在提炼 prompt 中增加 confidence 评估指引：

在提炼 prompt 末尾追加：
```
对每个数据点评估 confidence:
- "high": 引用了具体型号、厂商官方数据表、价格表、认证文档
- "medium": 引用了新闻报道、分析师估算、二手评测
- "low": 无明确来源、基于推理或假设
```

---

## P1-5: KB 软删除

在 `scripts/kb_governance.py` 中，替换 `_safe_delete()`：

```python
TRASH_DIR = KB_ROOT.parent / "knowledge_trash"

def _safe_delete(path: str, reason: str = ""):
    """软删除：移到 trash 目录而不是删除"""
    try:
        src = Path(path)
        if not src.exists(): return
        TRASH_DIR.mkdir(parents=True, exist_ok=True)
        dest = TRASH_DIR / f"{time.strftime('%Y%m%d')}_{src.name}"
        src.rename(dest)
        # 记录删除原因
        meta = dest.with_suffix('.delete_meta')
        meta.write_text(json.dumps({
            "original_path": str(path),
            "deleted_at": time.strftime('%Y-%m-%d %H:%M'),
            "reason": reason
        }, ensure_ascii=False), encoding='utf-8')
    except Exception as e:
        print(f"  [KB] 软删除失败: {e}")
```

更新所有调用 `_safe_delete(path)` 的地方，传入 reason 参数。

---

## P1-6: Watchdog 自动重启

创建 `scripts/watchdog.py`：

```python
"""进程监控 — 检查飞书连接心跳，超时自动重启"""
import time, subprocess, sys
from pathlib import Path

HEARTBEAT_FILE = Path(__file__).parent.parent / ".ai-state" / "heartbeat.txt"
MAX_SILENT_SECONDS = 300  # 5 分钟无心跳视为死亡
CHECK_INTERVAL = 60

def watch():
    print("[Watchdog] 启动监控")
    while True:
        time.sleep(CHECK_INTERVAL)
        if HEARTBEAT_FILE.exists():
            last_beat = HEARTBEAT_FILE.stat().st_mtime
            silent = time.time() - last_beat
            if silent > MAX_SILENT_SECONDS:
                print(f"[Watchdog] 心跳超时 ({silent:.0f}s)，重启服务...")
                # 重启飞书服务
                subprocess.Popen([sys.executable, "scripts/feishu_sdk_client.py"],
                                 cwd=str(Path(__file__).parent.parent))
        else:
            print("[Watchdog] 心跳文件不存在，等待...")

if __name__ == "__main__":
    watch()
```

在 `feishu_sdk_client.py` 的主循环中，定期写入心跳：

搜索飞书消息处理的主循环（lark SDK 的回调注册处），在消息接收成功时更新心跳：
```python
HEARTBEAT_FILE.write_text(str(time.time()), encoding='utf-8')
```

---

## P1-7: API 用量日报

在 `src/utils/token_usage_tracker.py` 中新增 `generate_daily_report()` 函数。

如果该文件已有日报功能，增强为飞书推送格式。如果没有：

```python
def generate_daily_report(date_str: str = None) -> str:
    """生成指定日期的 API 用量日报"""
    if not date_str:
        date_str = time.strftime('%Y-%m-%d')
    # 从 usage_records.jsonl 中过滤当天记录
    # 按 provider 分组汇总 tokens 和调用次数
    # 返回格式化文本
```

在 `text_router.py` 中注册"用量报告"指令：
```python
if text_stripped in ("用量报告", "用量", "usage", "API用量"):
    from src.utils.token_usage_tracker import generate_daily_report
    report = generate_daily_report()
    send_reply(reply_target, report)
    return
```

---

## 提交

```bash
git add -A && git commit -m "improve: task tracker, connection pool, stale thresholds, auto-confidence, soft-delete, watchdog, usage report" && git push origin main
```

**不要重启服务。**
