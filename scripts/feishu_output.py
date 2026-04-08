"""
@description: 飞书输出工具 — 统一输出到飞书云文档/多维表格
@dependencies: subprocess, lark-cli
@last_modified: 2026-04-08
"""
import subprocess
import json
import shutil
import os
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 飞书文档 ID 存储（首次创建后记录）
DOC_REGISTRY_PATH = PROJECT_ROOT / ".ai-state" / "feishu_doc_registry.json"


def _find_lark_cli() -> str:
    """查找 lark-cli 可执行文件路径"""
    # 尝试直接调用（依赖 PATH）
    result = shutil.which("lark-cli")
    if result:
        return result

    # Windows npm 安装路径
    common_paths = [
        "C:\\Users\\uih00653\\nodejs\\lark-cli.cmd",
        os.path.expanduser("~\\nodejs\\lark-cli.cmd"),
        "lark-cli",  # 回退到 PATH
    ]

    for path in common_paths:
        if Path(path).exists() or path == "lark-cli":
            return path

    return "lark-cli"  # 默认回退


LARK_CLI = _find_lark_cli()


def _load_registry() -> dict:
    """加载文档注册表"""
    if DOC_REGISTRY_PATH.exists():
        try:
            return json.loads(DOC_REGISTRY_PATH.read_text(encoding="utf-8"))
        except:
            return {}
    return {}


def _save_registry(data: dict):
    """保存文档注册表"""
    DOC_REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    DOC_REGISTRY_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _extract_doc_id(output: str) -> Optional[str]:
    """从 lark-cli 输出提取文档 ID"""
    try:
        data = json.loads(output)
        return data.get("data", {}).get("doc_id")
    except:
        # 尝试正则提取
        import re
        match = re.search(r'"doc_id":\s*"([^"]+)"', output)
        if match:
            return match.group(1)
    return None


def _extract_doc_url(output: str) -> Optional[str]:
    """从 lark-cli 输出提取文档 URL"""
    try:
        data = json.loads(output)
        return data.get("data", {}).get("doc_url")
    except:
        import re
        match = re.search(r'"doc_url":\s*"([^"]+)"', output)
        if match:
            return match.group(1)
    return None


def get_or_create_doc(title: str, initial_content: str = "") -> tuple:
    """获取已有文档 ID，或创建新文档

    Returns:
        (doc_id, doc_url) 元组
    """
    registry = _load_registry()

    if title in registry:
        entry = registry[title]
        return entry.get("doc_id"), entry.get("doc_url")

    # 创建新文档（使用 stdin 传递内容，避免 Windows 命令行截断）
    content = initial_content or f"# {title}\n\n初始化中..."
    result = subprocess.run(
        [LARK_CLI, "docs", "+create",
         "--title", title,
         "--markdown", "-",  # 使用 stdin
         "--as", "bot"],
        input=content,
        capture_output=True, text=True, timeout=30,
        encoding='utf-8'
    )

    doc_id = _extract_doc_id(result.stdout)
    doc_url = _extract_doc_url(result.stdout)

    if doc_id:
        registry[title] = {"doc_id": doc_id, "doc_url": doc_url}
        _save_registry(registry)

    return doc_id, doc_url


def update_doc(title: str, content: str) -> Optional[str]:
    """更新飞书云文档内容

    Returns:
        doc_url 或 None
    """
    doc_id, doc_url = get_or_create_doc(title)

    if not doc_id:
        # 创建新文档
        doc_id, doc_url = get_or_create_doc(title, content)
        return doc_url

    # 更新已有文档（使用 stdin 传递内容）
    result = subprocess.run(
        [LARK_CLI, "docs", "+update",
         "--doc", doc_id,
         "--markdown", "-",  # 使用 stdin
         "--as", "bot"],
        input=content,
        capture_output=True, text=True, timeout=30,
        encoding='utf-8'
    )

    return doc_url


def create_doc(title: str, content: str) -> Optional[str]:
    """创建新的飞书云文档（不重用）

    Returns:
        doc_url 或 None
    """
    result = subprocess.run(
        [LARK_CLI, "docs", "+create",
         "--title", title,
         "--markdown", "-",  # 使用 stdin
         "--as", "bot"],
        input=content,
        capture_output=True, text=True, timeout=30,
        encoding='utf-8'
    )

    return _extract_doc_url(result.stdout)


def notify_with_doc(reply_target: str, send_reply, title: str, content: str,
                    short_msg: str = "") -> Optional[str]:
    """发飞书消息 + 同步创建/更新云文档

    Args:
        reply_target: 回复目标
        send_reply: 发送函数
        title: 文档标题
        content: 文档内容
        short_msg: 短消息（可选）

    Returns:
        doc_url 或 None
    """
    doc_url = update_doc(title, content)
    msg = short_msg or f"📄 {title}"
    if doc_url:
        msg += f"\n🔗 {doc_url}"
    send_reply(reply_target, msg)
    return doc_url


def get_or_create_bitable(name: str) -> Optional[str]:
    """获取或创建多维表格

    Returns:
        app_token 或 None
    """
    registry = _load_registry()
    key = f"bitable:{name}"

    if key in registry:
        return registry[key].get("app_token")

    # 创建多维表格
    result = subprocess.run(
        [LARK_CLI, "bitable", "+create",
         "--name", name,
         "--as", "bot"],
        capture_output=True, text=True, timeout=30,
        encoding='utf-8', errors='ignore'
    )

    try:
        data = json.loads(result.stdout)
        app_token = data.get("data", {}).get("app", {}).get("app_token")
        if app_token:
            registry[key] = {"app_token": app_token}
            _save_registry(registry)
        return app_token
    except:
        return None


def add_bitable_record(app_token: str, table_id: str, record: dict) -> bool:
    """向多维表格添加记录

    Args:
        app_token: 多维表格 token
        table_id: 数据表 ID
        record: 记录数据

    Returns:
        是否成功
    """
    result = subprocess.run(
        [LARK_CLI, "bitable", "+records-create",
         "--app-token", app_token,
         "--table-id", table_id,
         "--record", json.dumps(record, ensure_ascii=False),
         "--as", "bot"],
        capture_output=True, text=True, timeout=15,
        encoding='utf-8', errors='ignore'
    )

    try:
        data = json.loads(result.stdout)
        return data.get("ok", False)
    except:
        return False


# 导出接口
__all__ = [
    "get_or_create_doc",
    "update_doc",
    "create_doc",
    "notify_with_doc",
    "get_or_create_bitable",
    "add_bitable_record",
]