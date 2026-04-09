# Day 17 系统全量审计 - Part 3: 基础设施 + 配置状态

## D. 基础设施

### 22. scripts/auto_restart_and_verify.py 完整内容

**流程：**
1. 停止 feishu_sdk_client_v2.py 进程
2. 重新启动 SDK（后台）
3. 等待连接就绪（检测日志）
4. 执行验证（6 项）
5. 发送报告到飞书

**验证项：**
- 状态指令
- 监控范围
- 圆桌 TaskSpec
- Verifier 规则库
- Model Gateway
- 路由匹配

### 23. scripts/regression_check.py 完整内容

**功能：**
- 文件行数检查（WARNING: 800, ERROR: 1200）
- 飞书指令检查
- 内部功能检查
- 定时任务检查

### 24. .git/hooks/post-commit 完整内容

**流程：**
1. 更新 system_status.md
2. 重启 SDK
3. 运行验证
4. 发飞书通知

### 25. scripts/start_sdk.bat 完整内容

**流程：**
1. 停止旧进程
2. 清空日志
3. 启动后台进程
4. 等待并获取 PID

---

## E. 配置和状态文件

### 27. .ai-state/system_status.md

```markdown
# 系统状态

> 最后更新：2026-04-08 (由 Claude Code 自动维护)

## 当前状态
- **阶段**：方案论证
- **Git 分支**：main
- **最近提交**：feat: generator retry, snapshots, verdict parser

## 最近变更
- 2026-04-09: fix: Day 17 诊断修复 - 5 个问题
- 2026-04-08: 圆桌 v2 核心重构（收敛分层、因果链、动态输入、规则库）
- 2026-04-08: Generator 重试机制、过程快照保留、评判解析器
- 2026-04-07: HUD Demo Segment 5 完成 + 视觉打磨

## 能力清单
- `圆桌` - 多角色讨论引擎（Phase 1-4）
- `深度学习` - 五层管道（7h）
- `自学习` - 周期知识补强（30min）
- `KB治理` - 知识库清洗
- `竞品监控` - 竞品动态追踪
- `GitHub Issue` - 指令通道

## 模型可用性
| 模型 | 角色 | 状态 |
|------|------|------|
| o3-deep-research | 深度研究主力 | ✅ 可用 |
| gpt_5_4 | 高级降级 | ✅ 可用 |
| gpt-4o | 通用降级 | ✅ 可用 |
| doubao_seed_pro | 中文搜索+Critic | ✅ 可用 |
| gemini_3_1_pro | 备选 | ✅ 可用 |

## 已知问题
- roundtable.py 超过 800 行（已豁免，待独立重构）
- text_router.py 约 2292 行（待拆分）
```

### 30. .ai-state/competitor_monitor_config.json

**6 层监控范围：**
- direct_competitors: Shoei Smart, 洛克兄弟, MOTOEYE, EyeLights, iC-R, Sena, Cardo
- tech_supply_chain: JBD, Sony ECX, 京东方, FreeForm, 光波导, 高通AR
- riding_ecosystem: 摩托车市场, 摩旅用户, 小红书抖音KOL, 政策
- adjacent_tech: 汽车HUD, 车载语音, 端侧AI, Mesh通讯, AR眼镜, 飞书CLI
- regulations: ECE 22.06, GB 811, 两轮ADAS强制, HUD合法性
- cross_reference: 滑雪头盔, 自行车头盔, 智能硬件融资, Bosch两轮

### 31. .ai-state/notify_config.json

```json
{
  "deep_research": {"start": true, "progress": false, "complete": true, "error": true},
  "competitor_monitor": {"start": false, "no_update": false, "has_update": true, "error": true},
  "auto_learn": {"start": false, "progress": false, "complete": false, "error": true},
  "roundtable": {"start": true, "phase_complete": false, "convergence": true, "task_complete": true, "error": true},
  "kb_governance": {"start": false, "complete": true, "error": true}
}
```

### 33. .ai-state/task_specs/hud_demo.json

**acceptance_criteria（14 条）：**
1. 单 HTML 文件，零外部依赖（字体CDN除外），双击可在浏览器打开
2. 全屏黑色背景模拟护目镜视角
3. 四角布局：LT=速度+骑行状态，RT=设备状态，RB=导航，LB=通知
4. 中央视野完全留空
5. 7个页面态全部可触发
6. 页面态按优先级自动切换
7. 预警时对应方向角落闪烁
8. 3条自动剧本
9. 手动沙盒模式
10. A/B光学方案切换
11. 速度分级S0-S3自动适应信息密度
12. 键盘快捷键覆盖所有核心操作
13. 全彩OLED为默认配色方案
14. 开机自检动画

**generator_input_mode**: raw_proposal

### 34. .ai-state/verifier_rules/global.json

```json
[
  {"type": "html_valid", "params": {}, "criterion": "HTML 格式有效", "severity": "P0"},
  {"type": "no_external_deps", "params": {}, "criterion": "零外部依赖", "severity": "P1"},
  {"type": "keyword_exists", "params": {"keyword": "</script>"}, "criterion": "script 标签闭合", "severity": "P0"}
]
```

### 35. .ai-state/verifier_rules/type_html.json

```json
[
  {"type": "line_count_range", "params": {"min_lines": 10, "max_lines": 5000}, "criterion": "文件大小合理范围", "severity": "P1"}
]
```

### 37. .ai-state/research_task_pool.yaml

**状态**: 文件存在

### 38. .ai-state/product_decision_tree.yaml（前 200 行）

**决策项：**
- v1_display: V1 HUD 用 OLED+FreeForm 还是 MicroLED+衍射光波导？（priority: 1, deadline: 2026-04-30）
- v1_soc: 主 SoC 用 Qualcomm AR1 Gen1？（status: decided）
- v1_intercom: Mesh Intercom 自研还是授权 Cardo DMC？（priority: 1, deadline: 2026-04-25）
- v1_audio: 扬声器用骨传导还是传统动圈？（priority: 2）
- v1_safety_cert: V1 认证走 DOT+ECE 还是额外加 SNELL？（priority: 2）
- v1_camera: V1 是否集成摄像头？（priority: 2）
- v1_jdm_partner: JDM 合作伙伴选歌尔、立讯还是其他？（priority: 1, deadline: 2026-04-20）

### 39. .env 非敏感项

```
AZURE_OPENAI_API_KEY=***
AZURE_OPENAI_ENDPOINT=***
AZURE_OPENAI_NORWAY_API_KEY=***
AZURE_OPENAI_NORWAY_ENDPOINT=***
GEMINI_API_KEY=***
FEISHU_APP_ID=***
FEISHU_APP_SECRET=***
FEISHU_WEBHOOK_URL=***
```

---

## F. 运行时状态

### 40. roundtable_runs/ 目录

```
roundtable_runs/
├── HUDDemo生成_20260408_112335/  (空)
├── HUDDemo生成_20260408_144049/
│   ├── convergence_trace.jsonl
│   ├── crystal_context_summary.md
│   ├── generator_input_actual.md
│   ├── input_task_spec.json
│   ├── phase2_proposal_full.md
│   └── phase4_critic_final.md
└── HUDDemo生成_20260408_154038/
    ├── convergence_trace.jsonl
    ├── crystal_context_summary.md
    ├── generator_input_actual.md
    ├── input_task_spec.json
    ├── phase2_proposal_full.md
    └── phase4_critic_final.md
```

### 41. .ai-state/verifier_rules/

```
verifier_rules/
├── evolution_log.jsonl
├── global.json
└── type_html.json
```

### 42. .ai-state/task_specs/

```
task_specs/
└── hud_demo.json
```

### 45. git log --oneline -20

```
b313187 feat: SDK 后台服务运行方式改造
3ebd1f1 fix: post-commit hook 不再自动启动 SDK
a45928c fix: Day 17 诊断修复 - 5 个问题
4180122 fix: 夜间运行 8 个问题修复
89180e5 fix: agent 自然语言调试 + AutoLearn 缺口过滤修复
ced2fd0 fix: agent.py 修复 Claude Code CLI 调用和 chat_id 传递
537187f feat: thinking layer consultation rules + GitHub Issue instruction channel
...
```

### 46. git tag -l

```
backup-before-batch5-refactor
backup-before-lark-cli-step2
backup-before-v2-refactor
```

---

**审计完成**