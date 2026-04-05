# Day 16 操作指南

---

## 当前状态

| 项目 | 状态 |
|------|------|
| 可用模型 | 6 个：gpt-5.4, gpt-4o, o3-deep, doubao-pro, doubao-lite, deepseek-v3 |
| Gemini | ❌ 全系 API key leaked，等 IT 重新生成 |
| Claude CLI | ✅ 可用，后端 GLM-5（通过 Z.AI） |
| 飞书服务 | ✅ 运行中 |
| 自检 | 24/26 通过 |

---

## 操作步骤

### 第 1 步：下载文件

下载以下 2 个文件到 `D:\Users\uih00653\my_agent_company\pythonProject1\.ai-state\`：

- `cc_exec_day16_window1.md`
- `cc_exec_day16_window2.md`

### 第 2 步：Git 推送

```powershell
cd D:\Users\uih00653\my_agent_company\pythonProject1
git add .ai-state/cc_exec_day16_window1.md .ai-state/cc_exec_day16_window2.md
git commit -m "docs: Day 16 CC execution documents"
git push origin main
```

### 第 3 步：开 2 个 CC 窗口

**窗口 1（串行，约 30-40 分钟）：**

```
读取 .ai-state/cc_exec_day16_window1.md 并按顺序执行所有任务。

重要前置：
- Gemini 全系列不可用（API key leaked）
- 所有原本用 gemini 的地方改用 doubao_seed_lite（轻量）或 gpt_4o_norway（需质量）
- Claude CLI 可用但后端是 GLM-5，不是 Claude
```

**窗口 2（独立，约 15-20 分钟）：**

```
读取 .ai-state/cc_exec_day16_window2.md 并执行。

重要前置：
- Gemini 不可用，视觉验证跳过
- Playwright 如果装不上就跳过
```

### 第 4 步：等待完成

两个窗口都完成后，看窗口 1 最后的自检结果。

### 第 5 步：重启飞书验证

```powershell
# 先停掉当前飞书服务（Ctrl+C）
# 重启
cd D:\Users\uih00653\my_agent_company\pythonProject1
.venv\Scripts\python.exe scripts/feishu_sdk_client.py
```

在飞书中依次测试：

```
自检
早报
状态
深度学习
```

深度学习输入 `1`（跑 1 小时做快速验证），看：
- API 健康检查是否在启动前自动跑
- L2 提炼是否不再是 0/N
- 学习系统是否在记录
- 决策树是否有回流
- 任务池跑完后是否从决策树发现新任务

---

## Day 16 验证标准

| 指标 | Day 15 | Day 16 目标 |
|------|--------|------------|
| 自检通过率 | 24/26 | 25/26+ |
| L2 提炼成功率 | 0% | 80%+（用 gpt_4o 替代 Flash） |
| 搜索学习记录 | 0 条 | 有记录 |
| 决策树回流 | 0/7 | 至少 2/7 有数据 |
| auto_fixer 解析率 | 0% | 50%+（有 CLI fallback） |
| 深度学习时间利用率 | 4.1/8h | 更高（有决策树补充任务） |
| 启动前健康检查 | 无 | 自动检查 + 飞书通知 |
