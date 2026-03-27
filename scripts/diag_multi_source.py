"""诊断多源搜索为什么只有 1 src"""
import os, sys
sys.path.insert(0, '.')

# 检查 1: TAVILY_API_KEY
from pathlib import Path
env_file = Path(".env")
if env_file.exists():
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())

tavily_key = os.environ.get("TAVILY_API_KEY", "")
print(f"[1] TAVILY_API_KEY: {'已设置 (' + tavily_key[:8] + '...)' if tavily_key else '未设置'}")

# 检查 2: tavily 包
try:
    from tavily import TavilyClient
    print(f"[2] tavily 包: 已安装")
except ImportError:
    print(f"[2] tavily 包: 未安装")

# 检查 3: 实际调用测试
from src.tools.tool_registry import get_tool_registry
registry = get_tool_registry()

print(f"\n[3] 实际搜索测试:")
test_query = "motorcycle smart helmet HUD AR display 2026"

r1 = registry.call("deep_research", test_query)
print(f"  deep_research: success={r1.get('success')}, data_len={len(r1.get('data', ''))}")
if not r1.get('success'):
    print(f"    error: {r1.get('error', '')[:200]}")

r2 = registry.call("tavily_search", test_query)
print(f"  tavily_search: success={r2.get('success')}, data_len={len(r2.get('data', ''))}")
if not r2.get('success'):
    print(f"    error: {r2.get('error', '')[:200]}")

# 检查 4: alt_query 逻辑
alt_query = test_query.replace("2026", "latest") if "2026" in test_query else test_query + " 2026 review"
r3 = registry.call("tavily_search", alt_query)
print(f"  tavily_alt: success={r3.get('success')}, data_len={len(r3.get('data', ''))}")
if not r3.get('success'):
    print(f"    error: {r3.get('error', '')[:200]}")

total_src = sum(1 for r in [r1, r2, r3] if r.get('success') and len(r.get('data', '')) > 200)
print(f"\n[总计] {total_src}/3 个来源有效")
if total_src >= 2:
    print("多源搜索正常")
else:
    print("多源搜索异常，需要修复")