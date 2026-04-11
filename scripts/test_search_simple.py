"""
简单测试搜索层
"""
import sys
import io
import time
from pathlib import Path

# Windows UTF-8 输出
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv(project_root / ".env")

# 测试单个搜索任务
task = {
    "id": "test_seeya",
    "title": "SeeYA SY049 OLED",
    "goal": "查找 SeeYA SY049 OLED 微显示屏的技术规格",
    "searches": ["SeeYA SY049 OLED microdisplay specifications"]
}

print("=== 测试搜索层 ===")
print(f"任务: {task['title']}")

from scripts.deep_research.pipeline import deep_research_one

start = time.time()
try:
    result = deep_research_one(task)
    elapsed = time.time() - start
    print(f"\n=== 完成 ===")
    print(f"耗时: {elapsed:.1f} 秒")
    print(f"报告长度: {len(result)} 字")
    print(f"\n报告内容预览:\n{result[:1000]}")
except Exception as e:
    elapsed = time.time() - start
    print(f"\n=== 失败 ===")
    print(f"耗时: {elapsed:.1f} 秒")
    print(f"错误: {e}")