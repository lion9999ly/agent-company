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

# === 探测 Azure 全量模型 ===
import requests

endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", "").rstrip("/")
api_key = os.environ.get("AZURE_OPENAI_API_KEY", "")
api_version = "2024-12-01-preview"

if not endpoint or not api_key:
    print("\nAZURE_OPENAI_ENDPOINT or AZURE_OPENAI_API_KEY not set")
else:
    # o3 系列扩展探测
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

    all_candidates = (
        [("o3", c) for c in o3_candidates_extended] +
        [("gpt", c) for c in gpt_candidates_extended] +
        [("other", c) for c in other_candidates_extended]
    )

    print(f"\n{'='*60}")
    print(f"Extended Azure probe ({len(all_candidates)} candidates)")
    print(f"Endpoint: {endpoint[:50]}...")
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
                print(f"  OK [{group}] {dep_name}")
                found.append(dep_name)
            else:
                # 非 404 非 200，可能是权限/配额问题，但至少说明 deployment 存在
                print(f"  {resp.status_code} [{group}] {dep_name}")
                found.append(f"{dep_name} (status={resp.status_code})")
        except requests.exceptions.Timeout:
            print(f"  TIMEOUT [{group}] {dep_name}")
        except Exception as e:
            pass  # 网络错误，跳过

    print(f"\n{'='*60}")
    if found:
        print(f"Found {len(found)} available deployments:")
        for d in found:
            print(f"  -> {d}")
    else:
        print("No additional deployments found.")
    print(f"{'='*60}")