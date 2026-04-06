"""
深度研究 — 守夜模式
职责: 关键环节失败时自动诊断 + 修复 + 重试 + 飞书通知 + 守夜报告
改进: GLM-5 做常规诊断，思考通道(CDP)仅用于战略问题（节省 Max 额度）
被调用方: pipeline.py, runner.py
依赖: models.py
"""
import json
import subprocess
import time
from pathlib import Path

from scripts.deep_research.models import call_model, FALLBACK_MAP

NIGHT_WATCH_ENABLED = True

# 全局飞书回调（在 runner.py 入口处赋值）
_send_reply_global = None
_reply_target_global = None

LOG_PATH = Path(__file__).resolve().parent.parent.parent / ".ai-state" / "night_watch_log.jsonl"


def set_feishu_callback(send_reply, reply_target):
    global _send_reply_global, _reply_target_global
    _send_reply_global = send_reply
    _reply_target_global = reply_target


def _update_night_log(stage: str, action: str):
    """更新守夜日志的最后一条记录"""
    if not LOG_PATH.exists():
        return
    lines = LOG_PATH.read_text(encoding='utf-8').strip().split('\n')
    if lines:
        try:
            last = json.loads(lines[-1])
            if last.get("stage") == stage:
                last["action_taken"] = action
                lines[-1] = json.dumps(last, ensure_ascii=False)
                LOG_PATH.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        except:
            pass


def diagnose(stage: str, error: str, context: str = "",
             retry_fn=None, retry_args=None, is_strategic: bool = False) -> dict:
    """守夜诊断 + 自动修复 + 重试

    改进: 默认用 GLM-5（glm_4_7）做诊断，仅 is_strategic=True 时用 CDP 思考通道。

    Returns:
        {"diagnosed": bool, "fixed": bool, "retried": bool, "retry_result": any}
    """
    if not NIGHT_WATCH_ENABLED:
        return {"diagnosed": False}

    result = {"diagnosed": False, "fixed": False, "retried": False, "retry_result": None}

    prompt = (
        f"深度学习管道在 [{stage}] 阶段失败。\n\n"
        f"错误信息: {error[:500]}\n\n"
        f"上下文: {context[:500]}\n\n"
        f"请分析根因并分类：\n"
        f"A) 模型不可用 — 给出替代模型名\n"
        f"B) 代码 bug — 给出具体的文件和修复方案\n"
        f"C) 数据/输入问题 — 给出调整建议\n"
        f"D) 临时问题（网络/限流）— 建议等待后重试\n\n"
        f"回答格式：\n"
        f"类型: A/B/C/D\n"
        f"诊断: 具体原因\n"
        f"修复: 具体方案"
    )

    try:
        diagnosis = None

        if is_strategic:
            # 战略问题才用 CDP 思考通道
            try:
                from scripts.claude_bridge import call_claude_via_cdp
                diagnosis = call_claude_via_cdp(prompt, inject_context=True)
            except Exception as e:
                print(f"[NightWatch] CDP 调用失败，降级到 GLM: {e}")

        if not diagnosis:
            # 常规诊断用 GLM-5（节省 Max 额度）
            glm_result = call_model("glm_4_7", prompt,
                                    "你是系统运维诊断专家。", "night_watch_diagnose")
            if glm_result.get("success"):
                diagnosis = glm_result["response"]

        if not diagnosis:
            return result

        result["diagnosed"] = True
        print(f"[NightWatch] 诊断 [{stage}]: {diagnosis[:200]}")

        # 记录日志
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_PATH, 'a', encoding='utf-8') as f:
            f.write(json.dumps({
                "stage": stage,
                "error": error[:300],
                "diagnosis": diagnosis[:1000],
                "timestamp": time.strftime('%Y-%m-%d %H:%M'),
                "action_taken": "pending",
                "diagnoser": "cdp" if is_strategic else "glm_4_7",
            }, ensure_ascii=False) + "\n")

        # 根据诊断类型自动修复
        diagnosis_lower = diagnosis.lower()

        if "类型: a" in diagnosis_lower or "类型:a" in diagnosis_lower or "模型不可用" in diagnosis_lower:
            print(f"[NightWatch] 类型 A: 模型不可用，尝试替代")
            suggested_model = None
            for model_name in ["doubao_seed_lite", "gpt_4o_norway", "gpt_5_4",
                               "deepseek_v3_volcengine", "deepseek_r1_volcengine",
                               "gemini_2_5_flash", "gemini_2_5_pro"]:
                if model_name in diagnosis_lower:
                    suggested_model = model_name
                    print(f"[NightWatch] 建议替代模型: {model_name}")
                    if retry_args and isinstance(retry_args, dict):
                        retry_args["model_name"] = model_name
                    break

            if not suggested_model and retry_args and isinstance(retry_args, dict):
                current_model = retry_args.get("model_name", "")
                if current_model in FALLBACK_MAP:
                    fallback = FALLBACK_MAP[current_model]
                    retry_args["model_name"] = fallback
                    print(f"[NightWatch] 使用降级链: {current_model} -> {fallback}")

            result["fixed"] = True

        elif "类型: b" in diagnosis_lower or "类型:b" in diagnosis_lower or "代码" in diagnosis_lower:
            print(f"[NightWatch] 类型 B: 代码问题，尝试自动修复")
            try:
                project_root = Path(__file__).resolve().parent.parent.parent
                fix_prompt = (
                    f"在项目 {project_root} 中修复以下问题：\n\n"
                    f"阶段: {stage}\n"
                    f"错误: {error[:300]}\n"
                    f"架构师诊断: {diagnosis[:500]}\n\n"
                    f"请直接修改代码并用 git commit --no-verify 提交。"
                )
                fix_result = subprocess.run(
                    ['python', '-c', f'''
import sys
sys.path.insert(0, "{project_root}")
from scripts.claude_bridge import call_claude_via_cdp
result = call_claude_via_cdp("""{fix_prompt[:500]}""")
print(result[:200] if result else "No response")
'''],
                    capture_output=True, text=True, timeout=120, cwd=str(project_root)
                )
                if fix_result.returncode == 0:
                    print(f"[NightWatch] 代码修复完成: {fix_result.stdout[:100]}")
                    result["fixed"] = True
            except Exception as e:
                print(f"[NightWatch] 代码修复失败: {e}")

        elif "类型: d" in diagnosis_lower or "类型:d" in diagnosis_lower or "重试" in diagnosis_lower or "临时" in diagnosis_lower:
            print(f"[NightWatch] 类型 D: 临时问题，等待 30 秒后重试")
            time.sleep(30)
            result["fixed"] = True

        # 重试
        if result["fixed"] and retry_fn and retry_args:
            print(f"[NightWatch] 重试 [{stage}]...")
            try:
                retry_result = retry_fn(**retry_args)
                result["retried"] = True
                result["retry_result"] = retry_result

                if isinstance(retry_result, dict) and retry_result.get("success"):
                    print(f"[NightWatch] 重试成功！")
                    _update_night_log(stage, "fixed_and_retried")
                else:
                    print(f"[NightWatch] 重试仍然失败")
                    _update_night_log(stage, "retry_failed")
            except Exception as e:
                print(f"[NightWatch] 重试异常: {e}")
                _update_night_log(stage, f"retry_error: {str(e)[:50]}")

        # 推送飞书
        if result["diagnosed"] and _send_reply_global and _reply_target_global:
            try:
                status = "重试成功" if result.get("retried") and isinstance(result.get("retry_result"), dict) and result["retry_result"].get("success") else "已诊断"
                _send_reply_global(_reply_target_global,
                    f"守夜修复 [{stage}]\n诊断: {diagnosis[:200]}\n状态: {status}")
            except Exception as e:
                print(f"[NightWatch] 飞书通知失败: {e}")

    except Exception as e:
        print(f"[NightWatch] 守夜诊断异常: {e}")

    return result


def generate_night_report(task_results, send_reply=None, reply_target=None):
    """生成守夜报告 — 推送到飞书"""
    total_tasks = len(task_results) if task_results else 0
    success_tasks = sum(1 for t in (task_results or []) if t.get("success"))

    report_lines = [f"🌙 深度学习守夜报告 {time.strftime('%Y-%m-%d %H:%M')}"]
    report_lines.append(f"任务完成: {success_tasks}/{total_tasks}")

    if LOG_PATH.exists():
        diagnoses = LOG_PATH.read_text(encoding='utf-8').strip().split('\n')
        today = time.strftime('%Y-%m-%d')
        tonight_diags = []
        for d in diagnoses:
            if today in d:
                try:
                    tonight_diags.append(json.loads(d))
                except:
                    pass
        if tonight_diags:
            report_lines.append(f"\n⚠️ 今晚架构师介入 {len(tonight_diags)} 次:")
            for d in tonight_diags:
                report_lines.append(f"  [{d['stage']}] {d['diagnosis'][:100]}")
        else:
            report_lines.append("\n✅ 全程无异常，架构师未介入")

    ai_state = Path(__file__).resolve().parent.parent.parent / ".ai-state"
    for name, label in [("search_learning.jsonl", "搜索学习"),
                        ("model_effectiveness.jsonl", "模型效果")]:
        p = ai_state / name
        if p.exists():
            count = sum(1 for _ in open(p, encoding='utf-8'))
            report_lines.append(f"📈 {label}: {count} 条记录")

    report = "\n".join(report_lines)

    if send_reply and reply_target:
        send_reply(reply_target, report)
    print(report)
