读取以下三份执行文档，按顺序执行全部改造：

1. `.ai-state/cc_exec_part1_pipeline_overhaul.md` — 五层管道架构 + 模型路由 + Bug 修复
2. `.ai-state/cc_exec_part1_supplement_concurrency.md` — 并发与流水线
3. `.ai-state/cc_exec_part2_learning_system.md` — 自学习 + 深度学习 + KB 治理

执行规则：
- 先完整读完三份文档，理解整体架构后再动手
- Part 1 和补充文档合在一起改 tonight_deep_research.py 和 model_gateway.py，不要分两次改同一个文件
- deep_research_one() 必须拆成 _run_layers_1_to_3() 和 _run_layers_4_to_5() 两个函数，原函数保留为兼容入口
- Layer 1/2/3 的所有模型调用用 _call_with_backoff()（带信号量 + 限流退避），Layer 4/5 用 _call_model()
- 现有定时机制先搜索确认（grep scheduler/cron/Timer/interval），再决定怎么注册自学习和深度学习
- 飞书 handler 中注册 "深度学习" 指令时，先搜索现有路由模式（grep text_router.py 中的 if/elif 结构），保持一致
- model_registry.yaml 中已有的豆包和 Norway East 配置，检查是否完整，缺什么补什么，不要重复添加
- .env 不要动，已经配好了
- 所有改动合成一次 commit：`git add -A && git commit -m "feat: deep research v2 — five-layer pipeline, dual search, concurrency, learning system, KB governance"`
- 不要重启服务，Leo 手动重启
