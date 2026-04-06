"""
@description: 元能力层 — 自主进化机制（工具注册表、缺口扫描、自主补齐引擎）
@dependencies: src.utils.model_gateway
@last_modified: 2026-03-31

设计:
- Agent 运行中发现能力缺口 → 标记 [CAPABILITY_GAP: xxx]
- 元能力层接管 → 查注册表 → 没有 → 分析缺口 → 制定方案 → 执行补齐 → 验证 → 注册
- 三级能力扩展: L1创建脚本, L2安装包, L3修改代码
"""
import json
import subprocess
import time
import re
import sys
from pathlib import Path

# 获取当前 venv 的 pip 路径（Windows: .venv\Scripts\pip.exe, Linux: .venv/bin/pip）
_VENV_PIP = str(Path(sys.executable).parent / "pip")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

REGISTRY_PATH = PROJECT_ROOT / ".ai-state" / "tool_registry.json"
TOOLS_DIR = PROJECT_ROOT / ".ai-state" / "tools"

# 确保工具目录存在
TOOLS_DIR.mkdir(parents=True, exist_ok=True)

# ============================================================
# 禁止列表（硬编码，不可被 LLM 覆盖）
# ============================================================
FORBIDDEN_PATTERNS = [
    r"rm\s+-rf", r"rmdir", r"del\s+/", r"shutil\.rmtree",
    r"\.env", r"FEISHU_APP_ID", r"FEISHU_APP_SECRET",
    r"api_key", r"API_KEY", r"SECRET",
    r"git\s+push",
    r"os\.system\(['\"]shutdown", r"subprocess\.call\(['\"]reboot",
    r"os\.system\s*\(", r"subprocess\.Popen\s*\([^)]*shell\s*=\s*True",  # 命令注入防护
    r"DROP\s+TABLE", r"DELETE\s+FROM",  # SQL 注入防护
    r"eval\s*\(", r"exec\s*\(",  # 代码注入防护
]


# ============================================================
# 能力缺口标记指令（注入到 Agent prompt）
# ============================================================
CAPABILITY_GAP_INSTRUCTION = """
## 能力缺口标记规则

如果你在分析中发现需要某种计算、验证或数据获取能力，但你作为 LLM 无法直接完成，
请在输出中标记:

[CAPABILITY_GAP: 简要描述需要的能力]
[GAP_TYPE: calculation / data_fetch / visualization / code_check / other]
[GAP_SPEC: 具体需求，如"需要计算OLED面板在不同角度下的亮度衰减曲线"]

标记后继续你的分析（用已有信息尽量完成），不要因为缺口而停止。
系统会在后台自动补齐能力，在下一轮分析中提供。
"""


# ============================================================
# 注册表 API
# ============================================================

def load_registry() -> dict:
    """加载工具注册表"""
    if REGISTRY_PATH.exists():
        try:
            return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        except:
            pass
    return {"version": 1, "tools": [], "evolution_log": []}


def save_registry(registry: dict):
    """保存工具注册表"""
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY_PATH.write_text(
        json.dumps(registry, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def find_tool(name: str) -> dict:
    """查找已注册的工具"""
    registry = load_registry()
    for tool in registry["tools"]:
        if tool["name"] == name and tool["status"] == "active":
            return tool
    return None


def register_tool(tool_info: dict, gap_context: str = ""):
    """注册新工具"""
    registry = load_registry()
    # 去重
    registry["tools"] = [t for t in registry["tools"] if t["name"] != tool_info["name"]]
    tool_info["installed_at"] = time.strftime('%Y-%m-%d %H:%M')
    tool_info["installed_by"] = "meta_capability"
    tool_info["usage_count"] = 0
    tool_info["last_used"] = None
    tool_info["status"] = tool_info.get("status", "active")
    registry["tools"].append(tool_info)

    registry["evolution_log"].append({
        "timestamp": time.strftime('%Y-%m-%d %H:%M'),
        "gap": gap_context,
        "action": f"registered {tool_info['name']} ({tool_info['type']})",
        "result": "success",
    })
    save_registry(registry)
    print(f"  [Meta] 注册工具: {tool_info['name']}")


def record_usage(name: str):
    """记录工具使用"""
    registry = load_registry()
    for tool in registry["tools"]:
        if tool["name"] == name:
            tool["usage_count"] = tool.get("usage_count", 0) + 1
            tool["last_used"] = time.strftime('%Y-%m-%d %H:%M')
    save_registry(registry)


def is_forbidden(code_or_cmd: str) -> bool:
    """检查是否触犯禁止列表"""
    for pattern in FORBIDDEN_PATTERNS:
        if re.search(pattern, code_or_cmd, re.IGNORECASE):
            return True
    return False


def list_capabilities() -> list:
    """列出所有已有能力"""
    registry = load_registry()
    return [
        {"name": t["name"], "type": t["type"], "description": t["description"]}
        for t in registry["tools"]
        if t["status"] == "active"
    ]


# ============================================================
# 能力缺口扫描
# ============================================================

def scan_capability_gaps(text: str) -> list:
    """从 Agent 输出中扫描能力缺口"""
    gaps = []
    # 匹配 [CAPABILITY_GAP: xxx] 标记
    gap_pattern = re.compile(
        r'\[CAPABILITY_GAP:\s*(.+?)\]'
        r'(?:\s*\[GAP_TYPE:\s*(.+?)\])?'
        r'(?:\s*\[GAP_SPEC:\s*(.+?)\])?',
        re.DOTALL
    )
    for match in gap_pattern.finditer(text):
        gaps.append({
            "description": match.group(1).strip(),
            "type": match.group(2).strip() if match.group(2) else "other",
            "spec": match.group(3).strip() if match.group(3) else "",
        })
    return gaps


# ============================================================
# 自主补齐引擎
# ============================================================

def resolve_capability_gap(gap: dict, gateway) -> dict:
    """自主分析并补齐一个能力缺口

    流程:
    1. 查注册表（已有就直接返回）
    2. 让 LLM 分析需要什么 → 生成安装/编写方案
    3. 执行方案（pip install / 写脚本 / 改代码）
    4. 验证
    5. 注册

    返回: {"success": bool, "tool_name": str, "invoke": str}
    """
    description = gap["description"]
    gap_type = gap["type"]
    spec = gap.get("spec", "")

    print(f"\n  [Meta] 检测到能力缺口: {description}")
    print(f"  [Meta] 类型: {gap_type}")

    # Step 1: 查注册表
    existing = _find_matching_tool(description)
    if existing:
        print(f"  [Meta] 已有工具: {existing['name']}")
        record_usage(existing["name"])
        return {"success": True, "tool_name": existing["name"],
                "invoke": existing.get("invoke", "")}

    # Step 2: 让 LLM 制定补齐方案
    plan_prompt = f"""你是一个开发工程师。系统在运行深度研究任务时发现了以下能力缺口:

缺口描述: {description}
缺口类型: {gap_type}
详细需求: {spec}

当前环境:
- Python 3.11, Windows
- 已安装: requests, yaml, json, pandas, openpyxl
- 项目路径: D:\\Users\\uih00653\\my_agent_company\\pythonProject1
- 工具脚本目录: .ai-state/tools/
- 可以 pip install 任何包
- 可以创建 Python 脚本

已有工具:
{json.dumps(list_capabilities(), ensure_ascii=False, indent=2)}

请制定补齐方案，输出 JSON:
{{
    "approach": "pip_install / write_script / modify_code / already_available",
    "tool_name": "工具名称（英文下划线）",
    "description": "工具描述",
    "steps": [
        {{"action": "pip_install", "package": "package_name"}},
        {{"action": "write_script", "path": ".ai-state/tools/xxx.py", "content": "完整代码"}},
        {{"action": "modify_file", "path": "相对路径", "search": "要替换的代码", "replace": "替换后的代码"}}
    ],
    "verify_cmd": "验证命令（python -c 'xxx' 或 python script.py --test）",
    "invoke_template": "调用模板（python .ai-state/tools/xxx.py --input {{input}}）"
}}

只输出 JSON。如果已有工具就能满足，approach 填 already_available。
"""

    result = gateway.call("gpt_5_4", plan_prompt,
                           "你是系统工程师，制定精确的能力补齐方案。",
                           "meta_capability")
    if not result.get("success"):
        print(f"  [Meta] 方案生成失败: {result.get('error', '')[:100]}")
        return {"success": False, "error": "Plan generation failed"}

    try:
        resp = result["response"].strip()
        resp = re.sub(r'^```json\s*', '', resp)
        resp = re.sub(r'\s*```$', '', resp)
        plan = json.loads(resp)
    except Exception as e:
        print(f"  [Meta] 方案解析失败: {e}")
        return {"success": False, "error": "Plan parse failed"}

    if plan.get("approach") == "already_available":
        print(f"  [Meta] LLM 判断已有能力可满足")
        return {"success": True, "tool_name": plan.get("tool_name", "existing"),
                "invoke": plan.get("invoke_template", "")}

    # Step 3: 执行方案
    for step in plan.get("steps", []):
        action = step.get("action")

        if action == "pip_install":
            package = step.get("package", "")
            cmd = f"pip install {package}"
            if is_forbidden(cmd):
                print(f"  [Meta] ⛔ 禁止: {cmd}")
                continue
            print(f"  [Meta] 安装: {cmd}")
            try:
                subprocess.run(
                    [_VENV_PIP, "install", package, "--break-system-packages"],
                    capture_output=True, text=True, timeout=120
                )
            except Exception as e:
                print(f"  [Meta] 安装失败: {e}")

        elif action == "write_script":
            path = step.get("path", "")
            content = step.get("content", "")
            if is_forbidden(content):
                print(f"  [Meta] ⛔ 脚本内容触犯禁止列表")
                continue
            # 确保在允许的目录下
            if not path.startswith(".ai-state/tools/"):
                path = f".ai-state/tools/{Path(path).name}"
            full_path = PROJECT_ROOT / path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content, encoding="utf-8")
            print(f"  [Meta] 创建脚本: {path}")

        elif action == "modify_file":
            file_path = step.get("path", "")
            search = step.get("search", "")
            replace = step.get("replace", "")
            if is_forbidden(replace):
                print(f"  [Meta] ⛔ 代码修改触犯禁止列表")
                continue
            full_path = PROJECT_ROOT / file_path
            if full_path.exists():
                text_content = full_path.read_text(encoding="utf-8")
                if search in text_content:
                    text_content = text_content.replace(search, replace, 1)
                    full_path.write_text(text_content, encoding="utf-8")
                    print(f"  [Meta] 修改: {file_path}")
                else:
                    print(f"  [Meta] 未找到匹配: {file_path}")

    # Step 4: 验证
    verify_cmd = plan.get("verify_cmd", "")
    verified = False
    if verify_cmd and not is_forbidden(verify_cmd):
        try:
            r = subprocess.run(
                verify_cmd, shell=True, capture_output=True,
                text=True, timeout=30,
                cwd=str(PROJECT_ROOT)
            )
            verified = r.returncode == 0
            if verified:
                print(f"  [Meta] ✅ 验证通过")
            else:
                print(f"  [Meta] ❌ 验证失败: {r.stderr[:200] if r.stderr else r.stdout[:200]}")
        except Exception as e:
            print(f"  [Meta] 验证异常: {e}")

    # Step 5: 注册（即使验证失败也注册，标记状态）
    steps = plan.get("steps", [])
    register_tool(
        {
            "name": plan.get("tool_name", "unknown"),
            "type": plan.get("approach", "script"),
            "path": steps[0].get("path") if steps else None,
            "description": plan.get("description", description),
            "invoke": plan.get("invoke_template", ""),
            "verify_cmd": verify_cmd,
            "dependencies": [s.get("package") for s in steps
                            if s.get("action") == "pip_install"],
            "status": "active" if verified else "unverified",
        },
        gap_context=description
    )

    # 推送飞书通知（如果有回调）
    if verified and hasattr(resolve_capability_gap, '_feishu_callback'):
        callback = resolve_capability_gap._feishu_callback
        if callback:
            try:
                callback(f"🧬 元能力进化: 新增工具 [{plan.get('tool_name', '')}] — {plan.get('description', '')[:60]}")
            except:
                pass

    return {
        "success": verified,
        "tool_name": plan.get("tool_name", "unknown"),
        "invoke": plan.get("invoke_template", "")
    }


def _find_matching_tool(description: str) -> dict:
    """在注册表中模糊匹配已有工具"""
    registry = load_registry()
    desc_lower = description.lower()
    for tool in registry["tools"]:
        if tool.get("status") != "active":
            continue
        # 简单关键词匹配
        tool_words = set(tool.get("description", "").lower().split())
        desc_words = set(desc_lower.split())
        overlap = tool_words & desc_words
        if len(overlap) >= 2:
            return tool
    return None


# ============================================================
# 进化报告
# ============================================================

def generate_evolution_report() -> str:
    """生成进化报告"""
    registry = load_registry()
    tools = registry.get("tools", [])
    log = registry.get("evolution_log", [])

    active = [t for t in tools if t.get("status") == "active"]
    unverified = [t for t in tools if t.get("status") == "unverified"]

    report = f"## 能力进化报告\n\n"
    report += f"- 已有能力: {len(active)} 个\n"
    report += f"- 待验证: {len(unverified)} 个\n"
    report += f"- 进化记录: {len(log)} 次\n\n"

    if active:
        report += "### 已有能力\n"
        for t in active:
            usage = t.get("usage_count", 0)
            report += f"- **{t['name']}** ({t['type']}): {t.get('description', '')} [使用 {usage} 次]\n"

    if log:
        report += "\n### 最近进化\n"
        for entry in log[-5:]:
            report += (f"- [{entry['timestamp']}] {entry.get('gap', '')[:60]} "
                      f"→ {entry.get('action', '')[:40]} ({entry.get('result', '')})\n")

    return report


# ============================================================
# 批量缺口处理
# ============================================================

def resolve_all_gaps(gaps: list, gateway, max_resolve: int = 3) -> list:
    """批量处理能力缺口

    Args:
        gaps: 缺口列表，每项含 description, type, spec, source_agent
        gateway: 模型网关
        max_resolve: 单次最多补齐数量

    Returns:
        已解决的缺口列表
    """
    if not gaps:
        return []

    print(f"  [Meta] 发现 {len(gaps)} 个能力缺口")
    resolved_tools = []

    for gap in gaps[:max_resolve]:
        result = resolve_capability_gap(gap, gateway)
        if result.get("success") or result.get("tool_name"):
            resolved_tools.append(result)

    return resolved_tools


if __name__ == "__main__":
    # 测试
    print("=" * 50)
    print("[Meta Capability] 测试")
    print("=" * 50)

    # 测试注册表
    registry = load_registry()
    print(f"注册表: {len(registry.get('tools', []))} 个工具")

    # 测试缺口扫描
    test_text = """
    这是测试输出。
    [CAPABILITY_GAP: 需要光学参数计算]
    [GAP_TYPE: calculation]
    [GAP_SPEC: 计算OLED面板在不同角度下的亮度衰减曲线]
    继续分析...
    """
    gaps = scan_capability_gaps(test_text)
    print(f"扫描到的缺口: {gaps}")

    # 测试进化报告
    report = generate_evolution_report()
    print(report)