"""多模态知识入库 — 图片 OCR → 结构化提取 → KB
@description: 从 OCR 文本中提取结构化数据并入库
@dependencies: model_gateway, knowledge_base
@last_modified: 2026-04-04
"""
import json, re
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent


def process_image_to_kb(image_path: str, image_text: str, gateway) -> dict:
    """从 OCR 文本中提取结构化数据并入库

    支持: 报价单、数据表、名片、白板

    Args:
        image_path: 图片路径
        image_text: OCR 识别文本
        gateway: 模型网关实例

    Returns:
        提取的结构化数据
    """
    # 判断文档类型
    doc_type = _classify_document(image_text)

    if doc_type == "quotation":
        result = _extract_quotation(image_text, gateway)
    elif doc_type == "datasheet":
        result = _extract_datasheet(image_text, gateway)
    elif doc_type == "namecard":
        result = _extract_namecard(image_text, gateway)
    elif doc_type == "whiteboard":
        result = _extract_whiteboard(image_text, gateway)
    else:
        result = {"type": "unknown", "text": image_text}

    # 入库
    _save_to_kb(result, image_path)

    return result


def _classify_document(text: str) -> str:
    """分类文档类型"""
    if any(kw in text for kw in ["报价", "单价", "MOQ", "交期", "quotation", "price"]):
        return "quotation"
    elif any(kw in text for kw in ["规格", "参数", "spec", "datasheet", "voltage", "current"]):
        return "datasheet"
    elif any(kw in text for kw in ["名片", "电话", "邮箱", "手机", "微信"]):
        return "namecard"
    else:
        return "whiteboard"


def _extract_quotation(text: str, gateway) -> dict:
    """从报价单提取价格/MOQ/交期"""
    result = gateway.call("gemini_2_5_flash",
        f"从以下报价单 OCR 文本中提取结构化数据:\n\n{text[:2000]}\n\n"
        f"输出 JSON: {{"
        f"\"supplier\": \"供应商名\", \"items\": ["
        f"{{\"name\": \"产品名\", \"price\": \"单价\", \"moq\": \"最小订单量\", \"lead_time\": \"交期\"}}]}}",
        task_type="data_extraction")
    if result.get("success"):
        try:
            return json.loads(re.sub(r'^```json\s*|\s*```$', '', result["response"].strip()))
        except json.JSONDecodeError:
            pass
    return {"type": "quotation", "raw": text[:500]}


def _extract_namecard(text: str, gateway) -> dict:
    """从名片提取联系人信息"""
    result = gateway.call("gemini_2_5_flash",
        f"从以下名片 OCR 文本中提取联系人信息:\n\n{text}\n\n"
        f"输出 JSON: {{\"name\": \"\", \"company\": \"\", \"title\": \"\", \"phone\": \"\", \"email\": \"\", \"wechat\": \"\"}}",
        task_type="data_extraction")
    if result.get("success"):
        try:
            return json.loads(re.sub(r'^```json\s*|\s*```$', '', result["response"].strip()))
        except json.JSONDecodeError:
            pass
    return {"type": "namecard", "raw": text}


def _extract_datasheet(text: str, gateway) -> dict:
    """从数据表提取规格参数"""
    result = gateway.call("gemini_2_5_flash",
        f"从以下数据表 OCR 文本中提取规格参数:\n\n{text[:2000]}\n\n"
        f"输出 JSON: {{\"product\": \"产品名\", \"specs\": {{\"参数名\": \"参数值\"}}}}",
        task_type="data_extraction")
    if result.get("success"):
        try:
            return json.loads(re.sub(r'^```json\s*|\s*```$', '', result["response"].strip()))
        except json.JSONDecodeError:
            pass
    return {"type": "datasheet", "raw": text[:500]}


def _extract_whiteboard(text: str, gateway) -> dict:
    """从白板照片提取要点"""
    result = gateway.call("gemini_2_5_flash",
        f"从以下白板/笔记 OCR 文本中提取关键要点:\n\n{text[:2000]}\n\n"
        f"输出 JSON: {{\"title\": \"主题\", \"points\": [\"要点1\", \"要点2\"]}}",
        task_type="data_extraction")
    if result.get("success"):
        try:
            return json.loads(re.sub(r'^```json\s*|\s*```$', '', result["response"].strip()))
        except json.JSONDecodeError:
            pass
    return {"type": "whiteboard", "raw": text[:500]}


def _save_to_kb(data: dict, source_path: str):
    """保存提取结果到知识库"""
    import time
    try:
        from src.tools.knowledge_base import add_knowledge
        kb_entry = {
            "title": data.get("supplier", data.get("name", data.get("product", "未知来源")),
            "domain": "供应商" if data.get("type") == "quotation" else "技术参数",
            "content": json.dumps(data, ensure_ascii=False),
            "source": source_path,
            "confidence": 0.8,
            "tags": [data.get("type", "unknown")],
            "created_at": time.strftime('%Y-%m-%d %H:%M'),
        }
        add_knowledge(kb_entry)
    except ImportError:
        # 直接保存到文件
        kb_path = PROJECT_ROOT / "knowledge_base" / "multimodal" / f"doc_{int(time.time())}.json"
        kb_path.parent.mkdir(parents=True, exist_ok=True)
        kb_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == "__main__":
    print("多模态知识入库器已就绪")