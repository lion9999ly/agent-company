# Day 17 系统全量审计 - 配置文件和基础设施

## 1. .git/hooks/post-commit

```bash
#!/bin/bash
# Git post-commit hook: 重启 SDK + 验证
# SDK 统一由 start_sdk.bat / stop_sdk.bat 管理

echo "=========================================="
echo "Post-commit: 重启 SDK 并验证"
echo "=========================================="

# 切换到项目根目录
cd "$(git rev-parse --show-toplevel)"

STATUS_FILE=".ai-state/system_status.md"
LEO_OPEN_ID="ou_8e5e4f183e9eca4241378e96bac3a751"

# 1. 更新 system_status.md
echo "[1/4] 更新系统状态..."
if [ -f "$STATUS_FILE" ]; then
    LAST_COMMIT=$(git log -1 --pretty=format:"%s" 2>/dev/null || echo "unknown")
    TODAY=$(date +%Y-%m-%d)
    if ! grep -q "$TODAY" "$STATUS_FILE" 2>/dev/null; then
        sed -i "/## 最近变更/a - $TODAY: $LAST_COMMIT" "$STATUS_FILE" 2>/dev/null || true
        echo "  [OK] system_status.md 已更新"
    else
        echo "  [OK] 今日变更已存在，跳过"
    fi
fi

# 2. 重启 SDK（调用 bat 脚本）
echo "[2/4] 重启 SDK..."
cmd //c scripts\\stop_sdk.bat 2>/dev/null
sleep 2
cmd //c scripts\\start_sdk.bat 2>/dev/null
echo "  [OK] SDK 已重启"

# 3. 验证
echo "[3/4] 运行验证..."
python scripts/auto_restart_and_verify.py --verify-only --no-push 2>/dev/null || echo "  [WARN] 验证失败"

# 4. 发飞书通知
echo "[4/4] 发送飞书通知..."
LAST_COMMIT=$(git log -1 --pretty=format:"%s" 2>/dev/null || echo "unknown")
lark-cli im +messages-send \
    --receive-id "$LEO_OPEN_ID" \
    --receive-type "open_id" \
    --msg-type "text" \
    --content "{\"text\":\"✅ Post-commit 完成\n\n📝 $LAST_COMMIT\"}" \
    --as bot 2>/dev/null || echo "  [WARN] 飞书通知失败"

echo "=========================================="
echo "Post-commit 完成"
echo "=========================================="
```

## 2. scripts/start_sdk.bat

```batch
@echo off
chcp 65001 >nul 2>&1
cd /d D:\Users\uih00653\my_agent_company\pythonProject1

set PID_FILE=.ai-state\sdk.pid
set LOG_FILE=.ai-state\feishu_sdk.log

echo 启动 SDK...

REM 停止旧进程
if exist "%PID_FILE%" (
    set /p OLD_PID=<"%PID_FILE%"
    taskkill /PID %OLD_PID% /F >nul 2>&1
    del "%PID_FILE%" >nul 2>&1
)

REM 通过进程名停止
for /f "tokens=2" %%i in ('wmic process where "commandline like '%%feishu_sdk%%'" get processid 2^>nul ^| findstr /r "[0-9]"') do (
    taskkill /PID %%i /F >nul 2>&1
)

REM 清空日志
echo [%date% %time%] SDK 启动中... > "%LOG_FILE%"

REM 启动后台进程
start /B "" ".venv\Scripts\pythonw.exe" "scripts\feishu_sdk_client_v2.py" >> "%LOG_FILE%" 2>&1

REM 等待进程启动
ping -n 3 127.0.0.1 >nul

REM 获取 PID
for /f "tokens=2" %%i in ('wmic process where "commandline like '%%feishu_sdk%%'" get processid 2^>nul ^| findstr /r "[0-9]"') do (
    echo %%i > "%PID_FILE%"
    echo SDK 已启动，PID: %%i
    echo [%date% %time%] SDK 已启动，PID: %%i >> "%LOG_FILE%"
    goto :done
)

:done
echo 完成
```

## 3. .ai-state/system_status.md

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

## 待执行改进
见 `.ai-state/improvement_backlog_complete.md`
```

## 4. .ai-state/competitor_monitor_config.json

```json
{
  "monitor_layers": {
    "direct_competitors": {
      "description": "直接竞品",
      "brands": ["Shoei Smart", "洛克兄弟", "MOTOEYE", "EyeLights", "iC-R", "Sena", "Cardo"],
      "search_keywords": [
        "智能骑行头盔 HUD 2026",
        "motorcycle helmet HUD product 2026",
        "智能头盔 产品 发布 2026"
      ]
    },
    "tech_supply_chain": {
      "description": "技术供应链",
      "topics": ["JBD", "Sony ECX", "京东方", "FreeForm", "光波导", "高通AR"],
      "search_keywords": [
        "JBD micro display 2026",
        "Sony ECX OLED micro display 2026",
        "光波导 技术 进展 2026",
        "AR chip Qualcomm 2026"
      ]
    },
    "riding_ecosystem": {
      "description": "骑行生态",
      "topics": ["摩托车市场", "摩旅用户", "小红书抖音KOL", "政策"],
      "search_keywords": [
        "摩托车市场 趋势 2026 中国",
        "摩旅 用户画像 需求 2026",
        "摩托车 政策 法规 2026"
      ]
    },
    "adjacent_tech": {
      "description": "相邻技术",
      "topics": ["汽车HUD", "车载语音", "端侧AI", "Mesh通讯", "AR眼镜", "飞书CLI"],
      "search_keywords": [
        "汽车 HUD 技术 发展 2026",
        "端侧 AI 语音识别 2026",
        "Mesh通讯 摩托车 头盔 2026",
        "飞书 CLI 更新 changelog 2026",
        "lark-cli new features github releases"
      ]
    },
    "regulations": {
      "description": "法规标准",
      "topics": ["ECE 22.06", "GB 811", "两轮ADAS强制", "HUD合法性"],
      "search_keywords": [
        "ECE 22.06 helmet regulation 2026",
        "摩托车 ADAS 法规 2026",
        "HUD 显示 法规 交通安全 2026"
      ]
    },
    "cross_reference": {
      "description": "跨界参考",
      "topics": ["滑雪头盔", "自行车头盔", "智能硬件融资", "Bosch两轮"],
      "search_keywords": [
        "智能头盔 融资 2026",
        "Bosch motorcycle ADAS 2026",
        "AR helmet funding 2026"
      ]
    }
  },
  "time_filters": {
    "current_year": true,
    "discard_months_old": 6,
    "fallback_months": 12
  },
  "output_rules": {
    "no_update_no_push": true,
    "require_substantial_content": true
  },
  "impact_analysis": {
    "enabled": true,
    "model": "gpt_4o_norway",
    "dimensions": ["技术选型", "竞品动态", "市场趋势", "供应链", "法规", "用户需求"],
    "relevance_levels": ["high", "medium", "low"]
  }
}
```

## 5. .ai-state/notify_config.json

```json
{
  "deep_research": {
    "start": true,
    "progress": false,
    "complete": true,
    "error": true,
    "description": "深度学习（7h管道）：开始+完成+异常，静默进度"
  },
  "competitor_monitor": {
    "start": false,
    "no_update": false,
    "has_update": true,
    "error": true,
    "description": "竞品监控：仅推送有更新的，静默无更新"
  },
  "auto_learn": {
    "start": false,
    "progress": false,
    "complete": false,
    "error": true,
    "description": "自学习（30min）：静默运行，仅推送异常"
  },
  "roundtable": {
    "start": true,
    "phase_complete": false,
    "convergence": true,
    "task_complete": true,
    "error": true,
    "description": "圆桌：开始+收敛+完成+异常，静默中间阶段"
  },
  "kb_governance": {
    "start": false,
    "complete": true,
    "error": true,
    "description": "KB治理：完成+异常"
  }
}
```

## 6. .ai-state/task_specs/hud_demo.json

```json
{
  "topic": "HUD Demo 生成",
  "goal": "生成一个可双击打开的 HUD 演示 HTML 文件，用于给供应商和投资人展示智能骑行座舱的 HUD 体验",
  "acceptance_criteria": [
    "单 HTML 文件，零外部依赖（字体CDN除外），双击可在浏览器打开",
    "全屏黑色背景模拟护目镜视角",
    "四角布局：LT=速度+骑行状态，RT=设备状态，RB=导航，LB=通知",
    "中央视野完全留空",
    "7个页面态全部可触发：骑行主界面/导航/来电/音乐/组队/预警/录制",
    "页面态按优先级自动切换：预警>来电>导航>组队>音乐>录制>主界面",
    "预警时对应方向角落闪烁：前方=LT+RT，左后=LB，右后=RB",
    "3条自动剧本（日常通勤/紧急场景/组队骑行），底部时间轴可播放/暂停/拖拽",
    "手动沙盒模式：右侧面板按类别分组列出所有可触发事件",
    "A/B光学方案切换：OLED全彩（默认）vs 光波导单绿色，有明显视觉差异",
    "速度分级S0-S3自动适应信息密度",
    "键盘快捷键覆盖所有核心操作",
    "全彩OLED为默认配色方案，各功能色彩语义清晰区分",
    "开机自检动画"
  ],
  "proposer": "CDO",
  "reviewers": ["CTO", "CMO"],
  "critic": "Critic",
  "authority_map": {
    "design": "CDO",
    "feasibility": "CTO",
    "user_fit": "CMO",
    "final": "Leo"
  },
  "input_docs": [
    ".ai-state/product_anchor.md",
    ".ai-state/founder_mindset.md"
  ],
  "kb_search_queries": [
    "HUD display layout",
    "helmet HUD user interface",
    "motorcycle HUD competitor",
    "ADAS warning display",
    "heads up display design principles"
  ],
  "role_prompts": {
    "CDO": "本议题是 HUD Demo 的视觉和交互设计。关注：四角布局信息密度、预警视觉冲击力、全彩配色的功能色语义（速度白/导航蓝/预警红/组队青/音乐紫）、A/B光学方案的视觉差异表达、自动剧本的叙事节奏。已知陷阱：HUD不是手机App，骑手用余光扫视，信息必须一瞥可读。产品核心使命：消灭停车掏手机。",
    "CTO": "本议题是 HUD Demo 的技术实现。关注：单HTML文件零依赖约束、状态机完整性（7个页面态+优先级切换）、键盘事件全覆盖、自动剧本时序驱动机制、代码结构可维护性。已知陷阱：单次LLM生成超500行HTML时质量下降——考虑是否需要分段生成策略。但最终产物必须是单文件。",
    "CMO": "本议题是 HUD Demo 的演示说服力。关注：竞品 Shoei GT-Air 3 Smart（$1199，EyeLights OLED HUD）的体验对标——我们要比它好在哪里看得出来？ADAS预警是核心差异化（Shoei做不到）——Demo里ADAS场景是否足够震撼？3分钟内投资人/供应商能否get到产品价值？目标用户是玩乐骑+摩旅骑手，不是通勤。",
    "Critic": "审查标准：14条验收标准逐条验证。额外关注：Demo是否传达了产品的核心差异化（ADAS安全感知），还是沦为了一个花哨的信息展示板？审查各角色置信度标注是否诚实。"
  },
  "output_type": "html",
  "output_path": "demo_outputs/hud_demo_roundtable.html",
  "generator_input_mode": "raw_proposal",
  "auto_verify_rules": [],
  "max_iterations": 10,
  "timeout_minutes": 60
}
```

## 7. .ai-state/verifier_rules/global.json

```json
[
  {
    "type": "html_valid",
    "params": {},
    "criterion": "HTML 格式有效",
    "severity": "P0"
  },
  {
    "type": "no_external_deps",
    "params": {},
    "criterion": "零外部依赖",
    "severity": "P1"
  },
  {
    "type": "keyword_exists",
    "params": {"keyword": "</script>"},
    "criterion": "script 标签闭合",
    "severity": "P0"
  }
]
```

## 8. .ai-state/verifier_rules/type_html.json

```json
[
  {
    "type": "line_count_range",
    "params": {"min_lines": 10, "max_lines": 5000},
    "criterion": "文件大小合理范围",
    "severity": "P1"
  }
]
```

## 9. .ai-state/verifier_rules/evolution_log.jsonl

```json
{"timestamp": "2026-04-08T00:00:00", "event": "初始化规则库", "files": ["global.json", "type_html.json"]}
```

## 10. .env 非敏感项

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

## 11. roundtable_runs/ 目录结构

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

## 12. git log --oneline -20

```
b313187 feat: SDK 后台服务运行方式改造
3ebd1f1 fix: post-commit hook 不再自动启动 SDK
a45928c fix: Day 17 诊断修复 - 5 个问题
4180122 fix: 夜间运行 8 个问题修复
89180e5 fix: agent 自然语言调试 + AutoLearn 缺口过滤修复
ced2fd0 fix: agent.py 修复 Claude Code CLI 调用和 chat_id 传递
537187f feat: thinking layer consultation rules + GitHub Issue instruction channel
eefbf9a fix: remove invalid --no-input flag from Claude CLI call
6b395a7 debug: add verbose logging for Agent mode
6789af6 feat: auto SDK restart on commit + agent mode integration
2e98bd8 fix: auto-add edit permission for Leo on created docs
9381567 fix: 4 critical bugs in feishu output, autolearn, and roundtable
945d7e4 fix: lark-cli --document-id → --doc parameter + add lark-cli tracking
87c1028 fix: add encoding='utf-8' to subprocess calls for Windows compatibility
c99d342 feat: lark-bot-agent architecture + scheduler independent
633ccfa fix: use shutil.which to find lark-cli path for subprocess
f876ba3 feat: feishu CLI output layer — cloud docs + bitable
86f503a fix: auto_restart_and_verify.py with PID tracking
ca52181 fix: auto_restart_and_verify.py with SDK restart + direct API notification
b577e5b refactor: rewrite auto_restart_and_verify.py with direct function verification
```

## 13. git tag -l

```
backup-before-batch5-refactor
backup-before-lark-cli-step2
backup-before-v2-refactor
```