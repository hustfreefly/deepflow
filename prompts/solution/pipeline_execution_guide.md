# Solution Pro Pipeline 执行指南

> 本指南供主Agent使用，通过 `sessions_spawn` 工具执行8阶段方案设计管线

## 前置准备

```python
# 1. 创建配置
from domains.solution import SolutionConfig, BlackboardManager

config = SolutionConfig(
    session_id="sol_" + uuid.uuid4().hex[:8],
    topic="高并发电商订单系统架构设计",
    constraints=["支持10万QPS", "P99延迟<100ms"],
    stakeholders=["技术总监", "架构师"]
)

# 2. 初始化Blackboard
bb = BlackboardManager(config.session_id)
bb.write_input(config.get_input_data())
print(f"Session: {config.session_id}")
print(f"Blackboard: {bb.base_path}")
```

## Stage 1: Planner (串行)

**任务**: 分析需求，生成8阶段执行计划

```python
# 读取Prompt
prompt = open("/Users/allen/.openclaw/workspace/.deepflow/prompts/solution/worker_planner.md").read()

# 填充变量
filled_prompt = prompt.format(
    blackboard_path=str(bb.base_path)
)

# Spawn Worker
sessions_spawn(
    runtime="subagent",
    mode="run",
    label=f"solution_planner_{config.session_id}",
    task=filled_prompt,
    timeout_seconds=600
)
```

**等待完成**: 检查 `{bb.base_path}/stages/stage_01_planner_output.json`

## Stage 2: Reviewers (并行)

**任务**: 3个Reviewer并行审查计划

```python
reviewers = ["reviewer_completeness", "reviewer_architecture", "reviewer_feasibility"]

# 并行spawn
for reviewer in reviewers:
    prompt = open("/Users/allen/.openclaw/workspace/.deepflow/prompts/solution/worker_reviewer.md").read()
    filled = prompt.format(
        blackboard_path=str(bb.base_path),
        reviewer_type=reviewer.replace("reviewer_", "")
    )
    
    sessions_spawn(
        runtime="subagent",
        mode="run",
        label=f"{reviewer}_{config.session_id}",
        task=filled,
        timeout_seconds=600
    )
```

**等待完成**: 检查3个输出文件
- `stage_02_reviewer_completeness_output.json`
- `stage_02_reviewer_architecture_output.json`
- `stage_02_reviewer_feasibility_output.json`

## Stage 3: Fixer (串行)

**任务**: 根据Reviewer反馈修复计划

```python
prompt = open("/Users/allen/.openclaw/workspace/.deepflow/prompts/solution/worker_fixer.md").read()
# 填充并spawn...
```

**输出**: `stage_03_fixer_planner_output.json`

## Stage 4: Researchers (并行)

**任务**: 3个Researcher并行研究

```python
researchers = ["researcher_tech", "researcher_practice", "researcher_risk"]
# 类似Stage 2，并行spawn...
```

**输出**: 
- `stage_04_researcher_tech_output.json`
- `stage_04_researcher_practice_output.json`
- `stage_04_researcher_risk_output.json`

## Stage 5: Consolidator (串行)

**任务**: 整合研究成果

**输出**: `stage_05_consolidator_output.json`

## Stage 6: Auditors (并行)

**任务**: 3个Auditor并行审计

```python
auditors = ["auditor_completeness", "auditor_architecture", "auditor_risk"]
# 并行spawn...
```

**输出**:
- `stage_06_auditor_completeness_output.json`
- `stage_06_auditor_architecture_output.json`
- `stage_06_auditor_risk_output.json`

## Stage 7: Fixer Expert (串行)

**任务**: 根据Auditor反馈修复最终方案

**输出**: `stage_07_fixer_expert_output.json`

## Stage 8: Summarizer (串行)

**任务**: 生成最终方案文档

**输出**: `stage_08_summarizer_output.md` (Markdown格式)

## 关键约束

### 1. 中心化写入（契约C）
- Workers **不直接写入文件**
- Workers 在回复中返回JSON
- 主Agent调用 `bb.write_stage_output()` 统一写入

### 2. 并行控制
- Stage 2, 4, 6 是并行（各3个Workers）
- 其他Stage是串行
- 每Stage完成后才进入下一阶段

### 3. 超时处理
- Planner/Reviewer/Fixer: 600s
- Researcher/Auditor: 900s
- Summarizer: 600s

### 4. 输出验证
Worker返回前必须验证：
- JSON格式正确
- 包含必要的字段
- 不是spawn元数据（排除 `{"status": "accepted"}`）

## 完成标准

- [ ] 所有8个Stage执行完成
- [ ] 14个Worker输出文件写入Blackboard
- [ ] `stage_08_summarizer_output.md` 生成
- [ ] `final_result.json` 汇总

## 输出文件清单

```
blackboard/{session_id}/
├── input_plan.json
├── progress.json
├── final_result.json
└── stages/
    ├── stage_01_planner_output.json
    ├── stage_02_reviewer_completeness_output.json
    ├── stage_02_reviewer_architecture_output.json
    ├── stage_02_reviewer_feasibility_output.json
    ├── stage_03_fixer_planner_output.json
    ├── stage_04_researcher_tech_output.json
    ├── stage_04_researcher_practice_output.json
    ├── stage_04_researcher_risk_output.json
    ├── stage_05_consolidator_output.json
    ├── stage_06_auditor_completeness_output.json
    ├── stage_06_auditor_architecture_output.json
    ├── stage_06_auditor_risk_output.json
    ├── stage_07_fixer_expert_output.json
    └── stage_08_summarizer_output.md
```