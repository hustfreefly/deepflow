# DeepFlow 文件目录整理方案

> **日期**: 2026-05-29  
> **依据**: DIRECTORY_STRUCTURE_CONTRACT.md  
> **策略**: 先整理文件，后统一改契约

---

## 当前问题总览

| 问题类型 | 数量 | 说明 |
|---------|------|------|
| 根目录 .py 文件 | 10 个 | 违反红线"禁止根目录放业务代码" |
| 根目录 .sh 文件 | 5 个 | 同上 |
| 根目录多余 .md | 15+ 个 | 应归入 docs/ |
| 备份/临时文件 | 6 个 | 应删除 |
| 不在契约中的目录 | 12 个 | frontend/cron/agents/pipelines/data/data_sources/data_providers/reviews/research/output/checkpoints/state |
| 重复模块 | 3 处 | core/ 和 domains/ 有同名文件 |
| 配置散落 | 3 处 | 根目录 config.json + config/ + core/config/ |

---

## 分阶段执行计划

### 阶段 0：清理垃圾（5 分钟，零风险）

**目标**：删除所有备份文件和临时文件

| 操作 | 命令 | 风险 |
|------|------|------|
| 删除备份文件 | `rm orchestrator_agent.py.bak.20260423` | 无 |
| 删除备份目录 | `rm -rf cage.backup/ skills/deep-research.backup/ tests/deepclaw.backup/` | 无 |
| 删除空数据库 | `rm deepflow.db` | 无（空文件） |
| 删除临时日志 | `rm heartbeat.log` | 无 |

### 阶段 1：根目录脚本迁移（10 分钟，低风险）

**目标**：根目录不再有 .py 和 .sh 文件

| 文件 | 目标位置 | 说明 |
|------|---------|------|
| `deepflow.py` | `tools/deepflow_cli.py` | CLI 入口 |
| `spec_pro_api.py` | `tools/spec_pro_api.py` | Spec Pro API |
| `orchestrator_agent.py` | **删除** | 与 core/ 和 domains/ 重复 |
| `run_spec_pro.py` | `scripts/runners/run_spec_pro.py` | 运行脚本 |
| `run_solution_task.py` | `scripts/runners/run_solution_task.py` | 运行脚本 |
| `run_all_tasks.py` | `scripts/runners/run_all_tasks.py` | 运行脚本 |
| `run_task_1.py` | `scripts/runners/run_task_1.py` | 运行脚本 |
| `run_solution_test.py` | `tests/integration/run_solution_test.py` | 测试脚本 |
| `check_frontend_completion.py` | `scripts/checks/check_frontend_completion.py` | 检查脚本 |
| `ci.sh` | `scripts/ci/ci.sh` | CI 脚本 |
| `run_tests.sh` | `scripts/ci/run_tests.sh` | CI 脚本 |
| `run_orchestrator.sh` | `scripts/runners/run_orchestrator.sh` | 运行脚本 |
| `cleanup_plan.sh` | `scripts/maintenance/cleanup_plan.sh` | 维护脚本 |
| `test_run.sh` | `scripts/ci/test_run.sh` | CI 脚本 |

### 阶段 2：文档整理（10 分钟，零风险）

**目标**：根目录 .md 文件归入 docs/

| 文件 | 目标位置 |
|------|---------|
| `CHANGELOG.md` | **保留根目录**（标准位置） |
| `README.md` | **保留根目录**（标准位置） |
| `LICENSE` | **保留根目录**（标准位置） |
| `DEVELOPMENT_RULES.md` | `docs/design/DEVELOPMENT_RULES.md` |
| `CODING_STANDARDS.md` | `docs/design/CODING_STANDARDS.md` |
| `PROTOCOLS.md` | `docs/design/PROTOCOLS.md` |
| `PROTOCOLS_README.md` | `docs/design/PROTOCOLS_README.md` |
| `SYSTEM_PROMPT.md` | `docs/design/SYSTEM_PROMPT.md` |
| `SKILL.md` | `docs/SKILL.md` |
| `DIRECTORY_STRUCTURE_CONTRACT.md` | **保留根目录**（契约文件） |
| `CONTRACT_CONFLICT_REPORT.md` | `docs/CONTRACT_CONFLICT_REPORT.md` |
| `ARCHITECTURE_REVIEW_REPORT.md` | `docs/ARCHITECTURE_REVIEW_REPORT.md` |
| `ARCHIVE_STATUS.md` | `docs/archive/ARCHIVE_STATUS.md` |
| `OPENCLAW_AGENT_MECHANISM_REFERENCE.md` | `docs/reference/OPENCLAW_AGENT_MECHANISM_REFERENCE.md` |
| `UNIFIED_ENTRY_IMPLEMENTATION.md` | `docs/design/UNIFIED_ENTRY_IMPLEMENTATION.md` |
| `PROGRESS_FRONTEND_2026-05-08.md` | `docs/archive/PROGRESS_FRONTEND_2026-05-08.md` |
| `nightly_test_log.md` | `docs/archive/nightly_test_log.md` |
| `test_report.md` | `docs/archive/test_report.md` |
| `docs-review-technical-docs-expert.md` | `docs/docs-review-technical-docs-expert.md` |

### 阶段 3：配置文件合并（10 分钟，中风险）

**目标**：配置集中到 config/

| 文件 | 操作 |
|------|------|
| `config.json` | 检查内容，合并到 `config/global.yaml`，删除 |
| `core/config/` | 检查与 `config/` 的关系，保留 `path_config.py`（代码），配置合并 |

### 阶段 4：未覆盖目录决策（15 分钟，高风险）

**目标**：决定 12 个"不在契约中"的目录的去留

| 目录 | 当前内容 | 建议操作 | 理由 |
|------|---------|---------|------|
| `frontend/` | FastAPI + React | **加入契约**，保留 | 6 个契约在用 |
| `agents/` | Agent 定义 | **加入契约**，保留 | 独立层 |
| `cron/` | 定时任务 | **加入契约**，保留 | 独立层 |
| `pipelines/` | 流水线定义 | **加入契约**，保留 | 独立层 |
| `data/` | 数据文件 | 检查是否可归入 config/ | 需确认内容 |
| `data_sources/` | 数据源配置 | 合并到 `config/data_sources/` | 是配置 |
| `data_providers/` | 数据提供者 | 检查是否可合并 | 需确认内容 |
| `reviews/` | 审查文档 | 移入 `docs/archive/` | 是文档 |
| `research/` | 研究文档 | 移入 `docs/archive/` | 是文档 |
| `industries/` | 行业数据 | 检查是否可归入 config/ | 需确认内容 |
| `checkpoints/` | 检查点 | 移入 `blackboard/` | 是运行时数据 |
| `state/` | 状态文件 | 移入 `blackboard/` | 是运行时数据 |
| `output/` | 输出文件 | **删除**（空目录） | 无内容 |
| `audit_reports/` | 审计报告 | 移入 `docs/archive/` | 是文档 |
| `test_results/` | 测试结果 | 移入 `tests/` | 是测试数据 |
| `reports/` | 报告 | 检查是否可归入 docs/ | 需确认内容 |

### 阶段 5：core/ 内部重组（30 分钟，高风险）

**目标**：core/ 平铺文件归入子包

当前 core/ 有 20+ 个 .py 文件平铺，需按契约归入：
- `core/orchestrators/` — orchestrator 相关
- `core/blackboard/` — blackboard 相关
- `core/prompt/` — prompt 相关
- `core/cage/` — 契约笼子相关
- `core/data/` — 数据管理相关
- `core/quality/` — 质量门禁相关

⚠️ **高风险**：涉及大量 import 路径变更，需要逐步执行 + 测试验证

### 阶段 6：重复模块合并（30 分钟，高风险）

**目标**：消除 3 处重复

| 重复 | 操作 |
|------|------|
| `core/orchestrator_agent.py` vs `domains/solution/orchestrator_agent.py` | 保留 domains 版本 |
| `core/task_builder.py` vs `domains/solution/task_builder.py` | 检查差异，合并 |
| `core/spec_pro/` vs 契约要求放 `domains/` | P1 迁移，移到 domains/spec_pro/ |

### 阶段 7：更新所有契约路径（20 分钟，低风险）

**目标**：整理完成后，批量更新 18 个 cage/*.yaml 中的路径引用

| 契约 | 需更新 |
|------|--------|
| `deepclaw_v1.0.yaml` | `deep-research` → `research-pro`（30+ 处） |
| `spec_pro_v2.0.yaml` | `core/spec_pro/` → `domains/spec_pro/`（10+ 处） |
| `ui_polish_contract.yaml` | 添加 `base_dir` 前缀 |
| 其他 | 按实际路径更新 |

---

## 执行顺序与时间估算

| 阶段 | 工作内容 | 时间 | 风险 | 前置依赖 |
|------|---------|------|------|---------|
| **0** | 清理垃圾 | 5 分钟 | 无 | 无 |
| **1** | 根目录脚本迁移 | 10 分钟 | 低 | 阶段 0 |
| **2** | 文档整理 | 10 分钟 | 无 | 阶段 0 |
| **3** | 配置文件合并 | 10 分钟 | 中 | 阶段 1 |
| **4** | 未覆盖目录决策 | 15 分钟 | 高 | 阶段 1-3 |
| **5** | core/ 内部重组 | 30 分钟 | 高 | 阶段 3 |
| **6** | 重复模块合并 | 30 分钟 | 高 | 阶段 5 |
| **7** | 更新所有契约路径 | 20 分钟 | 低 | 阶段 6 |

**总计：约 2 小时**

阶段 0-3 可以一气呵成（35 分钟），阶段 4-6 需要你确认决策后再执行。

---

## 每个阶段的回滚策略

- **阶段 0**：Git 恢复已删除文件
- **阶段 1-2**：`git mv` 可逆操作
- **阶段 3-6**：每个阶段完成后 commit，出问题 `git reset` 回退
- **阶段 7**：纯文本替换，`git diff` 确认无误后 commit

---

## 建议

**立即执行**阶段 0-2（清理 + 脚本迁移 + 文档整理），这 25 分钟的工作零风险、立竿见影。

阶段 3-7 需要你确认后再推进。
