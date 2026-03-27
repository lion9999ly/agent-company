# Agent 认知深化 — 知识图谱 + 决策树 + 自完整性检测

> 生成时间: 2026-03-25
> 核心目标: Agent 从"搜索整合"进化到"专业判断"
> 执行顺序: Task 1 → 2 → 3 → 4

---

## Task 1: 芯片领域知识图谱深挖（今晚自动执行）

**目标**: 把 AR/XR 可穿戴芯片的完整产品线全部搜到 datasheet 级深度。不是搜一个芯片，是搜整个产品家族。

### 1.1 创建 scripts/knowledge_graph_expander.py

```python
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
# 知识图谱扩展：种子节点 → 发现关联节点 → 逐个深挖
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
        progress_callback(f"🔬 知识图谱扩展: {name}...")
    
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
            progress_callback(f"  🔍 [{name}] {i}/{len(all_chips)}: {chip[:20]}...")
        
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
            report_lines.append(f"  ⏭️ {chip} — 搜索结果不足")
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
            report_lines.append(f"  ✅ {chip} ({len(content)}字)")
        else:
            report_lines.append(f"  ❌ {chip} — 提炼失败")
        
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
            f"   - 如果只需要 HUD+语音+蓝牙 → 推荐 XX，因为 YY\n"
            f"   - 如果需要 HUD+4K+ADAS → 推荐 XX，因为 YY\n"
            f"   - 如果需要全功能（HUD+4K+ADAS+AI） → 推荐 XX，但要注意 ZZ\n"
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
            report_lines.append(f"\n  📊 决策树生成完成 ({len(tree_result['response'])}字)")
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
```

### 1.2 注册飞书指令

在 feishu_sdk_client.py 中添加：

```python
elif text.strip() in ("知识图谱", "kg expand", "深挖芯片"):
    send_reply(open_id, "🔬 开始知识图谱扩展（AR/XR SoC + 音频 SoC + HUD 光学），预计 30-60 分钟...")
    import threading
    def _kg():
        try:
            from scripts.knowledge_graph_expander import expand_all_domains
            report = expand_all_domains(progress_callback=lambda msg: send_reply(open_id, msg))
            send_reply(open_id, report[:4000])
        except Exception as e:
            send_reply(open_id, f"❌ 知识图谱扩展失败: {e}")
    threading.Thread(target=_kg, daemon=True).start()
```

### 1.3 嵌入夜间自动执行

在 daily_learning.py 的 `run_night_deep_learning` 末尾，自主研究之后添加：

```python
    # === 知识图谱扩展（每周一次，周日夜间） ===
    if datetime.now().weekday() == 6:  # 周日
        KG_FLAG = Path(__file__).parent.parent / ".ai-state" / f"kg_expand_{datetime.now().strftime('%Y%m%d')}.flag"
        if not KG_FLAG.exists():
            try:
                print("[KG Expand] 周日夜间，自动执行知识图谱扩展")
                from scripts.knowledge_graph_expander import expand_all_domains
                kg_report = expand_all_domains(progress_callback=progress_callback)
                KG_FLAG.write_text(datetime.now().isoformat(), encoding="utf-8")
                report += f"\n\n{kg_report}"
                if progress_callback:
                    progress_callback(f"📊 知识图谱扩展完成")
            except Exception as e:
                print(f"[KG Expand] 失败: {e}")
```

### 验证

```bash
python -c "
from scripts.knowledge_graph_expander import DOMAIN_SEEDS, expand_one_domain
print(f'领域种子: {len(DOMAIN_SEEDS)} 个')
for key, domain in DOMAIN_SEEDS.items():
    print(f'  {key}: {domain[\"name\"]}, {len(domain[\"seeds\"])} 个种子')
print('✅ Task 1 完成')
"
```

---

## Task 2: 知识自完整性检测（Agent 主动发现知识缺口）

**目标**: 系统自动检测"我知道 AR1 但不知道 AR1+/AR2"这种家族性缺口，主动触发深挖。不需要用户指出。

### 2.1 创建 scripts/knowledge_completeness_checker.py

```python
"""
@description: 知识自完整性检测 - 自动发现和填补知识家族缺口
@dependencies: src.utils.model_gateway, src.tools.knowledge_base
@last_modified: 2026-03-25
"""
import json
import re
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.model_gateway import get_model_gateway
from src.tools.knowledge_base import search_knowledge, get_knowledge_stats, KB_ROOT


def detect_gaps() -> list:
    """扫描知识库，检测家族性缺口"""
    gateway = get_model_gateway()
    
    # 收集知识库中提到的所有"系列型号"模式
    all_titles = []
    all_content_snippets = []
    
    for f in KB_ROOT.rglob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            title = data.get("title", "")
            content = data.get("content", "")[:300]
            all_titles.append(title)
            all_content_snippets.append(f"{title}: {content[:200]}")
        except:
            continue
    
    # 让 LLM 分析知识库中的"家族缺口"
    sample = "\n".join(all_content_snippets[:100])  # 采样前 100 条
    
    gap_prompt = (
        f"你是智能摩托车全盔项目的知识管理专家。\n\n"
        f"以下是我们知识库中 {len(all_titles)} 条知识的采样（前 100 条标题和摘要）。\n\n"
        f"请分析知识库中的'家族性缺口'——即我们知道某个产品/技术的一个型号，但不知道同系列的其他型号。\n\n"
        f"例如：\n"
        f"- 我们知道 AR1 Gen1 但不知道 AR1+、AR2（高通 AR 芯片家族缺口）\n"
        f"- 我们知道 BES2800 但不知道 BES2700/2600/2900（恒玄芯片家族缺口）\n"
        f"- 我们知道 Sena Packtalk 但不知道 Sena 50S/50R/Spider（Sena 产品线缺口）\n"
        f"- 我们知道 ECE 22.06 但不知道它和 ECE 22.05 的具体差异（标准版本缺口）\n\n"
        f"请找出 5-8 个最重要的家族缺口。\n\n"
        f"输出 JSON 数组：\n"
        f'[{{"known": "我们已知的型号/产品", "missing": ["缺失的型号1", "缺失的型号2"], '
        f'"domain": "components/competitors/standards", '
        f'"priority": "high/medium", '
        f'"reason": "为什么这个缺口重要"}}]\n\n'
        f"知识库采样：\n{sample}"
    )
    
    result = gateway.call_azure_openai("cpo", gap_prompt, "只输出 JSON 数组。", "completeness_check")
    
    if not result.get("success"):
        return []
    
    try:
        resp = result["response"].strip()
        resp = re.sub(r'^```json\s*', '', resp)
        resp = re.sub(r'\s*```$', '', resp)
        gaps = json.loads(resp)
        if isinstance(gaps, list):
            print(f"[Completeness] 发现 {len(gaps)} 个家族缺口")
            for gap in gaps:
                print(f"  - 已知 {gap.get('known', '?')}, 缺失 {gap.get('missing', [])}")
            return gaps
    except:
        pass
    
    return []


def fill_gap(gap: dict, progress_callback=None) -> str:
    """填补一个家族缺口"""
    from src.tools.tool_registry import get_tool_registry
    from src.tools.knowledge_base import add_knowledge
    
    gateway = get_model_gateway()
    registry = get_tool_registry()
    
    known = gap.get("known", "")
    missing = gap.get("missing", [])
    domain = gap.get("domain", "components")
    
    filled = 0
    for item in missing:
        # 搜索
        queries = [
            f"{item} datasheet specifications features 2026",
            f"{item} 参数 规格 价格 对比 {known}",
        ]
        
        search_data = ""
        for q in queries:
            result = registry.call("deep_research", q)
            if result.get("success") and len(result.get("data", "")) > 200:
                search_data += f"\n{result['data'][:3000]}"
        
        if len(search_data) < 300:
            continue
        
        # 提炼
        refine_prompt = (
            f"请输出关于 {item} 的技术档案。\n"
            f"重点和已知的 {known} 做对比：哪些方面更好、哪些更差、适用场景有何不同。\n"
            f"必须包含具体参数、价格、已知客户。\n\n"
            f"搜索结果：\n{search_data[:6000]}"
        )
        
        refine_result = gateway.call_azure_openai("cpo", refine_prompt,
            "输出完整技术档案。", "gap_fill")
        
        if refine_result.get("success") and len(refine_result["response"]) > 200:
            add_knowledge(
                title=f"[技术档案] {item}（对比 {known}）",
                domain=domain,
                content=refine_result["response"][:1200],
                tags=["knowledge_graph", "gap_fill", "auto_completeness"],
                source="completeness_check",
                confidence="high"
            )
            filled += 1
            print(f"  ✅ 填补: {item}")
        
        import time
        time.sleep(2)
    
    return f"已知 {known} → 填补 {filled}/{len(missing)} 个缺失"


def run_completeness_check(progress_callback=None) -> str:
    """完整性检测 + 自动填补"""
    print("\n[Completeness] 开始知识自完整性检测...")
    
    gaps = detect_gaps()
    if not gaps:
        return "[Completeness] 未发现明显家族缺口"
    
    # 按优先级排序
    gaps.sort(key=lambda x: 0 if x.get("priority") == "high" else 1)
    
    report_lines = [f"[Completeness] 发现 {len(gaps)} 个缺口，开始填补"]
    
    for i, gap in enumerate(gaps[:5], 1):  # 每次最多填 5 个
        if progress_callback:
            progress_callback(f"🔍 填补缺口 [{i}/{min(len(gaps), 5)}]: {gap.get('known', '?')}")
        
        result = fill_gap(gap, progress_callback)
        report_lines.append(f"  {result}")
    
    report = "\n".join(report_lines)
    print(report)
    return report


if __name__ == "__main__":
    run_completeness_check()
```

### 2.2 嵌入夜间自动执行（每 3 天一次）

在 daily_learning.py 的 `run_night_deep_learning` 末尾添加：

```python
    # === 知识自完整性检测（每 3 天一次） ===
    COMPLETENESS_FLAG = Path(__file__).parent.parent / ".ai-state" / f"completeness_{datetime.now().strftime('%Y%m%d')}.flag"
    day_of_year = datetime.now().timetuple().tm_yday
    if day_of_year % 3 == 0 and not COMPLETENESS_FLAG.exists():
        try:
            print("[Completeness] 触发自完整性检测")
            from scripts.knowledge_completeness_checker import run_completeness_check
            comp_report = run_completeness_check(progress_callback=progress_callback)
            COMPLETENESS_FLAG.write_text(datetime.now().isoformat(), encoding="utf-8")
            report += f"\n\n{comp_report}"
            if progress_callback:
                progress_callback(comp_report[:500])
        except Exception as e:
            import traceback
            print(f"[Completeness] 失败: {e}")
            print(traceback.format_exc())
```

### 2.3 飞书指令

```python
elif text.strip() in ("完整性检测", "completeness", "缺口检测"):
    send_reply(open_id, "🔍 开始知识自完整性检测，寻找家族性缺口...")
    import threading
    def _check():
        try:
            from scripts.knowledge_completeness_checker import run_completeness_check
            report = run_completeness_check(progress_callback=lambda msg: send_reply(open_id, msg))
            send_reply(open_id, report[:4000])
        except Exception as e:
            send_reply(open_id, f"❌ 完整性检测失败: {e}")
    threading.Thread(target=_check, daemon=True).start()
```

### 验证

```bash
python -c "
from scripts.knowledge_completeness_checker import detect_gaps
print('detect_gaps 可导入')
print('✅ Task 2 完成')
"
```

---

## Task 3: 决策树知识自动生成

**目标**: 每次知识图谱扩展后，自动生成"选型决策树"型知识。已在 Task 1 的 expand_one_domain 末尾实现（Step 3: 生成领域决策树）。

此 Task 已合并到 Task 1 中。无需额外改动。

但需要确保 CPO 规划时能读到决策树知识。在 router.py 的 `_search_knowledge_for_task` 中，决策树型知识应该获得更高权重。

在 router.py 的 `_search_knowledge_for_task` 函数中，内部文档优先级逻辑旁边，添加决策树优先级：

```python
                # 决策树型知识加权
                is_decision_tree = "decision_tree" in tags or "knowledge_graph" in tags
                
                if is_internal:
                    score += 20
                elif is_decision_tree:
                    score += 10  # 决策树次于内部文档，但高于普通条目
```

### 验证

```bash
python -c "
from src.graph.router import _search_knowledge_for_task
result = _search_knowledge_for_task('芯片选型 SoC AR1')
print(f'检索结果: {len(result)} 字')
print('✅ Task 3 完成')
"
```

---

## Task 4: 今晚立即执行芯片领域深挖

### 4.1 手动触发（不等周日）

让系统今晚就跑一次知识图谱扩展。在飞书发"知识图谱"或"深挖芯片"。

或者直接命令行跑：

```bash
python -c "
import sys; sys.path.insert(0, '.')
from scripts.knowledge_graph_expander import expand_one_domain
# 先跑最重要的：AR/XR SoC
report = expand_one_domain('ar_xr_soc', progress_callback=lambda msg: print(msg))
print(report)
"
```

预计耗时 30-60 分钟，会搜索 15-25 个芯片的完整技术档案并生成决策树。

---

## 执行完成后的检查清单

```bash
# 1. 确认新文件可导入
python -c "from scripts.knowledge_graph_expander import expand_all_domains; print('KG OK')"
python -c "from scripts.knowledge_completeness_checker import run_completeness_check; print('Completeness OK')"

# 2. 确认飞书指令注册
python -c "from scripts.feishu_sdk_client import handle_message; print('Feishu OK')"

# 3. 确认路由器能读决策树知识
python -c "from src.graph.router import _search_knowledge_for_task; print('Router OK')"

# 4. 重启服务，然后飞书发"深挖芯片"触发第一次知识图谱扩展
```

---

## 待办事项（下一步）

| 优先级 | 事项 | 说明 |
|--------|------|------|
| P1 | Agent 质疑和反驳能力 | Critic 基于硬数据指出矛盾，不只是评分 |
| P1 | 更多领域的知识图谱种子 | 电池/BMS、传感器/IMU、连接器、材料、认证标准 |
| P2 | 知识条目之间的关联图 | "AR1 功耗大 → 影响散热 → 影响电池选型" 这种链式推理 |
| P2 | 决策树自动更新 | 新知识入库后，相关决策树自动刷新 |
| P3 | 知识可信度衰减 | 超过 6 个月的条目自动标记"可能过时" |

---

## 新增飞书指令

| 指令 | 功能 |
|------|------|
| 知识图谱 / kg expand / 深挖芯片 | 手动触发知识图谱扩展（所有领域） |
| 完整性检测 / completeness / 缺口检测 | 检测并自动填补家族性知识缺口 |
