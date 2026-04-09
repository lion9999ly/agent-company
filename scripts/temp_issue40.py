"""临时脚本：创建 Issue #40"""
import requests
from pathlib import Path

env_file = Path(__file__).parent.parent / ".env"
token = ""
if env_file.exists():
    for line in env_file.read_text(encoding="utf-8").splitlines():
        if line.startswith("GITHUB_TOKEN="):
            token = line.split("=", 1)[1].strip()
            break

if not token:
    print("ERROR: GITHUB_TOKEN not found")
    exit(1)

title = "[修复] 第五轮 - 云文档路径修复 + TaskSpec诊断 + Issue改requests - 2026-04-09"
body = """## 修复清单

### #1 云文档：lark-cli 相对路径问题
- **根因**: lark-cli 要求 `--markdown @file` 必须是相对路径，不能是系统临时目录的绝对路径
- **诊断输出**:
```
[get_or_create_doc] stderr: --markdown: invalid file path "C:\\Users\\...\\Temp\\tmpxxx.md":
--file must be a relative path within the current directory
```
- **修复**: 把临时文件放在当前工作目录下（`.temp_doc_xxx.md`）
- **验证**: `update_doc('测试云文档-第五轮', '# 测试内容')` 返回 `https://www.feishu.cn/docx/xxx`

### #2 TaskSpec 确认：feishu 参数诊断
- **位置**: `scripts/roundtable/roundtable.py` pre_check_task_spec
- **新增**: `print(f"[TaskSpec] 审查有问题，self.feishu={self.feishu}, type={type(self.feishu)}")`
- **目的**: 下次圆桌跑时看日志确认 feishu 参数是否为 None
- **从 roundtable_handler.py 看到**: feishu 是 FeishuNotifier() 对象（有 notify 方法）

### #3 Issue 自动创建：gh CLI 改 requests
- **修复**: 把 subprocess.run(["gh", ...]) 替换为 requests.post()
- **原因**: gh CLI 在 Windows bash 环境不可用
- **验证**: 已多次成功用 requests 创建 Issue

## Git Commit
- 9c85cf8

## 文件变更
- `scripts/feishu_output.py` - 云文档临时文件改相对路径 + 诊断日志
- `scripts/roundtable/__init__.py` - Issue 创建改 requests
- `scripts/roundtable/roundtable.py` - TaskSpec feishu 参数诊断

---
*由 Claude Code 创建*
"""

url = "https://api.github.com/repos/lion9999ly/agent-company/issues"
headers = {
    "Authorization": f"token {token}",
    "Accept": "application/vnd.github.v3+json"
}
data = {
    "title": title,
    "body": body,
    "labels": ["bugfix", "roundtable"]
}

response = requests.post(url, headers=headers, json=data)
if response.status_code == 201:
    issue = response.json()
    print(f"SUCCESS: Issue #{issue['number']} created")
    print(f"URL: {issue['html_url']}")
else:
    print(f"ERROR: {response.status_code}")
    print(response.text[:500])