"""
@description: 结构化检查规则引擎 — Critic 评审的硬性约束层
@dependencies: json, pathlib, src.tools.knowledge_base, src.utils.model_gateway
@last_modified: 2026-03-26

Hashimoto 闭环核心：每次 Agent 犯错 → 生成检查规则 → Critic 下次强制检查 → 永不再犯同类错误

规则来源（三通道）：
  1. D 评价自动生成（handle_rating 的失败分析）
  2. 人工锚点（产品决策者的行业共识）
  3. Critic 自身发现（评审中发现的矛盾）

规则存储：知识库 lessons/ 目录，tag 含 critic_rule
规则匹配：LLM 语义匹配（Flash 模型，低成本高准确度）
"""

import json
import re
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

from src.tools.knowledge_base import KB_ROOT, add_knowledge, search_knowledge


# ============================================================
# 1. 规则数据结构
# ============================================================

def create_rule(
    check_description: str,
    trigger_context: str,
    severity: str = "must_check",
    source: str = "manual",
    source_task_id: str = "",
) -> Dict[str, Any]:
    """创建一条检查规则

    Args:
        check_description: 具体描述要检查什么（如 "mesh 方案必须对标 Cardo DMC 数据"）
        trigger_context: 什么类型的任务应该触发这条规则（如 "mesh 对讲 intercom 通讯方案"）
        severity: must_check | should_check | nice_to_have
        source: user_rating_D | user_rating_A | manual_anchor | critic_discovery
        source_task_id: 来源任务 ID（如果有）

    Returns:
        规则字典
    """
    rule_id = f"RULE_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    return {
        "rule_id": rule_id,
        "check_description": check_description,
        "trigger_context": trigger_context,
        "severity": severity,
        "source": source,
        "source_task_id": source_task_id,
        "created_at": datetime.now().isoformat(),
        "hit_count": 0,
        "last_hit": None,
    }


# ============================================================
# 2. 规则持久化（写入知识库）
# ============================================================

def add_critic_rule(
    check_description: str,
    trigger_context: str,
    severity: str = "must_check",
    source: str = "manual",
    source_task_id: str = "",
) -> Optional[str]:
    """添加一条 Critic 检查规则到知识库

    Returns:
        写入路径，或 None（去重命中）
    """
    rule = create_rule(check_description, trigger_context, severity, source, source_task_id)

    # 去重：检查是否已有相似规则
    existing = load_all_rules()
    for r in existing:
        existing_desc = r.get("content", "")
        # 简单去重：check_description 前 40 字相同视为重复
        if check_description[:40] in existing_desc:
            print(f"[CriticRules] 规则已存在，跳过: {check_description[:50]}")
            return None

    # 规则数量上限
    if len(existing) >= 50:
        print(f"[CriticRules] 规则数量已达上限 (50)，跳过新规则")
        return None

    # 写入知识库
    content = (
        f"## 检查规则\n"
        f"**规则 ID**: {rule['rule_id']}\n"
        f"**检查内容**: {check_description}\n"
        f"**触发场景**: {trigger_context}\n"
        f"**严重级别**: {severity}\n"
        f"**来源**: {source}\n"
        f"**来源任务**: {source_task_id or 'N/A'}\n"
    )

    path = add_knowledge(
        title=f"[检查规则] {check_description[:50]}",
        domain="lessons",
        content=content,
        tags=["critic_rule", f"severity_{severity}", f"source_{source}"],
        source=f"critic_rule:{source}",
        confidence="high",
        caller="critic_rule"
    )

    if path:
        print(f"[CriticRules] 新规则已入库: {rule['rule_id']} — {check_description[:60]}")
    return path


# ============================================================
# 3. 规则加载
# ============================================================

def load_all_rules() -> List[Dict[str, Any]]:
    """从知识库加载所有 critic_rule 标签的条目"""
    rules = []
    if not KB_ROOT.exists():
        return rules

    for jf in KB_ROOT.rglob("*.json"):
        try:
            data = json.loads(jf.read_text(encoding="utf-8"))
            tags = data.get("tags", [])
            if "critic_rule" in tags:
                rules.append(data)
        except Exception:
            continue

    return rules


def _parse_rule_fields(content: str) -> Dict[str, str]:
    """从规则内容中解析结构化字段"""
    fields = {}
    for line in content.split("\n"):
        line = line.strip()
        if line.startswith("**检查内容**:"):
            fields["check_description"] = line.split(":", 1)[1].strip()
        elif line.startswith("**触发场景**:"):
            fields["trigger_context"] = line.split(":", 1)[1].strip()
        elif line.startswith("**严重级别**:"):
            fields["severity"] = line.split(":", 1)[1].strip()
        elif line.startswith("**规则 ID**:"):
            fields["rule_id"] = line.split(":", 1)[1].strip()
    return fields


# ============================================================
# 4. LLM 语义匹配（Phase 1.2）
# ============================================================

def get_relevant_rules(task_description: str, gateway=None) -> List[Dict[str, Any]]:
    """用 LLM 语义匹配，找出与当前任务相关的检查规则

    Args:
        task_description: 当前任务的目标描述
        gateway: ModelGateway 实例（不传则自动获取）

    Returns:
        相关规则列表，每条包含 rule 原始数据 + relevance_score
    """
    all_rules = load_all_rules()
    if not all_rules:
        return []

    # 少于 3 条规则时全部返回，不需要 LLM 匹配
    if len(all_rules) <= 3:
        for r in all_rules:
            r["_relevance_score"] = 10  # 全部高相关
        return all_rules

    if gateway is None:
        from src.utils.model_gateway import get_model_gateway
        gateway = get_model_gateway()

    # 构建规则摘要列表
    rule_summaries = []
    for i, rule in enumerate(all_rules):
        fields = _parse_rule_fields(rule.get("content", ""))
        check = fields.get("check_description", rule.get("title", ""))
        trigger = fields.get("trigger_context", "")
        severity = fields.get("severity", "unknown")
        rule_summaries.append(
            f"[{i}] ({severity}) {check}"
            + (f" | 触发场景: {trigger}" if trigger else "")
        )

    rules_text = "\n".join(rule_summaries)

    prompt = (
        f"你是一个规则匹配引擎。下面是一组检查规则和一个任务描述。\n"
        f"判断每条规则与任务的相关性（0-10 分）。\n\n"
        f"## 任务描述\n{task_description}\n\n"
        f"## 检查规则列表\n{rules_text}\n\n"
        f"## 输出要求\n"
        f"只输出 JSON 数组，每个元素是 {{\"index\": 编号, \"score\": 0-10}}。\n"
        f"score >= 6 表示相关，应该注入评审。\n"
        f"只输出 JSON，不要有其他内容。"
    )

    # 用 Flash 模型（快+便宜）
    result = gateway.call_gemini("gemini_2_5_flash", prompt,
        "只输出 JSON 数组。", "rule_matching")

    if not result.get("success"):
        # 降级：全部返回 must_check 规则
        print("[CriticRules] LLM 匹配失败，降级返回所有 must_check 规则")
        must_rules = []
        for r in all_rules:
            fields = _parse_rule_fields(r.get("content", ""))
            if fields.get("severity") == "must_check":
                r["_relevance_score"] = 8
                must_rules.append(r)
        return must_rules

    # 解析 LLM 输出
    try:
        resp = result["response"].strip()
        resp = re.sub(r'^```json\s*', '', resp)
        resp = re.sub(r'\s*```$', '', resp)
        scores = json.loads(resp)
    except Exception as e:
        print(f"[CriticRules] JSON 解析失败: {e}，降级返回所有 must_check")
        must_rules = []
        for r in all_rules:
            fields = _parse_rule_fields(r.get("content", ""))
            if fields.get("severity") == "must_check":
                r["_relevance_score"] = 8
                must_rules.append(r)
        return must_rules

    # 筛选相关规则（score >= 6）
    relevant = []
    for item in scores:
        idx = item.get("index", -1)
        score = item.get("score", 0)
        if 0 <= idx < len(all_rules) and score >= 6:
            rule = all_rules[idx]
            rule["_relevance_score"] = score
            relevant.append(rule)

    # 按相关性排序
    relevant.sort(key=lambda x: x.get("_relevance_score", 0), reverse=True)

    print(f"[CriticRules] 匹配完成: {len(all_rules)} 条规则中 {len(relevant)} 条相关")
    return relevant


# ============================================================
# 5. 格式化为 Critic prompt 注入文本
# ============================================================

def format_rules_for_critic(rules: List[Dict[str, Any]]) -> str:
    """将规则格式化为可注入 Critic prompt 的文本

    Returns:
        格式化的规则清单文本，如果无规则返回空字符串
    """
    if not rules:
        return ""

    lines = [
        "## 必须逐项检查的规则清单",
        "以下规则来自历史经验和产品决策者的要求。你必须对每条规则给出明确的检查结论。",
        ""
    ]

    for i, rule in enumerate(rules, 1):
        fields = _parse_rule_fields(rule.get("content", ""))
        check = fields.get("check_description", rule.get("title", ""))
        severity = fields.get("severity", "unknown")
        rule_id = fields.get("rule_id", f"RULE_{i}")

        severity_icon = {
            "must_check": "🔴",
            "should_check": "🟡",
            "nice_to_have": "🟢",
        }.get(severity, "⚪")

        lines.append(f"{severity_icon} [{rule_id}] {check}")

    lines.append("")
    lines.append("对每条规则，请在评审中明确标注：")
    lines.append("  ✅ PASS: 方案符合此规则")
    lines.append("  ❌ FAIL: 方案违反此规则（必须说明具体问题）")
    lines.append("  ⚠️ UNVERIFIED: 无法确认（知识库/方案中缺少相关数据）")
    lines.append("")

    return "\n".join(lines)


# ============================================================
# 6. 辅助函数
# ============================================================

def get_rules_summary() -> str:
    """获取规则库概览（用于飞书指令展示）"""
    rules = load_all_rules()
    if not rules:
        return "📋 Critic 检查规则库为空。给研发任务打 D 评价后，系统会自动生成检查规则。"

    lines = [f"📋 Critic 检查规则库 ({len(rules)} 条)\n"]

    for rule in rules:
        fields = _parse_rule_fields(rule.get("content", ""))
        check = fields.get("check_description", rule.get("title", ""))
        severity = fields.get("severity", "unknown")
        source = rule.get("source", "")

        severity_icon = {"must_check": "🔴", "should_check": "🟡", "nice_to_have": "🟢"}.get(severity, "⚪")
        lines.append(f"{severity_icon} {check[:60]}")
        lines.append(f"   来源: {source}")

    return "\n".join(lines)
