# CC 执行文档 Part 3: 元能力层 — 自主进化机制

> 日期: 2026-03-31
> 依赖: Part 1（五层管道）先完成
> 涉及文件:
>   - `scripts/tonight_deep_research.py`（元能力层集成）
>   - `scripts/meta_capability.py`（新建）
>   - `.ai-state/tool_registry.json`（新建，自动维护）
>   - `.ai-state/tools/`（新建目录，存放自主创建的工具脚本）
> 与 Part 1/2 同一次 commit

---

## 一、设计概览

```
Agent 运行中发现能力缺口
        ↓
  [CAPABILITY_GAP: "需要光学参数计算"]
        ↓
  元能力层接管
        ↓
  ┌─ 查注册表 → 已有? → 直接调用 → 回到任务
  └─ 没有 → 分析缺口 → 制定方案 → 执行补齐 → 验证 → 注册 → 回到任务
```

**三级能力扩展（全自主，无审批）：**

| 级别 | 动作 | 例子 |
|------|------|------|
| L1 | 在 `.ai-state/tools/` 下创建新脚本 | BOM成本计算器、光学参数换算 |
| L2 | `pip install` + 注册工具 | 安装 optics 库、pandas |
| L3 | 修改现有核心代码 | 给 model_gateway 加新 provider |

**禁止列表（硬编码，不可覆盖）：**
```python
FORBIDDEN_ACTIONS = [
    "rm -rf", "rmdir", "del /", "shutil.rmtree",  # 不能删文件
    ".env",                                         # 不能改环境变量
    "FEISHU_APP_ID", "FEISHU_APP_SECRET",          # 不能动飞书凭证
    "api_key", "API_KEY", "SECRET",                # 不能改任何凭证
    "git push",                                     # 不能推送
    "os.system('shutdown", "subprocess.call('reboot", # 不能关机重启
]
```

---

## 二、工具注册表

### 2.1 数据结构

`.ai-state/tool_registry.json`:

```json
{
  "version": 1,
  "tools": [
    {
      "name": "bom_calculator",
      "type": "script",
      "path": ".ai-state/tools/bom_calculator.py",
      "description": "计算头盔 BOM 成本，支持多方案对比",
      "invoke": "python .ai-state/tools/bom_calculator.py --input {input_json}",
      "verify_cmd": "python .ai-state/tools/bom_calculator.py --test",
      "installed_at": "2026-04-01 02:15",
      "installed_by": "meta_capability",
      "usage_count": 0,
      "last_used": null,
      "dependencies": ["pandas"],
      "status": "active"
    },
    {
      "name": "pandas",
      "type": "pip_package",
      "path": null,
      "description": "数据分析库",
      "invoke": "import pandas",
      "verify_cmd": "python -c \"import pandas; print(pandas.__version__)\"",
      "installed_at": "2026-04-01 02:14",
      "installed_by": "meta_capability",
      "usage_count": 3,
      "last_used": "2026-04-01 03:20",
      "dependencies": [],
      "status": "active"
    }
  ],
  "evolution_log": [
    {
      "timestamp": "2026-04-01 02:14",
      "gap": "需要结构化数据分析能力",
      "action": "pip install pandas",
      "result": "success",
      "task_context": "optical_suppliers 研究任务"
    }
  ]
}
```

### 2.2 注册表 API

```python
# scripts/meta_capability.py

import json
import subprocess
import time
import re
from pathlib import Path

REGISTRY_PATH = Path(__file__).parent.parent / ".ai-state" / "tool_registry.json"
TOOLS_DIR = Path(__file__).parent.parent / ".ai-state" / "tools"
TOOLS_DIR.mkdir(parents=True, exist_ok=True)

FORBIDDEN_PATTERNS = [
    r"rm\s+-rf", r"rmdir", r"del\s+/", r"shutil\.rmtree",
    r"\.env", r"FEISHU_APP_ID", r"FEISHU_APP_SECRET",
    r"api_key", r"API_KEY", r"SECRET",
    r"git\s+push",
    r"os\.system\(['\"]shutdown", r"subprocess\.call\(['\"]reboot",
]


def load_registry() -> dict:
    if REGISTRY_PATH.exists():
        return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    return {"version": 1, "tools": [], "evolution_log": []}


def save_registry(registry: dict):
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
    tool_info["status"] = "active"
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
```

---

## 三、能力缺口检测与补齐

### 3.1 Agent prompt 注入

在每个 Agent（CTO/CMO/CDO）的 system prompt 末尾追加:

```python
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
```

### 3.2 缺口扫描

在每个 Layer 完成后扫描输出:

```python
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
```

### 3.3 自主补齐引擎

```python
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
                "invoke": existing["invoke"]}

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
    except:
        print(f"  [Meta] 方案解析失败")
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
            if is_forbidden(f"pip install {package}"):
                print(f"  [Meta] ⛔ 禁止: pip install {package}")
                continue
            print(f"  [Meta] 安装: pip install {package}")
            try:
                subprocess.run(
                    ["pip", "install", package, "--break-system-packages"],
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
            full_path = Path(__file__).parent.parent / path
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
            full_path = Path(__file__).parent.parent / file_path
            if full_path.exists():
                text = full_path.read_text(encoding="utf-8")
                if search in text:
                    text = text.replace(search, replace, 1)
                    full_path.write_text(text, encoding="utf-8")
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
                cwd=str(Path(__file__).parent.parent)
            )
            verified = r.returncode == 0
            if verified:
                print(f"  [Meta] ✅ 验证通过")
            else:
                print(f"  [Meta] ❌ 验证失败: {r.stderr[:200]}")
        except Exception as e:
            print(f"  [Meta] 验证异常: {e}")

    # Step 5: 注册（即使验证失败也注册，标记状态）
    register_tool(
        {
            "name": plan.get("tool_name", "unknown"),
            "type": plan.get("approach", "script"),
            "path": plan.get("steps", [{}])[0].get("path") if plan.get("steps") else None,
            "description": plan.get("description", description),
            "invoke": plan.get("invoke_template", ""),
            "verify_cmd": verify_cmd,
            "dependencies": [s.get("package") for s in plan.get("steps", [])
                            if s.get("action") == "pip_install"],
            "status": "active" if verified else "unverified",
        },
        gap_context=description
    )

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
        if tool["status"] != "active":
            continue
        # 简单关键词匹配
        tool_words = set(tool.get("description", "").lower().split())
        desc_words = set(desc_lower.split())
        overlap = tool_words & desc_words
        if len(overlap) >= 2:
            return tool
    return None
```

---

## 四、集成到五层管道

### 4.1 在 Layer 3 Agent 输出后扫描缺口

在 `_run_layers_1_to_3()` 的 Agent 并行执行完成后，添加:

```python
    # === 元能力层: 扫描并补齐能力缺口 ===
    all_gaps = []
    for role, output in agent_outputs.items():
        gaps = scan_capability_gaps(output)
        for g in gaps:
            g["source_agent"] = role
        all_gaps.extend(gaps)

    if all_gaps:
        print(f"  [Meta] 发现 {len(all_gaps)} 个能力缺口")
        resolved_tools = []
        for gap in all_gaps[:3]:  # 单次最多补齐 3 个
            result = resolve_capability_gap(gap, gateway)
            if result.get("success"):
                resolved_tools.append(result)

        # 如果补齐了新能力，用新能力重跑受影响的 Agent
        if resolved_tools:
            print(f"  [Meta] 补齐 {len(resolved_tools)} 个能力，重跑受影响的 Agent...")
            for gap in all_gaps:
                if gap["source_agent"] in agent_outputs:
                    # 在该 Agent 的 prompt 中注入新工具信息
                    tool_info = "\n".join([
                        f"[新增工具] {t['tool_name']}: {t['invoke']}"
                        for t in resolved_tools
                    ])
                    # 追加到 Agent 输出（不重跑整个 Agent，只补充分析）
                    supplement_prompt = (
                        f"你之前的分析中标记了能力缺口。"
                        f"现在系统已补齐以下工具:\n{tool_info}\n\n"
                        f"请基于你之前的分析，补充使用新工具后可以得出的额外结论。"
                        f"只输出补充部分，不要重复之前的内容。"
                    )
                    supplement = _call_model(
                        _get_model_for_role(gap["source_agent"]),
                        supplement_prompt, task_type="meta_supplement"
                    )
                    if supplement.get("success"):
                        agent_outputs[gap["source_agent"]] += (
                            f"\n\n## 补充分析（能力补齐后）\n"
                            f"{supplement['response']}"
                        )
```

### 4.2 在 Layer 5 Critic 中也启用

Critic 的 prompt 中同样注入 `CAPABILITY_GAP_INSTRUCTION`。如果 Critic 发现需要交叉验证某个数据但缺乏工具，也会触发元能力层。

在 `_run_critic_challenge()` 中，Critic 输出后:

```python
    # Critic 也可能发现能力缺口
    critic_gaps = scan_capability_gaps(critic_result.get("response", ""))
    if critic_gaps:
        print(f"  [Meta-Critic] 发现 {len(critic_gaps)} 个验证能力缺口")
        for gap in critic_gaps[:2]:
            resolve_capability_gap(gap, gateway)
```

---

## 五、进化日志与自省

### 5.1 进化报告

在每次深度学习结束时，输出进化报告:

```python
def generate_evolution_report() -> str:
    """生成进化报告"""
    registry = load_registry()
    tools = registry.get("tools", [])
    log = registry.get("evolution_log", [])

    active = [t for t in tools if t["status"] == "active"]
    unverified = [t for t in tools if t["status"] == "unverified"]

    report = f"## 能力进化报告\n\n"
    report += f"- 已有能力: {len(active)} 个\n"
    report += f"- 待验证: {len(unverified)} 个\n"
    report += f"- 进化记录: {len(log)} 次\n\n"

    if active:
        report += "### 已有能力\n"
        for t in active:
            usage = t.get("usage_count", 0)
            report += f"- **{t['name']}** ({t['type']}): {t['description']} [使用 {usage} 次]\n"

    if log:
        report += "\n### 最近进化\n"
        for entry in log[-5:]:
            report += (f"- [{entry['timestamp']}] {entry['gap'][:60]} "
                      f"→ {entry['action'][:40]} ({entry['result']})\n")

    return report
```

### 5.2 集成到深度学习收尾

在 `run_deep_learning()` 的收尾部分:

```python
    # 进化报告
    evolution_report = generate_evolution_report()
    print(evolution_report)

    if progress_callback:
        progress_callback(f"🧬 {evolution_report[:200]}")
```

---

## 六、执行顺序

1. 创建 `.ai-state/tools/` 目录
2. 创建 `.ai-state/tool_registry.json`（空初始化）
3. 创建 `scripts/meta_capability.py`
4. 在 `tonight_deep_research.py` 中 import meta_capability
5. 在 Agent prompt 中注入 `CAPABILITY_GAP_INSTRUCTION`
6. 在 `_run_layers_1_to_3()` 末尾集成缺口扫描和补齐
7. 在 `_run_critic_challenge()` 中集成 Critic 缺口扫描

与 Part 1/2 同一次 commit。
