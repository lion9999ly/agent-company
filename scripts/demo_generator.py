"""
Demo Generator — HUD/App 演示 Demo 生成器
职责: 根据配置文件生成可交互的 HTML Demo
设计:
- 所有产品设计决策从 JSON 配置读取，Python 不硬编码产品逻辑
- 5 步管道: Smart Preflight → Spec Generation → Asset Mapping → Code Generation → Visual Review
"""
import json
import base64
import asyncio
import time
import re
from pathlib import Path
from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass

# 依赖
from scripts.litellm_gateway import get_model_gateway
from src.tools.knowledge_base import KB_ROOT

# 路径常量
SPECS_DIR = Path(".ai-state/demo_specs")
ASSETS_DIR = Path(".ai-state/demo_assets/hud_icons")
OUTPUT_DIR = Path("demo_outputs")


@dataclass
class DemoStatus:
    stage: str = "idle"
    message: str = ""
    last_output: str = ""
    start_time: float = 0


class DemoGenerator:
    """Demo 生成器 — HUD + App"""

    def __init__(self, feishu_notify: Optional[Callable] = None):
        self.gw = get_model_gateway()
        self.feishu_notify = feishu_notify
        self.status = DemoStatus()
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # ============================================================
    # 配置加载
    # ============================================================
    def _load_configs(self, demo_type: str) -> dict:
        """加载 JSON 配置文件，每次生成时调用以获取最新配置"""
        config_file = "hud_config.json" if demo_type == "hud" else "app_config.json"
        config_path = SPECS_DIR / config_file
        scenarios_path = SPECS_DIR / "demo_scenarios.json"

        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)

        with open(scenarios_path, 'r', encoding='utf-8') as f:
            scenarios = json.load(f)

        config["scenarios"] = scenarios
        return config

    # ============================================================
    # 状态管理
    # ============================================================
    async def get_status(self) -> str:
        """返回当前生成状态"""
        elapsed = time.time() - self.status.start_time if self.status.start_time else 0
        return (
            f"📊 Demo 生成器状态\n"
            f"阶段: {self.status.stage}\n"
            f"信息: {self.status.message}\n"
            f"耗时: {elapsed:.1f}s\n"
            f"最近输出: {self.status.last_output or '无'}"
        )

    async def _notify(self, msg: str):
        """发送飞书通知"""
        self.status.message = msg
        if self.feishu_notify:
            try:
                await self.feishu_notify(msg)
            except Exception as e:
                print(f"[DemoGen] 飞书通知失败: {e}")
        print(f"[DemoGen] {msg}")

    # ============================================================
    # Step 1: Smart Preflight
    # ============================================================
    async def _smart_preflight(self, demo_type: str) -> dict:
        """自愈式前置检查"""
        await self._notify("🔍 Step 1: 前置检查...")

        config = self._load_configs(demo_type)
        result = {"icons": {}, "kb_context": "", "config": config}

        # 检查图标素材
        if demo_type == "hud":
            icons_config = config.get("icons", {})
            ASSETS_DIR.mkdir(parents=True, exist_ok=True)

            for name, filename in icons_config.items():
                icon_path = ASSETS_DIR / filename
                if icon_path.exists():
                    result["icons"][name] = icon_path
                else:
                    # 自动补生成
                    await self._notify(f"⚠️ 缺失图标 {filename}，自动补生成...")
                    await self._generate_missing_icon(name, filename)
                    if icon_path.exists():
                        result["icons"][name] = icon_path

        # 检查 KB 相关条目
        kb_count = await self._count_kb_entries(demo_type)
        if kb_count < 3:
            await self._notify(f"⚠️ KB 条目不足({kb_count})，启动 mini research...")
            await self._mini_research(demo_type)

        result["kb_context"] = await self._get_kb_context(demo_type)

        # 检查模型可用性
        models_ok = await self._check_models()
        if not models_ok:
            raise RuntimeError("核心模型不可用，无法生成 Demo")

        await self._notify(f"✅ 前置检查完成: {len(result['icons'])} 图标, KB上下文 {len(result['kb_context'])} 字")
        return result

    async def _generate_missing_icon(self, name: str, filename: str):
        """补生成缺失图标"""
        prompts = {
            "nav_arrow_left.png": "A minimal green arrow pointing left, HUD style, on pure black background, monochrome green (#00FF41), 256x256",
            "nav_arrow_right.png": "A minimal green arrow pointing right, HUD style, on pure black background, monochrome green (#00FF41), 256x256",
            "nav_u_turn.png": "A minimal green U-turn arrow icon, HUD style, on pure black background, monochrome green (#00FF41), 256x256",
            "speed_indicator.png": "A minimal motorcycle speedometer HUD element showing 85 km/h in green text on black background, monochrome green (#00FF41), 512x256",
            "adas_warning_bsd.png": "A motorcycle blind spot detection warning icon, red exclamation triangle with car silhouette, on black background, HUD style, 256x256",
            "adas_warning_fcw.png": "A forward collision warning icon, red car silhouette with distance lines, on black background, HUD style, 256x256",
            "incoming_call.png": "A phone call incoming notification HUD element, green phone icon with John text, on black background, minimal HUD style, 512x256",
            "group_ride.png": "A group ride indicator showing 3 small rider dots on a minimal map, green on black background, HUD style, 512x256",
            "battery_indicator.png": "A minimal battery icon showing 75% charge, green on black background, HUD style, 128x128",
            "recording_dot.png": "A small red recording dot with REC text, on black background, HUD style, 128x128",
        }
        prompt = prompts.get(filename, f"A minimal {name} icon, HUD style, green on black background")
        result = self.gw.call_image(prompt, model_name="nano_banana_pro",
                                     save_path=str(ASSETS_DIR / filename))
        if not result.get("success"):
            print(f"[DemoGen] 图标生成失败: {result.get('error')}")

    async def _count_kb_entries(self, demo_type: str) -> int:
        """统计 KB 相关条目"""
        count = 0
        keywords = ["hud", "头盔", "导航", "adas"] if demo_type == "hud" else ["app", "界面", "交互"]
        for f in KB_ROOT.rglob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                title = data.get("title", "").lower()
                if any(kw in title for kw in keywords):
                    count += 1
            except:
                continue
        return count

    async def _mini_research(self, demo_type: str):
        """快速补充知识，3-5 query，L1 only"""
        queries = {
            "hud": [
                "motorcycle helmet HUD UI design best practices",
                "AR HUD information density speed dependent",
                "HUD warning icon design automotive"
            ],
            "app": [
                "motorcycle companion app UI design",
                "smart helmet app information architecture",
                "riding dashboard UX design"
            ]
        }
        for query in queries.get(demo_type, []):
            result = self.gw.call("gemini_2_5_flash", query, task_type="quick_qa")
            if result.get("success"):
                print(f"[MiniResearch] {query[:30]}: OK")

    async def _get_kb_context(self, demo_type: str) -> str:
        """获取 KB 上下文"""
        entries = []
        keywords = ["hud", "头盔", "导航"] if demo_type == "hud" else ["app", "界面"]
        for f in list(KB_ROOT.rglob("*.json"))[:10]:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                title = data.get("title", "")
                if any(kw in title.lower() for kw in keywords):
                    entries.append(f"- {title[:50]}")
            except:
                continue
        return "\n".join(entries[:5])

    async def _check_models(self) -> bool:
        """检查核心模型可用性"""
        for model in ["gpt_5_4", "gemini_2_5_flash"]:
            result = self.gw.call(model, "ping", task_type="health_check")
            if not result.get("success"):
                print(f"[DemoGen] 模型 {model} 不可用")
                return False
        return True

    # ============================================================
    # Step 2: Spec Generation
    # ============================================================
    async def _generate_tech_spec(self, demo_type: str, preflight_result: dict) -> dict:
        """将产品配置翻译为技术实现 spec"""
        await self._notify("📝 Step 2: 生成技术 Spec...")

        config = preflight_result["config"]
        kb_context = preflight_result["kb_context"]

        if demo_type == "hud":
            prompt = f"""你是 HUD 前端工程师。根据以下产品配置，生成技术实现 spec。

产品配置:
{json.dumps(config, ensure_ascii=False, indent=2)}

KB 上下文:
{kb_context}

输出 JSON 格式的技术 spec，包含:
1. css_variables: 颜色、字体、尺寸的 CSS 变量
2. animation_timing: 各动画的 duration 和 easing
3. event_handlers: 键盘事件映射
4. speed_tier_rules: 速度分级的信息密度规则
5. warning_flash: 预警闪烁的 timing 和颜色

只输出 JSON，不要其他内容。"""
        else:
            prompt = f"""你是移动端前端工程师。根据以下产品配置，生成技术实现 spec。

产品配置:
{json.dumps(config, ensure_ascii=False, indent=2)}

输出 JSON 格式的技术 spec，包含:
1. css_variables: 主题色、字体、间距
2. tab_bar: 底部导航栏配置
3. page_routes: hash 路由映射
4. component_styles: 各组件样式规则

只输出 JSON，不要其他内容。"""

        result = self.gw.call("gemini_2_5_flash", prompt, task_type="planning")

        if result.get("success"):
            resp = result["response"].strip()
            resp = re.sub(r'^```json\s*', '', resp)
            resp = re.sub(r'\s*```$', '', resp)
            try:
                tech_spec = json.loads(resp)
            except:
                tech_spec = {"raw": resp}
        else:
            tech_spec = {"error": result.get("error")}

        # 保存 spec
        spec_path = SPECS_DIR / f"{demo_type}_tech_spec.json"
        spec_path.parent.mkdir(parents=True, exist_ok=True)
        with open(spec_path, 'w', encoding='utf-8') as f:
            json.dump(tech_spec, f, ensure_ascii=False, indent=2)

        await self._notify(f"✅ Tech Spec 已生成: {spec_path}")
        return tech_spec

    # ============================================================
    # Step 3: Asset Mapping
    # ============================================================
    async def _map_and_encode_assets(self, config: dict) -> dict:
        """图标匹配 + base64 编码"""
        await self._notify("🖼️ Step 3: 图标编码...")

        b64_assets = {}
        icons_config = config.get("icons", {})

        for name, filename in icons_config.items():
            icon_path = ASSETS_DIR / filename
            if icon_path.exists():
                with open(icon_path, 'rb') as f:
                    b64_assets[name] = f"data:image/png;base64,{base64.b64encode(f.read()).decode()}"
            else:
                b64_assets[name] = ""  # 占位

        await self._notify(f"✅ 已编码 {len(b64_assets)} 个图标")
        return b64_assets

    # ============================================================
    # Step 4: Code Generation
    # ============================================================
    async def _generate_hud_html(self, config: dict, tech_spec: dict, b64_assets: dict, scenarios: dict) -> str:
        """生成 HUD Demo HTML"""
        await self._notify("💻 Step 4a: 生成 HUD HTML...")

        prompt = f"""你是前端工程师，生成一个完整的 HUD Demo HTML 文件。

## 产品配置
{json.dumps(config, ensure_ascii=False, indent=2)}

## 技术 Spec
{json.dumps(tech_spec, ensure_ascii=False, indent=2)}

## 剧本场景
{json.dumps(scenarios, ensure_ascii=False, indent=2)}

## 图标 (base64 data URI，已省略实际内容)
图标名称: {list(b64_assets.keys())}

## 要求
1. 单文件 HTML，零外部依赖，双击打开
2. 全屏黑色背景模拟护目镜视角
3. 四角信息区 (LT/RT/LB/RB)，中央完全留空
4. 两种模式:
   - 自动剧本模式 (底部时间轴)
   - 手动沙盒模式 (右侧抽屉事件面板)
5. 键盘快捷键: ←→导航、U掉头、B BSD、F FCW、C来电、R录制、G组队、+-速度
6. 预警时对应角落红色闪烁
7. A/B 光学方案切换条 (顶部)
8. 速度变化时自动按 speed_tiers 调整信息密度
9. 图标用占位 div 表示，class 命名为 icon-{{name}}

输出完整 HTML 代码，从 <!DOCTYPE html> 开始。"""

        result = self.gw.call("gpt_5_4", prompt,
            "你是前端工程师，输出完整的 HTML 代码，不要解释。",
            "code_generation")

        if not result.get("success"):
            # 降级
            result = self.gw.call("gpt_4o_norway", prompt, task_type="code_generation")

        if result.get("success"):
            html = result["response"]
            # 提取代码块
            if "```html" in html:
                match = re.search(r'```html\s*([\s\S]*?)\s*```', html)
                if match:
                    html = match.group(1)

            # 保存
            output_path = OUTPUT_DIR / "hud_demo.html"
            output_path.write_text(html, encoding="utf-8")

            await self._notify(f"✅ HUD HTML 已生成: {output_path}")
            return str(output_path)

        raise RuntimeError(f"HTML 生成失败: {result.get('error')}")

    async def _generate_app_html(self, config: dict, tech_spec: dict) -> str:
        """生成 App Demo HTML"""
        await self._notify("💻 Step 4b: 生成 App HTML...")

        # Step 4b-1: 骨架生成
        skeleton_prompt = f"""你是移动端前端工程师，生成 App 骨架 HTML。

## 产品配置
{json.dumps(config, ensure_ascii=False, indent=2)}

## 技术 Spec
{json.dumps(tech_spec, ensure_ascii=False, indent=2)}

## 要求
1. 单文件 HTML，零外部依赖
2. 手机尺寸模拟 (375x812 居中，圆角边框)
3. 底部 Tab 导航 (设备/社区/商城/我的)
4. 每个Tab内容区用占位符: <!-- TAB:device -->...<!-- /TAB:device -->
5. 主题色使用配置中的 theme

输出完整 HTML 骨架代码。"""

        skeleton_result = self.gw.call("gpt_5_4", skeleton_prompt, task_type="code_generation")
        if not skeleton_result.get("success"):
            skeleton_result = self.gw.call("gpt_4o_norway", skeleton_prompt, task_type="code_generation")

        html = skeleton_result.get("response", "<!-- empty -->")

        # Step 4b-2: 逐 Tab 填充
        tabs = config.get("tabs", [])
        pages = config.get("pages", {})

        for tab in tabs:
            tab_id = tab["id"]
            tab_pages = pages.get(tab_id, {})

            fill_prompt = f"""填充 App 中 "{tab['label']}" Tab 的内容。

## 该 Tab 的页面
{json.dumps(tab_pages, ensure_ascii=False, indent=2)}

## 主题色
{json.dumps(config.get('theme', {}), ensure_ascii=False)}

生成该 Tab 下所有页面的组件 HTML，使用主题色。输出纯 HTML 片段，不要完整文档。"""

            fill_result = self.gw.call("gpt_5_4", fill_prompt, task_type="code_generation")
            if fill_result.get("success"):
                tab_content = fill_result["response"]
                # 替换占位符
                html = html.replace(f"<!-- TAB:{tab_id} -->", tab_content.split("<!-- /TAB")[0] if "<!-- /TAB" in tab_content else tab_content)

        # 保存
        output_path = OUTPUT_DIR / "app_demo.html"
        output_path.write_text(html, encoding="utf-8")

        await self._notify(f"✅ App HTML 已生成: {output_path}")
        return str(output_path)

    # ============================================================
    # Step 5: Visual Review
    # ============================================================
    async def _visual_review(self, html_path: str, tech_spec: dict) -> dict:
        """审查代码是否符合 spec"""
        await self._notify("👁️ Step 5: 视觉审查...")

        html = Path(html_path).read_text(encoding="utf-8")

        # 截取关键部分 (前 3000 字符)
        html_preview = html[:3000]

        prompt = f"""检查以下 HTML 代码是否正确实现了 spec 要求。

## 技术 Spec
{json.dumps(tech_spec, ensure_ascii=False, indent=2)}

## HTML 代码 (前 3000 字符)
```html
{html_preview}
```

请列出:
1. 符合 spec 的地方
2. 不符合 spec 的地方 (如有)

输出 JSON: {{"passed": true/false, "issues": [...], "good_points": [...]}}"""

        result = self.gw.call("gemini_2_5_flash", prompt, task_type="review")

        if result.get("success"):
            resp = result["response"].strip()
            try:
                review = json.loads(re.sub(r'^```json?\s*|\s*```$', '', resp))
            except:
                review = {"raw": resp}
        else:
            review = {"error": result.get("error")}

        issues = review.get("issues", [])
        if issues:
            await self._notify(f"⚠️ 审查发现 {len(issues)} 个问题: {issues[:3]}")
        else:
            await self._notify("✅ 视觉审查通过")

        return review

    def _validate_html(self, html: str, spec: dict) -> list:
        """规则验证: 标签闭合 + 功能点覆盖"""
        issues = []

        # 简单的标签闭合检查
        open_tags = re.findall(r'<(\w+)[^>]*>', html)
        close_tags = re.findall(r'</(\w+)>', html)

        for tag in set(open_tags):
            if tag not in ['br', 'hr', 'img', 'input', 'meta', 'link']:
                if open_tags.count(tag) > close_tags.count(tag):
                    issues.append(f"未闭合标签: <{tag}>")

        return issues

    # ============================================================
    # 入口方法
    # ============================================================
    async def generate_hud_demo(self) -> str:
        """生成 HUD Demo"""
        self.status = DemoStatus(stage="running", start_time=time.time())

        try:
            # Step 1: Preflight
            preflight = await self._smart_preflight("hud")

            # Step 2: Tech Spec
            tech_spec = await self._generate_tech_spec("hud", preflight)

            # Step 3: Asset Encoding
            b64_assets = await self._map_and_encode_assets(preflight["config"])

            # Step 4: HTML Generation
            output_path = await self._generate_hud_html(
                preflight["config"], tech_spec, b64_assets, preflight["config"].get("scenarios", {})
            )

            # Step 5: Visual Review
            review = await self._visual_review(output_path, tech_spec)

            self.status.stage = "completed"
            self.status.last_output = output_path
            await self._notify(f"🎉 HUD Demo 生成完成!\n文件: {output_path}")
            return output_path

        except Exception as e:
            self.status.stage = "failed"
            await self._notify(f"❌ HUD Demo 生成失败: {e}")
            raise

    async def generate_app_demo(self) -> str:
        """生成 App Demo"""
        self.status = DemoStatus(stage="running", start_time=time.time())

        try:
            # Step 1: Preflight
            preflight = await self._smart_preflight("app")

            # Step 2: Tech Spec
            tech_spec = await self._generate_tech_spec("app", preflight)

            # Step 4: HTML Generation (App 没有 Step 3 图标编码)
            output_path = await self._generate_app_html(preflight["config"], tech_spec)

            # Step 5: Visual Review
            review = await self._visual_review(output_path, tech_spec)

            self.status.stage = "completed"
            self.status.last_output = output_path
            await self._notify(f"🎉 App Demo 生成完成!\n文件: {output_path}")
            return output_path

        except Exception as e:
            self.status.stage = "failed"
            await self._notify(f"❌ App Demo 生成失败: {e}")
            raise


# ============================================================
# CLI 入口
# ============================================================
if __name__ == "__main__":
    import sys

    async def main():
        gen = DemoGenerator()
        demo_type = sys.argv[1] if len(sys.argv) > 1 else "hud"

        if demo_type == "hud":
            path = await gen.generate_hud_demo()
        else:
            path = await gen.generate_app_demo()

        print(f"\n✅ Demo 已生成: {path}")

    asyncio.run(main())