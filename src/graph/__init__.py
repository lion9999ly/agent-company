# 📊 Graph 模块 (State Graph & Router)
"""
LangGraph状态机与流转拓扑。

核心组件：
- router.py: 状态机定义与节点实现
- context_slicer.py: 上下文切片管理器

设计原则：
1. CPO拥有全局视野，CTO/CMO严格执行切片隔离
2. 所有状态变更通过Reducer机制，禁止直接覆盖
3. 安全检查节点在前，业务节点在后
"""

from .router import app, workflow
from .context_slicer import (
    ContextSlicer,
    get_context_slicer,
    create_cto_slice,
    create_cmo_slice,
    SliceType,
    AccessLevel,
    ContextSlice
)

__all__ = [
    # Router
    "app",
    "workflow",
    # Context Slicer
    "ContextSlicer",
    "get_context_slicer",
    "create_cto_slice",
    "create_cmo_slice",
    "SliceType",
    "AccessLevel",
    "ContextSlice"
]