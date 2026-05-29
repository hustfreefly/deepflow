# DeepFlow 文件目录系统契约

> **版本**: 1.0.0  
> **生效日期**: 2026-05-30  
> **核心目标**: 规范目录结构，解决文件散乱问题

---

## 第一章 总则

### 1.1 契约目的

本契约定义 DeepFlow 项目的**目录结构规范**，确保：
- 项目结构清晰、可预测
- 新成员快速定位代码
- 避免文件散落和命名混乱
- 支持多业务域并行开发

### 1.2 适用范围

本契约适用于：
- `.deepflow/` 目录下所有文件
- `skills/` 目录下的 DeepFlow 技能
- 所有新增代码和配置

### 1.3 与其他契约的关系

**本契约是目录结构层面的规范**，不覆盖：
- CI/CD 流水线（参考 `.deepflow/cage/cicd_v1.0.yaml`）
- 代码风格（参考 `pyproject.toml` 中的 black/ruff 配置）
- 测试标准（参考 `.deepflow/cage/test_v1.0.yaml`）
- 性能要求（参考 `.deepflow/cage/performance_v1.0.yaml`）

**冲突处理**：如果发现本契约与其他契约存在冲突，应该：
1. 明确列出冲突点
2. 评估哪一方的设计更合理
3. 修改不合理的一方（可能是本契约，也可能是其他契约）
4. 不预设优先级，以整体架构一致性为准

---

## 第二章 目录结构

### 2.1 项目根目录

```
.deepflow/
├── CONSTITUTION.md          # 本宪法
├── README.md                # 项目说明
├── CHANGELOG.md             # 变更日志
├── pyproject.toml           # Python 项目配置
├── .gitignore               # Git 忽略规则
│
├── core/                    # 核心引擎（基础设施层）
├── domains/                 # 业务域（业务逻辑层）
├── skills/                  # 技能模块（能力扩展层）
├── config/                  # 配置管理
├── prompts/                 # Prompt 管理
├── cage/                    # 契约笼子
├── tests/                   # 测试管理
├── docs/                    # 文档管理
├── scripts/                 # 脚本管理
├── tools/                   # 工具集
└── blackboard/              # 运行时数据（不入库）
```

### 2.2 目录职责说明

| 目录 | 职责 | 层级 |
|------|------|------|
| `core/` | 基础设施：状态机、Blackboard、Prompt注册 | 基础设施层 |
| `domains/` | 业务逻辑：Spec Pro、Solution Pro 等 | 业务逻辑层 |
| `skills/` | 能力扩展：Research Pro、Deep Dive 等 | 能力扩展层 |
| `config/` | 配置管理：全局配置、域配置 | 配置层 |
| `prompts/` | Prompt 管理：Prompt 模板、注册表 | 配置层 |
| `cage/` | 契约笼子：契约定义、验证规则 | 质量层 |
| `tests/` | 测试管理：单元、集成、E2E 测试 | 质量层 |
| `docs/` | 文档管理：架构、API、用户文档 | 文档层 |
| `scripts/` | 脚本管理：CI/CD、工具脚本 | 工具层 |
| `tools/` | 工具集：独立工具、CLI | 工具层 |
| `blackboard/` | 运行时数据：状态、日志（不入库） | 数据层 |

### 2.3 红线规则

1. **禁止在根目录创建新目录**（除非修改本宪法）
2. **禁止在 core/ 放置业务逻辑**（业务逻辑必须在 domains/）
3. **禁止在根目录放置独立脚本**（必须放入 scripts/ 或 tools/）
4. **blackboard/ 不入库**（必须加入 .gitignore）

---

## 第三章 核心引擎（core/）

### 3.1 职责

`core/` 是 DeepFlow 的基础设施层，提供所有业务域共享的核心能力：
- 状态机引擎（PipelineOrchestrator）
- Blackboard 管理
- Prompt 注册与管理
- 契约笼子执行
- 路径管理

### 3.2 目录结构

```
core/
├── __init__.py
├── config/
│   ├── __init__.py
│   └── path_config.py        # 跨平台路径管理
├── orchestrators/
│   ├── __init__.py
│   ├── base.py               # Orchestrator 基类
│   ├── pipeline.py           # Pipeline 编排器
│   └── entry.py              # 入口编排器
├── blackboard/
│   ├── __init__.py
│   ├── manager.py            # BlackboardManager
│   └── bridge.py             # Blackboard 桥接
├── prompt/
│   ├── __init__.py
│   ├── registry.py           # Prompt 注册中心
│   └── utils.py              # Prompt 工具
├── cage/
│   ├── __init__.py
│   ├── loader.py             # 契约加载器
│   ├── validator.py          # 契约验证器
│   └── checkpoint.py         # 检查点管理
├── data/
│   ├── __init__.py
│   ├── manager.py            # 数据管理器
│   └── search.py             # 搜索引擎
└── quality/
    ├── __init__.py
    ├── gate.py               # 质量门禁
    └── observability.py      # 可观测性
```

### 3.3 规则

1. **单一职责**：每个文件只做一件事
2. **禁止包含业务逻辑**：业务逻辑必须在 `domains/`
3. **子模块上限**：core/ 子模块数量 ≤ 10 个，超出时应考虑拆分

---

## 第四章 业务域（domains/）

### 4.1 职责

`domains/` 是 DeepFlow 的业务逻辑层，每个子目录代表一个独立的业务域：
- Spec Pro：需求收集与梳理
- Solution Pro：方案设计
- Research Pro：深度研究
- Investment：投资分析

### 4.2 目录结构

```
domains/
├── __init__.py
├── spec_pro/                 # Spec Pro 业务域
│   ├── __init__.py
│   ├── orchestrator.py       # 域 Orchestrator
│   ├── coordinator.py        # 协调器
│   ├── models.py             # 数据模型
│   ├── merge_spec.py         # Spec 合并
│   └── config.yaml           # 域配置
├── solution/                 # Solution Pro 业务域
│   ├── __init__.py
│   ├── orchestrator.py       # 域 Orchestrator
│   ├── task_builder.py       # 任务构建
│   ├── harness_scorer.py     # Harness 评分
│   └── config.yaml           # 域配置
└── research_pro/             # Research Pro 业务域
    ├── __init__.py
    ├── orchestrator.py       # 域 Orchestrator
    └── config.yaml           # 域配置
```

### 4.3 规则

1. **每个域独立**：域之间通过 Blackboard 通信，禁止直接 import
2. **域 Orchestrator 唯一**：每个域只有一个 `orchestrator.py`
3. **域配置隔离**：每个域有自己的 `config.yaml`

---

## 第五章 技能模块（skills/）

### 5.1 职责

`skills/` 是 DeepFlow 的能力扩展层，包含所有技能模块：
- Research Pro：深度研究技能
- Deep Dive：代码审查技能
- DeepClaw：通用研究技能

### 5.2 目录结构

```
skills/
├── research-pro/             # Research Pro 技能
│   ├── __init__.py
│   ├── lib/                  # 核心代码
│   ├── config/               # 配置
│   ├── prompts/              # Prompt
│   └── SKILL.md              # 技能描述
├── deep-dive/                # Deep Dive 技能
│   └── SKILL.md
└── deepclaw/                 # DeepClaw 技能
    └── SKILL.md
```

### 5.3 规则

1. **每个技能独立**：技能之间禁止直接 import
2. **配置隔离**：每个技能有自己的 `config/` 目录
3. **Prompt 隔离**：每个技能有自己的 `prompts/` 目录

---

## 第六章 配置管理（config/）

### 6.1 目录结构

```
config/
├── global.yaml               # 全局配置
├── paths.yaml                # 路径配置
├── timeouts.yaml             # 超时配置
└── data_sources/             # 数据源配置
    ├── investment.yaml
    └── solution.yaml
```

### 6.2 配置优先级

```
环境变量 > global.yaml > domains/*/config.yaml > skills/*/config/ > 代码默认值
```

### 6.3 规则

1. **全局配置唯一**：`global.yaml` 是唯一的全局配置文件
2. **域配置隔离**：每个域有自己的 `config.yaml`
3. **技能配置隔离**：每个技能有自己的 `config/` 目录

---

## 第七章 命名规范

### 7.1 文件命名

| 类型 | 规范 | 示例 |
|------|------|------|
| Python 模块 | `snake_case.py` | `orchestrator.py` |
| 配置文件 | `kebab-case.yaml` | `global.yaml` |
| Prompt 文件 | `snake_case_vX.md` | `planner_v2.md` |
| 契约文件 | `snake_case_vX.X.yaml` | `spec_pro_v2.0.yaml` |
| 测试文件 | `test_snake_case.py` | `test_orchestrator.py` |
| 备份文件 | ❌ 禁止 | 用 Git 管理 |

### 7.2 目录命名

| 类型 | 规范 | 示例 |
|------|------|------|
| 代码目录 | `snake_case` | `spec_pro/` |
| 技能目录 | `kebab-case` | `research-pro/` |
| 文档目录 | `snake_case` | `api/` |

### 7.3 类命名

| 类型 | 规范 | 示例 |
|------|------|------|
| Orchestrator | `XxxOrchestrator` | `SolutionOrchestrator` |
| Manager | `XxxManager` | `BlackboardManager` |
| Validator | `XxxValidator` | `CageValidator` |
| Builder | `build_xxx()` | `build_planner_task()` |

---

## 第八章 迁移规则

### 8.1 迁移优先级

| 优先级 | 动作 | 截止时间 |
|--------|------|----------|
| P0 | 清理备份文件（`.bak`、`.backup`） | 1 天内 |
| P0 | 根目录脚本移入 `tools/` | 1 天内 |
| P0 | 删除 `orchestrator_deprecated.py` | 1 天内 |
| P1 | `core/spec_pro/` 移至 `domains/spec_pro/` | 1 周内 |
| P1 | 合并重复的 Orchestrator | 1 周内 |
| P2 | 配置文件合并到 `config/` | 2 周内 |
| P2 | 文档重新组织到 `docs/` | 2 周内 |
| P3 | 脚本分类到 `scripts/` | 1 个月内 |
| P3 | 测试分类到 `tests/` | 1 个月内 |

### 8.2 迁移原则

1. **原子迁移**：每个迁移步骤必须原子完成，不允许半迁移状态
2. **回滚策略**：每个迁移步骤必须有回滚脚本
3. **影响分析**：迁移前必须分析影响范围
4. **测试验证**：迁移后必须运行测试套件

---

## 第九章 执行与审计

### 9.1 验证脚本

必须实现 `tests/unit/validate_constitution.py`，自动检查：
- 根目录无 `.py`/`.sh` 文件
- 禁止目录不存在
- 命名规范合规
- 配置文件位置正确

### 9.2 定期审计

每个 Sprint 结束时：
1. 运行 `validate_constitution.py`
2. 生成合规报告
3. 修复所有 P0/P1 违规
4. 记录 P2 违规到技术债务清单

### 9.3 违规处理

| 优先级 | 处理方式 | 截止时间 |
|--------|----------|----------|
| P0 | 禁止合并，必须立即修复 | 立即 |
| P1 | 允许合并，但必须排期修复 | 1 个 Sprint |
| P2 | 记录到技术债务清单 | 排期修复 |

---

## 附录：当前状态与目标状态对比

### 当前状态（As-Is）

| 问题 | 数量 | 示例 |
|------|------|------|
| 根目录 .py 文件 | 8 个 | `deepflow.py`, `spec_pro_api.py`, `orchestrator_agent.py` |
| 根目录 .sh 文件 | 5 个 | `ci.sh`, `run_tests.sh` |
| 备份目录 | 3 个 | `cage.backup/`, `skills/deep-research.backup/` |
| 重复 Orchestrator | 5 个 | `core/orchestrator_agent.py`, `domains/solution/orchestrator_agent.py` |
| 配置散落 | 4 处 | `config/`, `core/config/`, `domains/*.yaml`, `skills/*/config/` |

### 目标状态（To-Be）

| 改进 | 验收标准 |
|------|----------|
| 根目录干净 | 无 `.py`/`.sh` 文件 |
| 无备份目录 | 删除所有 `.backup` 目录 |
| Orchestrator 唯一 | 每个域只有一个 `orchestrator.py` |
| 配置集中 | 全局配置在 `config/global.yaml` |

---

## 变更历史

| 版本 | 日期 | 变更 | 评审专家 |
|------|------|------|----------|
| 1.0.0（精简版） | 2026-05-30 | 初始版本，聚焦目录结构 | 架构、DevOps、Python、文档、代码质量 |

---

**本宪法由 5 位专家评审通过，自 2026-05-30 起生效。**
