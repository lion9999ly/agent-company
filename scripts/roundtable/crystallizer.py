"""
@description: 知识结晶器 - KB原料转化为高密度决策备忘录 + 角色分片上下文
@dependencies: model_gateway, knowledge_base, memory
@last_modified: 2026-04-06
"""
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

from src.utils.model_gateway import get_model_gateway
from src.tools.knowledge_base import search_knowledge, format_knowledge_for_prompt
from scripts.roundtable.memory import format_memos_for_context, create_decision_memo
from scripts.roundtable.roles import get_role_prompt


@dataclass
class CrystalContext:
    """知识结晶后的上下文"""
    anchor_docs: str                     # 核心锚点（所有角色共享）
    decision_memos: str                  # 已有备忘录（所有角色共享）
    distilled_facts: str                 # 提炼后的关键事实（所有角色共享）
    raw_kb_refs: List[str]               # 原始 KB 条目摘要（可查但不默认传递）
    role_slices: Dict[str, str]          # 角色专属上下文分片


class Crystallizer:
    """知识结晶器

    三步流程：
    1. 读取核心锚点文档 + 已有决策备忘录
    2. 从 KB 搜索相关条目并提炼
    3. 按角色分片上下文
    """

    def __init__(self, gw=None, kb=None):
        self.gw = gw or get_model_gateway()
        self.kb = kb  # KB 模块直接使用 search_knowledge 函数

    async def prepare_context(self, task) -> CrystalContext:
        """准备上下文

        Args:
            task: TaskSpec 对象

        Returns:
            CrystalContext 对象
        """
        # 1. 读取核心锚点文档
        anchor_docs = self._load_anchor_docs(task.input_docs)

        # 2. 读取已有决策备忘录
        decision_memos = format_memos_for_context()

        # 3. 从 KB 搜索相关条目
        kb_entries = []
        for query in task.kb_search_queries:
            entries = search_knowledge(query, limit=3)
            kb_entries.extend(entries)

        # 4. 用 gpt_5_4 提炼 KB 条目为关键事实摘要
        distilled_facts = await self._distill_kb_facts(kb_entries)

        # 5. 原始 KB 条目摘要（用于追溯）
        raw_kb_refs = [e.get("content", "")[:200] for e in kb_entries[:5]]

        # 6. 按角色分片上下文
        role_slices = self._slice_by_role(task, anchor_docs, distilled_facts, kb_entries)

        return CrystalContext(
            anchor_docs=anchor_docs,
            decision_memos=decision_memos,
            distilled_facts=distilled_facts,
            raw_kb_refs=raw_kb_refs,
            role_slices=role_slices,
        )

    def _load_anchor_docs(self, input_docs: List[str]) -> str:
        """加载核心锚点文档"""
        if not input_docs:
            # 默认锚点文档
            default_anchors = [
                ".ai-state/product_anchor.md",
                ".ai-state/founder_mindset.md",
            ]
            input_docs = default_anchors

        contents = []
        for doc_path in input_docs:
            path = Path(doc_path)
            if path.exists():
                content = path.read_text(encoding="utf-8")
                # 截取关键部分（前 1000 字）
                contents.append(f"### {path.stem}\n{content[:1000]}")

        if not contents:
            return ""

        return "## 核心锚点文档\n" + "\n\n".join(contents)

    async def _distill_kb_facts(self, kb_entries: List[Dict]) -> str:
        """用模型提炼 KB 条目为关键事实摘要"""

        if not kb_entries:
            return ""

        # 格式化 KB 条目
        kb_text = format_knowledge_for_prompt(kb_entries)

        # 用 gpt_5_4 提炼
        prompt = f"""请将以下知识库条目提炼为关键事实摘要（约 500 字）。
只保留与产品决策直接相关的事实，去除冗余和推测性内容。
保持置信度标注格式。

{kb_text}"""

        result = self.gw.call_with_fallback(
            primary="gpt_5_4",
            fallback="gpt_4o_norway",
            prompt=prompt,
            system_prompt="你是知识提炼专家，专注于提取对产品决策有直接价值的信息。",
            task_type="refine",
        )

        if result.get("success"):
            return result.get("response", "")[:800]
        return kb_text[:800]  # 失败时返回截断的原文本

    def _slice_by_role(self, task, anchor_docs: str, distilled_facts: str,
                       kb_entries: List[Dict]) -> Dict[str, str]:
        """按角色分片上下文

        分片逻辑：
        - CMO：用户画像 + 竞品数据 + 产品锚点中的用户需求部分
        - CTO：技术约束 + 供应商数据 + 产品锚点中的技术选型部分
        - CDO：设计原则 + 视觉参考 + 产品锚点中的形态/审美部分
        - Critic：验收标准 + 所有角色的分片摘要

        如果无法自动分片，退化为所有角色收到相同的提炼版上下文。
        """
        role_slices = {}
        all_roles = [task.proposer] + task.reviewers + [task.critic, "Echo"]

        # 基础共享内容
        shared_base = f"{anchor_docs}\n\n{distilled_facts}"

        for role in all_roles:
            # 获取角色议题专属 prompt
            role_prompt = task.role_prompts.get(role, "")
            full_prompt = get_role_prompt(role, role_prompt)

            # 根据角色类型定制上下文
            role_context = self._get_role_specific_context(role, kb_entries, task)

            # 组合：共享内容 + 角色定制内容 + 角色 prompt
            if role_context:
                role_slices[role] = f"{shared_base}\n\n{role_context}\n\n---\n\n{full_prompt}"
            else:
                role_slices[role] = f"{shared_base}\n\n---\n\n{full_prompt}"

        return role_slices

    def _get_role_specific_context(self, role: str, kb_entries: List[Dict],
                                    task) -> str:
        """获取角色特定的上下文片段"""
        role_keywords = {
            "CMO": ["用户", "市场", "竞品", "需求", "骑手", "体验"],
            "CTO": ["技术", "供应商", "芯片", "实现", "可行性", "成本"],
            "CDO": ["设计", "视觉", "布局", "交互", "形态", "审美"],
            "Critic": [],  # Critic 接收完整摘要
            "Echo": [],    # Echo 接收完整摘要
        }

        keywords = role_keywords.get(role, [])
        if not keywords:
            return ""

        # 从 KB 条目中筛选相关内容
        relevant_content = []
        for entry in kb_entries:
            content = entry.get("content", "")
            title = entry.get("title", "")
            # 关键词匹配
            if any(kw in content.lower() or kw in title.lower() for kw in keywords):
                relevant_content.append(f"- [{entry.get('confidence', 'medium')}] {title}: {content[:200]}")

        if relevant_content:
            return f"## {role} 专属参考\n" + "\n".join(relevant_content[:5])

        return ""

    async def crystallize_learnings(self, task, roundtable_output):
        """圆桌结束后，将讨论中产生的新结论写回决策备忘录

        Args:
            task: TaskSpec 对象
            roundtable_output: RoundtableResult 对象
        """
        # 提取达成共识的判断
        consensus_claims = self._extract_consensus_claims(roundtable_output)

        if not consensus_claims:
            return

        # 创建或更新决策备忘录
        conclusion = roundtable_output.executive_summary[:500]
        supporting = [c.text for c in consensus_claims]

        create_decision_memo(
            topic=task.topic,
            conclusion=conclusion,
            supporting_claims=supporting,
            status="已确认",
        )

    def _extract_consensus_claims(self, roundtable_output) -> List:
        """从圆桌输出中提取达成共识的判断"""
        from scripts.roundtable.confidence import extract_all_claims, Claim

        # 从最终方案中提取高置信声明
        claims = []
        final_proposal = roundtable_output.final_proposal

        # 提取带置信度标注的声明
        extracted = extract_all_claims(final_proposal, "Echo")
        # 只保留高置信度和中置信度的事实/判断
        for claim in extracted:
            if claim.claim_type in ["事实", "判断"] and claim.confidence in ["高", "中"]:
                claims.append(claim)

        return claims