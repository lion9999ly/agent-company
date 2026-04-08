# CC 指令：系统全面升级 v2

> **来源**：Claude Chat 与 Leo 讨论确认的架构改进 + 技术债清理 + 夜间管道修复 + 竞品监控重建
> **执行原则**：先讨论确认架构，再写代码。每个模块完成后 commit + push。
> **验证**：每个改动必须有端到端冒烟测试，不接受只报"已完成"。
> **备份**：开始前 `git tag backup-before-v2-refactor`。大重构项各自打 tag。出问题一条命令回退。

---

## 总览：24 个改进项，7 批执行

### 第一批：圆桌核心逻辑（P0）
| # | 改进 | 文件 |
|---|------|------|
| 1 | 收敛分层：方案层 ≤3 轮 + 代码层独立迭代 | roundtable.py |
| 2 | proposer 因果链：Critic 标注新增/遗留/回归 | roundtable.py |
| 3 | Generator 输入动态选择：代码类用 raw_proposal | generator.py, task_spec.py |
| 4 | Verifier 规则库三层结构 + 自动生成规则 | verifier.py, task_spec.py |

### 第二批：增强机制（P1）
| # | 改进 | 文件 |
|---|------|------|
| 5 | Generator 分段失败重试 + 换模型 | generator.py |
| 6 | 圆桌过程快照保留（roundtable_runs/） | roundtable.py, generator.py, verifier.py |
| 7 | 用户评判驱动规则库迭代 | 新建 verdict_parser.py |

### 第三批：系统透明化（P1）
| # | 改进 | 文件 |
|---|------|------|
| 8 | system_status.md + commit 后自动更新 | 新建 |
| 9 | system_architecture_digest.md 初始版本 | 新建 |
| 10 | product_context_digest.md 占位 | 新建（内容由 Claude Chat 维护）|
| 11 | 飞书 "状态" 指令 | text_router.py |

### 第四批：技术债小修（P1）
| # | 改进 | 文件 |
|---|------|------|
| 12 | model_gateway 404 死代码修复 | model_gateway.py |
| 13 | send_reply 定义统一 | 多文件 |
| 14 | 备份文件清理确认 | scripts/, src/utils/ |

### 第五批：大重构（P2，各自打 tag 备份）
| # | 改进 | 文件 |
|---|------|------|
| 15 | model_gateway 去重（_call_openai_compatible） | model_gateway.py |
| 16 | text_router.py 拆分为 handler 模块 | scripts/feishu_handlers/ |
| 17 | 散落测试文件收拢到 tests/ | scripts/ → tests/ |

### 第六批：夜间管道修复（P1）
| # | 改进 | 文件 |
|---|------|------|
| 18 | 深度学习主题池动态化（不再重复搜索） | tonight_deep_research.py |
| 19 | 飞书推送降噪（只推开始+完成+异常） | 多文件 |

### 第七批：竞品监控重建（P1）
| # | 改进 | 文件 |
|---|------|------|
| 20 | 监控维度重建（6 层监控体系） | competitor_monitor.py + 配置 |
| 21 | 搜索词时间限定（丢弃 6 个月前数据） | competitor_monitor.py |
| 22 | 监控输出格式改造（无动态不推送） | competitor_monitor.py |
| 23 | 信息影响研判层（LLM 判断产品相关度） | competitor_monitor.py |
| 24 | 监控配置外部化 | .ai-state/competitor_monitor_config.json |

---

## 第一批详细设计（#1-4）

### #1 收敛分层

**当前问题**：方案讨论阶段试图验证代码层验收标准，10 轮 P0 数量 13→12→10→12→13→13→9→10→10→13，完全没下降。

**改为两层迭代**：

```python
# roundtable.py discuss() 方法

# ====== 方案层（最多 3 轮）======
# Critic prompt："你在审查方案文档，不是代码。
#   只关注：方案是否覆盖所有验收标准（有描述即可）、
#   约束是否矛盾、逻辑是否自洽。
#   不检查：代码可实现性。"
MAX_PROPOSAL_ROUNDS = 3
for i in range(MAX_PROPOSAL_ROUNDS):
    if critic_result.passed or i == MAX_PROPOSAL_ROUNDS - 1:
        break

# ====== 代码层（Generator + Verifier 闭环）======
# 不回方案讨论，Verifier 反馈直接给 Generator.fix()
```

**震荡检测**：
```python
convergence_trace.append(len(critic_result.p0_issues))
if len(convergence_trace) >= 3 and convergence_trace[-1] >= convergence_trace[-3]:
    proposer_prompt += "\n⚠️ 修复震荡。方案已锁定为基线。只改 P0 段落，不重写其他部分。"
```

**冒烟测试**：`圆桌:hud_demo` 方案层 ≤3 轮收敛。

### #2 proposer 因果链

**当前问题**：proposer 盲改，修 A 引入 B，修 B 又破坏 A。

**Critic 输出格式增加**：
```
对每个 P0 问题标注：
- [新增] 本轮新出现
- [遗留] 上轮未修复
- [回归] 上轮已修但又出现（说明上轮哪个修改导致回归）
```

**feedback 包含因果链**：
```python
def _build_p0_feedback(self, critic_result, prev_critic_result):
    for issue in critic_result.p0_issues:
        if issue in prev_p0: feedback += f"- [遗留] {issue}\n"
        elif was_fixed_last_round(issue): feedback += f"- [回归] {issue}（上轮修 {related_fix} 导致）\n"
        else: feedback += f"- [新增] {issue}\n"
```

### #3 Generator 输入动态选择

**当前问题**：CDO 方案有配色值、状态机、剧本事件序列，经 Echo 压缩成 500 字后全丢。

**TaskSpec 新增**：
```python
generator_input_mode: str = "auto"  # "raw_proposal" | "executive_summary" | "auto"
```

**auto 逻辑**：
```python
if output_type in ("html", "code", "json", "jsx"): return "raw_proposal"
elif output_type in ("markdown", "report", "pptx"): return "executive_summary"
```

**Generator 切换输入源**：
```python
if mode == "raw_proposal":
    source = rt_result.final_proposal + rt_result.reviewer_amendments
else:
    source = rt_result.executive_summary
```

**RoundtableResult 新增**：`reviewer_amendments: str = ""`（Phase 3 ❌ 项合并）

**executive_summary 不废弃**，只用于飞书通知和决策备忘录。

**更新 hud_demo.json**：加 `"generator_input_mode": "raw_proposal"`

**冒烟测试**：日志确认 Generator 收到 proposal 原文。

### #4 Verifier 规则库 + 自动生成

**TaskSpec 新增**：
```python
auto_verify_rules: list = field(default_factory=list)
```

**规则类型库**：
```python
RULE_CHECKS = {
    "no_external_deps": ..., "keyword_count": ..., "keyword_exists": ...,
    "file_size_range": ..., "html_valid": ..., "json_parseable": ..., "line_count_range": ...
}
```

**三层执行**：global.json → type_{output_type}.json → TaskSpec.auto_verify_rules

**自动生成**：TaskSpec 无规则时 LLM 根据验收标准生成，保存回 TaskSpec 文件。

**存储**：`.ai-state/verifier_rules/{global,type_html,...}.json` + `evolution_log.jsonl`

**冒烟测试**：清空 hud_demo 的 rules，确认自动生成。

---

## 第二批详细设计（#5-7）

### #5 Generator 分段失败重试

```python
async def _generate_segment(self, segment_def, context, prev_segments, task):
    for model in ["gpt_5_4", "gpt_5_4", "gemini_3_1_pro"]:  # 主→重试→换模型
        result = await self._call_segment(model, segment_def, context, prev_segments)
        if result and self._validate_segment(result): return result
    await self.feishu.notify(f"⚠️ Segment '{segment_def['name']}' 3次失败")
    return None
```

### #6 过程快照保留

每次圆桌创建独立目录 `roundtable_runs/{topic}_{timestamp}/`：

```
input_task_spec.json, crystal_context_summary.md, phase2_proposal_full.md,
phase4_critic_final.md（LLM 原始输出）, generator_input_actual.md（前 3000 字）,
generator_segments/{seg1_input.md, seg1_output.html, ...},
generator_output_raw.html, verifier_result.md, convergence_trace.jsonl, user_verdict.md
```

不保留：每轮 Phase 1/3 中间输出、重试失败临时文件。

### #7 评判解析器

**新建 `scripts/roundtable/verdict_parser.py`**：

用户自然语言评价（如"ADAS按钮点了没反应"）→ LLM 解析为结构化缺陷 → 判断能否转化为规则 → 飞书展示规则草案 → 用户回复"确认"后入库。

**飞书交互**：圆桌完成后 10 分钟内用户发的消息自动当评判处理。

---

## 第三批详细设计（#8-11）

### #8 system_status.md
CC 每次 commit 后自动追加最近变更、已知问题、能力清单、模型可用性。

### #9 system_architecture_digest.md
接口变更时更新。含数据流、关键数据类、模型分配、飞书路由优先级。供 Claude Chat fetch 对齐。

### #10 product_context_digest.md
CC 创建占位文件。内容由 Claude Chat 维护：产品定位、V1 确认决策、待确认决策。CC SDK 调用时注入 system prompt。

### #11 飞书 "状态" 指令
`text_stripped in ("状态", "系统状态", "status")` → 返回 system_status.md 内容。

---

## 第四批详细设计（#12-14）

### #12 gateway 404 死代码
删除 `call_azure_openai` 中 `from text_router import reply_target` 那段永远走 except 的死代码。

### #13 send_reply 统一
`grep "def send_reply"` → 确认 chat_helpers.py 为权威 → 其他位置改 import。

### #14 备份文件清理
确认并删除 `tonight_deep_research_backup_20260406.py` 和 `model_gateway_backup_20260406.py`。

---

## 第五批详细设计（#15-17）

### #15 gateway 去重
**tag**: `backup-before-gateway-refactor`

抽取 `_call_openai_compatible()` 覆盖 Azure/智谱/DeepSeek/火山引擎。保留 `call_gemini` 和 `call_azure_responses`。`call()` 改 dispatch dict。

**回退**：`git checkout backup-before-gateway-refactor -- src/utils/model_gateway.py`
**冒烟**：`python src/utils/model_gateway.py`

### #16 text_router 拆分
**tag**: `backup-before-router-split`

拆为：text_router.py(~150行路由) + learning_handlers.py + roundtable_handler.py + import_handlers.py + smart_chat.py

统一接口：`try_handle(text, reply_target, ...) -> bool`

**回退**：`git checkout backup-before-router-split -- scripts/feishu_handlers/`
**冒烟**：重启 SDK 测全路由。

### #17 测试文件收拢
`find scripts/ -name "test_*.py"` → 移到 `tests/`。

---

## 第六批详细设计（#18-19）

### #18 深度学习主题池动态化

动态选择优先级：决策树数据需求 > KB 弱知识补强 > 竞品深挖 > 固定池未覆盖项。

搜索完成后必须更新 covered_topics，去重最近 7 天已研究主题。

### #19 飞书推送降噪

```python
NOTIFY_RULES = {
    "deep_research": {"start": True, "progress": False, "complete": True, "error": True},
    "competitor_monitor": {"start": False, "no_update": False, "has_update": True},
    "auto_learn": {"start": False, "progress": False, "complete": False, "error": True},
    "roundtable": {"start": True, "phase_complete": False, "convergence": True, "task_complete": True, "error": True}
}
```

配置存 `.ai-state/notify_config.json`。

---

## 第七批详细设计（#20-24）

### #20 监控维度重建

从 5 个品牌名 → 6 层监控：
1. 直接竞品（Shoei Smart/洛克兄弟/MOTOEYE/EyeLights/iC-R/Sena/Cardo...）
2. 技术供应链（JBD/Sony ECX/京东方/FreeForm/光波导/高通AR...）
3. 骑行生态（摩托车市场/摩旅用户/小红书抖音KOL/政策...）
4. 相邻技术（汽车HUD/车载语音/端侧AI/Mesh通讯/AR眼镜...）
5. 法规标准（ECE 22.06/GB 811/两轮ADAS强制/HUD合法性...）
6. 跨界参考（滑雪头盔/自行车头盔/智能硬件融资/Bosch两轮...）

完整搜索词库见配置文件 `.ai-state/competitor_monitor_config.json`。

### #21 搜索词时间限定
自动追加当前年份，丢弃 6 个月前数据，放宽到 12 个月兜底。

### #22 输出格式改造
"无重要新动态"不显示不推送。只推有实质内容的。

### #23 信息影响研判层

每条搜索结果经 LLM 研判（基于 product_context_digest.md）：
- relevance: high/medium/low
- impact_dimension: 技术选型/竞品动态/市场趋势/供应链/法规/用户需求
- impact_detail: 一句话具体影响
- suggested_action: 深挖研究/加入KB/更新竞品档案/无需动作

**分流**：
- high + push_to_founder → 飞书推送 + 入 KB + 标记深挖（自动进入深度学习主题池）
- medium → 只入 KB
- low → 丢弃

**推送格式**：
```
🔔 [技术选型] Google 发布 Gemma 4 端侧模型
影响：语音交互可能实现全端侧化，降低网络依赖
建议：深挖研究
来源：Google AI Blog | 2026-04-07
```

### #24 监控配置外部化
`.ai-state/competitor_monitor_config.json`，飞书指令 `监控范围` 展示配置，`关注 XXX` 追加搜索词。

---

## 执行顺序

```
⚠️ 开始前：git tag backup-before-v2-refactor

第一批 #1-4 → commit: refactor: roundtable v2 core → push → 冒烟：圆桌 ≤3 轮
第二批 #5-7 → commit: feat: generator retry, snapshots, verdict parser → push
第三批 #8-11 → commit: feat: system transparency → push → 冒烟：飞书 "状态"
第四批 #12-14 → commit: fix: tech debt cleanup → push
第五批 #15-17 → 每个单独 commit + tag → push → 冒烟：全路由 + gateway 测试
第六批 #18-19 → commit: feat: dynamic topics, notification noise reduction → push
第七批 #20-24 → commit: refactor: competitor monitor v2 → push → 冒烟：竞品监控

每批完成后 push + 飞书通知。
所有批次完成后更新 system_architecture_digest.md。
```

---

## 验证清单

```
=== 圆桌核心 ===
✅ #1 收敛分层：方案层 ≤3 轮 + 代码层独立
✅ #2 因果链：Critic 标注新增/遗留/回归
✅ #3 Generator 输入：html 用 raw_proposal
✅ #4 Verifier 三层规则 + 自动生成

=== 增强机制 ===
✅ #5 Generator 重试 + 换模型
✅ #6 快照：roundtable_runs/ 完整
✅ #7 评判解析器就绪

=== 透明化 ===
✅ #8 system_status.md 自动更新
✅ #9 architecture_digest.md 初始版本
✅ #10 product_context_digest.md 占位
✅ #11 飞书 "状态" 可用

=== 技术债 ===
✅ #12 gateway 死代码已删
✅ #13 send_reply 统一
✅ #14 备份已清理

=== 大重构 ===
✅ #15 gateway 去重（tag 可回退）
✅ #16 text_router 拆分（tag 可回退）
✅ #17 测试文件收拢

=== 夜间管道 ===
✅ #18 主题池动态化
✅ #19 推送降噪

=== 竞品监控 ===
✅ #20 6 层监控体系
✅ #21 搜索时间限定
✅ #22 无动态不推
✅ #23 影响研判层（高相关推飞书 + 自动入深度学习池）
✅ #24 配置外部化 + 飞书 "监控范围"

=== 最终 ===
✅ regression_check 全量通过
✅ 飞书全路由正常
✅ gateway 测试通过
✅ git push 完成
✅ architecture_digest.md 已更新
```
