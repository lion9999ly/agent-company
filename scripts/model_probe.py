"""模型 API 可用性测试脚本"""
import os
import yaml
import json
import urllib.request
import urllib.error
from pathlib import Path

# 直接读取 .env 文件
env_path = Path('.env')
if env_path.exists():
    for line in env_path.read_text(encoding='utf-8').split('\n'):
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            key, val = line.split('=', 1)
            os.environ[key] = val

# 加载 registry
registry_path = Path('src/config/model_registry.yaml')
data = yaml.safe_load(registry_path.read_text(encoding='utf-8'))
models = data.get('model_registry', {})

# 获取凭据
AZURE_KEY = os.getenv('AZURE_OPENAI_API_KEY', '')
AZURE_ENDPOINT = os.getenv('AZURE_OPENAI_ENDPOINT', '').rstrip('/')
AZURE_NORWAY_KEY = os.getenv('AZURE_OPENAI_NORWAY_API_KEY', '')
AZURE_NORWAY_ENDPOINT = os.getenv('AZURE_OPENAI_NORWAY_ENDPOINT', '').rstrip('/')
GEMINI_KEY = os.getenv('GEMINI_API_KEY', '')
ARK_KEY = os.getenv('ARK_API_KEY', '')

results = []

def test_azure_chat(endpoint, api_key, deployment, api_version="2024-12-01-preview"):
    """测试 Azure OpenAI Chat API"""
    url = f"{endpoint}/openai/deployments/{deployment}/chat/completions?api-version={api_version}"
    headers = {
        "api-key": api_key,
        "Content-Type": "application/json"
    }
    payload = {
        "messages": [{"role": "user", "content": "Hello"}],
        "max_tokens": 10
    }
    try:
        req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers, method='POST')
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.getcode(), None
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode())
            error_msg = body.get('error', {}).get('code', body.get('error', {}).get('message', str(body)[:100]))
        except:
            error_msg = str(e)
        return e.code, error_msg
    except Exception as e:
        return 0, str(e)

def test_azure_responses(endpoint, api_key, deployment, api_version="2025-04-01-preview"):
    """测试 Azure OpenAI Responses API (for o3 models)"""
    url = f"{endpoint}/openai/deployments/{deployment}/responses?api-version={api_version}"
    headers = {
        "api-key": api_key,
        "Content-Type": "application/json"
    }
    payload = {
        "input": "Hello",
        "max_output_tokens": 10
    }
    try:
        req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers, method='POST')
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.getcode(), None
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode())
            error_msg = body.get('error', {}).get('code', body.get('error', {}).get('message', str(body)[:100]))
        except:
            error_msg = str(e)
        return e.code, error_msg
    except Exception as e:
        return 0, str(e)

def test_gemini(api_key, model):
    """测试 Gemini API"""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{"parts": [{"text": "Hello"}]}]
    }
    try:
        req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers, method='POST')
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.getcode(), None
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode())
            error_msg = body.get('error', {}).get('code', body.get('error', {}).get('message', str(body)[:100]))
        except:
            error_msg = str(e)
        return e.code, error_msg
    except Exception as e:
        return 0, str(e)

def test_volcengine(api_key, model):
    """测试火山引擎 API"""
    url = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Hello"}],
        "max_tokens": 10
    }
    try:
        req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers, method='POST')
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.getcode(), None
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode())
            error_msg = body.get('error', {}).get('code', body.get('error', {}).get('message', str(body)[:100]))
        except:
            error_msg = str(e)
        return e.code, error_msg
    except Exception as e:
        return 0, str(e)

def list_azure_deployments(endpoint, api_key):
    """列出 Azure 可用的部署"""
    url = f"{endpoint}/openai/deployments?api-version=2024-12-01-preview"
    headers = {"api-key": api_key}
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode())
            return [d.get('id') for d in body.get('data', [])]
    except Exception as e:
        return [f"Error: {e}"]


if __name__ == "__main__":
    print("="*60)
    print("环境变量检查")
    print("="*60)
    print(f"AZURE_OPENAI_API_KEY: {'SET' if AZURE_KEY else 'NOT SET'} (len={len(AZURE_KEY)})")
    print(f"AZURE_OPENAI_ENDPOINT: {AZURE_ENDPOINT}")
    print(f"AZURE_OPENAI_NORWAY_API_KEY: {'SET' if AZURE_NORWAY_KEY else 'NOT SET'} (len={len(AZURE_NORWAY_KEY)})")
    print(f"AZURE_OPENAI_NORWAY_ENDPOINT: {AZURE_NORWAY_ENDPOINT}")
    print(f"GEMINI_API_KEY: {'SET' if GEMINI_KEY else 'NOT SET'} (len={len(GEMINI_KEY)})")
    print(f"ARK_API_KEY: {'SET' if ARK_KEY else 'NOT SET'} (len={len(ARK_KEY)})")

    print("\nTesting models...")
    # 测试每个模型
    for name, config in models.items():
        provider = config.get('provider', '')
        deployment = config.get('deployment', '')
        model = config.get('model', '')

        status = "?"
        error = None

        if provider == 'azure_openai':
            endpoint_env = config.get('endpoint_env', '')

            if 'NORWAY' in endpoint_env:
                endpoint = AZURE_NORWAY_ENDPOINT
                api_key = AZURE_NORWAY_KEY
            else:
                endpoint = AZURE_ENDPOINT
                api_key = AZURE_KEY

            if not endpoint or not api_key:
                status = "SKIP"
                error = "Missing credentials"
            elif 'o3' in name.lower():
                status, error = test_azure_responses(endpoint, api_key, deployment)
            else:
                status, error = test_azure_chat(endpoint, api_key, deployment)

        elif provider == 'google':
            if not GEMINI_KEY:
                status = "SKIP"
                error = "Missing GEMINI_API_KEY"
            else:
                status, error = test_gemini(GEMINI_KEY, model)

        elif provider == 'volcengine':
            if not ARK_KEY:
                status = "SKIP"
                error = "Missing ARK_API_KEY"
            else:
                status, error = test_volcengine(ARK_KEY, model)

        else:
            status = "SKIP"
            error = f"Unknown provider: {provider}"

        results.append({
            'name': name,
            'provider': provider,
            'deployment': deployment or model,
            'status': status,
            'error': error
        })
        print(f"  {name}: {status}")

    # 输出结果表
    print("\n" + "="*110)
    print("模型 API 可用性测试结果")
    print("="*110)
    print(f"{'模型':<25} {'Provider':<15} {'Deployment':<40} {'Status':<8} 结果")
    print("-"*110)

    for r in results:
        status_str = str(r['status'])
        if r['status'] == 200:
            result = "OK"
        elif r['status'] == 0:
            result = f"ERROR: {str(r['error'])[:50] if r['error'] else 'unknown'}"
        elif r['status'] == 'SKIP':
            result = f"SKIP: {str(r['error'])[:50] if r['error'] else 'unknown'}"
        else:
            result = f"FAIL: {str(r['error'])[:50] if r['error'] else 'unknown'}"

        print(f"{r['name']:<25} {r['provider']:<15} {r['deployment']:<40} {status_str:<8} {result}")

    print("="*110)

    # 统计
    ok_count = sum(1 for r in results if r['status'] == 200)
    fail_count = sum(1 for r in results if r['status'] not in [200, 'SKIP'])
    skip_count = sum(1 for r in results if r['status'] == 'SKIP')
    print(f"\nTotal: {len(results)} | OK: {ok_count} | FAIL: {fail_count} | SKIP: {skip_count}")

    # 列出 Azure 可用的部署
    print("\n" + "="*60)
    print("Azure 主账号可用部署:")
    print("="*60)
    deployments = list_azure_deployments(AZURE_ENDPOINT, AZURE_KEY)
    for d in deployments:
        print(f"  - {d}")

    print("\n" + "="*60)
    print("Azure Norway 账号可用部署:")
    print("="*60)
    deployments_norway = list_azure_deployments(AZURE_NORWAY_ENDPOINT, AZURE_NORWAY_KEY)
    for d in deployments_norway:
        print(f"  - {d}")

    # 保存结果
    result_path = Path('.ai-state/model_probe_results.json')
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"\n结果已保存到: {result_path}")