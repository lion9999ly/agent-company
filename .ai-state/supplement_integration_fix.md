# 补充操作指南

---

## 一、GitHub 连接（修正版）

之前说的"Settings > Connectors"是错的。正确操作如下：

### 方式 A：在对话中添加（每次对话临时用）

1. 打开 claude.ai，进入任意对话
2. 在输入框左下角找到 **"+"** 按钮，点击
3. 下拉菜单中选 **"Add from GitHub"**
4. 首次使用会跳转到 GitHub 授权页面 → 授权
5. 授权后出现文件浏览器，搜索 `lion9999ly/agent-company`
6. 选择要添加的文件/文件夹（建议选整个仓库或关键目录）
7. 发送消息时，我就能读到这些文件

### 方式 B：在 Project 中添加（持久生效，推荐）

1. claude.ai → 左侧栏 → **Projects** → **New Project**
2. 名字：`智能骑行头盔 R&D`
3. 在 Project 页面右上角的 Knowledge 区域，点 **"+"**
4. 选 **"GitHub"**
5. 搜索 `lion9999ly/agent-company` 或粘贴仓库 URL
6. 用文件浏览器选择关键文件：
   - `CLAUDE.md`
   - `scripts/tonight_deep_research.py`
   - `scripts/feishu_handlers/text_router.py`
   - `src/tools/knowledge_base.py`
   - `src/config/model_registry.yaml`
   - `.ai-state/product_decision_tree.yaml`
7. 以后在这个 Project 里开对话，我自动有这些文件的上下文
8. 代码更新后点 **"Sync"** 图标刷新到最新版

**注意：** 如果你的仓库是 Private，需要在 GitHub 授权页面勾选该仓库的访问权限。如果是 Public 则直接可用。

---

## 二、集成修复 + C-2 + C-14（一个 CC 窗口搞定）

等轨道 D 完成后，开一个新 CC 窗口，粘贴以下指令：

```
这是一个集成修复任务。轨道 A/B/C/D 已各自完成，但有些跨轨道的连接点需要打通。

请按顺序执行以下任务：

## 1. 补做 C-2：统一错误处理

在 scripts/feishu_handlers/text_router.py 中，找到所有 `except Exception as e: send_reply(reply_target, f"...失败: {e}")` 的模式，替换为统一的错误处理：

新建或找到 safe_reply_error 函数：
```python
def _safe_reply_error(send_reply, reply_target, task_name, error):
    import traceback
    print(f"[ERROR] {task_name}: {traceback.format_exc()}")
    send_reply(reply_target, f"⚠️ {task_name} 遇到问题，已记录日志。请稍后重试。")
```

然后把所有 handler 的 except 块改用这个函数。

git add -A && git commit -m "fix: unified error handling across all feishu handlers" && git push origin main

## 2. 补做 C-14：信心校准的 text_router 部分

在 text_router.py 的智能回复函数中（_smart_route_and_reply 或类似函数），如果回答引用了 KB 数据，在末尾追加反馈提示：

```python
if kb_used:
    reply_text += "\n\n📊 这个回答准确吗？回复 👍 或 👎"
```

并处理 👍/👎 回复，调用 knowledge_base.py 中的 record_answer_feedback()。

git add -A && git commit -m "feat: answer confidence feedback in chat replies" && git push origin main

## 3. 集成修复：连通各轨道产出

检查以下集成点，修复任何断开的连接：

a) 轨道 A 新增的深钻(deep_drill)、沙盘(sandbox_what_if)、压力测试(stress_test_product) 等函数，是否在 text_router.py 中有对应的飞书指令注册？如果没有，补上。

b) 轨道 C 新增的 KB 字段（confidence_score, uncertainty_range, derived_from, observed_at），轨道 A 的 Layer 2 提炼是否在填充这些字段？如果没有，在提炼 prompt 中增加这些字段的提取指引。

c) 轨道 D 新增的模块（trust_tracker, guardrail_engine, load_manager 等），是否有被 text_router 或 deep_research 调用？检查每个模块是否有至少一个调用入口。未被调用的，在合适的位置添加调用。

d) 轨道 A 的学习系统（W1-W3）生成的 search_learning.jsonl, agent_lessons.yaml, model_effectiveness.jsonl，是否在对应的搜索/Agent/模型选择流程中被读取？如果没有，补上读取逻辑。

e) 轨道 B 的学习系统（W4）生成的 output_preferences.yaml，是否在报告生成时被读取？如果没有，补上。

f) 轨道 C 的学习系统（W5-W7）生成的 prd_learning.yaml, critic_evolved_rules.yaml，是否被 PRD 生成和 Critic 读取？如果没有，补上。

每修复一个集成点：
git add -A && git commit -m "fix: integrate [描述]" && git push origin main

## 4. 自动化验证

全部修完后，运行测试套件（如果轨道 D 已创建 test_suite.py）：
python scripts/test_suite.py

如果 test_suite.py 不存在，运行基础 import 验证：
python -c "
import sys; sys.path.insert(0, '.')
for m in ['scripts.tonight_deep_research', 'scripts.feishu_handlers.text_router', 'src.tools.knowledge_base']:
    try: __import__(m); print(f'  {m.split(chr(46))[-1]} OK')
    except Exception as e: print(f'  {m.split(chr(46))[-1]} FAIL: {e}')
for m in ['handoff_processor','system_log_generator','work_memory','roi_tracker','decision_logger','trust_tracker','brand_layer','collaboration','insight_engine','crm_lite','demo_generator','guardrail_engine','load_manager']:
    try: __import__(f'scripts.{m}'); print(f'  {m} OK')
    except Exception as e: print(f'  {m} FAIL: {e}')
"

如果有 import 失败，分析原因并修复。

## 5. 触发自愈系统首次自检

如果 scripts/self_heal.py 存在：
python scripts/self_heal.py

把自检结果贴出来。

不要重启服务。
```

---

## 三、关于验证自动化

验证不需要你手动操作。集成修复 CC 指令的第 4 步和第 5 步就是自动化验证：
- 第 4 步：import 验证（CC 自己跑，自己看结果，自己修）
- 第 5 步：自愈系统自检（测试套件 + 自动修复）

CC 会把最终结果贴出来。你只需要看最后的总结。
