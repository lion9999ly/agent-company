# 📋 行为边界审计日志模块 (Behavior Boundary Logger)
"""
@description: 记录和审计Agent行为，确保行为边界合规，防止Agent学习人类闲聊、越权操作、边界漂移
@dependencies: json, hashlib, datetime, pathlib, dataclasses, enum, threading
@last_modified: 2026-03-18

核心职责：记录和审计Agent行为，确保行为边界合规。

参考：虎嗅文章《Multi-Agent协作的三大陷阱》
行为审计：防止Agent学习人类闲聊、越权操作、边界漂移

作者：虚拟研发中心安全团队
创建：2026-03-16
"""

import json
import hashlib
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, Any
import threading

# === 类型定义 ===

class BehaviorCategory(Enum):
    """行为分类"""
    TASK_EXECUTION = "task_execution"       # 任务执行
    COMMUNICATION = "communication"          # 通信交互
    RESOURCE_ACCESS = "resource_access"      # 资源访问
    DECISION = "decision"                    # 决策行为
    ERROR_HANDLING = "error_handling"        # 错误处理
    BOUNDARY_CROSS = "boundary_cross"        # 边界越界（违规）


class BehaviorSeverity(Enum):
    """行为严重程度"""
    INFO = "info"           # 信息
    WARNING = "warning"     # 警告
    VIOLATION = "violation" # 违规
    CRITICAL = "critical"   # 严重违规


@dataclass
class BehaviorLogEntry:
    """行为日志条目"""
    timestamp: str
    agent_id: str
    agent_role: str                  # CPO/CTO/CMO/Critic
    category: BehaviorCategory
    severity: BehaviorSeverity
    action: str                      # 行为描述
    context: dict = field(default_factory=dict)  # 上下文数据
    input_hash: Optional[str] = None  # 输入哈希（用于追踪）
    output_hash: Optional[str] = None # 输出哈希
    duration_ms: Optional[int] = None # 执行时长
    boundary_checked: bool = False    # 是否通过边界检查
    is_ai_declared: bool = True       # 是否声明了AI身份

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "agent_id": self.agent_id,
            "agent_role": self.agent_role,
            "category": self.category.value,
            "severity": self.severity.value,
            "action": self.action,
            "context": self.context,
            "input_hash": self.input_hash,
            "output_hash": self.output_hash,
            "duration_ms": self.duration_ms,
            "boundary_checked": self.boundary_checked,
            "is_ai_declared": self.is_ai_declared
        }


@dataclass
class BehaviorAuditReport:
    """行为审计报告"""
    audit_time: str
    total_entries: int
    violations: int
    warnings: int
    boundary_crosses: list[dict]
    ai_identity_compliance: float  # AI身份声明合规率
    recommendations: list[str]


# === 核心审计器 ===

class BehaviorLogger:
    """行为边界审计日志器"""

    def __init__(self, log_dir: Optional[Path] = None):
        self.log_dir = log_dir or Path(__file__).parent.parent.parent / ".ai-state" / "behavior_logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.current_log_file = self.log_dir / f"behavior_{datetime.now().strftime('%Y%m%d')}.jsonl"
        self._lock = threading.Lock()
        self._session_entries: list[BehaviorLogEntry] = []

    def _hash_content(self, content: Any) -> str:
        """生成内容哈希"""
        if isinstance(content, dict):
            content = json.dumps(content, sort_keys=True)
        return hashlib.sha256(str(content).encode()).hexdigest()[:16]

    def log(self,
            agent_id: str,
            agent_role: str,
            category: BehaviorCategory,
            severity: BehaviorSeverity,
            action: str,
            context: Optional[dict] = None,
            input_content: Optional[Any] = None,
            output_content: Optional[Any] = None,
            duration_ms: Optional[int] = None,
            boundary_checked: bool = False) -> BehaviorLogEntry:
        """
        记录行为日志

        Args:
            agent_id: Agent唯一标识
            agent_role: Agent角色（CPO/CTO/CMO等）
            category: 行为分类
            severity: 严重程度
            action: 行为描述
            context: 上下文数据
            input_content: 输入内容（将被哈希）
            output_content: 输出内容（将被哈希）
            duration_ms: 执行时长（毫秒）
            boundary_checked: 是否通过边界检查

        Returns:
            BehaviorLogEntry: 日志条目
        """
        entry = BehaviorLogEntry(
            timestamp=datetime.now().isoformat(),
            agent_id=agent_id,
            agent_role=agent_role,
            category=category,
            severity=severity,
            action=action,
            context=context or {},
            input_hash=self._hash_content(input_content) if input_content else None,
            output_hash=self._hash_content(output_content) if output_content else None,
            duration_ms=duration_ms,
            boundary_checked=boundary_checked,
            is_ai_declared=True  # 默认已声明AI身份
        )

        with self._lock:
            self._session_entries.append(entry)
            self._write_entry(entry)

        return entry

    def _write_entry(self, entry: BehaviorLogEntry):
        """写入日志条目到文件"""
        with open(self.current_log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")

    def log_task_execution(self,
                          agent_id: str,
                          agent_role: str,
                          task_desc: str,
                          input_contract: dict,
                          output_contract: dict,
                          duration_ms: int,
                          passed_review: bool) -> BehaviorLogEntry:
        """记录任务执行"""
        return self.log(
            agent_id=agent_id,
            agent_role=agent_role,
            category=BehaviorCategory.TASK_EXECUTION,
            severity=BehaviorSeverity.INFO if passed_review else BehaviorSeverity.WARNING,
            action=f"执行任务: {task_desc[:50]}...",
            context={"passed_review": passed_review},
            input_content=input_contract,
            output_content=output_contract,
            duration_ms=duration_ms,
            boundary_checked=passed_review
        )

    def log_boundary_violation(self,
                              agent_id: str,
                              agent_role: str,
                              violation_type: str,
                              details: str) -> BehaviorLogEntry:
        """记录边界违规"""
        return self.log(
            agent_id=agent_id,
            agent_role=agent_role,
            category=BehaviorCategory.BOUNDARY_CROSS,
            severity=BehaviorSeverity.VIOLATION,
            action=f"边界违规 [{violation_type}]: {details}",
            context={"violation_type": violation_type},
            boundary_checked=False
        )

    def log_communication(self,
                         agent_id: str,
                         agent_role: str,
                         target_agent: str,
                         message_type: str,
                         is_structured: bool) -> BehaviorLogEntry:
        """记录通信行为"""
        severity = BehaviorSeverity.INFO if is_structured else BehaviorSeverity.WARNING

        return self.log(
            agent_id=agent_id,
            agent_role=agent_role,
            category=BehaviorCategory.COMMUNICATION,
            severity=severity,
            action=f"通信 -> {target_agent} ({message_type})",
            context={"target_agent": target_agent, "message_type": message_type, "is_structured": is_structured},
            boundary_checked=is_structured
        )

    def generate_audit_report(self) -> BehaviorAuditReport:
        """生成审计报告"""
        entries = self._session_entries
        total = len(entries)

        violations = sum(1 for e in entries if e.severity == BehaviorSeverity.VIOLATION)
        warnings = sum(1 for e in entries if e.severity == BehaviorSeverity.WARNING)
        boundary_crosses = [
            e.to_dict() for e in entries
            if e.category == BehaviorCategory.BOUNDARY_CROSS
        ]

        # 计算AI身份声明合规率
        ai_declared_count = sum(1 for e in entries if e.is_ai_declared)
        ai_compliance = (ai_declared_count / total * 100) if total > 0 else 100.0

        # 生成建议
        recommendations = []
        if violations > 0:
            recommendations.append(f"发现 {violations} 次违规，建议审查边界配置")
        if warnings > 3:
            recommendations.append("警告次数较多，建议优化Agent行为规范")
        if ai_compliance < 100:
            recommendations.append("部分Agent未声明AI身份，建议检查prompt配置")
        if not recommendations:
            recommendations.append("行为边界合规良好，继续保持")

        return BehaviorAuditReport(
            audit_time=datetime.now().isoformat(),
            total_entries=total,
            violations=violations,
            warnings=warnings,
            boundary_crosses=boundary_crosses,
            ai_identity_compliance=ai_compliance,
            recommendations=recommendations
        )

    def export_report(self, output_path: Optional[Path] = None) -> Path:
        """导出审计报告"""
        report = self.generate_audit_report()
        output_path = output_path or self.log_dir / f"audit_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump({
                "audit_time": report.audit_time,
                "total_entries": report.total_entries,
                "violations": report.violations,
                "warnings": report.warnings,
                "boundary_crosses": report.boundary_crosses,
                "ai_identity_compliance": report.ai_identity_compliance,
                "recommendations": report.recommendations
            }, f, ensure_ascii=False, indent=2)

        return output_path


# === 全局实例 ===

_global_logger: Optional[BehaviorLogger] = None

def get_behavior_logger() -> BehaviorLogger:
    """获取全局行为日志器"""
    global _global_logger
    if _global_logger is None:
        _global_logger = BehaviorLogger()
    return _global_logger


def log_behavior(agent_id: str,
                agent_role: str,
                category: BehaviorCategory,
                severity: BehaviorSeverity,
                action: str,
                **kwargs) -> BehaviorLogEntry:
    """便捷函数：记录行为"""
    return get_behavior_logger().log(
        agent_id=agent_id,
        agent_role=agent_role,
        category=category,
        severity=severity,
        action=action,
        **kwargs
    )


# === 测试入口 ===

if __name__ == "__main__":
    logger = BehaviorLogger()

    print("=" * 60)
    print("行为边界审计日志测试")
    print("=" * 60)

    # 模拟Agent行为日志
    logger.log_task_execution(
        agent_id="cpo-001",
        agent_role="CPO",
        task_desc="分析蓝牙模块需求并生成任务契约",
        input_contract={"requirement": "低功耗蓝牙5.0"},
        output_contract={"tasks": ["硬件选型", "协议适配"]},
        duration_ms=1500,
        passed_review=True
    )

    logger.log_boundary_violation(
        agent_id="cto-001",
        agent_role="CTO",
        violation_type="GLOBAL_STATE_ACCESS",
        details="CTO节点尝试读取全局状态树"
    )

    logger.log_communication(
        agent_id="cmo-001",
        agent_role="CMO",
        target_agent="CTO",
        message_type="informal",
        is_structured=False
    )

    # 生成报告
    report = logger.generate_audit_report()
    print(f"\n审计报告:")
    print(f"  总条目: {report.total_entries}")
    print(f"  违规次数: {report.violations}")
    print(f"  警告次数: {report.warnings}")
    print(f"  AI身份合规率: {report.ai_identity_compliance:.1f}%")
    print(f"\n建议:")
    for rec in report.recommendations:
        print(f"  - {rec}")

    # 导出报告
    report_path = logger.export_report()
    print(f"\n报告已导出: {report_path}")