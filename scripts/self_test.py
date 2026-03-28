# -*- coding: utf-8 -*-
"""
@description: Knowledge base self-test engine - generate questions, answer, score, find weak areas, trigger deep dive
@dependencies: src.utils.model_gateway, src.tools.knowledge_base
@last_modified: 2026-03-28
"""
import json
import re
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.model_gateway import get_model_gateway
from src.tools.knowledge_base import search_knowledge, format_knowledge_for_prompt, KB_ROOT


def generate_test_questions(topics: list, gateway, count=10) -> list:
    """Generate test questions based on recently learned topics"""

    titles = [t if isinstance(t, str) else t.get("title", "") for t in topics[:30]]

    prompt = (
        f"Below are recently learned knowledge topics for smart motorcycle helmet project:\n"
        + "\n".join(f"- {t}" for t in titles) + "\n\n"
        f"Please generate {count} test questions to verify if the knowledge base has truly captured useful information.\n\n"
        f"Requirements:\n"
        f"1. Each question must require specific data to answer (models, parameters, prices, quantities, dates)\n"
        f"2. Do NOT ask definition questions ('What is XX'), ask comparison/selection/decision questions\n"
        f"3. Cover different domains (hardware/certification/cost/user/competitor)\n"
        f"4. Difficulty: questions a professional PM or engineer would ask daily\n\n"
        f"Output JSON array, each element:\n"
        f'{{"question":"question text","domain":"domain","expected_data":"expected data type"}}\n\n'
        f"Only output JSON."
    )

    result = gateway.call_azure_openai("cpo", prompt,
        "Generate professional test questions. Only output JSON.", "self_test_gen")

    if result.get("success"):
        match = re.search(r'\[[\s\S]*\]', result["response"])
        if match:
            try:
                return json.loads(match.group())
            except:
                pass
    return []


def answer_question_from_kb(question: str, gateway) -> dict:
    """Answer question using knowledge base, and evaluate answer quality"""

    # Search knowledge base
    kb_entries = search_knowledge(question, limit=8)
    kb_context = format_knowledge_for_prompt(kb_entries) if kb_entries else ""

    if not kb_context or len(kb_context) < 100:
        return {
            "answer": "",
            "kb_hit": False,
            "score": 0,
            "reason": "No relevant content in knowledge base"
        }

    # Answer using knowledge base
    answer_prompt = (
        f"Answer the question based on the following knowledge base content.\n"
        f"Must cite specific data (models, parameters, prices).\n"
        f"If knowledge base has no relevant data, clearly say 'No relevant data found in knowledge base'.\n"
        f"Do not fabricate data.\n\n"
        f"Knowledge base content:\n{kb_context[:4000]}\n\n"
        f"Question: {question}\n\n"
        f"Answer (within 300 words):"
    )

    result = gateway.call_azure_openai("cpo", answer_prompt,
        "Answer based on knowledge base, cite specific data.", "self_test_answer")

    answer = result.get("response", "") if result.get("success") else ""

    # Score the answer
    score, reason = _score_answer(answer, question)

    return {
        "answer": answer[:500],
        "kb_hit": len(kb_context) > 200,
        "score": score,
        "reason": reason
    }


def _score_answer(answer: str, question: str) -> tuple:
    """Score: 0-10"""

    if not answer or len(answer) < 50:
        return 0, "No valid answer"

    if "not found" in answer.lower() or "no relevant" in answer.lower() or "not available" in answer.lower():
        return 1, "Knowledge base missing"

    # Check for specific data
    has_number = bool(re.search(r'\d+\.?\d*\s*(mm|cm|g|kg|mAh|W|V|Hz|dB|USD|\$|%|nits|GHz|MB)', answer))
    has_model = bool(re.search(r'[A-Z]{2,}\d{2,}|IMX\d|QCC\d|BES\d', answer))
    has_brand = bool(re.search(r'(Qualcomm|Sony|Bosch|Sena|Cardo|Forcite|LIVALL|GoPro|Insta360)', answer))
    has_comparison = bool(re.search(r'(vs|compared|better|worse|higher|lower)', answer, re.IGNORECASE))

    score = 3  # Base score (has answer)
    if has_number:
        score += 2
    if has_model:
        score += 2
    if has_brand:
        score += 1
    if has_comparison:
        score += 1
    if len(answer) > 200:
        score += 1

    score = min(score, 10)

    reasons = []
    if not has_number:
        reasons.append("missing numbers")
    if not has_model:
        reasons.append("missing model")
    if not has_brand:
        reasons.append("missing brand")

    reason = ", ".join(reasons) if reasons else "data sufficient"
    return score, reason


def run_self_test(topics=None, count=10, notify_func=None) -> dict:
    """Execute a self-test round, return results and weak areas"""

    gateway = get_model_gateway()

    # If no topics provided, extract from recent KB entries
    if not topics:
        recent = []
        for f in sorted(KB_ROOT.rglob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)[:30]:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                recent.append(data.get("title", ""))
            except:
                continue
        topics = recent

    print(f"\n[SelfTest] Generating {count} test questions...")
    questions = generate_test_questions(topics, gateway, count)

    if not questions:
        print("[SelfTest] Failed to generate test questions")
        return {"score": 0, "weak_areas": [], "questions": []}

    print(f"[SelfTest] Starting to answer ({len(questions)} questions)...")
    results = []
    total_score = 0
    weak_areas = []

    for i, q in enumerate(questions, 1):
        question = q.get("question", "")
        domain = q.get("domain", "")

        answer_result = answer_question_from_kb(question, gateway)
        score = answer_result["score"]
        total_score += score

        icon = "OK" if score >= 7 else "WARN" if score >= 4 else "FAIL"
        print(f"  [{icon}] [{i}/{len(questions)}] {score}/10 | {question[:50]}... -- {answer_result['reason']}")

        results.append({
            "question": question,
            "domain": domain,
            "score": score,
            "reason": answer_result["reason"],
            "answer_preview": answer_result["answer"][:200]
        })

        # Low score -> weak area
        if score < 5:
            weak_areas.append({
                "question": question,
                "domain": domain,
                "score": score,
                "reason": answer_result["reason"],
                "suggested_searches": [
                    f"{question} specific data parameters models",
                    f"{domain} specifications comparison 2025 2026",
                ]
            })

    avg_score = round(total_score / len(questions), 1) if questions else 0
    pass_rate = round(sum(1 for r in results if r["score"] >= 7) / len(results) * 100, 1) if results else 0

    summary = (
        f"\n[SelfTest] Self-test complete\n"
        f"  Average score: {avg_score}/10\n"
        f"  Pass rate (>=7): {pass_rate}%\n"
        f"  Weak areas: {len(weak_areas)}\n"
    )
    print(summary)

    if notify_func:
        try:
            notify_func(
                f"Knowledge base self-test complete\n"
                f"Average: {avg_score}/10 | Pass rate: {pass_rate}%\n"
                f"Weak areas: {len(weak_areas)}"
            )
        except:
            pass

    # Save self-test report
    report = {
        "timestamp": datetime.now().isoformat(),
        "avg_score": avg_score,
        "pass_rate": pass_rate,
        "total_questions": len(questions),
        "weak_count": len(weak_areas),
        "results": results,
        "weak_areas": weak_areas
    }

    report_dir = Path(__file__).parent.parent / ".ai-state" / "self_tests"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"test_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "avg_score": avg_score,
        "pass_rate": pass_rate,
        "weak_areas": weak_areas,
        "results": results
    }


def auto_deep_dive_weak_areas(weak_areas: list, notify_func=None) -> dict:
    """Automatically deep dive into weak areas"""
    if not weak_areas:
        print("[AutoDeepDive] No weak areas to deep dive")
        return {"added": 0}

    from src.tools.tool_registry import get_tool_registry
    gateway = get_model_gateway()
    registry = get_tool_registry()

    added = 0

    for i, weak in enumerate(weak_areas, 1):
        question = weak["question"]
        domain = weak.get("domain", "components")
        searches = weak.get("suggested_searches", [question])

        print(f"\n[AutoDeepDive] [{i}/{len(weak_areas)}] Deep diving: {question[:50]}...")

        # Multi-round search
        search_data = ""
        for q in searches[:3]:
            result = registry.call("deep_research", q)
            if result.get("success") and len(result.get("data", "")) > 200:
                search_data += f"\n---\n{result['data'][:3000]}"

        if len(search_data) < 500:
            print(f"  SKIP - Insufficient search data")
            continue

        # Refine (answer the original question specifically)
        refine_prompt = (
            f"The following search results are to answer this question:\n{question}\n\n"
            f"Please output a detailed knowledge entry based on search results.\n"
            f"Must include specific data (models, parameters, prices, brand names).\n"
            f"If not found, mark 'not found'.\n"
            f"Output 800-1500 words.\n\n"
            f"Search results:\n{search_data[:6000]}"
        )

        result = gateway.call_azure_openai("cpo", refine_prompt,
            "Output data-supported knowledge entry.", "auto_deep_dive")

        if result.get("success") and len(result.get("response", "")) > 300:
            from src.tools.knowledge_base import add_knowledge
            add_knowledge(
                title=f"[SelfTest DeepDive] {question[:60]}",
                domain=domain,
                content=result["response"][:2000],
                tags=["self_test_dive", "auto_evolution"],
                source="self_test_auto_dive",
                confidence="high"
            )
            added += 1
            print(f"  OK - Added to KB ({len(result['response'])} chars)")
        else:
            print(f"  FAIL - Refinement failed")

    print(f"\n[AutoDeepDive] Complete: Deep dived {len(weak_areas)}, added {added}")

    if notify_func:
        try:
            notify_func(f"Auto deep dive complete: {added}/{len(weak_areas)} weak areas strengthened")
        except:
            pass

    return {"added": added}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Knowledge base self-test")
    parser.add_argument("--count", type=int, default=10, help="Number of test questions")
    parser.add_argument("--deep-dive", action="store_true", help="Auto deep dive weak areas")
    args = parser.parse_args()

    result = run_self_test(count=args.count)
    print(f"\nResult: avg={result['avg_score']}/10, weak={len(result['weak_areas'])}")

    if args.deep_dive and result["weak_areas"]:
        auto_deep_dive_weak_areas(result["weak_areas"])