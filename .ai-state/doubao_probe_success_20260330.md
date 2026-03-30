# 火山引擎（豆包）API 探测成功

> 执行时间：2026-03-30

---

## 关键发现

| 项目 | 值 |
|------|-----|
| 正确 Endpoint | `https://ark.cn-beijing.volces.com/api/v3` |
| 错误 Endpoint | `https://ark.cn-beijing.volces.com/api/coding/v3` (InvalidSubscription) |
| API Key | `ARK_API_KEY=06d4009f-65fe-4918-9046-ae454d34120d` |

---

## 可用模型

| 模型 ID | 状态 | 说明 |
|---------|------|------|
| `doubao-seed-2-0-pro-260215` | ✅ OK | 旗舰版，强推理 |
| `doubao-seed-2-0-lite-260215` | ✅ OK | 轻量版，快速响应 |
| `deepseek-v3-2-251201` | ✅ OK | DeepSeek V3.2 |

---

## 接入配置

### model_registry.yaml 新增

```yaml
  # ============================================================
  # 火山引擎（豆包）阵列
  # ============================================================

  doubao_seed_pro:
    provider: "volcengine"
    model: "doubao-seed-2-0-pro-260215"
    api_key_env: "ARK_API_KEY"
    endpoint: "https://ark.cn-beijing.volces.com/api/v3"
    purpose: "中文旗舰推理、长上下文分析"
    capabilities: ["multilingual", "long_context", "analysis"]
    cost_tier: "$$"
    performance: 5
    max_tokens: 4096
    temperature: 0.1

  doubao_seed_lite:
    provider: "volcengine"
    model: "doubao-seed-2-0-lite-260215"
    api_key_env: "ARK_API_KEY"
    endpoint: "https://ark.cn-beijing.volces.com/api/v3"
    purpose: "中文快速响应、轻量任务"
    capabilities: ["multilingual", "fast"]
    cost_tier: "$"
    performance: 4
    max_tokens: 4096
    temperature: 0.1

  deepseek_v3_volcengine:
    provider: "volcengine"
    model: "deepseek-v3-2-251201"
    api_key_env: "ARK_API_KEY"
    endpoint: "https://ark.cn-beijing.volces.com/api/v3"
    purpose: "DeepSeek 推理（火山引擎托管）"
    capabilities: ["reasoning", "multilingual"]
    cost_tier: "$$"
    performance: 5
    max_tokens: 4096
    temperature: 0.1
```

### model_gateway.py 新增

使用 OpenAI SDK 调用（火山引擎 API 兼容 OpenAI 格式）：

```python
def call_volcengine(self, model_name: str, prompt: str, system_prompt: str = None,
                    task_type: str = "general") -> Dict[str, Any]:
    """调用火山引擎（豆包）API — OpenAI 兼容格式"""
    cfg = self.models.get(model_name)
    if not cfg or not cfg.api_key:
        return {"success": False, "error": f"Model {model_name} not configured"}

    endpoint = cfg.endpoint or "https://ark.cn-beijing.volces.com/api/v3"

    client = OpenAI(api_key=cfg.api_key, base_url=endpoint)

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    timeout = TIMEOUT_BY_TASK.get(task_type, 120)
    start_time = time.time()

    try:
        resp = client.chat.completions.create(
            model=cfg.model,
            messages=messages,
            max_tokens=cfg.max_tokens,
            temperature=cfg.temperature
        )
        latency_ms = int((time.time() - start_time) * 1000)

        text = resp.choices[0].message.content
        usage = {"prompt_tokens": resp.usage.prompt_tokens, "completion_tokens": resp.usage.completion_tokens}

        if HAS_TRACKER:
            get_tracker().record(
                model=cfg.model, provider="volcengine",
                prompt_tokens=usage["prompt_tokens"],
                completion_tokens=usage["completion_tokens"],
                task_type=task_type, success=True, latency_ms=latency_ms
            )

        return {"success": True, "model": model_name, "response": text, "usage": usage}

    except Exception as e:
        return {"success": False, "error": str(e)}
```

---

## 下一步

1. 更新 `model_registry.yaml`
2. 更新 `model_gateway.py` 添加 `call_volcengine` 方法
3. 更新 `call()` 统一入口添加 volcengine 路由
4. Git commit