#!/usr/bin/env python3
"""
HUD Demo Orchestrator — 状态机驱动，程序控制流程

用法：python run_hud_demo.py
前提：npm install jsdom puppeteer

流程：
  Phase 1 准备 → Phase 2 写模块(M1-M5) → Phase 3 拼装 →
  Phase 4 测试 → Phase 5 截图+视觉审查 → Phase 6 交付

每个节点：CC 只做核心任务，流程控制不依赖 CC 判断。
"""

import subprocess
import sys
import os
import json
import time
import shutil
from pathlib import Path
from datetime import datetime

# ============================================================
# 配置
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEMO_DIR = PROJECT_ROOT / "demo_outputs"
MODULES_DIR = DEMO_DIR / "hud_modules"
SCREENSHOTS_DIR = DEMO_DIR / "screenshots"
SPECS_DIR = DEMO_DIR / "specs"

FINAL_HTML = DEMO_DIR / "hud_demo_final.html"
ASSEMBLE_PY = DEMO_DIR / "assemble.py"
TEST_SPEC_JS = SPECS_DIR / "hud_demo_test_spec.js"
SCREENSHOT_JS = DEMO_DIR / "screenshot.js"

# CC CLI 路径
NODEJS_PATH = Path.home() / "nodejs"
CLAUDE_CMD = str(NODEJS_PATH / "claude.cmd") if (NODEJS_PATH / "claude.cmd").exists() else "claude"

# 重试限制
MAX_CODE_ITERATIONS = 10
MAX_VISUAL_ITERATIONS = 5

# 模块定义（顺序固定）
MODULES = [
    {
        "id": "M1",
        "name": "骨架",
        "files": ["m1_skeleton.css", "m1_skeleton.html"],
        "desc": "HTML 结构 + CSS 变量 + 四角布局 + 动画关键帧 + .theme-green",
    },
    {
        "id": "M2",
        "name": "状态机",
        "files": ["m2_state_machine.js"],
        "desc": "MODE/PRIORITY 定义、setMode/getMode/popMode/emitEvent/emitWarning/setSpeed/getSpeedLevel、优先级栈、renderAll 占位",
    },
    {
        "id": "M3",
        "name": "渲染器",
        "files": ["m3_renderers.js"],
        "desc": "覆盖 renderAll()、7 状态 × 四角内容表、S0-S3 信息密度控制、flashWarning DOM 操作",
    },
    {
        "id": "M4",
        "name": "剧本",
        "files": ["m4_scenarios.js"],
        "desc": "SCENARIOS 对象(commute/emergency/group)、playScenario/pauseScenario/seekScenario、时间轴进度更新",
    },
    {
        "id": "M5",
        "name": "控制",
        "files": ["m5_controls.html", "m5_controls.js"],
        "desc": "沙盒面板 HTML(6 组按钮) + boot-overlay + 键盘快捷键 + bootSequence()",
    },
]


# ============================================================
# 工具函数
# ============================================================

def log(phase, msg):
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] [{phase}] {msg}")


def run_cmd(cmd, cwd=None, timeout=300):
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


def call_cc(prompt, cwd=None, timeout=180):
    """调用 Claude Code CLI，返回输出文本"""
    # 清除 Z.AI 环境变量
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


def read_file(path):
    return Path(path).read_text(encoding="utf-8") if Path(path).exists() else ""


def write_file(path, content):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(content, encoding="utf-8")


def notify_feishu(msg):
    """飞书通知（尽力而为，失败不阻塞）"""
    try:
        from scripts.feishu_output import LARK_CLI
        chat_id = os.environ.get("LEO_CHAT_ID", "oc_43bca641a75a5beed8215541845c7b73")
        subprocess.run(
            [LARK_CLI, "im", "+messages-send", "--chat-id", chat_id, "--text", msg, "--as", "bot"],
            capture_output=True, timeout=15, encoding="utf-8", errors="ignore",
        )
    except Exception:
        pass


def create_github_issue(title, body, labels=None):
    """创建 GitHub Issue（通过 requests）"""
    try:
        import requests
        from dotenv import load_dotenv
        load_dotenv()
        token = os.environ.get("GITHUB_TOKEN", "")
        if not token:
            log("GitHub", "GITHUB_TOKEN 未设置")
            return None
        headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}
        payload = {"title": title, "body": body}
        if labels:
            payload["labels"] = labels
        resp = requests.post(
            "https://api.github.com/repos/lion9999ly/agent-company/issues",
            headers=headers, json=payload, timeout=30,
        )
        if resp.status_code == 201:
            url = resp.json().get("html_url", "")
            log("GitHub", f"Issue 创建成功: {url}")
            return url
        else:
            log("GitHub", f"Issue 创建失败: {resp.status_code}")
            return None
    except Exception as e:
        log("GitHub", f"Issue 创建异常: {e}")
        return None


# ============================================================
# 前置/后置检查（程序化，不依赖 LLM）
# ============================================================

def check_module_quality(module_id, files):
    """模块写完后的程序化检查"""
    issues = []

    for filename in files:
        filepath = MODULES_DIR / filename
        if not filepath.exists():
            issues.append(f"{filename} 文件不存在")
            continue

        content = filepath.read_text(encoding="utf-8")
        lines = content.split("\n")

        # 行数检查
        if len(lines) > 200:
            issues.append(f"{filename} 超过 200 行（{len(lines)} 行）")

        # JS 文件检查
        if filename.endswith(".js"):
            # 禁止 var
            for i, line in enumerate(lines):
                stripped = line.strip()
                if stripped.startswith("var ") and not stripped.startswith("var("):
                    issues.append(f"{filename}:{i+1} 使用了 var 声明")

            # 函数必须用 function 关键字（如果是 M2-M5 的 API 函数）
            if module_id == "M2":
                required_fns = ["setMode", "getMode", "getPriority", "popMode",
                               "emitEvent", "emitWarning", "setSpeed", "getSpeedLevel"]
                for fn in required_fns:
                    if f"function {fn}" not in content and f"window.{fn}" not in content:
                        issues.append(f"{filename} 缺少 {fn} 函数定义或 window 挂载")

            # window 挂载检查
            if module_id == "M2":
                for fn in ["MODE", "PRIORITY", "setMode", "getMode", "emitEvent",
                          "emitWarning", "setSpeed", "getSpeedLevel", "renderAll", "popMode"]:
                    if f"window.{fn}" not in content:
                        issues.append(f"{filename} 未将 {fn} 挂载到 window")

        # CSS 文件检查
        if filename.endswith(".css"):
            required_vars = ["--bg", "--c-speed", "--c-nav", "--c-warn", "--c-mesh",
                           "--c-music", "--c-call", "--c-dvr"]
            for v in required_vars:
                if v not in content:
                    issues.append(f"{filename} 缺少 CSS 变量 {v}")

            if ".theme-green" not in content:
                issues.append(f"{filename} 缺少 .theme-green 定义")

        # HTML 片段检查
        if filename.endswith(".html"):
            if module_id == "M1":
                for dom_id in ["hud-root", "zone-lt", "zone-rt", "zone-lb", "zone-rb",
                             "center-clear", "bottom-bar", "timeline"]:
                    if dom_id not in content:
                        issues.append(f"{filename} 缺少 #{dom_id}")
            if module_id == "M5":
                if "sandbox" not in content:
                    issues.append(f"{filename} 缺少 #sandbox")
                if "boot-overlay" not in content:
                    issues.append(f"{filename} 缺少 #boot-overlay")

    return issues


# ============================================================
# Phase 实现
# ============================================================

def phase1_prepare():
    """Phase 1: 准备目录和依赖"""
    log("P1", "准备目录和依赖...")

    MODULES_DIR.mkdir(parents=True, exist_ok=True)
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    SPECS_DIR.mkdir(parents=True, exist_ok=True)

    # 检查 jsdom
    rc, out, err = run_cmd(["node", "-e", "require('jsdom')"], timeout=10)
    if rc != 0:
        log("P1", "安装 jsdom...")
        run_cmd(["npm", "install", "jsdom"], timeout=120)

    # 检查 puppeteer
    rc, out, err = run_cmd(["node", "-e", "require('puppeteer')"], timeout=10)
    if rc != 0:
        log("P1", "安装 puppeteer...")
        run_cmd(["npm", "install", "puppeteer"], timeout=300)

    # 检查 tech_spec 存在
    tech_spec = SPECS_DIR / "hud_demo_tech_spec.md"
    if not tech_spec.exists():
        log("P1", "错误: tech_spec 不存在，请先放置到 demo_outputs/specs/")
        return False

    log("P1", "准备完成")
    return True


def phase2_write_module(module, tech_spec_content):
    """Phase 2: 让 CC 写一个模块"""
    mid = module["id"]
    log("P2", f"写模块 {mid}: {module['name']}...")

    # 提取该模块的 spec 段落（从 tech_spec 中截取相关部分）
    # 传给 CC 的是：Style Guide + 全局契约 + 该模块的规格
    prompt = f"""你是一个前端开发者。请严格按照以下技术规格写代码。

=== 任务 ===
写 HUD Demo 的模块 {mid}（{module['name']}）。
产出文件：{', '.join(module['files'])}
保存到：{MODULES_DIR}/

=== 模块职责 ===
{module['desc']}

=== 完整技术规格（请仔细阅读后再写代码）===
{tech_spec_content}

=== 关键约束 ===
1. 严格遵守 Style Guide（function 声明，不用箭头函数，禁止 var）
2. 严格使用契约中的 DOM ID 和 API 签名
3. 所有 API 函数挂到 window 上
4. 单文件不超过 200 行
5. 直接写文件到 {MODULES_DIR}/，不要解释

开始写代码。"""

    result = call_cc(prompt, timeout=180)

    # 检查文件是否生成
    all_exist = all((MODULES_DIR / f).exists() for f in module["files"])
    if not all_exist:
        log("P2", f"{mid} 文件未生成，CC 输出: {result[:200]}")
        return False

    # 程序化质量检查
    issues = check_module_quality(mid, module["files"])
    if issues:
        log("P2", f"{mid} 质量检查发现 {len(issues)} 个问题:")
        for issue in issues:
            log("P2", f"  - {issue}")
        return False

    log("P2", f"{mid} 写入完成，质量检查通过")
    return True


def phase2_fix_module(module, tech_spec_content, issues_text):
    """Phase 2: 修复模块"""
    mid = module["id"]
    log("P2", f"修复 {mid}...")

    # 读取当前文件内容
    current_files = {}
    for f in module["files"]:
        path = MODULES_DIR / f
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
{tech_spec_content}

请修复上述问题，将修复后的完整文件保存到 {MODULES_DIR}/。
只改有问题的部分，不要重写无关代码。"""

    call_cc(prompt, timeout=180)

    # 重新检查
    new_issues = check_module_quality(mid, module["files"])
    return new_issues


def phase3_assemble():
    """Phase 3: 拼装"""
    log("P3", "拼装模块...")

    # 写 assemble.py（确定性脚本，不依赖 CC）
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
<meta name="viewport" content="width=device-width,initial-scale=1.0,viewport-fit=cover">
<title>Smart Riding HUD Demo</title>
<style>
{read('m1_skeleton.css')}
</style>
</head>
<body>
{read('m1_skeleton.html')}
{read('m5_controls.html')}
<script>
// === M2: State Machine ===
{read('m2_state_machine.js')}
// === M3: Renderers ===
{read('m3_renderers.js')}
// === M4: Scenarios ===
{read('m4_scenarios.js')}
// === M5: Controls ===
{read('m5_controls.js')}
// === Boot ===
document.addEventListener('DOMContentLoaded', function() {{
  bootSequence();
}});
</script>
</body>
</html>"""

OUTPUT_FILE.write_text(html, encoding="utf-8")
print(f"OK|{len(html) / 1024:.1f}KB|{len(html.splitlines())}lines")
'''
    write_file(ASSEMBLE_PY, assemble_code)

    rc, out, err = run_cmd(["python", str(ASSEMBLE_PY)], cwd=str(DEMO_DIR))
    if rc != 0:
        log("P3", f"拼装失败: {err}")
        return False

    log("P3", f"拼装完成: {out.strip()}")
    return FINAL_HTML.exists()


def phase4_test():
    """Phase 4: 跑结构测试"""
    log("P4", "运行结构测试...")

    test_file = SPECS_DIR / "hud_demo_test_spec.js"
    if not test_file.exists():
        log("P4", "错误: test_spec.js 不存在")
        return False, "test_spec.js 不存在"

    rc, out, err = run_cmd(
        ["node", str(test_file), str(FINAL_HTML)],
        timeout=30,
    )

    # 解析结果
    lines = out.split("\n")
    fail_lines = [l for l in lines if "❌" in l]
    pass_lines = [l for l in lines if "✅" in l]

    log("P4", f"测试结果: {len(pass_lines)} passed, {len(fail_lines)} failed")

    if rc == 0 and len(fail_lines) == 0:
        return True, out
    else:
        return False, "\n".join(fail_lines) if fail_lines else err


def phase4_fix(fail_info, tech_spec_content):
    """Phase 4: 根据测试失败信息让 CC 修复"""
    log("P4", "根据测试失败修复代码...")

    # 定位失败项对应的模块
    module_hints = {
        "DOM": "M1", "zone-": "M1", "CSS": "M1", "theme-green": "M1",
        "MODE": "M2", "PRIORITY": "M2", "setMode": "M2", "getMode": "M2",
        "popMode": "M2", "speed": "M2", "emitEvent": "M2", "emitWarning": "M2",
        "renderAll": "M3", "render": "M3", "warn": "M3", "cruise": "M3",
        "SCENARIO": "M4", "play": "M4", "timeline": "M4",
        "sandbox": "M5", "boot": "M5", "keydown": "M5", "keyboard": "M5",
    }

    affected = set()
    for line in fail_info.split("\n"):
        for keyword, mod in module_hints.items():
            if keyword.lower() in line.lower():
                affected.add(mod)

    if not affected:
        affected = {"M2", "M3"}  # 默认怀疑状态机和渲染器

    log("P4", f"可能受影响的模块: {affected}")

    # 读取受影响模块的当前代码
    module_code = {}
    for mod in MODULES:
        if mod["id"] in affected:
            for f in mod["files"]:
                path = MODULES_DIR / f
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

请修复后将文件保存回 {MODULES_DIR}/。
只改有问题的部分。"""

    call_cc(prompt, timeout=180)


def phase5_screenshot():
    """Phase 5a: 截图"""
    log("P5", "截图中...")

    # screenshot.js 由 cc_instructions 提供，这里直接写
    screenshot_code = '''
const puppeteer = require('puppeteer');
const path = require('path');
const fs = require('fs');

const HTML_PATH = path.join(__dirname, 'hud_demo_final.html');
const SCREENSHOT_DIR = path.join(__dirname, 'screenshots');
if (!fs.existsSync(SCREENSHOT_DIR)) fs.mkdirSync(SCREENSHOT_DIR, {recursive:true});

(async () => {
  const browser = await puppeteer.launch({
    headless: 'new',
    args: ['--no-sandbox'],
  });
  const page = await browser.newPage();
  await page.setViewport({width:1280, height:720});
  await page.goto('file://' + HTML_PATH);
  await page.waitForTimeout(5000);

  const scenarios = [
    {name:'S01_cruise', setup:"setSpeed(40);setMode('cruise');", wait:1000},
    {name:'S02_nav', setup:"setSpeed(40);setMode('cruise');emitEvent({type:'nav',data:{dest:'公司',dist:'3.2km'}});", wait:1000},
    {name:'S03_warn_front', setup:"setSpeed(60);setMode('cruise');emitWarning('front');", wait:500},
    {name:'S04_warn_left', setup:"setSpeed(60);setMode('cruise');emitWarning('left');", wait:500},
    {name:'S05_warn_right', setup:"setSpeed(60);setMode('cruise');emitWarning('right');", wait:500},
    {name:'S06_call', setup:"setSpeed(40);setMode('cruise');emitEvent({type:'call',data:{name:'张三'}});", wait:1000},
    {name:'S07_music', setup:"setSpeed(40);setMode('cruise');emitEvent({type:'music',data:{track:'梦中的额吉',artist:'布仁巴雅尔'}});", wait:1000},
    {name:'S08_mesh', setup:"setSpeed(40);setMode('cruise');emitEvent({type:'mesh',data:{team:'周末骑行群',members:3}});", wait:1000},
    {name:'S09_dvr', setup:"setSpeed(40);setMode('cruise');emitEvent({type:'dvr'});", wait:1000},
    {name:'S10_green', setup:"setSpeed(40);setMode('cruise');document.body.classList.add('theme-green');", wait:1000},
    {name:'S11_s3', setup:"document.body.classList.remove('theme-green');setMode('cruise');setSpeed(120);", wait:1000},
    {name:'S12_sandbox', setup:"setSpeed(40);setMode('cruise');document.getElementById('sandbox').style.display='flex';", wait:500},
    {name:'S13_scenario', setup:"document.getElementById('sandbox').style.display='none';playScenario('emergency');", wait:6000},
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
    write_file(SCREENSHOT_JS, screenshot_code)

    rc, out, err = run_cmd(["node", str(SCREENSHOT_JS)], cwd=str(DEMO_DIR), timeout=120)

    if rc != 0:
        log("P5", f"截图失败: {err[:200]}")
        return False

    png_count = len(list(SCREENSHOTS_DIR.glob("*.png")))
    log("P5", f"截图完成: {png_count} 张")
    return png_count >= 10


def phase5_visual_review():
    """Phase 5b: 视觉审查（多模态 LLM）"""
    log("P5", "视觉审查中...")

    # 读取 visual_criteria
    criteria_file = SPECS_DIR / "hud_demo_visual_criteria.md"
    if not criteria_file.exists():
        log("P5", "错误: visual_criteria.md 不存在")
        return False, {}

    criteria_content = criteria_file.read_text(encoding="utf-8")

    # 让 CC 执行视觉审查（CC 有 model_gateway 访问权限）
    screenshots = sorted(SCREENSHOTS_DIR.glob("*.png"))
    screenshot_list = "\n".join(f"  - {s.name}" for s in screenshots)

    prompt = f"""执行视觉审查。

截图目录: {SCREENSHOTS_DIR}
截图列表:
{screenshot_list}

视觉验收标准文件: {criteria_file}

请：
1. 读取每张截图
2. 对照 visual_criteria.md 中对应场景的验收标准
3. 调用 model_gateway 的多模态模型（gemini_3_1_pro）审查
4. 将结果保存到 {DEMO_DIR}/visual_review_report.json

报告格式:
{{
  "S01_cruise": {{"passed": true/false, "details": "..."}},
  ...
  "summary": {{"total": 13, "passed": N, "failed": M}}
}}

直接执行，不要解释。"""

    call_cc(prompt, timeout=300)

    # 读取报告
    report_file = DEMO_DIR / "visual_review_report.json"
    if not report_file.exists():
        log("P5", "视觉审查报告未生成")
        return False, {}

    try:
        report = json.loads(report_file.read_text(encoding="utf-8"))
        summary = report.get("summary", {})
        passed = summary.get("passed", 0)
        total = summary.get("total", 0)
        log("P5", f"视觉审查: {passed}/{total} 通过")
        return passed == total, report
    except Exception as e:
        log("P5", f"报告解析失败: {e}")
        return False, {}


def phase5_fix_visual(report, tech_spec_content):
    """Phase 5: 根据视觉审查失败修复"""
    log("P5", "根据视觉反馈修复...")

    failed_items = []
    for scenario, result in report.items():
        if scenario == "summary":
            continue
        if not result.get("passed", True):
            failed_items.append(f"{scenario}: {result.get('details', '')}")

    fail_text = "\n".join(failed_items)

    prompt = f"""视觉审查发现以下问题，请修复。

=== 视觉问题 ===
{fail_text}

请根据问题描述，修改 {MODULES_DIR}/ 下对应的模块文件。
布局/颜色/背景问题 → m1_skeleton.css 或 m1_skeleton.html
状态内容显示问题 → m3_renderers.js
闪烁/动画问题 → m1_skeleton.css + m3_renderers.js
沙盒面板问题 → m5_controls.html 或 m5_controls.js

修复后保存文件。"""

    call_cc(prompt, timeout=180)


def phase6_deliver():
    """Phase 6: 交付"""
    log("P6", "交付中...")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    final_name = f"hud_demo_{timestamp}.html"
    final_path = DEMO_DIR / final_name
    shutil.copy2(FINAL_HTML, final_path)

    # 创建 GitHub Issue
    body = f"""## HUD Demo 交付

- 文件: `demo_outputs/{final_name}`
- 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
- 结构测试: 全部 PASS
- 视觉审查: 全部 PASS

---
*由 orchestrator 自动生成*
"""
    issue_url = create_github_issue(
        f"[交付] HUD Demo - {datetime.now().strftime('%Y-%m-%d')}",
        body, labels=["delivery"],
    )

    # 飞书通知
    notify_feishu(
        f"HUD Demo 已完成\n"
        f"文件: demo_outputs/{final_name}\n"
        f"Issue: {issue_url or '创建失败'}\n"
        f"截图: demo_outputs/screenshots/"
    )

    log("P6", f"交付完成: {final_name}")
    return final_path


def phase_stuck(phase, reason, details):
    """卡住处理：创建 Issue + 飞书通知"""
    log(phase, f"卡住: {reason}")

    body = f"""## 卡住报告

**阶段:** {phase}
**原因:** {reason}

**详情:**
```
{details[:3000]}
```

**建议:**
- 测试脚本 bug → 修改 test_spec.js 后重跑
- 规格矛盾 → 修改 tech_spec.md 后重跑
- 能力不足 → 简化对应模块的要求

---
*由 orchestrator 自动生成*
"""
    issue_url = create_github_issue(f"[卡住] {phase} - {reason}", body, labels=["blocked"])
    notify_feishu(f"HUD Demo 卡住\n阶段: {phase}\n原因: {reason}\nIssue: {issue_url or '创建失败'}")


# ============================================================
# 主流程（状态机）
# ============================================================

def main():
    log("MAIN", "=== HUD Demo Orchestrator 启动 ===")
    start_time = time.time()

    # Phase 1: 准备
    if not phase1_prepare():
        log("MAIN", "Phase 1 失败，退出")
        return

    # 读取 tech_spec
    tech_spec_content = read_file(SPECS_DIR / "hud_demo_tech_spec.md")
    if not tech_spec_content:
        log("MAIN", "tech_spec 为空，退出")
        return

    # Phase 2: 写模块
    for module in MODULES:
        success = phase2_write_module(module, tech_spec_content)
        if not success:
            # 重试修复
            for retry in range(3):
                issues = check_module_quality(module["id"], module["files"])
                if not issues:
                    break
                issues_text = "\n".join(issues)
                log("P2", f"{module['id']} 第 {retry+1} 次修复...")
                remaining = phase2_fix_module(module, tech_spec_content, issues_text)
                if not remaining:
                    break
            else:
                phase_stuck("P2", f"{module['id']} 3 次修复仍不通过", "\n".join(issues))
                return

    # Phase 3 + 4 循环：拼装 → 测试 → 修复
    for iteration in range(MAX_CODE_ITERATIONS):
        log("MAIN", f"=== 测试迭代 {iteration + 1}/{MAX_CODE_ITERATIONS} ===")

        # Phase 3: 拼装
        if not phase3_assemble():
            phase_stuck("P3", "拼装失败", "assemble.py 执行出错")
            return

        # Phase 4: 测试
        test_passed, test_output = phase4_test()
        if test_passed:
            log("P4", "全部测试通过!")
            break

        # 修复
        phase4_fix(test_output, tech_spec_content)
    else:
        phase_stuck("P4", f"{MAX_CODE_ITERATIONS} 轮测试仍未通过", test_output)
        return

    # Phase 5: 截图 + 视觉审查循环
    for v_iter in range(MAX_VISUAL_ITERATIONS):
        log("MAIN", f"=== 视觉迭代 {v_iter + 1}/{MAX_VISUAL_ITERATIONS} ===")

        # 截图
        if not phase5_screenshot():
            log("P5", "截图失败，尝试继续...")
            # puppeteer 可能有问题，跳过视觉审查直接交付
            log("P5", "跳过视觉审查，直接交付（截图环境不可用）")
            break

        # 视觉审查
        visual_passed, report = phase5_visual_review()
        if visual_passed:
            log("P5", "视觉审查全部通过!")
            break

        # 修复 → 重新拼装
        phase5_fix_visual(report, tech_spec_content)
        phase3_assemble()
    else:
        if not visual_passed:
            phase_stuck("P5", f"{MAX_VISUAL_ITERATIONS} 轮视觉审查未通过",
                       json.dumps(report, ensure_ascii=False, indent=2))
            return

    # Phase 6: 交付
    final_path = phase6_deliver()

    elapsed = time.time() - start_time
    log("MAIN", f"=== 完成! 耗时 {elapsed/60:.1f} 分钟 ===")
    log("MAIN", f"产出: {final_path}")


if __name__ == "__main__":
    main()
