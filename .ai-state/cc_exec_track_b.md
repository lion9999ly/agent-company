# CC 执行文档 — 轨道 B: 飞书交互层

> 文件集: scripts/feishu_handlers/text_router.py, commands.py, feishu_sdk_client.py
> 不要动: tonight_deep_research.py, deep_research/*.py, knowledge_base.py, model_gateway.py
> 每项改完后: `git add -A && git commit -m "..." && git push origin main`
> **不要重启服务。**

---

## B-1: A3 深度学习交互式触发

已有执行文档: `.ai-state/cc_exec_deep_learn_interactive.md`。按该文档执行。

核心改动：
- text_router.py 中添加 `_deep_learn_pending` 状态
- 发"深度学习"先问时长，回复数字后启动
- < 0.5h 拒绝，0.5-12h 直接启动，> 12h 二次确认

commit: `"feat: deep learning interactive trigger with duration prompt"`

---

## B-2: C1 每日早报

在 text_router.py 中注册"早报"指令，并创建早报生成逻辑：

```python
# 在 route_text_message() 中添加:
if text_stripped in ("早报", "morning", "日报"):
    _handle_morning_brief(reply_target, send_reply)
    return
```

```python
def _handle_morning_brief(reply_target: str, send_reply):
    """生成并推送每日早报（决策视角）"""
    send_reply(reply_target, "🌅 正在生成早报...")

    def _run():
        try:
            brief = _generate_morning_brief()
            send_reply(reply_target, brief)
        except Exception as e:
            send_reply(reply_target, f"早报生成失败: {e}")

    threading.Thread(target=_run, daemon=True).start()


def _generate_morning_brief() -> str:
    """生成每日早报"""
    lines = [f"🌅 早报 {datetime.now().strftime('%Y-%m-%d')}\n"]

    # 1. 决策进展
    dt_path = PROJECT_ROOT / ".ai-state" / "product_decision_tree.yaml"
    if dt_path.exists():
        try:
            import yaml as _yaml
            dt = _yaml.safe_load(dt_path.read_text(encoding='utf-8'))
            lines.append("📌 决策进展")
            for d in dt.get("decisions", []):
                if d.get("status") == "open":
                    total = len(d.get("blocking_knowledge", []))
                    resolved = len(d.get("resolved_knowledge", []))
                    icon = "🟢" if resolved >= total * 0.8 else "🟡" if resolved >= total * 0.5 else "🔴"
                    lines.append(f"  {icon} {d['question'][:50]} ({resolved}/{total})")
        except:
            pass

    # 2. 最近报告摘要
    reports_dir = PROJECT_ROOT / ".ai-state" / "reports"
    if reports_dir.exists():
        recent = sorted(reports_dir.glob("*.summary.json"), reverse=True)[:3]
        if recent:
            lines.append("\n📝 最新研究")
            for f in recent:
                try:
                    s = json.loads(f.read_text(encoding='utf-8'))
                    lines.append(f"  • {s.get('task_title', '?')[:30]}")
                    lines.append(f"    → {s.get('core_finding', '')[:60]}")
                except:
                    continue

    # 3. KB 统计
    try:
        from src.tools.knowledge_base import get_knowledge_stats
        stats = get_knowledge_stats()
        total = sum(stats.values())
        lines.append(f"\n📚 知识库: {total} 条")
    except:
        pass

    # 4. Critic 统计
    drift_path = PROJECT_ROOT / ".ai-state" / "critic_drift_log.jsonl"
    if drift_path.exists():
        try:
            last_lines = drift_path.read_text(encoding='utf-8').strip().split('\n')[-5:]
            p0_rates = [json.loads(l).get("p0_rate", 0) for l in last_lines]
            avg_p0 = sum(p0_rates) / len(p0_rates) if p0_rates else 0
            lines.append(f"🔍 Critic P0 率: {avg_p0:.0%}（最近 {len(p0_rates)} 次）")
        except:
            pass

    return "\n".join(lines)
```

同时注册定时推送（如果有 scheduler）。如果有 APScheduler 或类似机制，注册每天 8:00 自动推送。如果没有，只支持手动触发。

commit: `"feat: daily morning brief — decision-focused daily digest"`

---

## B-3: C3 状态仪表盘

在 text_router.py 中注册"状态"指令：

```python
if text_stripped in ("状态", "dashboard", "仪表盘", "status"):
    _handle_dashboard(reply_target, send_reply)
    return
```

```python
def _handle_dashboard(reply_target: str, send_reply):
    """生成系统状态仪表盘"""
    lines = [f"📊 agent_company 状态\n"]

    # KB
    try:
        from src.tools.knowledge_base import get_knowledge_stats
        stats = get_knowledge_stats()
        total = sum(stats.values())
        detail = " | ".join([f"{k}: {v}" for k, v in stats.items()])
        lines.append(f"🧠 知识库: {total} 条 ({detail})")
    except:
        pass

    # 任务
    try:
        tracker_path = PROJECT_ROOT / ".ai-state" / "task_tracker.jsonl"
        if tracker_path.exists():
            today = datetime.now().strftime('%Y-%m-%d')
            today_tasks = sum(1 for l in tracker_path.read_text(encoding='utf-8').strip().split('\n')
                             if today in l and '"completed"' in l)
            lines.append(f"📝 今日任务: {today_tasks} 个完成")
    except:
        pass

    # 元能力
    try:
        reg_path = PROJECT_ROOT / ".ai-state" / "tool_registry.json"
        if reg_path.exists():
            reg = json.loads(reg_path.read_text(encoding='utf-8'))
            tools = [t for t in reg.get("tools", []) if t.get("status") == "active"]
            if tools:
                names = ", ".join([t["name"] for t in tools[:5]])
                lines.append(f"🧬 元能力: {len(tools)} 个工具 ({names})")
    except:
        pass

    # API 用量
    try:
        from src.utils.token_usage_tracker import get_tracker
        tracker = get_tracker()
        # 如果有 generate_daily_report 方法则调用
        if hasattr(tracker, 'generate_daily_report'):
            lines.append(f"💰 {tracker.generate_daily_report()}")
    except:
        pass

    # Critic
    try:
        drift_path = PROJECT_ROOT / ".ai-state" / "critic_drift_log.jsonl"
        if drift_path.exists():
            last_lines = drift_path.read_text(encoding='utf-8').strip().split('\n')[-5:]
            p0_rates = [json.loads(l).get("p0_rate", 0) for l in last_lines]
            avg_p0 = sum(p0_rates) / len(p0_rates) if p0_rates else 0
            lines.append(f"🔍 Critic: P0 率 {avg_p0:.0%}（最近 {len(p0_rates)} 次）")
    except:
        pass

    # 校准
    try:
        cal_path = PROJECT_ROOT / ".ai-state" / "critic_calibration.jsonl"
        if cal_path.exists():
            count = sum(1 for _ in open(cal_path, encoding='utf-8'))
            lines.append(f"🎯 校准: {count} 条已标注")
    except:
        pass

    send_reply(reply_target, "\n".join(lines))
```

commit: `"feat: system dashboard — full status overview via Feishu command"`

---

## B-4: C5 产品 One-Pager

```python
if text_stripped in ("产品简介", "one pager", "产品概要", "产品介绍"):
    _handle_one_pager(reply_target, send_reply)
    return
```

```python
def _handle_one_pager(reply_target: str, send_reply):
    """生成产品 One-Pager"""
    send_reply(reply_target, "📄 正在生成产品简介...")

    def _run():
        try:
            from src.utils.model_gateway import get_model_gateway
            from src.tools.knowledge_base import search_knowledge, get_knowledge_stats
            gw = get_model_gateway()

            # 收集 KB 精华
            highlights = search_knowledge("智能骑行头盔 V1 核心功能 HUD 导航", limit=10)
            kb_text = "\n".join([f"- {h.get('title','')}: {h.get('content','')[:200]}" for h in highlights])

            prompt = (
                f"基于以下知识库信息，生成一份智能骑行头盔的产品 One-Pager。\n\n"
                f"## 知识库精华\n{kb_text}\n\n"
                f"## 要求\n"
                f"1. 标题 + 一句话副标题\n"
                f"2. 3-4 个核心功能亮点（每个一句话）\n"
                f"3. 目标用户和市场定位\n"
                f"4. 技术差异化（和竞品比有什么独特的）\n"
                f"5. V1 上市时间线\n\n"
                f"语言要有感染力，像给投资人看的 pitch deck 第一页。"
            )

            result = gw.call("gpt_5_4", prompt, "你是产品营销专家。", "content_generation")
            if result.get("success"):
                send_reply(reply_target, result["response"])
            else:
                send_reply(reply_target, f"生成失败: {result.get('error', '')[:200]}")
        except Exception as e:
            send_reply(reply_target, f"生成失败: {e}")

    threading.Thread(target=_run, daemon=True).start()
```

commit: `"feat: product one-pager generation via Feishu command"`

---

## B-5: B4 决策简报

```python
if text_stripped.startswith("决策简报") or text_stripped.startswith("decision brief"):
    decision_id = text_stripped.replace("决策简报", "").replace("decision brief", "").strip().strip(":：")
    _handle_decision_brief(decision_id, reply_target, send_reply)
    return
```

```python
def _handle_decision_brief(decision_id: str, reply_target: str, send_reply):
    """生成决策简报"""
    send_reply(reply_target, f"📋 正在生成决策简报: {decision_id}...")

    def _run():
        try:
            import yaml as _yaml
            from src.utils.model_gateway import get_model_gateway
            from src.tools.knowledge_base import search_knowledge
            gw = get_model_gateway()

            # 读决策树
            dt_path = PROJECT_ROOT / ".ai-state" / "product_decision_tree.yaml"
            decision = None
            if dt_path.exists():
                dt = _yaml.safe_load(dt_path.read_text(encoding='utf-8'))
                for d in dt.get("decisions", []):
                    if decision_id.lower() in d.get("id", "").lower() or decision_id in d.get("question", ""):
                        decision = d
                        break

            if not decision:
                send_reply(reply_target, f"⚠️ 未找到决策: {decision_id}\n可用决策ID: " +
                    ", ".join([d["id"] for d in dt.get("decisions", [])]))
                return

            # 搜索相关 KB
            kb_results = search_knowledge(decision["question"], limit=15)
            kb_text = "\n".join([f"- [{r.get('confidence','')}] {r.get('title','')}: {r.get('content','')[:200]}"
                                for r in kb_results])

            # 读 resolved_knowledge
            resolved = decision.get("resolved_knowledge", [])
            resolved_text = "\n".join([f"- {r.get('knowledge','')}" for r in resolved]) if resolved else "暂无"

            prompt = (
                f"生成决策简报。\n\n"
                f"## 决策问题\n{decision['question']}\n\n"
                f"## 已确认的知识\n{resolved_text}\n\n"
                f"## 相关知识库条目\n{kb_text}\n\n"
                f"## 仍缺的知识\n" +
                "\n".join([f"- {bk}" for bk in decision.get("blocking_knowledge", [])]) +
                f"\n\n## 要求\n"
                f"1. 列出所有可选方案（每个方案的优势/劣势/BOM/供应商/风险）\n"
                f"2. 标注数据来源的 confidence\n"
                f"3. 标注仍缺的关键信息\n"
                f"4. 如果数据足够，给出推荐\n"
                f"5. 如果数据不足，说明还需要什么信息才能做决定"
            )

            result = gw.call("gpt_5_4", prompt, "你是产品决策顾问，输出结构化的决策简报。", "synthesis")
            if result.get("success"):
                send_reply(reply_target, result["response"])
            else:
                send_reply(reply_target, f"生成失败: {result.get('error', '')[:200]}")
        except Exception as e:
            send_reply(reply_target, f"生成失败: {e}")

    threading.Thread(target=_run, daemon=True).start()
```

commit: `"feat: decision brief generation — structured decision support document"`

---

## B-6: H5 谈判准备简报

```python
if text_stripped.startswith("谈判准备") or text_stripped.startswith("negotiation"):
    target_name = text_stripped.replace("谈判准备", "").replace("negotiation", "").strip().strip(":：")
    _handle_negotiation_brief(target_name, reply_target, send_reply)
    return
```

实现逻辑类似决策简报，但 prompt 聚焦于：对方产能/报价/竞品对比/BATNA/谈判策略。

commit: `"feat: negotiation prep brief — auto-generate bargaining chips for supplier talks"`

---

## B-7: I1 注意力管理

在 `.ai-state/focus.yaml` 中维护当前关注焦点：

```python
if text_stripped.startswith("关注焦点") or text_stripped.startswith("focus"):
    focus_text = text_stripped.replace("关注焦点", "").replace("focus", "").strip().strip(":：")
    _handle_set_focus(focus_text, reply_target, send_reply)
    return
```

早报和汇总报告按 focus 排序过滤。

commit: `"feat: attention management — focus-based filtering for all notifications"`

---

## B-8: I2 决策复盘

```python
if text_stripped.startswith("决策复盘") or text_stripped.startswith("decision replay"):
    ...
```

commit: `"feat: decision replay — reconstruct full decision timeline for stakeholder review"`

---

## B-9: J2 反事实推演

```python
if text_stripped.startswith("假如") or text_stripped.startswith("what if"):
    ...
```

commit: `"feat: counterfactual reasoning — what-if analysis for alternative decisions"`

---

## B-10: J3 入职知识包

```python
if text_stripped.startswith("入职包") or text_stripped.startswith("onboarding"):
    ...
```

commit: `"feat: onboarding knowledge pack — role-based structured learning path"`

---

## B-11: E5 多角色支持

在 `.ai-state/user_roles.yaml` 中记录用户角色映射（open_id → role）。回答时根据角色调整深度和视角。

commit: `"feat: multi-role support — different perspectives for different team members"`

---

## 总提交数: 11 个 commit

---

## B-12: L1 意图智能路由

替换 `is_rd_task()` 的关键词匹配，用 Flash 做意图分类。在 `route_text_message()` 中，当前面的精确指令和快捷方式都没匹配上时，用 LLM 判断意图：

```python
def _classify_intent(text: str) -> str:
    """用 Flash 分类用户意图"""
    from src.utils.model_gateway import get_model_gateway
    gw = get_model_gateway()
    result = gw.call("gemini_2_5_flash",
        f"用户说: {text}\n\n"
        f"判断意图类别（只输出类别名）:\n"
        f"research_task — 需要多Agent协作的研发分析\n"
        f"decision_brief — 想看某个决策的简报\n"
        f"negotiation — 谈判准备\n"
        f"knowledge_query — 查询知识库\n"
        f"deep_drill — 想深入研究某个话题\n"
        f"coach — 想理清思路，需要教练式提问\n"
        f"product_vision — 想看产品愿景或场景描述\n"
        f"status — 想看系统状态\n"
        f"chat — 普通闲聊或简单问题\n",
        task_type="intent_classify")
    if result.get("success"):
        return result["response"].strip().split("\n")[0].strip()
    return "chat"
```

在兜底路由之前插入意图分类，根据分类结果路由到对应处理器。

commit: `"feat: LLM-based intent routing — natural language understanding replaces keyword matching"`

---

## B-13: L2 教练模式

```python
_coach_mode = {}  # {open_id: True}

# 在 route_text_message 中:
if text_stripped in ("教练模式", "帮我理清思路", "coach", "coaching"):
    _coach_mode[open_id or "default"] = True
    send_reply(reply_target, "🧠 已进入教练模式。我只问问题，不给答案。\n说"退出教练"结束。\n\n你目前最纠结的决策是什么？")
    return

if text_stripped in ("退出教练", "exit coach"):
    _coach_mode.pop(open_id or "default", None)
    send_reply(reply_target, "✅ 已退出教练模式。")
    return

# 在兜底路由之前:
if _coach_mode.get(open_id or "default"):
    _handle_coach_response(text_stripped, reply_target, send_reply)
    return


def _handle_coach_response(text: str, reply_target: str, send_reply):
    """教练模式回复——只问问题，不给答案"""
    from src.utils.model_gateway import get_model_gateway
    gw = get_model_gateway()
    # 注入 KB 上下文，让教练的问题有数据支撑
    from src.tools.knowledge_base import search_knowledge
    kb = search_knowledge(text, limit=5)
    kb_text = "\n".join([f"- {r.get('title','')}: {r.get('content','')[:150]}" for r in kb])

    result = gw.call("gpt_5_4",
        f"用户说: {text}\n\n"
        f"相关知识:\n{kb_text}\n\n"
        f"你是一个苏格拉底式教练。规则:\n"
        f"1. 绝对不给答案或建议\n"
        f"2. 只问一个尖锐的问题，挑战用户的假设或暴露盲区\n"
        f"3. 问题要基于数据（引用知识库中的信息）\n"
        f"4. 保持友善但犀利",
        "你是产品教练，只问问题不给答案。", "coach")
    if result.get("success"):
        send_reply(reply_target, result["response"])
    else:
        send_reply(reply_target, "你这个问题很有意思——你觉得最大的风险是什么？")
```

commit: `"feat: coaching mode — Socratic questioning to challenge assumptions and reveal blind spots"`

---

## B-14: L4 竞品战争推演

```python
if text_stripped.startswith("竞品推演") or text_stripped.startswith("competitor war game"):
    competitor = text_stripped.replace("竞品推演", "").replace("competitor war game", "").strip().strip(":：")
    _handle_competitor_wargame(competitor, reply_target, send_reply)
    return
```

实现：搜索 KB 中该竞品的全部数据，用 gpt-5.4 推演未来 12 个月动向 + 应对策略。

commit: `"feat: competitor war game — predict competitor moves and prepare counter-strategies"`

---

## 更新后总提交数: 14 个 commit

---

## B-15: M2 知识滴灌

在 feishu_sdk_client.py 或 text_router.py 中注册一个定时推送（如果有 scheduler）或在深度学习空闲间隔推送：

```python
def _drip_knowledge(send_reply, reply_target: str):
    """推送一条高价值知识滴灌"""
    from src.tools.knowledge_base import KB_ROOT
    import random

    # 筛选：最近 7 天入库 + high confidence + 未被滴灌过
    candidates = []
    dripped_path = PROJECT_ROOT / ".ai-state" / "dripped_ids.json"
    dripped = set()
    if dripped_path.exists():
        try: dripped = set(json.loads(dripped_path.read_text(encoding='utf-8')))
        except: pass

    for f in KB_ROOT.rglob("*.json"):
        try:
            data = json.loads(f.read_text(encoding='utf-8'))
            if (data.get("confidence") in ("high", "authoritative") and
                str(f) not in dripped and
                data.get("created_at", "") >= (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")):
                candidates.append((f, data))
        except:
            continue

    if not candidates:
        return

    path, entry = random.choice(candidates)
    # 用 Flash 生成一句话摘要
    from src.utils.model_gateway import get_model_gateway
    gw = get_model_gateway()
    result = gw.call("gemini_2_5_flash",
        f"用一句话总结这条知识的核心价值（30字以内）:\n{entry.get('title','')}: {entry.get('content','')[:300]}",
        task_type="quick_summary")
    if result.get("success"):
        send_reply(reply_target, f"💡 你知道吗：{result['response'].strip()}")
        dripped.add(str(path))
        dripped_path.write_text(json.dumps(list(dripped)[-500:], ensure_ascii=False), encoding='utf-8')
```

飞书指令注册：
```python
if text_stripped in ("关闭滴灌", "stop drip"):
    # 设置标志关闭滴灌
    ...
if text_stripped in ("开启滴灌", "start drip"):
    # 开启滴灌
    ...
```

commit: `"feat: knowledge drip — periodic high-value knowledge micro-notifications"`

---

## B-16: M3 报告自动提取行动清单

在报告摘要生成后，追加行动项提取。在 text_router.py 注册"待办"指令：

```python
if text_stripped in ("待办", "todo", "行动清单", "action items"):
    _handle_action_items(reply_target, send_reply)
    return
```

行动项存储在 `.ai-state/action_items.jsonl`，由深度研究报告完成后自动提取并追加。

commit: `"feat: auto-extract action items from research reports + todo command"`

---

## 最终总提交数: 16 个 commit

---

## B-17: O1 应知清单

```python
if text_stripped.startswith("应知清单") or text_stripped.startswith("due diligence"):
    decision_id = text_stripped.replace("应知清单", "").replace("due diligence", "").strip().strip(":：")
    _handle_due_diligence(decision_id, reply_target, send_reply)
    return
```

标准 checklist 模板维度：技术可行性、供应链可靠性、BOM 成本、专利风险、用户接受度、安全认证兼容、售后维修方案、竞品应对策略。对比 KB 覆盖，输出 ✅/❌ 清单。

commit: `"feat: due diligence checklist — auto-detect what you should know but don't"`

---

## B-18: O6 产出版本管理与 Diff

```python
if text_stripped.startswith("简报diff") or text_stripped.startswith("brief diff"):
    decision_id = text_stripped.replace("简报diff", "").replace("brief diff", "").strip().strip(":：")
    _handle_output_diff(decision_id, reply_target, send_reply)
    return
```

每次生成决策简报/产品简介等结构化输出时，自动保存到 `.ai-state/output_versions/{type}_{id}_{timestamp}.md`。diff 时加载最近两个版本，用 Flash 做语义级对比。

commit: `"feat: output versioning and semantic diff — track how conclusions evolve over time"`

---

## 最终总提交数: 18 个 commit

---

## B-19: P2 HUD 设计规范生成器

```python
if text_stripped in ("HUD设计规范", "hud design spec", "HUD规范"):
    _handle_hud_design_spec(reply_target, send_reply)
    return
```

系统从 KB 搜索 HUD 技术约束 + 竞品布局 + 人因工程数据，生成信息布局规范。

commit: `"feat: HUD design spec generator — layout rules from KB technical constraints"`

## B-20: P3 Demo 场景脚本生成器

```python
if text_stripped in ("Demo脚本", "demo script", "demo场景"):
    _handle_demo_script(reply_target, send_reply)
    return
```

从 PRD 提取 5-8 个核心场景，生成分镜脚本。

commit: `"feat: demo scenario script generator — storyboard from PRD"`

## B-21: Q4 简单问答快速通道

在 `_smart_route_and_reply()` 之前，如果智能路由判定为 `knowledge_query`，直接走 KB 搜索 + 单次模型调用，跳过多 Agent。

commit: `"feat: fast-track for simple queries — KB + single model call, skip multi-agent"`

## B-22: 设置截止日指令

```python
if text_stripped.startswith("设置截止日") or text_stripped.startswith("set deadline"):
    # 解析 "设置截止日: v1_display 2026-04-30"
    # 更新 product_decision_tree.yaml 中对应决策的 deadline 字段
    ...
```

commit: `"feat: set decision deadline command"`

---

## 最终总提交数: 22 个 commit

---

## B-23: R1 权限层

新增 `_check_permission(open_id, required_role)` 函数，在每个指令处理前调用。从 `.ai-state/access_control.yaml` 读取角色映射。未注册用户默认 viewer。

commit: `"feat: access control — role-based permission checking for all commands"`

## B-24: R2 操作分级

在高成本操作（深度学习、深钻、谈判简报等）的 handler 中，调用 `_check_permission(open_id, "manager")`。权限不足时回复"⚠️ 此操作需要 manager 及以上权限"。

commit: `"feat: operation-level access control — restrict expensive operations by role"`

## B-25: R6 新手引导

在消息处理入口检查 open_id 是否首次出现。首次出现时发送引导消息（根据角色定制），并记录到 `.ai-state/known_users.json`。

commit: `"feat: onboarding guide — personalized welcome for first-time users"`

---

## 最终总提交数: 25 个 commit

---

## B-26: X4+X5 自检指令 + 定时健康监控

在 text_router.py 中注册"自检"指令：

```python
if text_stripped in ("自检", "self check", "health check", "测试", "自愈"):
    _handle_self_check(reply_target, send_reply)
    return

def _handle_self_check(reply_target, send_reply):
    send_reply(reply_target, "🔍 开始系统自检...")
    def _run():
        from scripts.self_heal import run_self_heal_cycle
        run_self_heal_cycle(send_reply=send_reply, reply_target=reply_target)
    threading.Thread(target=_run, daemon=True).start()
```

在 feishu_sdk_client.py 的启动逻辑中注册定时健康监控：

```python
def _start_health_monitor():
    """每 6 小时自动运行自愈循环"""
    def _loop():
        while True:
            time.sleep(6 * 3600)
            try:
                from scripts.self_heal import run_self_heal_cycle
                run_self_heal_cycle()  # 无飞书通知的静默模式，结果写日志
            except: pass
    threading.Thread(target=_loop, daemon=True).start()
```

commit: `"feat: self-check command + periodic health monitor every 6 hours"`

---

## 最终最终总提交数: 26 个 commit
