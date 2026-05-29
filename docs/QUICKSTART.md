# DeepFlow 快速执行卡（半屏速查）

> **版本**: 0.1.1 (V4.0 投资分析 + V3.1 方案设计)

---

## 投资分析 — 三步启动

```python
# 第1步：设置环境变量
export DEEPFLOW_DOMAIN=investment
export DEEPFLOW_CODE=688652.SH
export DEEPFLOW_NAME=京仪装备

# 第2步：主Agent spawn Orchestrator
sessions_spawn(
    runtime="subagent",
    mode="run",
    label="orchestrator",
    task="""
你是 DeepFlow V1.0 Orchestrator Agent。
读取 {deepflow_base}/prompts/pipeline_engine_orchestrator.md
按指令执行完整管线。所有 sessions_spawn 必须设置 label。
""".format(deepflow_base=str(PathConfig.resolve().base_dir)),
    timeout_seconds=600
)

# 第3步：等待完成
sessions_yield()  # ← 禁止轮询！等待推送
```

## 方案设计 — 三步启动

```python
# 第1步：主Agent spawn Solution Pro
sessions_spawn(
    runtime="subagent",
    mode="run",
    label="solution_pro",
    task="""
你是 DeepFlow Solution Pro Orchestrator Agent。

任务: 设计一个智能物流仓储系统升级方案
类型: architecture
约束: 预算500万，周期6个月
利益相关者: 技术团队，财务总监
session_prefix: 智能仓储

执行 10 阶段完整管线:
1. Data Collection
2. Planning + Reviewers（Harness V2 评审）
3. Research ×N（并行）
4. Consolidator（整合）
5. Audit + Fix（审计+修复）
6. Harness Final（最终质量把关）
7. Summarizer（生成报告）

所有输出写入 blackboard/ 目录。
""",
    timeout_seconds=1800
)

# 第2步：等待完成
sessions_yield()  # ← 禁止轮询！等待推送
```

## 验证清单（执行后检查）

```bash
ls blackboard/{session_id}/
# 投资分析应有：
# ├── config/data/INDEX.json              ✅
# ├── researcher_*_output.json     ✅ (>2KB)
# ├── auditor_*_output.json        ✅ (>2KB)
# └── final_report.md              ✅

# 方案设计应有：
# ├── stages/planner_output.json     ✅
# ├── stages/reviewer_*_output.json  ✅
# ├── stages/researcher_*_output.json ✅
# ├── stages/auditor_*_output.json   ✅
# ├── stages/harness_final_output.json ✅
# └── final_report.md                ✅
```

## 常见问题

| 问题 | 原因 | 解决 |
|------|------|------|
| "sessions_spawn 不可用" | 未在 Agent Run 环境 | 必须通过 sessions_spawn 启动 |
| Worker 输出只有元数据 | 未等待 Worker 完成 | 检查 _wait_for_worker_completion |
| 收敛评分偏低 | 数据缺口/逻辑矛盾 | 检查 auditor P0/P1 问题 |
| Solution Pro 超时 | 任务复杂，Agent 数量多 | 增加 timeout_seconds 至 1800+ |

## 记忆锚点

> "Agent环境才spawn；spawn_fn逐层注入；yield等推送别轮询"
> "Worker 输出 >2KB 才真实；元数据 <500 字节是假的"
> "DataManager 是 Pipeline 第一个 stage，自动 spawn 不用管"
> "Solution Pro 用 EntryHarness → PipelineOrchestrator → Workers"

---
*标准执行手册详见：docs/STANDARD_EXECUTION.md（投资分析）*
*Solution Pro 设计详见：docs/SOLUTION_PRO_MODE_DESIGN.md（方案设计）*
