# Solution Pro - 系统级解决方案设计引擎

> 通过 10 阶段 pipeline 自动化生成高质量技术解决方案

## 当前版本

- **版本**: V4.3 (B方案 - 完整10阶段)
- **架构**: 固定10阶段流水线 + 4维质量门禁 + REQ-ID 需求追踪
- **模型**: 默认使用 Qwen 3.6 Plus

## 快速开始

### 1. 生成执行计划

```python
from domains.solution import run_solution_pro

plan = run_solution_pro(
    topic="AI智能客服系统",
    solution_type="architecture",
    mode="standard",
    constraints=["支持10万+日对话", "响应时间<2秒"],
    stakeholders=["技术团队", "产品团队"]
)

# plan 包含: session_id, base_path, execution_plan_path, tasks_path
```

### 2. 执行完整流程

参见 [SKILL.md](SKILL.md) 中的 6 步执行指南。

### 3. 验证结果

```bash
# Golden Case 验证（推荐）
python3 tests/golden/verify_golden_case.py <session_id>

# 快速 dry-run
python3 scripts/golden_solution_pro_dry_run.py

# 契约验证
python3 scripts/validate_solution_pro_contract.py <session_dir>
```

## 核心概念

### 10 阶段流水线

1. **Data Collection** - 结构化需求收集
2. **Planning** - 任务规划与分解
3. **Reviewers (×3 并行)** - 多角度审查
4. **Research (×3 并行)** - 领域研究
5. **Consolidator** - 结果整合
6. **Audit** - 质量审计
7. **Fix** - 问题修复
8. **Fixer Expert** - 专家级修复
9. **Harness Final** - 4维质量门禁
10. **Summarizer** - 最终总结

### 质量契约

- **Schema 分层**: 核心层（必需）+ 标准层（可选）+ 元数据层（可选）
- **质量门禁**: 完整性/必要性/目标一致性/全局影响 4维评分
- **需求追踪**: REQ-ID 全链路追踪

详细 schema 定义见 [docs/contracts/solution_pro_schema.md](../../docs/contracts/solution_pro_schema.md)

## 文档导航

| 文档 | 用途 | 受众 |
|------|------|------|
| [SKILL.md](SKILL.md) | Agent 执行步骤 | AI Agent |
| [_overview.md](_overview.md) | 代码文件索引 | 开发者 |
| [docs/contracts/solution_pro_schema.md](../../docs/contracts/solution_pro_schema.md) | Schema 契约 | 开发者 |
| [prompts/pipeline_orchestrator_v4.md](prompts/pipeline_orchestrator_v4.md) | Orchestrator 指令 | 运行时 |
| [tests/golden/README.md](../../tests/golden/README.md) | Golden Case 测试 | 测试工程师 |

## 禁止事项

- ❌ Python 代码中禁止直接 import OpenClaw SDK（使用 `sessions_spawn` 工具）
- ❌ `run_solution_pro()` 不接收 `spawn_fn` 参数
- ❌ 不要修改 `STAGE_OUTPUT_SCHEMA` 的核心层字段（status, stage, covered_req_ids）
- ❌ 不要删除 `HARNESS_EXEMPT_STAGES` 中的豁免阶段

## 版本历史

详见 [CHANGELOG.md](../../CHANGELOG.md)
