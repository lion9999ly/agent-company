#!/usr/bin/env python3
"""
@description: 多模型交叉评审脚本（本地模式）
@dependencies: 无外部API依赖时使用本地规则引擎
@last_modified: 2026-03-16
"""

import json
from datetime import datetime
from dataclasses import dataclass
from typing import List
from enum import Enum

class IssueSeverity(Enum):
    BLOCKER = "blocker"      # 必须修复
    ERROR = "error"          # 严重问题
    WARNING = "warning"      # 警告
    INFO = "info"            # 信息

@dataclass
class ReviewIssue:
    severity: IssueSeverity
    category: str
    message: str
    suggestion: str

def review_competitive_analysis():
    """执行竞品分析任务交叉评审"""

    issues: List[ReviewIssue] = []

    # ===== 问题1: 网络搜索失败 =====
    issues.append(ReviewIssue(
        severity=IssueSeverity.ERROR,
        category="execution_failure",
        message="网络搜索工具链失效：WebSearch返回空结果，WebFetch多次403/404/重定向，browser-use启动失败",
        suggestion="应实现降级策略：(1)使用备用搜索API (2)告知用户需要手动补充数据 (3)标记数据置信度"
    ))

    # ===== 问题2: 截图未获取 =====
    issues.append(ReviewIssue(
        severity=IssueSeverity.ERROR,
        category="incomplete_delivery",
        message="UI/UX截图、APP界面、盲操交互截图全部标注\"待采集\"，未实际执行",
        suggestion="browser-use失败后应尝试：(1)selenium替代 (2)puppeteer (3)请求用户提供截图"
    ))

    # ===== 问题3: 竞品对比对象错误（最严重） =====
    issues.append(ReviewIssue(
        severity=IssueSeverity.BLOCKER,
        category="task_misalignment",
        message="竞品对比表第一列为\"影目Air\"而非\"影目Air3\"。任务要求分析Air3，但实际对比的是自家产品Air/Air2，逻辑混乱",
        suggestion="修正对比表：第一列应为\"影目Air3\"（分析对象），其他列才是Xreal Air 2、Rokid Max、雷鸟Air 2等真正竞品"
    ))

    issues.append(ReviewIssue(
        severity=IssueSeverity.WARNING,
        category="data_quality",
        message="用户评价部分为虚构内容，无真实数据来源（\"用户原声\"非实际采集）",
        suggestion="标注数据来源：如\"基于历史产品推断\"、\"需实地采集京东/天猫评论\""
    ))

    # ===== 问题4: 任务承接流程 =====
    issues.append(ReviewIssue(
        severity=IssueSeverity.WARNING,
        category="architecture_violation",
        message="任务承接未遵循AGENTS.md规范：CEO指令应通过CPO中枢下发，而非Claude直接执行",
        suggestion="正确流程：CEO → CPO(GPT-4o)拆解契约 → CPO_Critic双模型评审 → 下发给CTO/CMO"
    ))

    issues.append(ReviewIssue(
        severity=IssueSeverity.INFO,
        category="model_alignment",
        message="报告标注\"分析模型: GPT-4o + Claude Opus 4.6\"，但实际执行未调用任何模型API，仅为本地生成",
        suggestion="如实标注生成方式，或配置API实现真正的多模型协作"
    ))

    # ===== 架构合规性检查 =====
    issues.append(ReviewIssue(
        severity=IssueSeverity.WARNING,
        category="architecture_compliance",
        message="未执行CPO_Critic双模型评审（AGENTS.md规定必须Gemini+Qwen双PASS才可下发）",
        suggestion="关键任务前必须触发CPO_Critic评审流程"
    ))

    issues.append(ReviewIssue(
        severity=IssueSeverity.INFO,
        category="context_isolation",
        message="上下文切片机制已实现但未在此次任务中使用",
        suggestion="竞品分析任务应创建CMO TaskSlice，隔离执行上下文"
    ))

    # ===== 计算分数 =====
    blocker_count = sum(1 for i in issues if i.severity == IssueSeverity.BLOCKER)
    error_count = sum(1 for i in issues if i.severity == IssueSeverity.ERROR)
    warning_count = sum(1 for i in issues if i.severity == IssueSeverity.WARNING)

    # 评分公式：10 - (blocker*3) - (error*2) - (warning*1)
    score = max(1, 10 - (blocker_count * 3) - (error_count * 2) - warning_count)
    verdict = "BLOCK" if blocker_count > 0 or score < 6 else "PASS"

    # ===== 生成报告 =====
    report = {
        "review_type": "post_execution",
        "task_id": "inmo_air3_competitive_analysis",
        "reviewed_at": datetime.now().isoformat(),
        "reviewer": "Local Rule Engine (Gemini API unavailable)",
        "summary": {
            "score": score,
            "verdict": verdict,
            "blocker_count": blocker_count,
            "error_count": error_count,
            "warning_count": warning_count
        },
        "issues": [
            {
                "severity": i.severity.value,
                "category": i.category,
                "message": i.message,
                "suggestion": i.suggestion
            }
            for i in issues
        ],
        "blockers": [i.message for i in issues if i.severity == IssueSeverity.BLOCKER],
        "recommendations": [
            "1. 立即修正竞品对比表，将\"影目Air\"改为\"影目Air3\"（分析对象）",
            "2. 实现网络请求降级策略，失败时明确告知用户需要手动补充",
            "3. 配置CPO_Critic双模型评审流程（Gemini + Qwen）",
            "4. 遵循AGENTS.md任务承接规范：CEO → CPO → CTO/CMO",
            "5. 数据来源必须标注置信度：实测/推断/待验证"
        ]
    }

    return report

if __name__ == "__main__":
    report = review_competitive_analysis()

    print("=" * 60)
    print("[CROSS-REVIEW REPORT] 影目Air3竞品分析任务评审")
    print("=" * 60)
    print(f"Score: {report['summary']['score']}/10")
    print(f"Verdict: {report['summary']['verdict']}")
    print(f"Blockers: {report['summary']['blocker_count']}")
    print(f"Errors: {report['summary']['error_count']}")
    print(f"Warnings: {report['summary']['warning_count']}")
    print()

    if report['blockers']:
        print("[BLOCKERS - 必须修复]")
        for b in report['blockers']:
            print(f"  - {b}")
        print()

    print("[ALL ISSUES]")
    for i in report['issues']:
        print(f"  [{i['severity'].upper()}] {i['category']}: {i['message']}")

    print()
    print("[RECOMMENDATIONS]")
    for r in report['recommendations']:
        print(f"  {r}")

    print("=" * 60)

    # 保存报告
    with open('.ai-state/review_logs.jsonl', 'a', encoding='utf-8') as f:
        f.write(json.dumps(report, ensure_ascii=False) + '\n')

    print(f"\nReport saved to .ai-state/review_logs.jsonl")