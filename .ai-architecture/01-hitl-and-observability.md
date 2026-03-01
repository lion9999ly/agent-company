# 🚦 人类介入闭环与系统可观测性规范 (HITL & Observability)

> **[SYSTEM DIRECTIVE]**
> 本文件定义了系统在遭遇极端异常、依赖死锁或硬件验证失败时，如何安全地将控制权移交人类，以及人类如何标准化地将系统唤醒。同时定义了系统的轻量级探针标准。

## 1. 人类介入 (HITL) 触发与标准操作流 (SOP)

当系统生成 `.SYSTEM_HALTED.lock` 并挂起时，人类架构师必须通过以下标准闭环进行干预，严禁直接去代码堆里“乱改一通”后强行重启。

### 1.1 状态诊断
* 人类首先读取 `.ai-state/control_data_dump.json`，查看 `error_traceback` 和 `node_execution_logs` 定位崩溃节点。

### 1.2 注入人类指令 (Human Feedback Injection)
* 人类必须在 `.ai-state/` 目录下新建/修改 `human_feedback.json` 文件，严格遵循以下 Schema：

```json
{
  "timestamp": "2026-02-28T17:00:00Z",
  "operator": "human_architect",
  "action_taken": "修改了 CTO 的任务契约，放宽了蓝牙模块的功耗限制",
  "resume_from_node": "Router", // 极其关键：告诉状态机从哪里重新流转
  "override_state_updates": {
    // 如果需要强行修改当前 State，在此处写明 JSON Path 和新值
  }
}
```

### 1.3 唤醒序列与预检锁
[预校验防线 (Pre-flight Validation)]
resume_graph.py 脚本在将人类的 human_feedback.json 合并入状态树之前，必须在内存中执行以下强校验（防呆机制）：

Schema 校验：人类覆盖的 override_state_updates 必须能够完美通过 AgentGlobalState 的数据类型断言（不能填错数据格式）。

枚举校验：所有填入的状态字符串必须存在于系统定义的 Enum 字典类中（只能做“单选题”，不能随便乱造词）。

拓扑合法性：resume_from_node 指定的节点名称，必须是存在于 00-global-architecture.md 中定义的合法节点。

权限越界阻断 (新增)：强制校验 human_feedback.json 里的 operator_role。如果角色是 pm 却试图修改 CTO 的 acceptance_criteria.hardware_metrics，脚本直接抛出 PermissionError 并拒绝唤醒系统。

惩罚机制：若以上任何一项预检失败，唤醒脚本必须直接报错退出，并绝对拒绝解除 .SYSTEM_HALTED.lock 死锁文件。

## 2. 并行路由调度与超时异常机制
[依赖阻断与超时级联 (Cascading Timeout)]

当 Router（路由调度节点）轮询前置依赖任务时，若依赖任务的耗时超过了该任务契约设定的 dependency_timeout_sec（默认 1800 秒）。

系统立即将该依赖任务的状态标记为 TIMEOUT，并直接触发全局 HALTED（挂起死锁）。

级联阻断：所有等待该依赖的下游任务（例如 CMO 节点正在等待 CTO 节点的输出），其状态必须同步变更为 ERROR (Dependency Failed)。彻底杜绝系统假死与计算资源的无效空转。

[依赖分级降级 (Soft Timeout) (新增)]

如果 CTO 任务超时，且 is_core_dependency == False（例如只是外观渲染图没出），Router 将不再挂起全局系统。

而是将下游依赖该任务的节点状态置为 WAITING_FOR_CONFIRM，通过桌面通知请求人类确认：“非核心依赖已超时，是否强行跳过该依赖继续执行？”