# 一夜知识库质量大修 — 从 2500 条"量大质疑"到"条条可靠"

> 生成时间: 2026-03-25 晚
> 预计运行: 8-10 小时（今晚到明早）
> 运行方式: 命令行启动后放着不管，飞书推送关键节点进度
> 推送策略: 每完成一个大阶段推一次（共约 6-8 次），不推中间进度

---

## 创建 scripts/overnight_kb_overhaul.py

```python
"""
@description: 一夜知识库质量大修 - 去伪存真、补深补全、重建决策树
@dependencies: src.tools.knowledge_base, src.utils.model_gateway, scripts.knowledge_graph_expander
@last_modified: 2026-03-25
"""
import json
import re
import gc
import sys
import time
import hashlib
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, str(Path(__file__).parent.parent))

# 加载环境变量
from dotenv import load_dotenv
load_dotenv()

from src.utils.model_gateway import get_model_gateway
from src.tools.knowledge_base import (
    add_knowledge, add_report, search_knowledge,
    get_knowledge_stats, KB_ROOT
)
from src.tools.tool_registry import get_tool_registry


def log(msg: str, notify_func=None):
    """打印 + 可选飞书通知"""
    timestamp = datetime.now().strftime("%H:%M")
    full_msg = f"[{timestamp}] {msg}"
    print(full_msg)
    if notify_func:
        notify_func(full_msg)


def phase_summary(phase_name: str, stats: dict, notify_func=None):
    """阶段完成总结（一定推送飞书）"""
    msg = (
        f"✅ {phase_name} 完成\n"
        f"处理: {stats.get('processed', 0)} 条\n"
        f"改善: {stats.get('improved', 0)} 条\n"
        f"删除: {stats.get('deleted', 0)} 条\n"
        f"耗时: {stats.get('duration_min', 0):.0f} 分钟"
    )
    print(f"\n{'='*50}\n{msg}\n{'='*50}")
    if notify_func:
        notify_func(msg)


# ==========================================
# Phase 1: 深度去重（模糊匹配）
# ==========================================
def phase1_deep_dedup(notify_func=None) -> dict:
    """去除标题和内容高度相似的重复条目，保留最长最新的"""
    start = time.time()
    log("Phase 1: 深度去重开始", notify_func)
    
    from collections import defaultdict
    
    # 收集所有条目
    entries = []
    for f in KB_ROOT.rglob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            entries.append({
                "path": f,
                "title": data.get("title", ""),
                "content": data.get("content", ""),
                "tags": data.get("tags", []),
                "confidence": data.get("confidence", "medium"),
                "mtime": f.stat().st_mtime,
                "size": len(data.get("content", ""))
            })
        except:
            continue
    
    log(f"  扫描到 {len(entries)} 条知识")
    
    # 按标题清洗后分组
    groups = defaultdict(list)
    for entry in entries:
        # 清洗标题：去掉日期前缀、方括号标记、标点
        title = entry["title"]
        clean = re.sub(r'^[\d_]+', '', title)  # 去 0324_ 前缀
        clean = re.sub(r'^\[.*?\]\s*', '', clean)  # 去 [技术档案] [浅档案] 前缀
        clean = re.sub(r'深化[:：]', '', clean)  # 去 深化: 前缀
        clean = re.sub(r'跨界[:：]', '', clean)  # 去 跨界: 前缀
        clean = ''.join(c for c in clean[:40].lower() if c.isalnum() or '\u4e00' <= c <= '\u9fff')
        
        if len(clean) > 5:
            groups[clean].append(entry)
    
    deleted = 0
    for key, group in groups.items():
        if len(group) <= 1:
            continue
        
        # 排序：高置信度 > 内容更长 > 更新
        group.sort(key=lambda x: (
            -({'authoritative': 3, 'high': 2, 'medium': 1, 'low': 0}.get(x['confidence'], 1)),
            -x['size'],
            -x['mtime']
        ))
        
        # 保留第一个，删除其余
        for entry in group[1:]:
            try:
                entry["path"].unlink()
                deleted += 1
            except:
                pass
    
    duration = (time.time() - start) / 60
    stats = {"processed": len(entries), "improved": 0, "deleted": deleted, "duration_min": duration}
    phase_summary("Phase 1: 深度去重", stats, notify_func)
    gc.collect()
    return stats


# ==========================================
# Phase 2: 推测性内容降级/清理
# ==========================================
def phase2_speculative_cleanup(notify_func=None) -> dict:
    """处理推测性内容：有真实数据的保留但标注，纯假想的降级"""
    start = time.time()
    log("Phase 2: 推测性内容清理开始", notify_func)
    
    gateway = get_model_gateway()
    processed = 0
    improved = 0
    deleted = 0
    
    speculative_entries = []
    for f in KB_ROOT.rglob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if "speculative" in data.get("tags", []):
                speculative_entries.append({"path": f, "data": data})
        except:
            continue
    
    log(f"  发现 {len(speculative_entries)} 条推测性条目")
    
    for entry in speculative_entries:
        data = entry["data"]
        content = data.get("content", "")
        title = data.get("title", "")
        processed += 1
        
        # 快速判断：有真实数据的保留，纯假想的删除
        has_real_data = bool(re.search(
            r'\d+\.?\d*\s*(mm|cm|g|kg|mAh|W|V|Hz|dB|美元|元|USD|\$|%|nits|lux|fps|°|μm|TOPS|nm|GHz|MB|GB)',
            content
        ))
        has_real_model = bool(re.search(
            r'[A-Z]{2,}\d{2,}|IMX\d|QCC\d|BES\d|nRF\d|AR[12]|ECE\s*\d|BMI\d|ICM-\d',
            content
        ))
        
        if has_real_data or has_real_model:
            # 有真实数据但混了推测——保留，但在内容前加标注
            if "【注意：以下部分内容为推测】" not in content:
                data["content"] = "【注意：以下部分内容基于趋势推测，非官方确认数据】\n\n" + content
                entry["path"].write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                improved += 1
        else:
            # 纯假想内容，没有任何真实数据——删除
            try:
                entry["path"].unlink()
                deleted += 1
            except:
                pass
        
        if processed % 50 == 0:
            print(f"  进度: {processed}/{len(speculative_entries)}")
    
    duration = (time.time() - start) / 60
    stats = {"processed": processed, "improved": improved, "deleted": deleted, "duration_min": duration}
    phase_summary("Phase 2: 推测性内容清理", stats, notify_func)
    gc.collect()
    return stats


# ==========================================
# Phase 3: 浅条目批量深化
# ==========================================
def phase3_deepen_shallow(notify_func=None) -> dict:
    """浅条目（<200字）批量深化：搜索补充具体数据"""
    start = time.time()
    log("Phase 3: 浅条目深化开始", notify_func)
    
    gateway = get_model_gateway()
    registry = get_tool_registry()
    
    shallow_entries = []
    for f in KB_ROOT.rglob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            content = data.get("content", "")
            tags = data.get("tags", [])
            
            if (len(content) < 200 
                and data.get("type") != "report"
                and "night_deepened" not in tags
                and "speculative" not in tags):
                shallow_entries.append({"path": f, "data": data})
        except:
            continue
    
    log(f"  发现 {len(shallow_entries)} 条浅条目需要深化")
    
    improved = 0
    failed = 0
    
    for i, entry in enumerate(shallow_entries):
        data = entry["data"]
        title = data.get("title", "")
        content = data.get("content", "")
        
        if not title or len(title) < 5:
            continue
        
        # 搜索补充
        query = f"{title} 详细参数 技术规格 datasheet 2026"
        search_result = registry.call("deep_research", query)
        
        if search_result.get("success") and len(search_result.get("data", "")) > 300:
            # 用 LLM 深化
            deepen_prompt = (
                f"以下知识条目内容太浅（仅{len(content)}字），请深化到 400-800 字。\n"
                f"必须补充具体数据（型号、参数、价格、供应商名）。\n"
                f"如果搜索结果中没有具体数据，保持原文不要编造。\n\n"
                f"当前标题：{title}\n当前内容：{content}\n\n"
                f"搜索结果：\n{search_result['data'][:4000]}"
            )
            
            result = gateway.call_azure_openai("cpo", deepen_prompt,
                "深化知识条目，补充具体数据。", "kb_deepen")
            
            if result.get("success") and len(result.get("response", "")) > len(content) + 100:
                data["content"] = result["response"][:1200]
                data["tags"] = list(set(data.get("tags", []) + ["night_deepened", "overhaul_deepened"]))
                data["confidence"] = "medium" if data.get("confidence") == "low" else data.get("confidence", "medium")
                entry["path"].write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                improved += 1
            else:
                failed += 1
        else:
            failed += 1
        
        if (i + 1) % 20 == 0:
            print(f"  进度: {i+1}/{len(shallow_entries)}, 成功: {improved}, 失败: {failed}")
            gc.collect()
        
        time.sleep(1)  # 控制 API 调用频率
    
    duration = (time.time() - start) / 60
    stats = {"processed": len(shallow_entries), "improved": improved, "deleted": 0, "duration_min": duration}
    phase_summary("Phase 3: 浅条目深化", stats, notify_func)
    gc.collect()
    return stats


# ==========================================
# Phase 4: 无数据条目补充
# ==========================================
def phase4_enrich_no_data(notify_func=None) -> dict:
    """给没有具体数据（型号/参数/价格）的条目补充数据"""
    start = time.time()
    log("Phase 4: 无数据条目补充开始", notify_func)
    
    gateway = get_model_gateway()
    registry = get_tool_registry()
    
    no_data_entries = []
    for f in KB_ROOT.rglob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            content = data.get("content", "")
            tags = data.get("tags", [])
            
            if "overhaul_enriched" in tags or "speculative" in tags:
                continue
            if data.get("type") == "report":
                continue
            if len(content) < 100:
                continue
            
            has_data = bool(re.search(
                r'\d+\.?\d*\s*(mm|cm|g|kg|mAh|W|V|Hz|dB|美元|元|USD|\$|%|nits|lux|fps|°|μm|TOPS|GHz)',
                content
            ))
            has_model = bool(re.search(
                r'[A-Z]{2,}\d{2,}|IMX\d|QCC\d|BES\d|nRF\d|AR[12]|ECE\s*\d|BMI\d',
                content
            ))
            
            if not has_data and not has_model:
                no_data_entries.append({"path": f, "data": data})
        except:
            continue
    
    log(f"  发现 {len(no_data_entries)} 条无数据条目")
    
    # 限制每晚处理量，避免 API 耗尽
    batch = no_data_entries[:200]
    log(f"  本轮处理前 {len(batch)} 条")
    
    improved = 0
    
    for i, entry in enumerate(batch):
        data = entry["data"]
        title = data.get("title", "")
        content = data.get("content", "")
        
        # 搜索补充数据
        query = f"{title} 具体参数 型号 规格 价格 供应商"
        search_result = registry.call("deep_research", query)
        
        if search_result.get("success") and len(search_result.get("data", "")) > 200:
            enrich_prompt = (
                f"以下知识条目缺少具体数据。请基于搜索结果补充：\n"
                f"- 具体型号（如 IMX678、BES2800、QCC5181）\n"
                f"- 具体参数（如 3000nits、42dB、1.65kg）\n"
                f"- 具体价格（如 $15-25/颗）\n"
                f"- 具体公司/品牌名\n\n"
                f"标题：{title}\n原内容：{content[:500]}\n\n"
                f"搜索结果：\n{search_result['data'][:3000]}\n\n"
                f"输出补充数据后的完整内容（500-800字），不要编造数据。"
            )
            
            result = gateway.call_azure_openai("cpo", enrich_prompt,
                "补充具体数据，不要编造。", "kb_enrich")
            
            if result.get("success") and len(result.get("response", "")) > len(content):
                # 验证确实补充了数据
                new_content = result["response"]
                has_new_data = bool(re.search(
                    r'\d+\.?\d*\s*(mm|cm|g|kg|mAh|W|V|Hz|dB|美元|元|USD|\$|%|nits)',
                    new_content
                ))
                
                if has_new_data:
                    data["content"] = new_content[:1200]
                    data["tags"] = list(set(data.get("tags", []) + ["overhaul_enriched"]))
                    entry["path"].write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                    improved += 1
        
        if (i + 1) % 30 == 0:
            print(f"  进度: {i+1}/{len(batch)}, 成功补充: {improved}")
            gc.collect()
        
        time.sleep(1)
    
    duration = (time.time() - start) / 60
    stats = {"processed": len(batch), "improved": improved, "deleted": 0, "duration_min": duration}
    phase_summary("Phase 4: 无数据条目补充", stats, notify_func)
    gc.collect()
    return stats


# ==========================================
# Phase 5: 自完整性检测 + 缺口填补
# ==========================================
def phase5_completeness(notify_func=None) -> dict:
    """检测家族缺口并自动填补"""
    start = time.time()
    log("Phase 5: 自完整性检测开始", notify_func)
    
    try:
        from scripts.knowledge_completeness_checker import run_completeness_check
        report = run_completeness_check()
        
        # 统计填补了多少
        filled = report.count("✅")
        
        duration = (time.time() - start) / 60
        stats = {"processed": 1, "improved": filled, "deleted": 0, "duration_min": duration}
        phase_summary("Phase 5: 自完整性检测", stats, notify_func)
    except Exception as e:
        log(f"  Phase 5 失败: {e}")
        stats = {"processed": 0, "improved": 0, "deleted": 0, "duration_min": 0}
    
    gc.collect()
    return stats


# ==========================================
# Phase 6: 自主深挖（选择薄弱方向）
# ==========================================
def phase6_deep_dive(notify_func=None) -> dict:
    """自主深挖薄弱领域"""
    start = time.time()
    log("Phase 6: 自主深挖开始", notify_func)
    
    try:
        from scripts.knowledge_graph_expander import run_autonomous_deep_dive
        report = run_autonomous_deep_dive(progress_callback=None)  # 不推中间进度
        
        new_entries = report.count("✅")
        
        duration = (time.time() - start) / 60
        stats = {"processed": 1, "improved": new_entries, "deleted": 0, "duration_min": duration}
        phase_summary("Phase 6: 自主深挖", stats, notify_func)
    except Exception as e:
        log(f"  Phase 6 失败: {e}")
        import traceback
        traceback.print_exc()
        stats = {"processed": 0, "improved": 0, "deleted": 0, "duration_min": 0}
    
    gc.collect()
    return stats


# ==========================================
# Phase 7: 决策树重建
# ==========================================
def phase7_rebuild_decision_trees(notify_func=None) -> dict:
    """基于清理后的知识库重建所有决策树"""
    start = time.time()
    log("Phase 7: 决策树重建开始", notify_func)
    
    gateway = get_model_gateway()
    
    # 按领域分组知识
    domain_profiles = {}
    for f in KB_ROOT.rglob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            tags = data.get("tags", [])
            if "knowledge_graph" not in tags and "tech_profile" not in tags:
                continue
            if "speculative" in tags:
                continue
            
            # 找到领域 key
            domain_key = None
            for tag in tags:
                if tag in ("ar_xr_soc", "audio_soc", "optical_hud", "sensor_imu",
                          "connector", "battery_bms", "mesh_intercom"):
                    domain_key = tag
                    break
            
            if domain_key:
                if domain_key not in domain_profiles:
                    domain_profiles[domain_key] = []
                domain_profiles[domain_key].append(
                    f"{data.get('title', '')}: {data.get('content', '')[:400]}"
                )
        except:
            continue
    
    trees_built = 0
    
    for domain_key, profiles in domain_profiles.items():
        if len(profiles) < 3:
            continue
        
        log(f"  生成决策树: {domain_key} ({len(profiles)} 份档案)")
        
        decision_prompt = (
            f"你是智能摩托车全盔项目的技术总监。\n"
            f"以下是 {domain_key} 领域的 {len(profiles)} 份技术档案。\n\n"
            f"请生成一份【选型决策树】。\n\n"
            f"格式：\n"
            f"1. 关键决策维度（算力/功耗/接口/成本）\n"
            f"2. 按场景分支推荐，每个推荐说明理由和风险\n"
            f"3. 标注不确定的地方\n"
            f"4. 简洁实用，1500-2500字\n\n"
            f"技术档案：\n" + "\n---\n".join(profiles[:15])
        )
        
        result = gateway.call_azure_openai("cpo", decision_prompt,
            "生成简洁实用的选型决策树。", "rebuild_decision_tree")
        
        if result.get("success") and len(result.get("response", "")) > 500:
            # 先删除旧的决策树
            for f in KB_ROOT.rglob("*.json"):
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                    if "decision_tree" in data.get("tags", []) and domain_key in data.get("tags", []):
                        f.unlink()
                except:
                    continue
            
            # 存新的
            add_report(
                title=f"[决策树] {domain_key} 选型指南（大修后重建）",
                domain="components",
                content=result["response"],
                tags=["knowledge_graph", "decision_tree", domain_key, "overhaul_rebuilt"],
                source=f"overhaul:rebuild_tree:{domain_key}",
                confidence="high"
            )
            trees_built += 1
        
        time.sleep(3)
    
    duration = (time.time() - start) / 60
    stats = {"processed": len(domain_profiles), "improved": trees_built, "deleted": 0, "duration_min": duration}
    phase_summary("Phase 7: 决策树重建", stats, notify_func)
    gc.collect()
    return stats


# ==========================================
# 主流程
# ==========================================
def run_overnight_overhaul(notify_func=None):
    """一夜知识库质量大修主流程"""
    
    start_time = time.time()
    start_stats = get_knowledge_stats()
    start_total = sum(start_stats.values())
    
    log(f"\n{'#'*60}", notify_func)
    log(f"# 知识库质量大修启动", notify_func)
    log(f"# 起始: {start_total} 条", notify_func)
    log(f"# 时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}", notify_func)
    log(f"{'#'*60}", notify_func)
    
    all_stats = {}
    
    # Phase 1: 去重
    all_stats["dedup"] = phase1_deep_dedup(notify_func)
    time.sleep(5)
    
    # Phase 2: 推测性内容清理
    all_stats["speculative"] = phase2_speculative_cleanup(notify_func)
    time.sleep(5)
    
    # Phase 3: 浅条目深化
    all_stats["deepen"] = phase3_deepen_shallow(notify_func)
    time.sleep(5)
    
    # Phase 4: 无数据补充
    all_stats["enrich"] = phase4_enrich_no_data(notify_func)
    time.sleep(5)
    
    # Phase 5: 自完整性检测
    all_stats["completeness"] = phase5_completeness(notify_func)
    time.sleep(5)
    
    # Phase 6: 自主深挖
    all_stats["deep_dive"] = phase6_deep_dive(notify_func)
    time.sleep(5)
    
    # Phase 7: 决策树重建
    all_stats["decision_trees"] = phase7_rebuild_decision_trees(notify_func)
    
    # 最终总结
    end_stats = get_knowledge_stats()
    end_total = sum(end_stats.values())
    total_duration = (time.time() - start_time) / 60
    
    # 最终审计
    shallow_count = 0
    no_data_count = 0
    spec_count = 0
    for f in KB_ROOT.rglob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            content = data.get("content", "")
            tags = data.get("tags", [])
            if len(content) < 200:
                shallow_count += 1
            has_data = bool(re.search(r'\d+\.?\d*\s*(mm|cm|g|kg|mAh|W|V|Hz|dB|美元|元|\$|%|nits)', content))
            has_model = bool(re.search(r'[A-Z]{2,}\d{2,}|IMX\d|QCC\d|BES\d', content))
            if not has_data and not has_model:
                no_data_count += 1
            if "speculative" in tags:
                spec_count += 1
        except:
            continue
    
    shallow_pct = round(shallow_count / end_total * 100, 1) if end_total > 0 else 0
    no_data_pct = round(no_data_count / end_total * 100, 1) if end_total > 0 else 0
    
    final_report = (
        f"\n{'#'*60}\n"
        f"# 知识库质量大修完成报告\n"
        f"{'#'*60}\n\n"
        f"⏱️ 总耗时: {total_duration:.0f} 分钟\n\n"
        f"📊 知识库变化:\n"
        f"  修前: {start_total} 条\n"
        f"  修后: {end_total} 条\n"
        f"  分布: {json.dumps(end_stats, ensure_ascii=False)}\n\n"
        f"📈 质量指标:\n"
        f"  浅条目: {shallow_count} ({shallow_pct}%)\n"
        f"  无数据: {no_data_count} ({no_data_pct}%)\n"
        f"  推测性: {spec_count}\n\n"
        f"🔧 各阶段:\n"
    )
    
    for phase_name, stats in all_stats.items():
        final_report += (
            f"  {phase_name}: "
            f"处理{stats['processed']} 改善{stats['improved']} 删除{stats['deleted']} "
            f"({stats['duration_min']:.0f}min)\n"
        )
    
    print(final_report)
    
    if notify_func:
        notify_func(final_report)
    
    # 保存报告到文件
    report_dir = Path(__file__).parent.parent / ".ai-state" / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"overhaul_{datetime.now().strftime('%Y%m%d_%H%M')}.md"
    report_path.write_text(final_report, encoding="utf-8")
    
    return final_report


if __name__ == "__main__":
    # 命令行独立运行
    notify = None
    
    # 尝试连接飞书推送
    try:
        from scripts.feishu_sdk_client import send_reply
        NOTIFY_TARGET = "ou_8e5e4f183e9eca4241378e96bac3a751"  # 你的 open_id
        
        def feishu_notify(msg):
            try:
                send_reply(NOTIFY_TARGET, msg)
            except:
                pass
        
        notify = feishu_notify
        print("[Overhaul] 飞书推送已连接")
    except:
        print("[Overhaul] 飞书推送不可用，仅终端输出")
    
    run_overnight_overhaul(notify_func=notify)
```

---

## 启动方式

在 PyCharm 终端新开一个窗口（不要关掉飞书机器人的那个），执行：

```powershell
cd D:\Users\uih00653\my_agent_company\pythonProject1
.venv\Scripts\activate
python scripts/overnight_kb_overhaul.py
```

然后去睡觉。明早看飞书推送的最终报告。

---

## 7 个阶段预计时间和产出

| 阶段 | 做什么 | 预计耗时 | 预计效果 |
|------|--------|---------|---------|
| Phase 1 | 深度去重 | 5 分钟 | 删除 50-100 条重复 |
| Phase 2 | 推测性内容清理 | 10 分钟 | 标注/删除 100+ 条假想内容 |
| Phase 3 | 浅条目深化 | 2-3 小时 | 深化 200-300 条浅条目 |
| Phase 4 | 无数据条目补充 | 2-3 小时 | 给 100-200 条补充具体数据 |
| Phase 5 | 自完整性检测 | 30 分钟 | 发现并填补 5-10 个家族缺口 |
| Phase 6 | 自主深挖 | 1-2 小时 | 新增 20-50 条新领域知识 |
| Phase 7 | 决策树重建 | 30 分钟 | 重建 3-5 棵决策树 |

飞书推送约 7-8 次（每个阶段完成推一次 + 最终总结），不会打扰你睡觉。
