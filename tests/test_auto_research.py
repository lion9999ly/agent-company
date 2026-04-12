"""Test auto research extraction"""
import sys
sys.path.insert(0, '.')
sys.stdout.reconfigure(encoding='utf-8')
import json
import re
from dotenv import load_dotenv
load_dotenv()

# Test the extraction logic
from scripts.litellm_gateway import get_model_gateway

gateway = get_model_gateway()
test_report = """
知识缺口：ADAS安全维度仅69条，远低于其他维度。
行动建议：建议重点研究毫米波雷达在摩托车头盔上的集成方案、V2X通讯标准、以及ADAS传感器供应商对比。
"""

extract_prompt = (
    f"从以下对齐报告提取2个研究主题，输出JSON数组。每个主题包含title和searches字段。\n{test_report}"
)
result = gateway.call_azure_openai("cpo", extract_prompt, "只输出JSON数组。", "test")

if result.get("success"):
    resp = result["response"].strip()
    resp = re.sub(r"^```json\s*", "", resp)
    resp = re.sub(r"^```\s*", "", resp)
    resp = re.sub(r"\s*```$", "", resp)
    try:
        tasks = json.loads(resp)
        print(f"Extracted {len(tasks)} research topics:")
        for t in tasks:
            print(f"  - {t.get('title', '')}")
        print("Task 5 verified OK")
    except Exception as e:
        print(f"JSON parse error: {e}")
        print(f"Response: {resp[:200]}")
else:
    print(f"LLM call failed: {result.get('error')}")