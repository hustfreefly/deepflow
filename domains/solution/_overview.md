# Solution Pro — 方案设计引擎

> 版本: 4.3.0 | 更新: 2026-06-02

## 职责
固定 10 阶段管线：理解需求 → 并行研究/评审 → 整合审计 → 质量门输出方案。

## 入口
```python
from domains.solution import run_solution_pro
# 生成 execution_plan.json + tasks.json + frozen_spec.json
# 管线由主 Agent 通过 sessions_spawn 启动 LLM Orchestrator
```

内部类: `_SolutionDispatcher`（orchestrator_agent.py）

## 代码索引

| 文件 | 职责 |
|------|------|
| `__init__.py` | 公共 API `run_solution_pro()` |
| `orchestrator_agent.py` | 主编排器 `_SolutionDispatcher`，生成 session/tasks/plan |
| `task_builder.py` | Worker Task 构建 + Schema 定义 + 验证器 |
| `control_contract.py` | Planning 后确定性刷新 control_contract.json |
| `completion_handler.py` | 完成检查 + Schema 运行时验证 |
| `blackboard.py` | Blackboard 管理 + `STAGE_PATH_REGISTRY` |
| `frozen_spec.py` | REQ-ID 冻结规格生成 |
| `security_validator.py` | 输入清理 + 路径遍历检测 |
| `harness_scorer.py` | Harness 评分 |
| `harness_scoring.py` | Harness 评分辅助 |
| `harness_validator.py` | Harness 验证 |
| `harness_check_expert.py` | Harness 专家 |
| `planner.py` | 规划器辅助 |
| `prefix_extractor.py` | Session ID 前缀提取 |
| `progress_tracker.py` | 进度追踪 |
| `check_contract.py` | 契约检查 |
| `config.py` | 配置 |

## Schema 分层

```
核心层（所有阶段必须）: status, stage, covered_req_ids
标准层（非 exempt 阶段）: + harness_check（4维评分）
可选层: layer2_response, metadata
```

Exempt 阶段: `data_collection`, `planning`, `summarizer`
- 只要求 `covered_req_ids`，不要求 `harness_check`

## Prompts

| 目录 | 说明 |
|------|------|
| `prompts/` | 36 个 Worker prompt（10 阶段 + Harness + 工具 prompt） |

## 测试

| 位置 | 说明 |
|------|------|
| `tests/golden/` | Golden Case E2E 测试（golden_case_001.json + verify_golden_case.py） |
| `scripts/golden_solution_pro_dry_run.py` | 快速 dry-run |
| `scripts/validate_solution_pro_contract.py` | 契约验证 |

## 配置

| 文件 | 用途 |
|------|------|
| `config/solution.yaml` | 域配置 |
