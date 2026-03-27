"""
@description: 飞书移动端审批执行器 - Agent 提出修复建议，用户审批后自动执行
@dependencies: json, pathlib, datetime
@last_modified: 2026-03-19
"""
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any
from dataclasses import dataclass, asdict


PENDING_DIR = Path(__file__).resolve().parent.parent.parent / ".ai-state" / "pending_fixes"
HISTORY_DIR = Path(__file__).resolve().parent.parent.parent / ".ai-state" / "fix_history"


@dataclass
class FixProposal:
    """修复提案"""
    fix_id: str
    title: str
    description: str
    file_path: str
    old_content: str
    new_content: str
    risk_level: str  # low / medium / high
    created_at: str
    status: str = "pending"  # pending / approved / rejected / executed


def create_proposal(title: str, description: str, file_path: str,
                    old_content: str, new_content: str, risk_level: str = "low") -> FixProposal:
    """创建修复提案并保存到磁盘"""
    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    fix_id = f"fix_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    proposal = FixProposal(
        fix_id=fix_id, title=title, description=description,
        file_path=file_path, old_content=old_content, new_content=new_content,
        risk_level=risk_level, created_at=datetime.now().isoformat(), status="pending"
    )
    filepath = PENDING_DIR / f"{fix_id}.json"
    filepath.write_text(json.dumps(asdict(proposal), ensure_ascii=False, indent=2), encoding="utf-8")
    return proposal


def get_pending_proposals() -> list:
    """获取所有待审批的提案"""
    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    proposals = []
    for f in sorted(PENDING_DIR.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if data.get("status") == "pending":
                proposals.append(data)
        except Exception:
            continue
    return proposals


def approve_and_execute(fix_id: str) -> Dict[str, Any]:
    """审批并执行修复"""
    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    filepath = PENDING_DIR / f"{fix_id}.json"
    if not filepath.exists():
        return {"success": False, "error": f"提案 {fix_id} 不存在"}

    data = json.loads(filepath.read_text(encoding="utf-8"))
    target_file = Path(data["file_path"])

    if not target_file.exists():
        return {"success": False, "error": f"目标文件 {data['file_path']} 不存在"}

    # 执行替换
    content = target_file.read_text(encoding="utf-8")
    if data["old_content"] not in content:
        return {"success": False, "error": "目标文件内容已变更，无法匹配原文"}

    new_content = content.replace(data["old_content"], data["new_content"], 1)
    target_file.write_text(new_content, encoding="utf-8")

    # 更新状态并移入历史
    data["status"] = "executed"
    data["executed_at"] = datetime.now().isoformat()
    history_path = HISTORY_DIR / f"{fix_id}.json"
    history_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    filepath.unlink()  # 从 pending 中删除

    return {"success": True, "fix_id": fix_id, "file": data["file_path"]}


def reject_proposal(fix_id: str, reason: str = "") -> Dict[str, Any]:
    """驳回提案"""
    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    filepath = PENDING_DIR / f"{fix_id}.json"
    if not filepath.exists():
        return {"success": False, "error": f"提案 {fix_id} 不存在"}

    data = json.loads(filepath.read_text(encoding="utf-8"))
    data["status"] = "rejected"
    data["rejected_at"] = datetime.now().isoformat()
    data["reject_reason"] = reason
    history_path = HISTORY_DIR / f"{fix_id}.json"
    history_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    filepath.unlink()

    return {"success": True, "fix_id": fix_id, "status": "rejected"}


def format_proposal_for_feishu(proposal: dict) -> str:
    """格式化提案为飞书消息"""
    risk_emoji = {"low": "🟢", "medium": "🟡", "high": "🔴"}.get(proposal["risk_level"], "⚪")
    return (
        f"📋 修复提案 [{proposal['fix_id']}]\n"
        f"标题: {proposal['title']}\n"
        f"风险: {risk_emoji} {proposal['risk_level']}\n"
        f"文件: {proposal['file_path']}\n"
        f"说明: {proposal['description']}\n\n"
        f"变更内容:\n"
        f"- 删除: {proposal['old_content'][:100]}...\n"
        f"+ 新增: {proposal['new_content'][:100]}...\n\n"
        f"回复「批准 {proposal['fix_id']}」执行\n"
        f"回复「驳回 {proposal['fix_id']}」拒绝"
    )