"""
@description: 知识图谱扩展器 - 从已知节点出发，自动发现和深挖关联节点
@dependencies: src.utils.model_gateway, src.tools.knowledge_base, src.tools.tool_registry
@last_modified: 2026-03-25
"""
import json
import re
import time
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.model_gateway import get_model_gateway
from src.tools.knowledge_base import add_knowledge, add_report, search_knowledge, get_knowledge_stats, KB_ROOT
from src.tools.tool_registry import get_tool_registry


# ==========================================
# 知识图谱扩展：种子节点 -> 发现关联节点 -> 逐个深挖
# ==========================================

# 需要深挖的领域种子（每个种子会自动发现整个家族）
DOMAIN_SEEDS = {
    "ar_xr_soc": {
        "name": "AR/XR 可穿戴 SoC 芯片",
        "seeds": [
            "Qualcomm AR1 Gen1",
            "Qualcomm AR2 Gen1",
            "Qualcomm XR2 Gen2",
            "Qualcomm XR2+ Gen2",
        ],
        "expansion_prompt": (
            "你是芯片选型专家。基于以下已知芯片，列出我们可能遗漏的同家族/竞品芯片。\n"
            "已知: {known_list}\n\n"
            "请补充：\n"
            "1. 同厂商的其他型号（如高通 AR1+、AR2、S5/S7 Gen2 等）\n"
            "2. 直接竞品（恒玄 BES2800/2900、联发科 Dimensity 相关、瑞芯微 RK3588、全志等）\n"
            "3. 特定场景芯片（专用音频 SoC、专用视觉 ISP、专用 AI 加速器）\n"
            "4. 新兴方案（RISC-V 可穿戴芯片、自研 NPU 等）\n\n"
            "只输出 JSON 数组，每个元素：\n"
            '[{{"chip": "具体型号", "vendor": "厂商", "category": "分类", '
            '"why_relevant": "为什么和智能摩托车全盔相关"}}]'
        ),
        "deep_search_template": [
            "{chip} datasheet specifications power consumption 2026",
            "{chip} {vendor} product brief features target applications",
            "{chip} vs {competitor} comparison benchmark wearable",
            "{chip} 参数 功耗 算力 接口 适用场景 价格",
        ],
        "knowledge_template": (
            "请基于以下搜索结果，输出关于 {chip} 的完整技术档案。\n\n"
            "必须包含（有多少写多少，没有的标注'未查到'）：\n"
            "1. 基本参数：制程、CPU/GPU/NPU 架构和算力、主频\n"
            "2. 接口：摄像头(CSI)、显示(DSI/MIPI)、音频(I2S/PDM)、无线(BT/WiFi/UWB)\n"
            "3. 功耗：典型功耗、峰值功耗、待机功耗\n"
            "4. 适用场景：官方定位的目标产品类型\n"
            "5. 软件生态：支持的 OS、SDK、开发工具\n"
            "6. 供货状态：是否量产、MOQ、大致价格区间\n"
            "7. 已知客户/产品：哪些产品在用这个芯片\n"
            "8. 对智能摩托车全盔的适配度评估：能支撑哪些功能，不能支撑什么\n\n"
            "搜索结果：\n{search_data}"
        ),
    },
    "audio_soc": {
        "name": "音频/通讯 SoC 芯片",
        "seeds": [
            "恒玄 BES2800",
            "高通 QCC5181",
            "高通 S5 Gen2",
        ],
        "expansion_prompt": (
            "你是音频芯片选型专家。基于以下已知芯片，列出同家族和竞品。\n"
            "已知: {known_list}\n\n"
            "请补充：\n"
            "1. 恒玄全系列（BES2600/2700/2800/2900/5200 等）\n"
            "2. 高通音频芯片全系列（QCC3xxx/5xxx、S3/S5/S7 Gen2 等）\n"
            "3. 联发科音频芯片（MT2523、Airoha AB1562 等）\n"
            "4. 其他（Realtek、Cirrus Logic、AKM 等可穿戴音频方案）\n"
            "5. ANC/ENC 专用 DSP（Qualcomm adaptive ANC、Sony V1 等）\n\n"
            "只输出 JSON 数组：\n"
            '[{{"chip": "型号", "vendor": "厂商", "category": "分类", '
            '"why_relevant": "与智能摩托车全盔的关系"}}]'
        ),
        "deep_search_template": [
            "{chip} datasheet ANC ENC specifications 2026",
            "{chip} {vendor} audio SoC features bluetooth wearable",
            "{chip} vs {competitor} ANC noise cancellation comparison",
            "{chip} 参数 蓝牙 降噪 ANC ENC 价格 功耗",
        ],
        "knowledge_template": (
            "请基于以下搜索结果，输出关于 {chip} 的完整技术档案。\n\n"
            "必须包含：\n"
            "1. 基本参数：蓝牙版本、支持编解码(aptX/LC3/AAC)、DSP 算力\n"
            "2. 降噪能力：ANC 档位、ENC 通话降噪、风噪抑制能力\n"
            "3. 音频接口：扬声器驱动、麦克风阵列支持数量、骨传导支持\n"
            "4. 功耗：ANC on/off 功耗差异、通话功耗\n"
            "5. 无线：BT 5.x、BLE Audio、Auracast、多点连接\n"
            "6. 已知产品：哪些耳机/头盔在用\n"
            "7. 对智能摩托车全盔的适配度：100km/h 风噪下能否有效 ANC\n\n"
            "搜索结果：\n{search_data}"
        ),
    },
    "optical_hud": {
        "name": "HUD/AR 光学方案",
        "seeds": [
            "Lumus waveguide",
            "DigiLens holographic waveguide",
        ],
        "expansion_prompt": (
            "你是 AR/HUD 光学方案专家。基于以下已知方案，列出我们可能遗漏的方案商和技术路线。\n"
            "已知: {known_list}\n\n"
            "请补充：\n"
            "1. 光波导方案商（珑璟光电、灵犀微光、谷东科技、WaveOptics/Snap、Vuzix 等）\n"
            "2. Birdbath/自由曲面方案商\n"
            "3. Micro LED/OLED 微显示供应商（JBD、SeeYA、BOE、Kopin、Sony 等）\n"
            "4. 光引擎/光机模组集成商\n"
            "5. 头盔专用 HUD 方案（和眼镜不同的技术约束）\n\n"
            "只输出 JSON 数组：\n"
            '[{{"chip": "方案/供应商", "vendor": "公司", "category": "技术路线", '
            '"why_relevant": "与摩托车全盔 HUD 的关系"}}]'
        ),
        "deep_search_template": [
            "{chip} {vendor} waveguide specifications FOV brightness 2026",
            "{chip} smart glasses motorcycle helmet HUD integration",
            "{chip} vs {competitor} AR optics comparison cost weight",
            "{chip} 光波导 参数 FOV 亮度 重量 价格 良率",
        ],
        "knowledge_template": (
            "请基于以下搜索结果，输出关于 {chip} 的完整技术档案。\n\n"
            "必须包含：\n"
            "1. 技术路线：衍射波导/几何波导/Birdbath/自由曲面/其他\n"
            "2. 光学参数：FOV、入眼亮度(nits)、分辨率、色彩、透过率\n"
            "3. 物理参数：模组重量、体积、厚度\n"
            "4. 成本：单价区间、MOQ、良率\n"
            "5. 适配性：能否集成到全盔面罩内、变色镜片兼容性\n"
            "6. 已知客户/产品\n"
            "7. 对摩托车全盔的适配度：强光/隧道/振动/温度环境下的表现\n\n"
            "搜索结果：\n{search_data}"
        ),
    },
}


def expand_one_domain(domain_key: str, progress_callback=None) -> str:
    """对一个领域执行完整的知识图谱扩展"""
    domain = DOMAIN_SEEDS.get(domain_key)
    if not domain:
        return f"未知领域: {domain_key}"

    gateway = get_model_gateway()
    registry = get_tool_registry()
    name = domain["name"]
    seeds = domain["seeds"]

    print(f"\n{'='*60}")
    print(f"[KG Expand] 开始扩展: {name}")
    print(f"[KG Expand] 种子节点: {len(seeds)} 个")
    print(f"{'='*60}")

    if progress_callback:
        progress_callback(f"[KG Expand] {name}...")

    report_lines = [f"[KG Expand] {name}"]

    # Step 1: 从种子发现更多节点
    known_list = ", ".join(seeds)
    expand_prompt = domain["expansion_prompt"].format(known_list=known_list)

    expand_result = gateway.call_azure_openai("cpo", expand_prompt, "只输出 JSON 数组。", "kg_expand")

    all_chips = []
    for seed in seeds:
        all_chips.append({"chip": seed, "vendor": "", "category": "seed", "why_relevant": "种子节点"})

    if expand_result.get("success"):
        try:
            resp = expand_result["response"].strip()
            resp = re.sub(r'^```json\s*', '', resp)
            resp = re.sub(r'\s*```$', '', resp)
            discovered = json.loads(resp)
            if isinstance(discovered, list):
                all_chips.extend(discovered)
                print(f"[KG Expand] 发现 {len(discovered)} 个新节点")
                report_lines.append(f"  发现 {len(discovered)} 个新节点（加上 {len(seeds)} 个种子 = {len(all_chips)} 个）")
        except:
            print("[KG Expand] 解析发现结果失败")

    # Step 2: 对每个节点深搜
    new_knowledge = 0
    for i, chip_info in enumerate(all_chips, 1):
        chip = chip_info.get("chip", "")
        vendor = chip_info.get("vendor", "")
        if not chip:
            continue

        print(f"\n  [{i}/{len(all_chips)}] 深搜: {chip}")
        if progress_callback and i % 3 == 0:
            progress_callback(f"  [{name}] {i}/{len(all_chips)}: {chip[:20]}...")

        # 多维度搜索
        search_data = ""
        templates = domain["deep_search_template"]

        # 找一个竞品名用于对比搜索
        competitor = ""
        for other in all_chips:
            if other["chip"] != chip and other.get("vendor", "") != vendor:
                competitor = other["chip"]
                break

        for tmpl in templates[:3]:  # 每个芯片搜 3 次
            query = tmpl.format(chip=chip, vendor=vendor, competitor=competitor)
            result = registry.call("deep_research", query)
            if result.get("success") and len(result.get("data", "")) > 200:
                search_data += f"\n---\n{result['data'][:3000]}"
            time.sleep(1)

        if not search_data or len(search_data) < 300:
            report_lines.append(f"  [SKIP] {chip} - 搜索结果不足")
            continue

        # 用领域专用模板提炼
        knowledge_prompt = domain["knowledge_template"].format(
            chip=chip, search_data=search_data[:8000]
        )

        refine_result = gateway.call_azure_openai("cpo", knowledge_prompt,
            f"你是{name}专家，输出完整技术档案。", "kg_refine")

        if refine_result.get("success") and len(refine_result["response"]) > 300:
            content = refine_result["response"]

            # 存入知识库
            add_knowledge(
                title=f"[技术档案] {chip} ({vendor})" if vendor else f"[技术档案] {chip}",
                domain="components",
                content=content[:1500],  # 技术档案允许更长
                tags=["knowledge_graph", "tech_profile", domain_key, vendor.lower()] if vendor else ["knowledge_graph", "tech_profile", domain_key],
                source=f"kg_expand:{domain_key}",
                confidence="high"
            )
            new_knowledge += 1
            report_lines.append(f"  [OK] {chip} ({len(content)} chars)")
        else:
            report_lines.append(f"  [FAIL] {chip} - 提炼失败")

        time.sleep(2)

    # Step 3: 生成领域决策树
    print(f"\n[KG Expand] 生成 {name} 决策树...")

    # 读取刚入库的所有档案
    all_profiles = []
    for f in KB_ROOT.rglob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if "knowledge_graph" in data.get("tags", []) and domain_key in data.get("tags", []):
                all_profiles.append(f"{data['title']}: {data['content'][:500]}")
        except:
            continue

    if len(all_profiles) >= 3:
        decision_prompt = (
            f"你是智能摩托车全盔项目的技术总监。\n"
            f"以下是 {name} 领域的 {len(all_profiles)} 份技术档案摘要。\n\n"
            f"请生成一份【选型决策树】，帮助在不同场景下快速选择最合适的方案。\n\n"
            f"格式要求：\n"
            f"1. 先列出关键决策维度（算力需求/功耗预算/接口要求/成本约束）\n"
            f"2. 按场景分支：\n"
            f"   - 如果只需要 HUD+语音+蓝牙 -> 推荐 XX，因为 YY\n"
            f"   - 如果需要 HUD+4K+ADAS -> 推荐 XX，因为 YY\n"
            f"   - 如果需要全功能（HUD+4K+ADAS+AI） -> 推荐 XX，但要注意 ZZ\n"
            f"3. 标注每个推荐的风险和 Plan B\n"
            f"4. 标注你不确定或数据不足的地方\n\n"
            f"技术档案：\n" + "\n---\n".join(all_profiles[:15])
        )

        tree_result = gateway.call_azure_openai("cpo", decision_prompt,
            "你是技术总监，生成选型决策树。", "kg_decision_tree")

        if tree_result.get("success"):
            add_report(
                title=f"[决策树] {name} 选型指南",
                domain="components",
                content=tree_result["response"],
                tags=["knowledge_graph", "decision_tree", domain_key],
                source=f"kg_expand:{domain_key}",
                confidence="high"
            )
            report_lines.append(f"\n  [DecisionTree] {len(tree_result['response'])} chars")
            print(f"[KG Expand] 决策树: {len(tree_result['response'])} 字")

    report_lines.append(f"\n  总计: 新增 {new_knowledge} 条技术档案")

    report = "\n".join(report_lines)
    print(f"\n{report}")
    return report


def expand_all_domains(progress_callback=None) -> str:
    """扩展所有领域的知识图谱"""
    reports = []
    for domain_key in DOMAIN_SEEDS:
        try:
            report = expand_one_domain(domain_key, progress_callback)
            reports.append(report)
        except Exception as e:
            import traceback
            reports.append(f"[KG Expand] {domain_key} 失败: {e}\n{traceback.format_exc()}")
        time.sleep(5)

    return "\n\n".join(reports)


if __name__ == "__main__":
    expand_all_domains()