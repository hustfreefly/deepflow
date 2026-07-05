---
id: contracts/directory_structure
version: "3.1.0"
updated: "2026-06-01"
---

# DeepFlow 目录结构契约

> **版本**: 3.1.0
> **生效日期**: 2026-05-30
> **核心原则**: 模块自包含 · core 纯基础设施 · 契约分层管理 · 禁止按文件类型分层

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
├── contracts/               # 基础契约（全局规范，LLM 可读的 .md 文件）
│   ├── directory_structure.md
│   ├── coding_standards.md
│   ├── development_workflow.md
│   ├── cage_framework.md
│   └── integration/         # 跨模块集成契约
├── cage/                    # 场景契约（模块级行为定义，.yaml 文件）
│   ├── active/              # 活跃契约
│   └── archive/             # 已完成/过时的契约
├── prompts/                 # 仅跨模块共享 prompts
├── config/                  # 仅全局配置（域配置在域内部）
├── tests/                   # 仅跨模块集成测试（域测试在域内部）
├── frontend/                # 独立子项目
├── scripts/                 # 运维脚本
├── docs/                    # 参考文档（不是契约）
├── ARCHIVED/                # 归档（已完成的旧项目/旧模块）
├── blackboard/              # 运行时数据（不入库）
├── tools/                   # 仅跨模块通用工具
│
├── __init__.py
├── README.md
├── CHANGELOG.md
├── CONTRACTS.md             # 契约系统规范（定义契约的格式和生命周期）
├── DIRECTORY_STRUCTURE_CONTRACT.md  # 本文件
├── SKILL.md
├── pyproject.toml
├── pytest.ini
├── requirements.txt
└── .gitignore
```

### 2.1 四条铁律

| # | 规则 | 违反示例 |
|---|------|---------|
| 1 | **core/ 只放基础设施，禁止放业务代码** | ❌ `core/spec_pro/` |
| 2 | **每个域自包含 — 代码+prompts+配置+测试在同一目录** | ❌ 代码在 `domains/`，prompts 在 `prompts/` |
| 3 | **根目录禁止散落 .py/.sh/.yaml** | ❌ 根目录放 `deepflow.py` |
| 4 | **契约分层：基础契约在 contracts/，场景契约在 cage/active/** | ❌ 契约散在 docs/、根目录、cage/ 根 |

---

## 第三章 core/（基础设施层）

### 3.1 职责

所有业务域共享的基础能力。**禁止包含任何业务逻辑。**

### 3.2 目标结构

```
core/
├── config/                      # 配置加载
│   ├── path_config.py
│   └── config_loader.py
├── orchestrator/                # 编排引擎
│   ├── orchestrator_base.py
│   ├── pipeline_orchestrator.py
│   ├── master_agent.py
│   └── orchestrator_agent.py
├── blackboard/                  # Blackboard 系统
│   ├── blackboard_manager.py
│   └── blackboard_bridge.py
├── cage/                        # 契约笼子引擎（代码，非契约文件）
│   ├── cage_loader.py
│   ├── cage_validator.py
│   └── cage_checkpoint.py
├── data/                        # 数据管理 + 搜索
│   ├── data_manager.py
│   ├── data_manager_worker.py
│   ├── data_providers/          # 数据源适配器
│   └── search_engine.py
├── quality/                     # 质量与可观测
│   ├── quality_gate.py
│   ├── entry_harness.py
│   └── observability.py
├── agents/                      # 定时/Webhook 任务
│   ├── cron_task_checker.py
│   └── webhook_task_processor.py
├── app_config.py
├── checkpoint_manager.py
├── prompt_registry.py
├── prompt_utils.py
├── task_builder.py
└── unified_entry.py
```

### 3.3 规则

1. 新增基础设施模块必须归入对应子目录，禁止直接放 `core/` 根
2. 子目录数量上限 8 个
3. **禁止在 core/ 放业务域代码**（如 spec_pro/）
4. `core/cage/` 是契约引擎的**代码**（Python），不是契约文件（YAML）。契约文件在顶层 `cage/`

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
│   ├── _overview.md
│   ├── coordinator.py
│   ├── models.py
│   ├── merge_spec.py
│   ├── utils.py
│   ├── worker_fallback.py
│   ├── process_guard.py
│   ├── spec_pro_api.py
│   ├── prompts/
│   │   ├── orchestrator.md
│   │   ├── guide.md
│   │   ├── assess.md
│   │   ├── structure.md
│   │   ├── parse.md
│   │   ├── harness.md
│   │   └── parse_response.md
│   ├── config/                  # 域运行参数（非契约）
│   └── tests/
│
├── solution/                    # Solution Pro：方案设计
│   ├── __init__.py
│   ├── _overview.md
│   ├── orchestrator_agent.py
│   ├── task_builder.py
│   ├── ...
│   ├── prompts/
│   ├── config/
│   │   └── solution.yaml
│   └── tests/
│
├── research_pro/                # Research Pro：深度研究
│   ├── __init__.py
│   ├── _overview.md
│   ├── orchestrator.py
│   ├── citation_verifier.py
│   ├── keyword_generator.py
│   ├── source_registry.py
│   ├── tier_classifier.py
│   ├── prompts/
│   ├── config/
│   └── tests/
│
└── investment/                  # Investment：投资分析
    ├── __init__.py
    ├── _overview.md
    ├── cage_orchestrator.py
    ├── prompts/
    ├── config/
    │   └── investment.yaml
    └── tests/
```

### 4.3 规则

1. **新建域必须包含**: `__init__.py` + `_overview.md` + `prompts/` + `config/` + `tests/`
2. **域间禁止直接 import**，通过 Blackboard 通信
3. **每个域只有一个 orchestrator** 作为入口
4. **域内 config/ 放运行参数**，不放场景契约（场景契约在 `cage/active/`）
5. **禁止域内 config/ 和 cage/active/ 存同一契约的双份副本**

### 4.4 _overview.md 格式

每个域必须有一个 `_overview.md`，让新人 30 秒理解模块全貌：

```markdown
# [模块名]

## 职责
一句话描述

## 入口
- Orchestrator: `[file].py` → `[ClassName]`

## 代码索引
| 文件 | 职责 |
|------|------|

## Prompts
| 文件 | 用途 |
|------|------|

## 配置
| 文件 | 用途 |
|------|------|

## 场景契约
- `cage/active/[module]_v[X.Y].yaml`
```

---

## 第五章 contracts/（基础契约层）

### 5.1 职责

存放**全局规范**——所有模块、所有开发活动必须遵守的规则。
基础契约是 `.md` 文件，读者是 LLM（大语言模型），LLM 读懂后在具体场景下自觉遵守。

### 5.2 目标结构

```
contracts/
├── directory_structure.md       # 目录结构规范（从本文件提炼）
├── coding_standards.md          # 编码规范（P0/P1/P2 规则）
├── development_workflow.md      # 开发流程（契约先行→实现→验证）
├── cage_framework.md            # 契约笼子机制定义（四层约束）
└── integration/                 # 跨模块集成契约
    └── spec_to_solution.md      # Spec Pro → Solution Pro 数据交接规范
```

### 5.3 规则

1. **基础契约统一放 `contracts/`**，不在 cage/、docs/、根目录散落
2. 基础契约格式必须包含：版本 + 适用范围 + MUST/NEVER/SHOULD 规则 + 验证方式
3. `contracts/integration/` 存放跨模块数据流和交接规范
4. 基础契约变更必须更新版本号

### 5.4 与 cage/ 的区别

| | contracts/（基础契约） | cage/active/（场景契约） |
|---|---|---|
| **范围** | 全局，所有模块 | 特定模块 |
| **格式** | .md（自然语言） | .yaml（结构化） |
| **读者** | 所有 Agent | 对应模块的 Agent |
| **示例** | "禁止 bare except" | "Spec Pro Coordinator 不含 LLM 推理代码" |

---

## 第六章 cage/（场景契约层）

### 6.1 职责

存放**模块级行为定义**——特定模块开发时必须遵守的接口、行为、数据约束。
场景契约是 `.yaml` 文件，读者是 LLM，LLM 读懂后自觉遵守并生成检查逻辑。

### 6.2 目标结构

```
cage/
├── README.md                    # 唯一允许的根文件（契约笼子使用说明）
├── active/                      # 活跃契约（当前开发中的模块）
│   ├── spec_pro_v2.0.yaml       # ✅ 已创建（24KB）
│   ├── research_pro_v1.0.yaml   # ✅ 已创建（18KB）
│   ├── investment_v2.0.yaml     # ✅ 已创建（5.4KB）
│   └── solution_v1.0.yaml       # ✅ 已创建（9.7KB）
└── archive/                     # 已完成/过时的契约
    ├── spec_pro_v1.0.yaml
    ├── frontend_*.yaml
    └── ...
```

### 6.3 规则

1. **场景契约统一放 `cage/active/`**，完成后移入 `cage/archive/`
2. **cage/ 根目录只允许**：`README.md` + `active/` + `archive/`，禁止放其他文件
3. **命名**：`{module}_v{X.Y}.yaml`
4. **必须有 redlines + check 字段**
5. **文件大小指导**：simple ≤ 5KB / medium ≤ 15KB / complex ≤ 30KB（以内容完整性为优先，大小为参考）
6. **场景契约唯一位置**：`cage/active/`，禁止在 domains/*/config/ 存副本
7. `core/cage/`（Python 代码）和 `cage/`（YAML 契约）同名不同质，注意区分

### 6.4 生命周期

```
draft → active → archive
                   ↓
              reactivated（重新激活）→ active
```

| 操作 | 规则 |
|------|------|
| 新增 | 必须声明 version 和 created |
| 修改 | 必须更新 version 和 updated |
| 归档 | 移入 archive/ |
| 删除 | **禁止**，只能归档 |

---

## 第七章 共享资源

### 7.1 prompts/（共享 Prompt 层）

仅存放**跨模块共享**的 prompts：

```
prompts/
├── general/
├── code/
├── system/
└── architecture/
```

**禁止**在 `prompts/` 下创建域专属子目录（域 prompts 在域内部）。

### 7.2 config/（全局配置）

仅存放**跨模块共享**配置：

```
config/
├── global.yaml
└── paths.yaml
```

**禁止**在 `config/` 下放域专属配置（域配置在域内部）。

### 7.3 tests/（共享测试层）

仅存放**跨模块集成测试**：

```
tests/
├── conftest.py
├── integration/
└── e2e/
```

**禁止**在 `tests/` 下放域专属测试（域测试在域内部 `tests/`）。

### 7.4 tools/

仅存放**跨模块通用工具**。模块专属工具必须在域内部。

### 7.5 根目录

仅允许以下文件：
- `__init__.py`, `README.md`, `CHANGELOG.md`, `SKILL.md`
- `CONTRACTS.md`（契约系统规范）
- `DIRECTORY_STRUCTURE_CONTRACT.md`（本文件）
- `pyproject.toml`, `pytest.ini`, `requirements.txt`, `.gitignore`

**禁止**在根目录放 `.py`/`.sh`/`.yaml` 文件。

### 7.6 frontend/（前端子项目）

独立子项目，结构自定。

### 7.7 blackboard/（运行时数据）

不入库，已在 `.gitignore` 中。

### 7.8 ARCHIVED/（归档）

存放已完成的旧项目/旧模块/旧文档。只进不出。

### 7.9 docs/（参考文档）

存放参考文档，**不是契约**。按子目录分类：

```
docs/
├── architecture/          # 架构设计文档
├── reports/               # 审计报告、评审记录
├── research/              # 调研分析
├── design/                # 设计文档
└── guides/                # 使用指南
```

---

## 第八章 命名规范

| 类型 | 规范 | 示例 |
|------|------|------|
| Python 文件 | `snake_case.py` | `orchestrator.py` |
| 配置文件 | `snake_case.yaml` | `global.yaml` |
| Prompt 文件 | `snake_case.md` | `planner.md` |
| 基础契约 | `snake_case.md` | `coding_standards.md` |
| 场景契约 | `{module}_v{X.Y}.yaml` | `spec_pro_v2.0.yaml` |
| 测试文件 | `test_snake_case.py` | `test_orchestrator.py` |
| 目录（代码） | `snake_case` | `spec_pro/` |
| 目录（skill） | `kebab-case` | `research-pro/`（仅 skills/ 下） |
| 备份文件 | ❌ 禁止 `.bak` `.backup` `.p2-backup` | 用 Git 管理 |

---

## 第九章 迁移状态

### 已完成（2.0.0 → 2.0.0）

| Phase | 内容 | Commit |
|-------|------|--------|
| Phase 1 | 清理技术债（删空目录/deprecated/备份，cage/ 分类） | `9f37d1b` |
| Phase 2 | 重组 core/（15 文件→5 子目录 + 兼容层） | `a963d34` |
| Phase 3 | 迁移 Spec Pro → domains/spec_pro/（自包含） | `e932300` |
| Phase 4 | 迁移 Research Pro / Solution Pro / Investment | `943e9c7` |
| Phase 5 | 整理共享层 + 全量验证 58 项 | `bcd8ee5` |
| 遗留项 1 | coordinator.py 字符串路径修复 | `778e4ec` |
| 遗留项 2 | investment.yaml 合并 | `2e379c9` |
| 遗留项 3 | 删除兼容转发模块 | `11ae8fe` |

### 已完成（2.0.0 新增）

| Phase | 内容 | Commit |
|-------|------|--------|
| Phase 6 | 创建 `contracts/` 目录，迁入基础契约 | `c5f79e9` |
| Phase 7 | 整理 cage/（重命名 deepclaw→research_pro，清理根目录） | `3101cf6`, `85ade79` |
| Phase 8 | 删除 domains/spec_pro/config/spec_pro_v2.0.yaml 双份副本 | `e2e4208` |
| Phase 9 | 创建缺失的场景契约（investment/solution） | `36c60d0` |
| Phase 10 | 创建 contracts/integration/ 跨模块契约 | `36c60d0` |

---

## 第十章 验证

### 10.1 检查清单

| 检查项 | 规则 |
|--------|------|
| 根目录清洁 | 无 `.py`/`.sh`（白名单除外） |
| core/ 无业务 | 无 `spec_pro/`、`solution/` 等域目录 |
| 域自包含 | 每个域有 `prompts/` + `config/` + `tests/` |
| 无 deprecated | 无 `*_deprecated.py`、`*.p2-backup` |
| 无空目录 | — |
| 命名规范 | snake_case（域）/ kebab-case（skill） |
| cage 分离 | 有 `active/` + `archive/`，根目录只有 README.md |
| contracts 完整 | 有 4 个基础契约 + integration/ |
| 无契约双份 | cage/active/ 和 domains/*/config/ 不存同一文件 |
| _overview.md | 每个域有 |

### 10.2 审计节奏

- 每次 PR 跑检查清单
- 违规分级处理：P0 禁止合并，P1 下个 Sprint 修，P2 记技术债

---

## 变更历史

| 版本 | 日期 | 变更 | 评审 |
|------|------|------|------|
| 1.0.0 | 2026-05-30 | 初始版本 | 5 位专家 |
| 2.0.0 | 2026-05-30 | 核心重写：自包含域模式 + core 分组 + 迁移路径 | 4 位专家（Python结构/内聚性/可发现性/技术债） |
| 3.0.0 | 2026-05-30 | 新增 contracts/ 基础契约层 + cage/ 场景契约规则 + 四条铁律 + 迁移状态更新 | 4 位专家（LLM可读性/架构/文档/Python工程） |
| 3.1.0 | 2026-05-30 | 更新 cage/ 场景契约大小限制（complex ≤ 30KB）+ 更新迁移状态（Phase 6-10 已完成） | — |
