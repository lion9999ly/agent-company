"""快速测试 Gemini Deep Research 模型是否可用"""
import sys
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.litellm_gateway import get_model_gateway

gateway = get_model_gateway()

# 测试 gemini_deep_research
models_to_test = [
    "gemini_deep_research",
    "gemini_2_5_pro",   # 顺便测这个，也是未验证的
    "gemini_3_pro",      # 同上
]

for name in models_to_test:
    cfg = gateway.models.get(name)
    if not cfg:
        print(f"  ❌ {name}: 未在 registry 中")
        continue
    if not cfg.api_key:
        print(f"  ❌ {name}: 无 API key")
        continue

    print(f"\n  Testing {name} (model={cfg.model})...")
    result = gateway.call(name, "Say hello in one word.", "You are a test bot.", "general")

    if result.get("success"):
        print(f"  ✅ {name}: OK — {result.get('response', '')[:80]}")
    else:
        error = result.get("error", "unknown")[:200]
        print(f"  ❌ {name}: FAILED — {error}")
