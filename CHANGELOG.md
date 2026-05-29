# Changelog

All notable changes to DeepFlow will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
