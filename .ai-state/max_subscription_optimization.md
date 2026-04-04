# Max 会员能力最大化方案

> Leo 有 Claude Max 月度会员，没有 Claude API。以下是如何最大化利用 Max 能力。

---

## 能力 1：claude.ai GitHub 连接器（立即可用）

### 操作
在 claude.ai 对话中：
1. 点左下角"+" 按钮
2. 选"Connectors" 
3. 找到 GitHub → Connect
4. 授权访问 lion9999ly/agent-company 仓库

### 效果
- 我（claude.ai）可以直接读你的代码，不需要贴 URL
- 每次新会话只需说"看一下 agent-company 的最新代码"
- 能浏览目录结构、读文件内容、看 commit 历史
- 彻底解决"我看不到 CC 改了什么"的问题

### 行动
**今天就做。** 这是 ROI 最高的一个操作——1 分钟设置，以后每次会话节省 10 分钟贴 URL。

---

## 能力 2：claude-hub（GitHub ↔ Claude 自动化）

### 是什么
一个开源项目，让你在 GitHub issue/PR 中 @claude，Claude 自动读代码、写代码、提 PR。用你的 Max 订阅认证，不需要 API key。

### 操作
```bash
git clone https://github.com/claude-did-this/claude-hub.git
cd claude-hub
cp .env.quickstart .env
# 编辑 .env，填入 GitHub token
./scripts/setup/setup-claude-interactive.sh  # 用 Max 订阅认证
docker compose up -d
```

### 效果
- 在 GitHub 上开 issue "实现 HUD 设计规范生成器"，Claude 自动读代码、实现、提 PR
- 不需要手动开 CC 窗口
- 可以同时开多个 issue 并行执行
- PR 可以 review 后再 merge，比直接 commit 更安全

### 行动
可以后续探索，优先级低于 GitHub 连接器。

---

## 能力 3：CC 作为 Claude 代理（替代 S8/S9）

### 方案
agent_company 遇到架构问题时，不需要 Claude API。而是：

1. 把问题写入 `.ai-state/claude_consultation_queue.jsonl`
2. CC 的后台 watch 机制检测到新问题
3. CC 读取问题，用自己的 Claude 能力（Max 额度）思考
4. CC 把答案写入 `.ai-state/claude_consultation_answers.jsonl`
5. agent_company 读取答案继续执行

实现更简单：直接在 agent_company 的 Python 代码中用 subprocess 调用 CC：

```python
import subprocess
result = subprocess.run(
    ["claude", "-p", question_text, "--output-format", "text"],
    capture_output=True, text=True, timeout=120
)
answer = result.stdout
```

这样 agent_company 可以随时"问 Claude"，走的是 Max 额度，不需要 API key。

### 行动
追加到轨道 D 的执行文档中。S8/S9 改为此方案。

---

## 能力 4：claude --remote（云端并行执行）

### 是什么
CC 的 --remote 模式，把任务发到云端执行，不占本地资源。

### 效果
- 本地 4 个 CC 窗口 + 云端若干个 remote 任务 = 更多并行
- 适合不依赖本地文件系统的独立任务（如生成文档、分析报告）

### 行动
可以在 4 轨道并行的基础上，把一些独立任务用 --remote 额外并行。

---

## 能力 5：Claude Projects（项目级上下文）

### 是什么
在 claude.ai 中创建一个 Project，把 CLAUDE.md、决策树、handoff 文件等放入 Project Knowledge。每次对话自动加载，不需要重新解释背景。

### 操作
1. claude.ai → Projects → New Project
2. 名字: "智能骑行头盔 R&D"
3. 添加 Project Knowledge:
   - CLAUDE.md（通过 GitHub 连接器选择）
   - product_decision_tree.yaml
   - improvement_backlog_complete.md
   - 最近的 handoff 文件

### 效果
- 每次新会话自动有完整上下文
- 不需要重新解释"你是谁、在做什么项目"
- 对话更深入，因为背景已知

### 行动
GitHub 连接器设置好后就创建 Project。
