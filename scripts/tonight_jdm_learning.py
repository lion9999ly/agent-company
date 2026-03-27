"""
@description: JDM供应商定向学习脚本 - 专项研究代工厂、光学、声学、电池供应商
@dependencies: src.utils.model_gateway, src.tools.knowledge_base, src.tools.tool_registry
@last_modified: 2026-03-22
"""
import json
import time
import re
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.model_gateway import get_model_gateway
from src.tools.knowledge_base import add_knowledge, get_knowledge_stats, KB_ROOT
from src.tools.tool_registry import ToolRegistry

registry = ToolRegistry()
gateway = get_model_gateway()

# JDM 供应商选型专项学习主题
JDM_TOPICS = [
    # 歌尔深挖
    "Goertek smart glasses helmet ODM JDM capability 2026",
    "歌尔股份 智能穿戴 代工 客户案例 Meta Ray-Ban",
    "Goertek XR AR headset manufacturing cost pricing",
    "歌尔 Alpha Labs 智能眼镜 研发 量产 报价",
    "Goertek annual report 2025 smart wearable revenue",

    # 替代 JDM 供应商
    "智能头盔 ODM JDM 供应商 除歌尔外 2026",
    "Luxshare 立讯精密 smart wearable ODM capability",
    "Flex Jabil smart helmet wearable manufacturing",
    "BYD Electronics 比亚迪电子 智能穿戴 代工",
    "Pegatron 和硕 smart device ODM 2026",
    "Compal 仁宝 smart wearable ODM capability",
    "Inventec 英业达 smart glasses AR headset ODM",
    "Sunny Optical 舜宇光学 AR光学模组 供应商",
    "AAC Technologies 瑞声科技 声学 触觉 穿戴设备",
    "智能头盔 小型代工厂 深圳 东莞 方案商 2026",

    # 光学方案商对比
    "AR HUD waveguide supplier comparison 2026 Lumus DigiLens",
    "Micro OLED display supplier Sony JBD BOE 2026 smart glasses",
    "光波导供应商 珑璟光电 灵犀微光 谷东科技 对比 2026",
    "BirdBath 光学方案 成本 供应商 vs 光波导 vs 自由曲面",

    # 声学方案商对比
    "骨传导扬声器 供应商 韶音 歌尔 瑞声 对比 参数",
    "MEMS microphone supplier Knowles InvenSense Goertek comparison",
    "主动降噪 ANC 方案商 头盔 穿戴设备 芯片 BES Qualcomm",
    "speaker driver smart helmet audio supplier 2026",

    # 摄像头方案商对比
    "微型摄像头 模组 供应商 舜宇 丘钛 欧菲光 穿戴设备",
    "OmniVision OV sensor smart glasses helmet camera module",
    "Sony IMX sensor small form factor wearable camera 2026",

    # BOM 成本分析
    "smart helmet BOM cost breakdown component pricing 2026",
    "AR glasses BOM analysis Meta Ray-Ban teardown cost",
    "智能头盔 量产成本 分析 芯片 光学 声学 电池 结构件",
    "helmet injection mold tooling cost China supplier",

    # 歌尔 vs 竞争对手直接对比
    "Goertek vs Luxshare smart wearable ODM comparison",
    "歌尔 vs 立讯 vs 比亚迪电子 智能穿戴 代工 对比",
    "Goertek smart glasses customer list Meta Qualcomm partnership",
]


def run_jdm_learning():
    """执行 JDM 供应商定向学习"""
    print(f"[JDM Learning] 启动 JDM 供应商定向学习，共 {len(JDM_TOPICS)} 个主题")

    learned = 0
    failed = 0

    for i, topic in enumerate(JDM_TOPICS, 1):
        print(f"\n[{i}/{len(JDM_TOPICS)}] 搜索: {topic[:60]}...")

        try:
            # 用 deep_research 获取高质量内容
            result = registry.call("deep_research", topic)

            if not result.get("success") or len(result.get("data", "")) < 200:
                # fallback 到 tavily
                result = registry.call("tavily_search", topic)

            if not result.get("success") or len(result.get("data", "")) < 200:
                print(f"  ❌ 搜索失败或内容过少")
                failed += 1
                continue

            content = result["data"][:5000]

            # LLM 提炼
            refine_prompt = (
                f"你是智能骑行头盔项目的供应链研究专家。\n"
                f"请从以下搜索结果中提炼与「JDM/ODM供应商选型」相关的关键信息。\n"
                f"重点关注：公司名称、核心能力、代工客户、报价水平、产能规模、技术参数。\n"
                f"保留所有具体数字（价格、参数、份额）。\n"
                f"输出 JSON：{{\"title\": \"标题(含公司名)\", \"domain\": \"components\", "
                f"\"summary\": \"300字结构化摘要\", \"tags\": [\"标签\"]}}\n\n"
                f"搜索词：{topic}\n搜索结果：\n{content[:4000]}"
            )

            llm_result = gateway.call_azure_openai(
                "cpo", refine_prompt,
                "只输出 JSON。不要有其他内容。",
                "jdm_learning"
            )

            if not llm_result.get("success"):
                print(f"  ❌ LLM 提炼失败")
                failed += 1
                continue

            response = llm_result["response"].strip()
            response = re.sub(r'^```json\s*', '', response)
            response = re.sub(r'\s*```$', '', response)

            item = json.loads(response)

            domain = item.get("domain", "components")
            if domain not in ("competitors", "components", "standards", "lessons"):
                domain = "components"

            add_knowledge(
                title=item.get("title", topic[:50])[:80],
                domain=domain,
                content=item.get("summary", "")[:800],
                tags=item.get("tags", []) + ["jdm_study"],
                source="jdm_learning",
                confidence="high"
            )

            learned += 1
            print(f"  ✅ [{domain}] {item.get('title', '')[:50]}")

        except Exception as e:
            print(f"  ❌ 异常: {e}")
            failed += 1

        # 避免 API 限流
        time.sleep(3)

    stats = get_knowledge_stats()
    total = sum(stats.values())
    print(f"\n[JDM Learning] 完成！新增: {learned} 条 | 失败: {failed} 条")
    print(f"[JDM Learning] 知识库: {stats}, 总计: {total}")

    return f"JDM 定向学习完成：新增 {learned} 条，失败 {failed} 条"


if __name__ == "__main__":
    run_jdm_learning()