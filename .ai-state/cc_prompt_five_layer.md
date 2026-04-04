五层诊断改进，分两批执行。

## 第一批: P0（先做）

读取 `.ai-state/cc_exec_five_layer_p0.md`，按顺序执行三项 P0 改进：
1. 创建产品决策树 + 注入任务发现引擎
2. Agent prompt 统一管理（从 agent_prompts.yaml 读取，不再内联）
3. 拆分 tonight_deep_research.py 为 scripts/deep_research/ 模块包

每项完成后单独 commit + push：
```bash
git add -A && git commit -m "improve: {描述}" && git push origin main
```

拆分 tonight_deep_research.py 时特别注意：
- 所有现有的 import 路径必须继续工作（text_router.py 中的 `from scripts.tonight_deep_research import run_deep_learning`）
- 拆完后运行 `python -c "from scripts.tonight_deep_research import run_deep_learning; print('OK')"` 验证
- 如果验证失败，修复后再 commit

## 第二批: P1（P0 全部完成后再做）

读取 `.ai-state/cc_exec_five_layer_p1.md`，执行 7 项 P1 改进。合成一次 commit + push。

不要重启服务。
