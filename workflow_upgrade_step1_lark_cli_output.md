# CC 指令：工作流升级 Step 1 — 飞书 CLI 作为输出层

> **前提**：飞书 CLI 已安装验证通过（3/3）
> **原则**：不改消息接收逻辑，只把输出从 SDK send_reply 迁移到飞书 CLI
> **备份**：`git tag backup-before-lark-cli-migration`

---

## 总览：8 项改动

| # | 改动 | 文件 |
|---|------|------|
| 1 | 创建飞书 CLI 输出封装层 | 新建 scripts/feishu_handlers/lark_cli_output.py |
| 2 | 圆桌结果 → 飞书云文档 | roundtable/__init__.py |
| 3 | system_status.md → 飞书云文档同步 | system_status 更新逻辑 |
| 4 | 竞品监控报告 → 飞书多维表格 | competitor_monitor.py |
| 5 | 验证报告 → 飞书云文档 | auto_restart_and_verify.py |
| 6 | model_registry.yaml 更新 | src/config/model_registry.yaml |
| 7 | 圆桌角色模型更新 | scripts/roundtable/roles.py |
| 8 | HUD Demo TaskSpec 更新 | .ai-state/task_specs/hud_demo.json |

---

## #1 飞书 CLI 输出封装层

```python
# scripts/feishu_handlers/lark_cli_output.py
"""
飞书 CLI 输出封装——统一所有通过 CLI 操作飞书的方法
所有对外输出优先走 CLI，CLI 失败时 fallback 到 SDK send_reply
"""
import subprocess
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# Leo 的 open_id（从 .env 读取）
import os
LEO_OPEN_ID = os.getenv("LEO_OPEN_ID", "ou_8e5e4f183e9eca4241378e96bac3a751")
LEO_CHAT_ID = os.getenv("LEO_CHAT_ID", "oc_43bca641a75a5beed8215541845c7b73")


def cli_send_message(text: str, chat_id: str = None) -> bool:
    """通过飞书 CLI 发送消息"""
    target = chat_id or LEO_CHAT_ID
    try:
        result = subprocess.run(
            ["lark-cli", "im", "+messages-send",
             "--chat-id", target, "--text", text, "--as", "bot"],
            capture_output=True, text=True, timeout=15
        )
        return result.returncode == 0
    except Exception as e:
        print(f"[LarkCLI] 发送消息失败: {e}")
        return False


def cli_create_doc(title: str, content_md: str) -> str:
    """通过飞书 CLI 创建云文档，返回文档链接"""
    try:
        result = subprocess.run(
            ["lark-cli", "docs", "+create",
             "--title", title, "--markdown", content_md, "--as", "bot"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            # 解析输出拿到文档链接
            output = result.stdout.strip()
            # 尝试从输出中提取 URL
            for line in output.split("\n"):
                if "feishu.cn" in line or "larkoffice.com" in line:
                    return line.strip()
            return output
        return ""
    except Exception as e:
        print(f"[LarkCLI] 创建文档失败: {e}")
        return ""


def cli_update_doc(doc_id: str, content_md: str) -> bool:
    """通过飞书 CLI 更新云文档内容"""
    try:
        result = subprocess.run(
            ["lark-cli", "docs", "+update",
             "--document-id", doc_id, "--markdown", content_md, "--as", "bot"],
            capture_output=True, text=True, timeout=30
        )
        return result.returncode == 0
    except Exception as e:
        print(f"[LarkCLI] 更新文档失败: {e}")
        return False


def cli_create_or_update_bitable_record(app_token: str, table_id: str,
                                         fields: dict) -> bool:
    """通过飞书 CLI 写入多维表格记录"""
    try:
        fields_json = json.dumps(fields, ensure_ascii=False)
        result = subprocess.run(
            ["lark-cli", "bitable", "+records-create",
             "--app-token", app_token, "--table-id", table_id,
             "--fields", fields_json, "--as", "bot"],
            capture_output=True, text=True, timeout=15
        )
        return result.returncode == 0
    except Exception as e:
        print(f"[LarkCLI] 写入多维表格失败: {e}")
        return False


# === 兼容层：优先 CLI，失败 fallback 到 SDK ===
def smart_send(text: str, reply_target: str = None, send_reply_func=None):
    """智能发送：优先 CLI，失败走 SDK"""
    if cli_send_message(text):
        return True
    if send_reply_func and reply_target:
        send_reply_func(reply_target, text)
        return True
    return False
```

## #2 圆桌结果 → 飞书云文档

```python
# roundtable/__init__.py 的 run_task() 末尾，输出阶段改造

# 原来：只保存本地文件 + 飞书发消息通知路径
# 改为：保存本地 + 创建飞书云文档 + 飞书通知带文档链接

from scripts.feishu_handlers.lark_cli_output import cli_create_doc, cli_send_message

# 保存本地文件（保留）
Path(task.output_path).write_text(output, encoding='utf-8')

# 创建飞书云文档（新增）
if task.output_type in ("html", "markdown"):
    doc_title = f"圆桌产出：{task.topic} ({datetime.now().strftime('%m-%d %H:%M')})"
    if task.output_type == "html":
        # HTML 不能直接放飞书文档，放摘要 + 本地路径
        doc_content = f"# {task.topic}\n\n产出类型：HTML\n本地路径：{task.output_path}\n\n"
        doc_content += f"## 执行摘要\n{rt_result.executive_summary[:1000]}"
    else:
        doc_content = output[:5000]  # markdown 直接放
    
    doc_link = cli_create_doc(doc_title, doc_content)
    if doc_link:
        cli_send_message(f"🎯 圆桌任务完成：{task.topic}\n📄 文档：{doc_link}")
    else:
        cli_send_message(f"🎯 圆桌任务完成：{task.output_path}")
```

## #3 system_status.md → 飞书云文档同步

```python
# system_status 更新逻辑中，每次更新 md 后同步到飞书

# 首次创建文档，保存 doc_id 到 .ai-state/feishu_doc_ids.json
# 后续更新同一个文档

import json
from scripts.feishu_handlers.lark_cli_output import cli_create_doc, cli_update_doc

DOC_IDS_PATH = PROJECT_ROOT / ".ai-state" / "feishu_doc_ids.json"

def sync_status_to_feishu():
    status_content = Path(".ai-state/system_status.md").read_text(encoding="utf-8")
    
    doc_ids = {}
    if DOC_IDS_PATH.exists():
        doc_ids = json.loads(DOC_IDS_PATH.read_text(encoding="utf-8"))
    
    if "system_status" in doc_ids:
        # 更新已有文档
        cli_update_doc(doc_ids["system_status"], status_content)
    else:
        # 首次创建
        link = cli_create_doc("系统状态（实时）", status_content)
        if link:
            # 从 link 中提取 doc_id 并保存
            doc_ids["system_status"] = extract_doc_id(link)
            DOC_IDS_PATH.write_text(json.dumps(doc_ids, ensure_ascii=False, indent=2))
```

## #4 竞品监控报告 → 飞书多维表格

```python
# competitor_monitor.py 输出改造

# 创建多维表格（首次）或追加记录
# 表结构：日期 | 层级 | 标题 | 摘要 | 相关度 | 影响维度 | 建议动作 | 来源

from scripts.feishu_handlers.lark_cli_output import cli_create_or_update_bitable_record

def save_to_bitable(assessed_result: dict, app_token: str, table_id: str):
    fields = {
        "日期": assessed_result.get("date", ""),
        "层级": assessed_result.get("layer", ""),
        "标题": assessed_result.get("title", ""),
        "摘要": assessed_result.get("summary", "")[:500],
        "相关度": assessed_result.get("relevance", "low"),
        "影响维度": assessed_result.get("impact_dimension", ""),
        "建议动作": assessed_result.get("suggested_action", ""),
        "来源": assessed_result.get("source", "")
    }
    cli_create_or_update_bitable_record(app_token, table_id, fields)
```

注意：多维表格的 app_token 和 table_id 需要首次手动创建表后记录到 `.ai-state/feishu_doc_ids.json`。或者用 CLI 自动创建：
```bash
lark-cli bitable +apps-create --name "竞品监控" --as bot
```

## #5 验证报告 → 飞书云文档

```python
# auto_restart_and_verify.py 结果输出改造

from scripts.feishu_handlers.lark_cli_output import cli_create_doc, cli_send_message

def send_verify_report(report_md: str):
    # 创建文档
    link = cli_create_doc(
        f"验证报告 {datetime.now().strftime('%m-%d %H:%M')}",
        report_md
    )
    # 飞书消息带链接
    if link:
        cli_send_message(f"✅ 验证完成\n📄 报告：{link}")
    else:
        # fallback: 直接发消息
        cli_send_message(report_md[:2000])
```

## #6 model_registry.yaml 更新

```yaml
# 新增模型配置

gpt_5_3_codex:
    provider: azure_openai
    model: gpt-5.3-codex
    deployment: gpt-5.3-codex
    endpoint_env: AZURE_SHARE_ENDPOINT  # ai-share 端点
    api_key_env: AZURE_SHARE_API_KEY
    api_version: "2024-12-01-preview"
    purpose: "代码生成专用"
    max_tokens: 8192
    temperature: 0.1
    capabilities: ["code_generation", "html_generation", "refactoring"]
    cost_tier: "$$$"
    performance: 5

grok_3:
    provider: azure_openai
    model: grok-3
    deployment: grok-3
    endpoint_env: AZURE_SHARE_ENDPOINT
    api_key_env: AZURE_SHARE_API_KEY
    api_version: "2024-12-01-preview"
    purpose: "Critic 交叉评审"
    max_tokens: 4096
    temperature: 0.1
    capabilities: ["review", "analysis", "critique"]
    cost_tier: "$$"
    performance: 4
```

同时更新 routing_rules：
```yaml
routing_rules:
    task_model_mapping:
        code_generation: ["gpt_5_3_codex", "gpt_5_4", "gpt_4o_norway"]
        html_generation: ["gpt_5_3_codex", "gpt_5_4"]
        review: ["grok_3", "gemini_3_1_pro", "gpt_4o_norway"]
```

## #7 圆桌角色模型更新

```python
# scripts/roundtable/roles.py 中 ROLE_REGISTRY 更新

# Generator 可以用 gpt-5.3-codex（代码专用）
# Critic 可以用 grok-3 做交叉评审

# Generator 模型优先级：
# HTML/代码类：gpt_5_3_codex → gpt_5_4
# 文档类：gpt_5_4

# Critic 交叉评审：
# 主评审：gemini_3_1_pro
# 交叉评审：grok_3（如果可用）
```

## #8 HUD Demo TaskSpec 更新

hud_demo.json 确认包含：
```json
{
    "generator_input_mode": "raw_proposal",
    "generator_model_preference": "gpt_5_3_codex"
}
```

---

## 执行 + 验证

```
git tag backup-before-lark-cli-migration

#1-5 飞书 CLI 输出层 → commit: feat: lark-cli output layer
#6-8 模型配置更新 → commit: feat: add gpt-5.3-codex and grok-3, update routing

验证：
- 飞书发 "状态" → 应返回内容 + 云文档链接
- 手动触发竞品监控一次 → 检查多维表格有没有写入
- python src/utils/model_gateway.py → 确认新模型可调用
```
