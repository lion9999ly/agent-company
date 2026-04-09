# [诊断] Day 17 深度检查 v2

## 文件汇总清单

### 1. scripts/feishu_sdk_client_v2.py - 消息处理入口

**关键代码段（Lines 56-155）：**

```python
def handle_message(event):
    """处理收到的消息 - v2 模块化版本"""
    # ... 初始化部分 ...
    
    # === v2.1: 使用 Agent 模式（飞书 → Claude Code CLI）===
    print(f"  [DEBUG] USE_AGENT_MODE={USE_AGENT_MODE}")
    if USE_AGENT_MODE:
        try:
            from scripts.agent import handle_message as agent_handle_message
            print(f"  [Agent模式] 调用 agent.handle_message(text, chat_id={chat_id}, open_id={open_id})")
            agent_handle_message(text, chat_id, open_id)
            print(f"  [Agent模式] agent.handle_message 返回")
        except Exception as e:
            import traceback
            print(f"  [Agent模式失败] {e}")
            traceback.print_exc()
            # 降级到旧路由器
            route_text_message(...)
```

---

### 2. .git/hooks/post-commit

```bash
#!/bin/bash
echo "=========================================="
echo "Post-commit: 重启 SDK 并验证"
echo "=========================================="

cd "$(git rev-parse --show-toplevel)"

# 1. 更新 system_status.md
# 2. 重启 SDK (stop_sdk.bat + start_sdk.bat)
# 3. 验证 (auto_restart_and_verify.py --verify-only)
# 4. 飞书通知
```

---

### 3. scripts/start_sdk.bat

```batch
@echo off
chcp 65001 >nul 2>&1
cd /d D:\Users\uih00653\my_agent_company\pythonProject1

# 停止旧进程
# 清空日志
# 启动: .venv\Scripts\pythonw.exe scripts\feishu_sdk_client_v2.py
```

---

### 4. scripts/start_sdk.vbs

```vbs
Set ws = CreateObject("WScript.Shell")
ws.CurrentDirectory = "D:\Users\uih00653\my_agent_company\pythonProject1"
ws.Run "cmd /c .venv\Scripts\pythonw.exe scripts\feishu_sdk_client_v2.py >> .ai-state\feishu_sdk.log 2>&1", 0, False
```

---

### 5. scripts/auto_learn.py - 缺口检测函数

**_load_covered_topics():**
- 从 `.ai-state/auto_learn_covered.json` 加载
- 过滤 7 天前的记录

**_find_kb_gaps():**
- 从决策树 `blocking_knowledge` 获取缺口
- 从 `research_task_pool.yaml` 获取未完成任务
- 从域分布、时效性、产品锚点关键词获取补充

---

### 6. .ai-state/competitor_monitor_config.json

**6 层监控：**
| 层级 | 内容 |
|------|------|
| direct_competitors | Shoei Smart, 洛克兄弟, MOTOEYE, EyeLights, iC-R, Sena, Cardo |
| tech_supply_chain | JBD, Sony ECX, 京东方, FreeForm, 光波导, 高通AR |
| riding_ecosystem | 摩托车市场, 摩旅用户, 小红书抖音KOL, 政策 |
| adjacent_tech | 汽车HUD, 车载语音, 端侧AI, Mesh通讯, AR眼镜, 飞书CLI |
| regulations | ECE 22.06, GB 811, 两轮ADAS强制, HUD合法性 |
| cross_reference | 滑雪头盔, 自行车头盔, 智能硬件融资, Bosch两轮 |

---

### 7. .ai-state/research_task_pool.yaml

| ID | 状态 | 优先级 | 标题 |
|----|------|--------|------|
| auto_001 | ✅ 完成 | 1 | 智能头盔主动安全系统集成与标准研究 |
| auto_002 | ✅ 完成 | 1 | 先进HUD显示技术与用户界面设计研究 |
| auto_003 | ⏳ 待执行 | 2 | 嘈杂环境下的头盔语音控制与降噪技术研究 |
| auto_004 | ⏳ 待执行 | 2 | 集成智能头盔竞争格局与功能对标分析 |
| demo_hud_screenshots | ⏳ 待执行 | 1 | 竞品 HUD 界面截图与布局分析 |
| lark_cli_update | ⏳ 待执行 | 2 | 飞书 CLI 最新能力与更新日志追踪 |
| demo_app_screenshots | ⏳ 待执行 | 1 | 竞品 App 界面截图与信息架构分析 |
| demo_hud_pixel_spec | ⏳ 待执行 | 2 | HUD 像素级布局规范 v0.2 |
| demo_app_ia | ⏳ 待执行 | 2 | App 信息架构 v0.1 |
| hud_thermal_design | ⏳ 待执行 | 1 | HUD 光学模组散热设计研究 |
| helmet_battery_safety | ⏳ 待执行 | 1 | 头盔电池安全标准研究 |
| hud_fov_optimization | ⏳ 待执行 | 2 | HUD 视野角度优化研究 |

---

### 8. .ai-state/product_decision_tree.yaml

| ID | 状态 | 优先级 | 问题 | 截止日期 |
|----|------|--------|------|----------|
| v1_display | open | 1 | OLED+FreeForm vs MicroLED+衍射光波导 | 2026-04-30 |
| v1_soc | decided | 1 | 主 SoC 用 Qualcomm AR1 Gen1？ | - |
| v1_intercom | open | 1 | Mesh 自研 vs 授权 Cardo DMC | 2026-04-25 |
| v1_audio | open | 2 | 扬声器用骨传导还是传统动圈？ | 2026-05-10 |
| v1_safety_cert | open | 2 | DOT+ECE 还是额外加 SNELL？ | 2026-05-20 |
| v1_camera | open | 2 | V1 是否集成摄像头？前置/后置/双摄？ | 2026-05-15 |
| v1_jdm | open | 2 | JDM 供应商选择 | - |

---

### 9. 最新日志 (tail -50)

```
[Lark] [2026-04-09 08:49:59] [INFO] connected to wss://msg-frontier.feishu.cn/ws/v2
[Lark] [2026-04-09 08:49:59] [DEBUG] ping success
[Lark] [2026-04-09 08:49:59] [DEBUG] receive pong
[Lark] [2026-04-09 08:51:29] [DEBUG] ping success
[Lark] [2026-04-09 08:51:29] [DEBUG] receive pong
[Lark] [2026-04-09 08:52:59] [DEBUG] ping success
[Lark] [2026-04-09 08:52:59] [DEBUG] receive pong
```

**状态：** 心跳正常，WebSocket 连接稳定，无错误日志。

---

### 10. roundtable_runs/HUDDemo生成_20260408_154038/

| 文件 | 大小 | 说明 |
|------|------|------|
| input_task_spec.json | 3.4KB | 输入 TaskSpec |
| crystal_context_summary.md | 10.7KB | 上下文结晶摘要 |
| generator_input_actual.md | 9.3KB | 生成器实际输入 |
| phase2_proposal_full.md | 8.0KB | Phase 2 提案 |
| phase4_critic_final.md | 3.3KB | Phase 4 Critic 最终评审 |
| convergence_trace.jsonl | 57B | 收敛追踪 |

---

## 完整文件路径

需要查看的完整文件：
1. `scripts/feishu_sdk_client_v2.py`
2. `scripts/agent.py`
3. `.git/hooks/post-commit`
4. `scripts/start_sdk.bat`
5. `scripts/start_sdk.vbs`
6. `scripts/auto_learn.py`
7. `.ai-state/competitor_monitor_config.json`
8. `.ai-state/research_task_pool.yaml`
9. `.ai-state/product_decision_tree.yaml`
10. `.ai-state/feishu_sdk.log`

---

*生成时间: 2026-04-09*