# CC 执行指令 v3

## 你拿到了四份文件

1. `hud_demo_tech_spec.md` — 技术规格
2. `hud_demo_test_spec.js` — 测试脚本
3. `hud_demo_visual_criteria.md` — 视觉标准
4. `run_hud_demo.py` — **Orchestrator 脚本（状态机，控制全流程）**

## 执行步骤

```bash
# 1. 放置文件
cd D:/Users/uih00653/my_agent_company/pythonProject1
mkdir -p demo_outputs/specs

cp run_hud_demo.py demo_outputs/
cp hud_demo_tech_spec.md demo_outputs/specs/
cp hud_demo_test_spec.js demo_outputs/specs/
cp hud_demo_visual_criteria.md demo_outputs/specs/

# 2. 安装依赖
npm install jsdom puppeteer

# 3. 运行
python demo_outputs/run_hud_demo.py
```

## 说明

`run_hud_demo.py` 是状态机，它会：
- 自动按顺序调用你（CC）写 5 个模块
- 每个模块写完自动做质量检查（行数、var 禁止、函数挂载等）
- 检查不过自动让你修
- 自动拼装成单 HTML
- 自动跑测试（node test_spec.js）
- 测试不过自动定位模块让你修，最多 10 轮
- 自动截图（puppeteer）
- 自动视觉审查（多模态 LLM）
- 全通过后自动交付（GitHub Issue + 飞书通知）
- 卡住时自动创建 Issue 报告 + 飞书通知

**你不需要理解流程，只需要响应 orchestrator 的调用，写好代码。**
