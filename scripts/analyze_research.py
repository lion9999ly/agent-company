"""
汇总分析脚本 - 生成 optical_constraints.md
"""
import os
import sys
import json

# 添加项目根目录到 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from src.utils.model_gateway import get_model_gateway

load_dotenv()

# 读取原始数据
with open('.ai-state/research_raw_data.json', 'r', encoding='utf-8') as f:
    raw_data = json.load(f)

# 提取关键信息摘要
summary = """
# 搜索结果关键数据摘要

## 路径1: OLED + FreeForm

### SeeYA SY049WDM02 (0.49")
- 分辨率: 1920×1080 (FHD)
- 面板亮度: 3000nits (官方) / 1800cd/m² (部分型号)
- 对比度: 50,000:1
- PPI: >4500
- 刷新率: 最高90Hz
- 接口: MIPI
- 来源: seeya-tech.com, tindie.com, PRNewswire
- 置信度: 高 (供应商官方)

### Freeform棱镜/反射膜
- 典型FOV: 20°-30°
- 光学效率: 15%-30%
- 到眼亮度推算: 3000nits × 20% = 600nits
- 透过率: ~70%
- 置信度: 中 (行业经验)

## 路径2: MicroLED + 树脂光波导

### JBD Hummingbird (0.13")
- 分辨率: 640×480 VGA
- PPI: 6350
- 面板亮度: 绿200万nits, 红20万nits, 蓝150万nits
- 功耗: 百毫瓦量级 (低功耗)
- 标准FOV: 30° (可定制25-45°)
- 到眼亮度: 1800nits (配合波导)
- 光通量: 3-5 lumens
- 来源: prnewswire.com, displaydaily.com, trendforce.com
- 置信度: 高 (供应商官方+新闻报道)

### JBD Phoenix (最新2024)
- 面板亮度: 200万nits (RGB全彩)
- 到眼亮度: 6000nits (配合30°衍射波导)
- 光通量: 6 lumens
- 来源: trendforce.com
- 置信度: 高

### JBD单色规格
- 功耗: 百毫瓦级 (静态/低速图像)
- SPI/QSPI接口
- 5000级亮度可调
- OTP内存支持亮度均匀性补偿
- 来源: titaa.org.tw PDF
- 置信度: 高

### 树脂衍射光波导
- 典型FOV: 20°-40°
- 透过率: 80%-85%
- 光效: 0.5%-2%
- 眼盒: 8×6mm典型
- 彩虹效应: 普遍存在，需验证
- 置信度: 中 (行业经验)

## 路径3: 单色绿光波导

### 单色绿光优势
- 面板亮度: >200万nits (JBD绿光)
- 无彩虹效应
- 到眼亮度可达1500-2000nits
- 功耗更低
- 置信度: 中 (基于JBD规格推算)

## 竞品参考

### EyeRide/EyeLights
- FOV: ~20°
- 标称亮度: 3000nits
- 实测到眼亮度: 450-900nits (推算)
- 可靠性问题: 线缆易损
- 置信度: 中 (用户反馈+竞品分析)

### Shoei GT-Air 3 Smart
- 使用EyeLights方案
- 置信度: 低 (公开信息有限)
"""

# 构建分析 prompt
prompt = f"""
请基于以下搜索数据，生成一份结构化的光学约束参数文档。

**原始数据摘要**:
{summary}

**要求**:
1. 整理三条路径的参数对比表
2. 每个数据标注来源和置信度
3. 明确标注"未找到，需商务接触"的项
4. 给出默认建议值
5. 输出格式为 Markdown

三条路径定义:
- 路径1: OLED微显示器 + FreeForm光学
- 路径2: 双目全彩光波导（树脂衍射）
- 路径3: 双目单色绿光波导（树脂衍射）

需要覆盖的参数:
- FOV（视场角）
- 到眼亮度（nits）
- 分辨率
- 虚像距离
- 眼盒（eyebox）
- 可视窗口物理尺寸
- 透过率
- 户外阳光下对比度
- 功耗
- 体积/重量

输出完整的 Markdown 文档内容。
"""

# 调用 model_gateway
print("调用 model_gateway 汇总分析...")
gw = get_model_gateway()
result = gw.call(
    model_name='gpt_5_4',
    prompt=prompt,
    task_type='chat'
)

if result.get('success'):
    response = result.get('response', '')
    print(f"分析完成，响应长度: {len(response)} 字符")

    # 保存结果
    output_path = 'demo_outputs/specs/optical_constraints.md'
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(response)
    print(f"文档已保存到: {output_path}")
else:
    print(f"分析失败: {result.get('error')}")