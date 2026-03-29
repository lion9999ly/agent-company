"""逐个测试 model_registry 中所有模型的可用性"""
import os
import sys
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(str(PROJECT_ROOT / ".env"))

from src.utils.model_gateway import get_model_gateway

gateway = get_model_gateway()

# 要测试的模型列表（深度研究管道用到的）
test_models = [
    ("o3", "azure_openai"),
    ("o3_deep_research", "azure_openai"),
    ("gpt_5_4", "azure_openai"),
    ("gemini_3_1_pro", "google"),
    ("gemini_2_5_flash", "google"),
    ("gpt_5_3", "azure_openai"),
]

print("=" * 60)
print("模型可用性测试")
print("=" * 60)

for model_name, expected_provider in test_models:
    cfg = gateway.models.get(model_name)
    if not cfg:
        print(f"  ❌ {model_name}: 未在 registry 中找到")
        continue
    if not cfg.api_key:
        print(f"  ❌ {model_name}: 无 API key")
        continue

    print(f"\n  Testing {model_name} (deployment={cfg.deployment}, model={cfg.model})...")
    result = gateway.call(model_name, "Say hello in one word.", "You are a test bot.", "general")

    if result.get("success"):
        resp_preview = result.get("response", "")[:80]
        print(f"  ✅ {model_name}: OK — {resp_preview}")
    else:
        error = result.get("error", "unknown")[:200]
        status = result.get("status_code", "?")
        print(f"  ❌ {model_name}: FAILED (status={status}) — {error}")

        # 如果是 404，给出修复建议
        if "404" in str(error) or status == 404:
            print(f"     💡 建议：检查 Azure portal 中 {model_name} 的实际 deployment 名称")
            print(f"     💡 当前配置 deployment={cfg.deployment}")

print("\n" + "=" * 60)

# === 探测 o3 / gpt-5.3 实际 deployment 名称 ===
import requests

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