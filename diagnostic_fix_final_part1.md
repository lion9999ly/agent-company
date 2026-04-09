# CC 执行指令：Day 17 系统全量诊断修复（Part 1/2 — 修复指令）

> **来源**：Claude Chat 对 GitHub Issue #10-#32 共 23 个文件完整源码逐行审查
> **断点总数**：21 个（2 P0 + 9 P1 + 10 P2），#9 无需修复，实际修 20 个
> **执行前**：`git tag backup-before-diagnostic-fix`
> **执行后**：跑 Part 2 的 diagnostic_verify.py + 5 条飞书验证，结果发 GitHub Issue

---

## P0（2 个）

### #1 agent.py CLI 被 Windows 截断
**文件**：scripts/agent.py handle_with_claude_code()
**改**：把 prompt 写临时文件，去掉 shell=True。用临时文件内容传 -p 参数，或用 stdin。修完后删临时文件。

### #4 research_task_pool.yaml 不存在
**文件**：.ai-state/research_task_pool.yaml（新建 5 个任务：端侧AI/电池/Mesh/FreeForm/AI剪辑）
同时确认 product_decision_tree.yaml 存在且有 open decisions。

---

## P1（9 个）

### #2 agent.py 监控范围读错文件名
**文件**：scripts/agent.py handle_monitor_scope()
**改**：monitor_scope.json → competitor_monitor_config.json，解析用 config.get("monitor_layers", {})

### #3 post-commit hook 去掉 SDK 重启
**文件**：.git/hooks/post-commit
**改**：删除 stop_sdk + start_sdk 步骤，只保留 status 更新 + 验证 + 飞书通知

### #5 飞书文档内容为空
**文件**：scripts/feishu_output.py
**改**：先跑 lark-cli docs +create --help 确认参数。如果 stdin 不生效改为临时文件方式。测试：创建有内容的文档确认能看到。

### #7 P0 反弹检测过于激进
**文件**：scripts/roundtable/roundtable.py discuss()
**改**：convergence_trace[-1] > convergence_trace[-2] → convergence_trace[-1] > convergence_trace[0]

### #13 Verifier 自动生成规则不被加载
**文件**：scripts/roundtable/verifier.py _get_all_rules()
**改**：增加加载 task_{safe_topic}.json 的逻辑

### #14 AutoLearn 搜索失败也标记 covered
**文件**：scripts/auto_learn.py auto_learn_cycle()
**改**：只在 add_knowledge 成功后才 _save_covered_topic。删除搜索无结果/提取失败/质量不足时的 _save_covered_topic。

### #17 competitor_monitor 用旧 import
**文件**：scripts/competitor_monitor.py _send_feishu_notification()
**改**：from scripts.feishu_sdk_client import send_reply → from scripts.feishu_handlers.chat_helpers import send_reply

### #18 should_notify() 没被调用
**改**：在 tonight_deep_research/competitor_monitor/auto_learn/roundtable_handler 的通知发送点前加 should_notify 判断

### #20 learning_handlers 调用不存在的函数
**文件**：scripts/feishu_handlers/learning_handlers.py _handle_auto_learning()
**改**：from scripts.auto_learn import run_auto_learn → from scripts.auto_learn import auto_learn_cycle
threading.Thread(target=run_auto_learn) → threading.Thread(target=auto_learn_cycle)

---

## P2（10 个）

### #6 system_status.md 更新逻辑
**文件**：.git/hooks/post-commit
**改**："最近提交"每次覆盖，"最近变更"追加不去重，最多 10 条

### #8 因果链改为 Critic 自带 P0 ID
**文件**：scripts/roundtable/roundtable.py _phase_4_critic_proposal() prompt + _build_p0_feedback()
**改**：prompt 要求标注 P0-1/P0-2 ID，匹配用 ID 前缀

### #10 Generator 重试链加 gpt-5.3-codex
**文件**：scripts/roundtable/generator.py _generate_segment_with_retry()
**改**：models = ["gpt_5_3_codex", "gpt_5_4", "gemini_3_1_pro"]
前提：确认 model_registry.yaml 有配置

### #11 Generator _assemble_html 防御裸 JS
**文件**：scripts/roundtable/generator.py _assemble_html()
**改**：正则匹配不到 script 标签时主动包裹

### #12 Verifier no_external_deps 豁免字体 CDN
**文件**：scripts/roundtable/verifier.py RULE_CHECKS
**改**：排除 fonts.googleapis.com 和 fonts.gstatic.com

### #15 Generator.fix() 用 executive_summary 而非 raw_proposal
**文件**：scripts/roundtable/generator.py fix() + scripts/roundtable/__init__.py run_task()
**改**：fix() 加 task 参数，用 _get_input_source(task, rt_result)。run_task 调 fix 时传 task。

### #16 竞品监控影响研判层未实现
**文件**：scripts/competitor_monitor.py
**改**：search_keyword 返回后检查 impact_analysis.enabled，调 LLM 研判 high/medium/low，分流处理

### #19 text_router 和 agent.py 重复路由
**文件**：scripts/agent.py 全部快速通道
**改**：agent.py 的 handle_status/handle_monitor_scope 等改为 import text_router 或 handler 的实现，不重新写。共享实现，适配回复方式。

### #21 import_handlers URL 分享用旧 import
**文件**：scripts/feishu_handlers/import_handlers.py _handle_share_url()
**改**：from scripts.feishu_sdk_client import handle_share_content → 迁移到 import_handlers 自身或用新模块

---

## 执行顺序

```bash
git tag backup-before-diagnostic-fix
# P0
git add -A && git commit --no-verify -m "fix(P0): agent CLI temp file + research_task_pool"
# P1
git add -A && git commit --no-verify -m "fix(P1): 9 fixes"
# P2
git add -A && git commit --no-verify -m "fix(P2): 10 fixes"
git push origin main
# 重启 SDK
# 跑 Part 2 验证
```
