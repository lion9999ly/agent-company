"""
@description: 知识图谱扩展器 - 从已知节点出发，自动发现和深挖关联节点
@dependencies: src.utils.model_gateway, src.tools.knowledge_base, src.tools.tool_registry
@last_modified: 2026-03-26
"""
# 加载 .env 环境变量（必须在其他 import 之前）
from dotenv import load_dotenv
load_dotenv()

import json
import re
import time
import sys
import psutil
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.litellm_gateway import get_model_gateway, call_for_search, call_for_refine
from src.tools.knowledge_base import add_knowledge, add_report, search_knowledge, get_knowledge_stats, KB_ROOT
from src.tools.tool_registry import get_tool_registry
from src.utils.progress_heartbeat import ProgressHeartbeat


# ==========================================
# 动态并行度（Phase 2.4）
# ==========================================
def _get_optimal_workers() -> int:
    """根据系统负载动态调整并行度"""
    try:
        cpu_pct = psutil.cpu_percent(interval=0.5)
        mem_pct = psutil.virtual_memory().percent
        if cpu_pct < 50 and mem_pct < 70:
            return 8   # 空闲：跑满
        elif cpu_pct < 80 and mem_pct < 85:
            return 4   # 中等负载：正常
        else:
            return 2   # 高负载：保守
    except Exception:
        return 4  # psutil 不可用时默认 4


# ==========================================
# 并行搜索辅助函数
# ==========================================
def _search_one_chip(chip_info: dict, domain: dict, registry) -> dict:
    """搜索单个芯片的所有维度（此函数在子线程中运行）"""
    chip = chip_info.get("chip", "")
    vendor = chip_info.get("vendor", "")
    category = chip_info.get("category", "")
    if not chip:
        return {"chip": chip, "vendor": vendor, "search_data": "", "success": False}

    templates = domain["deep_search_template"]
    search_data = ""

    # 同一个芯片的多次搜索也并行
    def _single_search(query):
        result = registry.call("deep_research", query)
        if result.get("success") and len(result.get("data", "")) > 200:
            return result["data"][:3000]
        return ""

    with ThreadPoolExecutor(max_workers=3) as inner_pool:
        queries = [t.format(chip=chip, vendor=vendor, competitor="") for t in templates[:3]]
        futures = {inner_pool.submit(_single_search, q): q for q in queries}
        for future in as_completed(futures):
            data = future.result()
            if data:
                search_data += f"\n---\n{data}"

    # === 加宽搜索策略 ===
    # 如果型号精确搜索结果不足 300 字，追加宽泛搜索
    if len(search_data) < 300:
        # 尝试提取品类关键词
        chip_words = chip.split()
        base_name = chip_words[0] if chip_words else chip

        # 加宽策略：搜品类+厂商+应用场景
        wider_queries = []
        if vendor:
            wider_queries.append(f"{vendor} {category} product lineup specifications 2026" if category else f"{vendor} product specifications datasheet")
        if base_name and len(base_name) > 2:
            wider_queries.append(f"{base_name} sensor IMU accelerometer gyroscope motorcycle helmet wearable specifications")
            wider_queries.append(f"{vendor} {base_name} connector FPC cable assembly smart helmet specs" if vendor else f"{base_name} specifications datasheet PDF")

        for wq in wider_queries[:2]:
            try:
                result = registry.call("deep_research", wq)
                if result.get("success") and len(result.get("data", "")) > 200:
                    search_data += f"\n---\n{result['data'][:3000]}"
                    print(f"    [加宽搜索] {chip}: {wq[:50]}... -> +{len(result['data'])}字")
                    if len(search_data) > 500:
                        break
            except Exception:
                continue

    return {"chip": chip, "vendor": vendor, "search_data": search_data, "success": len(search_data) > 300}


# ==========================================
# 分批执行配置
# ==========================================
BATCH_SIZE = 10
BATCH_FILE = Path(__file__).parent.parent / ".ai-state" / "kg_progress.json"


def _load_progress(domain_key: str) -> int:
    """加载上次执行到第几个节点"""
    if not BATCH_FILE.exists():
        return 0
    try:
        data = json.loads(BATCH_FILE.read_text(encoding="utf-8"))
        return data.get(domain_key, 0)
    except:
        return 0


def _save_progress(domain_key: str, index: int):
    """保存当前进度"""
    BATCH_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = {}
    if BATCH_FILE.exists():
        try:
            data = json.loads(BATCH_FILE.read_text(encoding="utf-8"))
        except:
            pass
    data[domain_key] = index
    BATCH_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def get_remaining_count() -> dict:
    """获取各领域剩余节点数"""
    remaining = {}
    if not BATCH_FILE.exists():
        return remaining
    try:
        data = json.loads(BATCH_FILE.read_text(encoding="utf-8"))
        # 返回未完成的领域及其剩余数
        for dk, idx in data.items():
            if idx > 0:
                remaining[dk] = idx
    except:
        pass
    return remaining

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


def auto_discover_domains() -> list:
    """
    自动发现需要深挖的领域，生成种子节点。
    不依赖硬编码——从知识库现状出发，让 LLM 判断哪里薄弱、该深挖什么。

    返回格式和 DOMAIN_SEEDS 中的条目一致，可以直接传给 expand_one_domain。
    """
    gateway = get_model_gateway()

    # Step 1: 收集知识库现状
    stats = get_knowledge_stats()
    total = sum(stats.values())

    # 维度覆盖统计
    dimension_counts = {}
    target_dimensions = {
        "HUD/AR显示": ["HUD", "AR", "光机", "光波导", "Micro OLED", "近眼显示", "waveguide"],
        "4K摄像": ["4K", "摄像", "IMX", "EIS", "防抖", "行车记录", "camera"],
        "ANC/ENC降噪": ["ANC", "ENC", "降噪", "风噪", "通话", "麦克风", "noise cancellation"],
        "ADAS安全": ["ADAS", "盲区", "碰撞预警", "前向预警", "雷达", "AEB", "APA", "BSD", "毫米波", "USS", "主动安全"],
        "SoC/芯片": ["AR1", "BES2800", "高通", "恒玄", "SoC", "芯片", "Nordic", "QCC", "J6", "Orin"],
        "认证标准": ["ECE", "DOT", "3C", "FCC", "CE RED", "UN38.3", "GB 811", "FMVSS", "ENCAP"],
        "供应商/JDM": ["歌尔", "Goertek", "JDM", "ODM", "供应商", "代工", "立讯"],
        "Mesh对讲": ["Mesh", "对讲", "自组网", "Sena", "Cardo", "intercom"],
        "电池/散热": ["电池", "散热", "热管理", "温控", "mAh", "充电", "BMS", "锂聚合物"],
        "结构/材料": ["碳纤维", "玻纤", "EPS", "壳体", "模具", "MIPS", "carbon fiber", "重量"],
        "连接器/接口": ["连接器", "FAKRA", "USB-C", "Type-C", "FPC", "天线", "RF"],
        "传感器/IMU": ["IMU", "加速度计", "陀螺仪", "气压计", "GPS", "GNSS", "跌倒检测"],
    }

    for dim_name, keywords in target_dimensions.items():
        count = 0
        for f in KB_ROOT.rglob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                text = (data.get("title", "") + " " + data.get("content", "")[:200]).lower()
                if any(kw.lower() in text for kw in keywords):
                    count += 1
            except:
                continue
        dimension_counts[dim_name] = count

    # 按覆盖量排序，找最薄弱的方向
    sorted_dims = sorted(dimension_counts.items(), key=lambda x: x[1])

    # 收集已有的技术档案标题（避免重复深挖）
    existing_profiles = set()
    for f in KB_ROOT.rglob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if "knowledge_graph" in data.get("tags", []) or "tech_profile" in data.get("tags", []):
                existing_profiles.add(data.get("title", "")[:40].lower())
        except:
            continue

    # Step 2: 让 LLM 基于薄弱方向生成深挖计划
    weak_report = "\n".join([f"  {d}: {c}条" for d, c in sorted_dims])
    existing_report = "\n".join(list(existing_profiles)[:30]) if existing_profiles else "暂无"

    plan_prompt = (
        f"你是智能摩托车全盔项目的知识管理专家。\n\n"
        f"## 知识库总量: {total} 条\n\n"
        f"## 各维度覆盖（从少到多排列）:\n{weak_report}\n\n"
        f"## 已有技术档案（不要重复这些）:\n{existing_report}\n\n"
        f"## 你的任务\n"
        f"从最薄弱的 2-3 个维度出发，为每个维度设计一个'知识图谱深挖计划'。\n\n"
        f"每个计划需要：\n"
        f"1. 明确的领域名称\n"
        f"2. 3-5 个种子节点（具体的产品/技术/标准名称，不要泛泛的关键词）\n"
        f"3. 让 LLM 发现更多节点的扩展提示词\n"
        f"4. 针对每个节点的深搜模板（中英文各 2 条）\n"
        f"5. 技术档案的输出模板（该领域特有的字段）\n\n"
        f"## 约束\n"
        f"- 必须围绕摩托车智能全盔\n"
        f"- 种子节点必须具体到型号/标准号/公司名\n"
        f"- 避免和已有技术档案重复\n"
        f"- 选择的维度应该是对产品决策最有影响的\n"
        f"- 种子节点必须是搜索引擎能搜到详细信息的（主流品牌的主流型号），不要选太冷门的型号\n"
        f"- 每个种子的格式必须是'品牌 型号'（如 'Bosch BMI323'），不要只写型号不写品牌\n\n"
        f"输出 JSON 数组，每个元素格式：\n"
        f'{{"domain_key": "英文标识(如 battery_bms)", '
        f'"name": "中文名称(如 电池与BMS方案)", '
        f'"seeds": ["种子1", "种子2", "种子3"], '
        f'"expansion_prompt": "让LLM发现更多节点的提示词...", '
        f'"deep_search_template": ["搜索模板1 {{chip}} {{vendor}}", "搜索模板2"], '
        f'"knowledge_template": "技术档案输出模板..."}}'
    )

    result = gateway.call_azure_openai("cpo", plan_prompt,
        "你是知识管理专家。只输出 JSON 数组。", "auto_discover_domains")

    if not result.get("success"):
        print("[AutoDiscover] LLM 调用失败，降级到硬编码种子")
        return []

    try:
        resp = result["response"].strip()
        resp = re.sub(r'^```json\s*', '', resp)
        resp = re.sub(r'\s*```$', '', resp)
        domains = json.loads(resp)

        if not isinstance(domains, list):
            return []

        # 转换为 expand_one_domain 能接受的格式
        valid_domains = []
        for d in domains[:3]:  # 每晚最多 3 个领域
            domain_key = d.get("domain_key", "")
            if not domain_key:
                continue

            # 确保必要字段存在
            domain_config = {
                "name": d.get("name", domain_key),
                "seeds": d.get("seeds", [])[:5],
                "expansion_prompt": d.get("expansion_prompt",
                    f"列出与以下已知节点同家族或竞品的其他选项：{{known_list}}\n只输出 JSON 数组。最多 15 个。"),
                "deep_search_template": d.get("deep_search_template", [
                    "{chip} datasheet specifications 2026",
                    "{chip} {vendor} features comparison",
                    "{chip} 参数 规格 价格 对比",
                    "{chip} smart motorcycle helmet application",
                ]),
                "knowledge_template": d.get("knowledge_template",
                    "请基于以下搜索结果，输出关于 {chip} 的完整技术档案。\n"
                    "必须包含具体参数、价格、适用场景、对摩托车全盔的适配度。\n\n"
                    "搜索结果：\n{search_data}"),
            }

            valid_domains.append({"key": domain_key, "config": domain_config})
            print(f"[AutoDiscover] 发现深挖方向: {domain_config['name']} ({len(domain_config['seeds'])} 个种子)")

        return valid_domains

    except Exception as e:
        print(f"[AutoDiscover] 解析失败: {e}")
        return []


def run_autonomous_deep_dive(progress_callback=None) -> str:
    """
    自主深挖：系统自动判断今晚该深挖什么领域，自动生成种子，自动执行。
    每晚由夜间学习调用，无需人工指定方向。
    """
    print(f"\n{'='*60}")
    print(f"[AutoDeepDive] 自主深挖启动 ({datetime.now().strftime('%H:%M')})")
    print(f"{'='*60}")

    report_lines = ["[AutoDeepDive] 自主深挖报告"]

    # Step 1: 检查是否有未完成的深挖任务（断点续传）
    progress_file = Path(__file__).parent.parent / ".ai-state" / "kg_progress.json"
    pending = {}
    has_pending = False
    if progress_file.exists():
        try:
            progress = json.loads(progress_file.read_text(encoding="utf-8"))
            # 检查是否有未完成的领域（进度值 > 0 且 < 总数）
            for key, idx in progress.items():
                if isinstance(idx, int) and idx > 0:
                    # 检查对应的领域是否存在于 DOMAIN_SEEDS
                    if key in DOMAIN_SEEDS:
                        has_pending = True
                        pending[key] = idx
        except:
            pass

    # 读取动态种子（断点续传）
    seed_file = Path(__file__).parent.parent / ".ai-state" / "kg_dynamic_seeds.json"
    if seed_file.exists():
        try:
            saved_seeds = json.loads(seed_file.read_text(encoding="utf-8"))
            for key, info in saved_seeds.items():
                if info.get("status") == "in_progress":
                    config = info.get("config")
                    if config and key not in DOMAIN_SEEDS:
                        DOMAIN_SEEDS[key] = config
                        print(f"[AutoDeepDive] 恢复动态种子: {config.get('name', key)}")
                        # 添加到 pending 以便续传
                        pending[key] = info.get("progress", 0)
                        has_pending = True
        except:
            pass

    if has_pending:
        # 续传未完成的任务
        report_lines.append(f"\n📋 发现 {len(pending)} 个未完成的深挖任务，优先续传")
        for key, idx in pending.items():
            if key in DOMAIN_SEEDS:
                report = expand_one_domain(key, progress_callback)
                report_lines.append(report)
    else:
        # Step 2: 自动发现今晚该深挖什么
        discovered = auto_discover_domains()

        if not discovered:
            # 降级：用硬编码种子中尚未完成的
            report_lines.append("  LLM 未能生成新方向，检查硬编码种子中未完成的领域")
            for key in DOMAIN_SEEDS:
                prog = _load_progress(key)
                if prog == 0:  # 还没开始的
                    report = expand_one_domain(key, progress_callback)
                    report_lines.append(report)
                    break  # 每晚只做一个
        else:
            report_lines.append(f"\n🔍 今晚深挖 {len(discovered)} 个方向:")

            for item in discovered:
                key = item["key"]
                config = item["config"]

                report_lines.append(f"\n  📊 {config['name']}")
                report_lines.append(f"  种子: {', '.join(config['seeds'][:3])}...")

                # 保存动态种子（断点续传用）
                seed_file = Path(__file__).parent.parent / ".ai-state" / "kg_dynamic_seeds.json"
                existing_seeds = {}
                if seed_file.exists():
                    try:
                        existing_seeds = json.loads(seed_file.read_text(encoding="utf-8"))
                    except:
                        pass
                existing_seeds[key] = {
                    "config": config,
                    "discovered_at": datetime.now().isoformat(),
                    "status": "in_progress"
                }
                seed_file.write_text(json.dumps(existing_seeds, ensure_ascii=False, indent=2), encoding="utf-8")

                # 动态注册
                DOMAIN_SEEDS[key] = config

                # 执行
                report = expand_one_domain(key, progress_callback)
                report_lines.append(report)

    report = "\n".join(report_lines)
    print(report)
    return report


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

    # Step 2: 对每个节点深搜（分批执行）
    new_knowledge = 0

    # 加载进度
    start_idx = _load_progress(domain_key)

    # 如果进度是 0，说明是新的一轮或已完成，需要发现节点
    # 如果进度 > 0，说明是继续上次未完成的

    if start_idx == 0:
        # 新的一轮，保存所有节点数量作为进度标记
        _save_progress(domain_key, 0)

    end_idx = min(start_idx + BATCH_SIZE, len(all_chips))
    batch = all_chips[start_idx:end_idx]

    print(f"[KG Expand] 本批: {start_idx+1}-{end_idx}/{len(all_chips)}（每批 {BATCH_SIZE} 个）")
    report_lines.append(f"  本批: {start_idx+1}-{end_idx}/{len(all_chips)} 节点")

    # Step 2: 并行搜索（动态并行度 Phase 2.4）
    workers = _get_optimal_workers()
    print(f"[KG Expand] 本批 {len(batch)} 个节点，{workers} 并行 (CPU:{psutil.cpu_percent()}%, MEM:{psutil.virtual_memory().percent}%)")

    # === 心跳初始化 ===
    hb = ProgressHeartbeat(
        f"KG扩展:{domain_key}",
        total=len(batch),
        feishu_callback=progress_callback,
        log_interval=5,
        feishu_interval=10,
        feishu_time_interval=180
    )

    # 阶段 A：并行搜索所有芯片
    search_results = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_search_one_chip, chip_info, domain, registry): chip_info
            for chip_info in batch
        }
        for future in as_completed(futures):
            chip_info = futures[future]
            try:
                result = future.result()
                search_results.append(result)
                chip = result.get("chip", "?")
                if result["success"]:
                    print(f"  ✅ 搜索完成: {chip} ({len(result['search_data'])}字)")
                else:
                    print(f"  ⏭️ 搜索不足: {chip}")
            except Exception as e:
                print(f"  ❌ 搜索异常: {chip_info.get('chip', '?')}: {e}")
                search_results.append({"chip": chip_info.get("chip", ""), "vendor": chip_info.get("vendor", ""), "search_data": "", "success": False})

            # 并行搜索时也尊重 P0 优先级
            from src.utils.task_priority import get_priority_manager
            get_priority_manager().wait_if_p0_active(timeout=30)

    # 阶段 B：串行提炼（提炼需要深度推理，用 GPT-5.4，不适合太高并发）
    for result in search_results:
        chip = result.get("chip", "")
        vendor = result.get("vendor", "")
        search_data = result.get("search_data", "")

        if not result["success"] or not search_data:
            report_lines.append(f"  ⏭️ {chip} — 搜索结果不足")
            hb.tick(detail=f"跳过: {chip}", success=False)
            continue

        knowledge_prompt = domain["knowledge_template"].format(
            chip=chip, search_data=search_data[:8000]
        )

        # === Phase 2.3: 提炼用 GPT-5.4 ===
        refine_result = call_for_refine(knowledge_prompt, f"你是{name}专家，输出完整技术档案。", "kg_refine")

        if refine_result.get("success") and len(refine_result.get("response", "")) > 300:
            content = refine_result["response"]
            add_knowledge(
                title=f"[技术档案] {chip} ({vendor})" if vendor else f"[技术档案] {chip}",
                domain="components",
                content=content[:1500],
                tags=["knowledge_graph", "tech_profile", domain_key, vendor.lower()] if vendor else ["knowledge_graph", "tech_profile", domain_key],
                source=f"kg_expand:{domain_key}",
                confidence="high",
                caller="auto"
            )
            new_knowledge += 1
            report_lines.append(f"  ✅ {chip} ({len(content)}字)")
            hb.tick(detail=chip, success=True)
        else:
            # 打印详细失败原因
            error = refine_result.get("error", "未知")
            resp_len = len(refine_result.get("response", ""))
            print(f"  [KG] 提炼失败详情: success={refine_result.get('success')}, resp_len={resp_len}, error={error[:200] if error else '无'}")

            # 如果是返回了内容但太短（<300字），降低门槛存入，标记为浅条目
            if refine_result.get("success") and resp_len > 100:
                content = refine_result["response"]
                add_knowledge(
                    title=f"[浅档案] {chip} ({vendor})" if vendor else f"[浅档案] {chip}",
                    domain="components",
                    content=content[:800],
                    tags=["knowledge_graph", "tech_profile", "shallow", domain_key],
                    source=f"kg_expand:{domain_key}",
                    confidence="medium",
                    caller="auto"
                )
                new_knowledge += 1
                report_lines.append(f"  ⚠️ {chip} ({resp_len}字, 浅档案)")
                hb.tick(detail=f"{chip} (浅)", success=True)
            elif search_data:
                # 有搜索结果但提炼失败，重试一次用更简单的 prompt
                retry_prompt = (
                    f"请简要描述 {chip} 的基本信息：是什么、谁生产的、主要参数、适用场景。\n"
                    f"如果你不确定，就说不确定。200-500字即可。\n\n"
                    f"参考资料：\n{search_data[:3000]}"
                )
                retry = call_for_refine(retry_prompt, "简要描述即可。", "kg_retry")
                if retry.get("success") and len(retry.get("response", "")) > 100:
                    add_knowledge(
                        title=f"[浅档案] {chip}",
                        domain="components",
                        content=retry["response"][:800],
                        tags=["knowledge_graph", "shallow", domain_key],
                        source=f"kg_expand:{domain_key}",
                        confidence="low",
                        caller="auto"
                    )
                    new_knowledge += 1
                    report_lines.append(f"  ⚠️ {chip} (重试成功, 浅档案)")
                else:
                    retry_error = retry.get("error", "未知")
                    report_lines.append(f"  ❌ {chip} — 提炼失败: {retry_error[:80] if retry_error else '响应太短'}")
            else:
                report_lines.append(f"  ❌ {chip} — 无搜索数据, 跳过")

    # 保存进度
    _save_progress(domain_key, end_idx)

    # 完成推送：无论白天夜间都推送一次总结
    if progress_callback:
        is_complete = end_idx >= len(all_chips)
        summary_msg = (
            f"✅ [{name}] 知识图谱扩展{'本批' if not is_complete else '全部'}完成\n"
            f"节点: {start_idx+1}-{end_idx}/{len(all_chips)}\n"
            f"新增: {new_knowledge} 条技术档案"
        )
        if not is_complete:
            summary_msg += f"\n⏳ 剩余 {len(all_chips)-end_idx} 个节点待下批处理"
        progress_callback(summary_msg)

    # 检查是否全部完成
    if end_idx < len(all_chips):
        remaining = len(all_chips) - end_idx
        report_lines.append(f"\n  本批完成，剩余 {remaining} 个节点，下次继续")
        hb.finish(f"本批新增 {new_knowledge} 条")
        report = "\n".join(report_lines)
        print(f"\n{report}")
        return report

    # 全部完成，清除进度
    _save_progress(domain_key, 0)
    hb.finish(f"全部完成，新增 {new_knowledge} 条")

    # Step 3: 生成领域决策树（全部完成后）
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

        # === Phase 2.3: 决策树用 GPT-5.4 ===
        tree_result = call_for_refine(decision_prompt, "你是技术总监，生成选型决策树。", "kg_decision_tree")

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

    # 任务完成提示音
    from src.utils.notifier import notify
    notify("success")

    return "\n\n".join(reports)


if __name__ == "__main__":
    expand_all_domains()