"""逐个测试 model_registry 中所有模型的可用性"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

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