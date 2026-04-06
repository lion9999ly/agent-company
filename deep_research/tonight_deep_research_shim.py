"""
tonight_deep_research.py — 向后兼容入口
所有实现已迁移到 scripts/deep_research/ 包

保留此文件确保以下调用方不用改：
- feishu_handlers/text_router.py
- start_all.bat
- 其他 import tonight_deep_research 的地方
"""

# === 公开接口重导出 ===
from scripts.deep_research.runner import (
    run_all,
    run_deep_learning,
    run_research_from_file,
    parse_research_tasks_from_md,
    RESEARCH_TASKS,
)
from scripts.deep_research.pipeline import (
    deep_research_one,
    deep_drill,
)
from scripts.deep_research.learning import (
    stress_test_product,
    sandbox_what_if,
)

# === 保持旧的 __main__ 入口兼容 ===
if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        md_path = sys.argv[1]
        task_ids = sys.argv[2:] if len(sys.argv) > 2 else None
        run_research_from_file(md_path, task_ids=task_ids)
    else:
        run_all()
