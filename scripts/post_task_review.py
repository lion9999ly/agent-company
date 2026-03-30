"""
@description: 任务后评审脚本 - 自动触发多模型交叉评审，生成改进项
@dependencies: requests, yaml
@last_modified: 2026-03-17

使用方法:
    python scripts/post_task_review.py --task <task_id> --files <file1> <file2>
    python scripts/post_task_review.py --task looki_l1_analysis --files .ai-state/competitive_analysis/looki_l1_report.md
"""

import argparse
import json
import sys
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import requests
    import yaml
except ImportError:
    print("请安装依赖: pip install requests pyyaml")
    sys.exit(1)


class PostTaskReviewer:
    """任务后评审器 - 多模型交叉评审"""

    # 评审模型配置
    REVIEWERS = {
        "gemini_flash": {
            "provider": "google",
            "model": "gemini-2.5-flash",
            "api_key_env": "GOOGLE_API_KEY",
            "role": "主评审"
        },
        "gpt4o": {
            "provider": "azure_openai",
            "model": "gpt-4o",
            "api_key_env": "AZURE_OPENAI_KEY",
            "role": "交叉评审"
        },
        "qwen": {
            "provider": "alibaba",
            "model": "qwen-max",
            "api_key_env": "DASHSCOPE_API_KEY",
            "role": "中文专项"
        }
    }

    # 评审提示词模板
    REVIEW_PROMPT_TEMPLATE = """你是CPO_Critic评审专家，隶属于虚拟研发中心。请对以下任务成果进行交叉评审。

## 任务信息
- 任务ID: {task_id}
- 评审文件: {files}
- 评审维度: {dimensions}

## 评审标准
1. **维度覆盖度**: 是否覆盖所有规定维度？缺失维度是否合理标注？
2. **数据质量**: 数据来源是否标注？置信度等级是否合理？
3. **分析方法**: 分析逻辑是否严谨？结论是否有数据支撑？
4. **可操作性**: 采集指引是否清晰？下一步行动是否明确？

## 输出要求
请直接输出JSON格式评审结果（不要markdown代码块）：
{{
  "overall_score": <1-10分>,
  "pass": <true/false>,
  "strengths": ["优点列表"],
  "weaknesses": ["不足列表"],
  "suggestions": ["改进建议"],
  "critical_missing": ["关键缺失项"]
}}

注意: pass为true需overall_score>=8且critical_missing为空"""

    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or Path(__file__).parent.parent / "src" / "config" / "model_registry.yaml"
        self.review_logs_path = Path(__file__).parent.parent / ".ai-state" / "review_logs.jsonl"
        self.improvement_path = Path(__file__).parent.parent / ".ai-state" / "improvement_backlog.md"

    def get_api_key(self, env_name: str) -> Optional[str]:
        """获取API密钥"""
        # 优先从环境变量获取
        key = os.getenv(env_name)
        if key:
            return key

        # 尝试从配置文件获取
        if self.config_path.exists():
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                # 查找对应的API key
                for model_config in config.get('model_registry', {}).values():
                    if model_config.get('api_key') and not model_config.get('api_key_env'):
                        return model_config.get('api_key')

        return None

    def review_with_gemini(self, prompt: str) -> Dict[str, Any]:
        """使用Gemini进行评审"""
        api_key = self.get_api_key("GEMINI_API_KEY")
        if not api_key:
            return {"success": False, "error": "GEMINI_API_KEY 环境变量未设置"}

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"

        data = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.1, "maxOutputTokens": 1024}
        }

        try:
            response = requests.post(url, json=data, timeout=60)
            result = response.json()

            if 'candidates' in result:
                text = result['candidates'][0]['content']['parts'][0]['text']
                # 清理markdown
                text = text.replace('```json', '').replace('```', '').strip()
                return json.loads(text)
            else:
                return {"error": str(result), "overall_score": 0, "pass": False}
        except Exception as e:
            return {"error": str(e), "overall_score": 0, "pass": False}

    def review_with_gpt4o(self, prompt: str) -> Dict[str, Any]:
        """使用GPT-4o进行评审"""
        api_key = self.get_api_key("AZURE_OPENAI_KEY")
        if not api_key:
            api_key = "FeFNVOGsq4dkb3RIkbwgQH9mGWUp3Nobee6SUWn4plrJ9t2OTjl5JQQJ99BGACHYHv6XJ3w3AAAAACOGQ6xd"

        endpoint = "https://ai-ceoofficeinternai563252701791.services.ai.azure.com"
        url = f"{endpoint}/openai/deployments/gpt-4o/chat/completions?api-version=2024-02-15-preview"

        headers = {"Content-Type": "application/json", "api-key": api_key}
        data = {
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 1024
        }

        try:
            response = requests.post(url, headers=headers, json=data, timeout=60)
            result = response.json()

            if 'choices' in result:
                text = result['choices'][0]['message']['content']
                text = text.replace('```json', '').replace('```', '').strip()
                return json.loads(text)
            else:
                return {"error": str(result), "overall_score": 0, "pass": False}
        except Exception as e:
            return {"error": str(e), "overall_score": 0, "pass": False}

    def run_review(self, task_id: str, files: List[str], dimensions: List[str] = None) -> Dict[str, Any]:
        """执行多模型交叉评审"""
        if dimensions is None:
            dimensions = ["维度覆盖度", "数据质量", "分析方法", "可操作性"]

        prompt = self.REVIEW_PROMPT_TEMPLATE.format(
            task_id=task_id,
            files=", ".join(files),
            dimensions=", ".join(dimensions)
        )

        results = {
            "review_id": f"review_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "task_id": task_id,
            "timestamp": datetime.now().isoformat(),
            "reviewers": [],
            "aggregated_score": 0,
            "final_verdict": "BLOCK",
            "improvements": []
        }

        # Gemini评审
        print("[1/2] Gemini 2.5 Flash 评审中...")
        gemini_result = self.review_with_gemini(prompt)
        gemini_result["reviewer_model"] = "Gemini 2.5 Flash"
        gemini_result["role"] = "主评审"
        results["reviewers"].append(gemini_result)
        print(f"  评分: {gemini_result.get('overall_score', 'N/A')}")
        print(f"  结论: {'PASS' if gemini_result.get('pass') else 'BLOCK'}")

        # GPT-4o评审
        print("[2/2] GPT-4o 交叉评审中...")
        gpt4o_result = self.review_with_gpt4o(prompt)
        gpt4o_result["reviewer_model"] = "GPT-4o (Azure)"
        gpt4o_result["role"] = "交叉评审"
        results["reviewers"].append(gpt4o_result)
        print(f"  评分: {gpt4o_result.get('overall_score', 'N/A')}")
        print(f"  结论: {'PASS' if gpt4o_result.get('pass') else 'BLOCK'}")

        # 汇总评分
        scores = [r.get("overall_score", 0) for r in results["reviewers"] if "error" not in r]
        if scores:
            results["aggregated_score"] = round(sum(scores) / len(scores), 1)

        # 最终判定
        all_pass = all(r.get("pass", False) for r in results["reviewers"] if "error" not in r)
        results["final_verdict"] = "PASS" if all_pass else "BLOCK"

        # 生成改进项
        for i, weakness in enumerate(gpt4o_result.get("weaknesses", [])):
            results["improvements"].append({
                "id": f"IMP-{datetime.now().strftime('%Y%m%d')}-{i+1:03d}",
                "category": "P1-High" if i < 3 else "P2-Medium",
                "description": weakness,
                "suggestion": gpt4o_result.get("suggestions", [""])[i] if i < len(gpt4o_result.get("suggestions", [])) else "",
                "status": "pending"
            })

        return results

    def save_review_log(self, result: Dict[str, Any]) -> None:
        """保存评审日志"""
        self.review_logs_path.parent.mkdir(parents=True, exist_ok=True)

        with open(self.review_logs_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(result, ensure_ascii=False) + '\n')

        print(f"\n[评审日志已保存] {self.review_logs_path}")

    def print_summary(self, result: Dict[str, Any]) -> None:
        """打印评审摘要"""
        print("\n" + "=" * 60)
        print("📊 评审结果摘要")
        print("=" * 60)
        print(f"任务ID: {result['task_id']}")
        print(f"评审时间: {result['timestamp']}")
        print(f"汇总评分: {result['aggregated_score']}/10")
        print(f"最终判定: {'✅ PASS' if result['final_verdict'] == 'PASS' else '❌ BLOCK'}")
        print()

        print("评审详情:")
        for reviewer in result["reviewers"]:
            model = reviewer.get("reviewer_model", "Unknown")
            score = reviewer.get("overall_score", "N/A")
            verdict = "PASS" if reviewer.get("pass") else "BLOCK"
            print(f"  - {model}: {score}/10 ({verdict})")

        if result.get("improvements"):
            print(f"\n改进项 ({len(result['improvements'])}项):")
            for imp in result["improvements"]:
                print(f"  [{imp['category']}] {imp['description'][:50]}...")


def main():
    parser = argparse.ArgumentParser(description="任务后评审脚本")
    parser.add_argument("--task", "-t", required=True, help="任务ID")
    parser.add_argument("--files", "-f", nargs="+", required=True, help="待评审文件列表")
    parser.add_argument("--dimensions", "-d", nargs="+", help="评审维度")
    parser.add_argument("--output", "-o", help="输出文件路径")

    args = parser.parse_args()

    reviewer = PostTaskReviewer()
    result = reviewer.run_review(args.task, args.files, args.dimensions)

    reviewer.print_summary(result)
    reviewer.save_review_log(result)

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"\n[完整报告已保存] {args.output}")

    # 返回退出码
    sys.exit(0 if result["final_verdict"] == "PASS" else 1)


if __name__ == "__main__":
    # 设置控制台编码
    if sys.platform == 'win32':
        sys.stdout.reconfigure(encoding='utf-8')

    main()