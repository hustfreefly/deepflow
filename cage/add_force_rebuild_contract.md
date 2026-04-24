# 添加 force_rebuild 参数强制重新分析（方案 C）

## 修复目标
修改 DeepFlow 框架，添加 `force_rebuild` 参数，确保 Orchestrator 在检测到旧数据时能够强制重新执行分析，而不是复用历史结果。

## 根因分析
- 子 Agent 检测到历史 session 有完整数据时，主动决定复用旧数据
- 这是"优化"行为，但违背了用户"重新分析"的意图
- 需要框架层提供强制重建机制

## 修复方案

### 1. 修改 execution_plan.json 结构
添加 `force_rebuild` 字段：
```json
{
  "session_id": "xxx",
  "force_rebuild": true,
  "phases": [...]
}
```

### 2. 修改 Orchestrator 逻辑
在 `core/orchestrator.py` 中：
- 读取 execution_plan 时检查 `force_rebuild`
- 如果为 true，跳过历史数据检查，强制 spawn 新 Workers
- 如果为 false 或未设置，保持现有逻辑（允许复用）

### 3. 修改 Task Builder
在生成 Orchestrator Task 时，支持传递 `force_rebuild` 参数

## 修复范围
- core/orchestrator.py
- core/task_builder.py（build_orchestrator_task）
- core/master_agent.py（创建 execution_plan 时）

## 验收标准
- [ ] execution_plan.json 支持 `force_rebuild` 字段
- [ ] Orchestrator 读取到 `force_rebuild: true` 时，不检查历史 session
- [ ] 每个 Phase 都 spawn 新的 Workers
- [ ] 旧 session 数据保留，新 session 独立生成
- [ ] force_rebuild: false 时保持现有行为

## 执行步骤
1. 修改 master_agent.py 添加 force_rebuild 到 execution_plan
2. 修改 orchestrator.py 检查 force_rebuild 参数
3. 修改 task_builder.py 支持传递参数
4. 测试验证
5. 提交
