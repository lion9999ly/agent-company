# CC 指令：豆包 API 接入 + Azure 模型全量探测

> 执行文档 — 2026-03-30
> 不涉及 PRD 生成，纯配置和诊断
> 分两部分独立执行

---

## Part 1：豆包（火山引擎）API 接入

### Step 1：确认 API 信息

Leo 需要提供以下信息（检查火山引擎控制台）：

- API Key（或 Access Key + Secret Key）
- Endpoint URL（通常是 `https://ark.cn-beijing.volces.com/api/v3`）
- 已开通的模型列表（如果不确定，Step 2 会探测）

把 API Key 加入 `.env` 文件：

```bash
# .env 中新增
DOUBAO_API_KEY=你的API_Key
DOUBAO_ENDPOINT=https://ark.cn-beijing.volces.com/api/v3
```

### Step 2：探测豆包可用模型和能力

创建文件 `scripts/test_doubao.py`：

```python
"""探测豆包（火山引擎）API 可用模型和能力"""
import os
import requests
from dotenv import load_dotenv
load_dotenv()

API_KEY = os.environ.get("DOUBAO_API_KEY", "")
ENDPOINT = os.environ.get("DOUBAO_ENDPOINT", "https://ark.cn-beijing.volces.com/api/v3")

if not API_KEY:
    print("❌ DOUBAO_API_KEY 未设置，请检查 .env")
    exit(1)

print(f"Endpoint: {ENDPOINT}")
print(f"API Key: {API_KEY[:8]}...")

# 豆包 API 兼容 OpenAI 格式
headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

# Step 1: 列出可用模型
print("\n" + "=" * 60)
print("探测可用模型")
print("=" * 60)

try:
    resp = requests.get(f"{ENDPOINT}/models", headers=headers, timeout=15)
    if resp.status_code == 200:
        models = resp.json().get("data", [])
        print(f"发现 {len(models)} 个模型:")
        for m in models:
            mid = m.get("id", "?")
            owner = m.get("owned_by", "?")
            print(f"  {mid} (owner: {owner})")
    else:
        print(f"列出模型失败: {resp.status_code} {resp.text[:200]}")
        print("尝试直接测试已知模型...")
except Exception as e:
    print(f"列出模型失败: {e}")
    print("尝试直接测试已知模型...")

# Step 2: 逐个测试已知的豆包模型
# 注意：豆包的模型 ID 格式可能是 "ep-xxxxxxxx"（endpoint ID）而非模型名
# 也可能支持直接用模型名如 "doubao-pro-32k"
known_models = [
    # 豆包系列
    "doubao-pro-256k",
    "doubao-pro-32k",
    "doubao-pro-4k",
    "doubao-lite-32k",
    "doubao-lite-4k",
    "doubao-character-pro-32k",
    # 豆包视觉
    "doubao-vision-pro-32k",
    "doubao-vision-lite-32k",
    # 豆包嵌入
    "doubao-embedding",
    "doubao-embedding-large",
    # DeepSeek 系列（火山引擎托管）
    "deepseek-r1-250120",
    "deepseek-v3-241226",
    "deepseek-r1-distill-qwen-32b-250120",
    # 其他可能的模型
    "skylark-pro",
    "skylark-lite",
    "skylark-chat",
]

print(f"\n{'=' * 60}")
print(f"逐个测试 {len(known_models)} 个已知模型")
print(f"{'=' * 60}")

available = []
for model_id in known_models:
    try:
        resp = requests.post(
            f"{ENDPOINT}/chat/completions",
            headers=headers,
            json={
                "model": model_id,
                "messages": [{"role": "user", "content": "你好，请用一个词回复"}],
                "max_tokens": 10
            },
            timeout=15
        )
        if resp.status_code == 200:
            result = resp.json()
            text = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            print(f"  ✅ {model_id}: {text[:30]}")
            available.append(model_id)
        else:
            error = resp.json().get("error", {}).get("message", resp.text[:100])
            if "model not found" in error.lower() or "does not exist" in error.lower():
                pass  # 静默跳过不存在的模型
            else:
                print(f"  ⚠️ {model_id}: {resp.status_code} — {error[:80]}")
    except requests.exceptions.Timeout:
        print(f"  ⏳ {model_id}: timeout")
    except Exception as e:
        pass

# Step 3: 测试搜索/联网能力（如果有）
print(f"\n{'=' * 60}")
print("测试联网搜索能力")
print(f"{'=' * 60}")

if available:
    test_model = available[0]
    # 豆包的联网搜索通过 tools 参数启用
    try:
        resp = requests.post(
            f"{ENDPOINT}/chat/completions",
            headers=headers,
            json={
                "model": test_model,
                "messages": [{"role": "user", "content": "今天是几号？最新的科技新闻是什么？"}],
                "max_tokens": 200,
                "tools": [{"type": "web_search"}]  # 豆包联网搜索
            },
            timeout=30
        )
        if resp.status_code == 200:
            result = resp.json()
            text = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            has_search = "search" in str(result).lower() or "web" in str(result).lower()
            print(f"  ✅ {test_model} 联网搜索: {'支持' if has_search else '可能支持'}")
            print(f"  回复: {text[:200]}")
        else:
            print(f"  ❌ 联网搜索测试失败: {resp.status_code}")
            # 尝试不带 tools
            print("  尝试不带 tools 的联网模式...")
    except Exception as e:
        print(f"  ❌ {e}")

print(f"\n{'=' * 60}")
print(f"总结: {len(available)} 个可用模型")
for m in available:
    print(f"  → {m}")
print(f"{'=' * 60}")
```

运行：
```bash
python scripts/test_doubao.py
```

把完整输出贴回来。

### Step 3：接入 model_gateway

等 Step 2 确认可用模型后，在 `src/config/model_registry.yaml` 中新增豆包配置：

```yaml
  # ============================================================
  # 🫘 豆包（火山引擎）阵列
  # ============================================================

  doubao_pro_256k:
    provider: "doubao"
    model: "doubao-pro-256k"  # 根据 Step 2 结果调整
    api_key_env: "DOUBAO_API_KEY"
    endpoint_env: "DOUBAO_ENDPOINT"
    purpose: "中文长上下文、互联网内容分析、中文搜索增强"
    capabilities: ["multilingual", "long_context", "search", "analysis"]
    cost_tier: "$"
    performance: 4
    max_tokens: 4096
    temperature: 0.1

  doubao_pro_32k:
    provider: "doubao"
    model: "doubao-pro-32k"
    api_key_env: "DOUBAO_API_KEY"
    endpoint_env: "DOUBAO_ENDPOINT"
    purpose: "中文通用任务、快速响应"
    capabilities: ["multilingual", "fast", "analysis"]
    cost_tier: "$"
    performance: 4
    max_tokens: 4096
    temperature: 0.1
```

然后在 `src/utils/model_gateway.py` 中新增 `call_doubao` 方法。豆包 API 兼容 OpenAI 格式，可以复用 `call_azure_openai` 的大部分逻辑，只改 endpoint 和 auth header：

```python
def call_doubao(self, model_name: str, prompt: str, system_prompt: str = None,
                task_type: str = "general") -> Dict[str, Any]:
    """调用豆包（火山引擎）API — OpenAI 兼容格式"""
    cfg = self.models.get(model_name)
    if not cfg or not cfg.api_key:
        return {"success": False, "error": f"Model {model_name} not configured"}

    endpoint = cfg.endpoint or "https://ark.cn-beijing.volces.com/api/v3"
    url = f"{endpoint}/chat/completions"

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": cfg.model,
        "messages": messages,
        "max_tokens": cfg.max_tokens,
        "temperature": cfg.temperature
    }

    timeout = TIMEOUT_BY_TASK.get(task_type, 120)
    start_time = time.time()

    try:
        resp = requests.post(
            url, json=payload, timeout=timeout,
            headers={
                "Authorization": f"Bearer {cfg.api_key}",
                "Content-Type": "application/json"
            }
        )
        result = resp.json()
        latency_ms = int((time.time() - start_time) * 1000)

        print(f"  [Doubao-Diag] task={task_type}, status={resp.status_code}")

        if resp.status_code >= 400:
            return {"success": False, "error": f"Doubao {resp.status_code}: {str(result)[:200]}"}

        if 'choices' in result:
            text = result['choices'][0]['message']['content']
            usage = result.get('usage', {})

            if HAS_TRACKER:
                get_tracker().record(
                    model=cfg.model, provider="doubao",
                    prompt_tokens=usage.get('prompt_tokens', 0),
                    completion_tokens=usage.get('completion_tokens', 0),
                    task_type=task_type, success=True, latency_ms=latency_ms
                )

            return {
                "success": True, "model": model_name, "response": text,
                "raw": result,
                "usage": {
                    "prompt_tokens": usage.get('prompt_tokens', 0),
                    "completion_tokens": usage.get('completion_tokens', 0)
                }
            }
        else:
            return {"success": False, "error": str(result)}

    except Exception as e:
        return {"success": False, "error": str(e)}
```

在 `call()` 统一入口中添加 doubao 路由：

```python
def call(self, model_name, prompt, system_prompt=None, task_type="general"):
    cfg = self.models.get(model_name)
    # ... 现有逻辑 ...
    elif cfg.provider == "doubao":
        return self.call_doubao(model_name, prompt, system_prompt, task_type)
    # ...
```

**等 Step 2 结果出来再执行 Step 3。**

---

## Part 2：Azure 全量模型探测

### 重新探测（含 o3 deep research）

更新 `scripts/test_model_availability.py` 中的探测候选列表，加入更多可能的 deployment 名：

```python
# 在探测部分的 all_candidates 中新增：
o3_candidates_extended = [
    # 原有
    "o3", "o3-mini", "o3-2025-04-16", "o3-mini-2025-01-31",
    "o3-2025-01-31", "o3-preview", "o3-mini-high",
    "o3-pro", "o3-pro-2025-06-10",
    "o3-deep-research", "o3-deep-research-2025-06-26",
    # 新增：更多可能的命名
    "o3-2025-06-26", "o3-mini-2025-04-16",
    "o3-deep-research-preview",
    "o3-2026", "o3-latest",
    # Azure 有时用全小写或带版本后缀
    "o3mini", "o3-mini-latest",
]

gpt_candidates_extended = [
    "gpt-5.4", "gpt-5.3", "gpt-5.3-chat-2026-03-03",
    "gpt-5", "gpt-5.0", "gpt-5-turbo",
    "gpt-4o", "gpt-4o-mini", "gpt-4o-2024-08-06",
    "gpt-4", "gpt-4-turbo", "gpt-4-32k",
    "gpt-4o-mini-2024-07-18",
    "gpt-4.1", "gpt-4.1-mini", "gpt-4.1-nano",
    "gpt-4o-2024-11-20",
]

other_candidates_extended = [
    # o1 系列
    "o1", "o1-mini", "o1-preview",
    "o1-2024-12-17", "o1-mini-2024-09-12",
    # Claude via Azure
    "claude-opus-4-6", "claude-sonnet-4-6",
    "claude-3-5-sonnet", "claude-3-opus",
    # DeepSeek via Azure
    "DeepSeek-R1", "deepseek-r1", "DeepSeek-V3", "DeepSeek-V3.2",
    # Llama via Azure
    "Llama-4-Maverick-17B-128E-Instruct-FP8",
    "meta-llama-3.1-405b-instruct",
    "meta-llama-3.1-70b-instruct",
    # Qwen via Azure
    "qwen-3-32b", "Qwen2.5-72B-Instruct",
    # Grok
    "grok-4-fast-reasoning", "grok-3",
    # Phi
    "Phi-4", "Phi-3.5-mini-instruct",
    # Mistral
    "Mistral-large-2411", "mistral-small-2503",
    # DALL-E / Whisper
    "dall-e-3", "whisper",
]
```

运行：
```bash
python scripts/test_model_availability.py
```

把完整输出贴回来。重点关注：
- o3 系列是否有新的可用 deployment
- 是否有之前不知道的已部署模型

---

## 不要做的事
- 不要改 model_registry.yaml（等探测结果出来再改）
- 不要重启飞书服务
- 不要 git commit
