# 搜索层对比测试报告

测试时间: 2026-04-12 12:36:48

测试查询数: 3

## 测试查询列表
1. 智能骑行头盔 AR显示技术 2026
2. 骨传导耳机 供应商 歌尔
3. 光波导显示 module specification

## Tavily 搜索对比

| 指标 | 旧管道 | 新管道 | 差异 |
|------|--------|--------|------|
| 成功率 | 0/3 | 3/3 | - |
| 平均字数 | 0 | 3429 | 3429 |
| 总耗时 | 0.00s | 14.36s | 14.36s |

### Tavily 详细结果

**查询: 智能骑行头盔 AR显示技术 2026**
- 旧管道: success=False, chars=0, time=0.00s
- 新管道: success=True, chars=3302, time=4.36s

**查询: 骨传导耳机 供应商 歌尔**
- 旧管道: success=False, chars=0, time=0.00s
- 新管道: success=True, chars=3441, time=4.22s

**查询: 光波导显示 module specification**
- 旧管道: success=False, chars=0, time=0.00s
- 新管道: success=True, chars=3545, time=5.79s

## Doubao 搜索对比

| 指标 | 旧管道 | 新管道 | 差异 |
|------|--------|--------|------|
| 成功率 | 3/3 | 3/3 | - |
| 平均字数 | 1436 | 3835 | 2399 |
| 总耗时 | 170.78s | 390.02s | 219.24s |

### Doubao 详细结果

**查询: 智能骑行头盔 AR显示技术 2026**
- 旧管道: success=True, chars=1400, time=66.96s
- 新管道: success=True, chars=3866, time=107.90s

**查询: 骨传导耳机 供应商 歌尔**
- 旧管道: success=True, chars=910, time=46.25s
- 新管道: success=True, chars=3189, time=122.74s

**查询: 光波导显示 module specification**
- 旧管道: success=True, chars=2000, time=57.57s
- 新管道: success=True, chars=4450, time=159.38s

## 结论
- Tavily 新管道可用: True
- Doubao 新管道可用: True

## 建议
- Tavily smolagents 工具接入成功，可替代旧管道