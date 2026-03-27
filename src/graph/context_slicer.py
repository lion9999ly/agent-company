# 🔀 上下文切片管理器 (Context Slicer)
"""
核心职责：为CTO/CMO执行节点提供隔离的上下文切片，防止全局状态污染。

设计原则：
1. 执行级盲盒隔离：CTO/CMO绝对禁止读取AgentGlobalState全量数据
2. 白名单机制：只允许访问明确声明的字段
3. 依赖追踪：记录每个切片的依赖关系，支持增量更新
4. 审计日志：所有切片访问行为记录到行为日志

参考：虎嗅文章《Multi-Agent协作的三大陷阱》
- 上下文熵增：Token爆炸导致系统不可控
- 解决方案：渐进式加载，按需切片

作者：虚拟研发中心安全团队
创建：2026-03-16
"""

import json
import hashlib
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional, Any, Callable
from enum import Enum

# === 类型定义 ===

class SliceType(Enum):
    """切片类型"""
    CTO_DEVELOPMENT = "cto_development"      # CTO研发切片
    CMO_MARKETING = "cmo_marketing"          # CMO市场切片
    PROTOTYPE_LOFI = "prototype_lofi"        # 低保真原型切片
    PROTOTYPE_HIFI = "prototype_hifi"        # 高保真原型切片
    CRITIC_REVIEW = "critic_review"          # 评审切片


class AccessLevel(Enum):
    """访问级别"""
    READ_ONLY = "read_only"      # 只读
    READ_WRITE = "read_write"    # 可读写（仅限自己产出）
    FULL_ACCESS = "full_access"  # 完全访问（仅CPO）


@dataclass
class FieldAccess:
    """字段访问权限"""
    field_path: str              # 字段路径，如 "task_contract.task_goal"
    access_level: AccessLevel
    reason: str                  # 为什么需要访问这个字段


@dataclass
class ContextSlice:
    """上下文切片"""
    slice_id: str
    slice_type: SliceType
    target_agent: str            # 目标Agent ID
    created_at: str
    data: dict                   # 切片数据
    dependencies: list[str]      # 依赖的其他切片ID
    access_whitelist: list[FieldAccess]
    checksum: str                # 数据校验和


@dataclass
class SliceAuditLog:
    """切片访问审计日志"""
    timestamp: str
    slice_id: str
    agent_id: str
    action: str                  # create, read, write
    fields_accessed: list[str]
    allowed: bool


# === 白名单配置 ===

# CTO节点允许访问的字段
CTO_WHITELIST: list[FieldAccess] = [
    FieldAccess("task_contract.task_goal", AccessLevel.READ_ONLY, "需要了解全局目标"),
    FieldAccess("sub_tasks.{task_id}", AccessLevel.READ_ONLY, "自己的任务契约"),
    FieldAccess("execution.cto_output", AccessLevel.READ_WRITE, "自己的产出"),
    FieldAccess("control.error_traceback", AccessLevel.READ_ONLY, "错误历史用于调试"),
]

# CMO节点允许访问的字段
CMO_WHITELIST: list[FieldAccess] = [
    FieldAccess("task_contract.task_goal", AccessLevel.READ_ONLY, "需要了解全局目标"),
    FieldAccess("sub_tasks.{task_id}", AccessLevel.READ_ONLY, "自己的任务契约"),
    FieldAccess("execution.cmo_output", AccessLevel.READ_WRITE, "自己的产出"),
    FieldAccess("control.error_traceback", AccessLevel.READ_ONLY, "错误历史用于调试"),
]

# CPO节点允许访问的字段（完全访问）
CPO_WHITELIST: list[FieldAccess] = [
    FieldAccess("*", AccessLevel.FULL_ACCESS, "CPO是调度中枢，需要全局视野"),
]

# Critic节点允许访问的字段
CRITIC_WHITELIST: list[FieldAccess] = [
    FieldAccess("task_contract", AccessLevel.READ_ONLY, "需要评审契约"),
    FieldAccess("sub_tasks", AccessLevel.READ_ONLY, "需要评审子任务"),
    FieldAccess("execution.review_reports", AccessLevel.READ_WRITE, "写入评审报告"),
]


class ContextSlicer:
    """上下文切片管理器"""

    def __init__(self, audit_enabled: bool = True):
        self.audit_enabled = audit_enabled
        self._slice_cache: dict[str, ContextSlice] = {}
        self._audit_logs: list[SliceAuditLog] = []

    def _compute_checksum(self, data: dict) -> str:
        """计算数据校验和"""
        data_str = json.dumps(data, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(data_str.encode()).hexdigest()[:16]

    def _log_access(self, slice_id: str, agent_id: str, action: str,
                    fields: list[str], allowed: bool):
        """记录访问日志"""
        if not self.audit_enabled:
            return

        log = SliceAuditLog(
            timestamp=datetime.now().isoformat(),
            slice_id=slice_id,
            agent_id=agent_id,
            action=action,
            fields_accessed=fields,
            allowed=allowed
        )
        self._audit_logs.append(log)

        # 同时写入行为日志
        try:
            from src.audit import log_behavior, BehaviorCategory, BehaviorSeverity
            log_behavior(
                agent_id=agent_id,
                agent_role=slice_id.split("_")[0].upper(),
                category=BehaviorCategory.RESOURCE_ACCESS,
                severity=BehaviorSeverity.INFO if allowed else BehaviorSeverity.VIOLATION,
                action=f"Context slice {action}: {slice_id}",
                context={"fields": fields, "allowed": allowed}
            )
        except ImportError:
            pass  # 审计模块不可用时静默跳过

    def create_cto_slice(self,
                         task_id: str,
                         global_state: dict,
                         task_contract: dict) -> ContextSlice:
        """
        创建CTO研发切片

        Args:
            task_id: 任务ID
            global_state: 全局状态（仅提取白名单字段）
            task_contract: 任务契约

        Returns:
            ContextSlice: CTO上下文切片
        """
        slice_id = f"cto_{task_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}"

        # 严格按白名单提取数据
        slice_data = {
            "task_id": task_id,
            "task_goal": global_state.get("task_contract", {}).get("task_goal", ""),
            "my_contract": task_contract,
            "error_history": global_state.get("control", {}).get("error_traceback", [])[-5:],  # 最近5条错误
            "previous_output": global_state.get("execution", {}).get("cto_output"),
        }

        # 计算依赖
        dependencies = []
        if task_contract.get("depends_on"):
            dependencies.extend(task_contract["depends_on"])

        slice_obj = ContextSlice(
            slice_id=slice_id,
            slice_type=SliceType.CTO_DEVELOPMENT,
            target_agent="cto",
            created_at=datetime.now().isoformat(),
            data=slice_data,
            dependencies=dependencies,
            access_whitelist=CTO_WHITELIST,
            checksum=self._compute_checksum(slice_data)
        )

        self._slice_cache[slice_id] = slice_obj
        self._log_access(slice_id, "cto", "create", list(slice_data.keys()), True)

        return slice_obj

    def create_cmo_slice(self,
                         task_id: str,
                         global_state: dict,
                         task_contract: dict) -> ContextSlice:
        """
        创建CMO市场切片

        Args:
            task_id: 任务ID
            global_state: 全局状态（仅提取白名单字段）
            task_contract: 任务契约

        Returns:
            ContextSlice: CMO上下文切片
        """
        slice_id = f"cmo_{task_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}"

        # 严格按白名单提取数据
        slice_data = {
            "task_id": task_id,
            "task_goal": global_state.get("task_contract", {}).get("task_goal", ""),
            "my_contract": task_contract,
            "error_history": global_state.get("control", {}).get("error_traceback", [])[-5:],
            "previous_output": global_state.get("execution", {}).get("cmo_output"),
        }

        dependencies = []
        if task_contract.get("depends_on"):
            dependencies.extend(task_contract["depends_on"])

        slice_obj = ContextSlice(
            slice_id=slice_id,
            slice_type=SliceType.CMO_MARKETING,
            target_agent="cmo",
            created_at=datetime.now().isoformat(),
            data=slice_data,
            dependencies=dependencies,
            access_whitelist=CMO_WHITELIST,
            checksum=self._compute_checksum(slice_data)
        )

        self._slice_cache[slice_id] = slice_obj
        self._log_access(slice_id, "cmo", "create", list(slice_data.keys()), True)

        return slice_obj

    def create_critic_slice(self, global_state: dict) -> ContextSlice:
        """创建Critic评审切片"""
        slice_id = f"critic_{datetime.now().strftime('%Y%m%d%H%M%S')}"

        # Critic需要更多上下文进行评审
        slice_data = {
            "task_contract": global_state.get("task_contract", {}),
            "sub_tasks": global_state.get("sub_tasks", {}),
            "prototype_evaluation": global_state.get("prototype_evaluation", {}),
        }

        slice_obj = ContextSlice(
            slice_id=slice_id,
            slice_type=SliceType.CRITIC_REVIEW,
            target_agent="critic",
            created_at=datetime.now().isoformat(),
            data=slice_data,
            dependencies=[],
            access_whitelist=CRITIC_WHITELIST,
            checksum=self._compute_checksum(slice_data)
        )

        self._slice_cache[slice_id] = slice_obj
        self._log_access(slice_id, "critic", "create", list(slice_data.keys()), True)

        return slice_obj

    def get_slice(self, slice_id: str, agent_id: str) -> Optional[ContextSlice]:
        """
        获取切片

        Args:
            slice_id: 切片ID
            agent_id: 请求Agent ID

        Returns:
            ContextSlice 或 None
        """
        slice_obj = self._slice_cache.get(slice_id)
        if not slice_obj:
            self._log_access(slice_id, agent_id, "read", [], False)
            return None

        # 验证访问权限
        if slice_obj.target_agent != agent_id and agent_id != "cpo":
            self._log_access(slice_id, agent_id, "read", [], False)
            raise PermissionError(f"Agent {agent_id} 无权访问切片 {slice_id}")

        self._log_access(slice_id, agent_id, "read", list(slice_obj.data.keys()), True)
        return slice_obj

    def update_slice_output(self, slice_id: str, agent_id: str, output: dict) -> bool:
        """
        更新切片产出

        Args:
            slice_id: 切片ID
            agent_id: Agent ID
            output: 产出数据

        Returns:
            是否更新成功
        """
        slice_obj = self._slice_cache.get(slice_id)
        if not slice_obj:
            return False

        # 验证权限
        if slice_obj.target_agent != agent_id:
            self._log_access(slice_id, agent_id, "write", [], False)
            return False

        # 更新数据
        slice_obj.data["output"] = output
        slice_obj.checksum = self._compute_checksum(slice_obj.data)
        self._log_access(slice_id, agent_id, "write", ["output"], True)

        return True

    def validate_no_global_access(self, agent_id: str, accessed_fields: list[str]) -> bool:
        """
        验证Agent没有访问全局状态

        Args:
            agent_id: Agent ID
            accessed_fields: 实际访问的字段列表

        Returns:
            是否合规
        """
        if agent_id in ("cpo", "critic"):
            return True  # CPO和Critic允许全局访问

        # 确定白名单
        whitelist = CTO_WHITELIST if agent_id == "cto" else CMO_WHITELIST
        allowed_paths = {fa.field_path.replace("{task_id}", "*") for fa in whitelist}

        for field in accessed_fields:
            # 检查字段是否在白名单中
            allowed = False
            for allowed_path in allowed_paths:
                if allowed_path == "*":
                    allowed = True
                    break
                if allowed_path.endswith("*"):
                    if field.startswith(allowed_path[:-1]):
                        allowed = True
                        break
                elif field == allowed_path:
                    allowed = True
                    break

            if not allowed:
                self._log_access("global", agent_id, "read", [field], False)
                return False

        return True

    def get_audit_logs(self, limit: int = 100) -> list[dict]:
        """获取审计日志"""
        return [asdict(log) for log in self._audit_logs[-limit:]]

    def export_slice(self, slice_id: str) -> Optional[dict]:
        """导出切片为字典"""
        slice_obj = self._slice_cache.get(slice_id)
        if not slice_obj:
            return None
        return {
            "slice_id": slice_obj.slice_id,
            "slice_type": slice_obj.slice_type.value,
            "target_agent": slice_obj.target_agent,
            "created_at": slice_obj.created_at,
            "data": slice_obj.data,
            "dependencies": slice_obj.dependencies,
            "checksum": slice_obj.checksum
        }


# === 全局实例 ===

_slicer: Optional[ContextSlicer] = None

def get_context_slicer() -> ContextSlicer:
    """获取全局切片管理器"""
    global _slicer
    if _slicer is None:
        _slicer = ContextSlicer()
    return _slicer


# === 便捷函数 ===

def create_cto_slice(task_id: str, global_state: dict, task_contract: dict) -> ContextSlice:
    """便捷函数：创建CTO切片"""
    return get_context_slicer().create_cto_slice(task_id, global_state, task_contract)


def create_cmo_slice(task_id: str, global_state: dict, task_contract: dict) -> ContextSlice:
    """便捷函数：创建CMO切片"""
    return get_context_slicer().create_cmo_slice(task_id, global_state, task_contract)


# === 测试入口 ===

if __name__ == "__main__":
    print("=" * 60)
    print("上下文切片管理器测试")
    print("=" * 60)

    slicer = ContextSlicer()

    # 模拟全局状态
    mock_global_state = {
        "task_contract": {
            "task_goal": "开发智能骑行头盔蓝牙模块"
        },
        "sub_tasks": {
            "task_001": {
                "subtask_id": "task_001",
                "target_role": "cto",
                "task_description": "设计蓝牙5.0协议栈",
                "depends_on": []
            },
            "task_002": {
                "subtask_id": "task_002",
                "target_role": "cmo",
                "task_description": "调研蓝牙芯片供应商",
                "depends_on": ["task_001"]
            }
        },
        "control": {
            "error_traceback": ["之前的错误1", "之前的错误2"]
        },
        "execution": {
            "cto_output": None,
            "cmo_output": None
        }
    }

    # 创建CTO切片
    cto_slice = slicer.create_cto_slice(
        task_id="task_001",
        global_state=mock_global_state,
        task_contract=mock_global_state["sub_tasks"]["task_001"]
    )
    print(f"\nCTO Slice Created: {cto_slice.slice_id}")
    print(f"  Data keys: {list(cto_slice.data.keys())}")
    print(f"  Checksum: {cto_slice.checksum}")

    # 创建CMO切片
    cmo_slice = slicer.create_cmo_slice(
        task_id="task_002",
        global_state=mock_global_state,
        task_contract=mock_global_state["sub_tasks"]["task_002"]
    )
    print(f"\nCMO Slice Created: {cmo_slice.slice_id}")
    print(f"  Dependencies: {cmo_slice.dependencies}")

    # 验证权限
    print(f"\n权限验证:")
    print(f"  CTO访问全局状态: {slicer.validate_no_global_access('cto', ['task_contract.task_goal'])}")
    print(f"  CTO非法访问: {slicer.validate_no_global_access('cto', ['execution.cmo_output'])}")

    # 查看审计日志
    print(f"\n审计日志: {len(slicer.get_audit_logs())} 条")