"""
测试深度研究管道 - HUD 光学约束参数搜索
"""
import sys
import time
from pathlib import Path

# Windows UTF-8 输出修复
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# 确保项目路径
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv(project_root / ".env")

from scripts.deep_research.pipeline import deep_research_one

# 搜索词列表
SEARCH_TASKS = [
    {
        "id": "specs_seeya_sy049",
        "title": "SeeYA SY049 OLED microdisplay",
        "goal": "查找 SeeYA SY049 OLED 微显示屏的技术规格，包括分辨率、亮度、功耗、对比度等参数",
        "searches": [
            "SeeYA SY049 OLED microdisplay specifications",
            "SeeYA SY049 resolution brightness contrast",
            "SY049 OLED microdisplay datasheet"
        ]
    },
    {
        "id": "specs_jbd_hummingbird",
        "title": "JBD Hummingbird MicroLED",
        "goal": "查找 JBD Hummingbird MicroLED 微显示屏的亮度、功耗、分辨率等核心参数",
        "searches": [
            "JBD Hummingbird MicroLED brightness power consumption",
            "JBD Hummingbird MicroLED specifications",
            "JBD MicroLED display datasheet"
        ]
    },
    {
        "id": "specs_freeform_prism",
        "title": "Freeform prism helmet HUD",
        "goal": "查找自由曲面棱镜在头盔 HUD 中的视场角 FOV、眼动范围 eyebox 参数",
        "searches": [
            "freeform prism helmet HUD FOV eyebox",
            "freeform optical prism AR display specifications",
            "helmet HUD freeform prism design parameters"
        ]
    },
    {
        "id": "specs_resin_waveguide",
        "title": "树脂衍射光波导",
        "goal": "查找树脂衍射光波导的全彩显示能力、FOV、亮度效率参数",
        "searches": [
            "resin diffractive waveguide full color FOV brightness",
            "polymer waveguide AR display efficiency",
            "树脂光波导 全彩 FOV 亮度"
        ]
    },
    {
        "id": "specs_helmet_combiner",
        "title": "Motorcycle helmet HUD combiner",
        "goal": "查找摩托车头盔 HUD 光学组合薄膜的技术参数",
        "searches": [
            "motorcycle helmet HUD optical combiner film",
            "helmet HUD combiner reflectance transmittance",
            "HUD optical film helmet visor"
        ]
    },
    {
        "id": "specs_longjing_waveguide",
        "title": "珑璟光电树脂光波导",
        "goal": "查找珑璟光电树脂光波导产品的技术参数",
        "searches": [
            "珑璟光电 树脂光波导 参数",
            "Longjing Optics resin waveguide specifications",
            "珑璟光电 光波导 FOV 效率"
        ]
    },
    {
        "id": "specs_binocular_waveguide",
        "title": "Binocular waveguide vergence",
        "goal": "查找双目光波导侧置方案的视差 vergence 问题与解决方案",
        "searches": [
            "binocular waveguide side placement vergence",
            "dual waveguide vergence accommodation conflict",
            "AR glasses binocular waveguide placement"
        ]
    },
    {
        "id": "specs_rainbow_effect",
        "title": "树脂光波导彩虹效应",
        "goal": "查找树脂光波导彩虹效应的成因与解决方案",
        "searches": [
            "树脂光波导 彩虹效应 解决方案",
            "polymer waveguide rainbow effect mitigation",
            "diffractive waveguide color uniformity"
        ]
    }
]

def run_tests():
    """执行所有搜索任务"""
    output_dir = Path(__file__).resolve().parent.parent / "demo_outputs" / "specs"
    output_dir.mkdir(parents=True, exist_ok=True)

    all_results = []

    print(f"\n{'='*60}")
    print(f"深度研究管道测试 - HUD 光学约束参数")
    print(f"任务数: {len(SEARCH_TASKS)}")
    print(f"{'='*60}\n")

    start_time = time.time()

    for task in SEARCH_TASKS:
        print(f"\n--- 任务 {task['id']}: {task['title']} ---")
        try:
            result = deep_research_one(task)
            all_results.append({
                "id": task["id"],
                "title": task["title"],
                "success": True,
                "report": result[:5000] if len(result) > 5000 else result
            })
            print(f"  [OK] 完成，报告长度: {len(result)} 字")
        except Exception as e:
            all_results.append({
                "id": task["id"],
                "title": task["title"],
                "success": False,
                "error": str(e)
            })
            print(f"  [FAIL] 失败: {e}")

    elapsed = time.time() - start_time
    print(f"\n{'='*60}")
    print(f"总耗时: {elapsed/60:.1f} 分钟")
    print(f"成功: {sum(1 for r in all_results if r['success'])}/{len(all_results)}")
    print(f"{'='*60}\n")

    # 生成综合报告
    combined_report = generate_combined_report(all_results, elapsed)

    output_file = output_dir / "optical_constraints.md"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(combined_report)

    print(f"报告已保存: {output_file}")

    return all_results

def generate_combined_report(results: list, elapsed: float) -> str:
    """生成综合报告"""
    report = """# HUD 光学约束参数研究报告

> 生成时间: {time}
> 总耗时: {elapsed:.1f} 分钟
> 成功任务: {success}/{total}

---

## 搜索架构

本次研究使用修复后的深度研究管道：
- **Tavily**：主力搜索（速度快）
- **o3-deep-research**：深度搜索补充（慢但全面）
- **doubao_seed_pro**：中文搜索

---

""".format(
        time=time.strftime('%Y-%m-%d %H:%M'),
        elapsed=elapsed/60,
        success=sum(1 for r in results if r['success']),
        total=len(results)
    )

    for r in results:
        status = "[OK]" if r['success'] else f"[FAIL]: {r.get('error', 'unknown')}"
        report += f"\n## {r['id']}: {r['title']}\n\n"
        report += f"**状态**: {status}\n\n"
        if r['success']:
            report += r['report'] + "\n\n"
        report += "---\n\n"

    return report

if __name__ == "__main__":
    results = run_tests()