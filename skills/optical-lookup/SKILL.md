---
name: optical-lookup
description: Use when querying optical display constraints, parameters, supplier comparisons, or cost analysis for HUD/AR helmet display solutions
metadata:
  author: leo
  version: "1.0"
---

# Optical Lookup Skill

## Overview

光学参数查询是智能骑行头盔 HUD 方案选型的核心决策支持。涵盖光波导、BirdBath、自由曲面棱镜等技术路线的参数对比、供应商评估、成本分析。

**核心原则：光学方案决定 Demo 可实现性和产品成本结构。**

## When to Use

- HUD 光学方案选型（光波导 vs BirdBath vs OLED）
- 供应商参数对比（Lumus vs DigiLens vs 珑璟光电）
- 成本估算（BOM 成本、MOQ、NRE 费用）
- Demo A/B 方案可行性验证

**When NOT to Use:**
- 非 HUD 光学问题（摄像头、激光雷达）
- 已有确定方案无需对比

## Key Parameters

| 参数 | 说明 | 典型范围 |
|------|------|----------|
| 亮度 | nits | 1000-5000（户外要求） |
| FOV | 视场角 | 15°-30°（头盔 HUD） |
| 透光率 | 外界视野保持 | 70%-85% |
| 像素密度 | PPI | 2000-3000 |
| 重量 | 光学模组 | 10g-50g |
| 功耗 | W | 0.5-2W |

## Supplier Comparison

| 供应商 | 技术 | 成本 | MOQ | 成熟度 |
|--------|------|------|-----|--------|
| Lumus | 波导 | 高 | 1K+ | 高 |
| DigiLens | 波导 | 中 | 5K+ | 中 |
| 珑璟光电 | 波导 | 低 | 500 | 中 |
| 歌尔 | BirdBath | 低 | 1K+ | 高 |

## Cost Structure

```
光学模组 BOM：
- 显示源（Micro OLED）：$30-80
- 光学元件：$20-100（波导贵，棱镜便宜）
- 驱动电路：$5-15
- 结构件：$5-10
总成本：$60-200（视方案）
```

## Known Pitfalls

| 陷阱 | 规避方法 |
|------|----------|
| MOQ 不匹配小批量 | 找国内方案商（珑璟、灵犀） |
| 户外亮度不足 | 要求 ≥3000 nits |
| 透光率影响视野 | ≥80% 透光率约束 |
| 重量影响头盔平衡 | ≤30g 光学模组 |
| Demo 与实际方案脱节 | optical_constraints.md 明确约束 |

## Constraints File Format

```markdown
# optical_constraints.md

## 硬约束（不可违反）
- 亮度 ≥ 3000 nits（户外骑行）
- 透光率 ≥ 80%（视野安全）
- 重量 ≤ 30g（头盔平衡）

## 软约束（可权衡）
- FOV：20°-25°（最佳平衡）
- 成本：目标 $100 以下
- MOQ：优先 500 以下

## 当前方案
- OLED 全彩：索尼 Micro OLED + BirdBath
- 光波导单绿：珑璟光电方案
```

## Verification Criteria

- [ ] 参数满足硬约束
- [ ] 供应商报价合理（有来源）
- [ ] MOQ 可接受
- [ ] Demo 可实现

## Key Files

```
demo_outputs/specs/optical_constraints.md      # 光学约束定义
demo_outputs/specs/tech_spec_optical_modes.md  # Demo 光学模式
.ai-state/reports/supply_chain_optical_*.md    # 光学供应商研究
.ai-state/reports/optical_suppliers_*.md       # 方案对比报告
```

## Quick Reference

```bash
# 查看光学约束
cat demo_outputs/specs/optical_constraints.md

# 触发光学研究
深度学习 optical_suppliers

# Demo A/B 切换验证
打开 hud_demo_final.html，按 T 键切换光学模式
```