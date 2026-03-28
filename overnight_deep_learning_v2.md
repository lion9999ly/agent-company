# 10 小时深度学习任务 — 项目知识盲区定向补全

> 生成时间: 2026-03-27 晚
> 预计运行: 10 小时
> 启动方式: python scripts/overnight_deep_learning_v2.py --all
> 推送策略: 每完成一个 Phase 推送一次飞书（共 8 次），不推中间进度

---

## 知识盲区分析

你的项目正在从"技术调研"进入"PRD 细化 + 供应商评估"阶段。知识库硬件芯片类已经很扎实（AR/XR SoC 68个、音频 47 个、传感器、连接器），但以下方向严重缺失：

| 盲区 | 当前状态 | 为什么重要 |
|------|---------|-----------|
| 软件架构参考 | 几乎为零 | 你刚做 PRD，需要知道同类产品的软件怎么设计的 |
| HUD/AR 交互设计 | 零 | 给 UIUX 公司之前自己得有设计语言参考 |
| 竞品 App 拆解 | 零 | Sena/Cardo/Forcite 的 App 长什么样、功能怎么分 |
| 量产认证细节 | 浅 | ECE 22.06 具体测试项、费用、周期、实验室选择 |
| 电池热管理 | 浅 | 3800-4200mAh 在全盔里的热设计是核心难题 |
| 语音交互方案 | 浅 | 100km/h 风噪下的唤醒/识别方案细节 |
| 供应链成本 | 几乎为零 | BOM 估算需要各模块真实价格区间 |
| 骑行场景用研 | 零 | 摩旅/通勤/团骑用户的真实需求和痛点 |

---

## 创建 scripts/overnight_deep_learning_v2.py

```python
"""
@description: 10小时定向深度学习 - 补全项目知识盲区
@dependencies: src.utils.model_gateway, src.tools.knowledge_base, src.tools.tool_registry
@last_modified: 2026-03-27
"""
import json
import re
import gc
import sys
import time
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from src.utils.model_gateway import get_model_gateway
from src.tools.knowledge_base import add_knowledge, add_report, get_knowledge_stats, KB_ROOT
from src.tools.tool_registry import get_tool_registry


def log(msg, notify_func=None):
    ts = datetime.now().strftime("%H:%M")
    full = f"[{ts}] {msg}"
    print(full)
    if notify_func:
        try:
            notify_func(full)
        except:
            pass


def phase_done(name, stats, notify_func=None):
    msg = (
        f"✅ {name}\n"
        f"搜索: {stats.get('searched', 0)} | 入库: {stats.get('added', 0)} | "
        f"跳过: {stats.get('skipped', 0)} | 耗时: {stats.get('minutes', 0):.0f}min"
    )
    print(f"\n{'='*50}\n{msg}\n{'='*50}")
    if notify_func:
        try:
            notify_func(msg)
        except:
            pass


def _search_and_refine(topic: dict, registry, gateway) -> dict:
    """搜索一个主题并提炼为知识条目"""
    title = topic["title"]
    searches = topic.get("searches", [])
    domain = topic.get("domain", "components")
    tags = topic.get("tags", [])
    refine_prompt = topic.get("refine_prompt", "")
    
    # 并行搜索
    search_data = ""
    def _do_search(query):
        result = registry.call("deep_research", query)
        if result.get("success") and len(result.get("data", "")) > 200:
            return result["data"][:4000]
        return ""
    
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(_do_search, q): q for q in searches[:4]}
        for future in as_completed(futures):
            data = future.result()
            if data:
                search_data += f"\n---\n{data}"
    
    if len(search_data) < 500:
        return {"success": False, "title": title, "reason": "搜索不足"}
    
    # 提炼
    if not refine_prompt:
        refine_prompt = (
            f"基于以下搜索结果，输出关于「{title}」的详细知识条目。\n"
            f"必须包含具体数据（型号、参数、价格、品牌名）。\n"
            f"如果搜不到具体数据，标注'未查到'，不要编造。\n"
            f"输出 600-1200 字。\n\n"
            f"搜索结果：\n{search_data[:8000]}"
        )
    else:
        refine_prompt = refine_prompt.format(search_data=search_data[:8000], title=title)
    
    result = gateway.call_azure_openai("cpo", refine_prompt,
        "输出详细知识条目，包含具体数据。", "deep_learn_refine")
    
    if result.get("success") and len(result.get("response", "")) > 300:
        # 推测性检测
        content = result["response"]
        speculative_signals = ["假想", "假设", "推测", "推演", "预计将", "可能采用"]
        is_spec = any(s in content for s in speculative_signals)
        
        final_tags = tags + (["speculative"] if is_spec else [])
        
        add_knowledge(
            title=title,
            domain=domain,
            content=content[:1500],
            tags=final_tags,
            source="overnight_deep_v2",
            confidence="low" if is_spec else "high"
        )
        return {"success": True, "title": title, "chars": len(content)}
    
    return {"success": False, "title": title, "reason": "提炼失败"}


def run_phase(phase_name: str, topics: list, notify_func=None) -> dict:
    """运行一个学习阶段"""
    start = time.time()
    log(f"{phase_name} 开始（{len(topics)} 个主题）", notify_func)
    
    registry = get_tool_registry()
    gateway = get_model_gateway()
    
    added = 0
    skipped = 0
    
    for i, topic in enumerate(topics, 1):
        result = _search_and_refine(topic, registry, gateway)
        if result["success"]:
            added += 1
            print(f"  ✅ [{i}/{len(topics)}] {result['title'][:40]} ({result.get('chars', 0)}字)")
        else:
            skipped += 1
            print(f"  ⏭️ [{i}/{len(topics)}] {result['title'][:40]} — {result.get('reason', '')}")
        
        time.sleep(2)  # 控制频率
        
        if i % 10 == 0:
            gc.collect()
    
    minutes = (time.time() - start) / 60
    stats = {"searched": len(topics), "added": added, "skipped": skipped, "minutes": minutes}
    phase_done(phase_name, stats, notify_func)
    gc.collect()
    return stats


# ==========================================
# Phase 1: 竞品 App 拆解（Sena/Cardo/Forcite/LIVALL）
# 预计 60 分钟
# ==========================================
PHASE1_TOPICS = [
    # Sena App 拆解
    {"title": "Sena Motorcycles App 功能架构与界面设计拆解", "domain": "competitors",
     "searches": ["Sena Motorcycles app features UI UX review 2025", "Sena app device pairing mesh intercom settings", "Sena app ride tracking group ride features review"],
     "tags": ["app_teardown", "competitor_app", "sena"]},
    {"title": "Sena App 设备管理与 OTA 升级体验", "domain": "competitors",
     "searches": ["Sena app firmware update OTA process", "Sena app device settings noise control", "Sena app bluetooth pairing troubleshooting"],
     "tags": ["app_teardown", "competitor_app", "sena"]},
    {"title": "Sena App 组队骑行与 Mesh 对讲交互设计", "domain": "competitors",
     "searches": ["Sena app group ride mesh intercom UI", "Sena Mesh 2.0 app setup ride management", "Sena app rider location sharing team ride"],
     "tags": ["app_teardown", "competitor_app", "sena"]},
    # Cardo App 拆解
    {"title": "Cardo Connect App 功能架构与界面设计拆解", "domain": "competitors",
     "searches": ["Cardo Connect app features UI review 2025", "Cardo app DMC settings ride features", "Cardo app natural voice control setup"],
     "tags": ["app_teardown", "competitor_app", "cardo"]},
    {"title": "Cardo App 自然语音与音频设置体验", "domain": "competitors",
     "searches": ["Cardo app natural voice commands setup", "Cardo app audio settings JBL equalizer", "Cardo app noise reduction wind settings"],
     "tags": ["app_teardown", "competitor_app", "cardo"]},
    # Forcite App 拆解
    {"title": "Forcite Ride App 功能架构与骑行记录", "domain": "competitors",
     "searches": ["Forcite Ride app features review 2025", "Forcite app helmet camera video management", "Forcite app ride tracking navigation HUD"],
     "tags": ["app_teardown", "competitor_app", "forcite"]},
    {"title": "Forcite App 视频管理与社交分享设计", "domain": "competitors",
     "searches": ["Forcite app video download share social", "Forcite MK1S app camera settings resolution", "Forcite app highlight reel editing"],
     "tags": ["app_teardown", "competitor_app", "forcite"]},
    # LIVALL App
    {"title": "LIVALL Riding App 功能架构与安全功能", "domain": "competitors",
     "searches": ["LIVALL Riding app features SOS fall detection 2025", "LIVALL app LED control group ride walkie talkie", "LIVALL app cycling helmet smart features review"],
     "tags": ["app_teardown", "competitor_app", "livall"]},
    # EyeRide App
    {"title": "EyeRide HUD App 导航与 HUD 设置体验", "domain": "competitors",
     "searches": ["EyeRide app HUD navigation setup review", "EyeRide app display settings brightness", "EyeRide motorcycle HUD app features limitations"],
     "tags": ["app_teardown", "competitor_app", "eyeride"]},
    # CrossHelmet App
    {"title": "CrossHelmet X1 App 功能与 360° 视觉体验", "domain": "competitors",
     "searches": ["CrossHelmet X1 app features review 2025", "CrossHelmet app rear view camera settings", "CrossHelmet app sound control noise cancellation"],
     "tags": ["app_teardown", "competitor_app", "crosshelmet"]},
]


# ==========================================
# Phase 2: HUD/AR 交互设计模式
# 预计 75 分钟
# ==========================================
PHASE2_TOPICS = [
    {"title": "摩托车 HUD 信息架构设计原则：骑行安全与信息密度平衡", "domain": "lessons",
     "searches": ["motorcycle HUD information architecture design principles", "rider distraction HUD display research safety", "heads-up display glance time cognitive load motorcycle"],
     "tags": ["hud_design", "ux_pattern"]},
    {"title": "汽车 HUD 交互设计迁移到摩托车的关键差异", "domain": "lessons",
     "searches": ["automotive HUD vs motorcycle HUD design differences", "car HUD interaction patterns motorcycle adaptation", "two-wheeler HUD unique constraints vibration single eye"],
     "tags": ["hud_design", "ux_pattern"]},
    {"title": "AR 眼镜 UI 设计模式：信息分层与注意力管理", "domain": "lessons",
     "searches": ["AR glasses UI design patterns information layering", "smart glasses notification priority system design", "AR wearable attention management UX research 2025"],
     "tags": ["hud_design", "ux_pattern"]},
    {"title": "骑行中语音交互设计：指令集定义与反馈策略", "domain": "lessons",
     "searches": ["motorcycle voice interaction design wind noise", "riding voice command set design helmet", "voice UI feedback strategy eyes-free interaction"],
     "tags": ["hud_design", "voice_ux"]},
    {"title": "骑行 HUD 夜间与强光模式设计：对比度与可读性", "domain": "lessons",
     "searches": ["motorcycle HUD night mode daylight readability design", "HUD contrast ratio direct sunlight tunnel transition", "heads-up display adaptive brightness riding"],
     "tags": ["hud_design", "ux_pattern"]},
    {"title": "HUD 告警优先级设计：安全>导航>通信>娱乐", "domain": "lessons",
     "searches": ["HUD alert priority system design safety first", "automotive ADAS warning priority DIN ISO standard", "motorcycle rider alert fatigue warning frequency"],
     "tags": ["hud_design", "ux_pattern"]},
    {"title": "实体按键盲操设计：手套操作与触觉反馈", "domain": "lessons",
     "searches": ["motorcycle helmet button blind operation glove design", "tactile feedback button design riding helmet", "Sena Cardo button layout motorcycle helmet ergonomics"],
     "tags": ["hud_design", "hardware_ux"]},
    {"title": "头盔氛围灯交互设计：状态指示与骑行安全信号", "domain": "lessons",
     "searches": ["motorcycle helmet LED light interaction design", "smart helmet ambient light status indication", "cycling helmet brake light turn signal LED pattern"],
     "tags": ["hud_design", "hardware_ux"]},
    {"title": "骑行 App 首次使用引导设计：配对→校准→权限→试骑", "domain": "lessons",
     "searches": ["smart device onboarding UX first time setup", "helmet app pairing setup wizard design", "IoT device activation first run experience best practice"],
     "tags": ["app_design", "ux_pattern"]},
    {"title": "运动穿戴 App 数据可视化设计模式", "domain": "lessons",
     "searches": ["sports wearable app data visualization design 2025", "cycling app ride data dashboard design patterns", "fitness tracker app UX data presentation best practice"],
     "tags": ["app_design", "ux_pattern"]},
    {"title": "骑行社区 App 设计参考：Strava/Relive/Rever 模式分析", "domain": "lessons",
     "searches": ["Strava cycling community features analysis", "Relive ride video sharing app features", "Rever motorcycle route planning community app review"],
     "tags": ["app_design", "community"]},
    {"title": "智能头盔 HUD 开机动画与品牌体验设计", "domain": "lessons",
     "searches": ["smart device boot animation brand experience design", "HUD startup sequence self-check animation", "consumer electronics premium unboxing first power on experience"],
     "tags": ["hud_design", "brand"]},
]


# ==========================================
# Phase 3: 量产认证深度细节
# 预计 75 分钟
# ==========================================
PHASE3_TOPICS = [
    {"title": "ECE 22.06 完整测试项清单：冲击/穿透/视野/附件/环境", "domain": "standards",
     "searches": ["ECE 22.06 complete test requirements list impact penetration", "ECE R22.06 test procedure helmet certification details", "UNECE R22.06 Annex testing accessories electronics"],
     "tags": ["certification", "ece"]},
    {"title": "ECE 22.06 认证费用、周期与实验室选择", "domain": "standards",
     "searches": ["ECE 22.06 certification cost timeline laboratory", "motorcycle helmet certification process Europe fee schedule", "ECE helmet testing laboratory TUV DEKRA UTAC"],
     "tags": ["certification", "ece"]},
    {"title": "ECE 22.06 对电子附件的具体要求：Annex 8 详解", "domain": "standards",
     "searches": ["ECE 22.06 Annex 8 accessories electronics helmet requirements", "ECE R22.06 electronic attachment protrusion test", "motorcycle helmet HUD camera bluetooth ECE approval"],
     "tags": ["certification", "ece"]},
    {"title": "DOT FMVSS 218 认证流程与自认证模式详解", "domain": "standards",
     "searches": ["DOT FMVSS 218 self-certification process motorcycle helmet", "DOT helmet certification cost timeline USA", "FMVSS 218 testing requirements impact retention peripheral vision"],
     "tags": ["certification", "dot"]},
    {"title": "中国 3C/GB 811-2022 电动自行车头盔认证与摩托车头盔差异", "domain": "standards",
     "searches": ["GB 811-2022 3C certification motorcycle helmet China", "China CCC motorcycle helmet testing requirements 2025", "GB 811 vs ECE 22.06 motorcycle helmet differences"],
     "tags": ["certification", "china"]},
    {"title": "FCC/CE-RED 智能头盔无线认证：BLE+WiFi+UWB 多射频共存", "domain": "standards",
     "searches": ["FCC Part 15 smart helmet Bluetooth WiFi certification", "CE RED directive smart wearable multiple radio certification", "EMC testing smart helmet motorcycle vibration"],
     "tags": ["certification", "wireless"]},
    {"title": "UN38.3 锂电池认证：头盔内置电池运输与安全测试", "domain": "standards",
     "searches": ["UN38.3 lithium battery testing smart helmet wearable", "UN38.3 certification cost timeline battery wearable", "lithium polymer battery safety testing helmet IEC 62133"],
     "tags": ["certification", "battery"]},
    {"title": "Snell M2020/FIM FRHPhe 认证对比与高端市场价值", "domain": "standards",
     "searches": ["Snell M2020 vs ECE 22.06 certification comparison", "FIM FRHPhe motorcycle helmet standard racing", "Snell certification process cost premium helmet"],
     "tags": ["certification", "premium"]},
    {"title": "多国认证并行策略：欧洲+美国+中国+东南亚同步送检方案", "domain": "standards",
     "searches": ["motorcycle helmet multi-country certification strategy", "parallel certification ECE DOT 3C motorcycle helmet", "helmet certification Southeast Asia Thailand Indonesia"],
     "tags": ["certification", "strategy"]},
    {"title": "智能头盔认证案例：Forcite/Sena/LIVALL 怎么通过的", "domain": "standards",
     "searches": ["Forcite MK1S certification ECE DOT approval", "Sena smart helmet FCC CE certification", "LIVALL smart helmet certification CE FCC details"],
     "tags": ["certification", "case_study"]},
]


# ==========================================
# Phase 4: 电池热管理与续航工程
# 预计 60 分钟
# ==========================================
PHASE4_TOPICS = [
    {"title": "全盔内 3500-4500mAh 锂电池热设计方案：石墨片/均热板/隔热", "domain": "components",
     "searches": ["motorcycle helmet lithium battery thermal design graphite", "smart helmet battery heat management wearable", "4000mAh wearable device thermal solution copper heat pipe"],
     "tags": ["thermal", "battery"]},
    {"title": "HUD 光机 + 摄像头 + BLE/WiFi 并发时的功耗热点分析", "domain": "components",
     "searches": ["smart glasses HUD thermal hotspot analysis", "AR device camera WiFi concurrent power heat", "wearable device multi-module thermal simulation"],
     "tags": ["thermal", "power"]},
    {"title": "头盔佩戴面（贴脸区域）温升控制：45°C 红线与用户感知", "domain": "components",
     "searches": ["wearable device skin contact temperature limit IEC", "helmet inner surface temperature comfort threshold", "smart device face contact thermal comfort 45C"],
     "tags": ["thermal", "comfort"]},
    {"title": "智能头盔功耗预算表：各模块典型功耗与场景组合", "domain": "components",
     "searches": ["smart helmet power budget HUD camera bluetooth audio", "AR glasses power consumption breakdown by module", "wearable device power budget template engineering"],
     "tags": ["power", "engineering"],
     "refine_prompt": (
         "基于搜索结果，输出一份智能摩托车全盔的功耗预算表。\n"
         "必须包含每个模块的典型功耗（mW）、峰值功耗、待机功耗。\n"
         "模块包括：SoC、HUD光机、摄像头(4K/1080P)、BLE、WiFi、音频(扬声器+麦克风)、"
         "ANC、IMU+传感器、LED灯、MCU。\n"
         "然后给出3个场景的总功耗估算：\n"
         "1. 通勤模式（HUD导航+蓝牙音乐+1080P循环录制）\n"
         "2. 摩旅模式（HUD导航+4K录制+语音+ANC）\n"
         "3. 待机模式（蓝牙保活+IMU+低功耗）\n"
         "基于4000mAh电池估算各场景续航。\n\n"
         "搜索结果：\n{search_data}"
     )},
    {"title": "电池热降级策略：温度触发码率降低/HUD 降亮/WiFi 关闭", "domain": "components",
     "searches": ["mobile device thermal throttling strategy camera", "wearable device thermal management software policy", "smart device overheat protection battery life HUD brightness"],
     "tags": ["thermal", "strategy"]},
    {"title": "快充方案选型：USB PD/QC 在头盔场景的安全约束", "domain": "components",
     "searches": ["smart helmet USB-C charging solution PD QC", "wearable device fast charging safety lithium polymer", "helmet charging port waterproof USB-C design"],
     "tags": ["battery", "charging"]},
    {"title": "电池寿命与循环：高温骑行场景下的加速老化模型", "domain": "components",
     "searches": ["lithium battery cycle life high temperature degradation model", "wearable device battery lifespan hot climate", "battery aging prediction smart helmet summer use"],
     "tags": ["battery", "lifecycle"]},
    {"title": "无线充电在头盔中的可行性：Qi2/磁吸方案评估", "domain": "components",
     "searches": ["Qi2 wireless charging helmet wearable integration 2025", "magnetic wireless charging smart helmet design", "wireless charging coil weight power efficiency wearable"],
     "tags": ["battery", "wireless_charging"]},
]


# ==========================================
# Phase 5: 语音交互与降噪工程
# 预计 60 分钟
# ==========================================
PHASE5_TOPICS = [
    {"title": "100km/h 风噪环境下的语音唤醒方案：麦克风阵列布局与算法", "domain": "components",
     "searches": ["motorcycle helmet microphone array wind noise voice wake", "high speed wind noise voice recognition helmet solution", "MEMS microphone placement motorcycle helmet speech enhancement"],
     "tags": ["voice", "microphone"]},
    {"title": "本地语音 vs 云端语音：头盔场景延迟与可用性权衡", "domain": "components",
     "searches": ["on-device voice recognition vs cloud latency comparison", "offline voice assistant wearable helmet 2025", "edge AI voice processing low power wearable"],
     "tags": ["voice", "architecture"]},
    {"title": "语音 SDK 选型：讯飞/思必驰/云知声/Picovoice 对比", "domain": "components",
     "searches": ["Chinese voice SDK comparison iFlytek AISpeech Unisound 2025", "Picovoice Porcupine wake word motorcycle noise", "voice recognition SDK motorcycle helmet wind noise benchmark"],
     "tags": ["voice", "sdk"]},
    {"title": "ANC 降噪方案在全盔中的挑战：密封性/反馈/头型适配", "domain": "components",
     "searches": ["ANC active noise cancellation motorcycle helmet challenges", "motorcycle helmet ANC seal feedback microphone placement", "full face helmet ANC vs passive noise reduction"],
     "tags": ["audio", "anc"]},
    {"title": "骨传导扬声器在头盔中的应用评估", "domain": "components",
     "searches": ["bone conduction speaker motorcycle helmet integration 2025", "bone conduction vs traditional speaker helmet audio quality", "Merry Electronics bone conduction helmet actuator"],
     "tags": ["audio", "bone_conduction"]},
    {"title": "头盔通话音质评估方法：POLQA/PESQ/主观 MOS 测试", "domain": "standards",
     "searches": ["voice call quality assessment POLQA PESQ motorcycle", "speech quality MOS testing wearable device helmet", "voice quality benchmark standard ISO 3382 helmet"],
     "tags": ["voice", "testing"]},
    {"title": "多语言语音识别在头盔中的支持策略", "domain": "components",
     "searches": ["multilingual voice recognition wearable device strategy", "Chinese English voice command helmet international market", "voice assistant language switching IoT device"],
     "tags": ["voice", "multilingual"]},
    {"title": "语音指令集设计：高频 20 条 + 扩展 50 条定义", "domain": "lessons",
     "searches": ["voice command set design smart helmet motorcycle", "voice UI command taxonomy wearable device", "motorcycle rider voice interaction use cases priority"],
     "tags": ["voice", "ux_design"]},
]


# ==========================================
# Phase 6: BOM 成本与供应链
# 预计 75 分钟
# ==========================================
PHASE6_TOPICS = [
    {"title": "智能摩托车全盔 V1 BOM 成本估算：模块级拆解", "domain": "components",
     "searches": ["smart motorcycle helmet BOM cost breakdown 2025", "AR glasses BOM component cost analysis", "motorcycle helmet electronics module cost estimation"],
     "tags": ["bom", "cost"],
     "refine_prompt": (
         "基于搜索结果，输出智能摩托车全盔 V1 的 BOM 成本估算表。\n"
         "必须包含以下模块的单件成本区间（美元）：\n"
         "1. 头盔壳体（碳纤维/玻纤复合）\n"
         "2. EPS/EPP 缓冲层\n"
         "3. 面罩/镜片\n"
         "4. HUD 光机模组（含微显示+光学元件+支架）\n"
         "5. 主控 SoC（AR1/AR2 级别）\n"
         "6. 音频模组（扬声器+麦克风阵列+ANC）\n"
         "7. 摄像头模组（4K IMX 级别）\n"
         "8. 电池（4000mAh 锂聚合物）\n"
         "9. BLE+WiFi 模组\n"
         "10. 传感器（IMU+气压+GPS）\n"
         "11. LED 氛围灯\n"
         "12. PCB+线束+连接器\n"
         "13. 按键/触控模组\n"
         "14. 组装+测试\n"
         "给出总 BOM 范围和零售定价建议。\n\n"
         "搜索结果：\n{search_data}"
     )},
    {"title": "HUD 光机模组成本拆解：LCoS/DLP/MicroLED 路线成本对比", "domain": "components",
     "searches": ["HUD optical module cost LCoS DLP MicroLED comparison", "AR display module BOM cost waveguide birdbath", "motorcycle helmet HUD module unit cost 2025"],
     "tags": ["bom", "hud"]},
    {"title": "4K 摄像头模组成本与供应商：舜宇/丘钛/欧菲", "domain": "components",
     "searches": ["4K camera module cost supplier Sunny Optical QTech OFilm", "IMX678 camera module assembly cost BOM", "action camera module OEM price motorcycle helmet"],
     "tags": ["bom", "camera"]},
    {"title": "碳纤维全盔壳体成本与工艺：预浸料/RTM/拉挤对比", "domain": "components",
     "searches": ["carbon fiber motorcycle helmet shell cost manufacturing", "carbon fiber composite helmet prepreg RTM process cost", "motorcycle helmet shell manufacturing OEM cost 2025"],
     "tags": ["bom", "shell"]},
    {"title": "EPS/EPP 缓冲层模具与单件成本", "domain": "components",
     "searches": ["EPS EPP helmet liner mold cost unit price", "motorcycle helmet foam liner tooling investment", "MIPS liner cost motorcycle helmet integration"],
     "tags": ["bom", "liner"]},
    {"title": "歌尔/立讯/闻泰 JDM 报价模式与 NRE 行业基准", "domain": "components",
     "searches": ["Goertek JDM NRE pricing model smart wearable 2025", "Luxshare ODM helmet electronics module pricing", "smart wearable JDM ODM NRE cost benchmark China"],
     "tags": ["bom", "supply_chain"]},
    {"title": "头盔量产测试设备与产线投资估算", "domain": "components",
     "searches": ["motorcycle helmet production line equipment cost", "smart helmet manufacturing test equipment investment", "helmet production line automation assembly testing"],
     "tags": ["bom", "manufacturing"]},
    {"title": "首批 5000 台量产的物料采购策略与备货周期", "domain": "components",
     "searches": ["small batch production material procurement strategy", "5000 unit production run component lead time", "smart device pilot production inventory management"],
     "tags": ["supply_chain", "production"]},
    {"title": "认证送检与模具投资的前期资金需求估算", "domain": "lessons",
     "searches": ["motorcycle helmet certification mold investment budget", "smart helmet pre-production investment breakdown", "helmet startup capital requirement certification tooling"],
     "tags": ["bom", "investment"]},
    {"title": "头盔退货率与售后成本行业基准", "domain": "lessons",
     "searches": ["motorcycle helmet return rate industry benchmark", "smart wearable device RMA rate after-sales cost", "consumer electronics return rate helmet category"],
     "tags": ["bom", "after_sales"]},
]


# ==========================================
# Phase 7: 骑行用户研究与场景洞察
# 预计 60 分钟
# ==========================================
PHASE7_TOPICS = [
    {"title": "中国摩旅用户画像：年龄/收入/车型/骑行频次/消费意愿", "domain": "competitors",
     "searches": ["中国摩旅用户画像 年龄 收入 消费 2025", "motorcycle touring rider demographics China 2025", "摩托车骑行用户调研报告 中国市场"],
     "tags": ["user_research", "china"]},
    {"title": "高端摩托车用户装备消费：头盔/骑行服/电子设备预算分布", "domain": "competitors",
     "searches": ["premium motorcycle rider gear spending helmet budget", "motorcycle equipment consumer spending survey 2025", "高端摩托车装备 消费 头盔 预算 调研"],
     "tags": ["user_research", "spending"]},
    {"title": "摩托车骑行安全痛点调研：事故原因/盲区/疲劳/天气", "domain": "lessons",
     "searches": ["motorcycle accident cause analysis blind spot fatigue 2025", "motorcycle rider safety pain points survey", "摩托车事故原因 骑行安全 痛点 调研"],
     "tags": ["user_research", "safety"]},
    {"title": "团骑/车队用户需求：通信/编队/领队管理/路线共享", "domain": "lessons",
     "searches": ["motorcycle group ride communication needs survey", "motorcycle club ride management leader follower", "团骑 车队 通信 需求 对讲机 蓝牙"],
     "tags": ["user_research", "group_ride"]},
    {"title": "摩托车通勤用户需求：导航/通话/安全/快捷操作", "domain": "lessons",
     "searches": ["motorcycle commuter needs navigation call safety", "urban motorcycle rider daily use helmet features", "摩托车通勤 用户需求 导航 安全"],
     "tags": ["user_research", "commute"]},
    {"title": "内容创作骑手需求：拍摄/剪辑/分享/社区", "domain": "lessons",
     "searches": ["motorcycle content creator camera sharing needs", "motovlog rider gear requirements camera helmet", "摩托车内容创作 拍摄 分享 需求"],
     "tags": ["user_research", "content_creator"]},
    {"title": "智能头盔购买决策因子排序：安全>导航>通话>拍摄>价格", "domain": "lessons",
     "searches": ["smart motorcycle helmet purchase decision factors survey", "motorcycle helmet buyer priority safety features price", "智能头盔 购买因素 排名 调研"],
     "tags": ["user_research", "purchase"]},
    {"title": "头盔佩戴舒适度影响因素：重量/重心/通风/噪音/贴合", "domain": "lessons",
     "searches": ["motorcycle helmet comfort factors weight balance ventilation", "helmet comfort study head pressure noise reduction", "头盔舒适度 影响因素 重量 通风 降噪"],
     "tags": ["user_research", "comfort"]},
]


# ==========================================
# Phase 8: 软件架构参考
# 预计 45 分钟
# ==========================================
PHASE8_TOPICS = [
    {"title": "智能头盔软件架构：RTOS+Linux+App 三层分工", "domain": "components",
     "searches": ["smart helmet software architecture RTOS Linux app", "wearable device firmware architecture Bluetooth audio HUD", "IoT device software stack embedded Linux BLE"],
     "tags": ["software", "architecture"]},
    {"title": "HUD 渲染引擎方案：LVGL/Flutter Embedded/自研比较", "domain": "components",
     "searches": ["HUD rendering engine LVGL Flutter embedded comparison", "embedded GUI framework wearable display 2025", "motorcycle HUD display software rendering solution"],
     "tags": ["software", "hud_rendering"]},
    {"title": "头盔-手机蓝牙通信协议设计：BLE GATT + SPP + A2DP 混合", "domain": "components",
     "searches": ["BLE GATT SPP A2DP smart device communication design", "bluetooth protocol stack smart helmet phone", "wearable device bluetooth multi-profile concurrent"],
     "tags": ["software", "bluetooth"]},
    {"title": "OTA 升级安全设计：双分区/签名校验/断电恢复", "domain": "components",
     "searches": ["OTA firmware update safety dual partition wearable", "smart device OTA security signed image rollback", "embedded device OTA failure recovery best practice"],
     "tags": ["software", "ota"]},
    {"title": "头盔端 AI 推理框架：TensorFlow Lite/ONNX/自研 NPU", "domain": "components",
     "searches": ["edge AI inference framework wearable TFLite ONNX 2025", "on-device AI smart helmet voice ADAS inference", "NPU accelerator wearable device AI model deployment"],
     "tags": ["software", "ai_framework"]},
    {"title": "骑行数据采集与隐私合规：GDPR/个人信息保护法", "domain": "standards",
     "searches": ["smart helmet data collection privacy GDPR compliance", "wearable device personal data protection China PIPL", "motorcycle helmet camera GPS data privacy regulation"],
     "tags": ["software", "privacy"]},
    {"title": "视频编码与存储方案：H.265/AV1 + eMMC/microSD 选型", "domain": "components",
     "searches": ["4K video encoding H265 AV1 wearable device 2025", "action camera video storage eMMC microSD comparison", "video recording storage solution smart helmet"],
     "tags": ["software", "video"]},
]


# ==========================================
# 主流程
# ==========================================
def run_all(notify_func=None):
    start = time.time()
    start_stats = get_knowledge_stats()
    start_total = sum(start_stats.values())
    
    log(f"{'#'*60}", notify_func)
    log(f"# 10 小时定向深度学习启动", notify_func)
    log(f"# 知识库: {start_total} 条", notify_func)
    log(f"# 主题: {sum(len(x) for x in [PHASE1_TOPICS, PHASE2_TOPICS, PHASE3_TOPICS, PHASE4_TOPICS, PHASE5_TOPICS, PHASE6_TOPICS, PHASE7_TOPICS, PHASE8_TOPICS])} 个", notify_func)
    log(f"{'#'*60}", notify_func)
    
    all_stats = {}
    
    phases = [
        ("Phase 1: 竞品 App 拆解", PHASE1_TOPICS),
        ("Phase 2: HUD/AR 交互设计模式", PHASE2_TOPICS),
        ("Phase 3: 量产认证深度细节", PHASE3_TOPICS),
        ("Phase 4: 电池热管理与续航", PHASE4_TOPICS),
        ("Phase 5: 语音交互与降噪", PHASE5_TOPICS),
        ("Phase 6: BOM 成本与供应链", PHASE6_TOPICS),
        ("Phase 7: 骑行用户研究", PHASE7_TOPICS),
        ("Phase 8: 软件架构参考", PHASE8_TOPICS),
    ]
    
    for phase_name, topics in phases:
        stats = run_phase(phase_name, topics, notify_func)
        all_stats[phase_name] = stats
        time.sleep(10)
    
    # 最终总结
    end_stats = get_knowledge_stats()
    end_total = sum(end_stats.values())
    total_min = (time.time() - start) / 60
    total_added = sum(s["added"] for s in all_stats.values())
    
    final = (
        f"\n{'#'*60}\n"
        f"# 10 小时定向深度学习完成\n"
        f"{'#'*60}\n\n"
        f"⏱️ 耗时: {total_min:.0f} 分钟\n"
        f"📊 知识库: {start_total} → {end_total}（+{end_total - start_total}）\n"
        f"📝 本次入库: {total_added} 条\n\n"
    )
    
    for name, stats in all_stats.items():
        final += f"  {name}: +{stats['added']} 条 ({stats['minutes']:.0f}min)\n"
    
    print(final)
    if notify_func:
        notify_func(final)
    
    # 保存报告
    report_dir = Path(__file__).parent.parent / ".ai-state" / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / f"deep_learn_v2_{datetime.now().strftime('%Y%m%d_%H%M')}.md").write_text(final, encoding="utf-8")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="10小时定向深度学习")
    parser.add_argument("--all", action="store_true", help="执行全部阶段")
    parser.add_argument("--phase", type=int, help="执行单个阶段 (1-8)")
    args = parser.parse_args()
    
    notify = None
    try:
        from scripts.feishu_sdk_client import send_reply
        TARGET = "ou_8e5e4f183e9eca4241378e96bac3a751"
        def feishu_notify(msg):
            try:
                send_reply(TARGET, msg)
            except:
                pass
        notify = feishu_notify
        print("[DeepLearn] 飞书推送已连接")
    except:
        print("[DeepLearn] 飞书推送不可用")
    
    if args.all:
        run_all(notify)
    elif args.phase:
        phases = [
            ("Phase 1: 竞品 App 拆解", PHASE1_TOPICS),
            ("Phase 2: HUD/AR 交互设计模式", PHASE2_TOPICS),
            ("Phase 3: 量产认证深度细节", PHASE3_TOPICS),
            ("Phase 4: 电池热管理与续航", PHASE4_TOPICS),
            ("Phase 5: 语音交互与降噪", PHASE5_TOPICS),
            ("Phase 6: BOM 成本与供应链", PHASE6_TOPICS),
            ("Phase 7: 骑行用户研究", PHASE7_TOPICS),
            ("Phase 8: 软件架构参考", PHASE8_TOPICS),
        ]
        if 1 <= args.phase <= len(phases):
            name, topics = phases[args.phase - 1]
            run_phase(name, topics, notify)
    else:
        run_all(notify)
```

---

## 启动方式

让 CC 先创建文件，然后新开终端运行：

```powershell
cd D:\Users\uih00653\my_agent_company\pythonProject1
.venv\Scripts\activate
python scripts/overnight_deep_learning_v2.py --all
```

飞书收 8 次阶段完成通知 + 1 次最终总结。

---

## 8 个阶段预计产出

| Phase | 方向 | 主题数 | 预计入库 | 预计耗时 |
|-------|------|--------|---------|---------|
| 1 | 竞品 App 拆解 | 10 | 8-10 | 60 min |
| 2 | HUD/AR 交互设计 | 12 | 10-12 | 75 min |
| 3 | 量产认证细节 | 10 | 8-10 | 75 min |
| 4 | 电池热管理 | 8 | 6-8 | 60 min |
| 5 | 语音交互方案 | 8 | 6-8 | 60 min |
| 6 | BOM 与供应链 | 10 | 8-10 | 75 min |
| 7 | 骑行用户研究 | 8 | 6-8 | 60 min |
| 8 | 软件架构参考 | 7 | 5-7 | 45 min |
| **合计** | | **73** | **57-73** | **~8.5h** |
