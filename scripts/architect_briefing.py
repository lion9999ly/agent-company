"""架构师简报 — 供 Claude 快速了解系统状态
@description: 自动生成系统状态简报，供架构师快速了解关键信息
@dependencies: knowledge_base, claude_thinking_layer
@last_modified: 2026-04-05
"""
import json
import time
import subprocess
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent
BRIEFING_PATH = PROJECT_ROOT / ".ai-state" / "architect_briefing.md"


def generate_briefing() -> str:
    """生成架构师简报"""
    sections = []
    sections.append(f"# 架构师简报\n生成时间: {time.strftime('%Y-%m-%d %H:%M')}")

    # 1. 上次简报以来的变更
    sections.append(_section_recent_changes())

    # 2. 未决决策状态
    sections.append(_section_pending_decisions())

    # 3. 思考层待回答问题
    sections.append(_section_pending_thinking())

    # 4. 深度学习最近发现摘要
    sections.append(_section_recent_findings())

    # 5. 系统健康
    sections.append(_section_system_health())

    # 6. 需要架构师关注的事项
    sections.append(_section_attention_needed())

    briefing = "\n\n".join([s for s in sections if s])
    BRIEFING_PATH.parent.mkdir(parents=True, exist_ok=True)
    BRIEFING_PATH.write_text(briefing, encoding='utf-8')
    print(f"[Briefing] 已生成: {BRIEFING_PATH}")
    return briefing


def _section_recent_changes() -> str:
    """最近的 git 变更"""
    try:
        r = subprocess.run(
            "git log --oneline -20",
            shell=True, capture_output=True, text=True,
            cwd=str(PROJECT_ROOT)
        )
        if r.returncode == 0:
            return f"## 最近变更\n```\n{r.stdout.strip()}\n```"
    except:
        pass
    return ""


def _section_pending_decisions() -> str:
    """决策树中的未决项"""
    # 从 product_anchor.md 提取未决决策
    anchor_path = PROJECT_ROOT / ".ai-state" / "product_anchor.md"
    if anchor_path.exists():
        content = anchor_path.read_text(encoding='utf-8')
        if "## 未决决策" in content:
            section = content.split("## 未决决策")[1].split("##")[0]
            decisions = [line.strip("- ").strip() for line in section.split("\n") if line.strip().startswith("-")]
            if decisions:
                lines = ["## 未决决策"]
                for d in decisions:
                    lines.append(f"- ⏳ {d}")
                return "\n".join(lines)
    return "## 未决决策\n暂无记录"


def _section_pending_thinking() -> str:
    """思考层待回答的问题"""
    thinking_dir = PROJECT_ROOT / ".ai-state" / "thinking_requests"
    if not thinking_dir.exists():
        return "## 思考层\n无待回答问题"

    pending = []
    for f in thinking_dir.glob("think_*.json"):
        try:
            data = json.loads(f.read_text(encoding='utf-8'))
            if data.get("status") == "pending":
                urgency = data.get("urgency", "normal")
                icon = {"critical": "🔴", "normal": "🟡", "low": "🟢"}.get(urgency, "🟡")
                question = data.get("question", "")[:80]
                created = data.get("created_at", "")
                pending.append(f"- {icon} {question} ({created})")
        except:
            pass

    if not pending:
        return "## 思考层\n✅ 无待回答问题"
    return "## 思考层待回答\n" + "\n".join(pending)


def _section_recent_findings() -> str:
    """最近深度学习的关键发现"""
    # 从最近的报告中提取
    reports_dir = PROJECT_ROOT / ".ai-state" / "reports"
    if not reports_dir.exists():
        return "## 最近发现\n无"

    findings = []
    try:
        # 获取最近修改的报告
        reports = sorted(reports_dir.glob("*.md"), key=lambda x: x.stat().st_mtime, reverse=True)[:5]
        for report in reports:
            content = report.read_text(encoding='utf-8')[:500]
            findings.append(f"- [{report.name[:30]}] {content[:100]}...")
    except:
        pass

    if not findings:
        return "## 最近发现\n无"
    return "## 最近研究发现\n" + "\n".join(findings)


def _section_system_health() -> str:
    """系统健康状态"""
    lines = []

    # 测试结果
    test_path = PROJECT_ROOT / ".ai-state" / "integration_test_log.jsonl"
    if test_path.exists():
        try:
            lines_data = test_path.read_text(encoding='utf-8').strip().split('\n')
            total = len(lines_data)
            passed = sum(1 for l in lines_data if '"passed": true' in l)
            lines.append(f"- 集成测试: {passed}/{total} 通过")
        except:
            pass

    # KB 统计
    try:
        from src.tools.knowledge_base import get_knowledge_stats
        stats = get_knowledge_stats()
        total = sum(stats.values())
        lines.append(f"- 知识库: {total} 条")
    except:
        pass

    # 模型状态
    try:
        from scripts.litellm_gateway import get_model_gateway
        gw = get_model_gateway()
        enabled = sum(1 for m in gw.models.values() if m.enabled)
        lines.append(f"- 可用模型: {enabled} 个")
    except:
        pass

    if not lines:
        return "## 系统健康\n状态未知"
    return "## 系统健康\n" + "\n".join(lines)


def _section_attention_needed() -> str:
    """需要架构师关注的事项"""
    alerts = []

    # 检查思考层积压
    thinking_dir = PROJECT_ROOT / ".ai-state" / "thinking_requests"
    if thinking_dir.exists():
        try:
            pending_count = sum(
                1 for f in thinking_dir.glob("think_*.json")
                if json.loads(f.read_text(encoding='utf-8')).get("status") == "pending"
            )
            if pending_count > 3:
                alerts.append(f"🔴 思考层积压: {pending_count} 个问题待回答")
            elif pending_count > 0:
                alerts.append(f"🟡 思考层: {pending_count} 个问题待回答")
        except:
            pass

    # 检查 bug report
    bug_path = PROJECT_ROOT / ".ai-state" / "bug_report.md"
    if bug_path.exists():
        content = bug_path.read_text(encoding='utf-8')
        if "❌" in content:
            alerts.append("🟡 有未修复的问题")

    # 检查自动修复失败
    fix_log = PROJECT_ROOT / ".ai-state" / "auto_fix_log.jsonl"
    if fix_log.exists():
        try:
            lines = fix_log.read_text(encoding='utf-8').strip().split('\n')
            if lines:
                last = json.loads(lines[-1])
                if last.get("unfixed"):
                    alerts.append(f"🟡 自动修复未完成: {len(last['unfixed'])} 项")
        except:
            pass

    if not alerts:
        return "## 需要关注\n✅ 无需架构师介入"
    return "## ⚠️ 需要架构师关注\n" + "\n".join(alerts)


def should_alert_architect(send_reply=None, reply_target=None) -> bool:
    """判断是否需要通知架构师介入

    触发条件：
    1. 思考层积压 > 3
    2. 有 critical 级别未决问题
    3. 连续失败
    """
    briefing = generate_briefing()

    attention_section = _section_attention_needed()
    if "🔴" in attention_section:
        if send_reply and reply_target:
            send_reply(reply_target,
                f"⚠️ 建议找架构师对齐\n\n"
                f"请将以下 URL 发给 Claude:\n"
                f"https://raw.githubusercontent.com/lion9999ly/agent-company/main/.ai-state/architect_briefing.md")
        return True
    return False


def push_briefing_to_feishu(send_reply, reply_target):
    """推送简报到飞书"""
    briefing = generate_briefing()
    if briefing:
        # 截取前 2000 字
        send_reply(reply_target, briefing[:2000])
        return True
    return False


if __name__ == "__main__":
    briefing = generate_briefing()
    print(briefing)