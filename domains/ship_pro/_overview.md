# Ship Pro V3

## 职责
AI Native 多 Agent 协作系统。消费 Solution Pro 输出的 final_result.json，通过 5 个 LLM Agent 协作，生成 ship_package.json（AI Coding 时代的工作包）。

## 架构
```
Architect → Decomposer → Specifier → Reviewer ↔ 反馈闭环 → Packager
```

## 版本: V3.2 (2026-06-23)

### 核心理念
- **Pydantic 契约笼子**: Pydantic 模型 = 唯一真相源，改一处三处自动对齐
- **单一执行引擎**: `run_pipeline.py` CLI 为唯一入口
- **单一状态文件**: `pipeline_state.json` 记录所有状态

### 入口（唯一）
```bash
# 准备管线
python3 scripts/run_pipeline.py prepare <input_path> <output_dir>

# 获取 Agent 任务
python3 scripts/run_pipeline.py task <agent_name> <output_dir>

# 运行质量门禁
python3 scripts/run_pipeline.py gate <agent_name> <output_dir>

# 更新状态（每阶段完成后必须调用）
python3 scripts/run_pipeline.py update-status <output_dir> <agent_name> <PASS|CONDITIONAL|FAIL>

# 查看状态
python3 scripts/run_pipeline.py status <output_dir>

# 最终验证
python3 scripts/run_pipeline.py validate <output_dir>
```

### 契约笼子
```
contracts/architect.py    → ArchitectOutput Pydantic 模型
contracts/packager.py     → ShipPackage Pydantic 模型
contracts/pipeline_state.py → PipelineState 模型
contracts/generator.py    → 自动从模型生成 JSON Schema + Prompt 段落 + Gate 清单
```

CI 一致性检查: `python3 -m domains.ship_pro.contracts.generator --check`

## 代码索引

| 文件 | 职责 |
|------|------|
| `scripts/run_pipeline.py` | **唯一执行引擎**（prepare/task/gate/validate/status/update-status） |
| `scripts/orchestrator.py` | ~~编排准备~~ ⚠️ **DEPRECATED** — 已合并到 run_pipeline.py |
| `contracts/` | Pydantic 契约模型（唯一真相源） |
| `eval/gates.py` | 质量门禁（使用 Pydantic 验证） |
| `eval/eval_code_checks.py` | L2 代码级检查 |
| `prompts/` | 5 个 Agent 的 prompt 模板 |
| `schemas/` | JSON Schema（从 Pydantic 自动生成） |
| `scripts/e2e_test.py` | 端到端测试 |
| `scripts/validate_input.py` | 输入验证 |

## 禁止

- ❌ 直接写 `pipeline_state.json`（必须用 `update-status` CLI）
- ❌ 手动 spawn Agent（必须用 `task` + `gate` CLI）
- ❌ 修改 Pydantic 模型不同步 Schema（必须跑 `generator --check`）
- ❌ 调用 `orchestrator.py`（已废弃）

## 历史版本

| 版本 | 日期 | 变更 |
|------|------|------|
| V3.2 | 2026-06-23 | Pydantic 契约笼子 + 单一执行引擎 + 状态单一化 |
| V3.1 | 2026-06-22 | STAGE_PATH_REGISTRY 统一路径 |
| V3.0 | 2026-06-18 | 5 Agent LLM-native 管线 |
| V2.0 | 2026-06-15 | LLM 引导 + 确定性编译（已废弃） |
