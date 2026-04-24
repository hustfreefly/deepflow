# DeepFlow V4.0 修复报告：key_metrics 数据缺失
## 日期: 2026-04-23

---

## 修复内容

### 1. Prompt 层面修复（researcher_finance.md）

**问题**: key_metrics 中 PE/PB/PS/市值为 null 时，Agent 被迫自行搜索，耗时33分钟。

**修复**: 添加 "数据缺失 Fallback 策略" 章节：
- 明确优先级：东方财富实时API（5秒）→ 新浪财经（10秒）→ 放弃（使用默认值）
- 时间控制：单个查询≤10秒，总补全≤60秒
- 默认值参考：半导体制造行业 PE:60-80, PB:3-5, PS:8-12
- 标注 "数据缺失，使用行业默认值，confidence降低0.2"

### 2. 上下文层面修复（task_builder.py）

**问题**: task_builder 生成任务时未检测 key_metrics 数据完整性。

**修复**: 在 extract_data_summary 中添加数据质量检测：
- 检测 null 字段比例
- 如果 null 比例 > 50%，在任务中添加警告提示
- 添加数据质量评分

---

## 验证

- ✅ researcher_finance.md 语法正确
- ✅ task_builder.py 语法正确
- ✅ 所有模块可正常导入

---

## 预期效果

修复后，如果 key_metrics 数据缺失：
1. Finance Researcher 会在 60秒内尝试补全数据
2. 如果超时，使用默认值继续分析
3. 总耗时从 33分钟降至 5-10分钟

---

## 状态

修复完成，等待用户指示是否运行测试。
