"""
@description: 飞书自主开发助手 - 分析需求、读取代码、生成修改方案
@dependencies: src.utils.model_gateway, src.tools.fix_executor
@last_modified: 2026-03-21
"""
import sys
import re
import json
from pathlib import Path
from dataclasses import asdict

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.litellm_gateway import get_model_gateway
from src.tools.fix_executor import create_proposal, format_proposal_for_feishu

PROJECT_ROOT = Path(__file__).parent.parent


def _read_file_smart(filepath: str, max_lines: int = 200) -> str:
    """智能读取文件，超长时截取头尾"""
    full_path = PROJECT_ROOT / filepath
    if not full_path.exists():
        return f"[文件不存在: {filepath}]"
    lines = full_path.read_text(encoding="utf-8").splitlines()
    if len(lines) <= max_lines:
        return "\n".join(f"{i+1}: {l}" for i, l in enumerate(lines))
    head = lines[:100]
    tail = lines[-80:]
    return (
        "\n".join(f"{i+1}: {l}" for i, l in enumerate(head))
        + f"\n\n... ({len(lines) - 180} 行省略) ...\n\n"
        + "\n".join(f"{len(lines)-79+i}: {l}" for i, l in enumerate(tail))
    )


def _guess_target_files(request: str) -> list:
    """根据需求描述猜测需要修改的文件"""
    file_map = {
        "router": "src/graph/router.py",
        "feishu": "scripts/feishu_sdk_client.py",
        "gateway": "src/utils/model_gateway.py",
        "model_registry": "src/config/model_registry.yaml",
        "prompt": "src/config/agent_prompts.yaml",
        "slicer": "src/graph/context_slicer.py",
        "state": "src/schema/state.py",
        "tool_registry": "src/tools/tool_registry.py",
        "knowledge": "src/tools/knowledge_base.py",
        "fix_executor": "src/tools/fix_executor.py",
        "daily_learning": "scripts/daily_learning.py",
        "validator": "scripts/doc_sync_validator.py",
    }
    matched = []
    for keyword, path in file_map.items():
        if keyword in request.lower():
            matched.append(path)
    if not matched:
        matched = ["src/graph/router.py"]
    return matched


def generate_dev_proposal(request: str) -> dict:
    """分析开发需求，生成修改方案"""
    # 1. 猜测目标文件并读取
    target_files = _guess_target_files(request)
    file_contents = {}
    for f in target_files[:2]:
        file_contents[f] = _read_file_smart(f)

    # 2. 读取 context_board 获取项目上下文
    cb_path = PROJECT_ROOT / "context_board.md"
    context_board = ""
    if cb_path.exists():
        cb_text = cb_path.read_text(encoding="utf-8")
        context_board = cb_text[:2000]

    # 3. 构建 LLM prompt
    files_text = ""
    for f, content in file_contents.items():
        files_text += f"\n\n### 文件: {f}\n```\n{content}\n```"

    prompt = (
        f"## 开发需求\n{request}\n\n"
        f"## 项目上下文\n{context_board[:1000]}\n\n"
        f"## 相关代码文件{files_text}\n\n"
        f"## 你的任务\n"
        f"分析这个开发需求，生成一个精确的代码修改方案。\n"
        f"你必须严格按以下 JSON 格式回复，不要有任何其他内容：\n"
        f'{{"file_path": "要修改的文件路径", "title": "修改标题(20字以内)", '
        f'"description": "修改说明(100字以内)", '
        f'"old_content": "要被替换的原始代码(必须和文件中完全一致，包括缩进和空格)", '
        f'"new_content": "替换后的新代码", '
        f'"risk_level": "low/medium/high"}}\n\n'
        f"关键要求：\n"
        f"1. old_content 必须是文件中真实存在的连续代码片段，一字不差\n"
        f"2. 修改范围尽量小，只改必要的部分\n"
        f"3. 如果需求不明确或无法实现，risk_level 设为 high 并在 description 中说明原因"
    )

    system_prompt = (
        "你是一个精确的代码修改专家。你只输出 JSON，不输出任何其他内容。"
        "你生成的 old_content 必须和源文件中的代码完全一致。"
    )

    # 4. 调用 LLM
    gateway = get_model_gateway()
    result = gateway.call_azure_openai("cpo", prompt, system_prompt, "dev_proposal")
    if not result.get("success"):
        return {"success": False, "error": f"LLM 调用失败: {result.get('error')}"}

    # 5. 解析 JSON
    response = result["response"].strip()
    response = re.sub(r'^```json\s*', '', response)
    response = re.sub(r'\s*```$', '', response)

    try:
        proposal_data = json.loads(response)
    except Exception as e:
        return {"success": False, "error": f"JSON 解析失败: {e}\n原始响应: {response[:300]}"}

    # 6. 创建 FixProposal
    try:
        proposal = create_proposal(
            title=proposal_data.get("title", "开发修改"),
            description=proposal_data.get("description", request),
            file_path=proposal_data.get("file_path", target_files[0]),
            old_content=proposal_data.get("old_content", ""),
            new_content=proposal_data.get("new_content", ""),
            risk_level=proposal_data.get("risk_level", "medium")
        )
        return {
            "success": True,
            "proposal": asdict(proposal),
            "message": format_proposal_for_feishu(asdict(proposal))
        }
    except Exception as e:
        return {"success": False, "error": f"创建提案失败: {e}"}