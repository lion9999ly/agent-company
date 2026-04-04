"""轻量 CRM — 联系人和沟通记录管理
@description: 简化的联系人管理和沟通记录追踪
@dependencies: 无
@last_modified: 2026-04-04
"""
import yaml, time, re
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
CRM_PATH = PROJECT_ROOT / ".ai-state" / "contacts.yaml"


def parse_communication(text: str) -> dict:
    """从自然语言解析沟通记录

    Args:
        text: 如 '歌尔张工，讨论了产能问题，对方承诺下周给报价'

    Returns:
        解析后的沟通记录结构
    """
    # 尝试提取公司名
    companies = ["歌尔", "立讯", "舜宇", "京东方", "华星", "JBD", "Qualcomm", "MTK"]
    company = None
    for c in companies:
        if c in text:
            company = c
            break

    # 尝试提取联系人
    contact_match = re.search(r'([\u4e00-\u9fff]{2,3}工|[\u4e00-\u9fff]{2,4}|[A-Za-z]+)', text)

    return {
        "company": company or "未知",
        "contact": contact_match.group(1) if contact_match else "未知",
        "content": text,
        "timestamp": time.strftime('%Y-%m-%d %H:%M'),
    }


def add_communication(company: str, contact: str, content: str):
    """添加沟通记录"""
    CRM_PATH.parent.mkdir(parents=True, exist_ok=True)
    if CRM_PATH.exists():
        data = yaml.safe_load(CRM_PATH.read_text(encoding='utf-8')) or {"contacts": [], "communications": []}
    else:
        data = {"contacts": [], "communications": []}

    data["communications"].append({
        "company": company,
        "contact": contact,
        "content": content,
        "timestamp": time.strftime('%Y-%m-%d %H:%M'),
    })
    CRM_PATH.write_text(yaml.dump(data, allow_unicode=True), encoding='utf-8')


def get_company_history(company: str) -> list:
    """获取某公司的沟通历史"""
    if not CRM_PATH.exists():
        return []
    data = yaml.safe_load(CRM_PATH.read_text(encoding='utf-8'))
    return [c for c in data.get("communications", []) if company.lower() in c.get("company", "").lower()]


def add_contact(name: str, company: str, title: str = "", phone: str = "", email: str = ""):
    """添加联系人"""
    CRM_PATH.parent.mkdir(parents=True, exist_ok=True)
    if CRM_PATH.exists():
        data = yaml.safe_load(CRM_PATH.read_text(encoding='utf-8')) or {"contacts": [], "communications": []}
    else:
        data = {"contacts": [], "communications": []}

    data["contacts"].append({
        "name": name,
        "company": company,
        "title": title,
        "phone": phone,
        "email": email,
        "added_at": time.strftime('%Y-%m-%d %H:%M'),
    })
    CRM_PATH.write_text(yaml.dump(data, allow_unicode=True), encoding='utf-8')


def get_all_contacts() -> list:
    """获取所有联系人"""
    if not CRM_PATH.exists():
        return []
    data = yaml.safe_load(CRM_PATH.read_text(encoding='utf-8'))
    return data.get("contacts", [])


def search_contacts(query: str) -> list:
    """搜索联系人"""
    all_contacts = get_all_contacts()
    query_lower = query.lower()
    return [c for c in all_contacts if
            query_lower in c.get("name", "").lower() or
            query_lower in c.get("company", "").lower()]


if __name__ == "__main__":
    # 测试添加
    add_contact("张工", "歌尔", "项目经理")
    add_communication("歌尔", "张工", "讨论了产能问题，对方承诺下周给报价")
    print("CRM 测试完成")