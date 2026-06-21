# DeepFlow Solution Pro - 进度通知方案

## 架构设计

```
主 Agent
  ├── Step 1: spawn orchestrator (mode="run")
  ├── Step 2: 创建临时 cron job（每 3 分钟检查一次）
  └── Step 3: sessions_yield() 等待完成

orchestrator 子 Agent
  └── 执行 10 阶段管线，每完成一个阶段写文件到 stages/

cron job（临时巡检）
  ├── 每 3 分钟执行一次
  ├── 扫描 blackboard/{session_id}/stages/ 目录
  ├── 对比 .notified_stages.json，发现新阶段就推送进度
  ├── 检测到 .completed 标记 → 做最终汇报 → 删除自己
  └── 超时保护：超过 2 小时自动删除
```

## 实现细节

### 1. Orchestrator 写阶段文件（已有）

每个阶段完成后写入：
- `stages/{stage_name}.json`（如 `stages/planning.json`）
- 并行阶段写多个文件（如 `stages/reviewer_technical.json`）

### 2. 完成标记文件

orchestrator 全部完成后写入 `.completed`：
```json
{
  "session_id": "xxx",
  "status": "completed",
  "completed_at": "2026-06-01T00:30:00Z",
  "final_output": "final_solution.md"
}
```

### 3. Cron Job 巡检逻辑

```python
# cron job 的 prompt 中包含：
session_id = "xxx"
base_path = "/Users/allen/.openclaw/workspace/.deepflow/blackboard/xxx"

# 检查逻辑：
1. 读取 .notified_stages.json（记录已通知的阶段）
2. 扫描 stages/ 目录，列出所有 .json 文件
3. 对比：如果有新文件，推送进度
4. 检查 .completed 标记是否存在
5. 如果存在：
   - 做最终汇报
   - 删除 cron job
6. 更新 .notified_stages.json
```

### 4. Cron Job 生命周期

- **创建时机**：主 Agent spawn orchestrator 后立即创建
- **删除时机**：
  - 检测到 `.completed` 标记
  - 或超时 2 小时后自动删除（防止幽灵 cron）
- **命名规则**：`deepflow_progress_{session_id[:8]}`

## 用户体验

### 启动时
```
✅ 已启动 DeepFlow Solution Pro 管线
📊 共 10 个阶段，预计 30-60 分钟
💬 期间你可以继续问我其他问题，完成后我会通知你
```

### 每 3 分钟进度更新
```
📊 方案设计进度 [session_id]
━━━━━━━━━━━━━━━━━━━━
✅ Data Collection (1/10)
✅ Planning (2/10)
⏳ Reviewers (3/10) - 运行中...
⬜ Research
⬜ Consolidator
⬜ Audit
⬜ Fix
⬜ Fixer Expert
⬜ Harness Final
⬜ Summarizer

已耗时: 12:30 | 预计剩余: 20:00
```

### 完成时
```
✅ 方案设计完成！用时 45 分钟

快速摘要：
1. 架构：微服务 + Kubernetes
2. 数据库：PostgreSQL + Redis
3. 安全：OAuth 2.0 + JWT

完整方案已保存至 blackboard/xxx/final_solution.md
需要我解释某个部分，还是直接开始实施？
```

### 失败时
```
⚠️ 方案设计在第 4 阶段失败

原因：外部 API 触发了限流（429 Too Many Requests）
影响：第 1-3 阶段结果已保存，第 4-10 阶段未执行

选项：
1. 5 分钟后重试（自动退避）
2. 跳过第 4 阶段，继续后续阶段
3. 手动提供第 4 阶段所需信息

你想怎么处理？
```

## 优势

1. **零侵入** — 不需要改 orchestrator 代码，它已经在写文件
2. **职责分离** — orchestrator 专注编排，cron 专注通知
3. **生命周期清晰** — 任务开始创建，完成时删除
4. **主 Agent 不阻塞** — yield 后可处理其他请求
5. **失败也能通知** — orchestrator 失败时也会写 `.completed` 标记

## 风险与缓解

| 风险 | 缓解措施 |
|------|---------|
| cron job 没被删除（幽灵进程） | 超时 2 小时自动删除 + 命名规则便于清理 |
| cron job 检查频率太高（每 3 分钟 10 条消息） | 可调整为 5 分钟，或只在关键里程碑通知 |
| cron job 无法读取 blackboard 文件 | 确保 cron job 有足够的文件权限 |
| 用户觉得消息太多 | 提供配置选项：关闭进度通知，只保留完成通知 |

## 实现优先级

**Phase 1（MVP）**：
- 实现基础 cron 巡检
- 每 3 分钟检查一次
- 检测到完成时汇报 + 删除

**Phase 2（增强）**：
- 智能消息频率（只在关键里程碑通知）
- 失败场景的详细报告
- 用户可配置通知频率

**Phase 3（优化）**：
- 进度预测（基于历史数据估算剩余时间）
- 失败自动重试机制
- 多任务并行时的通知聚合
