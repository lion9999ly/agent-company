# 深度研究管道 Bug 修复文档

> CC 执行文档 — 2026-03-29
> 目标：修复 5 层升级后暴露的 4 个 bug
> 涉及文件：
>   - `src/utils/model_gateway.py`
>   - `scripts/tonight_deep_research.py`
> 完成后：`git add -A && git commit -m "fix: deep research pipeline — 404 alert, extract/critic wiring, consistency check"`

---

## Bug 1：o3 模型调用全部 404 + 静默降级（P0）

### 根因

`model_registry.yaml` 中 o3 的 `deployment` 值为 `"o3"`，但 Azure portal 上的实际部署名可能不同（如 `o3-2025-04-16` 或其他带日期后缀的名称）。`call_azure_openai()` 用 `deployment` 拼 URL，404 后返回 `{"success": False}`，调用方 `_call_model()` 直接返回失败，`deep_research_one()` 对 CTO/CMO 的失败处理是 `if result.get("success"): agent_outputs[role] = ...`——不成功就跳过，没有任何告警。

### 修复分两步

#### Step 1：model_gateway.py — 404 显式告警 + 飞书推送

文件：`src/utils/model_gateway.py`
位置：`call_azure_openai()` 方法，约第 671 行 `result = resp.json()` 之后

当前代码在 `resp.status_code != 200` 时只打印了 `[Azure-Diag] status=xxx`，然后走到 `'choices' not in result` 分支返回 `{"success": False}`。需要在此处加入 404 专项处理。

**在 `result = resp.json()` 和 `latency_ms = ...` 之后、`if 'choices' in result:` 之前，插入：**

```python
            # === Bug1 Fix: 404/部署名不匹配 显式告警 ===
            if resp.status_code == 404:
                error_msg = (
                    f"[MODEL_404] {model_name} (deployment={deployment_name}) "
                    f"返回 404。请检查 Azure portal 确认实际部署名。"
                    f"\n  URL: {url[:120]}"
                    f"\n  Response: {str(result)[:200]}"
                )
                print(error_msg)
                # 尝试推送飞书告警（best effort）
                try:
                    from scripts.feishu_handlers.text_router import send_feishu_alert
                    send_feishu_alert(f"⚠️ 模型 404\n{model_name} deployment={deployment_name}\n请检查 Azure 部署名")
                except Exception:
                    pass  # 告警失败不影响主流程
                return {
                    "success": False,
                    "error": error_msg,
                    "status_code": 404,
                    "model": model_name,
                    "deployment": deployment_name
                }

            if resp.status_code >= 400 and resp.status_code != 404:
                error_msg = (
                    f"[MODEL_ERROR] {model_name} status={resp.status_code}: "
                    f"{str(result)[:300]}"
                )
                print(error_msg)
                return {
                    "success": False,
                    "error": error_msg,
                    "status_code": resp.status_code,
                    "model": model_name
                }
```

注意：如果 `send_feishu_alert` 函数不存在，CC 需要在 `text_router.py` 中创建一个简单版本，或者把 try/except 里的 import 改成项目中已有的飞书推送函数。搜索项目中已有的飞书推送方式（如 `reply_target`、`send_message` 等），用已有的即可。

#### Step 2：确认 o3 真实部署名并更新 model_registry.yaml

这一步需要 Leo 在 Azure portal 手动确认。CC 先写一个测试脚本：

创建文件 `scripts/test_model_availability.py`：

```python
"""逐个测试 model_registry 中所有模型的可用性"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.model_gateway import get_model_gateway

gateway = get_model_gateway()

# 要测试的模型列表（深度研究管道用到的）
test_models = [
    ("o3", "azure_openai"),
    ("o3_deep_research", "azure_openai"),
    ("gpt_5_4", "azure_openai"),
    ("gemini_3_1_pro", "google"),
    ("gemini_2_5_flash", "google"),
    ("gpt_5_3", "azure_openai"),
]

print("=" * 60)
print("模型可用性测试")
print("=" * 60)

for model_name, expected_provider in test_models:
    cfg = gateway.models.get(model_name)
    if not cfg:
        print(f"  ❌ {model_name}: 未在 registry 中找到")
        continue
    if not cfg.api_key:
        print(f"  ❌ {model_name}: 无 API key")
        continue

    print(f"\n  Testing {model_name} (deployment={cfg.deployment}, model={cfg.model})...")
    result = gateway.call(model_name, "Say hello in one word.", "You are a test bot.", "general")

    if result.get("success"):
        resp_preview = result.get("response", "")[:80]
        print(f"  ✅ {model_name}: OK — {resp_preview}")
    else:
        error = result.get("error", "unknown")[:200]
        status = result.get("status_code", "?")
        print(f"  ❌ {model_name}: FAILED (status={status}) — {error}")

        # 如果是 404，给出修复建议
        if "404" in str(error) or status == 404:
            print(f"     💡 建议：检查 Azure portal 中 {model_name} 的实际 deployment 名称")
            print(f"     💡 当前配置 deployment={cfg.deployment}")

print("\n" + "=" * 60)
```

**Leo 需要做的**：运行 `python scripts/test_model_availability.py`，把结果贴给 CC。如果 o3 返回 404，从 Azure portal 复制实际部署名，CC 更新 `model_registry.yaml` 中 o3 和 o3_deep_research 的 `deployment` 字段。

---

## Bug 2：结构化提取 `_extract_structured_data` 未被调用（P0）

### 根因

`_extract_structured_data()` 函数定义在第 215 行，但在 `deep_research_one()` 的主流程中**从未被调用**。搜索完成后（Step 1，第 569 行），直接跳到了 Step 2（知识库检索）和 Step 3（角色分配），搜索原始文本直接拼接进 CTO/CMO/CDO 的 prompt，没有经过结构化提取。

同时，`_generate_targeted_queries()` 和 `_run_expert_analysis_in_slices()` 也定义了但未在主流程中使用。

### 修复

在 `deep_research_one()` 中，Step 1 搜索完成后（第 569 行 `hb.finish(...)` 之后）、Step 2 知识库检索之前，插入结构化提取步骤。

**在第 573 行 `return f"# {title}\n\n调研失败..."` 之后（即 `if not all_sources:` 块结束后），插入：**

```python
    # Step 1.5: 结构化提取 —— 从搜索结果中提取结构化数据点
    print(f"  [L3.A] 开始结构化提取...")
    structured_data_list = []
    task_type_hint = task.get("goal", "") + " " + title
    for src in all_sources:
        extracted = _extract_structured_data(
            raw_text=src["content"],
            task_type=task_type_hint,
            topic=src["query"]
        )
        if extracted:
            structured_data_list.append(extracted)
    print(f"  [L3.A] 提取完成: {len(structured_data_list)}/{len(all_sources)} 成功")

    # 将结构化数据序列化，附加到搜索材料中供 Agent 使用
    structured_dump = ""
    if structured_data_list:
        structured_dump = "\n\n## 结构化提取数据\n"
        structured_dump += json.dumps(structured_data_list, ensure_ascii=False, indent=2)[:6000]
```

然后在 Step 3.5 各 Agent 的 prompt 中，将 `source_material` 改为包含结构化数据：

**修改第 692 行：**

```python
    source_material = source_dump[:12000]  # 搜索材料
```

改为：

```python
    source_material = source_dump[:10000]  # 搜索材料
    if structured_dump:
        source_material += structured_dump[:4000]  # 附加结构化数据
```

同时，在 CTO prompt 中（约第 696 行）增加一段指引，让 CTO 优先使用结构化数据：

在 `cto_prompt` 的 `## 你的任务` 部分之前，插入：

```python
            f"## 结构化数据（优先使用）\n"
            f"以下是从搜索结果中提取的结构化数据点，每个字段附有 source 和 confidence。\n"
            f"优先基于这些数据做分析，原始搜索材料作为补充参考。\n\n"
```

### 验证

日志中应出现：
```
[L3.A] 开始结构化提取...
[L3.A] 提取完成: X/Y 成功
```

---

## Bug 3：Critic 挑战模式存在但有条件性不触发（P1）

### 根因

Critic 挑战代码**已经正确串联**在主流程中（第 853-966 行），但它位于 `else: report = synthesis_result["response"]` 分支内（第 850-851 行）。这意味着：

1. 如果 synthesis 成功（`synthesis_result.get("success")` 为 True）→ 进入 Critic 挑战 ✅
2. 如果 synthesis 失败 → 走 retry → 走 expand → Critic 不触发 ❌
3. 如果所有 Agent 都失败（o3 全 404）→ 走 fallback 单 CPO 模式（第 768 行）→ Critic 不触发 ❌

所以 Bug 3 是 Bug 1 的连锁后果：o3 全 404 → CTO/CMO 都失败 → 只有 CDO 输出 → synthesis 用 o3 也 404 → retry 也 404 → 走 expand fallback → **跳过 Critic**。

### 修复

将 Critic 挑战逻辑提取为独立函数，在所有报告生成路径之后统一调用：

**1. 提取 Critic 为独立函数（在 `deep_research_one` 之前添加）：**

```python
def _run_critic_challenge(report: str, goal: str, agent_outputs: dict,
                          progress_callback=None) -> str:
    """对报告执行 Critic 挑战，返回修正后的报告"""
    if len(report) < 500:
        print("  [Critic] 报告太短，跳过挑战")
        return report

    print("  [L5] 开始 Critic 挑战...")

    critic_prompt = (
        f"你的职责不是打分，而是提出最尖锐、最有建设性的挑战问题。\n\n"
        f"## 任务目标\n{goal}\n\n"
        f"## 报告（{len(report)}字）\n{report[:8000]}\n\n"
        f"## 挑战规则\n"
        f"1. 找出分析中最薄弱的 3 个论点，每个提出一个具体的反驳或追问\n"
        f"2. 反驳必须基于知识库数据、搜索到的事实、或明显的逻辑漏洞，不能泛泛说'建议加强'\n"
        f"3. 特别关注：\n"
        f"   - 数据来源的可靠性（confidence 标注是否合理？有没有把推测当事实？）\n"
        f"   - 缺失的关键视角（有没有忽略某个重要的竞品/约束/风险？）\n"
        f"   - 结论与数据的一致性（数据说 A，结论却选了 B？）\n"
        f"4. 如果分析质量已经足够好，指出 1-2 个可以进一步深化的方向\n\n"
        f"## 输出格式\n"
        f"输出 JSON：\n"
        f'{{"challenges": ["挑战1内容", "挑战2内容", "挑战3内容"], "overall": "PASS或NEEDS_FIX"}}\n'
    )

    critic_result = _call_model(
        _get_model_for_task("critic_challenge"), critic_prompt,
        "只输出 JSON。", "critic_review"
    )

    if not critic_result.get("success"):
        print(f"  [Critic] 调用失败: {critic_result.get('error', '')[:100]}")
        return report

    needs_fix = False
    challenges_list = []

    try:
        resp = critic_result["response"].strip()
        resp = re.sub(r'^```json\s*', '', resp)
        resp = re.sub(r'\s*```$', '', resp)
        critic_data = json.loads(resp)
        challenges_list = critic_data.get("challenges", [])

        if critic_data.get("overall") == "NEEDS_FIX" and challenges_list:
            needs_fix = True
            print(f"  [Critic] NEEDS_FIX: {len(challenges_list)} challenges")
        else:
            print(f"  [Critic] PASS")
    except Exception as e:
        print(f"  [Critic] Parse failed: {e}")
        # 仍附加原始 critic 输出
        report += f"\n\n---\n## Critic Review\n{critic_result['response'][:1000]}"
        return report

    # 如果需要修复，执行挑战回应流程
    if needs_fix and challenges_list:
        challenge_responses = []

        for i, challenge in enumerate(challenges_list[:3]):
            needs_search = any(kw in challenge for kw in ["数据", "证据", "来源", "补充"])
            extra_data = ""

            if needs_search:
                kw_result = _call_model("gemini_2_5_flash",
                    f"从以下挑战问题中提取 1-2 个搜索关键词：\n{challenge}\n只输出关键词，空格分隔",
                    task_type="query_generation")
                if kw_result.get("success"):
                    extra_query = kw_result["response"].strip()
                    if extra_query:
                        search_result = registry.call("deep_research", extra_query)
                        if search_result.get("success") and len(search_result.get("data", "")) > 100:
                            extra_data = f"\n\n## 针对此挑战的补充搜索结果\n{search_result['data'][:2000]}"

            primary_role = list(agent_outputs.keys())[0] if agent_outputs else "CTO"
            response_model = _get_model_for_role(primary_role)
            response_result = _call_model(response_model,
                f"Critic 对你的分析提出了以下挑战：\n\n{challenge}\n\n{extra_data}\n\n"
                f"请直接回应这个挑战。如果 Critic 说得对，承认并修正你的结论。",
                task_type=f"challenge_response_{i}")

            if response_result.get("success"):
                challenge_responses.append({
                    "challenge": challenge,
                    "response": response_result["response"],
                    "extra_search": bool(extra_data)
                })
                print(f"  [Challenge {i+1}] responded")

        if challenge_responses:
            challenge_dialogue = ""
            for r in challenge_responses:
                challenge_dialogue += f"\n[挑战] {r['challenge']}\n[回应] {r['response']}\n"

            final_result = _call_model(
                _get_model_for_task("final_synthesis"),
                f"以下是一份技术研究的完整过程：\n\n"
                f"## 初始分析报告\n{report[:6000]}\n\n"
                f"## Critic 挑战与专家回应\n{challenge_dialogue}\n\n"
                f"请基于初始报告和挑战对话，输出最终版报告。\n"
                f"要求：挑战中被证实的问题必须修正；新数据必须整合；\n"
                f"仍然遵守决策支撑输出格式；末尾添加'Critic 挑战记录'小节。\n\n"
                f"任务目标：{goal}",
                task_type="final_synthesis"
            )
            if final_result.get("success"):
                report = final_result["response"]
                print(f"  [Final Synthesis] {len(report)} chars")

    # 附加 Critic 评审意见
    report += f"\n\n---\n## Critic Review\n{critic_result['response'][:1000]}"
    return report
```

**2. 在 `deep_research_one()` 中，替换原有的 Critic 逻辑：**

删除第 852-969 行的内联 Critic 代码（从 `# Step 5: Critic 挑战（挑战者模式）` 到 `report += f"\n\n---\n## Critic Review\n..."`）。

在所有报告生成路径汇合后（fallback 和正常路径都执行完之后），统一调用：

```python
    # === Step 5: Critic 挑战（所有路径统一执行）===
    report = _run_critic_challenge(report, goal, agent_outputs, progress_callback)
```

这行代码应该放在当前第 970 行 `# Step 4: 保存报告到文件` 之前。确保无论是正常 synthesis、retry、expand fallback 还是 single CPO fallback，都会经过 Critic。

### 验证

日志中应出现：
```
[L5] 开始 Critic 挑战...
[Critic] PASS 或 [Critic] NEEDS_FIX: N challenges
```

无论 synthesis 走的是哪条路径。

---

## Bug 4：同一报告内结论自相矛盾（P1）

### 根因

研究 A 和研究 B 由不同模型（或同一模型的不同 fallback）处理，产出的推荐结论不一致。缺乏跨研究的一致性校验。

### 修复

在 `run_research_from_file()` 中（第 1186 行），所有研究任务跑完、汇总保存之前，插入一致性校验步骤。

**在第 1228 行 `time.sleep(3)` 之后、`# 汇总保存` 之前，插入：**

```python
    # === 跨研究一致性校验 ===
    if len(reports) >= 2:
        print(f"\n  [ConsistencyCheck] 检查 {len(reports)} 份报告的结论一致性...")

        # 提取每份报告的关键结论
        conclusions = ""
        for r in reports:
            conclusions += f"\n\n### {r['title']}\n{r['report'][:2000]}"

        consistency_prompt = (
            f"以下是同一个项目（智能骑行头盔）的 {len(reports)} 份研究报告的结论部分。\n\n"
            f"请检查它们之间是否存在自相矛盾：\n"
            f"1. 研究 A 推荐方案 X，但研究 B 推荐方案 Y？\n"
            f"2. 研究 A 说某参数为 P，研究 B 说同一参数为 Q？\n"
            f"3. 同一产品在不同报告中被不同评价？\n\n"
            f"输出 JSON：\n"
            f'{{"contradictions": [{{"report_a": "标题", "report_b": "标题", '
            f'"description": "矛盾描述", "severity": "high/medium/low"}}], '
            f'"consistent": true/false}}\n\n'
            f"如果没有发现矛盾，contradictions 为空数组，consistent 为 true。\n\n"
            f"{conclusions}"
        )

        check_result = _call_model(
            _get_model_for_task("critic_challenge"),
            consistency_prompt,
            "只输出 JSON。",
            "consistency_check"
        )

        if check_result.get("success"):
            try:
                resp = check_result["response"].strip()
                resp = re.sub(r'^```json\s*', '', resp)
                resp = re.sub(r'\s*```$', '', resp)
                check_data = json.loads(resp)

                contradictions = check_data.get("contradictions", [])
                if contradictions:
                    print(f"  [ConsistencyCheck] ⚠️ 发现 {len(contradictions)} 个矛盾:")
                    for c in contradictions:
                        print(f"    - [{c.get('severity','?')}] {c.get('description','')[:100]}")

                    # 将矛盾信息附加到汇总报告中
                    contradiction_section = "\n\n---\n## ⚠️ 跨研究一致性问题\n\n"
                    for c in contradictions:
                        contradiction_section += (
                            f"- **[{c.get('severity','')}]** {c.get('report_a','')} vs {c.get('report_b','')}：\n"
                            f"  {c.get('description','')}\n\n"
                        )
                    # 附加到最后一份报告的末尾
                    reports[-1]["report"] += contradiction_section

                    if progress_callback:
                        progress_callback(
                            f"⚠️ 一致性检查：发现 {len(contradictions)} 个跨报告矛盾，已记录在汇总中"
                        )
                else:
                    print(f"  [ConsistencyCheck] ✅ 无矛盾")
            except Exception as e:
                print(f"  [ConsistencyCheck] 解析失败: {e}")
        else:
            print(f"  [ConsistencyCheck] 调用失败: {check_result.get('error', '')[:100]}")
```

### 验证

汇总报告中多份研究结论不一致时，末尾会出现 `## ⚠️ 跨研究一致性问题` 小节。

---

## 附加：专家框架注入确认（P2）

### 当前状态

`_match_expert_framework()` 函数定义在第 77 行，`expert_frameworks.yaml` 已就绪。但在 `deep_research_one()` 主流程中，**从未被调用**。各 Agent 的 prompt 用的是硬编码的通用角色描述，没有注入专家框架中的 `role`、`known_pitfalls` 和 `evaluation_criteria`。

### 修复

在 `deep_research_one()` 中，Step 3.5 各 Agent 分析之前（约第 689 行），插入框架匹配：

```python
    # Step 3.4: 匹配专家框架
    expert_fw = _match_expert_framework(goal, title)
    expert_role = expert_fw.get("role", "")
    expert_pitfalls = expert_fw.get("known_pitfalls", [])
    expert_criteria = expert_fw.get("evaluation_criteria", [])

    expert_injection = ""
    if expert_role:
        expert_injection += f"\n## 你的专家背景\n{expert_role}\n"
    if expert_pitfalls:
        expert_injection += f"\n## 已知陷阱（必须检查）\n"
        for i, p in enumerate(expert_pitfalls, 1):
            expert_injection += f"{i}. {p}\n"
    if expert_criteria:
        expert_injection += f"\n## 评估标准\n"
        for i, c in enumerate(expert_criteria, 1):
            expert_injection += f"{i}. {c}\n"

    if expert_injection:
        print(f"  [ExpertFW] 匹配到专家框架，注入 {len(expert_injection)} 字")
```

然后在 CTO/CMO/CDO 的 prompt 中，将 `expert_injection` 插入到 `anchor_instruction` 之后：

```python
    # 示例 CTO prompt 修改（CMO/CDO 同理）：
    if "CTO" in roles:
        cto_prompt = (
            f"你是智能骑行头盔项目的技术合伙人（CTO）。\n"
            f"{expert_injection}\n"          # ← 新增
            f"{anchor_instruction}\n"
            f"{THINKING_PRINCIPLES}\n"
            # ... 后续不变
        )
```

### 验证

日志中应出现 `[ExpertFW] 匹配到专家框架，注入 XXX 字`。
CTO 分析光学参数时，应能看到"眼盒标称值 vs 实际可用值"等专业陷阱的影响。

---

## 执行顺序

1. Bug 1 Step 1（model_gateway 404 告警）
2. Bug 1 Step 2（创建测试脚本）→ **暂停，等 Leo 跑测试确认部署名**
3. Bug 2（结构化提取串联）
4. Bug 3（Critic 提取为独立函数 + 统一调用）
5. Bug 4（一致性校验）
6. 附加（专家框架注入）

全部改完后：

```bash
git add -A && git commit -m "fix: deep research pipeline — 404 alert, extract wiring, critic unified, consistency check, expert framework injection"
```

**不要重启服务，Leo 手动重启。**
