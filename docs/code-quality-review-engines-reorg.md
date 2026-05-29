# 代码质量专家评审报告

> **评审对象**: DeepFlow 三大核心引擎（Spec Pro / Solution Pro / Research Pro）组织方案
> **评审日期**: 2026-05-30
> **评审人**: 代码质量专家（10年+ 经验）
> **评审依据**: 对实际代码库的导入分析、依赖拓扑、现有契约文档审查

---

## 基线诊断（评审前的实际代码状态）

在评审三个方案之前，先诊断当前代码结构的核心问题：

| 问题 | 现状 | 严重度 |
|------|------|--------|
| **性质误分类** | `spec_pro` 放在 `core/`（基础设施层），但它是有状态的业务逻辑 | 🔴 高 |
| **语义冲突** | `research-pro` 放在 `skills/`（能力扩展层），但它是核心引擎，与 Spec Pro/Solution Pro 同等级 | 🔴 高 |
| **命名不一致** | `spec_pro`（snake_case）vs `solution`（无后缀）vs `research-pro`（kebab-case） | 🟡 中 |
| **内部结构不统一** | `spec_pro/` 是扁平目录（7个 .py 平级）；`solution/` 是中等结构（15个 .py 平级 + data_sources/）；`research-pro/` 有 lib/、config/、prompts/、templates/ 四层子目录 | 🟡 中 |
| **依赖耦合** | 三者都依赖 `core.config.path_config.PathConfig` 和 `core.prompt_registry`，耦合度可接受（依赖基础设施） | 🟢 低 |
| **外部引用散乱** | `tools/spec_pro_api.py`、`scripts/runners/run_spec_pro.py`、多个测试文件硬编码路径 | 🟡 中 |
| **契约冲突** | `DIRECTORY_STRUCTURE_CONTRACT.md`（2026-05-30 生效）第四章已明确定义 `domains/` 包含 "Spec Pro / Solution Pro / Research Pro / Investment"，但代码未对齐 | 🔴 高 |
| **技术债务堆积** | `domains/solution_v2/`（空迁移残留）、`orchestrator.py.p2-backup`（未清理）、`batch_rename.py` 中硬编码旧路径 | 🟡 中 |

**核心结论**: 当前状态是一个"渐进式生长"的产物，三个引擎随时间被放到"当时最方便的位置"，而非有意设计。

---

## 方案 A 评审：全部移到 `engines/`

```
.deepflow/
├── engines/                    ← 新增
│   ├── spec-pro/
│   ├── solution-pro/
│   └── research-pro/
├── core/                       ← 保留基础设施
├── domains/                    ← 保留业务域
└── skills/                     ← 保留技能
```

- **代码可维护性：5/10**
- **重构风险：4/10**
- **技术债务：4/10**
- **代码一致性：6/10**
- **可测试性：6/10**

**优点**:
- 语义最清晰：`engines/` 一眼就知道是"引擎"，不需要理解 core/domains/skills 的语义区分
- 新人友好：所有核心引擎在一个目录下，零认知负担
- 独立于现有分层争议

**问题**:
1. **违反现有契约**: `DIRECTORY_STRUCTURE_CONTRACT.md` 已定义三层架构（core/domains/skills），新增 `engines/` 需要修改契约。如果刚生效就修改，会削弱契约的权威性。
2. **creates a fourth parallel layer**: 现有 `domains/` 还包含 `investment/`（也是业务逻辑）。如果三个引擎去 `engines/`，`investment/` 留在 `domains/` —— 新人又会问"那 investment 算什么？"
3. **依赖关系不变**: 三个引擎都依赖 `core/` 的基础设施（PathConfig、PromptRegistry、Blackboard）。移到 `engines/` 不会改变依赖结构，只是换了目录名。
4. **产生新的技术债务**: 引入第四层级后，未来再加一个引擎（比如 `audit-pro`）时，团队需要再次讨论放 `engines/` 还是 `domains/`。
5. **根目录膨胀**: 根目录已有 15 个子目录（core, domains, skills, config, prompts, cage, tests, docs, scripts, tools, blackboard, frontend, ARCHIVED...），再加 `engines/` 变成 16 个。

**建议**:
- 不推荐。语义清晰度的收益被"违反现有契约"和"引入第四层级"的成本抵消。

---

## 方案 B 评审：全部统一到 `core/`

```
.deepflow/
├── core/
│   ├── spec-pro/
│   ├── solution-pro/
│   ├── research-pro/
│   ├── config/
│   └── agents/
└── domains/                    ← 保留业务域
└── skills/
```

- **代码可维护性：3/10**
- **重构风险：3/10**
- **技术债务：2/10**
- **代码一致性：5/10**
- **可测试性：5/10**

**优点**:
- `spec_pro` 已经在 `core/`，迁移量最小（只需移 solution 和 research-pro 进来）
- 三个引擎与 core 的基础设施（PathConfig、PromptRegistry）在同一个顶级目录下，import 路径稍短

**问题**:
1. **语义严重错误**: `core/` 的定义是"基础设施层"——所有业务域共享的底层能力（状态机、Blackboard、Prompt 注册、契约执行）。Spec Pro / Solution Pro / Research Pro 是**业务逻辑**，不是基础设施。把它们放进 `core/` 违反了单一职责原则和分层架构。
2. **违反现有契约红线**: `DIRECTORY_STRUCTURE_CONTRACT.md` 第 2.3 条红线规则 #2 明确写道："**禁止在 core/ 放置业务逻辑**（业务逻辑必须在 domains/）"。
3. **core/ 已经超载**: 当前 `core/` 有 18 个 .py 文件 + 5 个子目录，已接近契约定义的"子模块上限 ≤ 10 个"。再加三个引擎模块会彻底失控。
4. **投资域无处安放**: `domains/investment/` 也是业务逻辑，如果引擎去 `core/`，investment 留在 `domains/` —— 同一性质的东西放在不同层级。
5. **长期维护成本最高**: 随着引擎增多（未来可能有 audit-pro、compliance-pro 等），`core/` 会越来越臃肿，基础设施和业务逻辑混在一起，新成员根本无法区分哪些是"真正的核心基础设施"。

**建议**:
- **坚决不推荐**。这是三个方案中最差的。它用一个短期迁移成本的节省，换取了长期的架构腐化。

---

## 方案 C 评审：全部统一到 `domains/`

```
.deepflow/
├── domains/
│   ├── spec-pro/
│   ├── solution-pro/
│   ├── research-pro/
│   └── investment/
├── core/                       ← 纯基础设施
└── skills/                     ← 纯可插拔技能
```

- **代码可维护性：8/10**
- **重构风险：6/10**
- **技术债务：8/10**
- **代码一致性：7/10**
- **可测试性：8/10**

**优点**:
1. **与现有契约完全一致**: `DIRECTORY_STRUCTURE_CONTRACT.md` 第四章已经明确定义 `domains/` 是"业务逻辑层"，列举的域正是 "Spec Pro / Solution Pro / Research Pro / Investment"。这是**对齐代码与契约**，不是重新设计。
2. **语义正确**: 三个引擎是业务逻辑（需求梳理、方案设计、深度研究），放在业务逻辑层是架构上正确的选择。
3. **层次清晰**: `core/` = 基础设施（谁都不用理解业务逻辑也能看懂）；`domains/` = 业务域（每个域独立封装）；`skills/` = 能力扩展（可选插拔）。三层职责互不重叠。
4. **扩展性好**: 未来加新引擎（audit-pro、compliance-pro），自然放在 `domains/`，不需要讨论。
5. **测试友好**: `tests/` 已经按域组织（`tests/research_pro/` 已存在），迁移后 `tests/<domain_name>/` 的映射更自然。

**问题**:
1. **迁移量最大**: `spec_pro` 从 `core/` 移出（最多 import 变更），`research-pro` 从 `skills/` 移出（目录名和内部结构需要调整）。需要修改的引用点估计 30-50 处。
2. **research-pro 内部结构特殊**: 当前 `research-pro/` 有 `lib/`、`config/`、`prompts/`、`templates/` 四层子目录，而 `spec_pro/` 是扁平的。统一到 `domains/` 时需要决定是否统一内部结构。
3. **`domains/solution` 没有 `-pro` 后缀**: 命名需要统一为 `solution-pro`（kebab-case 与 `research-pro` 一致）还是 `solution_pro`（snake_case 与 `spec_pro` 一致）？
4. **`investment/` 语义层级问题**: investment 是一个具体业务域（投资分析），而 spec-pro/solution-pro/research-pro 是"引擎"。把它们放在同一目录下，需要文档说明它们的区别。

**建议**:
1. **统一命名**: 建议全部采用 `kebab-case`（`spec-pro`、`solution-pro`、`research-pro`），与 `skills/` 目录的命名风格一致，同时避免 Python 模块名（`import` 用 `snake_case`）和目录名的冲突。
2. **统一内部结构**: 为 `domains/` 下的每个引擎定义标准子目录结构：
   ```
   domains/<engine-name>/
   ├── __init__.py
   ├── orchestrator.py        # 域协调器（唯一入口）
   ├── models.py              # 数据模型
   ├── config/                # 域配置
   ├── prompts/               # 域 Prompt
   └── SKILL.md               # 引擎说明文档
   ```
3. **分阶段迁移**: 见下方迁移建议。

---

## 最终推荐

### 推荐方案 C（统一到 `domains/`），理由如下：

| 维度 | 方案 A (engines/) | 方案 B (core/) | 方案 C (domains/) ⭐ |
|------|:-:|:-:|:-:|
| 语义正确性 | ⚠️ 第四层级 | ❌ 违反分层 | ✅ 契约一致 |
| 与现有契约关系 | ❌ 需修改契约 | ❌ 违反红线 | ✅ 对齐契约 |
| 长期可维护性 | ⚠️ 中等 | ❌ 最差 | ✅ 最佳 |
| 迁移成本 | 中等 | 最低 | 最高 |
| 技术债务趋势 | 持平 | 恶化 | 减少 |
| 扩展性 | ⚠️ 需讨论 | ❌ core 膨胀 | ✅ 自然扩展 |

**核心论据**:

1. **契约优先**: `DIRECTORY_STRUCTURE_CONTRACT.md` 已经定义了正确的目标结构。方案 C 是让代码**对齐契约**，方案 A 是让契约**迁就代码**，方案 B 是让架构**倒退**。
2. **分层架构的基本原则**: 基础设施（core）应该是稳定的、通用的、与业务无关的。业务逻辑（domains）是可变的、特定的。把引擎放到 core 违反了依赖倒置原则。
3. **认知负担最低的路径**: 不是让目录名最直观（方案 A），而是让**现有框架保持一致**。一旦契约定义了三层的语义，所有新成员只需要记住一条规则："业务逻辑放 domains/"，不需要判断某个模块算不算"引擎"。

---

## 附：建议的分阶段迁移计划

### Phase 1（P0，1-2 天）：清理技术债务
- 删除 `orchestrator.py.p2-backup` 等备份文件
- 删除或归档 `domains/solution_v2/`
- 清理 `__pycache__/` 中不需要的缓存
- 运行现有测试套件，记录基线

### Phase 2（P1，1 周）：迁移 spec_pro → domains/spec-pro
1. 创建 `domains/spec-pro/`
2. 移动 `core/spec_pro/` 的所有 .py 文件
3. 更新 import 路径（`core.spec_pro` → `domains.spec_pro`）
4. 更新引用点：
   - `tools/spec_pro_api.py`
   - `scripts/runners/run_spec_pro.py`
   - `core/unified_entry.py`（如有引用）
5. 运行测试，验证通过
6. 从 `core/` 删除旧目录

### Phase 3（P1，1 周）：迁移 research-pro → domains/research-pro
1. 创建 `domains/research-pro/`
2. 移动 `skills/research-pro/` 的所有内容
3. 更新 `SKILL.md` 中的路径引用
4. 更新测试路径 `tests/research_pro/`（或移至 `tests/research-pro/`）
5. 运行测试，验证通过
6. 从 `skills/` 删除旧目录

### Phase 4（P2，1-2 周）：统一内部结构和命名
1. 为三个引擎定义统一的标准子目录结构
2. 统一命名（建议 `kebab-case` 目录名 + `snake_case` 模块名）
3. 更新 `DIRECTORY_STRUCTURE_CONTRACT.md` 中的结构示例
4. 实现 `tests/unit/validate_constitution.py`（契约第 9.1 条）

### 每个 Phase 的回滚策略
- 每次迁移前 `git commit` 当前状态
- 迁移后运行全量测试
- 测试失败 → `git revert`，排查后重试
