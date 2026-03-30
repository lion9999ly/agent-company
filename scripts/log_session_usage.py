"""
@description: 会话用量记录工具 - 记录Claude Code会话的token使用情况
@dependencies: token_usage_tracker
@last_modified: 2026-03-17

使用方法:
    python scripts/log_session_usage.py --model glm-4 --prompt 1000 --completion 500 --task "代码开发"
"""

import argparse
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.token_usage_tracker import get_tracker


def log_session_usage(model: str, prompt_tokens: int, completion_tokens: int,
                      task: str = "claude_code_session", notes: str = ""):
    """
    记录会话用量

    Args:
        model: 模型名称 (如 glm-4, glm-4-flash)
        prompt_tokens: 输入token数
        completion_tokens: 输出token数
        task: 任务描述
        notes: 备注
    """
    tracker = get_tracker()

    # 根据模型推断provider
    provider_map = {
        "glm": "zhipu",
        "gemini": "google",
        "gpt": "azure_openai",
        "qwen": "alibaba",
        "deepseek": "deepseek"
    }

    provider = "unknown"
    for prefix, prov in provider_map.items():
        if model.lower().startswith(prefix):
            provider = prov
            break

    # 记录
    record = tracker.record(
        model=model,
        provider=provider,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        task_type=task,
        success=True
    )

    print(f"[已记录] {model}")
    print(f"  输入: {prompt_tokens} tokens")
    print(f"  输出: {completion_tokens} tokens")
    print(f"  总计: {record.total_tokens} tokens")
    print(f"  估算成本: ${record.cost_estimate:.4f}")

    if notes:
        print(f"  备注: {notes}")

    # 显示今日统计
    stats = tracker.get_today_stats()
    print(f"\n[今日累计]")
    print(f"  调用: {stats['total_calls']} 次")
    print(f"  Token: {stats['total_tokens']:,}")
    print(f"  成本: ${stats['total_cost']:.4f}")


def show_stats(days: int = 7):
    """显示统计报告"""
    tracker = get_tracker()

    print(f"\n{'=' * 60}")
    print(f"[用量统计] 最近 {days} 天")
    print('=' * 60)

    stats = tracker.get_stats(days)

    print(f"\n总体统计:")
    print(f"  总调用: {stats['total_calls']} 次")
    print(f"  总Token: {stats['total_tokens']:,}")
    print(f"  估算成本: ${stats['total_cost']:.4f}")

    print(f"\n模型使用排名:")
    for m in tracker.get_model_ranking(days):
        print(f"  {m['model']}: {m['calls']} 次, {m['tokens']:,} tokens, ${m['cost']:.4f}")

    print(f"\n提供商使用排名:")
    for p in tracker.get_provider_ranking(days):
        print(f"  {p['provider']}: {p['calls']} 次, {p['tokens']:,} tokens, ${p['cost']:.4f}")


def interactive_mode():
    """交互式记录模式"""
    print("=" * 60)
    print("[会话用量记录工具]")
    print("=" * 60)
    print("\n提示: 从 Claude Code 界面查看本次会话的 token 使用量")
    print("通常显示在响应末尾，如 'Tokens: 1234 input, 567 output'")
    print()

    while True:
        print("-" * 40)
        model = input("模型名称 (如 glm-4, 留空结束): ").strip()
        if not model:
            break

        try:
            prompt_tokens = int(input("输入 token 数: ").strip())
            completion_tokens = int(input("输出 token 数: ").strip())
        except ValueError:
            print("请输入有效的数字")
            continue

        task = input("任务描述 (可选): ").strip() or "claude_code_session"
        notes = input("备注 (可选): ").strip()

        log_session_usage(model, prompt_tokens, completion_tokens, task, notes)

        more = input("\n继续记录? (y/n): ").strip().lower()
        if more != 'y':
            break

    show_stats(7)


if __name__ == "__main__":
    # 设置控制台编码
    if sys.platform == 'win32':
        sys.stdout.reconfigure(encoding='utf-8')

    parser = argparse.ArgumentParser(description="会话用量记录工具")
    parser.add_argument("--model", "-m", help="模型名称")
    parser.add_argument("--prompt", "-p", type=int, help="输入token数")
    parser.add_argument("--completion", "-c", type=int, help="输出token数")
    parser.add_argument("--task", "-t", default="claude_code_session", help="任务描述")
    parser.add_argument("--notes", "-n", default="", help="备注")
    parser.add_argument("--stats", "-s", type=int, help="显示最近N天统计")
    parser.add_argument("--interactive", "-i", action="store_true", help="交互模式")

    args = parser.parse_args()

    if args.interactive:
        interactive_mode()
    elif args.stats:
        show_stats(args.stats)
    elif args.model and args.prompt is not None and args.completion is not None:
        log_session_usage(args.model, args.prompt, args.completion, args.task, args.notes)
    else:
        # 默认显示统计
        show_stats(7)
        print("\n使用方法:")
        print("  交互模式: python scripts/log_session_usage.py -i")
        print("  快速记录: python scripts/log_session_usage.py -m glm-4 -p 1000 -c 500")
        print("  查看统计: python scripts/log_session_usage.py -s 7")