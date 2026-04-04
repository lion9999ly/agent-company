读取 `.ai-state/cc_exec_pipeline_improvements.md`，执行 5 项改进。

要点：
- 改进 1（任务去重）：在 `_discover_new_tasks()` 中注入已有任务列表 + 返回前标题相似度过滤
- 改进 2（批量校准）：`push_calibration_to_feishu()` 改为只保存 pending，新增 `push_batch_calibration_summary()` 在深度学习结束后统一推送。text_router.py 中校准入口条件从 `text in ("1","2","3","0")` 改为 `all(c in "0123" for c in text) and len(text) <= 10`，支持 `11213` 格式批量标注
- 改进 3（CMO 角色）：先 grep 找到角色分配逻辑的具体位置，确保 CMO 在大多数任务中默认参与
- 改进 4（汇总报告）：在 `run_deep_learning()` 开头记录 KB 初始数量，结尾推送汇总（任务列表 + KB 增量 + P0 率 + 元能力进化 + KB 治理），并在汇总后调用 `push_batch_calibration_summary()`
- 改进 5（元能力通知）：`resolve_capability_gap()` 成功注册工具后推送飞书通知

每次 git commit 之后都追加 `git push origin main`。不要重启服务。
