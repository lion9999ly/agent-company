# Handover Day 16 Session 2 → Session 3

## 一、本会话完成的所有改动

### 1. tonight_deep_research.py 拆分重构 ✅
原 2387 行单文件拆分为 `scripts/deep_research/` 包（10 个模块）：

```
scripts/deep_research/
├── __init__.py          # 公开接口
├── models.py            # 模型路由 + 降级链 + 信号量 + disable_model 机制
├── extraction.py        # L2 结构化提取 + JSON 修复 + prompt 长度约束
├── pipeline.py          # 核心管道 deep_research_one + 深钻 + Agent 辩论
├── critic.py            # L5 Critic 双审查 + 校准 + P0 回应
├── learning.py          # W1-W3 学习 + A3-A18 知识功能 + 压力测试 + 沙盘
├── night_watch.py       # 守夜诊断（GLM-5 优先，CDP 仅战略问题）
├── runner.py            # 调度器 + 任务池 + 自主发现 + CLI
├── health_monitor.py    # 运行健康巡检（规则止血 + LLM 追因）
└── post_learning_review.py  # 认知闭环（决策树更新 + 任务追加）
```

原 `tonight_deep_research.py` 改为 shim 重导出，向后兼容。
备份：`scripts/tonight_deep_research_backup_20260406.py`

### 2. model_gateway.py 拆分重构 ✅
原 1514 行单文件拆分为 `src/utils/model_gateway/` 包（7 个模块）：

```
src/utils/model_gateway/
├── __init__.py          # ModelGateway 类 + call() 路由 + 便捷函数
├── config.py            # ModelConfig, TaskType, TIMEOUT_BY_TASK, record_usage
└── providers/
    ├── __init__.py
    ├── gemini.py        # text + vision + audio + image_gen
    ├── azure_openai.py  # chat + responses (o3-deep-research)
    ├── volcengine.py    # doubao/deepseek/glm text + seedream image_gen
    └── others.py        # qwen + zhipu + deepseek 直连
```

**关键修复**：`call()` 方法现在正确路由图像生成模型——检测 `image_generation in capabilities` 时调用 `call_image()` 而不是 `call_gemini()`。
备份：`src/utils/model_gateway_backup_20260406.py`

### 3. Bug 修复 ✅
- **P0 L2 JSON 截断**：extraction.py 加了 `_try_repair_json()` + prompt 约束（输出≤800字，输入 3000→减少）
- **P1 Pre-flight 覆盖不全**：扩大到检查四通道搜索全部模型 + 自动禁用 404 模型
- **P1 grok_4 / o3 / gemini_deep_research 404**：model_registry.yaml 已设 enabled: false
- **P2 meta_capability pip 路径**：已改为 `_VENV_PIP`
- **searches: int bug**：`_discover_from_decision_tree()` 改为生成搜索词列表

### 4. 新增模块 ✅
- **health_monitor.py**：每个任务后执行规则止血（404 禁用、L2 低成功率缩输入、搜索全空切离线）+ GLM-5 异步追因
- **post_learning_review.py**：深度学习结束后 GLM-5 做结构化判断（哪些决策就绪、缺什么、下一轮优先什么）→ 自动更新决策树 + 追加任务池 + 飞书通知

### 5. 图像生成能力打通 ✅
四个模型全部验证通过：
- nano_banana_pro (464KB) ✅
- nano_banana_2 (74KB) ✅
- gemini_flash_image (105KB) ✅
- seedream_3_0 ✅

统一接口：`gw.call_image(prompt, model_name="nano_banana_pro", save_path="xxx.png")`

### 6. 灵魂注入 ✅
创始人深度对话完成，更新到 `.ai-state/founder_mindset.md` 和 `.ai-state/product_anchor.md`：
- 原始冲动：消灭"停车掏手机"
- 体验天花板：贾维斯 / 地板：30 秒语音
- 安全需求：BSD + 开门杀 + 行车记录仪（亲身经历）
- 形态底线：全内置，外观不能比普通全盔差
- 前置摄像头：不只是记录仪，是"生活记录"（雪景/樱花发朋友圈）
- 下巴位置，双模式（持续录 + 语音标记）
- 价格锚点：7000-8000 元
- 目标用户：玩乐骑 + 摩旅
- 组队通信：V1 刚需
- V1 功能优先级确认：语音 > HUD 导航 > ADAS > 行车记录仪 > Mesh 组队

### 7. Demo Milestone 计划 ✅
- 计划文档：`demo_milestone_plan.md`
- 决策树新增 v1_hud_demo + v1_app_demo 两个节点
- 任务池追加 4 个 Demo 前置研究任务（竞品 HUD 截图、竞品 App 截图、HUD 像素级规范、App 信息架构）
- CC 正在生成 HUD 图标素材到 `.ai-state/demo_assets/hud_icons/`

---

## 二、当前系统状态

### 模型可用性（2026-04-06 验证）
| 模型 | 状态 | 用途 |
|------|------|------|
| gpt_5_4 | ✅ | CTO/CPO 主力 |
| gpt_4o_norway | ✅ | CMO + 降级目标 |
| o3_deep_research | ✅ | L1 搜索 Channel A |
| gemini_2_5_flash | ✅ | L2 提炼 + 快速任务 |
| gemini_2_5_pro | ✅ | L4 整合 |
| gemini_3_1_pro | ✅ | Critic |
| doubao_seed_pro | ✅ | 中文搜索 |
| deepseek_v3_volcengine | ✅ | CDO |
| deepseek_r1_volcengine | ✅ | Critic cross + verifier |
| glm_4_7 | ✅ | 守夜诊断 + 认知闭环 |
| nano_banana_pro | ✅ | 图像生成（高质量） |
| nano_banana_2 | ✅ | 图像生成（快速） |
| gemini_flash_image | ✅ | 图像生成（基础） |
| seedream_3_0 | ✅ | 图像生成（中文场景） |
| grok_4 | ❌ disabled | 404 DeploymentNotFound |
| o3 | ❌ disabled | 404 DeploymentNotFound |
| gemini_deep_research | ❌ disabled | 404 |

### 架构分层
```
Leo（决策者）
├── Claude 主对话（有完整 memory）— 战略讨论、产品决策、架构设计
├── 思考通道（CDP 自动调用）— 深度学习后战略判断
│
agent_company（执行层）
├── scripts/deep_research/     — 五层研究管道（重构后 10 模块）
├── src/utils/model_gateway/   — 多模型网关（重构后 7 模块）
├── scripts/feishu_handlers/   — 飞书交互（7 模块）
├── 21+ 模型（14 可用 + 3 禁用 + 4 未部署）
├── 4 图像生成模型 ✅
├── 健康巡检 + 认知闭环 ✅
└── 定时任务 + 守夜模式
```

---

## 三、下一个会话的任务

### P0：Demo 生成器
- 新增 `scripts/demo_generator.py`
- 流程：前置知识检查 → CDO 生成 UI spec → 图标素材生成 → 代码生成 → 视觉审查
- HUD Demo：全屏黑色背景模拟护目镜，四角信息区，键盘模拟事件
- App Demo：React 单页应用，5 个页面
- 飞书指令注册："生成HUD Demo" / "生成App Demo" / "Demo状态"

### P1：思考通道 prompt 优化
- 改 `_build_thinking_context`，注入决策树状态 + 结构化提问格式
- 目标：思考通道的 Claude 收到的是约束式判断题，不是开放式对话

### P2：深度学习验证
- 确认 health_monitor 是否正常执行
- 确认 post_learning_review 是否产出决策树更新
- 确认 L2 成功率是否从 38% 提升到 80%+

---

## 四、关键文件路径

### 重构后的核心文件
- `scripts/deep_research/__init__.py` — 研究管道公开接口
- `scripts/deep_research/pipeline.py` — 核心管道 (800 行)
- `scripts/deep_research/runner.py` — 调度器 (660 行)
- `scripts/deep_research/health_monitor.py` — 健康巡检
- `scripts/deep_research/post_learning_review.py` — 认知闭环
- `src/utils/model_gateway/__init__.py` — 网关主文件 (450 行)
- `src/utils/model_gateway/providers/gemini.py` — Gemini 全部方法含图像生成

### 产品文档
- `.ai-state/founder_mindset.md` — 创始人心智模型（灵魂注入后）
- `.ai-state/product_anchor.md` — 产品锚点（V1 优先级确认后）
- `demo_milestone_plan.md` — Demo 生成计划

### GitHub
- https://github.com/lion9999ly/agent-company

---

## 五、设计原则备忘

- 讨论架构先，确认后再写代码
- 规则式做下限保障，LLM 做上限突破
- 执行层可以自治，决策层必须有人在环里
- 备份 + 回滚方案在手才动刀
- 每个文件单一职责，拆分的唯一理由是上下文保护
- Leo 不接受降级方案，不接受系统替他做决策
- 产品核心使命：消灭"停车掏手机"
