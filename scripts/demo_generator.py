"""Demo 原型生成器 — 从设计规范生成可交互 HTML
@description: 用 GPT-5.4 生成 HUD 和 App Demo 原型
@dependencies: model_gateway
@last_modified: 2026-04-04
"""
import re, time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent


def generate_hud_demo(design_spec: str, scenario_script: str, gateway) -> str:
    """生成 HUD Demo HTML

    Args:
        design_spec: HUD 设计规范
        scenario_script: 场景脚本
        gateway: 模型网关实例

    Returns:
        生成的 HTML 文件路径
    """
    prompt = (
        f"生成一个全屏 HTML 页面，模拟摩托车骑行头盔的 HUD 显示效果。\n\n"
        f"## 设计规范\n{design_spec[:2000]}\n\n"
        f"## 场景脚本\n{scenario_script[:2000]}\n\n"
        f"## 技术要求\n"
        f"- 单文件 HTML（内联 CSS + JS）\n"
        f"- 全屏黑色背景模拟骑行视角\n"
        f"- 半透明 HUD 元素叠加\n"
        f"- 导航箭头有渐入渐出动画\n"
        f"- 速度数字实时变化（模拟）\n"
        f"- 5 秒后模拟来电通知弹出\n"
        f"- 点击切换日间/夜间/隧道模式\n"
        f"- 适配手机浏览器全屏"
    )
    result = gateway.call("gpt_5_4", prompt,
        "你是前端工程师，生成完整的可运行 HTML 代码。", "code_generation")
    if result.get("success"):
        code = result["response"]
        # 提取 HTML 代码
        html_match = re.search(r'```html\s*([\s\S]*?)```', code)
        if html_match:
            code = html_match.group(1)
        output_path = PROJECT_ROOT / ".ai-state" / "exports" / "hud_demo.html"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(code.strip(), encoding='utf-8')
        return str(output_path)
    return ""


def generate_app_demo(prd_spec: str, gateway) -> str:
    """生成 App Demo HTML（移动端原型）

    Args:
        prd_spec: App PRD 规范
        gateway: 模型网关实例

    Returns:
        生成的 HTML 文件路径
    """
    prompt = (
        f"生成一个移动端 App Demo 原型 HTML 页面。\n\n"
        f"## PRD 规范\n{prd_spec[:2000]}\n\n"
        f"## 技术要求\n"
        f"- 单文件 HTML（内联 CSS + JS）\n"
        f"- 模拟 iPhone 尺寸（375x667）\n"
        f"- 包含底部导航栏\n"
        f"- 首页展示骑行数据卡片\n"
        f"- 点击切换不同页面\n"
        f"- 有简单的动画效果\n"
        f"- 适合嵌入 iframe 展示"
    )
    result = gateway.call("gpt_5_4", prompt,
        "你是移动端 UI 工程师，生成完整的可运行 HTML 代码。", "code_generation")
    if result.get("success"):
        code = result["response"]
        html_match = re.search(r'```html\s*([\s\S]*?)```', code)
        if html_match:
            code = html_match.group(1)
        output_path = PROJECT_ROOT / ".ai-state" / "exports" / "app_demo.html"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(code.strip(), encoding='utf-8')
        return str(output_path)
    return ""


def get_default_hud_spec() -> str:
    """获取默认 HUD 设计规范"""
    return """
## HUD 显示规范

### 信息层级
- L1 核心：速度、导航箭头、来电提示
- L2 重要：组队位置、电量、天气
- L3 辅助：时间、里程、音乐控制

### 视觉风格
- 背景：半透明深色（opacity 0.85）
- 字体：无衬线、白色、数字加粗
- 动画：渐入渐出、300ms

### 位置布局
- 速度：左下角
- 导航：屏幕中央偏上
- 来电：顶部弹出
"""


def get_default_scenario() -> str:
    """获取默认场景脚本"""
    return """
## 场景脚本

### 场景 1: 正常骑行（日间）
- 速度从 0 加速到 80 km/h
- 导航箭头指向右前方
- 无干扰

### 场景 2: 来电
- 5 秒后来电提示弹出
- 显示来电者姓名
- 10 秒后自动消失

### 场景 3: 骑入隧道
- 点击切换夜间模式
- HUD 背景变亮
- 速度数字变大
"""


if __name__ == "__main__":
    print("Demo 生成器已就绪")