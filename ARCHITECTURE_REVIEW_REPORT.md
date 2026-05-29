# 架构专家评审报告

## 总体评分：7/10

宪法草案整体设计方向正确，14 章覆盖了绝大多数关键关注点。但存在与现状严重脱节、部分章节过度理想化、迁移工作量被低估等问题。

---

## 维度 1：整体结构合理性（7/10）

**优点**：
- 14 章的划分基本合理，从目录→核心→业务→技能→配置→Prompt→契约→测试→文档→脚本→工具→命名→迁移→审计，逻辑链条完整
- 第一章明确禁止的目录清单很好（output/state/checkpoints → blackboard，data/industries/reviews → archive 等），减少歧义
- 第十四章的审计机制（Sprint 末运行宪法验证脚本 + P0/P1/P2 分级违规处理）是可执行的闭环

**问题**：
- **frontend/ 目录被完全忽略**。当前项目存在完整的 frontend/ 子项目（含 backend、frontend、web、data、task_queue 五个子目录 + README/STATUS），但宪法中没有任何章节处理前端代码的归属
- **agents/、cron/、pipelines/ 三个目录在宪法中没有对应位置**。当前它们存在于根目录，但按第一章的"禁止目录"规则，它们应该归入哪里？没有明确答案
- `tools/`（第十一章）的定位模糊。宪法说"工具集是对外入口"，但 `core/orchestrators/entry.py` 也是入口，`deepflow_cli.py` 和 entry 编排器的边界不清
- **缺少 CI/CD 章节**。第十章 scripts/ci/ 有 ci.sh，但 .github/workflows、lint 规则、pre-commit hooks 等现代工程实践未涉及

**建议**：
1. 增加"第十五章：前端与基础设施"或将 frontend/ 纳入 domains/ 或独立章节
2. 明确 agents/、cron/、pipelines/ 的归属（建议：agents→core/ 或 scripts/，cron→scripts/，pipelines→core/orchestrators/）
3. 补充 CI/CD 章节（lint、pre-commit、PR 检查）
4. 澄清 tools/ vs core/orchestrators/entry.py 的边界

---

## 维度 2：职责分离（7/10）

**优点**：
- core/domains/skills 三层架构方向正确：core=基础设施、domains=业务逻辑、skills=可插拔能力
- "一个域一个 orchestrator.py"规则简洁有力，直接打击当前 solution/ 下 orchestrator_agent.py + orchestrator_deprecated.py 的重复问题
- Orchestrator 基类 + pipeline.py + entry.py 的分层设计合理

**问题**：
- **core/spec_pro/ 的存在破坏了职责分层**。Spec Pro 是一个业务域，按第三章应放入 domains/spec_pro/，但现在放在 core/ 下。这导致 core 不再是"纯基础设施"
- **core/ 下的文件粒度不统一**。对比：
  - `blackboard/manager.py` 和 `blackboard/bridge.py`（合理拆成子目录）
  - `blackboard_manager.py` 和 `blackboard_bridge.py`（平铺在 core/ 根下）
  - 宪法 2.2 说要拆成 `core/blackboard/` 子目录，但当前 21 个 .py 文件全部平铺在 core/ 根下
- **task_builder.py 的职责归属模糊**。它在 core/ 下，但 solution 域也有自己的 task_builder.py。哪个是权威来源？
- **orchestrator 的种类过多且边界不清**：`orchestrator_base.py`、`orchestrator_agent.py`、`pipeline_orchestrator.py`、`entry_harness.py`、`master_agent.py`——宪法 2.3 说"同一类型只有一个文件"，但这些文件之间的类型区分没有定义
- **Internal Skills 的 lib/ 代码与 core/ 代码的关系未定义**。Internal Skill 的 orchestrator.py 和 domain 的 orchestrator.py 是否应该复用 core 基类？

**建议**：
1. 将 core/spec_pro/ 移至 domains/spec_pro/，或重新定义 core 的职责为"共享基础设施 + 部分核心业务域"
2. 定义 orchestrator 类型矩阵：Base（基类）、Pipeline（Phase 调度）、Domain（业务域入口）、Entry（用户入口），明确每种只存在一个
3. 明确 task_builder 的归属：共享逻辑放 core/，域特定逻辑放 domains/*/
4. 定义 Internal Skill 与 domain orchestrator 的关系图（继承？组合？）

---

## 维度 3：可扩展性（8/10）

**优点**：
- 新增业务域路径清晰：在 domains/ 下创建目录 + orchestrator.py + config.yaml 即可
- Internal Skills 的 `lib/` + `prompts/` + `config/` + `templates/` 标准结构可复用
- 配置优先级链（环境变量 > global.yaml > domain config > 默认值）是业界标准做法，支持多环境

**问题**：
- **domain config.yaml 与 config/data_sources/ 的关系不明确**。宪法第五章说数据源配置在 config/data_sources/，但第三章要求每个域有自己的 config.yaml。如果一个域需要数据源配置，应该写在哪？
- **没有域间通信机制的定义**。如果 investment 域需要调用 solution 域的能力，或者两个域共享 blackboard 数据，规则是什么？
- **Prompt 注册表的可扩展性存疑**。第六章要求所有 Prompt 在 registry.yaml 中注册，但当前 prompts/registry.yaml 的内容量未知。如果每个域有 10+ 个 Prompt 文件，registry.yaml 会变成单点瓶颈
- **缺少版本兼容策略**。新增域时，如何确保它使用正确版本的 core API？没有版本约束机制

**建议**：
1. 明确数据源配置的归属规则：域特定的数据源配置放 domains/*/config.yaml，共享的放 config/data_sources/
2. 增加"域间通信"章节或规则：定义 blackboard 作为域间数据交换的唯一通道
3. registry.yaml 改为分层结构：主注册表只索引子注册表（如 prompts/solution/registry.yaml）
4. 在 pyproject.toml 或 core/__init__.py 中定义 core API 版本号，domain 可声明依赖范围

---

## 维度 4：迁移可行性（5/10）

**优点**：
- P0→P1→P2→P3 的优先级分层合理：先清理垃圾文件，再处理关键重构
- "新增文件必须遵守宪法"的渐进式策略（13.1）正确

**问题**：
- **严重低估了 P0 的工作量**。当前根目录有 9 个 .py 文件 + 5 个 .sh 文件 + 1 个 .json + 16+ 个禁止目录 + .bak 文件。这些 P0 项每一项都涉及 import 路径变更和测试更新
- **P1 "合并 Orchestrator"是破坏性变更但未提及影响分析**。当前 solution/ 下有 orchestrator_agent.py、planner.py 等多个编排文件，investment/ 下有 cage_orchestrator.py、orchestrator_deprecated.py。合并后哪些代码被删除？功能是否有覆盖测试？
- **未定义回滚策略**。如果迁移导致运行失败，如何回退？宪法 13.2 没有提到 git tag、备份快照或回滚计划
- **缺少迁移验证清单**。宪法 14.1 提到 validate_constitution.py，但这是迁移后运行的。迁移过程中的每个步骤应该有独立的验证脚本
- **P1 "统一 Skills 位置"涉及 research-pro 的位置变更**，当前它在 .deepflow/skills/ 但宪法第四章说 OpenClaw Skills 在 workspace/skills/。这个迁移是否意味着 research-pro 需要同时存在于两个位置？还是完全迁移？
- **cage.backup/ 目录有 30+ 个文件**。宪法 1.2 和 7.2 都禁止它，但 P0 迁移中只说"清理备份和遗留文件"，没有指定 cage.backup/ 是删除还是归档

**建议**：
1. 在 P0 之前增加 P-1 阶段：建立完整的迁移快照（git tag + 运行当前测试基线）
2. 每个 P0/P1 迁移项增加具体的影响分析：涉及的 import 路径变更清单、需要更新的测试
3. 明确 cage.backup/ 处理方式：保留到 docs/archive/ 还是直接删除
4. 为 research-pro 的迁移路径做明确决策：作为 OpenClaw Skill 还是 Internal Skill
5. 迁移每个阶段增加"回归测试"步骤，确保已迁移部分不影响未迁移部分

---

## 维度 5：与现状的匹配度（6/10）

**优点**：
- 宪法直接针对当前项目的核心痛点：根目录散落文件、备份文件遍地、orchestrator 重复、配置散落、文档 33 个文件平铺
- 第一章的"禁止目录"清单完全基于当前真实存在的混乱目录（output、state、data、data_providers 等确实存在）
- "一个域一个 orchestrator"直接解决 solution/ 下 orchestrator_agent.py + orchestrator_deprecated.py 的问题

**问题**：
- **过度设计风险：core/ 的 5 个子目录全是规划中的，当前不存在**。宪法 2.2 定义了 core/orchestrators/、core/blackboard/、core/data/、core/quality/、core/prompt/ 五个子目录，但当前 core/ 下 21 个文件全部平铺。这意味着宪法描述的是一个"目标状态"而非"当前 + 渐进"
- **命名规范（第十二章）过于严格**。契约文件名用 `snake_case_vX.X.yaml` 的格式（如 `solution_orchestrator_v3_1.yaml`）在实践中不常用，版本号用 v3_1 而不是 v3.1 的约定容易出错
- **缺少 .gitignore 定义**。宪法没提到 .gitignore 应该包含什么。当前项目有 __pycache__/、*.bak、.DS_Store 等应该被忽略的文件
- **"禁止 33 个文件平铺"（第九章）和"禁止 25 个文件平铺"（第十章）是描述性规则而非可执行规则**。这些数字从何而来？如何验证？
- **frontend/ 的完全缺失**（已在维度 1 提及）是宪法与现状最大的脱节。一个有 5 个子目录的完整前端项目被宪法忽略了
- **config/ 的文件名不一致**。当前是 global_config.yaml、timeout_config.yaml（下划线），宪法第五章定义为 global.yaml、timeouts.yaml（无 _config 后缀）。这个差异会导致迁移时的混淆

**建议**：
1. 宪法应描述"目标状态 + 过渡路径"而非仅描述最终形态。对 core/ 子目录标注"待创建"状态
2. 补充 .gitignore 模板（包含 __pycache__/、*.pyc、.DS_Store、.bak*、*.backup、deepflow.db）
3. 统一 config 文件命名约定：宪法定义为 global.yaml，但当前是 global_config.yaml，需要明确迁移时的 rename 规则
4. 将"禁止 N 个文件平铺"改为可执行的规则（如脚本检查或 CI lint 规则）
5. 增加 frontend/ 章节或将其纳入宪法范围

---

## 关键建议（Top 3）

1. **补充前端与基础设施章节**：frontend/、agents/、cron/、pipelines/ 占当前项目相当大比重，宪法忽略它们会导致迁移时这些目录无处安放。建议新增"第十五章：前端与 CI/CD"或在各章中明确其归属。

2. **将 P0/P1 迁移细化为带影响分析的执行清单**：每个迁移项应列出具体的文件变更清单、import 路径变更、需要更新的测试、回滚策略。当前 13.2 只有一行描述，无法指导实际执行。

3. **解决 core/spec_pro/ 的职责冲突**：Spec Pro 作为业务域放在 core/ 下违反了 core = 基础设施的原则。要么移到 domains/spec_pro/，要么在第二章明确 core 可以容纳"核心业务域"。二选一，不能悬而未决。

---

## 总体评价

宪法草案的设计方向正确，14 章覆盖了项目结构的主要关注点，红线规则（禁止 .py/.sh 在根目录、一个域一个 orchestrator、备份用 Git）切实可行。主要不足在于：（1）完全忽略了 frontend/ 及相关基础设施目录，导致迁移时这些文件无处安放；（2）core/ 子目录结构是目标状态而非渐进路径，与当前 21 个文件平铺的现状差距巨大；（3）迁移策略缺乏影响分析、回滚计划和验证清单，执行风险高。建议在补充前端章节、细化迁移清单、明确 core/spec_pro/ 归属后再进入评审通过阶段。
