# 完整操作指南 — Day 15 最终版

> 日期: 2026-04-01
> 总改进项: 105+ 项（21 个批次 + Demo 闭环 V1-V4 + 学习系统 W1-W7）
> 执行方式: 4 个 CC 窗口并行
> 预计并行耗时: ~10h
> 你的动手时间: ~30 分钟

---

## 阶段 0：立即做的事（5 分钟）

### 0-1. claude.ai 连接 GitHub

1. 打开 claude.ai
2. 点左下角 "+" 按钮
3. 选 "Connectors"
4. 找到 GitHub → Connect
5. 授权访问 `lion9999ly/agent-company` 仓库

效果：以后我能直接读你的代码，不需要贴 URL。

### 0-2. 创建 Claude Project

1. claude.ai → 左侧栏 → Projects → New Project
2. 名字: `智能骑行头盔 R&D`
3. 添加 Project Knowledge（通过 GitHub 连接器）:
   - `CLAUDE.md`
   - `.ai-state/product_decision_tree.yaml`
4. 以后我们的对话在这个 Project 里进行

---

## 阶段 1：确认前置任务完成（2 分钟）

```powershell
cd D:\Users\uih00653\my_agent_company\pythonProject1
git log --oneline -15
```

确认以下 commit 存在：
- ✅ 248efcc — Agent prompt 统一
- ✅ ed82e2b — 决策树
- ✅ 8d50cec — 任务去重+批量校准+CMO+汇总+元能力通知
- ✅ 25652e6 — 架构清理+CLAUDE.md

确认 P0-3（拆分大文件）和 P1（7 项）是否完成。没完成就等完成后再继续。

---

## 阶段 2：下载 13 个文件

从 claude.ai 下载以下文件：

| # | 文件名 | 说明 |
|---|--------|------|
| 1 | `FINAL_COMPLETE_GUIDE.md` | 本操作指南 |
| 2 | `improvement_backlog_complete.md` | 105 项完整清单 |
| 3 | `handoff_20260331.md` | 今日会话交接文档 |
| 4 | `cc_exec_track_a.md` | 轨道 A 执行文档（19 项） |
| 5 | `cc_exec_track_b.md` | 轨道 B 执行文档（25 项） |
| 6 | `cc_exec_track_c.md` | 轨道 C 执行文档（21 项） |
| 7 | `cc_exec_track_d.md` | 轨道 D 执行文档（29 项） |
| 8 | `cc_exec_deep_learn_interactive.md` | 深度学习交互式触发 |
| 9 | `model_arsenal_activation.md` | 19 模型全面激活方案 |
| 10 | `max_subscription_optimization.md` | Max 会员能力最大化 |
| 11 | `cc_exec_demo_autonomous.md` | Demo 全自主闭环 V1-V4 |
| 12 | `cc_exec_learning_system.md` | 学习系统 W1-W7 |
| 13 | `cc_exec_self_healing.md` | 自愈系统 X1-X5 |
| 13 | `cc_exec_self_healing.md` | 自愈系统设计 X1-X5 |

---

## 阶段 3：放置文件（2 分钟）

全部放到 `.ai-state/` 目录下：

```powershell
$src = "$env:USERPROFILE\Downloads"
$dst = "D:\Users\uih00653\my_agent_company\pythonProject1\.ai-state"

Copy-Item "$src\FINAL_COMPLETE_GUIDE.md" "$dst\" -Force
Copy-Item "$src\improvement_backlog_complete.md" "$dst\" -Force
Copy-Item "$src\handoff_20260331.md" "$dst\" -Force
Copy-Item "$src\cc_exec_track_a.md" "$dst\" -Force
Copy-Item "$src\cc_exec_track_b.md" "$dst\" -Force
Copy-Item "$src\cc_exec_track_c.md" "$dst\" -Force
Copy-Item "$src\cc_exec_track_d.md" "$dst\" -Force
Copy-Item "$src\cc_exec_deep_learn_interactive.md" "$dst\" -Force
Copy-Item "$src\model_arsenal_activation.md" "$dst\" -Force
Copy-Item "$src\max_subscription_optimization.md" "$dst\" -Force
Copy-Item "$src\cc_exec_demo_autonomous.md" "$dst\" -Force
Copy-Item "$src\cc_exec_learning_system.md" "$dst\" -Force
Copy-Item "$src\cc_exec_self_healing.md" "$dst\" -Force
Copy-Item "$src\cc_exec_self_healing.md" "$dst\" -Force
```

---

## 阶段 4：提交到 Git（1 分钟）

```powershell
cd D:\Users\uih00653\my_agent_company\pythonProject1
git add .ai-state/
git commit -m "docs: add all execution documents, backlog, model activation, learning system, demo pipeline"
git push origin main
```

---

## 阶段 5：开 4 个 CC 窗口

打开 4 个独立的 PowerShell 窗口，每个先进入项目目录：

```powershell
cd D:\Users\uih00653\my_agent_company\pythonProject1
```

然后在每个窗口启动 CC 并粘贴对应指令。

---

### 窗口 1 — 轨道 A: 深度研究管道

```
读取以下文件：
1. .ai-state/cc_exec_track_a.md（执行文档，19 项）
2. .ai-state/model_arsenal_activation.md（模型分配方案）
3. .ai-state/cc_exec_learning_system.md（学习系统 W1-W3）
4. .ai-state/cc_exec_demo_autonomous.md（Demo 闭环 V1）

按 track_a 文档顺序执行全部 19 项，然后继续执行：
- 学习系统中的 W1（搜索策略学习）、W2（Agent prompt 自进化）、W3（模型效果学习）
- Demo 闭环中的 V1（Demo 信息自动补齐）

模型分配重点：
- Layer 1 搜索升级为四通道（o3 + doubao + grok-4 + gemini-deep-research）
- Layer 4 整合改用 gemini-2.5-pro（65K 上下文）
- Layer 5 Critic 增加 o3 交叉审查（双 Critic）
- 降级映射表和并发信号量按 model_arsenal_activation.md 更新
- 不要使用 Claude Opus 或 Claude Sonnet 模型

这条轨道只改 scripts/deep_research/ 目录（或 scripts/tonight_deep_research.py）。
不要动: text_router.py, knowledge_base.py, yaml/json 配置文件。

先做前置检查: ls scripts/deep_research/ 确认拆分是否完成。

每项改完后:
git add -A && git commit -m "描述" && git push origin main

如果 push 失败: git pull --rebase origin main && git push origin main

不要重启服务。
```

---

### 窗口 2 — 轨道 B: 飞书交互层

```
读取以下文件：
1. .ai-state/cc_exec_track_b.md（执行文档，25 项）
2. .ai-state/cc_exec_deep_learn_interactive.md（B-1 的详细实现）
3. .ai-state/model_arsenal_activation.md（模型分配方案）
4. .ai-state/cc_exec_demo_autonomous.md（Demo 闭环 V2-V4）
5. .ai-state/cc_exec_learning_system.md（学习系统 W4）

按 track_b 文档顺序执行全部 26 项（包含末尾的 X4+X5 自检指令和健康监控），然后继续执行：
- Demo 闭环中的 V2（生成中暂停等人确认）、V3（成品迭代修改）、V4（全流程编排器）
- 学习系统中的 W4（输出格式学习）

模型分配重点：
- 日常问答分 4 层路由: gemini-2.5-flash(1s) → gpt-5.3(3s) → gpt-5.4(10s) → o3(30s)
- 意图分类用 o3-mini
- 教练模式用 gpt-5.4
- 情绪感知用 o3-mini
- 不要使用 Claude Opus 或 Claude Sonnet 模型

这条轨道只改:
- scripts/feishu_handlers/text_router.py
- scripts/feishu_handlers/commands.py
- scripts/feishu_sdk_client.py

不要动: tonight_deep_research.py, deep_research/*.py, knowledge_base.py。

每项改完后:
git add -A && git commit -m "描述" && git push origin main

如果 push 失败: git pull --rebase origin main && git push origin main

不要重启服务。
```

---

### 窗口 3 — 轨道 C: 知识与数据层

```
读取以下文件：
1. .ai-state/cc_exec_track_c.md（执行文档，21 项）
2. .ai-state/model_arsenal_activation.md（模型分配和定价方案）
3. .ai-state/cc_exec_learning_system.md（学习系统 W5-W7）

按 track_c 文档顺序执行全部 21 项，然后继续执行：
- 学习系统中的 W5（PRD 生成学习）、W6（Critic 标准自进化）、W7（元学习自评）

重点：
- C-1 补充模型定价时包括所有 19 个模型（含 Grok $5.5/$27.5）
- C-19 KB 向量搜索需要先: pip install sentence-transformers --break-system-packages
- 不要使用 Claude Opus 或 Claude Sonnet 模型
- 如果某项涉及 text_router.py，跳过，由轨道 B 负责

这条轨道只改:
- src/tools/knowledge_base.py
- scripts/kb_governance.py
- scripts/auto_learn.py
- scripts/critic_calibration.py
- src/utils/token_usage_tracker.py
- .ai-state/ 下的 yaml/json 配置文件

不要动: text_router.py, tonight_deep_research.py, deep_research/*.py。

每项改完后:
git add -A && git commit -m "描述" && git push origin main

如果 push 失败: git pull --rebase origin main && git push origin main

不要重启服务。
```

---

### 窗口 4 — 轨道 D: 新模块（纯新建）

```
读取以下文件：
1. .ai-state/cc_exec_track_d.md（执行文档，29 项）
2. .ai-state/model_arsenal_activation.md（模型分配方案）
3. .ai-state/max_subscription_optimization.md（Max 会员能力方案）
4. .ai-state/cc_exec_self_healing.md（自愈系统设计）

按 track_d 文档顺序执行全部 29 项（D-1 到 D-29）。

重点：
- D-3 更新 CLAUDE.md 时只在末尾追加新章节，不改已有内容
- S8/S9（CC 调用 Claude）改为 Max 会员方案:
  用 subprocess.run(["claude", "-p", question, "--output-format", "text"]) 调用 CC CLI
  走 Max 订阅额度，不需要 API key
- 不要使用 Claude Opus 或 Claude Sonnet 模型（保留在 registry 但不在新代码中引用）
- critic_azure 角色改用 gpt-5.4 或 o3
- D-25 到 D-29 是自愈系统（X1-X5），参考 cc_exec_self_healing.md 中的详细设计
- D-28 在 feishu_sdk_client.py 启动逻辑中只追加一行线程启动，不改其他逻辑
- D-29 如果轨道 B 已完成则直接改 text_router.py 追加"自检"指令，否则只创建 handler 模块
- 全部完成后，作为最后一步，运行 python scripts/self_heal.py 触发首次自检
  首次自检会发现一些问题（因为其他轨道可能还没完成），这是正常的

这条轨道主要创建新文件。D-28 和 D-29 各追加一行调用到现有文件。
允许: 新建 scripts/*.py, 新建 .ai-state/ 下目录和配置, CLAUDE.md 末尾追加。

每项改完后:
git add -A && git commit -m "描述" && git push origin main

如果 push 失败: git pull --rebase origin main && git push origin main

不要重启服务。
```

---

## 阶段 6：等待完成（约 10 小时）

4 个窗口并行工作。你可以随时查看进度。

**如果某个窗口卡住了：**
- git 冲突 → `git pull --rebase origin main && git push origin main`
- 代码报错 → 让 CC 自己修复
- 理解不了文档 → 让 CC 跳过该项继续下一项

---

## 阶段 7：验证（10 分钟）

所有窗口完成后：

```
git log --oneline -100
```

然后运行 import 验证：

```powershell
python -c "
import sys; sys.path.insert(0, '.')
print('=== Core ===')
for m in ['scripts.tonight_deep_research', 'scripts.feishu_handlers.text_router', 'src.tools.knowledge_base']:
    try: __import__(m); print(f'  {m.split(chr(46))[-1]} OK')
    except Exception as e: print(f'  {m.split(chr(46))[-1]} FAIL: {e}')
print('=== New Modules ===')
for m in ['handoff_processor','system_log_generator','work_memory','roi_tracker','decision_logger','trust_tracker','brand_layer','collaboration','insight_engine','kb_visualizer','user_voice','crm_lite','demo_generator','visual_report_generator','user_profile_learner','guardrail_engine','load_manager','multimodal_intake','test_suite','auto_fixer','self_heal']:
    try: __import__(f'scripts.{m}'); print(f'  {m} OK')
    except Exception as e: print(f'  {m} FAIL: {e}')
print('=== DONE ===')
"
```

然后触发首次自愈循环——让系统自己检查并修复剩余问题：

```powershell
python scripts/self_heal.py
```

这一步会自动跑全部测试，发现问题会自动修复。你只需要看最终输出。

---

## 阶段 8：重启飞书并测试

```powershell
python scripts/feishu_sdk_client.py
```

飞书测试指令：

| 指令 | 预期 |
|------|------|
| `帮助` | 返回所有可用指令 |
| `状态` | 系统仪表盘 |
| `早报` | 每日决策摘要 |
| `深度学习` | 先问"跑几个小时？" |
| `决策简报: v1_display` | HUD 方案决策简报 |
| `产品简介` | One-Pager |
| `信任度` | 各领域信任指数 |
| `待办` | 行动清单 |
| `教练模式` | 苏格拉底式提问 |
| `生成 HUD Demo` | 全自主 Demo 流水线 |

---

## 阶段 9：下次找 Claude 时

在 Project "智能骑行头盔 R&D" 里开新对话：

```
看一下 agent-company 的最新代码和 .ai-state/system_log_latest.md
```

---

## 完成后的系统全貌

| 维度 | 能力 |
|------|------|
| 搜索 | 四通道并行: o3 + doubao + Grok + Gemini Deep |
| 分析 | 5 Agent + o3 验证 + Qwen 交叉 + 辩论机制 |
| 整合 | Gemini 2.5 Pro (65K) + DeepSeek R1 推理验证 |
| 审查 | 双 Critic (Gemini + o3) + 校准自进化 |
| 问答 | 4 层路由: Flash → 5.3 → 5.4 → o3 |
| 飞书 | 30+ 指令 + 自然语言意图理解 |
| Demo | 全自主闭环: 补信息→问偏好→生成→调试→迭代 |
| 自主 | 好奇心/护栏/反脆弱/保鲜/免疫/代理 |
| 学习 | 7 维自进化: 搜索/Agent/模型/输出/PRD/Critic/元学习 |
| 团队 | 权限/审计/协作/引导/负载/品牌 |
| 自愈 | 自动测试 + 自动修复 + 6h 定时健康检查 |
| 模型 | 19 个全部激活，0 个吃灰 |
