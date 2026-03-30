"""
@description: 全局状态树定义，包含TypedDict类型定义和枚举类
@dependencies: typing, enum
@last_modified: 2026-03-18
"""
import operator
from typing import TypedDict, Annotated, List, Dict, Optional, Any
from enum import Enum

# --- 1. 强类型枚举 (消除魔法字符串并补充 __str__ 方法) ---
class GlobalStatus(str, Enum):
    PENDING = "pending"
    PLANNING = "planning"
    PROTOTYPING_LO_FI = "prototyping_lo_fi"
    PROTOTYPING_HI_FI = "prototyping_hi_fi"
    EXECUTING = "executing"
    MERGING = "merging"
    HALTED = "halted"
    COMPLETED = "completed"
    TERMINATED = "terminated"
    ARCHIVED = "archived"

    def __str__(self) -> str:
        return self.value

class TargetRole(str, Enum):
    CTO = "cto"
    CMO = "cmo"
    PROTOTYPE = "prototype"

    def __str__(self) -> str:
        return self.value

class NodeStatus(str, Enum):
    SUCCESS = "success"
    ERROR = "error"
    HALTED = "halted"
    TIMEOUT = "timeout"

    def __str__(self) -> str:
        return self.value

class OperatorRole(str, Enum):
    ARCHITECT = "architect"
    PRODUCT_MANAGER = "pm"
    HARDWARE_ENGINEER = "hw_eng"

    def __str__(self) -> str:
        return self.value

# --- Reducer 函数 ---
def append_logs(existing: List[Any], new: List[Any]) -> List[Any]:
    return existing + new if existing else new

def merge_dict(left: dict, right: dict) -> dict:
    """通用字典合并函数：用于并行节点的字段合并"""
    merged = {**left}
    merged.update(right)
    return merged

# 专用的 reducer 别名（语义更清晰）
merge_execution = merge_dict
merge_metadata = merge_dict
merge_task_contract = merge_dict
merge_contract_metadata = merge_dict
merge_prototype_evaluation = merge_dict
merge_sub_tasks = merge_dict
merge_control = merge_dict

# --- 结构化字典 ---
class SubTaskContract(TypedDict):
    subtask_id: str
    target_role: TargetRole
    task_description: str
    depends_on: List[str]
    is_core_dependency: bool
    dependency_timeout_sec: int
    output_schema: Dict[str, str]
    acceptance_criteria: Dict[str, Dict[str, str]]
    tool_white_list: List[str]

class NodeExecutionLog(TypedDict):
    node_name: str
    start_time: float
    end_time: float
    duration_sec: float
    status: NodeStatus

# --- 核心状态树 ---
class ControlData(TypedDict):
    current_node: str
    retry_counts: Dict[str, int]
    error_traceback: Annotated[List[str], append_logs]
    human_approval_status: str
    resume_from_node: Optional[str]
    node_execution_logs: Annotated[List[NodeExecutionLog], append_logs]

class ExecutionData(TypedDict):
    prototype_output: Optional[Dict[str, str]]
    prototype_output_word_count: Optional[int]
    cto_output: Optional[Dict[str, str]]
    cto_output_word_count: Optional[int]
    cmo_output: Optional[Dict[str, str]]
    cmo_output_word_count: Optional[int]
    review_reports: Annotated[List[Dict[str, str]], append_logs]

class TaskMetadata(TypedDict):
    task_id: str
    global_status: GlobalStatus
    max_retry_threshold: int

# --- 2. 细化中枢元数据与契约 (消灭 Dict[str, Any]) ---
class ContractMetadata(TypedDict):
    contract_version: str
    generated_at: str
    operator_role_applied: str

class PrototypeEvaluation(TypedDict):
    has_hardware_ui: bool
    has_new_interaction_logic: bool
    is_existing_product_iteration: bool
    decision_result: str

class TaskContract(TypedDict):
    task_goal: str
    _sys_enforced_hash: str  # 由系统物理计算注入的哈希印记

# --- 3. 明确 Send API 扇出切片类型 ---
class CTOTaskSlice(TypedDict):
    """CTO研发任务切片 - 严格执行上下文隔离"""
    current_task_id: str
    slice_id: Optional[str]           # 切片唯一标识
    task_goal: Optional[str]          # 全局目标（只读）
    my_contract: Optional[SubTaskContract]  # 自己的任务契约
    error_history: Optional[List[str]]      # 最近错误历史
    previous_output: Optional[Dict[str, str]]  # 之前的产出
    dependencies: Optional[List[str]]        # 依赖的其他任务
    checksum: Optional[str]                  # 数据校验和


class CMOTaskSlice(TypedDict):
    """CMO市场任务切片 - 严格执行上下文隔离"""
    current_task_id: str
    slice_id: Optional[str]
    task_goal: Optional[str]
    my_contract: Optional[SubTaskContract]
    error_history: Optional[List[str]]
    previous_output: Optional[Dict[str, str]]
    dependencies: Optional[List[str]]
    checksum: Optional[str]


class CriticTaskSlice(TypedDict):
    """Critic评审任务切片 - 需要更多上下文"""
    slice_id: Optional[str]
    task_contract: Optional[TaskContract]
    sub_tasks: Optional[Dict[str, SubTaskContract]]
    prototype_evaluation: Optional[PrototypeEvaluation]

# --- 4. 组装终极 AgentGlobalState ---
class AgentGlobalState(TypedDict):
    metadata: Annotated[TaskMetadata, merge_metadata]              # 并行节点写入合并
    contract_metadata: Annotated[ContractMetadata, merge_contract_metadata]  # 并行节点写入合并
    prototype_evaluation: Annotated[PrototypeEvaluation, merge_prototype_evaluation]  # 并行节点写入合并
    task_contract: Annotated[TaskContract, merge_task_contract]   # 并行节点写入合并
    sub_tasks: Annotated[Dict[str, SubTaskContract], merge_sub_tasks]  # 并行节点写入合并
    execution: Annotated[ExecutionData, merge_execution]          # 并行节点写入合并
    control: Annotated[ControlData, merge_control]                # 并行节点写入合并