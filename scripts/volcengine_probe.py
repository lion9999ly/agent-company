"""火山引擎能力探测脚本"""
import os
import json
import urllib.request
import urllib.error
from pathlib import Path

# 读取 .env 文件
env_path = Path('.env')
if env_path.exists():
    for line in env_path.read_text(encoding='utf-8').split('\n'):
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            key, val = line.split('=', 1)
            os.environ[key] = val

ARK_API_KEY = os.getenv('ARK_API_KEY', '')
BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"

results = []

def make_request(url: str, payload: dict, method: str = "POST") -> tuple:
    """发起 HTTP 请求"""
    headers = {
        "Authorization": f"Bearer {ARK_API_KEY}",
        "Content-Type": "application/json"
    }
    try:
        data = json.dumps(payload).encode('utf-8') if payload else None
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = resp.read().decode('utf-8')
            return resp.getcode(), body[:500]
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode('utf-8')
        except:
            body = str(e)
        return e.code, body[:500]
    except Exception as e:
        return 0, str(e)


print("=" * 70)
print("火山引擎能力探测")
print("=" * 70)
print(f"ARK_API_KEY: {'SET' if ARK_API_KEY else 'NOT SET'} (len={len(ARK_API_KEY)})")
print()

# 1. 列出所有可用模型
print("1. 查询可用模型列表...")
code, body = make_request(f"{BASE_URL}/models", None, "GET")
print(f"   Status: {code}")
if code == 200:
    try:
        models_data = json.loads(body)
        print(f"   响应: {json.dumps(models_data, ensure_ascii=False, indent=2)[:1500]}")
        results.append(("Models List", "api/v3/models", code, "OK"))
    except:
        print(f"   响应: {body}")
        results.append(("Models List", "api/v3/models", code, body[:100]))
else:
    print(f"   错误: {body}")
    results.append(("Models List", "api/v3/models", code, body[:100]))

# 2. 图片理解 - doubao
print("\n2. 测试豆包图片理解...")
vision_payload = {
    "model": "doubao-seed-2-0-pro-260215",
    "messages": [{
        "role": "user",
        "content": [
            {"type": "text", "text": "描述这张图片"},
            {"type": "image_url", "image_url": {"url": "https://upload.wikimedia.org/wikipedia/commons/thumb/a/a7/Camponotus_flavomarginatus_ant.jpg/320px-Camponotus_flavomarginatus_ant.jpg"}}
        ]
    }]
}
code, body = make_request(f"{BASE_URL}/chat/completions", vision_payload)
print(f"   Status: {code}")
if code == 200:
    results.append(("Image Vision", "doubao-seed-2-0-pro", code, "OK"))
    print(f"   响应: {body[:300]}...")
else:
    results.append(("Image Vision", "doubao-seed-2-0-pro", code, body[:100]))
    print(f"   错误: {body}")

# 3. 图片理解 - deepseek
print("\n3. 测试 DeepSeek 图片理解...")
vision_payload_ds = {
    "model": "deepseek-v3-2-251201",
    "messages": [{
        "role": "user",
        "content": [
            {"type": "text", "text": "描述这张图片"},
            {"type": "image_url", "image_url": {"url": "https://upload.wikimedia.org/wikipedia/commons/thumb/a/a7/Camponotus_flavomarginatus_ant.jpg/320px-Camponotus_flavomarginatus_ant.jpg"}}
        ]
    }]
}
code, body = make_request(f"{BASE_URL}/chat/completions", vision_payload_ds)
print(f"   Status: {code}")
if code == 200:
    results.append(("Image Vision", "deepseek-v3-2", code, "OK"))
    print(f"   响应: {body[:300]}...")
else:
    results.append(("Image Vision", "deepseek-v3-2", code, body[:100]))
    print(f"   错误: {body}")

# 4. 图片生成 - Seedream
print("\n4. 测试图片生成 Seedream...")
seedream_models = ["seedream-3-0", "seedream-3.0", "Seedream-3-0", "seedream_3_0"]
for model_name in seedream_models:
    img_gen_payload = {
        "model": model_name,
        "prompt": "a motorcycle helmet with HUD display",
        "size": "1024x1024",
        "n": 1
    }
    code, body = make_request(f"{BASE_URL}/images/generations", img_gen_payload)
    print(f"   Model: {model_name}, Status: {code}")
    if code == 200:
        results.append(("Image Gen", model_name, code, "OK"))
        print(f"   响应: {body[:300]}...")
        break
    elif code != 404:
        results.append(("Image Gen", model_name, code, body[:100]))
        print(f"   错误: {body[:200]}")
    else:
        print(f"   模型不存在")

if not any(r[0] == "Image Gen" and r[3] == "OK" for r in results):
    results.append(("Image Gen", "seedream-*", 404, "Model not found"))

# 5. 视频生成 - Seedance
print("\n5. 测试视频生成 Seedance...")
seedance_models = ["seedance-1-0", "seedance-1.0", "Seedance-1-0", "seedance_1_0"]
for model_name in seedance_models:
    video_gen_payload = {
        "model": model_name,
        "prompt": "a motorcycle rider wearing smart helmet",
        "duration": 3
    }
    code, body = make_request(f"{BASE_URL}/contents/generations", video_gen_payload)
    print(f"   Model: {model_name}, Status: {code}")
    if code == 200:
        results.append(("Video Gen", model_name, code, "OK"))
        print(f"   响应: {body[:300]}...")
        break
    elif code != 404:
        results.append(("Video Gen", model_name, code, body[:100]))
        print(f"   错误: {body[:200]}")
    else:
        print(f"   模型不存在")

if not any(r[0] == "Video Gen" and r[3] == "OK" for r in results):
    results.append(("Video Gen", "seedance-*", 404, "Model not found"))

# 6. 联网搜索
print("\n6. 测试联网搜索...")
web_search_payload = {
    "model": "doubao-seed-2-0-pro-260215",
    "messages": [{"role": "user", "content": "2026年4月智能头盔市场最新动态"}],
    "tools": [{"type": "web_search"}]
}
code, body = make_request(f"{BASE_URL}/chat/completions", web_search_payload)
print(f"   Status: {code}")
if code == 200:
    results.append(("Web Search", "doubao-seed-2-0-pro", code, "OK"))
    print(f"   响应: {body[:400]}...")
else:
    results.append(("Web Search", "doubao-seed-2-0-pro", code, body[:100]))
    print(f"   错误: {body}")

# 7. 基础对话测试
print("\n7. 测试基础对话...")
for model in ["doubao-seed-2-0-pro-260215", "doubao-seed-2-0-lite-260215", "deepseek-v3-2-251201"]:
    chat_payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Hello, respond with 'OK'"}],
        "max_tokens": 10
    }
    code, body = make_request(f"{BASE_URL}/chat/completions", chat_payload)
    status = "OK" if code == 200 else body[:50]
    results.append(("Chat", model, code, status))
    print(f"   {model}: {code}")

# 输出结果表
print("\n" + "=" * 80)
print("能力探测结果汇总")
print("=" * 80)
print(f"{'能力':<15} {'Model':<30} {'Status':<8} 结果")
print("-" * 80)

for capability, model, status, result in results:
    result_short = result[:40] if len(result) > 40 else result
    print(f"{capability:<15} {model:<30} {status:<8} {result_short}")

print("=" * 80)

# 统计
ok_count = sum(1 for r in results if r[2] == 200)
fail_count = sum(1 for r in results if r[2] != 200)
print(f"\n总计: {len(results)} | OK: {ok_count} | FAIL: {fail_count}")

# 保存结果
result_path = Path('.ai-state/volcengine_capability_probe.json')
result_path.parent.mkdir(parents=True, exist_ok=True)
result_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
print(f"\n结果已保存到: {result_path}")