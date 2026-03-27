# Day 7 任务指令 — 直接执行，不需要讨论

> 生成时间: 2026-03-24
> 来源: Claude.ai 对话，基于 plan v5.5 + 源码分析
> 执行顺序: 严格按 Task 1 → 2 → 3 → 4 → 5 执行

---

## Task 1: Gemini API 配额耗尽自动降级（P0）

**问题**: Gemini 3.1 Pro RPD 253/250 已打满（公司公用 Paid tier 1）。昨晚 3505 次调用全打在 Pro 上。
**策略**: 不限制自己的使用量，而是配额快满时无缝降级到 Flash / Azure。

### 1.1 在 model_gateway.py 中添加 Gemini 配额感知降级

在 `ModelGateway` 类中，`call_gemini` 方法之前，添加以下属性和方法：

```python
# 在 ModelGateway.__init__ 方法末尾添加：
self._gemini_daily_counter = {}  # {"2026-03-24:gemini-3.1-pro": 150, ...}
self._gemini_consecutive_429 = 0  # 连续 429 计数

# 在 call_gemini 方法之前添加新方法：
def _gemini_rate_key(self, model: str) -> str:
    from datetime import datetime
    return f"{datetime.now().strftime('%Y-%m-%d')}:{model}"

def _should_degrade_gemini(self, model_name: str) -> str:
    """检查是否需要降级 Gemini 调用，返回实际应使用的 model_name 或 None"""
    cfg = self.models.get(model_name)
    if not cfg or cfg.provider != "google":
        return model_name  # 非 Gemini，不处理

    model_id = cfg.model
    rate_key = self._gemini_rate_key(model_id)
    count = self._gemini_daily_counter.get(rate_key, 0)

    # 策略：Pro 模型超过 180 次/天（给同事留余量），自动降级
    is_pro = "pro" in model_id.lower() and "flash" not in model_id.lower()
    if is_pro and count >= 180:
        # 尝试降级到 Flash
        flash_candidates = [name for name, c in self.models.items()
                           if c.provider == "google" and "flash" in c.model.lower() and c.api_key]
        if flash_candidates:
            print(f"[Gateway] Gemini Pro 今日 {count} 次，降级到 Flash: {flash_candidates[0]}")
            return flash_candidates[0]
        # Flash 也没有，降级到 Azure
        azure_candidates = [name for name, c in self.models.items()
                           if c.provider == "azure_openai" and c.api_key]
        if azure_candidates:
            print(f"[Gateway] Gemini Pro 今日 {count} 次，降级到 Azure: {azure_candidates[0]}")
            return azure_candidates[0]

    # 连续 429 错误 >= 3 次，强制降级
    if self._gemini_consecutive_429 >= 3:
        azure_candidates = [name for name, c in self.models.items()
                           if c.provider == "azure_openai" and c.api_key]
        if azure_candidates:
            print(f"[Gateway] Gemini 连续 {self._gemini_consecutive_429} 次 429，降级到 Azure")
            return azure_candidates[0]

    return model_name
```

### 1.2 修改 call_gemini 方法

在 `call_gemini` 方法的**开头**（`cfg = self.models.get(model_name)` 之前）添加降级检查：

```python
def call_gemini(self, model_name: str, prompt: str, system_prompt: str = None,
                 task_type: str = "general") -> Dict[str, Any]:
    """调用Google Gemini API"""
    # === 配额感知降级 ===
    actual_model = self._should_degrade_gemini(model_name)
    if actual_model != model_name:
        # 降级到非 Gemini 模型
        actual_cfg = self.models.get(actual_model)
        if actual_cfg and actual_cfg.provider == "azure_openai":
            result = self.call_azure_openai(actual_model, prompt, system_prompt, task_type)
            result["degraded_from"] = model_name
            return result
        elif actual_cfg and actual_cfg.provider == "google":
            model_name = actual_model  # 降级到 Flash，继续走 Gemini 逻辑

    cfg = self.models.get(model_name)
    # ... 原有逻辑 ...
```

在 `call_gemini` 方法的**成功返回前**（`return {"success": True, ...}` 之前）添加计数：

```python
# 记录调用计数
rate_key = self._gemini_rate_key(cfg.model)
self._gemini_daily_counter[rate_key] = self._gemini_daily_counter.get(rate_key, 0) + 1
self._gemini_consecutive_429 = 0  # 成功了，重置连续失败计数
```

在 `call_gemini` 方法的**失败处理**中（`return {"success": False, "error": str(result)}` 之前）添加 429 检测：

```python
# 检测 429 限流
error_str = str(result)
if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str or "quota" in error_str.lower():
    self._gemini_consecutive_429 += 1
    print(f"[Gateway] Gemini 429 detected (consecutive: {self._gemini_consecutive_429})")
    # 立即重试一次，用降级模型
    if self._gemini_consecutive_429 >= 1:
        azure_candidates = [name for name, c in self.models.items()
                           if c.provider == "azure_openai" and c.api_key]
        if azure_candidates:
            print(f"[Gateway] 429 自动重试，降级到 Azure: {azure_candidates[0]}")
            retry = self.call_azure_openai(azure_candidates[0], prompt, system_prompt, task_type)
            retry["degraded_from"] = model_name
            return retry
```

### 1.3 验证

```bash
python -c "
from src.utils.model_gateway import get_model_gateway
gw = get_model_gateway()
# 模拟 Pro 超限
gw._gemini_daily_counter = {'2026-03-24:gemini-3.1-pro': 200}
result = gw._should_degrade_gemini('critic_gemini')
print(f'降级测试: critic_gemini -> {result}')
# 模拟 429
gw._gemini_consecutive_429 = 3
result2 = gw._should_degrade_gemini('critic_gemini')
print(f'429降级: critic_gemini -> {result2}')
print('✅ Task 1 完成')
"
```

---

## Task 2: 对齐报告注入产品锚点（P0）

**问题**: `generate_alignment_report()` 在 daily_learning.py 第 828 行，prompt 中没有产品锚点，所以 LLM 会建议"HUD 不做"。

### 2.1 修改 generate_alignment_report 函数

在 daily_learning.py 的 `generate_alignment_report()` 函数中，找到 `analysis_prompt` 的构建（约第 888 行），在 prompt 开头注入产品锚点。

在这段代码之前（约第 887 行）添加读取锚点的逻辑：

```python
    # === 注入产品锚点 ===
    product_anchor = ""
    for f in KB_ROOT.rglob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            tags = data.get("tags", [])
            if "internal" in tags and ("prd" in tags or "product_definition" in tags):
                product_anchor = data.get("content", "")[:1500]
                break
        except:
            continue
    
    anchor_context = ""
    if product_anchor:
        anchor_context = (
            f"\n## 产品定义锚点（不可违背）\n"
            f"本项目是智能摩托车全盔（不是自行车头盔），HUD/AR显示、4K摄像、ADAS安全均为P0。\n"
            f"你的所有建议必须在此框架内。可以建议分V1/V2阶段，但不能建议'不做'某个P0功能。\n"
            f"{product_anchor[:1000]}\n"
        )
```

然后修改 `analysis_prompt`，在 `"你是智能摩托车头盔项目的研发总监。"` 之后注入 `anchor_context`：

```python
    analysis_prompt = (
        f"你是智能摩托车头盔项目的研发总监。{anchor_context}\n\n"
        f"以下是今天知识库的变化。\n\n"
        # ... 后续不变 ...
    )
```

### 2.2 验证

```bash
python -c "
from scripts.daily_learning import generate_alignment_report
report = generate_alignment_report()
print(report[:800])
# 检查是否包含摩托车相关内容
assert '自行车' not in report or '不是自行车' in report, '对齐报告仍在推荐自行车方向！'
print('✅ Task 2 完成')
"
```

---

## Task 3: 知识库去重清理（P0）

**问题**: 646 条 doc_import 中有大量重复（同一文档多次导入）。

### 3.1 运行一次性去重脚本

```python
python3 << 'PYEOF'
"""知识库一次性去重：基于内容 hash，保留最新的一条"""
import json, hashlib
from pathlib import Path
from collections import defaultdict

KB_ROOT = Path(".ai-state/knowledge")
if not KB_ROOT.exists():
    print("知识库目录不存在")
    exit()

# 按内容 hash 分组
hash_groups = defaultdict(list)
total = 0

for f in KB_ROOT.rglob("*.json"):
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
        content = data.get("content", "")
        title = data.get("title", "")
        # hash = 标题前30字 + 内容前200字
        fingerprint = f"{title[:30]}||{content[:200]}"
        h = hashlib.md5(fingerprint.encode()).hexdigest()
        hash_groups[h].append({
            "path": f,
            "title": title[:50],
            "mtime": f.stat().st_mtime,
            "source": data.get("source", "")
        })
        total += 1
    except:
        continue

# 删除重复（保留最新的）
deleted = 0
for h, entries in hash_groups.items():
    if len(entries) <= 1:
        continue
    # 按修改时间排序，保留最新
    entries.sort(key=lambda x: x["mtime"], reverse=True)
    for entry in entries[1:]:  # 跳过最新的
        try:
            entry["path"].unlink()
            deleted += 1
        except:
            pass
    if len(entries) > 2:
        print(f"  去重 {len(entries)-1} 条: {entries[0]['title']}")

duplicated_groups = sum(1 for entries in hash_groups.values() if len(entries) > 1)
print(f"\n总计: {total} 条")
print(f"重复组: {duplicated_groups}")
print(f"删除: {deleted} 条")
print(f"剩余: {total - deleted} 条")
PYEOF
```

### 3.2 在 knowledge_base.py 的 add_knowledge 中添加入库前去重

在 `add_knowledge` 函数开头（`import random` 之后）添加：

```python
    # === 入库前去重：同 domain 下相同内容不重复入库 ===
    import hashlib
    fingerprint = f"{title[:30]}||{content[:200]}"
    content_hash = hashlib.md5(fingerprint.encode()).hexdigest()
    domain = _normalize_domain(domain)
    domain_dir = KB_ROOT / domain
    if domain_dir.exists():
        for existing in domain_dir.glob("*.json"):
            try:
                existing_data = json.loads(existing.read_text(encoding="utf-8"))
                existing_fp = f"{existing_data.get('title', '')[:30]}||{existing_data.get('content', '')[:200]}"
                if hashlib.md5(existing_fp.encode()).hexdigest() == content_hash:
                    return str(existing)  # 已存在，返回现有路径
            except:
                continue
```

**注意**: 这个去重逻辑会遍历 domain 目录。如果 domain 目录条目超过 2000，性能可能受影响。到时候可以改用一个 hash index 文件。当前 1725 条分 4 个 domain，每个 domain 最多几百条，可以接受。

### 3.3 验证

```bash
python -c "
from src.tools.knowledge_base import add_knowledge, get_knowledge_stats
# 测试去重
path1 = add_knowledge('测试去重条目', 'lessons', '这是一条测试内容用于验证去重机制是否生效', ['test'])
path2 = add_knowledge('测试去重条目', 'lessons', '这是一条测试内容用于验证去重机制是否生效', ['test'])
assert path1 == path2, f'去重失败: {path1} != {path2}'
# 清理测试数据
from pathlib import Path
Path(path1).unlink(missing_ok=True)
print(f'去重前后路径一致: {path1}')
print('✅ Task 3 完成')
"
```

---

## Task 4: 本地资源自动管理（防电脑卡死）

**问题**: 昨晚跑了一夜，今天电脑卡死。多个 main.py、大量 __pycache__、日志文件堆积。

### 4.1 创建 scripts/resource_manager.py

```python
"""
@description: 本地资源自动管理 - 防止长时间运行导致电脑卡死
@dependencies: psutil (可选), pathlib, gc
@last_modified: 2026-03-24
"""
import gc
import os
import sys
import shutil
import threading
import time
from pathlib import Path
from datetime import datetime, timedelta

PROJECT_ROOT = Path(__file__).parent.parent


def cleanup_pycache():
    """清理所有 __pycache__ 目录"""
    count = 0
    for cache_dir in PROJECT_ROOT.rglob("__pycache__"):
        try:
            shutil.rmtree(cache_dir)
            count += 1
        except Exception:
            pass
    return count


def cleanup_old_logs(days: int = 3):
    """清理超过 N 天的日志和临时文件"""
    count = 0
    cutoff = datetime.now() - timedelta(days=days)
    
    # 清理 .ai-state 下的旧报告（保留最近 3 天）
    for pattern in ["reports/*.md", "reports/*.json"]:
        for f in (PROJECT_ROOT / ".ai-state").glob(pattern):
            try:
                if datetime.fromtimestamp(f.stat().st_mtime) < cutoff:
                    f.unlink()
                    count += 1
            except:
                continue
    
    # 清理旧的 alignment 报告（保留最近 5 份）
    reports_dir = PROJECT_ROOT / ".ai-state" / "reports"
    if reports_dir.exists():
        alignment_files = sorted(reports_dir.glob("alignment_*.md"), key=lambda x: x.stat().st_mtime, reverse=True)
        for f in alignment_files[5:]:
            try:
                f.unlink()
                count += 1
            except:
                continue
    
    # 清理 processed inbox（保留最近 20 个）
    processed_dir = PROJECT_ROOT / ".ai-state" / "inbox" / "processed"
    if processed_dir.exists():
        processed_files = sorted(processed_dir.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True)
        for f in processed_files[20:]:
            try:
                f.unlink()
                count += 1
            except:
                continue
    
    return count


def cleanup_memory():
    """强制 Python 垃圾回收，释放内存"""
    collected = gc.collect()
    return collected


def get_system_status() -> dict:
    """获取系统资源状态"""
    status = {
        "python_memory_mb": 0,
        "disk_free_gb": 0,
        "pycache_count": 0,
        "kb_size_mb": 0,
    }
    
    # Python 进程内存
    try:
        import psutil
        process = psutil.Process(os.getpid())
        status["python_memory_mb"] = round(process.memory_info().rss / 1024 / 1024, 1)
        status["cpu_percent"] = psutil.cpu_percent(interval=1)
        status["memory_percent"] = psutil.virtual_memory().percent
    except ImportError:
        pass
    
    # 磁盘
    try:
        usage = shutil.disk_usage(PROJECT_ROOT)
        status["disk_free_gb"] = round(usage.free / 1024 / 1024 / 1024, 1)
    except:
        pass
    
    # __pycache__ 数量
    status["pycache_count"] = sum(1 for _ in PROJECT_ROOT.rglob("__pycache__"))
    
    # 知识库大小
    kb_root = PROJECT_ROOT / ".ai-state" / "knowledge"
    if kb_root.exists():
        total_size = sum(f.stat().st_size for f in kb_root.rglob("*.json"))
        status["kb_size_mb"] = round(total_size / 1024 / 1024, 1)
    
    return status


def auto_cleanup():
    """自动清理一轮"""
    print(f"[ResourceMgr] 开始自动清理 ({datetime.now().strftime('%H:%M')})")
    
    cache_cleaned = cleanup_pycache()
    logs_cleaned = cleanup_old_logs()
    gc_collected = cleanup_memory()
    
    status = get_system_status()
    
    report = (
        f"[ResourceMgr] 清理完成:\n"
        f"  __pycache__: 清理 {cache_cleaned} 个\n"
        f"  旧文件: 清理 {logs_cleaned} 个\n"
        f"  GC: 回收 {gc_collected} 个对象\n"
        f"  内存: {status.get('memory_percent', '?')}%\n"
        f"  磁盘: {status.get('disk_free_gb', '?')} GB 可用\n"
        f"  知识库: {status.get('kb_size_mb', '?')} MB"
    )
    print(report)
    return report


def start_resource_monitor(interval_hours: float = 2.0, feishu_notify=None):
    """启动定时资源监控线程"""
    def _monitor():
        while True:
            time.sleep(interval_hours * 3600)
            try:
                report = auto_cleanup()
                
                # 如果内存超过 80%，发警告
                status = get_system_status()
                mem_pct = status.get("memory_percent", 0)
                if mem_pct > 80 and feishu_notify:
                    feishu_notify(f"⚠️ 系统内存 {mem_pct}%，建议关闭不必要的程序")
                    
            except Exception as e:
                print(f"[ResourceMgr] 监控失败: {e}")
    
    print(f"[ResourceMgr] 资源监控已启动（每 {interval_hours}h 清理一次）")
    t = threading.Thread(target=_monitor, daemon=True)
    t.start()
    return t


if __name__ == "__main__":
    report = auto_cleanup()
    print("\n系统状态:")
    for k, v in get_system_status().items():
        print(f"  {k}: {v}")
```

### 4.2 在 main.py 中注册资源管理器

找到 main.py 中启动各子系统的位置（应该有 `start_daily_scheduler` 的调用附近），添加：

```python
# 启动资源自动管理（每 2 小时清理一次）
from scripts.resource_manager import start_resource_monitor, auto_cleanup
auto_cleanup()  # 启动时先清理一轮
start_resource_monitor(interval_hours=2.0, feishu_notify=feishu_notify_func)
```

其中 `feishu_notify_func` 用你 main.py 中已有的飞书通知函数。

### 4.3 安装 psutil（可选但建议）

```bash
pip install psutil --break-system-packages
```

### 4.4 立即执行一次清理

```bash
python scripts/resource_manager.py
```

### 4.5 验证

```bash
python -c "
from scripts.resource_manager import get_system_status, auto_cleanup
auto_cleanup()
status = get_system_status()
print(status)
print('✅ Task 4 完成')
"
```

---

## Task 5: 夜间学习调频（配合 Gemini 降级）

**问题**: 夜间学习（1am-5am）每 30 分钟一轮，每轮 deep_research 调 Gemini，加上 3 个阶段（深化10条 + 拓展15条 + 跨界8条），一夜 3500 次 Gemini 调用。

### 5.1 修改 daily_learning.py 的夜间学习节奏

找到 `start_daily_scheduler` 函数中的夜间学习部分（约第 771-787 行）：

```python
            # 检查是否在夜间深度学习窗口（1:00-5:00）
            if 1 <= current_hour < 5:
```

把夜间等待从 30 分钟改为 60 分钟，并减少每轮的搜索量：

```python
            if 1 <= current_hour < 5:
                print(f"[NightLearn] 夜间深度学习 ({current_hour}:{datetime.now().minute:02d})")
                try:
                    report = run_night_deep_learning(
                        progress_callback=lambda msg: feishu_notify(msg) if feishu_notify else None
                    )
                    if feishu_notify:
                        feishu_notify(report)
                except Exception as e:
                    print(f"[NightLearn] 失败: {e}")
                    if feishu_notify:
                        feishu_notify(f"[NightLearn] 失败: {e}")
                # 夜间每 60 分钟一轮（之前是 30 分钟，调用量太大）
                time.sleep(3600)
                continue
```

### 5.2 减少夜间单轮搜索量

在 `run_night_deep_learning` 函数中：

- Phase 1 深化：`shallow_entries[:10]` 改为 `shallow_entries[:5]`（第 461 行）
- Phase 2 拓展：`expand_topics[:15]` 改为 `expand_topics[:8]`（第 531 行）
- Phase 3 跨界：跨界搜索从 8 个减到 4 个，在 `cross_prompt` 中把 "8 个" 改为 "4 个"（第 563 行），然后 `for query in cross_topics` 后面不需要改（因为 LLM 本身只生成 4 个了）

这样每轮从 ~33 次搜索降到 ~17 次，一夜 4 轮 = ~68 次 Gemini 调用（加上 LLM 提炼约 x2 = ~136 次），远低于限额。

### 5.3 验证

重启服务后查看日志，确认：
- 夜间学习间隔 60 分钟
- 每轮搜索量明显减少
- Gemini 429 自动降级到 Azure/Flash

---

## 执行完成后的检查清单

```bash
# 1. 确认所有改动能正常导入
python -c "from src.utils.model_gateway import get_model_gateway; print('gateway OK')"
python -c "from scripts.daily_learning import generate_alignment_report; print('alignment OK')"
python -c "from src.tools.knowledge_base import add_knowledge; print('KB OK')"
python -c "from scripts.resource_manager import auto_cleanup; print('resource OK')"

# 2. 运行一次资源清理
python scripts/resource_manager.py

# 3. 跑一次去重
# （Task 3.1 的脚本）

# 4. 重启主服务
# 观察日志确认：
#   - [ResourceMgr] 资源监控已启动
#   - [Gateway] 相关日志正常
#   - 夜间学习间隔改为 60 分钟
```

---

## 不包含在本次任务中的（记录备查）

- **多源搜索 1 src 问题** → Day 8，排查 tavily 和 alt_query 失败原因
- **知识库浅条目深化** → Day 8，建立自动审计机制
- **PRD V1 推进** → 今天下午，用修好的系统跑 PRD 研究
