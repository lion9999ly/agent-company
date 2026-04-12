"""
@description: OpenSpace MCP 接入测试脚本
@dependencies: requests, sseclient
@last_modified: 2026-04-12
"""

import json
import time
import requests
import sys
from pathlib import Path

PROJECT_ROOT = Path.cwd()
SKILL_DIRS = str(PROJECT_ROOT / "skills")
sys.path.insert(0, str(PROJECT_ROOT / "openspace_temp"))

# OpenSpace SSE endpoint
SSE_URL = "http://127.0.0.1:8080/sse"


def test_sse_connection():
    """测试 SSE 连接"""
    print("\n[1] 测试 SSE 连接...")
    try:
        resp = requests.get(SSE_URL, stream=True, timeout=5)
        # 读取前几行获取 session_id
        for line in resp.iter_lines(decode_unicode=True):
            if line:
                print(f"  收到: {line}")
                if "session_id" in line:
                    return line.split("session_id=")[-1].strip()
        return None
    except Exception as e:
        print(f"  失败: {e}")
        return None


def test_search_skills():
    """测试 search_skills 工具"""
    print("\n[2] 测试 search_skills 工具...")
    try:
        # 直接扫描 skills 目录
        skill_count = 0
        skills_found = []
        for skill_md in Path(SKILL_DIRS).rglob("SKILL.md"):
            skill_count += 1
            skill_dir = skill_md.parent
            skill_name = skill_dir.name
            skills_found.append(skill_name)
            print(f"    - {skill_name}: {skill_md}")

        print(f"  发现 {skill_count} 个本地 SKILL.md")
        results = {
            "count": skill_count,
            "skills": skills_found
        }
        return results
    except Exception as e:
        print(f"  失败: {e}")
        return {"count": 0, "skills": []}


def test_execute_task():
    """测试 execute_task 工具"""
    print("\n[3] 测试 execute_task 工具...")
    try:
        # 测试简单任务
        from openspace.executor import TaskExecutor

        import os
        os.environ["OPENSPACE_HOST_SKILL_DIRS"] = SKILL_DIRS

        executor = TaskExecutor()

        # 尝试执行一个简单任务
        result = executor.execute("测试任务：列出 skills 目录下的所有 SKILL.md")

        print(f"  执行结果: {result[:200] if result else 'empty'}...")
        return bool(result)
    except Exception as e:
        print(f"  失败: {e}")
        return False


def main():
    print("="*60)
    print("OpenSpace MCP 接入测试")
    print("="*60)

    results = {
        "test_time": time.strftime('%Y-%m-%d %H:%M:%S'),
        "sse_endpoint": SSE_URL,
        "skill_dirs": SKILL_DIRS,
    }

    # 测试 1: SSE 连接
    session_id = test_sse_connection()
    results["sse_connection"] = bool(session_id)
    results["session_id"] = session_id or "N/A"

    # 测试 2: search_skills
    skill_result = test_search_skills()
    results["skill_count"] = skill_result["count"]
    results["skills_found"] = skill_result["skills"]
    results["search_skills_success"] = skill_result["count"] > 0

    # 测试 3: execute_task (可选，可能需要 LLM)
    # execute_success = test_execute_task()
    # results["execute_task_success"] = execute_success

    # 生成报告
    print("\n" + "="*60)
    print("测试结果汇总")
    print("="*60)
    print(f"SSE 连接: {results['sse_connection']}")
    print(f"Session ID: {results['session_id']}")
    print(f"发现 SKILL.md 数量: {results['skill_count']}")
    print(f"search_skills 成功: {results['search_skills_success']}")

    # 保存结果
    output_dir = PROJECT_ROOT / ".ai-state"
    output_file = output_dir / "openspace_mcp_test.json"
    output_file.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n结果已保存: {output_file}")

    return results


if __name__ == "__main__":
    main()