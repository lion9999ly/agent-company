# CC 执行文档 Part 1 补充: 并发与流水线

> 日期: 2026-03-31
> 附属于 Part 1（五层管道改造），在 Part 1 的 Layer 1 改造和调度器部分引用
> 涉及文件: `scripts/tonight_deep_research.py`
> 与 Part 1 同一次 commit

---

## 一、并发基础设施

在 `tonight_deep_research.py` 顶部添加:

```python
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

# === 并发控制: 按 provider 限制并发数 ===
PROVIDER_SEMAPHORES = {
    "o3": threading.Semaphore(3),        # o3 慢，3 并发
    "doubao": threading.Semaphore(8),    # 豆包快，8 并发
    "flash": threading.Semaphore(8),     # Flash 提炼，8 并发
    "gemini_pro": threading.Semaphore(3),# 有限额，保守
    "gpt54": threading.Semaphore(4),     # 成本高
    "gpt4o": threading.Semaphore(4),     # 通用
}

# 限流退避重试
def _call_with_backoff(model_name: str, prompt: str, system_prompt: str = None,
                        task_type: str = "general", max_retries: int = 3) -> dict:
    """带限流退避的模型调用"""
    # 选择对应的信号量
    sem_key = _get_sem_key(model_name)
    sem = PROVIDER_SEMAPHORES.get(sem_key)

    for attempt in range(max_retries + 1):
        if sem:
            sem.acquire()
        try:
            result = _call_model(model_name, prompt, system_prompt, task_type)

            # 检查限流
            error = result.get("error", "")
            is_rate_limit = ("429" in str(error) or "rate" in str(error).lower()
                            or "quota" in str(error).lower()
                            or "RESOURCE_EXHAUSTED" in str(error))

            if is_rate_limit and attempt < max_retries:
                wait = (2 ** attempt) * 10  # 10s, 20s, 40s
                print(f"  [RateLimit] {model_name} attempt {attempt+1}, "
                      f"waiting {wait}s...")
                time.sleep(wait)
                continue

            return result
        finally:
            if sem:
                sem.release()

    return result  # 最后一次的结果


def _get_sem_key(model_name: str) -> str:
    """模型名 → 信号量 key"""
    if "o3" in model_name and "deep" in model_name:
        return "o3"
    elif "doubao" in model_name:
        return "doubao"
    elif "flash" in model_name:
        return "flash"
    elif "gemini" in model_name and "pro" in model_name:
        return "gemini_pro"
    elif "gpt_5_4" in model_name or "gpt-5.4" in model_name:
        return "gpt54"
    elif "4o" in model_name:
        return "gpt4o"
    return "gpt54"  # 默认保守
```

---

## 二、Layer 1 改造: 并发双搜索

替换 Part 1 中 4.3 节的 Layer 1 代码:

```python
    # === Layer 1: 并发双搜索 ===
    all_sources = []
    source_lock = threading.Lock()

    hb = ProgressHeartbeat(
        f"深度研究:{title[:20]}",
        total=len(searches),
        feishu_callback=progress_callback,
        log_interval=3, feishu_interval=5, feishu_time_interval=180
    )

    def _search_one_query(i: int, query: str) -> dict:
        """单个 query 的双通道搜索（在线程中运行）"""
        source_text = ""

        # Channel A: o3-deep-research
        o3_result = _call_with_backoff(
            "o3_deep_research", query,
            "Search for technical specifications, patents, and research papers.",
            "deep_research_search")
        o3_text = ""
        if o3_result.get("success") and len(o3_result.get("response", "")) > 200:
            o3_text = o3_result["response"][:3000]
            print(f"    [{i}] o3: {len(o3_result['response'])} 字")

        # Channel B: doubao（与 o3 串行，但跨 query 并发）
        doubao_result = _call_with_backoff(
            "doubao_seed_pro", query,
            "搜索中文互联网信息，重点关注小红书、B站、知乎、雪球、1688等平台。",
            "chinese_search")
        doubao_text = ""
        if doubao_result.get("success") and len(doubao_result.get("response", "")) > 200:
            doubao_text = doubao_result["response"][:3000]
            print(f"    [{i}] doubao: {len(doubao_result['response'])} 字")

        source_text = o3_text
        if doubao_text:
            source_text += "\n---\n" + doubao_text if source_text else doubao_text

        # Fallback: tavily
        if not source_text:
            tavily_result = registry.call("tavily_search", query)
            if tavily_result.get("success") and len(tavily_result.get("data", "")) > 200:
                source_text = tavily_result["data"][:3000]
                print(f"    [{i}] tavily(fallback): {len(source_text)} 字")

        return {"index": i, "query": query, "content": source_text}

    # 并发搜索所有 query
    print(f"  [L1] 并发搜索 {len(searches)} 个 query...")
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {
            executor.submit(_search_one_query, i, q): i
            for i, q in enumerate(searches, 1)
        }
        for future in as_completed(futures):
            result = future.result()
            if result["content"]:
                with source_lock:
                    all_sources.append({
                        "query": result["query"],
                        "content": result["content"][:6000]
                    })
                hb.tick(detail=result["query"][:40], success=True)
            else:
                hb.tick(detail=f"失败: {result['query'][:40]}", success=False)

    hb.finish(f"搜索完成，{len(all_sources)}/{len(searches)} 有效")
```

---

## 三、Layer 2 改造: 并发提炼

替换 Part 1 中 4.4 节的 Layer 2 代码:

```python
    # === Layer 2: 并发结构化提炼 ===
    print(f"  [L2] 并发提炼 {len(all_sources)} 条...")
    structured_data_list = []
    struct_lock = threading.Lock()
    task_type_hint = task.get("goal", "") + " " + title

    def _extract_one(src: dict) -> dict:
        """单条搜索结果的结构化提取"""
        return _extract_structured_data(
            raw_text=src["content"],
            task_type=task_type_hint,
            topic=src["query"]
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(_extract_one, src): src for src in all_sources}
        for future in as_completed(futures):
            extracted = future.result()
            if extracted:
                with struct_lock:
                    structured_data_list.append(extracted)

    print(f"  [L2] 提炼完成: {len(structured_data_list)}/{len(all_sources)} 成功")

    structured_dump = ""
    if structured_data_list:
        structured_dump = json.dumps(structured_data_list, ensure_ascii=False, indent=2)
```

---

## 四、Layer 3 改造: Agent 并行

替换 `deep_research_one()` 中 Step 3.5 的串行 Agent 调用:

```python
    # === Layer 3: Agent 并行分析 ===
    agent_outputs = {}
    agent_lock = threading.Lock()

    distilled_material = structured_dump[:8000] if structured_dump else source_dump[:8000]
    kb_material = kb_context[:2000]

    def _run_agent(role: str, prompt: str, sys_prompt: str) -> tuple:
        """运行单个 Agent（在线程中）"""
        model = _get_model_for_role(role)
        result = _call_with_backoff(model, prompt, sys_prompt,
                                     f"deep_research_{role.lower()}")
        if result.get("success"):
            return (role, result["response"])
        return (role, None)

    # 构建各 Agent 的 prompt（同 Part 1 中定义的 cto_prompt, cmo_prompt, cdo_prompt）
    agent_tasks = []
    if "CTO" in roles:
        agent_tasks.append(("CTO", cto_prompt, "你是资深技术合伙人，输出专业的技术分析。"))
    if "CMO" in roles:
        agent_tasks.append(("CMO", cmo_prompt, "你是资深市场合伙人，输出专业的商业分析。"))
    if "CDO" in roles:
        agent_tasks.append(("CDO", cdo_prompt, "你是资深设计合伙人，输出专业的设计分析。"))

    print(f"  [L3] 并行运行 {len(agent_tasks)} 个 Agent...")
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(_run_agent, role, prompt, sys): role
            for role, prompt, sys in agent_tasks
        }
        for future in as_completed(futures):
            role, output = future.result()
            if output:
                with agent_lock:
                    agent_outputs[role] = output
                print(f"  [{role}] {len(output)} chars")
            else:
                print(f"  [{role}] ❌ failed")
```

---

## 五、跨任务流水线（深度学习调度器）

修改 Part 2 中 `run_deep_learning()` 的任务执行部分:

```python
def run_deep_learning(max_hours: float = 7.0, progress_callback=None):
    """深度学习调度器 — 跨任务流水线版本

    设计: 当任务 A 进入 Layer 4（整合）时，任务 B 的 Layer 1（搜索）同时开始。
    Layer 4/5 是 CPU-bound（单次 LLM 调用），不需要并发。
    Layer 1/2/3 是 IO-bound（等 API 响应），并发收益最大。

    实现: 用 2 个工作线程 —— 一个做搜索+提炼+分析，另一个做整合+Critic。
    通过队列连接。
    """
    import queue

    start_time = time.time()
    deadline = start_time + max_hours * 3600
    completed = []

    # 搜索→分析 产出的中间结果队列
    synthesis_queue = queue.Queue()

    print(f"\n{'#'*60}")
    print(f"# 深度学习模式 — {max_hours}h 窗口（流水线）")
    print(f"# 开始: {time.strftime('%Y-%m-%d %H:%M')}")
    print(f"{'#'*60}")

    def _phase1_worker(tasks: list):
        """Phase 1 工作线程: Layer 1-3（搜索→提炼→分析）"""
        for task in tasks:
            if time.time() > deadline - 1800:  # 留 30min 给收尾
                break
            print(f"\n[P1] 开始 L1-L3: {task['title']}")
            # 执行 Layer 1-3（内部已并发）
            # 产出: agent_outputs + structured_dump + 任务元数据
            intermediate = _run_layers_1_to_3(task, progress_callback)
            synthesis_queue.put(intermediate)

        synthesis_queue.put(None)  # 结束信号

    def _phase2_worker():
        """Phase 2 工作线程: Layer 4-5（整合→Critic→入库）"""
        while True:
            item = synthesis_queue.get()
            if item is None:
                break
            print(f"\n[P2] 开始 L4-L5: {item['title']}")
            report = _run_layers_4_to_5(item, progress_callback)
            completed.append({
                "title": item["title"],
                "report_len": len(report),
                "duration_min": round(item.get("l1_l3_duration", 0) / 60, 1)
            })

    # 获取任务列表
    all_tasks = _get_tasks_for_session(deadline)

    # 启动两个工作线程
    p1_thread = threading.Thread(target=_phase1_worker, args=(all_tasks,))
    p2_thread = threading.Thread(target=_phase2_worker)

    p1_thread.start()
    p2_thread.start()

    p1_thread.join()
    p2_thread.join()

    # 收尾: KB 治理
    _run_post_session(completed, start_time, max_hours, progress_callback)


def _run_layers_1_to_3(task: dict, progress_callback=None) -> dict:
    """执行 Layer 1-3，返回中间结果供 Layer 4-5 使用

    这个函数内部的 L1/L2/L3 已经是并发的（见上文）。
    返回的 dict 包含:
    - agent_outputs: {role: output_text}
    - structured_dump: JSON 字符串
    - kb_context: 知识库上下文
    - goal, title: 元数据
    - l1_l3_duration: 耗时（秒）
    """
    t0 = time.time()

    # 复用 deep_research_one 中 Layer 1-3 的逻辑
    # 但不执行 Layer 4-5
    # CC 需要把 deep_research_one 拆分成两个函数:
    #   _run_layers_1_to_3(): 搜索+提炼+Agent分析
    #   _run_layers_4_to_5(): 整合+Critic+入库

    # ... (具体实现: 从 deep_research_one 中提取)

    return {
        "title": task["title"],
        "goal": task["goal"],
        "task": task,
        "agent_outputs": agent_outputs,
        "structured_dump": structured_dump,
        "kb_context": kb_context,
        "product_anchor": product_anchor,
        "l1_l3_duration": time.time() - t0,
    }


def _run_layers_4_to_5(intermediate: dict, progress_callback=None) -> str:
    """执行 Layer 4-5: 整合→Critic→入库

    输入: _run_layers_1_to_3 的输出
    输出: 最终报告文本
    """
    # ... (具体实现: 从 deep_research_one 中提取 synthesis + critic + 入库逻辑)
    pass


def _get_tasks_for_session(deadline: float) -> list:
    """获取本次深度学习的任务列表

    策略:
    1. 任务池中未完成的任务
    2. 任务池空了 → 自主发现新方向
    3. 估算每个任务耗时 ~20min（流水线模式），计算能跑多少个
    """
    remaining_hours = (deadline - time.time()) / 3600
    max_tasks = int(remaining_hours * 3)  # 流水线模式约 20min/任务

    pool = _load_task_pool()
    if len(pool) >= max_tasks:
        return pool[:max_tasks]

    # 任务池不够，自主发现补充
    needed = max_tasks - len(pool)
    new_tasks = _discover_new_tasks()
    if new_tasks:
        pool.extend(new_tasks[:needed])
        _save_task_pool(pool)

    return pool[:max_tasks]
```

---

## 六、CC 具体执行指引

### 拆分 `deep_research_one()`

当前 `deep_research_one()` 是一个 ~600 行的大函数。需要拆成:

1. **`_run_layers_1_to_3(task, progress_callback)`**
   - 包含: 搜索词生成 → 发现层 → Layer 1 并发搜索 → Layer 2 并发提炼 → 知识库检索 → 角色分配 → 专家框架注入 → Layer 3 Agent 并行分析
   - 返回: `dict`（agent_outputs, structured_dump, kb_context, product_anchor 等）

2. **`_run_layers_4_to_5(intermediate, progress_callback)`**
   - 包含: Layer 4 synthesis（含 retry/expand fallback）→ Layer 5 Critic → 保存报告 → 提取知识入库
   - 返回: `str`（最终报告文本）

3. **`deep_research_one(task, ...)`** 保留为兼容入口:
   ```python
   def deep_research_one(task, progress_callback=None, constraint_context=None):
       intermediate = _run_layers_1_to_3(task, progress_callback)
       return _run_layers_4_to_5(intermediate, progress_callback)
   ```

### 替换所有 `_call_model()` 为 `_call_with_backoff()`

在 Layer 1/2/3 的并发代码中，所有模型调用都用 `_call_with_backoff()` 而不是直接 `_call_model()`。
Layer 4/5 可以继续用 `_call_model()`（不需要并发控制）。

### 线程安全

- `all_sources` 和 `structured_data_list` 的写入用 `threading.Lock()`
- KB 写入 (`add_knowledge`) 检查是否线程安全，如果不是加锁
- print 语句本身是线程安全的（Python GIL）

---

## 七、预估效果

| 场景 | 串行 | 流水线 | 提速比 |
|------|------|--------|--------|
| 单任务 (8 query) | ~55min | ~15min | 3.5x |
| 5 任务串行 | ~4.5h | ~1.5h | 3x |
| 7h 窗口任务数 | ~8 个 | ~20 个 | 2.5x |

实际受 API 响应时间和限流影响，保守估计 2-3x 提速。
