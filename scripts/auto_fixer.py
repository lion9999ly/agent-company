"""自动修复引擎 — 测试失败时自动分析+修复+验证
@description: 使用 Claude CLI (Max 订阅) 分析错误并自动修复
@dependencies: test_suite, claude_cli_helper
@last_modified: 2026-04-05
"""
import subprocess, json, time, re
from pathlib import Path
from scripts.claude_cli_helper import call_claude_cli, is_claude_cli_available

PROJECT_ROOT = Path(__file__).parent.parent
FIX_LOG_PATH = PROJECT_ROOT / ".ai-state" / "auto_fix_log.jsonl"
BUG_REPORT_PATH = PROJECT_ROOT / ".ai-state" / "bug_report.md"


def auto_fix_failures(failed_items: list, max_rounds: int = 3) -> dict:
    """对失败的测试项自动修复

    流程:
    1. 把失败项的 error + traceback 交给 CC (Claude CLI) 分析
    2. CC 生成修复代码
    3. 重新跑测试
    4. 最多 3 轮
    5. 修不好的写入 bug_report.md

    Args:
        failed_items: 失败的测试项列表
        max_rounds: 最大修复轮数

    Returns:
        修复结果
    """
    fixed = []
    unfixed = []

    for item in failed_items:
        success = False
        item_name = item.get("name", "unknown")

        for round_num in range(1, max_rounds + 1):
            print(f"\n  [AutoFix] 修复 {item_name} (第 {round_num}/{max_rounds} 轮)")

            # 用 CC (Claude CLI) 分析并修复 - 使用 Max 订阅
            fix_prompt = (
                f"测试 '{item_name}' 失败了。\n\n"
                f"错误: {item.get('error', 'unknown')}\n"
                f"Traceback: {item.get('traceback', 'N/A')}\n"
                f"描述: {item.get('description', '')}\n\n"
                f"请分析原因并给出修复方案。如果需要修改代码，输出完整的文件路径和修改内容。\n"
                f"格式:\nFILE: path/to/file.py\nOLD:\n```\n旧代码\n```\nNEW:\n```\n新代码\n```"
            )

            # 追加格式要求
            fix_prompt += (
                "\n\n必须用以下格式输出修复（严格遵守）:\n"
                "FILE: scripts/example.py\n"
                "OLD:\n```python\n原始代码\n```\n"
                "NEW:\n```python\n新代码\n```\n\n"
                "如果问题不在代码（如 API 不可用、配置问题），说明原因即可，不需要给代码修复。"
            )

            if is_claude_cli_available():
                fix_suggestion = call_claude_cli(fix_prompt, timeout=120, cwd=str(PROJECT_ROOT))
            else:
                print(f"  [AutoFix] CC CLI 不可用，回退到 model_gateway")
                fix_suggestion = _fix_via_model_gateway(item)

            if not fix_suggestion:
                continue

            # 解析修复建议并应用
            applied = _apply_fix(fix_suggestion)
            if not applied:
                print(f"  [AutoFix] 无法解析修复建议")
                continue

            # 重新跑这一项测试
            from scripts.test_suite import run_all_tests
            retest = run_all_tests()
            still_failing = [f for f in retest["summary"]["failed_items"] if f["name"] == item_name]

            if not still_failing:
                print(f"  [AutoFix] ✅ {item_name} 修复成功")
                fixed.append({"item": item_name, "rounds": round_num, "fix": fix_suggestion[:200]})
                success = True

                # commit 修复
                subprocess.run(["git", "add", "-A"], cwd=str(PROJECT_ROOT))
                subprocess.run(
                    ["git", "commit", "-m", f"fix(auto): {item_name} — auto-fixed by self-healing system"],
                    cwd=str(PROJECT_ROOT)
                )
                subprocess.run(["git", "push", "origin", "main"], cwd=str(PROJECT_ROOT))
                break
            else:
                print(f"  [AutoFix] 第 {round_num} 轮修复未生效，继续")

        if not success:
            unfixed.append(item)

    # 写入修复日志
    log_entry = {
        "timestamp": time.strftime('%Y-%m-%d %H:%M'),
        "fixed": [f["item"] for f in fixed],
        "unfixed": [u["name"] for u in unfixed],
    }
    FIX_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(FIX_LOG_PATH, 'a', encoding='utf-8') as f:
        f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

    # 修不好的写入 bug_report
    if unfixed:
        _write_bug_report(unfixed)

    return {"fixed": fixed, "unfixed": unfixed}


def _fix_via_model_gateway(item: dict) -> str:
    """CC 不可用时，用 model_gateway 调用 gpt-5.4 分析"""
    try:
        from scripts.litellm_gateway import get_model_gateway
        gw = get_model_gateway()
        result = gw.call("gpt_5_4",
            f"测试失败: {item.get('error', '')}\nTraceback: {item.get('traceback', '')}\n"
            f"分析原因并给出修复代码。",
            "你是 Python 调试专家。", "bug_fix")
        return result.get("response", "") if result.get("success") else ""
    except Exception:
        return ""


def _apply_fix(fix_suggestion: str) -> bool:
    """解析 CC 的修复建议并应用到文件"""
    # 解析 FILE: / OLD: / NEW: 格式
    file_match = re.search(r'FILE:\s*(.+)', fix_suggestion)
    old_match = re.search(r'OLD:\s*```\w*\n?(.*?)```', fix_suggestion, re.DOTALL)
    new_match = re.search(r'NEW:\s*```\w*\n?(.*?)```', fix_suggestion, re.DOTALL)

    if not all([file_match, old_match, new_match]):
        # 尝试其他格式：直接在代码块中
        file_match = re.search(r'修改[文件]?[:\s]*(.+\.py)', fix_suggestion)
        code_blocks = re.findall(r'```(?:python)?\s*([\s\S]*?)```', fix_suggestion)
        if file_match and code_blocks:
            # 尝试用第一个代码块作为新代码
            file_path = _resolve_file_path(file_match.group(1).strip())
            if file_path.exists():
                new_code = code_blocks[0].strip()
                file_path.write_text(new_code, encoding='utf-8')
                print(f"  [AutoFix] 已修改: {file_path}")
                return True

        # CLI fallback 解析
        try:
            extract_result = call_claude_cli(
                f"从以下修复建议中提取代码修改。输出严格 JSON（不要 markdown）:"
                f'{{"file": "路径", "old_code": "原始代码", "new_code": "新代码"}}'
                f"如果不包含代码修改，输出: {{\"no_fix\": true}}\n\n{fix_suggestion[:2000]}",
                timeout=30
            )
            if extract_result:
                parsed = json.loads(extract_result.strip().replace('```json','').replace('```',''))
                if not parsed.get("no_fix"):
                    return _do_replace(parsed["file"], parsed.get("old_code", ""), parsed["new_code"])
        except Exception as e:
            print(f"  [AutoFix] CLI fallback 也失败: {e}")

        return False

    return _do_replace(file_match.group(1).strip(), old_match.group(1).strip(), new_match.group(1).strip())


def _resolve_file_path(file_path_str: str) -> Path:
    """解析文件路径，支持模糊匹配"""
    file_path = PROJECT_ROOT / file_path_str
    if file_path.exists():
        return file_path

    # 尝试加前缀
    for prefix in ["scripts/", "src/", "scripts/feishu_handlers/", "src/utils/", "src/config/"]:
        candidate = PROJECT_ROOT / prefix / file_path_str.split("/")[-1]
        if candidate.exists():
            return candidate

    return file_path


def _do_replace(file_path_str: str, old_code: str, new_code: str) -> bool:
    """执行代码替换"""
    file_path = _resolve_file_path(file_path_str)

    if not file_path.exists():
        print(f"  [AutoFix] 文件不存在: {file_path}")
        return False

    content = file_path.read_text(encoding='utf-8')

    if old_code and old_code in content:
        content = content.replace(old_code, new_code, 1)
        file_path.write_text(content, encoding='utf-8')
        print(f"  [AutoFix] 已修改: {file_path}")
        return True
    elif not old_code:
        # 没有旧代码，直接覆盖
        file_path.write_text(new_code, encoding='utf-8')
        print(f"  [AutoFix] 已创建/覆盖: {file_path}")
        return True
    else:
        print(f"  [AutoFix] 未找到旧代码片段")
        return False


def _write_bug_report(unfixed: list):
    """写入无法自动修复的 bug 报告"""
    lines = [f"# Bug 报告 — {time.strftime('%Y-%m-%d %H:%M')}\n"]
    lines.append(f"以下 {len(unfixed)} 个问题无法自动修复，需要人工介入：\n")
    for item in unfixed:
        lines.append(f"## ❌ {item.get('name', 'unknown')}")
        lines.append(f"- 错误: {item.get('error', 'unknown')}")
        lines.append(f"- 描述: {item.get('description', '')}")
        if item.get('traceback'):
            lines.append(f"- Traceback:\n```\n{item['traceback'][-300:]}\n```")
        lines.append("")

    BUG_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    BUG_REPORT_PATH.write_text("\n".join(lines), encoding='utf-8')

    # 自动 git push bug report
    subprocess.run(["git", "add", str(BUG_REPORT_PATH)], cwd=str(PROJECT_ROOT))
    subprocess.run(["git", "commit", "-m", "auto: bug report — issues that need human attention"],
                   cwd=str(PROJECT_ROOT))
    subprocess.run(["git", "push", "origin", "main"], cwd=str(PROJECT_ROOT))


if __name__ == "__main__":
    print("自动修复引擎已就绪")