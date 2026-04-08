"""
@description: 生成器 - 拿圆桌结论生成具体产物（分段生成版）
@dependencies: model_gateway, task_spec, roundtable
@last_modified: 2026-04-08

v2 新增：
- generator_input_mode: 动态选择输入源（raw_proposal / executive_summary / auto）
- raw_proposal 模式用于代码类输出，保留完整技术细节
- executive_summary 模式用于文档类输出，精简版本

分段生成策略：
- 段1: CSS + HTML 骨架（布局、配色变量、基础结构）
- 段2: 状态机 JS（7态定义、优先级栈、S0-S3 速度分级）
- 段3: 渲染函数（各状态的四角内容、预警闪烁动画、颜色映射）
- 段4: 自动剧本 + 时间轴（3条剧本事件序列、播放控制）
- 段5: 沙盒面板 + A/B光学切换 + 开机自检 + 键盘快捷键

每段包含：前面段的代码上下文 + 明确的接口约定
最后拼装成单 HTML 文件
"""
from pathlib import Path
from typing import Dict, Any, List
from dataclasses import dataclass
import re

from src.utils.model_gateway import get_model_gateway
from scripts.roundtable.task_spec import TaskSpec


@dataclass
class RoundtableResult:
    """圆桌结果（简化版，实际在 roundtable.py 定义）"""
    final_proposal: str
    executive_summary: str
    all_constraints: List[str]
    confidence_map: Dict[str, str]
    full_log_path: str
    rounds: int
    reviewer_amendments: str = ""  # v2: Reviewer 补充修改


class Generator:
    """生成器

    职责：
    - 拿圆桌收敛后的方案，分 5 段生成产物
    - 根据缺陷清单定点修复
    - v2: 支持 generator_input_mode 动态选择输入源
    """

    # 输出类型对应的模型
    OUTPUT_TYPE_MODEL = {
        "html": "gpt_5_4",
        "markdown": "gpt_5_4",
        "json": "gpt_5_4",
        "code": "gpt_5_4",
    }

    # v2: auto 模式下输出类型到输入模式的映射
    OUTPUT_TYPE_INPUT_MODE = {
        "html": "raw_proposal",
        "code": "raw_proposal",
        "json": "raw_proposal",
        "jsx": "raw_proposal",
        "markdown": "executive_summary",
        "report": "executive_summary",
        "pptx": "executive_summary",
    }

    # 分段定义
    SEGMENTS = [
        {
            "name": "CSS + HTML 骨架",
            "desc": "布局、配色变量、四象限固定结构、中央留空",
        },
        {
            "name": "状态机 JS",
            "desc": "7态定义(MODE_*)、优先级栈、S0-S3 速度分级、setMode/emitEvent 接口",
        },
        {
            "name": "渲染函数",
            "desc": "各状态的四角内容、ADAS 预警闪烁动画、颜色语义映射",
        },
        {
            "name": "自动剧本 + 时间轴",
            "desc": "3 条剧本事件序列、播放/暂停/跳转控制、时间轴 UI",
        },
        {
            "name": "沙盒面板 + 控制层",
            "desc": "手动触发按钮、A/B 光学切换、开机自检动画、键盘快捷键",
        },
    ]

    def __init__(self, gw=None):
        self.gw = gw or get_model_gateway()

    def _get_input_source(self, task: TaskSpec, rt_result: RoundtableResult) -> str:
        """v2: 根据 generator_input_mode 选择输入源"""
        mode = task.generator_input_mode

        if mode == "auto":
            mode = self.OUTPUT_TYPE_INPUT_MODE.get(task.output_type, "executive_summary")

        if mode == "raw_proposal":
            # 使用完整方案 + Reviewer 补充修改
            source = rt_result.final_proposal
            if rt_result.reviewer_amendments:
                source += f"\n\n【Reviewer 补充修改】\n{rt_result.reviewer_amendments}"
            return source
        else:
            # 使用执行摘要
            return rt_result.executive_summary

    async def generate(self, task: TaskSpec, rt_result: RoundtableResult) -> str:
        """生成产物（分段生成版）

        v2: 支持 generator_input_mode 动态选择输入源

        Args:
            task: TaskSpec
            rt_result: 圆桌收敛结果

        Returns:
            生成的产物内容
        """
        # v2: 选择输入源
        input_source = self._get_input_source(task, rt_result)
        print(f"  [Generator] 输入模式: {task.generator_input_mode}, 源长度: {len(input_source)} 字")

        if task.output_type != "html":
            # 非 HTML 直接单次生成
            return await self._generate_single(task, rt_result, input_source)

        # HTML 分段生成
        return await self._generate_html_segmented(task, rt_result, input_source)

    async def _generate_single(self, task: TaskSpec, rt_result: RoundtableResult,
                                input_source: str = "") -> str:
        """单次生成（非 HTML 类型）

        v2: 使用 input_source 而非 executive_summary
        """
        model_name = self.OUTPUT_TYPE_MODEL.get(task.output_type, "gpt_5_4")

        # v2: 使用动态选择的输入源
        source = input_source or rt_result.executive_summary

        prompt = f"""【输入源】
{source[:5000]}

【硬约束】
{chr(10).join(rt_result.all_constraints[:10])}

【验收标准】
{chr(10).join(task.acceptance_criteria)}

请根据输入源生成完整产物。直接输出内容，不解释。"""

        result = self.gw.call(
            model_name=model_name,
            prompt=prompt,
            system_prompt=f"你是专业的{task.output_type}生成器。",
            task_type="generation",
        )

        if result.get("success"):
            return result.get("response", "")
        return ""

    async def _generate_html_segmented(self, task: TaskSpec, rt_result: RoundtableResult,
                                        input_source: str = "") -> str:
        """HTML 分段生成

        v2: 使用 input_source 而非 executive_summary
        """
        segments_code = []

        # v2: 使用动态选择的输入源
        source = input_source or rt_result.executive_summary

        # 接口约定（各段必须遵守）
        interface_contract = """
【接口约定 - 必须严格遵守】
DOM ID 约定：
- #hud-container: 主容器
- #lt-zone, #lb-zone, #rt-zone, #rb-zone: 四象限区域
- #timeline-bar: 时间轴
- #control-panel: 控制面板
- #sandbox-panel: 沙盒面板

JS 全局变量：
- window.currentMode: 当前状态（字符串）
- window.currentSpeed: 当前速度等级（S0-S3）
- window.scriptPlaying: 剧本是否在播放

JS 函数签名：
- setMode(mode): 切换状态
- emitEvent(event): 触发事件
- renderZone(zoneId, content): 更新区域内容
- flashWarning(zoneId, color): 预警闪烁
"""

        for i, seg in enumerate(self.SEGMENTS):
            print(f"  [Generator] 生成段 {i+1}/5: {seg['name']}...")

            # 构建上下文：包含前面段的代码
            prev_context = ""
            if segments_code:
                prev_context = f"""
【前面段的代码 - 仅作参考，不要重复】
```html
{chr(10).join(segments_code[-2:]) if len(segments_code) >= 2 else segments_code[-1] if segments_code else ''}
```
"""

            prompt = f"""【输入源（本轮任务相关部分）】
{source[:3000]}

【本轮任务：{seg['name']}】
{seg['desc']}

{interface_contract}

{prev_context}

【输出要求】
1. 只输出本段的代码（不要输出完整的 HTML）
2. 段1 输出：<!DOCTYPE><html><head><style>CSS</style></head><body><div id="hud-container">...</div>
3. 段2-5 输出：<script>本段 JS 代码</script>
4. 严格遵守接口约定，确保与其他段兼容

直接输出代码，不要解释。
"""

            # v2: 分段失败重试 + 换模型
            code = await self._generate_segment_with_retry(
                prompt=prompt,
                segment_name=seg['name'],
                segment_index=i
            )
            segments_code.append(code)

        # 拼装成完整 HTML
        full_html = self._assemble_html(segments_code, task, rt_result)

        # 基础验证
        validation_result = self._validate_html(full_html)
        if validation_result["errors"]:
            print(f"  [Generator] HTML 验证警告: {validation_result['errors']}")

        return full_html

    async def _generate_segment_with_retry(self, prompt: str, segment_name: str,
                                            segment_index: int) -> str:
        """v2: 分段生成带重试 + 换模型

        重试链：gpt_5_4 → gpt_5_4（重试）→ gemini_3_1_pro
        """
        # 模型重试链
        models = ["gpt_5_4", "gpt_5_4", "gemini_3_1_pro"]
        last_error = None

        for attempt, model in enumerate(models):
            result = self.gw.call(
                model_name=model,
                prompt=prompt,
                system_prompt="你是专业的 HTML/JS 开发者，输出代码片段，不解释。",
                task_type="generation",
            )

            if result.get("success"):
                code = result.get("response", "")
                if self._validate_segment(code, segment_index):
                    if attempt > 0:
                        print(f"  [Generator] 段 {segment_index+1} 重试成功（模型: {model}）")
                    return code
                else:
                    last_error = "段验证失败"
            else:
                last_error = result.get("error", "模型调用失败")

        # 所有重试失败
        print(f"  [Generator] 段 {segment_index+1} ({segment_name}) 3次失败: {last_error}")
        return f"<!-- Segment {segment_index+1} ({segment_name}) generation failed: {last_error} -->"

    def _validate_segment(self, code: str, segment_index: int) -> bool:
        """验证分段代码基本质量"""
        if not code or len(code) < 50:
            return False

        # 段1 应该包含 HTML 骨架
        if segment_index == 0:
            return "<!DOCTYPE" in code or "<html" in code or "<style" in code

        # 段2-5 应该包含 JS 代码
        return "function" in code or "const " in code or "var " in code or "<script" in code

    def _assemble_html(self, segments: List[str], task: TaskSpec, rt_result: RoundtableResult) -> str:
        """拼装成完整 HTML"""

        # 段1 应该包含 HTML 骨架和 CSS
        # 段2-5 应该是 script 标签

        # 提取段1的 HTML 骨架
        segment1 = segments[0] if segments else ""

        # 收集所有 script 段
        script_parts = []
        for seg in segments[1:]:
            # 提取 script 内容
            script_match = re.search(r'<script[^>]*>(.*?)</script>', seg, re.DOTALL)
            if script_match:
                script_parts.append(script_match.group(1))
            else:
                script_parts.append(seg)

        # 确保 segment1 有 </body></html> 闭合
        if "</html>" not in segment1:
            # 需要添加闭合标签
            if "</body>" not in segment1:
                close_tags = "\n".join(script_parts) + "\n</body>\n</html>"
            else:
                # 在 </body> 前插入 scripts
                segment1 = segment1.replace("</body>", "\n".join(script_parts) + "\n</body>")
                close_tags = "</html>"
        else:
            close_tags = ""

        if close_tags and "</html>" not in segment1:
            full_html = segment1 + "\n<script>\n" + "\n".join(script_parts) + "\n</script>\n</body>\n</html>"
        else:
            full_html = segment1

        return full_html

    def _validate_html(self, html: str) -> Dict[str, Any]:
        """基础 HTML 验证"""
        errors = []

        # 检查必要标签
        required_tags = ["<!DOCTYPE", "<html", "</html>", "<head>", "</head>", "<body>", "</body>"]
        for tag in required_tags:
            if tag not in html:
                errors.append(f"缺少标签: {tag}")

        # 检查 script 闭合
        script_opens = html.count("<script")
        script_closes = html.count("</script>")
        if script_opens != script_closes:
            errors.append(f"script 标签不匹配: {script_opens} 开, {script_closes} 闭")

        # 检查 style 闭合
        style_opens = html.count("<style")
        style_closes = html.count("</style>")
        if style_opens != style_closes:
            errors.append(f"style 标签不匹配: {style_opens} 开, {style_closes} 闭")

        return {"passed": len(errors) == 0, "errors": errors}

    async def fix(self, current_output: str, issues: List[str],
                  rt_result: RoundtableResult) -> str:
        """定点修复

        Args:
            current_output: 当前输出代码
            issues: 具体缺陷清单
            rt_result: 圆桌结果（用于理解原始意图）

        Returns:
            修复后的输出
        """
        prompt = f"""【当前输出】
{current_output[:3000]}

【缺陷清单】
{chr(10).join(issues)}

【原始意图（执行摘要）】
{rt_result.executive_summary[:1000]}

请根据缺陷清单定点修复输出。
只修复指出的问题，不要重写其他部分。
直接输出修复后的完整内容。
"""

        result = self.gw.call_with_fallback(
            primary="gpt_5_4",
            fallback="gpt_4o_norway",
            prompt=prompt,
            system_prompt="你是代码修复专家，只修复指定问题，保持其他部分不变。",
            task_type="generation",
        )

        if result.get("success"):
            return result.get("response", "")
        return current_output

    async def escalate(self, current_output: str, stuck_issues: List[str],
                       rt_result: RoundtableResult) -> str:
        """升级策略：换更强模型或拆解问题

        当同一问题连续两轮未修复时触发。
        """
        # 尝试最强模型
        prompt = f"""【当前输出存在问题，需要彻底重新思考】

【当前输出】
{current_output[:2000]}

【卡住的问题】
{chr(10).join(stuck_issues)}

【原始意图】
{rt_result.executive_summary}

请从根本上重新设计解决方案，不要只是修补。
"""

        # 使用最强推理模型
        result = self.gw.call(
            model_name="o3-deep-research",
            prompt=prompt,
            system_prompt="你是顶级架构师，需要从根本上解决问题。",
            task_type="deep_research",
        )

        if result.get("success"):
            return result.get("response", "")

        # 降级到 gpt_5_4
        return await self.fix(current_output, stuck_issues, rt_result)