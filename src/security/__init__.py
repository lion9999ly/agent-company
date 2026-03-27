# 🛡️ 安全模块 (Security Module)
"""
安全模块：包含指令歧义防护、KPI陷阱检测等安全组件。

模块结构：
- instruction_guard.py: 指令歧义防护
- kpi_trap_detector.py: KPI陷阱检测
"""

from .instruction_guard import (
    InstructionGuard,
    check_instruction,
    is_instruction_safe,
    AmbiguityLevel,
    AmbiguityPattern,
    InstructionCheckResult
)

from .kpi_trap_detector import (
    KPITrapDetector,
    detect_kpi_trap_in_code,
    detect_kpi_trap_in_contract,
    TrapType,
    TrapSeverity,
    KPITrapPattern,
    TrapDetectionResult
)

__all__ = [
    # Instruction Guard
    "InstructionGuard",
    "check_instruction",
    "is_instruction_safe",
    "AmbiguityLevel",
    "AmbiguityPattern",
    "InstructionCheckResult",
    # KPI Trap Detector
    "KPITrapDetector",
    "detect_kpi_trap_in_code",
    "detect_kpi_trap_in_contract",
    "TrapType",
    "TrapSeverity",
    "KPITrapPattern",
    "TrapDetectionResult"
]