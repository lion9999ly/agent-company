# Claude Chat Inbox
> CC 每次任务完成后将摘要追加到此文件，Claude Chat 通过 raw URL fetch 审查。

---

## [交付] HUD Demo - 2026-04-10 16:44

- **结果**：通过
- **关键数据**：
  - 测试: 85/85 PASS
  - 文件: 26KB, 1045 行
  - 截图: 15 张
  - 模块: 5 个（骨架/状态机/渲染器/剧本/控制）
- **产出文件**：
  - GitHub Issue #47: https://github.com/lion9999ly/agent-company/issues/47
  - HTML: demo_outputs/hud_demo_final.html
  - 截图: demo_outputs/screenshots/
- **待决问题**：无

---

## [修复] #7 最终修复 - 步骤5-6 try-except + 全局UTF-8编码 - 2026-04-10 06:15

- **结果**：通过
- **关键数据**：
  - P0：步骤 5-6 加 try-except，异常不中断后续步骤
  - 全局：sys.stdout/stderr.reconfigure(encoding='utf-8') 根源解决 GBK
- **产出文件**：
  - GitHub Issue #44: https://github.com/lion9999ly/agent-company/issues/44
  - Git commit: 464eaae
- **待决问题**：无（修复完成）

---

## [排查] 圆桌后处理链路全面排查 - 2026-04-10 05:55

- **结果**：完成（未修代码，仅报告）
- **关键发现**：
  - stdout encoding: gbk（Windows 根因）
  - subprocess 无 encoding: 50+ 处
  - 步骤 5-6 缺 try-except 保护
  - 修复后三通道测试通过（云文档/Issue/飞书）
- **产出文件**：
  - GitHub Issue #43: https://github.com/lion9999ly/agent-company/issues/43
  - 测试 Issue #42: https://github.com/lion9999ly/agent-company/issues/42
  - 测试云文档: https://www.feishu.cn/docx/IuiqdjTDroxpyqxVcMBc5sJLnyh
- **遗留问题**：
  - P0: 步骤 5-6 缺 try-except
  - P1: feishu_output.py subprocess 无 encoding

---

## [修复] 第六轮 - GBK编码修复 - 2026-04-10 00:15

- **结果**：通过
- **关键数据**：
  - 移除 _notify 中的 emoji（云文档、Issue）
  - subprocess 调用加 encoding='utf-8', errors='ignore'
  - 添加缺失的 PROJECT_ROOT 定义和 load_dotenv
  - GITHUB_TOKEN: 直接 os.environ NOT SET，load_dotenv 后 SET
- **产出文件**：
  - GitHub Issue #41: https://github.com/lion9999ly/agent-company/issues/41
  - Git commit: 8c9755a
- **待决问题**：无

---

## [修复] 第五轮 - 云文档路径修复 + TaskSpec诊断 + Issue改requests - 2026-04-09 23:15

- **结果**：通过
- **关键数据**：
  - #1 云文档：lark-cli 要求相对路径，临时文件改工作目录
  - #2 TaskSpec：添加 feishu 参数诊断日志
  - #3 Issue：gh CLI 改 requests
- **产出文件**：
  - GitHub Issue #40: https://github.com/lion9999ly/agent-company/issues/40
  - Git commit: 9c85cf8
  - 验证云文档: https://www.feishu.cn/docx/AFTrdDiVpog6rhxapGHccS0Ongh
- **待决问题**：下次圆桌运行观察 TaskSpec feishu 参数是否为 None

---

## [修复] 第四轮 - bot自回复过滤（核心问题） - 2026-04-09 17:25

- **结果**：通过
- **关键数据**：
  - 新增 `SYSTEM_PREFIXES` 内容过滤，阻断系统通知消息的循环处理
  - 删除 `_review_issues` 死代码（第三轮遗留）
- **产出文件**：
  - GitHub Issue #39: https://github.com/lion9999ly/agent-company/issues/39
  - Git commit: d3590d7
- **待决问题**：无

---

## [修复] 第三轮圆桌Bug修复 - 2026-04-09 17:10

- **结果**：通过（但有架构问题）
- **关键数据**：
  - #2 TaskSpec等待：已添加到 `__init__.py`，但 `pre_check_task_spec` 不设置 `_review_issues`
  - #1/#9 审查异常保护：try-except 已添加
  - Bot诊断：sender_id 日志已添加
- **产出文件**：
  - GitHub Issue #38: https://github.com/lion9999ly/agent-company/issues/38
  - Git commit: e60d165
- **待决问题**：
  - `pre_check_task_spec` 不会设置 `task._review_issues`，需要后续修改
  - 现有代码有双重等待逻辑（`roundtable.py` + `__init__.py`）

---

## [修复] 第二轮圆桌Bug修复 - 2026-04-09 15:30

- **结果**：通过
- **关键数据**：
  - #1 云文档：添加详细日志定位根因
  - #2 TaskSpec确认：新增 handler + sender 过滤
  - #9 Issue创建：手动用 requests（gh CLI 不可用）
- **产出文件**：
  - GitHub Issue #36: https://github.com/lion9999ly/agent-company/issues/36
  - Git commit: c664ccd
- **待决问题**：下次圆桌运行验证 #1/#2

---

## [修复] 圆桌8项Bug批量修复 - 2026-04-09 14:20

- **结果**：通过
- **关键数据**：
  - P0 修复：2 项（云文档生成、TaskSpec确认）
  - P1 修复：4 项（文件命名、commit防护、日志）
  - P2 修复：1 项（SDK进程锁）
  - 跳过：1 项（#7 HTML产出质量待观察）
- **产出文件**：
  - GitHub Issue #35: https://github.com/lion9999ly/agent-company/issues/35
  - Git commit: e64bddf
- **待决问题**：无

---

## [圆桌] HUDDemo生成 - 2026-04-09 13:04

- **结果**：失败（P0 反弹 5→4→6）
- **关键数据**：
  - 迭代轮次：3 轮
  - P0 数量：5 → 4 → 6（未收敛）
  - Critic 评级：Passed: False
- **产出文件**：
  - `roundtable_runs/HUDDemo生成_20260409_130440/input_task_spec.json`
  - `roundtable_runs/HUDDemo生成_20260409_130440/phase2_proposal_full.md`
  - `roundtable_runs/HUDDemo生成_20260409_130440/phase4_critic_final.md`
  - `roundtable_runs/HUDDemo生成_20260409_130440/convergence_trace.jsonl`
- **待决问题**：
  - P0-1: 四角布局与状态枚举需对齐验收标准
  - P0-2: 优先级抢占规则缺失，ADAS 无法抢占语音
  - P0-3: 核心演示组件设计缺失（黑背景、沙盒面板）
  - P0-4: 置信度标注不诚实
  - P1-1: 单绿模式对比度保障策略缺失
  - P1-2: 时间轴拖拽与状态机耦合未明确

---

## [修复] Day 17 系统诊断 - 2026-04-09 12:00

- **结果**：通过（21/21 断点修复完成）
- **关键数据**：
  - P0 修复：2 项
  - P1 修复：9 项
  - P2 修复：10 项
  - Git 提交：4 commits
- **产出文件**：
  - GitHub Issue #33: https://github.com/lion9999ly/agent-company/issues/33
- **待决问题**：无
---

## [圆桌] HUD Demo 生成 - 2026-04-09 22:36

- **结果**: 通过
- **关键数据**: 迭代 2 轮
- **产出文件**: `demo_outputs\hud_demo_roundtable_20260409_223626.html`

---

## [研究] HUD三条光学路径参数补全 (v2) - 2026-04-11 16:25

- **结果**：通过
- **工具链**：Tavily API + requests + model_gateway (正确方式)
- **关键数据**：
  - SeeYA SY049: 1920x1080, 3000nits, 50000:1对比度
  - JBD Hummingbird: 640x480, 200万nits绿光, 30°FOV
  - JBD Phoenix: 200万nits全彩, 6000nits到眼 (2024最新)
  - 树脂波导: FOV 20-40°, 透过率80-85%
- **产出文件**：
  - GitHub Issue #53: https://github.com/lion9999ly/agent-company/issues/53
  - 参数文档: demo_outputs/specs/optical_constraints.md (覆盖旧版)
  - 原始数据: .ai-state/research_raw_data.json
- **数据缺口**：虚像距离、整机功耗、体积重量需商务接触

---

## [修复] 深度研究管道搜索层重构 - 2026-04-11 17:30

- **结果**：通过
- **关键数据**：
  - 搜索层重构：Tavily主力(快) + o3-deep补充(慢) + doubao中文
  - L1搜索：5/5有效 (Tavily: 2807-3812字/查询)
  - L2提炼：5/5成功
  - L3 Agent：CTO/CMO/CDO全部成功
  - Critic：P0:1, P1:2, P2:1
  - Final Synthesis：5190字
  - KB提取：3条知识
  - 总耗时：953.6秒(~16分钟)
- **产出文件**：
  - GitHub Issue #55: https://github.com/lion9999ly/agent-company/issues/55
  - 参数文档: demo_outputs/specs/optical_constraints.md (追加)
  - 测试报告: .ai-state/reports/test_seeya_20260411_1718.md
- **修改文件**：
  - scripts/deep_research/pipeline.py (搜索层重构)
  - scripts/deep_research/critic.py (gateway导入)
  - src/utils/progress_heartbeat.py (UTF-8编码)
- **待决问题**：完整8任务测试在后台运行中

---

## [修复] 深度研究管道8任务完整测试 - 2026-04-11 19:55

- **结果**：通过 (8/8)
- **关键数据**：
  - 总耗时：154.5分钟
  - 成功任务：8/8 (100%)
  - 新生成工具：5个 (光学仿真、成本估算等)
  - KB提取：多条知识
- **产出文件**：
  - GitHub Issue #55 Comment: https://github.com/lion9999ly/agent-company/issues/55#issuecomment-4229376170
  - 参数文档: demo_outputs/specs/optical_constraints.md (完整报告)
  - 各任务报告: .ai-state/reports/*.md
- **关键结论**：
  - 方案A（激进全彩）：市场吸引力高但体验风险极大
  - 方案B（稳健单色）：体验闭环、成本可控、推荐V1
  - 方案C（平台演进）：V1稳健+V2预研策略
- **P0级缺口**：供应商振动台实测数据缺失

---

## [诊断] MetaBot Peer 路由机制 - 2026-04-12 08:38

- **结果**：完成（发现根本原因，未改代码）
- **问题描述**：飞书发 "agent-service xxx" 未路由到 Peer，被 CC 直接处理
- **关键发现**：
  - **根本原因**：飞书消息路径完全不经过 peer 转发逻辑
  - MetaBot peer 功能是 **API 网关设计**，不是**消息路由设计**
  - `message-bridge.ts:handleMessage()` → `executeQuery()` → CC，无 peerManager 调用
  - Peer 转发仅对 `POST /api/talk` API 调用有效
- **API 层 peer 转发触发条件**：
  - 方式1：Qualified Name `peerName/botName`（如 `agent-company/agent-service`）
  - 方式2：本地 registry 查不到 botName → 自动查 peer fallback
- **测试验证**：
  - `GET /api/peers`: `{"peers":[{"name":"agent-company","url":"http://localhost:9300","healthy":true,"botCount":1}]}`
  - `GET http://localhost:9300/api/health`: `{"status":"healthy","kb_count":3502}`
  - Python 请求 `POST /api/talk` with `botName="agent-service"` 成功转发
- **可行方案**：
  - **方案A（推荐）**：创建 Skill 文件 `.claude/skills/roundtable.md`，飞书发 `/roundtable` → CC 执行 → 调用 Python 服务
  - **方案B**：CC 内部加路由逻辑，判断消息前缀后调用 Python 服务 API
  - **方案C**：改 MetaBot 源码（用户禁止）
- **产出文件**：
  - Python Peer 服务: `scripts/api_server.py` (端口 9300)
  - MetaBot 配置: `~/metabot/bots.json` (peers 配置已添加)
- **下一步**：待确认方案后实现

---

## [实现] Python 服务路由规则 - 2026-04-12 08:42

- **结果**：通过
- **关键数据**：
  - CLAUDE.md 新增路由规则段落（VERSION: 20260412.3）
  - Python 服务新增 3 个端点：POST /roundtable, /research, /agent
  - 端点验证：全部返回 200
- **路由规则**：
  - `/roundtable <主题>` → POST localhost:9300/roundtable
  - `/research <查询>` → POST localhost:9300/research
  - `/agent <指令>` → POST localhost:9300/agent
- **产出文件**：
  - CLAUDE.md (v20260412.3)
  - scripts/api_server.py (新增 3 端点)
- **端点测试结果**：
  - Health: 200 ✓
  - Roundtable: 200 ✓
  - Research: 200 ✓
  - Agent: 200 ✓
- **待决问题**：端点为 placeholder，实际功能待后续集成圆桌/深度研究脚本

---

## [验证] MetaBot 重启测试 - 2026-04-12 08:44

- **结果**：通过
- **关键数据**：
  - MetaBot 重启后 2 秒恢复
  - Peer 发现正常：healthy=true, botCount=1
  - 端点测试全部 200
- **重启验证**：
  - 关闭 PID 37172 → 重启 → 2秒恢复
  - MetaBot health: `{"status":"ok", "bots":1, "peerBots":1, "peersHealthy":1}`
  - Python health: `{"status":"healthy", "kb_count":3502}`
  - Roundtable test: 200 ✓
- **Windows 任务计划程序**：
  - MetaBot_AutoStart: ✓ 已配置（登录时触发）
  - 命令: `bash.exe -l -c "source ~/metabot/start_metabot.sh"`
- **待办**：
  - Python 服务（api_server.py）无自启配置
  - 需添加 Windows 任务计划程序任务 Python_Peer_AutoStart

---

## [配置] Python 服务开机自启 - 2026-04-12 08:50

- **结果**：通过
- **关键数据**：
  - 创建启动脚本: `~/metabot/start_python_peer.bat`
  - 任务计划: `Python_Peer_AutoStart`（登录时触发）
  - 运行级别: highest（最高权限）
- **产出文件**：
  - `C:\Users\uih00653\metabot\start_python_peer.bat`
- **验证结果**：
  - 任务名: `\Python_Peer_AutoStart`
  - 触发器: 登录时
  - 命令: `start_python_peer.bat`
  - 状态: 已启用
- **自启配置完成**：
  - MetaBot_AutoStart ✓（登录时）
  - Python_Peer_AutoStart ✓（登录时）

---

## [配置] 自启动改为后台无窗口运行 - 2026-04-12 09:30

- **结果**：部分完成（VBS验证通过，scheduled tasks需管理员重建）
- **关键数据**：
  - 创建 VBS 文件：`start_metabot_hidden.vbs`, `start_python_peer_hidden.vbs`
  - 创建 XML 配置：`MetaBot_AutoStart.xml`, `Python_Peer_AutoStart.xml`
  - VBS 启动测试：无窗口弹出，服务正常运行
  - 端口验证：9100 (MetaBot PID 22700), 9300 (Python Peer PID 15800) 已监听
- **产出文件**：
  - `C:\Users\uih00653\metabot\start_metabot_hidden.vbs`
  - `C:\Users\uih00653\metabot\start_python_peer_hidden.vbs`
  - `C:\Users\uih00653\metabot\MetaBot_AutoStart.xml`
  - `C:\Users\uih00653\metabot\Python_Peer_AutoStart.xml`
  - `C:\Users\uih00653\metabot\rebuild_tasks.ps1`
  - `C:\Users\uih00653\metabot\import_tasks.bat`
- **待办**：
  - 需以管理员权限运行 `import_tasks.bat` 重建 scheduled tasks
  - 双击 `C:\Users\uih00653\metabot\import_tasks.bat` 即可

---

## [创建] agentskills.io 标准 Skill 系统 - 2026-04-12 10:30

- **结果**：通过
- **关键数据**：
  - 创建 5 个 Skill 目录：roundtable, deep-research, hud-demo, optical-lookup, feishu-output
  - 每个 SKILL.md 包含 YAML frontmatter + 适用场景 + 执行步骤 + 已知坑 + 验收标准
  - 正文控制在 3000 tokens 以内
- **产出文件**：
  - `skills/roundtable/SKILL.md` - 圆桌讨论执行流程
  - `skills/deep-research/SKILL.md` - 深度研究五层管道
  - `skills/hud-demo/SKILL.md` - HUD Demo 生成规范
  - `skills/optical-lookup/SKILL.md` - 光学参数查询与约束
  - `skills/feishu-output/SKILL.md` - 飞书输出格式规范
- **目录结构验证**：
  - `ls skills/*/SKILL.md` 返回 5 个文件
- **待决问题**：无

---

## [轮子检查] LiteLLM (BerriAI/litellm) - 2026-04-12 10:45

- **对标组件**：`model_gateway/` 目录 + `model_registry.yaml`
- **Stars 数**：42,970
- **最近更新**：2026-04-12（今日活跃）
- **功能覆盖度**：95%

### 关键能力验证

| 能力 | 我们需求 | LiteLLM 支持 | 状态 |
|------|----------|--------------|------|
| Azure OpenAI | GPT-5.4, o3-deep-research | ✅ `litellm/llms/azure/` 完整目录 | 完全覆盖 |
| Volcengine | doubao, DeepSeek-R1, GLM-4 | ✅ endpoint `ark.cn-beijing.volces.com` | 完全覆盖 |
| Gemini | Gemini 3.1 Pro, 2.5 Flash | ✅ `litellm/llms/gemini/` 完整目录 | 完全覆盖 |
| Fallback 路由 | 禁用模型降级链 | ✅ `max_fallbacks`, `default_fallbacks`, `context_window_fallbacks`, `content_policy_fallbacks` | 完全覆盖 |
| 流式输出 | 流式响应 | ✅ `streaming` 支持 | 完全覆盖 |
| Agent 调用 | A2A Protocol | ✅ `litellm/a2a_protocol/` | 超出需求 |

### Windows 兼容性
✅ 完全兼容 — Python 项目，跨平台

### 接入改动量：**中**

1. **需替换**：`src/utils/model_gateway/` 整个目录（6 文件）
2. **需适配**：`model_registry.yaml` → LiteLLM RouterConfig 格式
3. **需验证**：14+ 模型路由正确性（已确认 Azure/Volcengine/Gemini 均有独立 provider）

### 结论：**替换**（高优先级）

- LiteLLM 提供 100+ LLM 统一接口，远超我们自建能力
- Fallback 系统比我们的 PEER_MODELS/FALLBACK_MAP 更完善
- 可减少维护负担，专注业务逻辑

### 接入建议

```yaml
# LiteLLM RouterConfig 示例（适配我们的配置）
model_list:
  - model_name: "gpt_5_4"
    litellm_params:
      model: "azure/gpt-5.4"
      api_key: "${AZURE_OPENAI_API_KEY}"
      api_base: "${AZURE_OPENAI_ENDPOINT}"
  - model_name: "doubao_seed_pro"
    litellm_params:
      model: "volcengine/doubao-seed-2-0-pro-260215"
      api_key: "${ARK_API_KEY}"
      api_base: "https://ark.cn-beijing.volces.com/api/v3"

fallbacks:
  - {"gpt_5_4": ["doubao_seed_pro", "gemini_2_5_pro"]}
  - {"o3_deep_research": ["gpt_5_4", "doubao_seed_pro"]}
```

---

## [轮子检查] LangChain open_deep_research - 2026-04-12 10:45

- **对标组件**：`scripts/deep_research/` 管道
- **Stars 数**：11,078
- **最近更新**：2026-04-12（今日活跃）
- **功能覆盖度**：70%

### 关键能力验证

| 能力 | 我们需求 | open_deep_research 支持 | 状态 |
|------|----------|------------------------|------|
| Tavily 搜索 | 英文搜索主力 | ✅ SearchAPI.TAVILY 默认 | 完全覆盖 |
| 多模型摘要 | L1-L5 分层模型 | ✅ Summarization/Research/Compression/Final 四角色 | 覆盖 70% |
| 结构化输出 | Critic 评分 | ✅ 需要 model 支持 structured outputs | 覆盖 |
| 中文查询 | doubao 中文优先 | ⚠️ 无内置 doubao SearchRouter | 需适配 |
| MCP 支持 | 工具扩展 | ✅ MCPConfig + tools 字段 | 完全覆盖 |
| 并发控制 | Provider Semaphore | ✅ max_concurrent_research_units | 部分覆盖 |

### Windows 兼容性
✅ 完全兼容 — README 有 Windows 激活命令 `.venv\Scripts\activate`

### 接入改动量：**大**

1. **架构差异**：LangGraph 架构 vs 我们的五层管道
2. **SearchRouter 缺失**：需适配 doubao 中文优先逻辑
3. **降级链不同**：需合并我们的 FALLBACK_MAP
4. **需集成**：替换 `tonight_deep_research.py` 主流程

### 结论：**暂缓**

- 覆盖度仅 70%，核心 SearchRouter 需大改
- 我们的五层管道有 doubao 中文增强，open_deep_research 缺失
- 可作为参考，但不建议直接替换
- 建议：借鉴其 LangGraph 架构思路，保留我们的 SearchRouter

### 可借鉴点

- LangGraph Studio UI（可视化调试）
- Deep Research Bench 评估体系（50 中文 + 50 英文任务）
- MCP server 集成模式

---

## [轮子检查] OpenSpace (HKUDS/OpenSpace) - 2026-04-12 10:45

- **对标组件**：无现有对标（新增能力）
- **Stars 数**：4,996
- **最近更新**：2026-04-12（今日活跃）
- **功能覆盖度**：80%（skill 自进化能力）

### 关键能力验证

| 能力 | 我们需求 | OpenSpace 支持 | 状态 |
|------|----------|---------------|------|
| MCP Server 接入 CC | 新增能力 | ✅ `openspace/mcp_server.py` SSE + HTTP 模式 | 完全覆盖 |
| Skill 自进化 | 元能力层目标 | ✅ `skill_engine/evolver.py` FIX/DERIVED/CAPTURED | 完全覆盖 |
| Skill Registry | 能力注册表 | ✅ `skill_engine/registry.py` + `store.py` | 完全覆盖 |
| Execution Analyzer | 任务分析 | ✅ `skill_engine/analyzer.py` | 完全覆盖 |
| Windows 兼容 | Windows 平台 | ✅ pyproject.toml 有 `pywinauto`, `pywin32` 依赖 | 完全覆盖 |

### Windows 兼容性
✅ 完全兼容 — 有 Windows optional dependencies

### 接入改动量：**中**

1. **无需替换**：现有组件不受影响
2. **新增接入**：作为 MCP server 接入 Claude Code
3. **配置工作**：启动 SSE 模式，配置 CC 的 MCP servers

### 结论：**替换**（作为新增能力接入）

- OpenSpace 提供我们 `meta_capability.py` 缺失的 skill 自进化闭环
- EvolutionType 三种模式：FIX（修复）、DERIVED（增强）、CAPTURED（捕获）
- SkillLineage 版本 DAG 模型，与我们质量控制需求匹配
- 不替换现有组件，而是 **并行接入**

### 接入建议

```bash
# 启动 OpenSpace MCP server（SSE 模式）
python -m openspace.mcp_server --transport sse --port 8080

# CC settings.json 添加 MCP server
{
  "mcpServers": {
    "openspace": {
      "url": "http://localhost:8080/sse"
    }
  }
}
```

### 依赖关系注意

- OpenSpace 本身依赖 `litellm>=1.70.0`
- 若接入 LiteLLM 作为 model_gateway，形成依赖链：
  - CC → OpenSpace MCP → LiteLLM → 各 provider

---

## [深度评估] open_deep_research 可扩展性分析 - 2026-04-12 11:15

### 1. 搜索层架构分析

#### 核心文件
- `src/open_deep_research/configuration.py` - SearchAPI Enum 定义
- `src/open_deep_research/utils.py` - get_search_tool(), get_all_tools()

#### SearchAPI 定义（硬编码）
```python
class SearchAPI(Enum):
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    TAVILY = "tavily"
    NONE = "none"
```

#### get_search_tool() 实现（硬编码路由）
```python
async def get_search_tool(search_api: SearchAPI):
    if search_api == SearchAPI.ANTHROPIC:
        return [{"type": "web_search_20250305", "name": "web_search"}]
    elif search_api == SearchAPI.OPENAI:
        return [{"type": "web_search_preview"}]
    elif search_api == SearchAPI.TAVILY:
        search_tool = tavily_search  # @tool decorated function
        return [search_tool]
    elif search_api == SearchAPI.NONE:
        return []
```

#### 可插拔性评估：**不可插拔**

| 方面 | 分析 |
|------|------|
| Enum 扩展 | ❌ 需修改 SearchAPI Enum（核心文件） |
| 工具注册 | ❌ 需修改 get_search_tool() 函数体 |
| MCP 扩展 | ✅ 可通过 MCPConfig 新增外部工具（不改核心） |

#### 新增 doubao 中文搜索的工作量

**方案A：修改核心代码（不推荐）**
```python
# configuration.py - 新增 Enum 值
class SearchAPI(Enum):
    DOUBAO = "doubao"  # 新增

# utils.py - 新增分支
elif search_api == SearchAPI.DOUBAO:
    doubao_tool = doubao_search  # 需实现 @tool 函数
    return [doubao_tool]
```

**工作量：中（2-8h）** - 需实现 doubao_search @tool 函数 + 修改2个核心文件

**方案B：通过 MCP 接入 doubao（推荐）**
```yaml
mcp_config:
  url: "http://localhost:9300/mcp"  # 我们的 Python 服务
  tools: ["doubao_search"]
```

**工作量：小（<2h）** - 仅配置 MCP endpoint

---

### 2. 模型层分析

#### 核心调用方式
```python
from langchain.chat_models import init_chat_model

configurable_model = init_chat_model(
    configurable_fields=("model", "max_tokens", "api_key"),
)

# 使用时
model = configurable_model.with_config({
    "model": configurable.research_model,  # "openai:gpt-4.1" 格式
    "api_key": get_api_key_for_model(model_name, config),
})
```

#### model 字符串格式
```
"openai:gpt-4.1-mini"
"anthropic:claude-sonnet-4"
"google:gemini-2.5-flash"
```

#### LiteLLM 兼容性：**需要适配层**

| 问题 | 分析 |
|------|------|
| 格式差异 | LiteLLM 使用 `azure/gpt-5.4`，LangChain 使用 `openai:gpt-4.1` |
| init_chat_model | 不支持 LiteLLM provider 名称 |
| 解决方案 | 写一个 LiteLLM → LangChain wrapper |

#### LiteLLM wrapper 实现思路
```python
from litellm import completion
from langchain_core.language_models import BaseChatModel

class LiteLLMChatModel(BaseChatModel):
    def _generate(self, messages, ...):
        response = completion(model=self.model, messages=messages)
        return AIMessage(content=response.choices[0].message.content)
```

**工作量：中（2-8h）** - wrapper + 测试

---

### 3. 输出格式分析

#### open_deep_research 输出
```python
# AgentState 定义
class AgentState(MessagesState):
    final_report: str  # markdown 格式字符串
    notes: list[str]   # 研究笔记列表
```

#### final_report_generation 输出
```python
return {
    "final_report": final_report.content,  # AIMessage.content
    "messages": [final_report],
}
```

#### KB 入库能力：**缺失**

| 方面 | open_deep_research | 我们的 pipeline.py |
|------|-------------------|-------------------|
| KB 入库 | ❌ 无 | ✅ add_knowledge(), add_report() |
| 结构化提取 | ❌ 无 | ✅ extract_structured_data() |
| domain/tags | ❌ 无 | ✅ domain, tags, confidence |

#### 对接我们的 KB 流程

**方案：后处理 hook**
```python
# 在 final_report_generation 后新增节点
async def kb_extraction_node(state: AgentState, config):
    report = state["final_report"]
    # 调用我们的 KB 提取逻辑
    entries = extract_knowledge_from_report(report)
    for entry in entries:
        add_knowledge(**entry)
    return state
```

**工作量：中（2-8h）** - 新增节点 + 提取逻辑迁移

---

### 4. 我们独有能力补齐工作量

| 能力 | open_deep_research 状态 | 补齐方案 | 工作量 |
|------|------------------------|----------|--------|
| doubao 中文搜索 | ❌ 硬编码 Enum | MCP 接入 | **小**（<2h） |
| KB 提取入库 | ❌ 无此功能 | 后处理节点 | **中**（2-8h） |
| SearchRouter 分流 | ❌ 无此设计 | 保留自建 SearchRouter | **大**（>8h） |
| 多模型摘要 | ✅ 已有（4角色） | 直接用 | **无** |
| 五层管道 | ⚠️ 架构不同（LangGraph） | 重构适配 | **大**（>8h） |
| Agent 辩论 | ❌ 无此功能 | 新增节点 | **中**（2-8h） |
| Critic P0/P1/P2 | ⚠️ 有评审但无分级 | 修改 prompts | **中**（2-8h） |

#### 总补齐工作量：**大（>16h）**

---

### 5. Fork vs 自建长期成本对比

| 维度 | Fork open_deep_research | 保留自建 |
|------|------------------------|----------|
| **功能更新** | ✅ 上游持续迭代（LangChain 官方维护） | ❌ 需自研 |
| **Bug 修复** | ✅ 上游社区修复 | ❌ 需自修 |
| **Merge 成本** | ❌ 每次上游更新需 Merge 冲突 | ✅ 无 Merge |
| **架构适配** | ❌ 需适配 LangGraph 架构 | ✅ 完全控制 |
| **搜索层扩展** | ❌ 需改核心代码或 MCP | ✅ SearchRouter 可插拔 |
| **KB 入库** | ❌ 需后处理 hook | ✅ 已有完善流程 |
| **模型扩展** | ⚠️ 需 LiteLLM wrapper | ✅ 已有 model_gateway |

#### 关键决策因素

1. **搜索层差异是致命伤**
   - open_deep_research 搜索层**硬编码**
   - 我们的 SearchRouter 是**可插拔设计**
   - doubao 中文优先是我们核心能力，fork 后需大改

2. **LangGraph 架构**
   - open_deep_research 是 LangGraph 状态机
   - 我们的五层管道是 ThreadPoolExecutor 并发
   - 架构迁移成本 >16h

3. **上游同步成本**
   - LangChain 官方频繁更新
   - 每 2-3 周 Merge 冲突处理
   - 长期成本 > 自建维护

#### 结论：**保留自建，借鉴架构**

| 推荐方案 | 原因 |
|----------|------|
| ✅ 保留自建 | 搜索层 + KB 入库 + Agent 辩论都是核心能力 |
| ⚠️ 借鉴架构 | LangGraph 状态机、MCP 工具扩展 |
| ❌ 不 Fork | 搜索层硬编码 + Merge 成本 > 自建成本 |

#### 借鉴建议

```python
# 1. 借鉴 LangGraph 状态机设计
class ResearchState(TypedDict):
    messages: list[Message]
    notes: Annotated[list[str], operator.add]
    final_report: str

# 2. 借鉴 MCP 工具扩展
mcp_config = {
    "url": "http://localhost:9300/mcp",
    "tools": ["doubao_search", "kb_extract"]
}

# 3. 保留我们的核心优势
- SearchRouter 类（可插拔搜索）
- KB 入库流程（add_knowledge）
- Agent 辩论机制
```

---
