# Changelog

All notable changes to DeepFlow will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- **frozen_spec.py V2.0 — 全量提取修复**（`domains/solution/frozen_spec.py`，16 行新增代码）
  - constraints 从硬编码 3 个 key（budget/timeline/tech_stack）→ 遍历所有 key（11 条）
  - guardrails.resolved 新增提取（7 条 design_decision）
  - inferred 新增提取（10 条 inferred category）
  - 总 REQ 数：74 → 98，信息保留率：~95% → ~100%
  - 下游零影响：所有消费方均为泛型遍历
- **文档全面更新**（6 份文档）
  - `docs/spec_pro_review.md`：更新 extraction 规则 + solution_pro_hints 消费状态
  - `ARCHITECTURE_REVIEW/frozen_spec_v2_review.md`：更新提取表 + 新增变更记录
  - `domains/spec_pro/IMPROVEMENTS.md`：标注 8 个问题的实施状态（7✅ 已完成 + 1⚠️ 待验证）
  - `reviews/spec-to-solution-ux-review.md`：标注 5 项 P0 问题已修复
  - `docs/design/spec_solution_link_v2.md`：标注三层缺陷已修复
  - `docs/design/spec_pro_to_solution_pro_link_upgrade.md`：标注架构缺陷已修复

## [0.1.4] - 2026-06-02

### Component Versions
- Spec Pro: 2.3.0
- **Solution Pro: 4.3.0** (from 3.2.0)
- Investment: 2.0.0
- Research Pro: 1.0.0

### Added
- **Golden Case E2E 测试框架** — 完整的端到端测试系统
  - `tests/golden/golden_case_001.json`: AI智能客服系统测试用例（10阶段 / 6约束 / 7 REQ-ID）
  - `tests/golden/run_golden_e2e.py`: 启动器脚本
  - `tests/golden/verify_golden_case.py`: 验证脚本（92项检查）
  - `tests/golden/README.md`: 测试文档
- **Schema 分层验证体系** — 三层 Schema 设计
  - 核心层: `status`, `stage`, `covered_req_ids`（所有阶段必须）
  - 标准层: + `harness_check`（4维评分，非 exempt 阶段）
  - 可选层: `layer2_response`, `metadata`
- **`HARNESS_EXEMPT_STAGES`** — 显式声明 exempt 阶段
  - `data_collection`, `planning`, `summarizer` 只要求核心层 + 需求追踪
- **运行时 Schema 验证** — `completion_handler.py` 接入 `validate_stage_output()`
  - 自动检查每个阶段输出是否符合 Schema
  - 有 Schema 错误时状态降级为 `partial`
  - 返回 `schema_errors` 字段记录具体违规

### Changed
- **Prompt 模板变量化** — stage 字段动态注入
  - `reviewer_v2_harness.md`: `"stage": "{{ stage_name }}"`（动态注入 `reviewer_{type}`）
  - `researcher_v2_harness.md`: `"stage": "{{ stage_name }}"`（动态注入 `research_expert_{id}`）
  - `summarizer_v2_harness.md`: `"stage": "{{ stage_name }}"`（动态注入 `summarizer`）
  - `task_builder.py`: 添加 `{{ stage_name }}` 变量替换逻辑（L633, L1009, L1461）
- **decision 枚举扩展** — 增加 `PASS_WITH_CONDITIONS`
  - `task_builder.py` L289: Schema 定义
  - `task_builder.py` L361: 验证函数
- **文档全面对齐** — 所有文档反映最新架构
  - `README.md`: 重写，增加 Schema 分层、exempt 阶段、运行时验证
  - `SKILL.md`: 更新 Worker 输出要求，增加 Schema 分层说明
  - `_overview.md`: 重写代码索引，增加 Schema 分层说明

### Fixed
- **planner.md 缺少 status/stage** — 唯一没定义 status 的 worker prompt
  - 添加 `"status": "completed"` 和 `"stage": "planning"` 到输出 schema
- **Golden Case 验证器字段对齐** — 8 个 WARN 全部修复
  - 对齐 prompt 真实输出 schema（`review` → `data`，`solution_architecture` → `analysis`）
  - 支持 `alias_fields` 别名机制（`for_planner` / `recommendations_for_planner`）
- **traceability matrix 查找逻辑** — 修复 REQ-ID 匹配 bug
  - 支持 `req_id` 和 `id` 两种命名
- **exempt 阶段验证逻辑** — 只检查 `covered_req_ids`
  - 不再强制要求 `status`/`stage`/`harness_check`

---

## [0.1.3] - 2026-06-01

### Component Versions
- Spec Pro: 2.3.0
- Solution Pro: 3.2.0
- Investment: 2.0.0
- Research Pro: 1.0.0

### Added
- **版本管理体系**: 三层版本架构（全局/组件/文件级）
  - 所有 prompt/cage/contract/domain 文件添加 YAML Front Matter 版本标识
  - `prompt_registry.py`: `read_prompt()` 自动剥离 Front Matter
  - `prompt_registry.py`: `validate()` 从报 warning 改为版本一致性检查
  - 迁移脚本: `scripts/migrate_version_headers.py`

### Changed
- 修复 `master_agent.py` / `orchestrator_agent.py` 硬编码版本问题

---



### Added
- **Spec Pro v2.3** — 需求vs设计边界/角色分离/主动检索/有效需求声明
  - prompts/guide.md: 边界自检 + boundary_check字段 + 问题数量3-5
  - prompts/assess.md: 宽容评分哲学（参考业界=有效需求）
  - prompts/parse_response.md: 有效需求声明识别（user_directives）
  - prompts/orchestrator.md: 主Agent行为约束 + API降级策略
  - prompts/structure.md: 摘要增加用户指令板块
  - IMPROVEMENTS.md: 8个问题完整复盘文档
  - update_conversation_log.py: 对话日志更新脚本
- **Solution Pro v3.2** — Living Spec交接 + 主Agent行为约束
  - SKILL.md: 统一执行入口 + living_spec参数
  - README.md: 更新使用方式 + 废弃旧入口
- **基础设施**
  - core/agents/spawn_resolver.py: 统一 spawn_fn 解析模块
  - contracts/skill_md_unification_contract.md: Skill MD 统一化契约
  - cage/spec_pro_direct_driver.yaml: Spec Pro 直接驱动契约

### Fixed
- Solution Pro prompt 注册表 + task_builder 断链
- 重构遗留的 import 断裂 + 测试适配

### Changed
- chore: gitignore 补全（.codegraph运行时文件 + tests/results JSON）
- refactor: core/ 基础设施重组 + domains/ 四大领域模块化迁移
- refactor: 契约笼子整理 + 代码清理 + 文档更新
- refactor: 遗留项清理 — 兼容层移除 + 路径修复 + 配置合并
- feat: 目录结构整理 — docs/config/tests/scripts 标准化迁移

## [0.1.2] - 2026-05-30

### Changed
- **大规模目录清理**（3 commits，8 项修复）
  - 删除 `skills/research-pro/`（与 `domains/research_pro` 代码重复）
  - 删除 `core/spec_pro/` 空壳目录
  - 删除 `frontend/frontend/`、`frontend/task_queue/`、`prompts/investment/`、`prompts/solution/`、`domains/spec_pro/config/` 空目录
  - 统一 35 个 `check_*.py` 到 `scripts/checks/`
  - 归档 29 个废弃文件到 `ARCHIVED/v1.0_legacy/`
  - 修复所有 import 链断裂（resilience_manager/observability/coordinator/quality_gate）
  - 更新 `.gitignore` 过期规则
- **根目录修复**（契约笼子方式）
  - 删除 `__pycache__/` 根目录残留
  - 删除 `config.json` 中无效的 `task_queue` 路径
  - 删除 `DIRECTORY_STRUCTURE_CONTRACT.md` 根目录副本（与 `contracts/` 一致）
  - 清理 `cage/archive/` 中的 `.py` 和非契约 `.md` 文件
  - 迁移 `cage/integrate_codegraph.yaml` 到 `cage/active/`
  - 更新 `pyproject.toml`（清理已不存在的 packages）
  - 更新 `pytest.ini`（添加 ARCHIVED/blackboard/docs 到 norecursedirs）
  - 清理 `prompts/` 垃圾文件（`.audit_report.md`）

### Archived
- 归档 `cage/archive/` 非契约文件到 `docs/archive/` 和 `ARCHIVED/v1.0_legacy/`
- 归档 5 个依赖已删除 Coordinator 的 `scripts/checks/` 脚本

### Fixed
- `tests/conftest.py`：注释 dead fixtures（mock_coordinator/mock_quality_gate/mock_blackboard_manager）
- `tests/unit/fixtures/test_helpers.py`：注释已删除的 Coordinator import
- `tests/contract/test_quality_gate.py`：更新 import 路径 `quality_gate` → `core.quality.quality_gate`

## [0.1.1] - 2026-05-18

### Added
- Frontend UI with FastAPI + React + Material Design (Phase 1-7)
- Task queue with file-based persistence and SQLite
- Webhook integration for OpenClaw Gateway
- Cron job processor for automated task handling
- Feishu document export functionality
- Contract Cage integration for spec validation
- Solution Pro V3.1 with 8 agent harnesses
- Configuration-driven architecture
- API documentation and architecture flow diagrams

### Changed
- Updated .gitignore to exclude sensitive configs and generated files
- Improved session naming with short prefixes

## [0.1.0] - 2026-05-06

### Added
- Multi-agent pipeline framework (10 stages)
- EntryHarness for startup validation
- PipelineOrchestrator for worker scheduling
- Quality gates with Harness V2 scoring
- DataManager Worker for unified data collection
- Contract Cage validation framework
- Investment Analysis domain (vertical scenario)
- Solution Pro domain (core framework)
- Prompt Registry for extensibility
- Comprehensive documentation (ARCHITECTURE.md, etc.)

### Notes
- Platform dependency: OpenClaw required for core scheduling
- Three-layer architecture: Platform → Framework → Domain
