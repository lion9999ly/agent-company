"""
@description: 今晚深度研究任务队列 - 10个核心问题的深度调研
@dependencies: scripts.tonight_deep_research
@last_modified: 2026-03-22
"""
import json
import time
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.tonight_deep_research import deep_research_one

TONIGHT_TASKS = [
    # === A: 供应商深挖 ===
    {
        "id": "supplier_negotiation",
        "title": "歌尔合作模式与商务条款拆解",
        "goal": "回答：与歌尔谈JDM，NRE怎么分阶段付？IP归属怎么约定？模具归谁？MOQ多少？行业惯例是什么？",
        "searches": [
            "Goertek JDM ODM NRE fee structure payment terms",
            "歌尔 JDM 合作模式 NRE 费用 分期 付款条件",
            "smart wearable ODM NRE intellectual property IP ownership terms",
            "消费电子 JDM 合作 模具归属 MOQ 最小起订量 行业惯例",
            "Goertek ODM contract terms conditions minimum order quantity",
            "智能穿戴 JDM 开发费 分几期 里程碑付款 EVT DVT PVT",
            "ODM JDM IP ownership mold tooling ownership negotiation best practice",
        ]
    },
    {
        "id": "competitor_supply_chain",
        "title": "竞品供应链溯源——谁在给竞品代工",
        "goal": "回答：Forcite MK1S谁代工？Sena通讯模组谁做的？LIVALL工厂在哪？Cardo Beyond GTS供应链？Shoei GT3 Smart的智能模组谁做的？",
        "searches": [
            "Forcite MK1S manufacturer factory OEM supplier Australia",
            "Forcite helmet who manufactures where is factory",
            "Sena smart helmet manufacturer OEM factory Korea China",
            "Sena communication module supplier chipset manufacturer",
            "LIVALL smart helmet factory manufacturer Shenzhen China OEM",
            "LIVALL BH51M supply chain component supplier",
            "Cardo Beyond GTS manufacturer factory Israel OEM supplier",
            "Cardo Packtalk communication module chipset supplier",
            "Shoei GT3 Smart intelligent module supplier manufacturer",
            "Shoei Opticson HUD display module who makes supplier",
            "smart helmet OEM ODM factory China Shenzhen Dongguan list",
        ]
    },

    # === B: 技术选型 ===
    {
        "id": "main_chipset_selection",
        "title": "头盔主控芯片选型深度对比",
        "goal": "回答：高通QCC/QCS vs 紫光展锐 vs 恒玄BES vs Nordic，哪个最适合智能骑行头盔？参数/价格/生态/功耗对比",
        "searches": [
            "Qualcomm QCC5181 QCC5171 smart helmet audio chipset specs price 2026",
            "Qualcomm QCS400 smart wearable chipset specs power consumption",
            "UNISOC 紫光展锐 smart wearable audio chipset W517 specs price",
            "Bestechnic BES2700 BES2600 smart helmet audio ANC chipset comparison",
            "Nordic nRF5340 nRF54H20 smart wearable BLE audio chipset 2026",
            "smart helmet main chipset selection comparison Qualcomm vs BES vs Nordic",
            "恒玄 BES2700 vs 高通 QCC5181 智能穿戴 音频芯片 对比 价格",
            "smart motorcycle helmet SoC processor selection criteria 2026",
        ]
    },
    {
        "id": "communication_solution",
        "title": "通讯方案选型——蓝牙 vs Mesh 对讲",
        "goal": "回答：Sena用什么方案？Cardo用什么？自研Mesh vs买模组的成本和风险？BLE Audio vs 经典蓝牙？",
        "searches": [
            "Sena Mesh 2.0 intercom technology chipset protocol details",
            "Cardo DMC dynamic meshwork communication technology how it works",
            "motorcycle helmet Mesh intercom vs Bluetooth comparison range latency",
            "BLE LE Audio Auracast motorcycle helmet intercom feasibility 2026",
            "motorcycle intercom module supplier buy vs build cost analysis",
            "Sena communication chipset teardown which chip CSR Qualcomm",
            "Cardo Packtalk teardown communication module chipset analysis",
            "智能头盔 Mesh 对讲 模组 供应商 成本 vs 蓝牙方案",
        ]
    },
    {
        "id": "hud_decision",
        "title": "HUD方案决策——现阶段该不该上",
        "goal": "回答：第一代产品该不该做HUD？如果做，Micro OLED vs 光波导 vs LED矩阵各自成本/风险/供应商？Forcite和Jarvish的教训？",
        "searches": [
            "smart helmet HUD first generation should include risk analysis",
            "Forcite MK1S HUD implementation lessons learned problems",
            "Jarvish X-AR HUD helmet failure analysis what went wrong",
            "EyeLights motorcycle HUD user complaints problems 2025 2026",
            "motorcycle helmet HUD Micro OLED vs waveguide vs LED matrix comparison cost",
            "helmet HUD minimum viable product approach low risk display",
            "Sony microOLED ECX339A specs price power consumption for helmet",
            "motorcycle helmet HUD supplier module cost BOM breakdown 2026",
        ]
    },

    # === C: 商业方向 ===
    {
        "id": "business_model",
        "title": "智能骑行头盔商业模式对比",
        "goal": "回答：众筹vs渠道vs B2B，Forcite/LIVALL/Sena各走什么路？成功和失败的原因？我们应该选哪条路？",
        "searches": [
            "Forcite MK1S business model crowdfunding to retail journey",
            "LIVALL smart helmet business model sales channel strategy",
            "Sena smart helmet distribution channel retail strategy global",
            "smart helmet crowdfunding Kickstarter Indiegogo success failure analysis",
            "smart wearable startup go-to-market strategy D2C vs retail vs B2B",
            "智能头盔 商业模式 众筹 渠道 B2B 成功案例 失败教训",
            "motorcycle accessories market distribution channel analysis 2026",
        ]
    },
    {
        "id": "user_persona",
        "title": "目标用户画像与购买决策",
        "goal": "回答：谁在买$200+智能头盔？骑行频次、收入水平、年龄、决策因素、信息渠道？摩托车vs自行车用户差异？",
        "searches": [
            "smart motorcycle helmet buyer persona demographics income age",
            "who buys premium smart helmet user profile survey data",
            "motorcycle rider technology adoption survey 2025 2026",
            "smart bicycle helmet consumer profile urban commuter vs sport",
            "premium helmet purchase decision factors price quality brand safety",
            "motorcycle accessories consumer behavior online research buying journey",
            "智能头盔 目标用户 画像 购买决策 因素 调研",
        ]
    },
    {
        "id": "user_pain_points",
        "title": "用户核心痛点与未满足需求",
        "goal": "回答：现有竞品用户评价中反复出现的抱怨是什么？哪些需求没被满足？最大的机会点在哪？",
        "searches": [
            "Sena smart helmet user review complaints problems Reddit",
            "Forcite MK1S user review problems complaints Amazon",
            "LIVALL helmet user review complaints what they hate",
            "Cardo Packtalk user complaints problems issues 2025 2026",
            "smart motorcycle helmet user pain points unmet needs survey",
            "motorcycle helmet technology wishlist what riders want 2026",
            "智能头盔 用户评价 差评 痛点 不满意 抱怨 汇总",
            "motorcycle helmet comfort noise wind rain problems user feedback",
        ]
    },

    # === D: PRD 信息储备 ===
    {
        "id": "prd_reference",
        "title": "智能头盔PRD参考——竞品功能规格与优先级",
        "goal": "回答：写PRD需要哪些功能模块？每个模块的参数基线是什么？竞品的功能优先级排序？V1应该包含什么、砍掉什么？",
        "searches": [
            "smart motorcycle helmet PRD product requirements document template",
            "Forcite MK1S full feature spec sheet technical specifications",
            "Sena S1 EVO R2 EVO full specifications features comparison",
            "LIVALL BH51M Neo full feature list specifications",
            "smart helmet MVP minimum viable product feature prioritization",
            "motorcycle smart helmet V1 what to include what to cut scope",
            "智能头盔 PRD 产品需求文档 功能优先级 V1 范围",
            "wearable device PRD best practice feature prioritization framework",
        ]
    },
    {
        "id": "prd_technical_baseline",
        "title": "PRD技术基线——关键模块参数参考值",
        "goal": "回答：蓝牙距离多少米？电池容量多少mAh？续航多少小时？防水等级？重量上限？摄像头分辨率？通话降噪指标？行业基线是什么？",
        "searches": [
            "smart helmet technical specification baseline Bluetooth range battery life",
            "motorcycle helmet electronics weight limit grams industry standard",
            "smart helmet battery capacity mAh typical range 2026 benchmark",
            "motorcycle helmet Bluetooth intercom range meters comparison Sena Cardo",
            "smart helmet waterproof IP rating IP67 IP65 requirement",
            "helmet camera resolution framerate minimum acceptable quality",
            "motorcycle intercom wind noise cancellation dB specification requirement",
            "smart helmet charge time USB-C wireless charging specification baseline",
        ]
    },
]


def run_tonight(progress_callback=None):
    """运行今晚所有深度研究任务"""
    from pathlib import Path
    import time

    REPORT_DIR = Path(".ai-state/reports")
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"\n{'#'*60}")
    print(f"# Tonight Deep Research Queue")
    print(f"# {len(TONIGHT_TASKS)} tasks")
    print(f"# Start: {time.strftime('%Y-%m-%d %H:%M')}")
    print(f"{'#'*60}")

    results = []
    for i, task in enumerate(TONIGHT_TASKS, 1):
        if progress_callback:
            progress_callback(f"[Tonight] [{i}/{len(TONIGHT_TASKS)}] {task['title']}")

        print(f"\n[{i}/{len(TONIGHT_TASKS)}] === {task['title']} ===")
        try:
            report = deep_research_one(task, progress_callback=progress_callback)
            results.append({"title": task["title"], "report": report, "status": "ok"})
            print(f"OK {task['title']} ({len(report)} chars)")

            if progress_callback:
                progress_callback(f"[Tonight] OK [{i}/{len(TONIGHT_TASKS)}] {task['title']} ({len(report)} chars)")
        except Exception as e:
            print(f"FAIL {task['title']}: {e}")
            results.append({"title": task["title"], "report": str(e), "status": "fail"})
            if progress_callback:
                progress_callback(f"[Tonight] FAIL [{i}/{len(TONIGHT_TASKS)}] {task['title']}: {e}")
        time.sleep(5)

    # 汇总报告
    summary_path = REPORT_DIR / f"tonight_research_{time.strftime('%Y%m%d_%H%M')}.md"
    summary = f"# Deep Research Summary ({time.strftime('%Y-%m-%d %H:%M')})\n\n"
    summary += f"Total: {len(TONIGHT_TASKS)} tasks, Success: {sum(1 for r in results if r['status']=='ok')}\n\n"
    for r in results:
        icon = "OK" if r["status"] == "ok" else "FAIL"
        summary += f"\n---\n\n# {icon} {r['title']}\n\n{r['report']}\n"
    summary_path.write_text(summary, encoding="utf-8")

    print(f"\n{'#'*60}")
    print(f"# All done! Report: {summary_path}")
    print(f"# End: {time.strftime('%Y-%m-%d %H:%M')}")
    print(f"{'#'*60}")

    return str(summary_path)


if __name__ == "__main__":
    run_tonight()