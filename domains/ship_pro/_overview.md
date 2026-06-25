# Ship Pro V4

## 职责
AI Native 多 Agent 协作系统。消费 Solution Pro 输出的 final_result.json，通过 5 个 LLM Agent 协作，生成 ship_package.json（AI Coding 时代的工作包）。

## 架构
```
主 Agent → Orchestrator (sub-agent) → 5 Workers (sessions_spawn)
                                      Architect → Decomposer → Specifier → Reviewer → Packager
```

## 版本: V4.0 (2026-06-25)

### 核心理念
- **Orchestrator 模式**: 主 Agent 只负责启动，Orchestrator 编排 5 Worker（与 Solution Pro 一致）
- **Pydantic 契约笼子**: Pydantic 模型 = 唯一真相源
- **CLI 工具层**: `run_pipeline.py` 提供 prepare/task/gate/update-status/validate 命令（Orchestrator 调用）
- **Cron Watcher**: 进度通知（隔离巡检，确定性检测）

### 入口（主 Agent）
```bash
# 启动管线（生成 spawn_params + watcher_cron_payload）
python3 scripts/start_ship_pro.py --input <input_path> --output <output_dir>
```

### CLI 命令（Orchestrator 使用）
```bash
python3 scripts/run_pipeline.py prepare <input_path> <output_dir>
python3 scripts/run_pipeline.py task <agent_name> <output_dir>
python3 scripts/run_pipeline.py gate <agent_name> <output_dir>
python3 scripts/run_pipeline.py feedback <agent_name> <output_dir>
python3 scripts/run_pipeline.py update-status <output_dir> <agent_name> <PASS|CONDITIONAL|FAIL>
python3 scripts/run_pipeline.py validate <output_dir>
python3 scripts/run_pipeline.py status <output_dir>
```

### 契约笼子
```
contracts/architect.py    → ArchitectOutput Pydantic 模型
contracts/packager.py     → ShipPackage Pydantic 模型
contracts/pipeline_state.py → PipelineState 模型
contracts/reviewer.py     → ReviewerOutput Pydantic 模型
contracts/generator.py    → 自动从模型生成 JSON Schema + Prompt 段落 + Gate 清单
```

CI 一致性检查: `python3 -m domains.ship_pro.contracts.generator --check`

## 代码索引

| 文件 | 职责 |
|------|------|
| `scripts/start_ship_pro.py` | **启动入口**（生成 orchestrator prompt + watcher payload） |
| `scripts/run_pipeline.py` | **CLI 工具层**（prepare/task/gate/validate/status/update-status） |
| `scripts/orchestrator.py` | ⚠️ DEPRECATED — 旧编排脚本，已由 Orchestrator sub-agent 替代 |
| `contracts/` | Pydantic 契约模型（唯一真相源） |
| `eval/gates.py` | 质量门禁（使用 Pydantic 验证） |
| `eval/eval_code_checks.py` | L2 代码级检查 |
| `prompts/` | 5 个 Agent 的 prompt 模板 |
| `schemas/` | JSON Schema（从 Pydantic 自动生成） |
| `config/watcher_config.json` | Watcher 配置 |
| `scripts/e2e_test.py` | 端到端测试 |
| `scripts/validate_input.py` | 输入验证 |

## 禁止

- ❌ 主 Agent 直接 spawn Worker（必须通过 Orchestrator）
- ❌ 直接写 `pipeline_state.json`（必须用 `update-status` CLI）
- ❌ 修改 Pydantic 模型不同步 Schema（必须跑 `generator --check`）
- ❌ 调用 `orchestrator.py`（已废弃）
- ❌ 手写 watcher prompt（必须用 start_ship_pro.py 生成的 watcher_cron_payload）

## 历史版本

| 版本 | 日期 | 变更 |
|------|------|------|
| **V4.0** | **2026-06-25** | **恢复 Orchestrator 模式（与 Solution Pro 一致）** |
| V3.2 | 2026-06-23 | Pydantic 契约笼子 + 单一执行引擎（扁平 spawn，已废弃） |
| V3.1 | 2026-06-22 | STAGE_PATH_REGISTRY 统一路径 |
| V3.0 | 2026-06-18 | 5 Agent LLM-native 管线 |
| V2.0 | 2026-06-15 | LLM 引导 + 确定性编译（已废弃） |
