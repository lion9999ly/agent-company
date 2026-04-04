# CC 执行文档 Part 1: 深度研究五层管道改造

> 日期: 2026-03-31
> 替代: `deep_research_pipeline_fix.md` + `deep_research_model_routing_fix.md`
> 涉及文件:
>   - `src/utils/model_gateway.py`
>   - `src/config/model_registry.yaml`
>   - `scripts/tonight_deep_research.py`
> 完成后: `git add -A && git commit -m "feat: deep research v2 — five-layer pipeline, dual search, bug fixes"`
> **不要重启服务，Leo 手动重启。**

---

## 一、架构概览

五层分层提炼，每层输入控制在 10-15k 字以内:

```
Layer 1: 搜索    → o3-deep-research + doubao 并行，tavily fallback
                   输出: ~40k 字原始材料
                         ↓
Layer 2: 提炼    → gemini-2.5-flash 逐条结构化提取
                   输出: ~8k 字结构化数据（带 source + confidence）
                         ↓
Layer 3: 分析    → CTO(gpt-5.4) + CMO(doubao) + CDO(gemini-3.1-pro)
                   各自只看提炼数据 + KB，不看原始材料
                   输出: ~4.5k 字 Agent 分析
                         ↓
Layer 4: 整合    → gpt-5.4 只看 Agent 输出 + 分歧摘要
                   输出: ~3k 字研究报告
                         ↓
Layer 5: Critic  → gemini-3.1-pro 独立审查，交叉验证 L2 数据点
                   输出: 最终报告 → KB + 文件
```

---

## 二、model_gateway.py 改造

### 2.1 新增 `call_azure_responses()` 方法

o3-deep-research 只支持 Responses API，不是 Chat Completions API。

在 `ModelGateway` 类中，`call_azure_openai()` 方法之后添加:

```python
def call_azure_responses(self, model_name: str, prompt: str,
                          task_type: str = "deep_research",
                          tools: list = None) -> Dict[str, Any]:
    """调用 Azure OpenAI Responses API（o3-deep-research 专用）

    与 Chat Completions API 的区别:
    - endpoint: /openai/deployments/{deployment}/responses
    - 请求体: {"input": "...", "max_output_tokens": N}
    - 响应体: {"output": [...], "usage": {...}}
    """
    cfg = self.models.get(model_name)
    if not cfg or not cfg.api_key:
        return {"success": False, "error": f"Model {model_name} not configured"}

    if not cfg.endpoint:
        return {"success": False, "error": f"Endpoint not configured for {model_name}"}

    deployment_name = cfg.deployment or cfg.model
    api_version = cfg.api_version or "2025-04-01-preview"

    url = (f"{cfg.endpoint.rstrip('/')}/openai/deployments/"
           f"{deployment_name}/responses?api-version={api_version}")

    payload = {
        "input": prompt,
        "max_output_tokens": cfg.max_tokens or 16000,
    }
    if tools:
        payload["tools"] = tools

    # o3-deep-research 单次可能 2-5 分钟
    timeout = max(TIMEOUT_BY_TASK.get(task_type, 180), 600)

    start_time = time.time()
    try:
        resp = requests.post(url, json=payload, timeout=timeout,
                             headers={"api-key": cfg.api_key,
                                      "Content-Type": "application/json"})
        result = resp.json()
        latency_ms = int((time.time() - start_time) * 1000)

        print(f"  [Azure-Responses] task={task_type} status={resp.status_code} "
              f"latency={latency_ms}ms")

        if resp.status_code == 404:
            msg = (f"[MODEL_404] {model_name} deployment={deployment_name} "
                   f"Responses API 404. URL: {url[:120]}")
            print(msg)
            return {"success": False, "error": msg, "status_code": 404}

        if resp.status_code >= 400:
            msg = f"[MODEL_ERROR] {model_name} status={resp.status_code}: {str(result)[:300]}"
            print(msg)
            return {"success": False, "error": msg, "status_code": resp.status_code}

        # 解析 Responses API 输出
        output = result.get("output", [])
        text_parts = []
        for item in output:
            if item.get("type") == "message":
                for content in item.get("content", []):
                    if content.get("type") == "output_text":
                        text_parts.append(content.get("text", ""))
            elif item.get("type") == "text":
                text_parts.append(item.get("text", ""))
        text = "\n".join(text_parts)

        # fallback 解析
        if not text:
            if isinstance(output, str):
                text = output
            elif isinstance(output, list) and output:
                first = output[0]
                text = first if isinstance(first, str) else json.dumps(first, ensure_ascii=False)

        usage = result.get("usage", {})
        p_tok = usage.get("input_tokens", usage.get("prompt_tokens", 0))
        c_tok = usage.get("output_tokens", usage.get("completion_tokens", 0))

        if HAS_TRACKER:
            get_tracker().record(model=cfg.model, provider="azure_responses",
                                prompt_tokens=p_tok, completion_tokens=c_tok,
                                task_type=task_type, success=bool(text),
                                latency_ms=latency_ms)

        if text:
            print(f"  [Azure-Responses] OK: {len(text)} chars, {c_tok} tokens")
            return {"success": True, "model": model_name, "response": text,
                    "raw": result,
                    "usage": {"prompt_tokens": p_tok, "completion_tokens": c_tok}}
        else:
            return {"success": False, "error": f"Empty response: {str(result)[:200]}"}

    except requests.exceptions.Timeout:
        ms = int((time.time() - start_time) * 1000)
        print(f"  [Azure-Responses] TIMEOUT after {ms}ms")
        return {"success": False, "error": f"Timeout after {ms}ms"}
    except Exception as e:
        return {"success": False, "error": str(e)}
```

### 2.2 确认 `call_volcengine()` 存在且 base_url 正确

CC 之前已添加此方法。确认走的是 `https://ark.cn-beijing.volces.com/api/v3`（不是 `/api/coding/v3`）。如果不对，修正。

### 2.3 更新 `call()` 统一入口

修改 `call()` 方法，添加 Responses API 和 volcengine 分支:

```python
def call(self, model_name: str, prompt: str, system_prompt: str = None,
         task_type: str = "general") -> Dict[str, Any]:
    """统一调用接口"""
    cfg = self.models.get(model_name)
    if not cfg:
        return {"success": False, "error": f"Unknown model: {model_name}"}

    if cfg.provider == "google":
        return self.call_gemini(model_name, prompt, system_prompt, task_type)
    elif cfg.provider == "alibaba":
        return self.call_qwen(model_name, prompt, system_prompt)
    elif cfg.provider == "azure_openai":
        # o3-deep-research 走 Responses API
        if "deep-research" in (cfg.deployment or "").lower():
            full_prompt = (f"[System]\n{system_prompt}\n\n[User]\n{prompt}"
                           if system_prompt else prompt)
            return self.call_azure_responses(model_name, full_prompt, task_type)
        return self.call_azure_openai(model_name, prompt, system_prompt, task_type)
    elif cfg.provider == "volcengine":
        return self.call_volcengine(model_name, prompt, system_prompt, task_type)
    elif cfg.provider == "zhipu":
        return self.call_zhipu(model_name, prompt, system_prompt, task_type)
    elif cfg.provider == "deepseek":
        return self.call_deepseek(model_name, prompt, system_prompt, task_type)
    else:
        return {"success": False, "error": f"Unsupported provider: {cfg.provider}"}
```

### 2.4 添加降级包装函数

在 `ModelGateway` 类中添加:

```python
def call_with_fallback(self, primary: str, fallback: str, prompt: str,
                        system_prompt: str = None, task_type: str = "general") -> Dict:
    """调用主模型，失败时降级到备选"""
    result = self.call(primary, prompt, system_prompt, task_type)
    if result.get("success"):
        return result
    print(f"  [Fallback] {primary} failed, degrading to {fallback}")
    result2 = self.call(fallback, prompt, system_prompt, task_type)
    result2["degraded_from"] = primary
    return result2
```

---

## 三、model_registry.yaml 补全

确认以下配置存在（检查并补全缺失的）:

```yaml
# Azure Norway East
o3_deep_research:
  provider: "azure_openai"
  model: "o3-deep-research-2025-06-26"
  deployment: "o3-deep-research"
  endpoint_env: "AZURE_OPENAI_NORWAY_ENDPOINT"
  api_key_env: "AZURE_OPENAI_NORWAY_API_KEY"
  api_version: "2025-04-01-preview"
  max_tokens: 16000
  temperature: 0.1
  purpose: "deep_research"
  capabilities: ["reasoning", "web_search", "long_context"]
  cost_tier: "$$$$"
  performance: 5

gpt_4o_norway:
  provider: "azure_openai"
  model: "gpt-4o"
  deployment: "gpt-4o"
  endpoint_env: "AZURE_OPENAI_NORWAY_ENDPOINT"
  api_key_env: "AZURE_OPENAI_NORWAY_API_KEY"
  api_version: "2025-04-01-preview"
  max_tokens: 4096
  temperature: 0.1
  purpose: "general_fallback"
  capabilities: ["multimodal", "function_calling"]
  cost_tier: "$$"
  performance: 4

# 火山引擎
doubao_seed_pro:
  provider: "volcengine"
  model: "doubao-seed-2-0-pro-260215"
  endpoint: "https://ark.cn-beijing.volces.com/api/v3"
  api_key_env: "ARK_API_KEY"
  max_tokens: 8192
  temperature: 0.1
  purpose: "chinese_research"
  capabilities: ["chinese_internet", "256k_context", "vision"]
  cost_tier: "$$"
  performance: 4

doubao_seed_lite:
  provider: "volcengine"
  model: "doubao-seed-2-0-lite-260215"
  endpoint: "https://ark.cn-beijing.volces.com/api/v3"
  api_key_env: "ARK_API_KEY"
  max_tokens: 4096
  temperature: 0.1
  purpose: "fast_chinese"
  capabilities: ["chinese_internet", "fast"]
  cost_tier: "$"
  performance: 3

deepseek_v3_volcengine:
  provider: "volcengine"
  model: "deepseek-v3-2-251201"
  endpoint: "https://ark.cn-beijing.volces.com/api/v3"
  api_key_env: "ARK_API_KEY"
  max_tokens: 8192
  temperature: 0.1
  purpose: "code_analysis"
  capabilities: ["code", "reasoning"]
  cost_tier: "$"
  performance: 4
```

---

## 四、tonight_deep_research.py 改造

### 4.1 模型路由

替换 `_get_model_for_role()`:

```python
def _get_model_for_role(role: str) -> str:
    """深度研究 v2: 各角色模型分配

    原则:
    - CTO/CPO: gpt_5_4（最强推理）→ gpt_4o_norway
    - CMO: doubao_seed_pro（中文互联网）→ doubao_seed_lite
    - CDO: gemini_3_1_pro（多模态）→ gemini_3_pro
    """
    role_model_map = {
        "CTO": "gpt_5_4",
        "CMO": "doubao_seed_pro",
        "CDO": "gemini_3_1_pro",
        "CPO": "gpt_5_4",
    }
    return role_model_map.get(role.upper(), "gpt_5_4")

# 降级映射表
FALLBACK_MAP = {
    "gpt_5_4": "gpt_4o_norway",
    "doubao_seed_pro": "doubao_seed_lite",
    "gemini_3_1_pro": "gemini_3_pro",
    "gemini_3_pro": "gemini_2_5_pro",
    "o3_deep_research": "gpt_5_4",  # o3 失败降级到 gpt-5.4
}
```

替换 `_get_model_for_task()`:

```python
def _get_model_for_task(task_type: str) -> str:
    """深度研究 v2: 各环节模型分配

    分层:
    - 搜索: o3_deep_research + doubao_seed_pro（并行）
    - 提炼: gemini_2_5_flash（便宜无限额）
    - 整合: gpt_5_4（最强推理）
    - Critic: gemini_3_1_pro（独立于 synthesis 模型）
    """
    task_model_map = {
        "discovery": "gemini_2_5_flash",
        "query_generation": "gemini_2_5_flash",
        "data_extraction": "gemini_2_5_flash",    # Layer 2 提炼
        "role_assign": "gemini_2_5_flash",
        "synthesis": "gpt_5_4",                    # Layer 4
        "re_synthesis": "gpt_5_4",
        "final_synthesis": "gpt_5_4",
        "critic_challenge": "gemini_3_1_pro",      # Layer 5
        "consistency_check": "gemini_3_1_pro",
        "knowledge_extract": "gemini_2_5_flash",
        "fix": "gemini_2_5_pro",
        "cdo_fix": "gemini_2_5_pro",
    }
    return task_model_map.get(task_type, "gpt_5_4")
```

### 4.2 替换 `_call_model()` 为带降级的版本

```python
def _call_model(model_name: str, prompt: str, system_prompt: str = None,
                task_type: str = "general") -> dict:
    """统一模型调用入口，自动降级"""
    result = gateway.call(model_name, prompt, system_prompt, task_type)
    if result.get("success"):
        return result

    # 自动降级
    fallback = FALLBACK_MAP.get(model_name)
    if fallback and fallback in gateway.models:
        print(f"  [Degrade] {model_name} failed, trying {fallback}")
        result2 = gateway.call(fallback, prompt, system_prompt, task_type)
        result2["degraded_from"] = model_name
        return result2

    return result
```

### 4.3 Layer 1 改造: 并行双搜索

替换 `deep_research_one()` 中 Step 1 的搜索逻辑（约第 544-569 行）:

```python
    # === Layer 1: 并行双搜索 ===
    all_sources = []

    hb = ProgressHeartbeat(
        f"深度研究:{title[:20]}",
        total=len(searches),
        feishu_callback=progress_callback,
        log_interval=3, feishu_interval=5, feishu_time_interval=180
    )

    for i, query in enumerate(searches, 1):
        print(f"  [{i}/{len(searches)}] 搜索: {query[:50]}...")
        source_text = ""

        # Channel A: o3-deep-research（英文技术 + 专利）
        o3_result = _call_model("o3_deep_research", query,
                                "Search for technical specifications, patents, and research papers.",
                                "deep_research_search")
        if o3_result.get("success") and len(o3_result.get("response", "")) > 200:
            source_text += o3_result["response"][:3000]
            model_used = o3_result.get("degraded_from", "o3_deep_research") if o3_result.get("degraded_from") else "o3"
            print(f"    o3: {len(o3_result['response'])} 字 (via {model_used})")

        # Channel B: doubao（中文互联网）
        cn_query = query  # 豆包能处理中英文混合
        doubao_result = _call_model("doubao_seed_pro", cn_query,
                                    "搜索中文互联网信息，重点关注小红书、B站、知乎、雪球、1688等平台的相关内容。",
                                    "chinese_search")
        if doubao_result.get("success") and len(doubao_result.get("response", "")) > 200:
            source_text += "\n---\n" + doubao_result["response"][:3000]
            print(f"    doubao: {len(doubao_result['response'])} 字")

        # Fallback: tavily（仅当双通道都失败时）
        if not source_text:
            tavily_result = registry.call("tavily_search", query)
            if tavily_result.get("success") and len(tavily_result.get("data", "")) > 200:
                source_text = tavily_result["data"][:3000]
                print(f"    tavily(fallback): {len(tavily_result['data'])} 字")

        if source_text:
            all_sources.append({"query": query, "content": source_text[:6000]})
            hb.tick(detail=query[:40], success=True)
        else:
            print(f"    ❌ 三通道全部无结果")
            hb.tick(detail=f"失败: {query[:40]}", success=False)

        time.sleep(2)

    hb.finish(f"搜索完成，{len(all_sources)}/{len(searches)} 有效")
```

### 4.4 Layer 2: 结构化提炼（Bug 2 修复）

在 Step 1 搜索完成后、Step 2 知识库检索之前，插入:

```python
    # === Layer 2: 结构化提炼 ===
    # 每条搜索结果独立提取，用 Flash（便宜无限额）
    print(f"  [L2] 开始结构化提炼 ({len(all_sources)} 条)...")
    structured_data_list = []
    task_type_hint = task.get("goal", "") + " " + title

    for src in all_sources:
        extracted = _extract_structured_data(
            raw_text=src["content"],
            task_type=task_type_hint,
            topic=src["query"]
        )
        if extracted:
            structured_data_list.append(extracted)

    print(f"  [L2] 提炼完成: {len(structured_data_list)}/{len(all_sources)} 成功")

    # 序列化供后续层使用
    structured_dump = ""
    if structured_data_list:
        structured_dump = json.dumps(structured_data_list, ensure_ascii=False, indent=2)
```

### 4.5 Layer 3: Agent 只看提炼数据

修改 Step 3.5 中 Agent 的输入材料:

```python
    # Layer 3 输入: 提炼数据 + KB，不是原始搜索材料
    distilled_material = structured_dump[:8000] if structured_dump else source_dump[:8000]
    kb_material = kb_context[:2000]
```

CTO/CMO/CDO 的 prompt 中，将 `source_material` 改为 `distilled_material`，并加说明:

```python
    # 在每个 Agent prompt 的材料部分:
    f"## 调研数据（已结构化提炼，每个数据点附 source 和 confidence）\n{distilled_material}\n\n"
    f"## 已有知识库\n{kb_material}\n\n"
```

### 4.6 Layer 4: Synthesis 只看 Agent 输出

当前代码已经是这样（`agent_section` 只拼 Agent 输出）。确认 synthesis_prompt 中**不要再包含** `source_material` 或 `source_dump`。只保留:
- agent_section（~4.5k 字）
- goal
- product_anchor
- THINKING_PRINCIPLES

### 4.7 Layer 5: Critic 独立 + 交叉验证（Bug 3 修复）

**Step A:** 提取 `_run_critic_challenge()` 为独立函数。

与之前的文档相同，但新增一个参数 `structured_data`:

```python
def _run_critic_challenge(report: str, goal: str, agent_outputs: dict,
                          structured_data: str = "",
                          progress_callback=None) -> str:
    """Layer 5: Critic 挑战 + 交叉验证

    新增: 将 Layer 2 的结构化数据传入，
    Critic 可以用原始数据点交叉验证报告中的结论。
    """
    if len(report) < 500:
        print("  [Critic] 报告太短，跳过")
        return report

    print("  [L5] 开始 Critic 挑战...")

    # 附加结构化数据供交叉验证
    cross_validate_section = ""
    if structured_data:
        cross_validate_section = (
            f"\n\n## 原始结构化数据（用于交叉验证）\n"
            f"以下是 Layer 2 提炼的结构化数据点。"
            f"请检查报告结论是否与这些数据点一致。\n"
            f"{structured_data[:4000]}\n"
        )

    critic_prompt = (
        f"你的职责不是打分，而是提出最尖锐、最有建设性的挑战问题。\n\n"
        f"## 任务目标\n{goal}\n\n"
        f"## 报告（{len(report)}字）\n{report[:8000]}\n\n"
        f"{cross_validate_section}"
        # ... 挑战规则同之前文档，不重复
    )
    # ... 后续逻辑同之前文档
```

**Step B:** 删除 `deep_research_one()` 中第 852-969 行的内联 Critic。

**Step C:** 在所有报告生成路径汇合后，统一调用:

```python
    # === Layer 5: Critic（所有路径统一执行）===
    report = _run_critic_challenge(
        report, goal, agent_outputs,
        structured_data=structured_dump,
        progress_callback=progress_callback
    )
```

### 4.8 Bug 4 修复: 跨研究一致性校验

在 `run_research_from_file()` 和 `run_all()` 中，所有任务完成后、汇总保存前，插入一致性校验。代码同之前文档，不变。

### 4.9 专家框架注入

在 `deep_research_one()` 中 Step 3.5 之前插入框架匹配。代码同之前文档，不变。

### 4.10 fallback 修正

约第 774 行:
```python
# 当前: _call_model("o3", ...)
# 改为: _call_model("gpt_5_4", ...)
```

---

## 五、.env 确认

```bash
# Azure A（已有）
AZURE_OPENAI_API_KEY=4VUFOKsbvcaBC9JQl0KNPr4bSsQMNkkQAnuWN3pVCUk2CbgjhV1nJQQJ99CCACHYHv6XJ3w3AAAAACOGYOQ8
AZURE_OPENAI_ENDPOINT=https://ai-share01ai443564620477.openai.azure.com/

# Azure B - Norway East（新增）
AZURE_OPENAI_NORWAY_API_KEY=2SwRIP65U55sR36FdpwhKRPVCwNYW2BqxSUcoqUjijddJwtD9r5GJQQJ99BHAChHRaEXJ3w3AAAAACOGU4pd
AZURE_OPENAI_NORWAY_ENDPOINT=https://admin-me1ed2lc-norwayeast.services.ai.azure.com/

# 火山引擎（新增）
ARK_API_KEY=06d4009f-65fe-4918-9046-ae454d34120d
```

---

## 六、执行顺序

1. `model_gateway.py`: 添加 `call_azure_responses()`
2. `model_gateway.py`: 更新 `call()` 入口
3. `model_gateway.py`: 添加 `call_with_fallback()`
4. `model_registry.yaml`: 补全所有新模型配置
5. `tonight_deep_research.py`: 替换 `_get_model_for_role()` + `_get_model_for_task()` + `FALLBACK_MAP`
6. `tonight_deep_research.py`: 替换 `_call_model()` 为降级版本
7. `tonight_deep_research.py`: Layer 1 改造（并行双搜索）
8. `tonight_deep_research.py`: Layer 2 插入（结构化提炼）
9. `tonight_deep_research.py`: Layer 3 修改（Agent 输入改为提炼数据）
10. `tonight_deep_research.py`: Layer 5（Critic 独立 + 交叉验证）
11. `tonight_deep_research.py`: Bug 4（跨研究一致性校验）
12. `tonight_deep_research.py`: 专家框架注入
13. `tonight_deep_research.py`: fallback `"o3"` → `"gpt_5_4"`

```bash
git add -A && git commit -m "feat: deep research v2 — five-layer pipeline, dual search, bug fixes"
```

**不要重启服务，Leo 手动重启。**

---

## 七、验证

```bash
python scripts/test_model_availability.py
```

期望:
- gpt_5_4 ✅
- o3_deep_research ✅（Responses API）
- gpt_4o_norway ✅
- doubao_seed_pro ✅
- gemini_3_1_pro ✅
- gemini_2_5_flash ✅

日志关键标记:
- `[Azure-Responses]` → o3 在工作
- `[L2]` → 结构化提炼在工作
- `[Degrade]` → 降级链在工作
- `[L5]` → Critic 在工作
- `doubao` → 豆包搜索在工作
