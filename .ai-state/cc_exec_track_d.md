# CC 执行文档 — 轨道 D: 新模块（纯新建）

> 文件集: 全部是新建文件，不修改任何现有代码
> 每项改完后: `git add -A && git commit -m "..." && git push origin main`
> **不要重启服务。**
> 注意: 这些模块创建后，需要后续在 text_router.py 或 deep_research 中集成调用。
> 集成调用由轨道 A 或 B 负责，本轨道只负责创建独立模块。

---

## D-1: K1 Handoff 文件机制

```bash
mkdir -p .ai-state/handoffs
```

新建 `scripts/handoff_processor.py`：

```python
"""Handoff 处理器 — 读取 claude.ai 生成的 handoff 文件"""
import json, time
from pathlib import Path

HANDOFF_DIR = Path(__file__).parent.parent / ".ai-state" / "handoffs"
HANDOFF_DIR.mkdir(parents=True, exist_ok=True)

def scan_unprocessed() -> list:
    """扫描未处理的 handoff 文件"""
    unprocessed = []
    for f in sorted(HANDOFF_DIR.glob("handoff_*.md")):
        meta = f.with_suffix('.processed')
        if not meta.exists():
            unprocessed.append(f)
    return unprocessed

def mark_processed(handoff_path: Path):
    """标记 handoff 为已处理"""
    meta = handoff_path.with_suffix('.processed')
    meta.write_text(time.strftime('%Y-%m-%d %H:%M'), encoding='utf-8')

def get_pending_tasks(handoff_path: Path) -> list:
    """从 handoff 文件中提取待执行任务"""
    content = handoff_path.read_text(encoding='utf-8')
    # 简单解析：提取 CC 提示词块
    tasks = []
    import re
    blocks = re.findall(r'```\n(.*?)```', content, re.DOTALL)
    for block in blocks:
        if 'git' in block or 'commit' in block:
            tasks.append(block.strip())
    return tasks
```

commit: `"feat: handoff processor — scan and execute claude.ai session handoffs"`

---

## D-2: K2 系统运行日志自动归档

新建 `scripts/system_log_generator.py`：

```python
"""系统运行日志生成 — 深度学习后自动生成并 push"""
import json, time, subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
LOG_PATH = PROJECT_ROOT / ".ai-state" / "system_log_latest.md"

def generate_system_log(session_summary: dict = None):
    """生成系统运行日志并自动 git push"""
    lines = [f"# 系统运行日志\n", f"> 生成时间: {time.strftime('%Y-%m-%d %H:%M')}\n"]

    # 深度学习汇总
    if session_summary:
        lines.append("## 深度学习汇总")
        lines.append(f"- 任务数: {session_summary.get('task_count', '?')}")
        lines.append(f"- 耗时: {session_summary.get('duration_hours', '?')}h")
        lines.append(f"- KB 增量: +{session_summary.get('kb_added', '?')} 条")
        lines.append(f"- P0 触发: {session_summary.get('p0_tasks', '?')} 个任务")
        for task in session_summary.get('tasks', []):
            lines.append(f"  - {task.get('title', '?')} ({task.get('duration_min', '?')}min)")

    # KB 统计
    try:
        from src.tools.knowledge_base import get_knowledge_stats
        stats = get_knowledge_stats()
        total = sum(stats.values())
        lines.append(f"\n## 知识库状态")
        lines.append(f"- 总条目: {total}")
        for k, v in stats.items():
            lines.append(f"  - {k}: {v}")
    except:
        pass

    # 元能力
    try:
        reg_path = PROJECT_ROOT / ".ai-state" / "tool_registry.json"
        if reg_path.exists():
            reg = json.loads(reg_path.read_text(encoding='utf-8'))
            tools = [t for t in reg.get("tools", []) if t.get("status") == "active"]
            if tools:
                lines.append(f"\n## 元能力工具")
                for t in tools:
                    lines.append(f"- {t['name']}: {t.get('description', '')[:50]} (使用 {t.get('usage_count', 0)} 次)")
    except:
        pass

    # 错误日志
    lines.append(f"\n## 最近错误")
    lines.append("（从 feishu_debug.log 中提取最近 5 条 ERROR）")
    debug_log = PROJECT_ROOT / ".ai-state" / "feishu_debug.log"
    if debug_log.exists():
        try:
            errors = [l for l in debug_log.read_text(encoding='utf-8').split('\n') if 'ERROR' in l or 'error' in l.lower()]
            for e in errors[-5:]:
                lines.append(f"- {e[:200]}")
        except:
            pass

    # 写入
    LOG_PATH.write_text("\n".join(lines), encoding='utf-8')
    print(f"[SystemLog] 已生成: {LOG_PATH}")

    # 自动 git push
    try:
        subprocess.run(["git", "add", str(LOG_PATH)], cwd=str(PROJECT_ROOT), capture_output=True)
        subprocess.run(["git", "commit", "-m", "auto: update system_log_latest.md", "--no-verify"],
                       cwd=str(PROJECT_ROOT), capture_output=True)
        subprocess.run(["git", "push", "origin", "main"], cwd=str(PROJECT_ROOT), capture_output=True)
        print("[SystemLog] 已 push 到 GitHub")
    except Exception as e:
        print(f"[SystemLog] push 失败: {e}")
```

commit: `"feat: system log auto-generation and GitHub push"`

---

## D-3: K3 + K4 CLAUDE.md 关键文件 URL 列表 + 共享大脑

修改 `CLAUDE.md`，在末尾追加两个新章节：

```markdown
---

## 关键文件 URL（供 claude.ai 快速 fetch）

```
https://raw.githubusercontent.com/lion9999ly/agent-company/refs/heads/main/CLAUDE.md
https://raw.githubusercontent.com/lion9999ly/agent-company/refs/heads/main/scripts/tonight_deep_research.py
https://raw.githubusercontent.com/lion9999ly/agent-company/refs/heads/main/src/utils/model_gateway.py
https://raw.githubusercontent.com/lion9999ly/agent-company/refs/heads/main/src/config/model_registry.yaml
https://raw.githubusercontent.com/lion9999ly/agent-company/refs/heads/main/scripts/feishu_handlers/text_router.py
https://raw.githubusercontent.com/lion9999ly/agent-company/refs/heads/main/scripts/meta_capability.py
https://raw.githubusercontent.com/lion9999ly/agent-company/refs/heads/main/scripts/critic_calibration.py
https://raw.githubusercontent.com/lion9999ly/agent-company/refs/heads/main/.ai-state/product_decision_tree.yaml
https://raw.githubusercontent.com/lion9999ly/agent-company/refs/heads/main/.ai-state/system_log_latest.md
https://raw.githubusercontent.com/lion9999ly/agent-company/refs/heads/main/.ai-state/research_task_pool.yaml
https://raw.githubusercontent.com/lion9999ly/agent-company/refs/heads/main/src/tools/knowledge_base.py
```

---

## 三系统共享上下文

### 当前项目阶段
方案论证

### 最近 Handoff 决策要点
（由 handoff 处理器自动更新）

### 系统运行统计
（由 system_log_generator 自动更新）

### 待执行改进清单
见 .ai-state/improvement_backlog_complete.md
```

commit: `"feat: CLAUDE.md upgraded to shared brain — URL registry + cross-system context"`

---

## D-4: E1 价值度量体系

新建 `scripts/roi_tracker.py`：

```python
"""ROI 度量 — 追踪系统产出的可量化指标"""
import json, time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
ROI_PATH = PROJECT_ROOT / ".ai-state" / "roi_metrics.jsonl"

def record_metric(metric_type: str, value: float, description: str = ""):
    """记录一条 ROI 指标"""
    entry = {
        "timestamp": time.strftime('%Y-%m-%d %H:%M'),
        "type": metric_type,
        "value": value,
        "description": description
    }
    ROI_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(ROI_PATH, 'a', encoding='utf-8') as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

def generate_roi_report() -> str:
    """生成 ROI 报告"""
    if not ROI_PATH.exists():
        return "暂无 ROI 数据"

    metrics = {}
    for line in ROI_PATH.read_text(encoding='utf-8').strip().split('\n'):
        try:
            e = json.loads(line)
            t = e["type"]
            if t not in metrics:
                metrics[t] = []
            metrics[t].append(e)
        except:
            continue

    lines = ["📊 ROI 报告\n"]
    # 统计各类指标
    for metric_type, entries in metrics.items():
        latest = entries[-1]
        total = sum(e["value"] for e in entries)
        lines.append(f"- {metric_type}: 最近={latest['value']}, 累计={total}")

    return "\n".join(lines)
```

commit: `"feat: ROI tracker — quantifiable value metrics for system output"`

---

## D-5: E3 主动洞察引擎

新建 `scripts/insight_engine.py`：

```python
"""主动洞察 — 发现异常/风险/机会时推送飞书"""
import json, re, time
from pathlib import Path

def scan_for_insights(report: str, task_title: str) -> list:
    """从研究报告中检测值得主动推送的洞察"""
    insights = []

    # 检测关键词模式
    alert_patterns = [
        (r"(?:新品|发布|上市|推出).*(?:Cardo|Sena|LIVALL|Jarvish|Shoei)", "竞品动态"),
        (r"(?:涨价|降价|缺货|停产|召回)", "供应链风险"),
        (r"(?:专利|侵权|诉讼|禁令)", "知产风险"),
        (r"(?:突破|革新|新技术|首次|全球首)", "技术机会"),
        (r"(?:矛盾|不一致|与.*不符)", "数据矛盾"),
    ]

    for pattern, category in alert_patterns:
        matches = re.findall(pattern, report)
        if matches:
            insights.append({
                "category": category,
                "matches": matches[:3],
                "task": task_title,
                "timestamp": time.strftime('%Y-%m-%d %H:%M'),
            })

    return insights

def format_insight_alert(insight: dict) -> str:
    """格式化洞察为飞书消息"""
    icons = {
        "竞品动态": "🏁", "供应链风险": "⚠️", "知产风险": "⚖️",
        "技术机会": "💡", "数据矛盾": "🔄"
    }
    icon = icons.get(insight["category"], "📢")
    return f"{icon} 主动洞察 [{insight['category']}]\n来源: {insight['task']}\n详情: {', '.join(insight['matches'][:3])}"
```

commit: `"feat: proactive insight engine — auto-detect risks, opportunities, and anomalies"`

---

## D-6: E4 外部信息源监控

新建 `scripts/external_monitor.py`：

```python
"""外部信息源监控 — 竞品动态和行业新闻"""
import time, json
from pathlib import Path

MONITOR_CONFIG = {
    "competitors": ["Cardo Packtalk", "Sena 50S", "LIVALL MC1", "Jarvish X-AR", "Shoei smart helmet"],
    "industry": ["motorcycle helmet technology 2026", "AR HUD helmet", "骑行头盔 智能"],
    "check_interval_hours": 24,
}

def run_external_scan(gateway, progress_callback=None):
    """执行一轮外部信息扫描"""
    findings = []

    for query in MONITOR_CONFIG["competitors"] + MONITOR_CONFIG["industry"]:
        result = gateway.call("doubao_seed_pro", query,
                              "搜索最近一周的最新动态、新品发布、价格变化。只报告新信息。",
                              "external_monitor")
        if result.get("success") and len(result.get("response", "")) > 100:
            findings.append({"query": query, "finding": result["response"][:500]})

    # 过滤：只保留真正的新信息
    # TODO: 与上次扫描结果对比去重

    return findings
```

commit: `"feat: external information monitor — competitor and industry news tracking"`

---

## D-7: F1 工作记忆层

新建 `scripts/work_memory.py`：

```python
"""工作记忆 — 记录对话中的关键结论和决策"""
import json, re, time
from pathlib import Path

MEMORY_DIR = Path(__file__).parent.parent / ".ai-state" / "work_memory"
MEMORY_DIR.mkdir(parents=True, exist_ok=True)

def extract_decisions_from_text(text: str) -> list:
    """从对话文本中提取决策信号"""
    signals = [
        r"决定了[：:]\s*(.+)",
        r"结论[是为：:]\s*(.+)",
        r"否决了?\s*(.+)",
        r"确认[：:]\s*(.+)",
        r"选择了?\s*(.+?)(?:方案|路线)",
    ]
    decisions = []
    for pattern in signals:
        for match in re.finditer(pattern, text):
            decisions.append({
                "decision": match.group(1).strip()[:200],
                "timestamp": time.strftime('%Y-%m-%d %H:%M'),
                "source": "feishu_conversation"
            })
    return decisions

def save_work_memory(decisions: list):
    """保存工作记忆"""
    if not decisions:
        return
    log_file = MEMORY_DIR / "decisions.jsonl"
    with open(log_file, 'a', encoding='utf-8') as f:
        for d in decisions:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")

def get_relevant_memories(query: str, limit: int = 5) -> str:
    """检索与当前问题相关的工作记忆"""
    log_file = MEMORY_DIR / "decisions.jsonl"
    if not log_file.exists():
        return ""
    keywords = set(re.findall(r'[\u4e00-\u9fff]{2,4}|[A-Z][a-z]+', query))
    results = []
    for line in log_file.read_text(encoding='utf-8').strip().split('\n'):
        try:
            d = json.loads(line)
            overlap = sum(1 for kw in keywords if kw in d.get("decision", ""))
            if overlap > 0:
                results.append((overlap, d))
        except:
            continue
    results.sort(reverse=True)
    if not results:
        return ""
    text = "\n## 相关工作记忆\n"
    for _, d in results[:limit]:
        text += f"- [{d.get('timestamp', '')}] {d['decision']}\n"
    return text
```

commit: `"feat: work memory layer — capture decisions from conversations for future reference"`

---

## D-8: F4 知识可视化

新建 `scripts/kb_visualizer.py`：

```python
"""知识库可视化 — 生成 HTML 知识地图"""
import json
from pathlib import Path
from collections import Counter

def generate_knowledge_map() -> str:
    """生成 KB 知识地图 HTML"""
    from src.tools.knowledge_base import KB_ROOT

    # 收集数据
    domain_counts = Counter()
    entity_counts = Counter()
    confidence_counts = Counter()

    for f in KB_ROOT.rglob("*.json"):
        try:
            data = json.loads(f.read_text(encoding='utf-8'))
            domain_counts[data.get("domain", "unknown")] += 1
            confidence_counts[data.get("confidence", "unknown")] += 1
            # 提取实体
            title = data.get("title", "")
            for entity in ["歌尔", "立讯", "Cardo", "Sena", "OLED", "MicroLED", "Qualcomm", "JBD"]:
                if entity.lower() in title.lower():
                    entity_counts[entity] += 1
        except:
            continue

    # 生成简单 HTML（用内联 CSS，不依赖外部库）
    html = _generate_map_html(domain_counts, entity_counts, confidence_counts)

    output_path = KB_ROOT.parent / "exports" / "knowledge_map.html"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding='utf-8')

    return str(output_path)


def _generate_map_html(domains: Counter, entities: Counter, confidence: Counter) -> str:
    """生成知识地图 HTML"""
    # CC 自行实现：用简单的 HTML + CSS 气泡图或表格
    # 不需要 D3.js，用纯 CSS 的 flexbox 气泡即可
    pass  # CC 实现
```

commit: `"feat: knowledge map visualization — HTML bubble chart of KB distribution"`

---

## D-9: F5 否决记录

新建 `.ai-state/decision_log.jsonl`（空文件）。

新建 `scripts/decision_logger.py`：

```python
"""决策与否决记录"""
import json, time
from pathlib import Path

LOG_PATH = Path(__file__).parent.parent / ".ai-state" / "decision_log.jsonl"

def log_decision(decision_id: str, decision_type: str, content: str, reason: str):
    """记录决策或否决
    decision_type: "decided" / "rejected" / "deferred"
    """
    entry = {
        "decision_id": decision_id,
        "type": decision_type,
        "content": content,
        "reason": reason,
        "timestamp": time.strftime('%Y-%m-%d %H:%M'),
    }
    with open(LOG_PATH, 'a', encoding='utf-8') as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

def get_rejections(query: str = "") -> list:
    """获取否决记录"""
    if not LOG_PATH.exists():
        return []
    results = []
    for line in LOG_PATH.read_text(encoding='utf-8').strip().split('\n'):
        try:
            e = json.loads(line)
            if e.get("type") == "rejected":
                if not query or query.lower() in e.get("content", "").lower():
                    results.append(e)
        except:
            continue
    return results
```

commit: `"feat: decision and rejection logger — track why options were rejected"`

---

## D-10: G1 Harness 成熟度

新建 `scripts/harness_assessment.py`：

```python
"""Harness 成熟度自评 — 六维雷达"""
import json, time
from pathlib import Path

HARNESS_PATH = Path(__file__).parent.parent / ".ai-state" / "harness_history.jsonl"

DIMENSIONS = [
    "Tool Integration",
    "Memory & State",
    "Context Engineering",
    "Planning & Decomposition",
    "Verification & Guardrails",
    "Lifecycle Management",
]

def assess_maturity() -> dict:
    """自动评估六维成熟度（每维 1-5 分）"""
    scores = {}

    # Tool Integration: 模型数量 + 降级链 + 元能力工具数
    # Memory & State: KB 条目数 + 工作记忆 + checkpoint
    # Context Engineering: Agent prompt 管理 + 决策树 + 专家框架
    # Planning & Decomposition: 五层管道 + 任务去重 + 深钻模式
    # Verification & Guardrails: Critic 分级 + 校准 + 安全禁止列表
    # Lifecycle Management: KB 治理 + 软删除 + watchdog + 用量追踪

    # CC 自行实现各维度的评分逻辑（检查对应功能是否存在和完善度）
    pass  # CC 实现

    return {"scores": scores, "timestamp": time.strftime('%Y-%m-%d %H:%M')}
```

commit: `"feat: Harness maturity self-assessment — six-dimension radar"`

---

## D-11: G5 产品愿景

新建 `scripts/product_vision.py`：

```python
"""产品愿景生成 — 基于数据的创造性产品描述"""

def generate_vision(gateway, kb_context: str = "") -> str:
    """生成产品愿景描述"""
    prompt = (
        f"你是一个极具想象力的产品设计师。\n\n"
        f"基于以下知识，描绘智能骑行头盔的使用场景。\n"
        f"不是列功能，而是讲故事——让读者'看到'用户在用这个产品。\n\n"
        f"{kb_context[:3000]}\n\n"
        f"场景 1: 用户第一次开箱并戴上头盔的前 60 秒\n"
        f"场景 2: 周末三个骑友组队穿越山路\n"
        f"场景 3: 暴雨中的长途骑行\n"
        f"场景 4: 深夜独骑回家\n\n"
        f"每个场景 150-200 字，有画面感，有情感，有细节。"
    )
    result = gateway.call("gpt_5_4", prompt,
                          "你是产品愿景设计师，用文字创造画面感。不要分析，只要想象。",
                          "creative_writing")
    return result.get("response", "") if result.get("success") else "生成失败"
```

commit: `"feat: product vision generator — creative scenario descriptions from data"`

---

## D-12: H2 用户声音采集

新建 `scripts/user_voice.py`：

```python
"""用户声音采集 — 从骑行社区提取用户痛点和需求"""

def collect_user_voice(gateway, progress_callback=None) -> str:
    """搜索骑行社区，提取用户声音"""
    queries = [
        "骑行头盔 吐槽 不满 小红书",
        "智能头盔 用户评价 问题 B站",
        "Cardo Sena 用户体验 知乎",
        "摩托车骑行 最烦的事 论坛",
        "motorcycle helmet complaint user review",
    ]
    # 用豆包搜索中文社区
    # 提取痛点/需求/吐槽
    # 分类汇总
    pass  # CC 实现
```

commit: `"feat: user voice collector — extract rider pain points from Chinese social platforms"`

---

## D-13: I5 轻量 CRM

创建 `.ai-state/contacts.yaml`（初始化为空结构）：

```yaml
contacts: []
communications: []
```

新建 `scripts/crm_lite.py`：

```python
"""轻量 CRM — 联系人和沟通记录管理"""
import yaml, time, re
from pathlib import Path

CRM_PATH = Path(__file__).parent.parent / ".ai-state" / "contacts.yaml"

def parse_communication(text: str) -> dict:
    """从自然语言解析沟通记录
    如: '歌尔张工，讨论了产能问题，对方承诺下周给报价'
    """
    # CC 自行实现自然语言解析逻辑
    pass

def add_communication(company: str, contact: str, content: str):
    """添加沟通记录"""
    data = yaml.safe_load(CRM_PATH.read_text(encoding='utf-8')) if CRM_PATH.exists() else {"contacts": [], "communications": []}
    data["communications"].append({
        "company": company,
        "contact": contact,
        "content": content,
        "timestamp": time.strftime('%Y-%m-%d %H:%M'),
    })
    CRM_PATH.write_text(yaml.dump(data, allow_unicode=True), encoding='utf-8')

def get_company_history(company: str) -> list:
    """获取某公司的沟通历史"""
    if not CRM_PATH.exists():
        return []
    data = yaml.safe_load(CRM_PATH.read_text(encoding='utf-8'))
    return [c for c in data.get("communications", []) if company.lower() in c.get("company", "").lower()]
```

commit: `"feat: lightweight CRM — contact and communication record management"`

---

## D-14: J5 claude.ai 同步协议

创建 `.ai-state/claude_sync/` 目录和 README：

```bash
mkdir -p .ai-state/claude_sync
```

新建 `.ai-state/claude_sync/README.md`：

```markdown
# Claude.ai 同步目录

放置 claude.ai 对话产生的 handoff 文件。
系统启动时自动扫描并处理。

文件命名: handoff_YYYYMMDD.md
```

commit: `"feat: claude.ai sync protocol — directory and convention for cross-system handoffs"`

---

## 总提交数: 14 个 commit

---

## D-15: L3 多模态知识入库

新建 `scripts/multimodal_intake.py`：

```python
"""多模态知识入库 — 图片 OCR → 结构化提取 → KB"""
import json, re
from pathlib import Path

def process_image_to_kb(image_path: str, image_text: str, gateway) -> dict:
    """从 OCR 文本中提取结构化数据并入库

    支持: 报价单、数据表、名片、白板
    """
    # 判断文档类型
    doc_type = _classify_document(image_text)

    if doc_type == "quotation":
        return _extract_quotation(image_text, gateway)
    elif doc_type == "datasheet":
        return _extract_datasheet(image_text, gateway)
    elif doc_type == "namecard":
        return _extract_namecard(image_text, gateway)
    elif doc_type == "whiteboard":
        return _extract_whiteboard(image_text, gateway)
    else:
        return {"type": "unknown", "text": image_text}


def _classify_document(text: str) -> str:
    """分类文档类型"""
    if any(kw in text for kw in ["报价", "单价", "MOQ", "交期", "quotation", "price"]):
        return "quotation"
    elif any(kw in text for kw in ["规格", "参数", "spec", "datasheet", "voltage", "current"]):
        return "datasheet"
    elif any(kw in text for kw in ["名片", "电话", "邮箱", "手机", "微信"]):
        return "namecard"
    else:
        return "whiteboard"


def _extract_quotation(text: str, gateway) -> dict:
    """从报价单提取价格/MOQ/交期"""
    result = gateway.call("gemini_2_5_flash",
        f"从以下报价单 OCR 文本中提取结构化数据:\n\n{text[:2000]}\n\n"
        f"输出 JSON: {{"
        f"\"supplier\": \"供应商名\", \"items\": ["
        f"{{\"name\": \"产品名\", \"price\": \"单价\", \"moq\": \"最小订单量\", \"lead_time\": \"交期\"}}]}}",
        task_type="data_extraction")
    if result.get("success"):
        try:
            return json.loads(re.sub(r'^```json\s*|\s*```$', '', result["response"].strip()))
        except:
            pass
    return {"type": "quotation", "raw": text[:500]}


def _extract_namecard(text: str, gateway) -> dict:
    """从名片提取联系人信息"""
    result = gateway.call("gemini_2_5_flash",
        f"从以下名片 OCR 文本中提取联系人信息:\n\n{text}\n\n"
        f"输出 JSON: {{\"name\": \"\", \"company\": \"\", \"title\": \"\", \"phone\": \"\", \"email\": \"\", \"wechat\": \"\"}}",
        task_type="data_extraction")
    if result.get("success"):
        try:
            return json.loads(re.sub(r'^```json\s*|\s*```$', '', result["response"].strip()))
        except:
            pass
    return {"type": "namecard", "raw": text}


def _extract_datasheet(text: str, gateway) -> dict:
    """从数据表提取规格参数"""
    # CC 自行实现
    return {"type": "datasheet", "raw": text[:500]}


def _extract_whiteboard(text: str, gateway) -> dict:
    """从白板照片提取要点"""
    # CC 自行实现
    return {"type": "whiteboard", "raw": text[:500]}
```

commit: `"feat: multimodal knowledge intake — OCR to structured data to KB pipeline"`

---

## 更新后总提交数: 15 个 commit

---

## D-16: M1 审美化输出

新建 `scripts/visual_report_generator.py`：

```python
"""可视化报告生成 — 从纯文本到 HTML 图表"""

def generate_comparison_chart(title: str, items: list, dimensions: list) -> str:
    """生成方案对比 HTML（含表格+雷达图）
    items: [{"name": "OLED", "cost": 85, "brightness": 3000, ...}, ...]
    dimensions: ["cost", "brightness", "supply_chain", ...]
    """
    # 用 Mermaid 或纯 HTML+CSS 生成
    # 输出到 .ai-state/exports/visual_xxx.html
    pass  # CC 自行实现


def generate_supplier_quadrant(suppliers: list) -> str:
    """生成供应商象限图 HTML
    suppliers: [{"name": "歌尔", "capability": 8, "cost": 7}, ...]
    """
    pass  # CC 自行实现
```

commit: `"feat: visual report generator — HTML charts, radar diagrams, quadrant maps"`

---

## D-17: N2 Leo 决策模型（数字孪生）

创建 `.ai-state/leo_profile.yaml`（初始化）：

```yaml
# Leo 的决策偏好画像（系统自动学习 + 手动修正）
decision_preferences:
  priority_dimensions:
    - cost         # 成本敏感度
    - time_to_market  # 上市速度
    - tech_differentiation  # 技术差异化
    - supply_chain_risk  # 供应链风险
  risk_tolerance: "moderate"  # conservative / moderate / aggressive
  info_style: "concise"  # concise / detailed / data_heavy
  thinking_style: "big_picture_first"  # big_picture_first / detail_first
  pet_peeves:
    - "没有数据支撑的结论"
    - "过长的报告"
    - "模糊的建议（'可以考虑'而不是'建议选A因为XYZ'）"

# 以下由系统从历史评价中自动提取，Leo 可修正
auto_learned:
  avg_rating_by_type: {}
  preferred_report_length: 1500  # 字
  topics_most_engaged: []
  last_updated: null
```

新建 `scripts/user_profile_learner.py`：

```python
"""从历史对话和评价中学习 Leo 的偏好"""

def learn_from_ratings():
    """从 A/B/C/D 评价中提取偏好模式"""
    pass  # CC 实现

def apply_profile_to_output(text: str, profile: dict) -> str:
    """根据 profile 调整输出格式和重点"""
    pass  # CC 实现
```

commit: `"feat: user decision profile — digital twin of Leo's preferences and thinking style"`

---

## D-18: N3 决策护栏与代理行动

创建 `.ai-state/decision_guardrails.yaml`：

```yaml
# 决策护栏 — Leo 不在时的自动响应规则
guardrails:
  - id: "goertek_risk"
    trigger: "歌尔 AND (产能风险 OR 产线变动 OR 被包下)"
    action: "auto_add_task"
    task:
      title: "[护栏触发] 替代供应商紧急评估"
      goal: "深入评估立讯精密和舜宇光学作为歌尔的备选 JDM 合作伙伴"
      priority: 1
    notify: true

  - id: "competitor_hud"
    trigger: "竞品 AND (HUD 头盔 OR 智能头盔) AND (发布 OR 上市 OR 新品)"
    action: "auto_deep_drill"
    topic: "竞品新品分析"
    notify: true

  - id: "patent_risk"
    trigger: "专利 AND (侵权 OR 诉讼 OR 骑行头盔)"
    action: "notify_only"
    notify: true
    priority: "urgent"
```

新建 `scripts/guardrail_engine.py`：

```python
"""决策护栏引擎 — 检测触发条件并执行预设行动"""

def check_guardrails(text: str, source: str = "deep_research"):
    """检查文本是否触发任何护栏规则"""
    pass  # CC 实现：加载 yaml，逐条正则匹配，触发则执行 action
```

在深度研究报告和外部监控结果中调用 `check_guardrails()`。

commit: `"feat: decision guardrails — autonomous pre-authorized responses when Leo is away"`

---

## 最终总提交数: 18 个 commit

---

## D-19: O5 信任指数

新建 `scripts/trust_tracker.py`：

```python
"""信任指数 — 按领域追踪系统可信度"""
import json, time
from pathlib import Path
from collections import defaultdict

TRUST_PATH = Path(__file__).parent.parent / ".ai-state" / "trust_index.json"

DOMAINS = ["光学方案", "成本估算", "供应商评价", "技术参数", "市场分析", "用户洞察", "竞品分析"]

def load_trust() -> dict:
    if TRUST_PATH.exists():
        try: return json.loads(TRUST_PATH.read_text(encoding='utf-8'))
        except: pass
    return {d: {"score": 0.5, "samples": 0, "correct": 0} for d in DOMAINS}

def update_trust(domain: str, is_accurate: bool):
    """更新某领域的信任分数"""
    trust = load_trust()
    if domain not in trust:
        trust[domain] = {"score": 0.5, "samples": 0, "correct": 0}
    t = trust[domain]
    t["samples"] += 1
    if is_accurate:
        t["correct"] += 1
    t["score"] = t["correct"] / max(t["samples"], 1)
    TRUST_PATH.write_text(json.dumps(trust, ensure_ascii=False, indent=2), encoding='utf-8')

def get_trust_report() -> str:
    trust = load_trust()
    lines = ["🎯 信任指数\n"]
    for domain, t in sorted(trust.items(), key=lambda x: x[1]["score"], reverse=True):
        bar = "█" * int(t["score"] * 10) + "░" * (10 - int(t["score"] * 10))
        lines.append(f"  {bar} {t['score']:.0%} {domain} ({t['samples']} 样本)")
    return "\n".join(lines)

def should_seek_confirmation(domain: str) -> bool:
    """信任度低于 60% 的领域需要寻求确认"""
    trust = load_trust()
    return trust.get(domain, {}).get("score", 0.5) < 0.6
```

commit: `"feat: trust index — domain-specific confidence tracking with adaptive autonomy"`

---

## 最终总提交数: 19 个 commit

---

## D-20: P5 HUD Demo 原型生成

新建 `scripts/demo_generator.py`：

```python
"""Demo 原型生成器 — 从设计规范生成可交互 HTML"""

def generate_hud_demo(design_spec: str, scenario_script: str, gateway) -> str:
    """生成 HUD Demo HTML

    用 gpt-5.4 生成全屏 HTML+CSS+JS 代码：
    - 模拟骑行视角背景
    - 导航箭头动画
    - 速度数字显示
    - 来电通知弹出
    - 组队成员位置标记
    - 场景自动切换（白天→隧道→夜间）
    """
    prompt = (
        f"生成一个全屏 HTML 页面，模拟摩托车骑行头盔的 HUD 显示效果。\n\n"
        f"## 设计规范\n{design_spec[:2000]}\n\n"
        f"## 场景脚本\n{scenario_script[:2000]}\n\n"
        f"## 技术要求\n"
        f"- 单文件 HTML（内联 CSS + JS）\n"
        f"- 全屏黑色背景模拟骑行视角\n"
        f"- 半透明 HUD 元素叠加\n"
        f"- 导航箭头有渐入渐出动画\n"
        f"- 速度数字实时变化（模拟）\n"
        f"- 5 秒后模拟来电通知弹出\n"
        f"- 点击切换日间/夜间/隧道模式\n"
        f"- 适配手机浏览器全屏"
    )
    result = gateway.call("gpt_5_4", prompt,
        "你是前端工程师，生成完整的可运行 HTML 代码。", "code_generation")
    if result.get("success"):
        code = result["response"]
        # 提取 HTML 代码
        import re
        html_match = re.search(r'```html\s*([\s\S]*?)```', code)
        if html_match:
            code = html_match.group(1)
        output_path = Path(__file__).parent.parent / ".ai-state" / "exports" / "hud_demo.html"
        output_path.write_text(code, encoding='utf-8')
        return str(output_path)
    return ""
```

commit: `"feat: HUD demo prototype generator — interactive HTML HUD simulator from design spec"`

## D-21: P6 App Demo 原型生成

类似 P5，但生成移动端 React 风格的 App 原型。CC 自行实现。

commit: `"feat: App demo prototype generator — interactive mobile app mockup from PRD"`

---

## 最终总提交数: 21 个 commit

---

## D-22: R5 协作工作流

新建 `scripts/collaboration.py`：

```python
"""协作工作流 — 提交→审批→通知"""
import json, time
from pathlib import Path

SUBMISSIONS_DIR = Path(__file__).parent.parent / ".ai-state" / "submissions"
SUBMISSIONS_DIR.mkdir(parents=True, exist_ok=True)

def submit_for_review(content: str, submitter: str, reviewer: str, title: str) -> str:
    """提交分析供审批"""
    sub_id = f"sub_{int(time.time())}"
    entry = {
        "id": sub_id, "title": title, "content": content,
        "submitter": submitter, "reviewer": reviewer,
        "status": "pending", "submitted_at": time.strftime('%Y-%m-%d %H:%M'),
    }
    path = SUBMISSIONS_DIR / f"{sub_id}.json"
    path.write_text(json.dumps(entry, ensure_ascii=False, indent=2), encoding='utf-8')
    return sub_id

def approve_submission(sub_id: str, comment: str = "") -> bool:
    path = SUBMISSIONS_DIR / f"{sub_id}.json"
    if not path.exists(): return False
    data = json.loads(path.read_text(encoding='utf-8'))
    data["status"] = "approved"
    data["comment"] = comment
    data["reviewed_at"] = time.strftime('%Y-%m-%d %H:%M')
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    return True

def get_pending_submissions(reviewer: str = "") -> list:
    results = []
    for f in SUBMISSIONS_DIR.glob("sub_*.json"):
        try:
            data = json.loads(f.read_text(encoding='utf-8'))
            if data.get("status") == "pending":
                if not reviewer or reviewer in data.get("reviewer", ""):
                    results.append(data)
        except: continue
    return results
```

commit: `"feat: collaboration workflow — submit-review-approve pipeline"`

## D-23: R7 负载管理

新建 `scripts/load_manager.py`：

```python
"""负载管理 — 用量配额 + 任务队列 + 优先级调度"""
import json, time, threading
from pathlib import Path

QUOTA_PATH = Path(__file__).parent.parent / ".ai-state" / "usage_quotas.json"
TASK_QUEUE = []
_queue_lock = threading.Lock()

ROLE_QUOTAS = {
    "admin": float('inf'),
    "manager": 500,
    "engineer": 200,
    "viewer": 50,
}

def check_quota(open_id: str, role: str) -> bool:
    """检查用户今日是否还有配额"""
    # CC 自行实现日计数逻辑
    pass

def enqueue_task(task_type: str, priority: int, open_id: str, callback):
    """任务入队，按优先级排序"""
    with _queue_lock:
        TASK_QUEUE.append({"type": task_type, "priority": priority,
                           "user": open_id, "callback": callback,
                           "queued_at": time.time()})
        TASK_QUEUE.sort(key=lambda x: x["priority"])
```

commit: `"feat: load management — user quotas, task queue, priority scheduling"`

## D-24: R8 系统品牌与人设

创建 `.ai-state/brand.yaml`：

```yaml
name: "Rider"  # 系统名称，Leo 可修改
greeting: "你好！我是 Rider，你的智能研发助手。"
tone: "专业但不死板，有观点但尊重数据"
self_reference: "我"  # 自称方式
sign_off: ""  # 结尾标记（空=不加）
style_rules:
  - "回答简洁，先给结论再展开"
  - "不确定的事情直说不确定"
  - "用数据说话，避免空泛建议"
```

新建 `scripts/brand_layer.py`：

```python
"""品牌层 — 统一系统回复的语气和风格"""
import yaml
from pathlib import Path

BRAND_PATH = Path(__file__).parent.parent / ".ai-state" / "brand.yaml"

def get_brand() -> dict:
    if BRAND_PATH.exists():
        return yaml.safe_load(BRAND_PATH.read_text(encoding='utf-8'))
    return {"name": "助手", "tone": "专业"}

def apply_brand(text: str) -> str:
    """对回复文本应用品牌层（暂时只做轻量处理）"""
    brand = get_brand()
    # 未来可以做更多：统一语气、添加签名等
    return text
```

commit: `"feat: system brand and persona — consistent identity across all interactions"`

---

## 最终总提交数: 24 个 commit

---

## D-25: X1 测试套件

读取 `.ai-state/cc_exec_self_healing.md` 中的测试套件设计，新建 `scripts/test_suite.py`，实现硬测试（import/函数不崩溃）+ 软测试（LLM 判断输出质量）+ 集成测试（配置完整性）。

commit: `"feat: automated test suite — hard tests, soft tests, integration tests"`

## D-26: X2 自动修复引擎

新建 `scripts/auto_fixer.py`，实现测试失败后自动用 CC（subprocess 调用 claude CLI）分析报错、生成修复代码、应用修复、重跑测试验证。最多 3 轮。修不好的写入 `.ai-state/bug_report.md`。

commit: `"feat: auto-fixer engine — CC analyzes errors and auto-generates fixes, max 3 rounds"`

## D-27: X3 自愈编排器

新建 `scripts/self_heal.py`，串联测试套件 + 自动修复 + 通知。入口函数 `run_self_heal_cycle()`，支持飞书回调推送结果。

commit: `"feat: self-heal orchestrator — test → fix → verify → notify pipeline"`

## D-28: X4 触发机制

在 `scripts/feishu_sdk_client.py` 的启动逻辑中注册后台健康监控线程（每 6 小时跑一次 `run_self_heal_cycle()`）。深度学习结束后也自动触发一次。

注意：只在启动逻辑中追加一行线程启动调用，不修改其他逻辑。

commit: `"feat: health monitor — periodic self-heal every 6 hours + post-deep-learn trigger"`

## D-29: X5 飞书"自检"指令

这项需要在 text_router.py 中注册指令——**但轨道 B 负责 text_router**。所以本轨道只创建一个 `scripts/health_check_handler.py` 模块，轨道 B 负责在 text_router 中调用它。

如果轨道 B 已经完成，则直接在 text_router.py 中追加：

```python
if text_stripped in ("自检", "self check", "health check", "测试"):
    from scripts.self_heal import run_self_heal_cycle
    threading.Thread(target=run_self_heal_cycle, args=(send_reply, reply_target), daemon=True).start()
    return
```

commit: `"feat: self-check command + health check handler"`

---

## 最终总提交数: 29 个 commit

---

## D-25: X1 自动化测试套件

读取 `.ai-state/cc_exec_self_healing.md` 第二节的完整设计，新建 `scripts/test_suite.py`。

实现硬测试（import + 函数不崩溃）、软测试（用 gemini-2.5-flash 判断输出质量）、集成测试（配置完整性）。

commit: `"feat: automated test suite — hard tests, LLM-powered soft tests, integration tests"`

## D-26: X2 自动修复引擎

读取 `.ai-state/cc_exec_self_healing.md` 第三节的完整设计，新建 `scripts/auto_fixer.py`。

测试失败时用 `subprocess.run(["claude", "-p", ...])` 调用 CC 分析报错并生成修复代码。最多 3 轮。修不好的写入 `.ai-state/bug_report.md`。

commit: `"feat: auto-fixer — CC self-analyzes and fixes failing tests up to 3 rounds"`

## D-27: X3 自愈编排器

读取 `.ai-state/cc_exec_self_healing.md` 第五节的完整设计，新建 `scripts/self_heal.py`。

串联测试→修复→验证→通知的完整闭环。支持从命令行直接运行 `python scripts/self_heal.py`。

commit: `"feat: self-healing orchestrator — test, fix, verify, notify in one cycle"`

---

## 最终最终总提交数: 27 个 commit
