# Phase 2.3 — 搜索/提炼模型分工 + Phase 2.4 — 并行吞吐提升

## 原则
- 搜索环节（query 生成、关键词提取、平台搜索）→ `gemini_2_5_flash`（快+便宜）
- 提炼环节（深度摘要、决策树生成、知识条目撰写）→ `gpt_5_4`（质量优先）
- 并行搜索从 4 路提升到 8 路，提炼保持串行（避免 Azure 限流）

---

## 2.3 改造模式

核心思路：在各脚本中，找到所有 `gateway.call_azure_openai(...)` 或 `gateway.call_gemini(...)`，
判断它是"搜索"还是"提炼"，然后分别路由。

### 提供的工具函数（加到 model_gateway.py 或各脚本开头均可）

```python
def call_for_search(gateway, prompt: str, system_prompt: str = "", task_type: str = "search") -> dict:
    """搜索环节：用 Flash（快+便宜）"""
    result = gateway.call_gemini("gemini_2_5_flash", prompt, system_prompt, task_type)
    if not result.get("success"):
        # Flash 失败，降级到 Azure
        result = gateway.call_azure_openai("cpo", prompt, system_prompt, task_type)
        result["degraded_from"] = "gemini_2_5_flash"
    return result


def call_for_refine(gateway, prompt: str, system_prompt: str = "", task_type: str = "refine") -> dict:
    """提炼环节：用 GPT-5.4（质量优先）"""
    return gateway.call_azure_openai("cpo", prompt, system_prompt, task_type)
```

### 各脚本改造指引

#### `scripts/daily_learning.py`
搜索部分（查找 `search_knowledge`、`platform_search`、`multi_engine_search` 的关键词提取）:
- 关键词提取 prompt → `call_for_search`
- 搜索结果摘要 prompt → `call_for_search`

提炼部分（查找 `add_knowledge`、知识条目生成）:
- 知识条目内容撰写 → `call_for_refine`
- 对齐报告生成 → `call_for_refine`

#### `scripts/knowledge_graph_expander.py`
- 种子发现（分析知识库薄弱方向）→ `call_for_search`（判断方向用 Flash 够了）
- 搜索 query 生成 → `call_for_search`
- 深搜提炼（从搜索结果生成知识条目）→ `call_for_refine`
- 决策树生成 → `call_for_refine`

#### `scripts/overnight_kb_overhaul.py`
- Phase 3 浅条目深化的搜索 → `call_for_search`
- Phase 3 浅条目深化的内容生成 → `call_for_refine`
- Phase 4 无数据补充的搜索 → `call_for_search`
- Phase 4 无数据补充的内容生成 → `call_for_refine`
- Phase 7 决策树 → `call_for_refine`

#### `scripts/feishu_sdk_client.py`
- `handle_share_content` 中关键词提取 → `call_for_search`
- `handle_share_content` 中内容提炼 → `call_for_refine`（已经是 Azure，保持不变）
- 图片理解（Gemini Vision）→ 保持不变（已经是 Flash）

---

## 2.4 并行吞吐提升

### 改造 `knowledge_graph_expander.py`

找到 `ThreadPoolExecutor` 相关代码（交接文档提到当前是 4 路并行）：

```python
# 原
with ThreadPoolExecutor(max_workers=4) as executor:
    ...

# 改为动态调整
import psutil

def _get_optimal_workers() -> int:
    """根据系统负载动态调整并行度"""
    try:
        cpu_pct = psutil.cpu_percent(interval=0.5)
        mem_pct = psutil.virtual_memory().percent
        if cpu_pct < 50 and mem_pct < 70:
            return 8   # 空闲：跑满
        elif cpu_pct < 80 and mem_pct < 85:
            return 4   # 中等负载：正常
        else:
            return 2   # 高负载：保守
    except Exception:
        return 4  # psutil 不可用时默认 4

workers = _get_optimal_workers()
print(f"[Parallel] CPU: {psutil.cpu_percent()}%, MEM: {psutil.virtual_memory().percent}% → workers={workers}")
with ThreadPoolExecutor(max_workers=workers) as executor:
    ...
```

注意：需要 `pip install psutil`（如果未安装）。

### 改造 `daily_learning.py`

同上模式，搜索环节用动态并行度，提炼环节保持串行：

```python
# 搜索阶段（可并行）
workers = _get_optimal_workers()
with ThreadPoolExecutor(max_workers=workers) as executor:
    search_futures = {executor.submit(search_one_topic, topic): topic for topic in topics}
    for future in as_completed(search_futures):
        result = future.result()
        ...

# 提炼阶段（串行，避免 Azure 限流）
for raw_data in search_results:
    refined = call_for_refine(gateway, refine_prompt, ...)
    ...
```

### 验证

```python
python -c "import psutil; print(f'CPU: {psutil.cpu_percent()}%, MEM: {psutil.virtual_memory().percent}%')"
```

---

## CC 执行指引

对于 2.3 和 2.4，建议让 CC 执行，指令如下：

```
请根据 phase_2.3_2.4_guidance.md 文档，对以下文件进行搜索/提炼模型分工改造：
1. scripts/daily_learning.py — 搜索环节改用 gemini_2_5_flash，提炼环节保持 gpt_5_4
2. scripts/knowledge_graph_expander.py — 同上 + ThreadPoolExecutor 并行度从 4 改为动态调整（psutil）
3. scripts/overnight_kb_overhaul.py — 搜索用 Flash，提炼用 GPT-5.4

注意：
- 不要改变函数签名和外部接口
- Flash 调用失败时必须降级到 Azure
- 提炼环节不并行（避免 Azure 限流）
- 添加 import psutil（如未安装先 pip install psutil --break-system-packages）
```
