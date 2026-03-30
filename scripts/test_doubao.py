"""探测豆包（火山引擎）API 可用模型和能力"""
import os
import sys
import requests
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(str(PROJECT_ROOT / ".env"))

API_KEY = os.environ.get("DOUBAO_API_KEY", "")
ENDPOINT = os.environ.get("DOUBAO_ENDPOINT", "https://ark.cn-beijing.volces.com/api/v3")

if not API_KEY:
    print("DOUBAO_API_KEY not set in .env")
    print("Please add to .env:")
    print("  DOUBAO_API_KEY=your_api_key")
    print("  DOUBAO_ENDPOINT=https://ark.cn-beijing.volces.com/api/v3")
    sys.exit(1)

print(f"Endpoint: {ENDPOINT}")
print(f"API Key: {API_KEY[:8]}...")

# 豆包 API 兼容 OpenAI 格式
headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

# Step 1: 列出可用模型
print("\n" + "=" * 60)
print("Probing available models")
print("=" * 60)

try:
    resp = requests.get(f"{ENDPOINT}/models", headers=headers, timeout=15)
    if resp.status_code == 200:
        models = resp.json().get("data", [])
        print(f"Found {len(models)} models:")
        for m in models:
            mid = m.get("id", "?")
            owner = m.get("owned_by", "?")
            print(f"  {mid} (owner: {owner})")
    else:
        print(f"List models failed: {resp.status_code} {resp.text[:200]}")
        print("Trying direct model tests...")
except Exception as e:
    print(f"List models failed: {e}")
    print("Trying direct model tests...")

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
print(f"Testing {len(known_models)} known models")
print(f"{'=' * 60}")

available = []
for model_id in known_models:
    try:
        resp = requests.post(
            f"{ENDPOINT}/chat/completions",
            headers=headers,
            json={
                "model": model_id,
                "messages": [{"role": "user", "content": "Hi, reply in one word"}],
                "max_tokens": 10
            },
            timeout=15
        )
        if resp.status_code == 200:
            result = resp.json()
            text = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            print(f"  OK {model_id}: {text[:30]}")
            available.append(model_id)
        else:
            error = resp.json().get("error", {}).get("message", resp.text[:100])
            if "model not found" in error.lower() or "does not exist" in error.lower():
                pass  # 静默跳过不存在的模型
            else:
                print(f"  WARN {model_id}: {resp.status_code} - {error[:80]}")
    except requests.exceptions.Timeout:
        print(f"  TIMEOUT {model_id}")
    except Exception as e:
        pass

# Step 3: 测试搜索/联网能力（如果有）
print(f"\n{'=' * 60}")
print("Testing web search capability")
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
                "messages": [{"role": "user", "content": "What is today's date? What's the latest tech news?"}],
                "max_tokens": 200,
                "tools": [{"type": "web_search"}]  # 豆包联网搜索
            },
            timeout=30
        )
        if resp.status_code == 200:
            result = resp.json()
            text = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            has_search = "search" in str(result).lower() or "web" in str(result).lower()
            print(f"  OK {test_model} web search: {'supported' if has_search else 'maybe'}")
            print(f"  Response: {text[:200]}")
        else:
            print(f"  Web search test failed: {resp.status_code}")
    except Exception as e:
        print(f"  Error: {e}")

print(f"\n{'=' * 60}")
print(f"Summary: {len(available)} available models")
for m in available:
    print(f"  -> {m}")
print(f"{'=' * 60}")