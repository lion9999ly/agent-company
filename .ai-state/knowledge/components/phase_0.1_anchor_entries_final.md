# Phase 0.1 决策树锚点 — 终稿（Leo 审核后直接入库）

> 三个 JSON 文件放入 `.ai-state/knowledge/components/`
> 文件名前缀 `ANCHOR_` 便于识别
> 标记 `internal` + `anchor`，检索加权 +20

---

## 锚点 1：mesh_intercom（对讲通讯方案）

文件名：`ANCHOR_20260326_001_mesh_intercom_基准线.json`

```json
{
  "title": "[锚点] Mesh 对讲方案选型基准线",
  "domain": "components",
  "content": "## 行业基准（产品决策者确认，不可被 Agent 推翻）\n\n### 全球标杆：Cardo DMC（Dynamic Mesh Communication）\n- Cardo Packtalk 系列搭载 DMC Gen 2，是摩托车头盔 Mesh 对讲公认的最优方案\n- 核心优势：自组网无需配对、自动路由修复、15 人 Mesh 群组、音质+降噪行业最佳\n- Packtalk Edge 是当前旗舰，ECE 22.06 兼容，IP67\n- 任何 Mesh 对讲方案选型必须以 Cardo DMC 的性能指标为对标基准\n\n### 国内最优平替：Reso\n- Reso 是国内 Mesh 对讲方案中公认的最优实现\n- 功能完整度最接近 Cardo DMC，价格优势明显\n- 适合作为 V1 版本的供应链合作候选（降低 BOM 成本）\n\n### 第二梯队（参考但非首选）\n- Sena Mesh 2.0：生态大但 Mesh 协议弱于 Cardo DMC，音质评价偏低\n- FreedConn / Fodsports：价格极低但品质和稳定性差距大\n\n### 选型红线\n- V1 方案必须达到 Cardo DMC 的基本性能指标（群组 ≥8 人、自组网、IP67）\n- 如果自研 Mesh 协议，必须对标 DMC Gen 2 的自动路由修复能力\n- 不接受以 Sena Mesh 2.0 或更低方案作为"够用就行"的选型依据",
  "source": "product_decision:Leo",
  "created_at": "2026-03-26",
  "tags": ["internal", "anchor", "decision_tree", "mesh_intercom", "product_decision"],
  "confidence": "authoritative"
}
```

---

## 锚点 2：main_soc（主控芯片/AR 处理平台）

文件名：`ANCHOR_20260326_002_main_soc_基准线.json`

```json
{
  "title": "[锚点] 主控 SoC / AR 处理平台选型基准线",
  "domain": "components",
  "content": "## 行业基准（产品决策者确认，不可被 Agent 推翻）\n\n### 芯片定位分层\n智能摩托车全盔的 SoC 选型需区分两层：\n1. **AR 处理平台**（HUD 渲染、摄像头 ISP、AI 推理）：决定产品智能化上限\n2. **连接/音频 SoC**（蓝牙、Mesh 对讲、音频 DSP）：决定通讯体验\n两者可以是同一颗芯片（高集成度方案），也可以是两颗芯片（灵活度高但 BOM 和功耗上升）\n\n### V1 首选：高通 Snapdragon AR1 Gen 1\n- AR1 是当前智能眼镜/AR 头显的事实标准平台\n- Meta 是最大客户（全球智能眼镜市场份额 73%，Counterpoint H1 2025 数据）\n- 双 ISP 支持高质量拍摄和 AI 视觉，内置 AI 引擎\n- 功耗设计针对 250mAh 级电池（眼镜场景），头盔场景电池容量（3000mAh+）远大于此，功耗裕量充足\n- 支持 BLE 5.x，可兼顾连接/音频需求（减少一颗芯片）\n- 阿里夸克 S1、星纪魅族 StarV Snap 等量产产品已验证 AR1 平台成熟度\n- **AR1 是项目 V1 的首选平台，偏离此选择需要产品决策者批准**\n\n### 备选：高通 Snapdragon AR2 Gen 1\n- 更低功耗方案，适合极致省电场景\n- 功能弱于 AR1（AI 能力和 ISP 规格下降）\n- 仅当 AR1 在头盔热管理中确实无法满足功耗预算时才考虑降级\n\n### 连接/音频 SoC（若需独立）\n- 高通 QCC5171 / QCC3083：蓝牙音频 + Mesh 组网能力\n- Cardo 和 Sena 均基于 QCC 系列，方案成熟\n- 如果 AR1 内置蓝牙能满足 Mesh 对讲需求，可省掉这颗芯片\n\n### 选型红线\n- 不选 MTK 低端平台（性能不足以支撑 HUD 渲染和 AI 推理）\n- 不选汽车级芯片（Snapdragon Ride 等，功耗 10W+ 不适合头盔，知识库已有确认条目）\n- 不选 Allwinner 等预算方案（定位不匹配）\n- V1 至少支持：单摄 ISP + BLE 5.x + 基础 AI（语音指令 + 简单视觉识别）",
  "source": "product_decision:Leo",
  "created_at": "2026-03-26",
  "tags": ["internal", "anchor", "decision_tree", "main_soc", "qualcomm_ar1", "product_decision"],
  "confidence": "authoritative"
}
```

---

## 锚点 3：hud_display（HUD 抬头显示方案）

文件名：`ANCHOR_20260326_003_hud_display_基准线.json`

```json
{
  "title": "[锚点] HUD 抬头显示方案选型基准线",
  "domain": "components",
  "content": "## 行业基准（产品决策者确认，不可被 Agent 推翻）\n\n### V1 并行评估的两条技术路线\n\n#### 路线 A：OLED 微显示 + Free Form 自由曲面光学\n- 技术成熟度高，Shoei GT-Air 3 Smart（2026 年中上市，$1,199）已量产验证\n- Shoei 方案由法国 EyeLights 提供 HUD 技术，采用 Sony OLEDoS 微显示器\n  - FHD 1920×1080，3000 nits（强光下可读），虚拟投影距离 3 米\n  - nano-OLED 投射到内置遮阳镜片（Free Form 曲面），无需额外棱镜\n  - ECE 22.06 + DOT 双认证，10 小时续航\n- 优势：供应链成熟（Sony OLEDoS 可采购）、光学设计自由度高、亮度充足\n- 劣势：Free Form 曲面模具成本高、光学设计需定制、显示区域受限于遮阳镜片位置\n- 适合场景：V1 快速量产、与已有头盔结构兼容\n\n#### 路线 B：Micro LED + 树脂衍射光波导\n- 行业趋势方向，2026 年 AR 眼镜主流路线正在向此收敛\n- 树脂衍射光波导优势：\n  - 比玻璃光波导减重约 50%（莫界方案已实现 25g 级 AR 眼镜）\n  - 透过率可达 98%，佩戴者和外界观感更自然\n  - 不易碎，抗冲击性优于玻璃基底（头盔场景重要优势）\n  - 形状处理灵活，可适配头盔曲面镜片\n  - 量产成本有望低于玻璃衍射光波导\n- 国内供应链：莫界（树脂衍射光波导首创者）、光粒科技（全息树脂光波导 Holoresin，年产 10 万片+，良率 95%+）\n- 光引擎：JBD 蜂鸟 Mini II（多家 AR 眼镜已采用）、Micro LED 全彩方案\n- 劣势：FOV 目前偏小（单色 25°-30°，全彩更小）、头盔场景的光学适配尚未有量产先例\n- 适合场景：V1.5/V2 技术升级路线，或 V1 如果能解决 FOV 和头盔适配问题则直接采用\n\n### 竞品参考\n- Shoei GT-Air 3 Smart：路线 A 标杆（OLED + Free Form，$1,199）\n- CrossHelmet / Skully（已失败）：LCoS + 组合棱镜，体积大亮度低，证明此路不通\n- 雷鸟 X3 Pro：Micro LED + 刻蚀光波导，AR 眼镜形态，76g，技术方向正确但非头盔场景\n\n### 选型红线\n- V1 必须做到强光下可读（≥2000 nits）\n- HUD 不能遮挡核心视野（位于视野上方或右上角）\n- 必须通过 ECE 22.06 视野遮挡测试\n- 虚拟投影距离 ≥2 米（避免眼疲劳）\n- 不选 LCoS + 棱镜方案（已被市场淘汰）\n- 不选纯外挂式 HUD（不符合全集成产品定位）\n- 路线 A 和路线 B 并行评估，V1 选择需基于供应链响应速度、成本、FOV 三个维度的实测数据做最终决策",
  "source": "product_decision:Leo",
  "created_at": "2026-03-26",
  "tags": ["internal", "anchor", "decision_tree", "hud_display", "oled_freeform", "resin_waveguide", "product_decision"],
  "confidence": "authoritative"
}
```

---

## 入库操作

将以上三个 JSON 内容分别保存为：
```
.ai-state/knowledge/components/ANCHOR_20260326_001_mesh_intercom_基准线.json
.ai-state/knowledge/components/ANCHOR_20260326_002_main_soc_基准线.json
.ai-state/knowledge/components/ANCHOR_20260326_003_hud_display_基准线.json
```

入库后验证：在飞书发送 `知识库`，确认最近新增中能看到三条 `[锚点]` 开头的条目。
