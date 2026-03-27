# 🛡️ 指令歧义防护模块 (Instruction Ambiguity Guard)
"""
核心职责：检测并拦截可能导致安全锁移除的歧义指令。

参考：虎嗅文章《Multi-Agent协作的三大陷阱》
- "越快越好" -> 可能导致跳过安全检查
- "简单处理" -> 可能绕过边界验证
- "看着办" -> 可能引发权限越界

作者：虚拟研发中心安全团队
创建：2026-03-16
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

# === 类型定义 ===

class AmbiguityLevel(Enum):
    """歧义危险等级"""
    SAFE = "safe"                    # 安全
    WARNING = "warning"              # 警告 - 需要澄清
    DANGER = "danger"                # 危险 - 必须拦截
    CRITICAL = "critical"            # 严重 - 触发熔断


@dataclass
class AmbiguityPattern:
    """歧义模式定义"""
    pattern: str                     # 正则匹配模式
    level: AmbiguityLevel            # 危险等级
    reason: str                      # 风险原因
    suggestion: str                  # 改进建议
    category: str                    # 分类标签


@dataclass
class InstructionCheckResult:
    """指令检查结果"""
    is_safe: bool
    level: AmbiguityLevel
    detected_patterns: list[AmbiguityPattern] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)


# === 歧义模式库 ===

AMBIGUITY_PATTERNS: list[AmbiguityPattern] = [
    # === 时间压力类 ===
    AmbiguityPattern(
        pattern=r"越快越好|尽快|马上|立刻|急|抓紧",
        level=AmbiguityLevel.WARNING,
        reason="时间压力可能导致跳过安全检查",
        suggestion="请明确具体截止时间，并确认安全检查不可跳过",
        category="time_pressure"
    ),
    AmbiguityPattern(
        pattern=r"先.*再说|先跑起来|先上线",
        level=AmbiguityLevel.DANGER,
        reason="暗示可以跳过验证环节",
        suggestion="请明确哪些步骤不可跳过，如：'先开发但必须通过评审后上线'",
        category="skip_process"
    ),

    # === 简化处理类 ===
    AmbiguityPattern(
        pattern=r"简单.*处理|随便.*写|应付一下|凑合",
        level=AmbiguityLevel.WARNING,
        reason="简化处理可能绕过质量边界",
        suggestion="请明确最低质量要求，如：'简化但必须包含XX边界检查'",
        category="quality_skip"
    ),
    AmbiguityPattern(
        pattern=r"不需要.*检查|跳过.*验证|忽略.*警告",
        level=AmbiguityLevel.DANGER,
        reason="明确要求绕过安全机制",
        suggestion="请说明为何可以跳过，并提供替代安全措施",
        category="security_bypass"
    ),

    # === 权限模糊类 ===
    AmbiguityPattern(
        pattern=r"看着办|你自己决定|你看着处理",
        level=AmbiguityLevel.WARNING,
        reason="决策权限模糊可能导致越界",
        suggestion="请明确决策边界，如：'在X范围内可自行决定，超出需确认'",
        category="authority_unclear"
    ),
    AmbiguityPattern(
        pattern=r"都行|随便|你定",
        level=AmbiguityLevel.WARNING,
        reason="完全放权可能导致不可控行为",
        suggestion="请至少指定一个硬性约束条件",
        category="no_constraint"
    ),

    # === 目标模糊类 ===
    AmbiguityPattern(
        pattern=r"差不多就行|大概|可能|好像|应该",
        level=AmbiguityLevel.WARNING,
        reason="模糊目标导致结果不可衡量",
        suggestion="请量化目标，如：'覆盖率>90%'而非'差不多'",
        category="vague_target"
    ),

    # === 危险组合类 ===
    AmbiguityPattern(
        pattern=r"越快越好.*简单|尽快.*跳过|着急.*随便",
        level=AmbiguityLevel.CRITICAL,
        reason="时间压力+简化处理的危险组合",
        suggestion="请拆分指令，分别明确时间要求和质量底线",
        category="dangerous_combo"
    ),
]


# === 核心检查器 ===

class InstructionGuard:
    """指令歧义防护器"""

    def __init__(self, custom_patterns: Optional[list[AmbiguityPattern]] = None):
        self.patterns = AMBIGUITY_PATTERNS.copy()
        if custom_patterns:
            self.patterns.extend(custom_patterns)

    def check(self, instruction: str) -> InstructionCheckResult:
        """
        检查指令是否存在歧义风险

        Args:
            instruction: 待检查的指令文本

        Returns:
            InstructionCheckResult: 检查结果
        """
        detected: list[AmbiguityPattern] = []
        warnings: list[str] = []
        suggestions: list[str] = []

        for pattern_def in self.patterns:
            if re.search(pattern_def.pattern, instruction):
                detected.append(pattern_def)
                warnings.append(f"[{pattern_def.category}] {pattern_def.reason}")
                suggestions.append(pattern_def.suggestion)

        # 确定最高危险等级
        if not detected:
            return InstructionCheckResult(
                is_safe=True,
                level=AmbiguityLevel.SAFE
            )

        max_level = max(detected, key=lambda p: list(AmbiguityLevel).index(p.level)).level

        return InstructionCheckResult(
            is_safe=max_level in (AmbiguityLevel.SAFE, AmbiguityLevel.WARNING),
            level=max_level,
            detected_patterns=detected,
            warnings=warnings,
            suggestions=suggestions
        )

    def format_report(self, result: InstructionCheckResult, instruction: str) -> str:
        """格式化检查报告"""
        if result.is_safe and result.level == AmbiguityLevel.SAFE:
            return "[PASS] 指令无歧义风险"

        level_emoji = {
            AmbiguityLevel.WARNING: "⚠️",
            AmbiguityLevel.DANGER: "🚨",
            AmbiguityLevel.CRITICAL: "💀"
        }

        report_lines = [
            f"{level_emoji.get(result.level, '❓')} [{result.level.value.upper()}] 指令歧义检测",
            f"原指令: {instruction}",
            "",
            "检测到的问题:"
        ]

        for pattern in result.detected_patterns:
            report_lines.append(f"  - [{pattern.category}] 匹配: {pattern.pattern}")
            report_lines.append(f"    风险: {pattern.reason}")
            report_lines.append(f"    建议: {pattern.suggestion}")

        return "\n".join(report_lines)


# === 便捷函数 ===

def check_instruction(instruction: str) -> InstructionCheckResult:
    """便捷函数：检查指令"""
    guard = InstructionGuard()
    return guard.check(instruction)


def is_instruction_safe(instruction: str) -> bool:
    """便捷函数：判断指令是否安全"""
    result = check_instruction(instruction)
    return result.is_safe


# === 测试入口 ===

if __name__ == "__main__":
    test_cases = [
        "请尽快完成这个功能的开发",
        "越快越好，简单处理就行",
        "先上线再说，安全检查可以跳过",
        "请在周五前完成蓝牙模块的开发，必须通过Critic评审",
        "你自己看着办",
    ]

    guard = InstructionGuard()
    print("=" * 60)
    print("指令歧义防护测试")
    print("=" * 60)

    for case in test_cases:
        result = guard.check(case)
        print(guard.format_report(result, case))
        print("-" * 40)