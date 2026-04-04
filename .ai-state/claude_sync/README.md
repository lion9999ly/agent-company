# Claude.ai 同步目录

放置 claude.ai 对话产生的 handoff 文件。
系统启动时自动扫描并处理。

文件命名: handoff_YYYYMMDD.md

## 使用方式

1. 在 claude.ai 完成会话后，生成 handoff 文件
2. 将 handoff 文件放入此目录
3. 系统（或手动调用 `python scripts/handoff_processor.py`）自动处理

## Handoff 文件格式

```markdown
# Handoff YYYYMMDD

## 本次会话要点
- ...

## 待执行任务
```
git commit -m "..."
```

## 下次继续
- ...
```