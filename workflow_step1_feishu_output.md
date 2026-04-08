# CC 指令：工作流升级 Step 1 — 飞书 CLI 作为输出层

> **目标**：所有系统输出从"本地文件+飞书消息"升级为"飞书云文档+多维表格"
> **前提**：飞书 CLI 已安装验证通过（commit b577e5b）
> **原则**：不改消息接收逻辑（feishu_sdk 长连接保留），只改输出方式

---

## 总览：6 项改造

| # | 改造 | 当前 | 升级后 |
|---|------|------|--------|
| 1 | 圆桌结果输出 | 本地 HTML 文件路径 | 飞书云文档（可手机查看）|
| 2 | system_status 展示 | 飞书消息（2000字截断）| 飞书云文档实时更新 |
| 3 | 竞品监控报告 | 飞书消息 | 飞书多维表格 + 仪表盘 |
| 4 | 自动验证报告 | 终端输出 | 飞书云文档 |
| 5 | model_registry 更新 | 缺 gpt-5.3-codex/grok-3 | 补齐并配置路由 |
| 6 | 通用输出工具封装 | 无 | feishu_output.py 统一接口 |

---

## #1 圆桌结果输出 → 飞书云文档

**当前**：圆桌完成后飞书消息 `🎯 任务完成：demo_outputs/hud_demo_roundtable.html`，Leo 需要到电脑打开文件。

**改为**：

```python
# scripts/roundtable/__init__.py run_task() 末尾

# 原来：只发文件路径
# await feishu.notify(f"🎯 任务完成：{task.output_path}")

# 改为：创建飞书云文档 + 发链接
import subprocess

# HTML 文件内容太长不适合直接放云文档，创建一个摘要文档
summary_content = f"""# 圆桌任务完成：{task.topic}

## 执行摘要
{rt_result.executive_summary[:1500]}

## 验收标准通过情况
{verify_summary}

## 产物
- 本地路径：{task.output_path}
- 讨论日志：{rt_result.full_log_path}
- 方案层轮数：{rt_result.rounds}

## 待评价
请在本文档评论区写下你的评价，系统会自动解析并更新规则库。
"""

result = subprocess.run(
    ["lark-cli", "docs", "+create", 
     "--title", f"圆桌结果：{task.topic}", 
     "--markdown", summary_content,
     "--as", "bot"],
    capture_output=True, text=True, timeout=30
)

# 解析文档链接
doc_url = _extract_doc_url(result.stdout)

await feishu.notify(f"🎯 任务完成\n📄 结果文档：{doc_url}\n💬 请在文档评论区写评价")
```

**冒烟测试**：跑一次 `圆桌:hud_demo`，确认飞书收到云文档链接而非本地路径。

---

## #2 system_status → 飞书云文档实时更新

**当前**：发 `状态` 返回飞书消息（有字数限制），内容是文件内容截断。

**改为**：维护一个固定的飞书云文档，每次 commit 后更新内容。

```python
# 新建 scripts/feishu_output.py

import subprocess
import json
from pathlib import Path

# 飞书文档 ID 存储（首次创建后记录）
DOC_REGISTRY_PATH = Path(".ai-state/feishu_doc_registry.json")

def get_or_create_doc(title: str, initial_content: str = "") -> str:
    """获取已有文档 ID，或创建新文档"""
    registry = _load_registry()
    
    if title in registry:
        return registry[title]  # 返回已有文档 ID
    
    # 创建新文档
    result = subprocess.run(
        ["lark-cli", "docs", "+create",
         "--title", title,
         "--markdown", initial_content or f"# {title}\n初始化中...",
         "--as", "bot"],
        capture_output=True, text=True, timeout=30
    )
    doc_id = _extract_doc_id(result.stdout)
    
    if doc_id:
        registry[title] = doc_id
        _save_registry(registry)
    
    return doc_id

def update_doc(title: str, content: str):
    """更新飞书云文档内容"""
    doc_id = get_or_create_doc(title)
    if not doc_id:
        return False
    
    subprocess.run(
        ["lark-cli", "docs", "+update",
         "--document-id", doc_id,
         "--markdown", content,
         "--as", "bot"],
        capture_output=True, text=True, timeout=30
    )
    return True

def _load_registry():
    if DOC_REGISTRY_PATH.exists():
        return json.loads(DOC_REGISTRY_PATH.read_text(encoding="utf-8"))
    return {}

def _save_registry(data):
    DOC_REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    DOC_REGISTRY_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
```

**system_status 更新逻辑**：

```python
# 每次 commit 后，或飞书发 "状态" 时
from scripts.feishu_output import update_doc

status_content = Path("system_status.md").read_text(encoding="utf-8")
update_doc("系统状态", status_content)

# 飞书回复文档链接而非内容
send_reply(reply_target, f"📊 系统状态：{doc_url}")
```

**冒烟测试**：飞书发 `状态`，确认收到云文档链接，打开能看到完整内容。

---

## #3 竞品监控 → 飞书多维表格

**当前**：竞品监控结果作为飞书消息推送，字数多了看不清，无法排序筛选。

**改为**：创建飞书多维表格，每条监控结果是一行记录。

```python
# scripts/competitor_monitor.py 输出改造

def write_to_bitable(results: list):
    """写入飞书多维表格"""
    # 首次创建表格
    bitable_id = get_or_create_bitable("竞品监控")
    
    for r in results:
        if r.get("relevance") == "low":
            continue  # 低相关不入表
        
        record = {
            "日期": r["date"],
            "来源层": r["layer"],
            "标题": r["title"],
            "摘要": r["summary"][:500],
            "相关度": r["relevance"],
            "影响维度": r.get("impact_dimension", ""),
            "影响说明": r.get("impact_detail", ""),
            "建议动作": r.get("suggested_action", ""),
            "来源": r["source"],
        }
        
        subprocess.run(
            ["lark-cli", "bitable", "+records-create",
             "--app-token", bitable_id,
             "--table-id", table_id,
             "--record", json.dumps(record, ensure_ascii=False),
             "--as", "bot"],
            capture_output=True, text=True, timeout=15
        )
```

**飞书推送改为**：
```
🔔 竞品监控完成，发现 3 条高相关动态
📊 查看详情：{bitable_url}
```

**冒烟测试**：手动触发竞品监控，确认多维表格创建并有数据。

---

## #4 自动验证报告 → 飞书云文档

```python
# scripts/auto_restart_and_verify.py 输出改造

# 验证完成后
report_md = f"""# 自动验证报告
时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}

## 结果：{passed}/{total} 通过

| 项目 | 状态 | 详情 |
|------|------|------|
{table_rows}
"""

update_doc("验证报告", report_md)
send_reply(reply_target, f"🔍 验证完成：{passed}/{total}\n📄 详情：{doc_url}")
```

---

## #5 model_registry 更新

**当前缺失**：Azure 部署了 gpt-5.3-codex 和 grok-3 但 model_registry.yaml 没配置。

```yaml
# src/config/model_registry.yaml 新增

gpt_5_3_codex:
  provider: azure_openai
  model: gpt-5.3-codex
  deployment: gpt-5.3-codex
  endpoint_env: AZURE_OPENAI_ENDPOINT_SHARE
  api_key_env: AZURE_OPENAI_KEY_SHARE
  api_version: "2024-12-01-preview"
  purpose: code_generation
  max_tokens: 8192
  temperature: 0.1
  capabilities: [code, html, json, debug]
  cost_tier: "$$$"
  performance: 5

grok_3:
  provider: azure_openai
  model: grok-3
  deployment: grok-3
  endpoint_env: AZURE_OPENAI_ENDPOINT_SHARE
  api_key_env: AZURE_OPENAI_KEY_SHARE
  api_version: "2024-12-01-preview"
  purpose: critic_cross_review
  max_tokens: 4096
  temperature: 0.1
  capabilities: [analysis, review, reasoning]
  cost_tier: "$$$"
  performance: 4
```

**路由规则更新**：
```yaml
routing_rules:
  task_model_mapping:
    code_generation: [gpt_5_3_codex, gpt_5_4, gpt_4o]
    # Generator HTML 生成优先用 codex
    critic_cross_review: [grok_3, gemini_3_1_pro]
    # Critic 交叉评审可用 grok-3
```

**冒烟测试**：`python src/utils/model_gateway.py` 确认新模型可调用。

---

## #6 通用输出工具封装

上面的 `feishu_output.py` 就是这个——统一接口，所有模块用同一套方法输出到飞书。

额外加一个便捷方法：

```python
def notify_with_doc(reply_target, send_reply, title, content, 
                     short_msg=""):
    """发飞书消息 + 同步创建/更新云文档"""
    doc_url = update_doc(title, content)
    msg = short_msg or f"📄 {title}"
    if doc_url:
        msg += f"\n🔗 {doc_url}"
    send_reply(reply_target, msg)
```

---

## 执行顺序

```
1. 创建 scripts/feishu_output.py（通用输出工具）
2. model_registry.yaml 更新（加 gpt-5.3-codex + grok-3）
3. 圆桌结果输出改造
4. system_status 输出改造 + 飞书 "状态" 指令更新
5. 竞品监控输出改造
6. 自动验证报告输出改造
→ commit: feat: feishu CLI output layer — cloud docs + bitable
→ push
→ 重启 SDK
→ 验证：飞书发 "状态" 确认收到云文档链接
```

---

## 验证清单

```
✅ feishu_output.py 创建
✅ model_registry 更新（gpt-5.3-codex + grok-3 可调用）
✅ 飞书 "状态" → 返回云文档链接
✅ 竞品监控 → 多维表格有数据
✅ 验证报告 → 云文档有内容
✅ git push 完成
```
