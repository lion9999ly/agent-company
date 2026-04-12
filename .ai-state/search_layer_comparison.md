# 搜索层对比测试报告

测试时间: 2026-04-12 12:07:25

测试查询数: 3

## 测试查询列表
1. 智能骑行头盔 AR显示技术 2026
2. 骨传导耳机 供应商 歌尔
3. 光波导显示 module specification

## Tavily 搜索对比

| 指标 | 旧管道 | 新管道 | 差异 |
|------|--------|--------|------|
| 成功率 | 0/3 | 3/3 | - |
| 平均字数 | 0 | 3545 | 3545 |
| 总耗时 | 0.00s | 4.05s | 4.05s |

### Tavily 详细结果

**查询: 智能骑行头盔 AR显示技术 2026**
- 旧管道: success=False, chars=0, time=0.00s
- 新管道: success=True, chars=3537, time=1.36s

**查询: 骨传导耳机 供应商 歌尔**
- 旧管道: success=False, chars=0, time=0.00s
- 新管道: success=True, chars=3502, time=1.32s

**查询: 光波导显示 module specification**
- 旧管道: success=False, chars=0, time=0.00s
- 新管道: success=True, chars=3598, time=1.37s

## Doubao 搜索对比

| 指标 | 旧管道 | 新管道 | 差异 |
|------|--------|--------|------|
| 成功率 | 3/3 | 3/3 | - |
| 平均字数 | 1200 | 104 | -1096 |
| 总耗时 | 163.35s | 90.92s | -72.42s |

### Doubao 详细结果

**查询: 智能骑行头盔 AR显示技术 2026**
- 旧管道: success=True, chars=1438, time=67.60s
- 新管道: success=True, chars=104, time=30.29s

**查询: 骨传导耳机 供应商 歌尔**
- 旧管道: success=True, chars=583, time=36.79s
- 新管道: success=True, chars=104, time=30.34s

**查询: 光波导显示 module specification**
- 旧管道: success=True, chars=1579, time=58.96s
- 新管道: success=True, chars=104, time=30.29s

## 结论
- Tavily 新管道可用: True
- Doubao 新管道可用: True

## 建议
- Tavily smolagents 工具接入成功，可替代旧管道