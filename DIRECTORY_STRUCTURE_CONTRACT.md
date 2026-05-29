# DeepFlow 目录结构契约

> **版本**: 2.0.0
> **生效日期**: 2026-05-30
> **核心原则**: 模块自包含 · core 纯基础设施 · 禁止按文件类型分层

---

## 第一章 总则

### 1.1 契约目的

定义 DeepFlow 的目录结构规范。只解决一个问题：**文件放在哪**。

### 1.2 适用范围

`.deepflow/` 目录下所有文件和目录。

### 1.3 不覆盖

代码风格、CI/CD、测试标准、性能要求 — 这些不是目录契约的事。

---

## 第二章 目标目录结构

```
.deepflow/
├── core/                    # 纯基础设施（按功能分组成子目录）
├── domains/                 # 业务域（每个域自包含：代码+prompts+配置+测试）
├── prompts/                 # 仅跨模块共享 prompts
├── config/                  # 仅全局配置（域配置在域内部）
├── cage/                    # 契约（活跃/ + archive/）
├── tests/                   # 仅跨模块集成测试（域测试在域内部）
├── frontend/                # 独立子项目
├── scripts/                 # 运维脚本
├── docs/                    # 项目文档
├── ARCHIVED/                # 归档（已完成的旧项目/旧模块）
├── blackboard/              # 运行时数据（不入库）
├── tools/                   # 仅跨模块通用工具
│
├── __init__.py
├── README.md
├── CHANGELOG.md
├── DIRECTORY_STRUCTURE_CONTRACT.md  # 本文件
├── SKILL.md
├── pyproject.toml
├── pytest.ini
├── requirements.txt
└── .gitignore
```

### 2.1 三条铁律

| # | 规则 | 违反示例 |
|---|------|---------|
| 1 | **core/ 只放基础设施，禁止放业务代码** | ❌ `core/spec_pro/` |
| 2 | **每个域自包含 — 代码+prompts+配置+测试在同一目录** | ❌ 代码在 `domains/`，prompts 在 `prompts/` |
| 3 | **根目录禁止散落 .py/.sh/.yaml** | ❌ 根目录放 `deepflow.py` |

---

## 第三章 core/（基础设施层）

### 3.1 职责

所有业务域共享的基础能力。**禁止包含任何业务逻辑。**

### 3.2 目标结构

```
core/
├── __init__.py
├── config/                      # 配置加载
│   ├── __init__.py
│   ├── path_config.py           # 路径管理
│   └── config_loader.py         # 配置加载器
├── orchestrator/                # 编排引擎
│   ├── __init__.py
│   ├── orchestrator_base.py
│   ├── pipeline_orchestrator.py
│   ├── master_agent.py
│   └── orchestrator_agent.py
├── blackboard/                  # Blackboard 系统
│   ├── __init__.py
│   ├── blackboard_manager.py
│   └── blackboard_bridge.py
├── cage/                        # 契约笼子引擎
│   ├── __init__.py
│   ├── cage_loader.py
│   ├── cage_validator.py
│   └── cage_checkpoint.py
├── data/                        # 数据管理 + 搜索
│   ├── __init__.py
│   ├── data_manager.py
│   ├── data_manager_worker.py
│   ├── data_providers/          # 数据源适配器
│   └── search_engine.py
├── quality/                     # 质量与可观测
│   ├── __init__.py
│   ├── quality_gate.py
│   ├── entry_harness.py
│   └── observability.py
├── agents/                      # 定时/Webhook 任务
│   ├── cron_task_checker.py
│   └── webhook_task_processor.py
├── app_config.py                # 应用级配置
├── checkpoint_manager.py        # 检查点管理
├── prompt_registry.py           # Prompt 注册中心
├── prompt_utils.py              # Prompt 工具
├── task_builder.py              # 通用任务构建器
└── unified_entry.py             # 统一入口
```

### 3.3 规则

1. 新增基础设施模块必须归入对应子目录，禁止直接放 `core/` 根
2. 子目录数量上限 8 个
3. **禁止在 core/ 放业务域代码**（如 spec_pro/）

---

## 第四章 domains/（业务域层）

### 4.1 核心原则：模块自包含

每个域的**代码 + prompts + 配置 + 测试**必须在同一个目录下。

### 4.2 目标结构

```
domains/
├── __init__.py
│
├── spec_pro/                    # Spec Pro：需求收集
│   ├── __init__.py
│   ├── _overview.md             # 模块索引（30秒理解全貌）
│   ├── coordinator.py
│   ├── models.py
│   ├── merge_spec.py
│   ├── utils.py
│   ├── worker_fallback.py
│   ├── process_guard.py
│   ├── spec_pro_api.py          # ← 从 tools/ 迁入
│   ├── prompts/                 # ← 从 prompts/spec_pro/ 迁入
│   │   ├── orchestrator.md
│   │   ├── guide.md
│   │   ├── assess.md
│   │   ├── structure.md
│   │   ├── parse.md
│   │   ├── harness.md
│   │   └── parse_response.md
│   ├── config/
│   │   └── spec_pro_v2.0.yaml   # ← 从 cage/ 迁入
│   └── tests/                   # 域内测试
│
├── solution/                    # Solution Pro：方案设计
│   ├── __init__.py
│   ├── _overview.md
│   ├── orchestrator_agent.py
│   ├── task_builder.py
│   ├── harness_scorer.py
│   ├── harness_validator.py
│   ├── blackboard.py
│   ├── planner.py
│   ├── config.py
│   ├── security_validator.py
│   ├── prefix_extractor.py
│   ├── check_contract.py
│   ├── harness_check_expert.py
│   ├── progress_tracker.py
│   ├── prompts/                 # ← 从 prompts/solution/ 迁入
│   ├── config/
│   │   └── solution.yaml        # ← 从 domains/solution.yaml 迁入
│   └── tests/
│
├── research_pro/                # Research Pro：深度研究
│   ├── __init__.py
│   ├── _overview.md
│   ├── orchestrator.py          # ← 从 skills/research-pro/lib/ 迁入
│   ├── citation_verifier.py
│   ├── keyword_generator.py
│   ├── source_registry.py
│   ├── tier_classifier.py
│   ├── prompts/                 # ← 从 skills/research-pro/prompts/ 迁入
│   ├── config/                  # ← 从 skills/research-pro/config/ 迁入
│   └── tests/                   # ← 从 tests/research_pro/ 迁入
│
└── investment/                  # Investment：投资分析
    ├── __init__.py
    ├── _overview.md
    ├── cage_orchestrator.py
    ├── prompts/                 # ← 从 prompts/investment/ 迁入
    ├── config/
    │   └── investment.yaml      # ← 合并 config/data_sources/investment.yaml
    └── tests/
```

### 4.3 规则

1. **新建域必须包含**: `__init__.py` + `_overview.md` + `prompts/` + `config/` + `tests/`
2. **域间禁止直接 import**，通过 Blackboard 通信
3. **每个域只有一个 orchestrator** 作为入口
4. 删除 `domains/solution_v2/`（空目录）
5. 删除 `domains/investment/orchestrator_deprecated.py`

### 4.4 _overview.md 格式

每个域必须有一个 `_overview.md`，让新人 30 秒理解模块全貌：

```markdown
# Spec Pro

## 职责
一句话描述

## 入口
- Orchestrator: `coordinator.py` → `SpecProCoordinator`

## 文件索引
| 文件 | 职责 |
|------|------|
| coordinator.py | 主协调器 |
| models.py | 数据模型 |
| ... | ... |

## Prompts
| 文件 | 用途 |
|------|------|

## 配置
| 文件 | 用途 |
|------|------|
```

---

## 第五章 共享资源

### 5.1 prompts/（共享 Prompt 层）

仅存放**跨模块共享**的 prompts：

```
prompts/
├── general/         # 通用 prompt 模板
├── code/            # 代码生成 prompt
├── system/          # 系统 prompt
└── architecture/    # 架构分析 prompt
```

**禁止**在 `prompts/` 下创建域专属子目录（域 prompts 在域内部）。

### 5.2 config/（全局配置）

仅存放**跨模块共享**配置：

```
config/
├── global.yaml          # 全局配置（唯一）
└── paths.yaml           # 路径配置
```

**禁止**在 `config/` 下放域专属配置（域配置在域内部）。
**禁止**在 `config/data_sources/` 放域数据源配置（如 investment.yaml — 迁入域内部）。

### 5.3 tests/（共享测试层）

仅存放**跨模块集成测试**：

```
tests/
├── conftest.py              # 共享 fixtures
├── integration/             # 跨模块集成测试
└── e2e/                     # 端到端测试
```

**禁止**在 `tests/` 下放域专属测试（域测试在域内部 `tests/`）。

### 5.4 cage/（契约管理）

```
cage/
├── active/                  # 活跃契约（当前使用）
│   ├── spec_pro_v2.0.yaml
│   └── deepflow_navigator_v1.0.yaml
└── archive/                 # 已完成/历史契约
    ├── frontend_*.yaml
    ├── github_release_contract.yaml
    └── ...
```

### 5.5 tools/

仅存放**跨模块通用工具**。模块专属工具必须在域内部。

当前违规：`tools/spec_pro_api.py` → 迁入 `domains/spec_pro/`

### 5.6 根目录

仅允许以下文件：
- `__init__.py`, `README.md`, `CHANGELOG.md`, `SKILL.md`
- `DIRECTORY_STRUCTURE_CONTRACT.md`（本文件）
- `pyproject.toml`, `pytest.ini`, `requirements.txt`, `.gitignore`

**禁止**在根目录放 `.py`/`.sh`/`.yaml` 文件。

### 5.7 frontend/（前端子项目）

独立子项目，结构自定。

### 5.8 blackboard/（运行时数据）

不入库，已在 `.gitignore` 中。

### 5.9 ARCHIVED/（归档）

存放已完成的旧项目/旧模块/旧文档。只进不出。

---

## 第六章 命名规范

| 类型 | 规范 | 示例 |
|------|------|------|
| Python 文件 | `snake_case.py` | `orchestrator.py` |
| 配置文件 | `kebab-case.yaml` 或 `snake_case.yaml` | `global.yaml` |
| Prompt 文件 | `snake_case.md` | `planner.md` |
| 契约文件 | `snake_case_vX.X.yaml` | `spec_pro_v2.0.yaml` |
| 测试文件 | `test_snake_case.py` | `test_orchestrator.py` |
| 目录（代码） | `snake_case` | `spec_pro/` |
| 目录（skill） | `kebab-case` | `research-pro/`（仅 skills/ 下） |
| 备份文件 | ❌ 禁止 `.bak` `.backup` `.p2-backup` | 用 Git 管理 |

---

## 第七章 迁移计划

### 当前问题 → 目标状态

```
当前:                              目标:
core/spec_pro/                     domains/spec_pro/
prompts/spec_pro/          →       domains/spec_pro/prompts/
cage/spec_pro_v2.0.yaml            domains/spec_pro/config/
tools/spec_pro_api.py              domains/spec_pro/spec_pro_api.py

skills/research-pro/lib/           domains/research_pro/
skills/research-pro/prompts/  →    domains/research_pro/prompts/
skills/research-pro/config/        domains/research_pro/config/
tests/research_pro/                domains/research_pro/tests/

domains/solution/                  domains/solution/
prompts/solution/          →       domains/solution/prompts/
domains/solution.yaml              domains/solution/config/solution.yaml

domains/investment/                domains/investment/
prompts/investment/        →       domains/investment/prompts/
config/data_sources/investment.yaml domains/investment/config/investment.yaml
core/data_providers/investment.py  core/data_providers/investment.py（保留）

core/（15+文件平铺）        →      core/（按功能分 6 个子目录）
cage/（32文件混杂）         →      cage/active/ + cage/archive/
```

### 迁移阶段

#### Phase 1：清理技术债（立即）

| 操作 | 目标 |
|------|------|
| 删除 `domains/solution_v2/` | 空目录 |
| 删除 `domains/investment/orchestrator_deprecated.py` | deprecated 文件 |
| 删除 `skills/research-pro/lib/orchestrator.py.p2-backup` | 备份残留 |
| `cage/` 历史契约 → `cage/archive/` | 减少噪音 |

#### Phase 2：重组 core/（基础设施分组）

1. 创建 `core/orchestrator/`, `core/blackboard/`, `core/cage/`, `core/config/`, `core/data/`, `core/quality/`
2. 将现有文件移入对应子目录
3. 更新所有 import 路径
4. 运行全量测试验证

#### Phase 3：迁移 Spec Pro（验证模式）

1. `core/spec_pro/` → `domains/spec_pro/`
2. `prompts/spec_pro/` → `domains/spec_pro/prompts/`
3. `cage/spec_pro_v2.0.yaml` → `domains/spec_pro/config/`
4. `tools/spec_pro_api.py` → `domains/spec_pro/`
5. 创建 `domains/spec_pro/_overview.md`
6. 运行测试验证

#### Phase 4：迁移其他域

1. **Research Pro**: `skills/research-pro/` 整体 → `domains/research_pro/`，`tests/research_pro/` → `domains/research_pro/tests/`
2. **Solution Pro**: `prompts/solution/` → `domains/solution/prompts/`，`domains/solution.yaml` → `domains/solution/config/`
3. **Investment**: `prompts/investment/` → `domains/investment/prompts/`，合并配置

#### Phase 5：整理共享层

1. `prompts/` 重命名为 `shared_prompts/`（或保留 `prompts/` 但只留共享内容）
2. 清理 `config/data_sources/`（已迁入域内部）
3. 创建 `_overview.md` 模板

### 迁移原则

1. **每阶段一次 git commit**，保持原子性
2. **代码+prompts+配置+测试一起迁**，不允许半迁移
3. **迁移后必须跑测试**
4. **迁移后更新本文档**

---

## 第八章 验证

### 8.1 检查清单

实现 `scripts/check_directory_contract.py`，自动检查：

| 检查项 | 规则 |
|--------|------|
| 根目录清洁 | 无 `.py`/`.sh`（白名单除外） |
| core/ 无业务 | 无 `spec_pro/`、`solution/` 等域目录 |
| 域自包含 | 每个域有 `prompts/` + `config/` + `tests/` |
| 无 deprecated | 无 `*_deprecated.py`、`*.p2-backup` |
| 无空目录 | — |
| 命名规范 | snake_case（域）/ kebab-case（skill） |
| cage 分离 | 有 `active/` + `archive/` |
| _overview.md | 每个域有 |

### 8.2 审计节奏

- 每次 PR 跑 `check_directory_contract.py`
- 违规分级处理：P0 禁止合并，P1 下个 Sprint 修，P2 记技术债

---

## 变更历史

| 版本 | 日期 | 变更 | 评审 |
|------|------|------|------|
| 1.0.0 | 2026-05-30 | 初始版本 | 5 位专家 |
| 2.0.0 | 2026-05-30 | 核心重写：自包含域模式 + core 分组 + 迁移路径 | 4 位专家（Python结构/内聚性/可发现性/技术债） |
