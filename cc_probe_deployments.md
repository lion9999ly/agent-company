# CC 指令：探测 o3 / gpt-5.3 实际 deployment 名称

> 执行文档 — 2026-03-30
> 不涉及 git commit，纯诊断

---

## 原理

Azure OpenAI 的 deployment 名称由用户创建时自定义，常见命名模式有限。
逐个尝试，返回非 404 的就是正确的 deployment 名称。

## 执行

在 `scripts/test_model_availability.py` 底部追加以下代码，然后重新运行：

```python
# === 探测 o3 实际 deployment 名称 ===
import requests, os

endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", "").rstrip("/")
api_key = os.environ.get("AZURE_OPENAI_API_KEY", "")
api_version = "2024-12-01-preview"

if not endpoint or not api_key:
    print("\n⚠️ AZURE_OPENAI_ENDPOINT 或 AZURE_OPENAI_API_KEY 未设置")
else:
    # 常见 o3 deployment 命名模式
    o3_candidates = [
        "o3", "o3-mini", "o3-2025-04-16", "o3-mini-2025-01-31",
        "o3-2025-01-31", "o3-preview", "o3-mini-high",
        "o3-pro", "o3-pro-2025-06-10",
        "o3-deep-research", "o3-deep-research-2025-06-26",
    ]

    gpt53_candidates = [
        "gpt-5.3-chat-2026-03-03", "gpt-53", "gpt-5-3", "gpt53",
        "gpt-5.3", "gpt-5.3-chat", "gpt5-3",
    ]

    # 额外：探测其他可能已部署的模型
    other_candidates = [
        "gpt-4o", "gpt-4o-mini", "gpt-4", "gpt-4-turbo",
        "gpt-4o-2024-08-06", "gpt-4o-mini-2024-07-18",
        "o1", "o1-mini", "o1-preview",
        "deepseek-r1", "DeepSeek-R1", "deepseek-v3",
        "claude-opus-4-6", "claude-sonnet-4-6",
        "grok-4-fast-reasoning",
        "Llama-4-Maverick-17B-128E-Instruct-FP8",
        "qwen-3-32b",
    ]

    all_candidates = (
        [("o3系列", c) for c in o3_candidates] +
        [("gpt-5.3系列", c) for c in gpt53_candidates] +
        [("其他模型", c) for c in other_candidates]
    )

    print(f"\n{'='*60}")
    print(f"探测 Azure deployments (endpoint: {endpoint[:50]}...)")
    print(f"{'='*60}")

    found = []
    for group, dep_name in all_candidates:
        url = f"{endpoint}/openai/deployments/{dep_name}/chat/completions?api-version={api_version}"
        try:
            resp = requests.post(
                url,
                json={"messages": [{"role": "user", "content": "hi"}], "max_tokens": 5},
                headers={"api-key": api_key, "Content-Type": "application/json"},
                timeout=15
            )
            if resp.status_code == 404:
                pass  # 不存在，静默跳过
            elif resp.status_code == 200:
                print(f"  ✅ [{group}] deployment={dep_name} → 200 OK")
                found.append(dep_name)
            else:
                # 非 404 非 200，可能是权限/配额问题，但至少说明 deployment 存在
                print(f"  ⚠️ [{group}] deployment={dep_name} → {resp.status_code}: {resp.text[:100]}")
                found.append(f"{dep_name} (status={resp.status_code})")
        except requests.exceptions.Timeout:
            print(f"  ⏳ [{group}] deployment={dep_name} → timeout (可能存在但慢)")
        except Exception as e:
            pass  # 网络错误，跳过

    print(f"\n{'='*60}")
    if found:
        print(f"发现 {len(found)} 个可用 deployment:")
        for d in found:
            print(f"  → {d}")
    else:
        print("未发现额外 deployment。可能 Azure 上只部署了 gpt-5.4。")
    print(f"{'='*60}")
```

## 运行

```bash
python scripts/test_model_availability.py
```

把完整输出贴回来。

## 不要做的事
- 不要改 model_registry.yaml
- 不要重启服务
- 不要 git commit
