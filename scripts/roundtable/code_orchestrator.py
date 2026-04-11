"""
@description: 代码类产出的 Orchestrator - 程序化控制 CC 分模块写代码 + 测试 + 截图 + 视觉审查
@dependencies: subprocess, pathlib, model_gateway, roundtable
@last_modified: 2026-04-11
"""

import subprocess
import sys
import os
import json
import time
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional, Tuple, Dict, Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# CC CLI 路径
NODEJS_PATH = Path.home() / "nodejs"
CLAUDE_CMD = str(NODEJS_PATH / "claude.cmd") if (NODEJS_PATH / "claude.cmd").exists() else "claude"

# 重试限制
MAX_CODE_ITERATIONS = 10
MAX_VISUAL_ITERATIONS = 5


# ============================================================
# 工具函数
# ============================================================

def log(phase: str, msg: str):
    """日志输出"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] [Orchestrator] [{phase}] {msg}")


def run_cmd(cmd: list, cwd: str = None, timeout: int = 300) -> Tuple[int, str, str]:
    """执行命令，返回 (returncode, stdout, stderr)"""
    try:
        result = subprocess.run(
            cmd, cwd=cwd or str(PROJECT_ROOT),
            capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace",
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "TIMEOUT"
    except FileNotFoundError as e:
        return -1, "", f"FileNotFoundError: {e}"


def call_cc(prompt: str, cwd: str = None, timeout: int = 180) -> str:
    """调用 Claude Code CLI，返回输出文本
    关键：每次只给一个模块任务，CC 不知道整体流程
    """
    clean_env = {**os.environ}
    for key in ["ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY",
                "ANTHROPIC_MODEL", "CLAUDE_BASE_URL"]:
        clean_env.pop(key, None)
    nodejs_path = str(NODEJS_PATH)
    if nodejs_path not in clean_env.get("PATH", ""):
        clean_env["PATH"] = nodejs_path + ";" + clean_env.get("PATH", "")

    try:
        result = subprocess.run(
            [CLAUDE_CMD, "-p"],
            input=prompt, cwd=cwd or str(PROJECT_ROOT),
            capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace", env=clean_env,
        )
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        return "[TIMEOUT]"
    except Exception as e:
        return f"[ERROR] {e}"


def read_file(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def write_file(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


# ============================================================
# 程序化质量检查（不依赖 LLM）
# ============================================================

def check_module_quality(module_id: str, files: list, modules_dir: Path) -> list:
    """模块写完后的程序化检查"""
    issues = []

    for filename in files:
        filepath = modules_dir / filename
        if not filepath.exists():
            issues.append(f"{filename} 文件不存在")
            continue

        content = filepath.read_text(encoding="utf-8")
        lines = content.split("\n")

        if len(lines) > 200:
            issues.append(f"{filename} 超过 200 行（{len(lines)} 行）")

        if filename.endswith(".js"):
            for i, line in enumerate(lines):
                stripped = line.strip()
                if stripped.startswith("var ") and not stripped.startswith("var("):
                    issues.append(f"{filename}:{i+1} 使用了 var 声明")

    return issues


# ============================================================
# Phase 实现（从 run_hud_demo.py 提取）
# ============================================================

def phase_write_module(module: dict, tech_spec_content: str, modules_dir: Path) -> bool:
    """Phase: 让 CC 写一个模块"""
    mid = module["id"]
    log("Code", f"写模块 {mid}: {module['name']}...")

    prompt = f"""你是一个前端开发者。请严格按照以下技术规格写代码。

=== 任务 ===
写 HUD Demo 的模块 {mid}（{module['name']}）。
产出文件：{', '.join(module['files'])}
保存到：{modules_dir}/

=== 模块职责 ===
{module['desc']}

=== 完整技术规格 ===
{tech_spec_content}

=== 关键约束 ===
1. 严格遵守 Style Guide（function 声明，不用箭头函数，禁止 var）
2. 严格使用契约中的 DOM ID 和 API 签名
3. 所有 API 函数挂到 window 上
4. 单文件不超过 200 行
5. 直接写文件，不要解释

开始写代码。"""

    call_cc(prompt, timeout=180)

    all_exist = all((modules_dir / f).exists() for f in module["files"])
    if not all_exist:
        log("Code", f"{mid} 文件未生成")
        return False

    issues = check_module_quality(mid, module["files"], modules_dir)
    if issues:
        log("Code", f"{mid} 质量检查发现 {len(issues)} 个问题")
        return False

    log("Code", f"{mid} 写入完成")
    return True


def phase_fix_module(module: dict, tech_spec_content: str, issues_text: str, modules_dir: Path) -> list:
    """Phase: 修复模块"""
    mid = module["id"]
    log("Code", f"修复 {mid}...")

    current_files = {}
    for f in module["files"]:
        path = modules_dir / f
        if path.exists():
            current_files[f] = path.read_text(encoding="utf-8")

    files_content = "\n\n".join(
        f"=== {name} ===\n{content}" for name, content in current_files.items()
    )

    prompt = f"""修复以下模块的问题。

=== 模块 {mid}: {module['name']} ===

=== 当前代码 ===
{files_content}

=== 需要修复的问题 ===
{issues_text}

=== 技术规格 ===
{tech_spec_content[:5000]}

请修复上述问题，将修复后的完整文件保存到 {modules_dir}/。
只改有问题的部分，不要重写无关代码。"""

    call_cc(prompt, timeout=180)
    return check_module_quality(mid, module["files"], modules_dir)


def phase_assemble(modules_dir: Path, output_dir: Path) -> bool:
    """Phase: 拼装模块为单 HTML 文件"""
    log("Assemble", "拼装模块...")

    assemble_py = output_dir / "assemble.py"
    final_html = output_dir / "hud_demo_final.html"

    assemble_code = '''#!/usr/bin/env python3
"""拼装 HUD Demo 模块为单 HTML 文件"""
import sys
from pathlib import Path
MODULES_DIR = Path(__file__).parent / "hud_modules"
OUTPUT_FILE = Path(__file__).parent / "hud_demo_final.html"
def read(filename):
    path = MODULES_DIR / filename
    if not path.exists():
        print(f"错误: {path} 不存在")
        sys.exit(1)
    return path.read_text(encoding="utf-8")
html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>HUD Demo</title>
<style>
{read('m1_skeleton.css')}
</style>
</head>
<body>
{read('m1_skeleton.html')}
{read('m5_controls.html')}
<script>
{read('m2_state_machine.js')}
{read('m3_renderers.js')}
{read('m4_scenarios.js')}
{read('m5_controls.js')}
document.addEventListener('DOMContentLoaded', function() {{ bootSequence(); }});
</script>
</body>
</html>"""
OUTPUT_FILE.write_text(html, encoding="utf-8")
print(f"OK|{len(html) / 1024:.1f}KB")
'''
    write_file(assemble_py, assemble_code)

    rc, out, err = run_cmd(["python", str(assemble_py)], cwd=str(output_dir))
    if rc != 0:
        log("Assemble", f"拼装失败: {err}")
        return False

    log("Assemble", f"拼装完成: {out.strip()}")
    return final_html.exists()


def phase_test(final_html: Path, test_spec_js: Path) -> Tuple[bool, str]:
    """Phase: 跑结构测试"""
    log("Test", "运行结构测试...")

    if not test_spec_js.exists():
        log("Test", "错误: test_spec.js 不存在")
        return False, "test_spec.js 不存在"

    rc, out, err = run_cmd(
        ["node", str(test_spec_js), str(final_html)],
        timeout=60,
    )

    lines = out.split("\n")
    fail_lines = [l for l in lines if "❌" in l]
    pass_lines = [l for l in lines if "✅" in l]

    log("Test", f"测试结果: {len(pass_lines)} passed, {len(fail_lines)} failed")

    if rc == 0 and len(fail_lines) == 0:
        return True, out
    else:
        return False, "\n".join(fail_lines) if fail_lines else err


def phase_fix_test(fail_info: str, tech_spec_content: str, modules_dir: Path, modules: list):
    """Phase: 根据测试失败信息让 CC 修复"""
    log("Test", "根据测试失败修复代码...")

    module_hints = {
        "DOM": "M1", "zone-": "M1", "CSS": "M1", "theme-green": "M1",
        "MODE": "M2", "PRIORITY": "M2", "setMode": "M2", "getMode": "M2",
        "renderAll": "M3", "render": "M3", "warn": "M3",
        "SCENARIO": "M4", "play": "M4",
        "sandbox": "M5", "boot": "M5", "keydown": "M5",
    }

    affected = set()
    for line in fail_info.split("\n"):
        for keyword, mod in module_hints.items():
            if keyword.lower() in line.lower():
                affected.add(mod)

    if not affected:
        affected = {"M2", "M3"}

    log("Test", f"可能受影响的模块: {affected}")

    module_code = {}
    for mod in modules:
        if mod["id"] in affected:
            for f in mod["files"]:
                path = modules_dir / f
                if path.exists():
                    module_code[f] = path.read_text(encoding="utf-8")

    files_text = "\n\n".join(f"=== {name} ===\n{code}" for name, code in module_code.items())

    prompt = f"""以下测试失败了，请修复代码。

=== 测试失败信息 ===
{fail_info}

=== 受影响的代码文件 ===
{files_text}

=== 技术规格（参考） ===
{tech_spec_content[:5000]}

请修复后将文件保存回 {modules_dir}/。
只改有问题的部分。"""

    call_cc(prompt, timeout=180)


def phase_screenshot(final_html: Path, screenshots_dir: Path) -> bool:
    """Phase: 截图"""
    log("Screenshot", "截图中...")

    screenshot_js = final_html.parent / "screenshot.js"

    screenshot_code = '''
const puppeteer = require('puppeteer');
const path = require('path');
const fs = require('fs');
const HTML_PATH = path.join(__dirname, 'hud_demo_final.html');
const SCREENSHOT_DIR = path.join(__dirname, 'screenshots');
if (!fs.existsSync(SCREENSHOT_DIR)) fs.mkdirSync(SCREENSHOT_DIR, {recursive:true});
(async () => {
  const browser = await puppeteer.launch({ headless: 'new', args: ['--no-sandbox'] });
  const page = await browser.newPage();
  await page.setViewport({width:1280, height:720});
  await page.goto('file://' + HTML_PATH);
  await page.waitForTimeout(5000);
  const scenarios = [
    {name:'S01_cruise', setup:"setSpeed(40);setMode('cruise');", wait:1000},
    {name:'S02_nav', setup:"emitEvent({type:'nav'});", wait:1000},
    {name:'S03_warn', setup:"emitWarning('front');", wait:500},
    {name:'S04_call', setup:"emitEvent({type:'call'});", wait:1000},
    {name:'S05_music', setup:"emitEvent({type:'music'});", wait:1000},
    {name:'S06_mesh', setup:"emitEvent({type:'mesh'});", wait:1000},
    {name:'S07_green', setup:"document.body.classList.add('theme-green');", wait:1000},
    {name:'S08_sandbox', setup:"document.getElementById('sandbox').style.display='flex';", wait:500},
  ];
  for (const s of scenarios) {
    await page.evaluate(() => { setSpeed(0); setMode('cruise'); });
    await page.waitForTimeout(300);
    await page.evaluate(s.setup);
    await page.waitForTimeout(s.wait);
    await page.screenshot({path: path.join(SCREENSHOT_DIR, s.name+'.png')});
    console.log('OK:'+s.name);
  }
  await browser.close();
  console.log('DONE:'+scenarios.length);
})();
'''
    write_file(screenshot_js, screenshot_code)

    rc, out, err = run_cmd(["node", str(screenshot_js)], cwd=str(final_html.parent), timeout=120)

    if rc != 0:
        log("Screenshot", f"截图失败: {err[:200]}")
        return False

    png_count = len(list(screenshots_dir.glob("*.png")))
    log("Screenshot", f"截图完成: {png_count} 张")
    return png_count >= 5


# ============================================================
# 主入口
# ============================================================

async def run_code_orchestrator(
    task: Any,
    rt_result: Any,
    gw: Any,
    feishu: Any
) -> Tuple[str, str]:
    """代码类产出的 Orchestrator

    流程：
    1. 规格加载（从 TaskSpec.spec_files）
    2. 模块化代码编写（CC，逐模块调用）
    3. 程序化质量检查
    4. 拼装
    5. 结构测试
    6. 截图
    7. 返回产出

    Returns:
        (output_content, output_path)
    """
    log("Main", f"=== Code Orchestrator 启动: {task.topic} ===")

    # 1. 规格加载
    output_dir = PROJECT_ROOT / "demo_outputs"
    modules_dir = output_dir / "hud_modules"
    screenshots_dir = output_dir / "screenshots"
    specs_dir = output_dir / "specs"

    modules_dir.mkdir(parents=True, exist_ok=True)
    screenshots_dir.mkdir(parents=True, exist_ok=True)
    specs_dir.mkdir(parents=True, exist_ok=True)

    # 从 TaskSpec 获取规格文件路径
    spec_files = getattr(task, 'spec_files', {}) or {}
    tech_spec_path = Path(spec_files.get('tech_spec', specs_dir / "hud_demo_tech_spec.md"))
    test_spec_path = Path(spec_files.get('test_spec', specs_dir / "hud_demo_test_spec.js"))
    visual_criteria_path = Path(spec_files.get('visual_criteria', specs_dir / "hud_demo_visual_criteria.md"))

    if not tech_spec_path.exists():
        log("Main", f"tech_spec 不存在: {tech_spec_path}")
        return "", ""

    tech_spec_content = read_file(tech_spec_path)

    # 2. 模块定义
    modules = [
        {"id": "M1", "name": "骨架", "files": ["m1_skeleton.css", "m1_skeleton.html"],
         "desc": "HTML 结构 + CSS 变量 + 四角布局 + 动画关键帧"},
        {"id": "M2", "name": "状态机", "files": ["m2_state_machine.js"],
         "desc": "MODE/PRIORITY 定义、setMode/getMode/popMode/emitEvent/emitWarning/setSpeed/getSpeedLevel"},
        {"id": "M3", "name": "渲染器", "files": ["m3_renderers.js"],
         "desc": "覆盖 renderAll()、7 状态内容表、S0-S3 信息密度控制"},
        {"id": "M4", "name": "剧本", "files": ["m4_scenarios.js"],
         "desc": "SCENARIOS 对象(commute/emergency/group)、playScenario/pauseScenario"},
        {"id": "M5", "name": "控制", "files": ["m5_controls.html", "m5_controls.js"],
         "desc": "沙盒面板 HTML + boot-overlay + 键盘快捷键 + bootSequence()"},
    ]

    # 3. 写模块（逐模块调用 CC）
    for module in modules:
        success = phase_write_module(module, tech_spec_content, modules_dir)
        if not success:
            for retry in range(3):
                issues = check_module_quality(module["id"], module["files"], modules_dir)
                if not issues:
                    break
                issues_text = "\n".join(issues)
                log("Code", f"{module['id']} 第 {retry+1} 次修复...")
                remaining = phase_fix_module(module, tech_spec_content, issues_text, modules_dir)
                if not remaining:
                    break

    # 4. 拼装 + 测试循环
    final_html = output_dir / "hud_demo_final.html"

    for iteration in range(MAX_CODE_ITERATIONS):
        log("Main", f"=== 测试迭代 {iteration + 1}/{MAX_CODE_ITERATIONS} ===")

        if not phase_assemble(modules_dir, output_dir):
            continue

        test_passed, test_output = phase_test(final_html, test_spec_path)
        if test_passed:
            log("Test", "全部测试通过!")
            break

        phase_fix_test(test_output, tech_spec_content, modules_dir, modules)

    # 5. 截图
    phase_screenshot(final_html, screenshots_dir)

    # 6. 返回产出
    output_content = read_file(final_html)
    output_path = str(final_html)

    log("Main", f"=== Code Orchestrator 完成: {output_path} ===")

    return output_content, output_path


__all__ = ["run_code_orchestrator"]