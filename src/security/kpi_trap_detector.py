# 🎯 KPI陷阱检测模块 (KPI Trap Detector)
"""
@description: 检测Agent为达成KPI而走捷径的行为模式，防止"表面达标"而非"实质达标"
@dependencies: re, dataclasses, enum, typing
@last_modified: 2026-03-18

核心职责：检测Agent为达成KPI而走捷径的行为模式。

参考：虎嗅文章《Multi-Agent协作的三大陷阱》
KPI陷阱：Agent可能选择"表面达标"而非"实质达标"
- 测试覆盖率90% -> 但只测简单路径
- 响应时间<100ms -> 但跳过异常处理
- 功能完成率100% -> 但忽略边界场景

作者：虚拟研发中心安全团队
创建：2026-03-16
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

# === 类型定义 ===

class TrapType(Enum):
    """KPI陷阱类型"""
    SHALLOW_COVERAGE = "shallow_coverage"      # 浅层覆盖
    FAST_PATH_ONLY = "fast_path_only"          # 只走快速路径
    METRIC_GAMING = "metric_gaming"            # 指标游戏
    BOUNDARY_SKIP = "boundary_skip"            # 边界跳过
    ERROR_SUPPRESSION = "error_suppression"    # 错误压制
    PLACEHOLDER_CODE = "placeholder_code"      # 占位代码


class TrapSeverity(Enum):
    """陷阱严重程度"""
    LOW = "low"           # 需要关注
    MEDIUM = "medium"     # 需要整改
    HIGH = "high"         # 需要打回
    CRITICAL = "critical" # 需要熔断


@dataclass
class KPITrapPattern:
    """KPI陷阱模式"""
    trap_type: TrapType
    severity: TrapSeverity
    indicator: str                   # 指标特征
    description: str                 # 行为描述
    detection_hints: list[str]       # 检测线索
    countermeasure: str              # 对策建议


@dataclass
class TrapDetectionResult:
    """陷阱检测结果"""
    has_trap: bool
    trap_type: Optional[TrapType] = None
    severity: TrapSeverity = TrapSeverity.LOW
    evidence: list[str] = field(default_factory=list)
    countermeasures: list[str] = field(default_factory=list)


# === KPI陷阱库 ===

KPI_TRAPS: list[KPITrapPattern] = [
    # === 浅层覆盖陷阱 ===
    KPITrapPattern(
        trap_type=TrapType.SHALLOW_COVERAGE,
        severity=TrapSeverity.MEDIUM,
        indicator="测试覆盖率>90%",
        description="只测试简单路径，忽略边界和异常",
        detection_hints=[
            "测试用例全部是正向流程",
            "没有异常分支测试",
            "边界值测试缺失",
            "mock了所有复杂依赖"
        ],
        countermeasure="要求同时提交：覆盖率报告 + 边界测试清单 + 异常场景列表"
    ),

    # === 快速路径陷阱 ===
    KPITrapPattern(
        trap_type=TrapType.FAST_PATH_ONLY,
        severity=TrapSeverity.HIGH,
        indicator="响应时间<100ms",
        description="只优化快速路径，忽略慢速路径",
        detection_hints=[
            "缓存了关键数据但无过期策略",
            "跳过了复杂校验逻辑",
            "硬编码了返回结果",
            "异常路径直接返回默认值"
        ],
        countermeasure="要求同时提交：性能报告 + 异常路径测试 + 缓存策略说明"
    ),

    # === 指标游戏陷阱 ===
    KPITrapPattern(
        trap_type=TrapType.METRIC_GAMING,
        severity=TrapSeverity.HIGH,
        indicator="功能完成率100%",
        description="技术性完成，实质功能缺失",
        detection_hints=[
            "功能存在但不可用",
            "返回假数据",
            "注释掉了复杂逻辑",
            "TODO标记超过5个"
        ],
        countermeasure="要求Demo演示 + 端到端测试 + 用户场景验证"
    ),

    # === 边界跳过陷阱 ===
    KPITrapPattern(
        trap_type=TrapType.BOUNDARY_SKIP,
        severity=TrapSeverity.HIGH,
        indicator="开发按时完成",
        description="跳过边界场景处理",
        detection_hints=[
            "没有空值检查",
            "没有超限处理",
            "没有并发保护",
            "错误处理只有pass"
        ],
        countermeasure="要求边界测试清单 + 压力测试报告 + 并发测试"
    ),

    # === 错误压制陷阱 ===
    KPITrapPattern(
        trap_type=TrapType.ERROR_SUPPRESSION,
        severity=TrapSeverity.CRITICAL,
        indicator="无报错",
        description="压制错误而非解决问题",
        detection_hints=[
            "大量try-except pass",
            "日志级别被提高",
            "错误被静默处理",
            "断言被禁用"
        ],
        countermeasure="代码审查禁用空except + 错误日志审计"
    ),

    # === 占位代码陷阱 ===
    KPITrapPattern(
        trap_type=TrapType.PLACEHOLDER_CODE,
        severity=TrapSeverity.MEDIUM,
        indicator="代码已提交",
        description="提交占位代码凑数",
        detection_hints=[
            "# TODO: implement",
            "# FIXME: this is a hack",
            "pass  # placeholder",
            "return None  # temporary"
        ],
        countermeasure="Hook拦截占位关键词 + 要求完成度自评"
    ),
]


# === 核心检测器 ===

class KPITrapDetector:
    """KPI陷阱检测器"""

    def __init__(self):
        self.traps = KPI_TRAPS
        self.detection_patterns = self._build_detection_patterns()

    def _build_detection_patterns(self) -> dict[TrapType, list[re.Pattern]]:
        """构建检测正则"""
        patterns = {}
        for trap in self.traps:
            trap_patterns = []
            for hint in trap.detection_hints:
                # 将提示转换为正则
                escaped = re.escape(hint)
                trap_patterns.append(re.compile(escaped, re.IGNORECASE))
            patterns[trap.trap_type] = trap_patterns
        return patterns

    def detect_in_code(self, code: str) -> TrapDetectionResult:
        """
        检测代码中的KPI陷阱

        Args:
            code: 待检测的代码文本

        Returns:
            TrapDetectionResult: 检测结果
        """
        evidence = []
        detected_types = []
        countermeasures = []

        for trap in self.traps:
            for hint in trap.detection_hints:
                if hint.lower() in code.lower():
                    evidence.append(f"[{trap.trap_type.value}] 发现: {hint}")
                    detected_types.append(trap.trap_type)
                    countermeasures.append(trap.countermeasure)
                    break  # 每种陷阱只记录一次

        if not evidence:
            return TrapDetectionResult(has_trap=False)

        # 确定最高严重程度
        severity = TrapSeverity.LOW
        for trap in self.traps:
            if trap.trap_type in detected_types:
                if list(TrapSeverity).index(trap.severity) > list(TrapSeverity).index(severity):
                    severity = trap.severity

        return TrapDetectionResult(
            has_trap=True,
            trap_type=detected_types[0] if len(detected_types) == 1 else None,
            severity=severity,
            evidence=evidence,
            countermeasures=list(set(countermeasures))
        )

    def detect_in_contract(self, contract: dict) -> TrapDetectionResult:
        """
        检测任务契约中的KPI陷阱风险

        Args:
            contract: 任务契约字典

        Returns:
            TrapDetectionResult: 检测结果
        """
        evidence = []
        countermeasures = []

        # 检查KPI定义是否过于简单
        if "metrics" in contract:
            metrics = contract["metrics"]
            for metric in metrics:
                metric_str = str(metric).lower()

                # 检测单一指标风险
                if any(kw in metric_str for kw in ["覆盖率", "完成率", "响应时间"]):
                    if "边界" not in metric_str and "异常" not in metric_str:
                        evidence.append(f"[metric_gaming] 单一指标可能诱导捷径: {metric}")
                        countermeasures.append("建议添加边界检查指标")

        if not evidence:
            return TrapDetectionResult(has_trap=False)

        return TrapDetectionResult(
            has_trap=True,
            trap_type=TrapType.METRIC_GAMING,
            severity=TrapSeverity.MEDIUM,
            evidence=evidence,
            countermeasures=countermeasures
        )

    def format_report(self, result: TrapDetectionResult) -> str:
        """格式化检测报告"""
        if not result.has_trap:
            return "[PASS] 未检测到KPI陷阱"

        severity_emoji = {
            TrapSeverity.LOW: "💡",
            TrapSeverity.MEDIUM: "⚠️",
            TrapSeverity.HIGH: "🚨",
            TrapSeverity.CRITICAL: "💀"
        }

        lines = [
            f"{severity_emoji.get(result.severity, '❓')} [{result.severity.value.upper()}] KPI陷阱检测",
            "",
            "检测到的陷阱证据:"
        ]

        for e in result.evidence:
            lines.append(f"  - {e}")

        lines.append("")
        lines.append("建议对策:")
        for c in result.countermeasures:
            lines.append(f"  → {c}")

        return "\n".join(lines)


# === 便捷函数 ===

def detect_kpi_trap_in_code(code: str) -> TrapDetectionResult:
    """便捷函数：检测代码中的KPI陷阱"""
    detector = KPITrapDetector()
    return detector.detect_in_code(code)


def detect_kpi_trap_in_contract(contract: dict) -> TrapDetectionResult:
    """便捷函数：检测契约中的KPI陷阱风险"""
    detector = KPITrapDetector()
    return detector.detect_in_contract(contract)


# === 测试入口 ===

if __name__ == "__main__":
    test_code_samples = [
        """
        def process_data(data):
            # 快速路径优化
            if data is None:
                return None  # temporary
            try:
                result = data.value
            except:
                pass
            return result
        """,
        """
        def calculate_score(test_results):
            # 测试覆盖率已达90%
            # TODO: add boundary tests
            coverage = len(test_results) / 100
            return coverage * 100
        """,
        """
        def handle_request(request):
            # FIXME: this is a hack
            return {"status": "ok"}  # mock response
        """
    ]

    detector = KPITrapDetector()
    print("=" * 60)
    print("KPI陷阱检测测试")
    print("=" * 60)

    for i, code in enumerate(test_code_samples, 1):
        print(f"\n样本 {i}:")
        print("-" * 40)
        result = detector.detect_in_code(code)
        print(detector.format_report(result))