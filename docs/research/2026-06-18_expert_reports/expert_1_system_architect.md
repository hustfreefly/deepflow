# 专家报告 1：系统架构师视角（DDD + 分层架构）

> **作者**: 专家 1 — 系统架构师（DDD / 分层架构 / 关注点分离）
> **日期**: 2026-06-18
> **输入**: `2026-06-18_architecture_redesign_context.md`
> **参考**: DDD ACL/Context Map, DTO/DO/VO 模式, Saga 编排模式

---

## 一、核心诊断：当前架构的本质问题

### 1.1 用 DDD 视角看当前架构

当前 DeepFlow 的三个模块实际上是三个 **Bounded Context**，各自有不同的 Ubiquitous Language：

| 模块 | Bounded Context | 语言 | 核心概念 |
|------|----------------|------|----------|
| Solution Pro | 方案设计上下文 | 架构语言 | Module, Pattern, Tech Stack, Layer, Responsibility |
| Ship Pro | 执行规划上下文 | 项目管理语言 | Work Package, Milestone, Dependency, Phase, Constraint |
| Super Loop | 代码执行上下文 | 工程实施语言 | Task, File, Function, Test, Build Step |

**核心问题**：当前的 `frozen_blueprint.json` 试图充当 Solution Pro → Ship Pro 的 **共享内核（Shared Kernel）**，但它既不是好的 Shared Kernel（信息在丢失），也不是好的 ACL（没有翻译，只有退化复制）。

### 1.2 用 DTO/DO/VO 模式类比

| 传统分层架构 | DeepFlow 对应 | 状态 |
|-------------|--------------|------|
| Domain Object（最丰富） | `final_result.json` | ✅ 信息最完整 |
| DTO（跨层传输） | `frozen_blueprint.json` | ❌ 序列化时丢数据 |
| View Object（展示层定制） | `ship_package.json` | ❌ 没有增值，只是换了字段名 |

**问题本质**：`frozen_blueprint` 作为 DTO，在"序列化"过程中丢失了 Domain Object（final_result）的大量关键信息。这就像把一个包含 372 个字段的 Domain Object 序列化成一个只剩空壳的 DTO——不是抽象，是**信息截肢**。

### 1.3 用 Saga 模式类比

整个流程是一个 **长程任务编排**（类似 Saga）：

```
Solution Pro [本地事务₁] → Contract → Ship Pro [本地事务₂] → Contract → Super Loop [本地事务₃]
```

Saga 模式的核心教训：
- 每个步骤之间的 **契约必须自洽**——下游不需要回溯上游的内部数据
- 如果下游需要上游的"原始数据"，说明契约设计失败
- **编排者（Orchestrator）负责上下文传递**，而不是让下游自己去翻上游的日志

当前问题：Ship Pro 被迫直接读 frozen_blueprint（一个退化的 DTO），而不是从 Solution Pro 获得一个完整的、面向 Ship Pro 需求设计的契约。

---

## 二、对 Q1-Q4 的明确建议

### Q1: Blueprint 层是否保留？

**我的建议：选项 C — 重新设计，但改变其角色**

不再把 Blueprint 当作"最终产物的退化副本"，而是把它重新定位为 **Solution Pro 的正式输出契约（Published Language）**。

具体来说：

| 维度 | 当前 frozen_blueprint | 重新设计后 |
|------|---------------------|-----------|
| 角色 | final_result 的副本 | Solution Pro 的正式交付物 |
| 信息完整度 | 丢信息 | 100% 覆盖 final_result 的关键决策 |
| 格式 | 和 final_result 同构但缩水 | 面向 Ship Pro 需求设计的专用结构 |
| 谁定义格式 | Solution Pro 内部 | Solution Pro 和 Ship Pro 共同约定的 Contract |

**关键设计决策**：不再存在 `living_blueprint` 和 `frozen_blueprint` 两个版本。只有一个 **Design Blueprint**，它是 Solution Pro 完成时的快照，也是 Ship Pro 的唯一输入。

**为什么不是选项 B（砍掉 Blueprint，Ship Pro 直接消费 final_result）？**

因为 `final_result` 是 Solution Pro 的 **内部 Domain Object**——它的结构反映的是 Solution Pro 的 10 阶段管线逻辑，而不是 Ship Pro 的需求。让 Ship Pro 直接消费 final_result，就像让 View 层直接操作 Domain Entity——短期可行，长期必然导致：
- Ship Pro 需要理解 Solution Pro 的内部结构（耦合）
- Solution Pro 改内部结构 → Ship Pro 崩（脆弱）
- 没有翻译层 → 语义泄漏

**这正是 ACL 存在的意义。**

### Q2: Solution Pro 应该输出什么？

**我的建议：两个产物，一个内部，一个外部**

```
Solution Pro 输出：
├── [内部] final_result.json     — 完整的 Domain Object（保留所有 372 个字段）
└── [外部] design_blueprint.json — Published Language（面向下游的正式契约）
```

**design_blueprint.json 应该包含什么？**

按 DDD 的 Published Language 模式，它应该包含 Ship Pro 做"执行规划"所需的 **全部决策信息**，但不包含 Solution Pro 的内部过程数据：

```json
{
  "schema_version": "2.0",
  "project_identity": {
    "name": "跨境AI算力中转站",
    "type": "全栈Web应用",
    "domain": "跨境支付 + AI算力调度"
  },
  "architecture_decisions": [
    {
      "id": "AD-001",
      "title": "API网关选型",
      "decision": "New API",
      "rationale": "支持多供应商并行...",
      "constraints": ["响应时间 < 500ms", "需支持流式传输"]
    }
  ],
  "module_designs": [
    {
      "id": "MOD-001",
      "name": "用户认证模块",
      "tier": "backend",
      "responsibilities": ["JWT签发", "OAuth2对接", "会话管理"],
      "tech_stack": { "language": "Node.js", "framework": "Express", "db": "PostgreSQL" },
      "interfaces": {
        "provides": ["POST /auth/login", "POST /auth/refresh"],
        "depends_on": ["MOD-003 (数据库层)"]
      },
      "complexity": "medium",
      "estimated_effort_hint": "3-5天"
    }
  ],
  "integration_points": [
    {
      "from": "MOD-001",
      "to": "MOD-002",
      "protocol": "REST",
      "contract": "JWT Token 格式..."
    }
  ],
  "delivery_guidance": {
    "suggested_phases": [
      {
        "phase": 1,
        "name": "核心基础设施",
        "modules": ["MOD-003", "MOD-001"],
        "duration_hint": "Day 1-5",
        "milestones": ["数据库schema确定", "认证链路跑通"]
      }
    ],
    "dependency_graph": ["MOD-003 → MOD-001 → MOD-002"],
    "parallelizable_groups": [["MOD-004", "MOD-005"]]
  },
  "non_functional_requirements": {
    "performance": "...",
    "security": "...",
    "deployment": "Docker on Railway"
  },
  "traceability": {
    "requirement_to_module": { "REQ-001": "MOD-001", "REQ-002": "MOD-002" }
  }
}
```

**关键原则**：
- **信息不丢失**：final_result 中的每一个对下游有用的字段，都必须出现在 blueprint 中（可能以不同的结构）
- **面向消费者设计**：blueprint 的结构应该按 Ship Pro 的需求来组织，而不是 Solution Pro 的内部管线逻辑
- **决策可追溯**：每个设计决策都有 rationale，Ship Pro 可以据此做权衡

### Q3: Ship Pro 应该做什么？

**我的建议：从"格式转换器"升级为"执行规划引擎"**

当前 Ship Pro 的问题不是代码写得不好，而是 **职责定义不清**。它应该做以下 **增值工作**：

```
Ship Pro 的核心职责（从架构师视角）：

1. 任务分解（Decomposition）
   - 把 module_design 分解为可执行的 work_packages
   - 每个 WP 有明确的输入、输出、验收标准
   - 不是简单复制 summary，而是理解 responsibility 后拆解

2. 依赖解析（Dependency Resolution）
   - 从 module.interfaces.depends_on 推导 WP 之间的依赖
   - 生成拓扑排序后的执行顺序
   - 识别可并行的 WP 组

3. 约束传递（Constraint Propagation）
   - 从 architecture_decisions.constraints 提取每个 WP 的技术约束
   - 从 non_functional_requirements 提取全局约束
   - 约束不是"上游未提供"，而是必须从 blueprint 中推导

4. 执行引擎适配（Engine Adaptation）
   - 根据目标引擎（Hermes/Codex/Claude Code）调整 WP 格式
   - 不同引擎有不同的 AC 粒度、上下文窗口、工具链
   - 这是忠礼强调的"通用中间层"角色

5. 集成检查点设计（Integration Checkpoint Design）
   - 在模块边界定义集成测试点
   - 设计回归验证策略
```

**Ship Pro 不应该做什么**：
- ❌ 不应该重新做架构决策（那是 Solution Pro 的事）
- ❌ 不应该写代码（那是 Super Loop 的事）
- ❌ 不应该简单复制字段（那是搬运工的事）

### Q4: 三个模块的数据流最优设计？

**我的建议：三层契约 + 两层 ACL**

```
┌─────────────────────────────────────────────────────────────────┐
│                     DeepFlow 架构数据流                          │
│                                                                 │
│  ┌──────────────┐    Design Blueprint     ┌──────────────┐     │
│  │ Solution Pro │ ──────────────────────→  │   Ship Pro   │     │
│  │  (架构师)     │    [Published Language]  │  (项目经理)   │     │
│  │              │                         │              │     │
│  │ 内部：        │    ← 反馈通道 →          │ 内部：        │     │
│  │ final_result │    (可行性/约束回传)       │ execution_   │     │
│  │ living_bp    │                         │ plan.json    │     │
│  └──────────────┘                         └──────┬───────┘     │
│                                                  │             │
│                                     Ship Package │             │
│                                   [Engine DTO]   │             │
│                                                  ↓             │
│                                          ┌──────────────┐     │
│                                          │ Super Loop   │     │
│                                          │  (施工队)     │     │
│                                          │              │     │
│                                          │ 消费 WP，     │     │
│                                          │ 产出代码+结果  │     │
│                                          └──────────────┘     │
│                                                                 │
│  数据流语义：                                                    │
│  final_result ─[ACL翻译]→ Design Blueprint ─[ACL翻译]→ Ship Pkg │
│  (Domain Obj)             (Published Lang)       (Engine DTO)  │
└─────────────────────────────────────────────────────────────────┘
```

**两次 ACL 翻译**：

| 翻译点 | 源语言 | 目标语言 | 翻译内容 |
|--------|--------|---------|---------|
| ACL₁: Solution Pro → Ship Pro | 架构语言（module, pattern, layer） | 项目管理语言（WP, milestone, dependency） | 模块设计 → 工作包；架构约束 → 技术约束；依赖图 → 拓扑排序 |
| ACL₂: Ship Pro → Super Loop | 项目管理语言 | 执行引擎语言（task, file, command） | WP → 具体 task；AC → 测试断言；约束 → lint/格式规则 |

**反馈通道**（当前架构缺失）：
- Ship Pro → Solution Pro：当 blueprint 中的设计不可执行时（技术约束冲突、依赖循环），Ship Pro 应该能请求 Solution Pro 修订
- Super Loop → Ship Pro：当 WP 执行受阻时，请求调整计划

---

## 三、推荐的架构数据流图（详细版）

```
                          ┌─────────────────────────────┐
                          │      Spec Pro (需求收集)      │
                          │  输出: spec.json             │
                          └──────────────┬──────────────┘
                                         │ spec.json
                                         │ [Requirements Contract]
                                         ▼
┌──────────────────────────────────────────────────────────────────┐
│                    Solution Pro (架构师)                          │
│                                                                  │
│  ┌─────────┐   ┌─────────┐   ┌─────────┐   ┌─────────┐        │
│  │ 阶段1-3  │──→│ 阶段4-6  │──→│ 阶段7-9  │──→│ 阶段10  │        │
│  │ 需求分析 │   │ 架构设计 │   │ 方案评审 │   │ 输出生成 │        │
│  └─────────┘   └─────────┘   └─────────┘   └────┬────┘        │
│                                                   │              │
│  内部产物（保留，不对外暴露）：                        │              │
│  ├── execution_plan.json  (执行计划)                │              │
│  ├── control_contract.json (控制契约)               │              │
│  ├── tasks.json (内部任务)                          │              │
│  └── final_result.json (完整Domain Object)         │              │
│                                                    │              │
│  外部产物（正式输出）：                                 │              │
│  └── design_blueprint.json ────────────────────────┘              │
│      [Published Language / Design Contract]                       │
│      包含：架构决策 + 模块设计 + 依赖图 + 交付指导 + NFR            │
└──────────────────────────────┬───────────────────────────────────┘
                               │ design_blueprint.json
                               │
                    ┌──────────┴──────────┐
                    │   ACL₁ 翻译边界      │
                    │                     │
                    │  架构语言            │
                    │    ↓                │
                    │  项目管理语言         │
                    └──────────┬──────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│                    Ship Pro (项目经理)                            │
│                                                                  │
│  输入：design_blueprint.json (唯一外部输入)                        │
│  可选输入：engine_config.json (目标引擎配置)                        │
│                                                                  │
│  ┌─────────────────────────────────────────────────────┐        │
│  │ 核心处理逻辑                                          │        │
│  │                                                      │        │
│  │ 1. 任务分解：module → work_package                    │        │
│  │ 2. 依赖拓扑排序                                       │        │
│  │ 3. 约束提取与传播                                      │        │
│  │ 4. 里程碑/检查点设计                                    │        │
│  │ 5. 引擎适配（Hermes/Codex/Claude Code 格式）           │        │
│  │ 6. 验收标准生成                                        │        │
│  └───────────────────────┬─────────────────────────────┘        │
│                          │                                       │
│  输出：ship_package.json │                                       │
│  [Engine-Specific DTO]   │                                       │
└──────────────────────────┼───────────────────────────────────────┘
                           │
                           │ ship_package.json
                           │
                ┌──────────┴──────────┐
                │   ACL₂ 翻译边界      │
                │                     │
                │  项目管理语言         │
                │    ↓                │
                │  执行引擎语言         │
                └──────────┬──────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│                    Super Loop (施工队)                            │
│                                                                  │
│  输入：ship_package.json                                          │
│  执行引擎：Hermes / Codex / Claude Code                           │
│                                                                  │
│  输出：代码 + 测试结果 + 执行报告                                    │
└──────────────────────────────────────────────────────────────────┘
```

---

## 四、最重要的 3 个设计决策

### 决策 1：Design Blueprint 作为 Published Language（最关键）

**决策**：design_blueprint.json 是 Solution Pro 的 **正式对外契约**，其 schema 由 Solution Pro 和 Ship Pro 共同定义，任何一方修改 schema 都需要双方协商。

**理由**：
- 这是两个 Bounded Context 之间的 **Shared Kernel**
- 当前 frozen_blueprint 的问题不是"不该存在"，而是"它不是一个好的契约"——信息丢失、结构不合理、没有版本控制
- Published Language 模式要求：schema 显式、版本化、双向协商
- 这解决了信息丢失的根因：不是"修复序列化逻辑"，而是"重新设计契约"

**实施影响**：
- 需要定义 `design_blueprint.schema.json`（JSON Schema）
- Solution Pro 的"阶段10 输出生成"需要按 schema 输出，而不是随意生成
- Ship Pro 只需要理解 blueprint schema，不需要理解 Solution Pro 内部

### 决策 2：Ship Pro 的唯一输入是 Design Blueprint（解耦关键）

**决策**：Ship Pro **不读** final_result.json、不读 living_blueprint、不读 tasks.json。它的唯一外部输入是 design_blueprint.json。

**理由**：
- 这是 Anti-Corruption Layer 的核心价值：**隔离**
- 如果 Ship Pro 直接读 final_result，那 blueprint 层就形同虚设
- 如果 blueprint 缺信息，正确做法是 **扩展 blueprint schema**，而不是让 Ship Pro 去翻 Solution Pro 的内部文件
- 这迫使团队在 blueprint 层面解决信息传递问题，而不是在下游打补丁

**实施影响**：
- Ship Pro 代码中不应该有任何 `readFileSync('final_result.json')` 
- 如果 Ship Pro 发现 blueprint 中缺少必要信息，应该报错并请求 Solution Pro 补充，而不是自己去捞
- 这类似于微服务中"服务只能通过 API 访问其他服务的数据，不能直连数据库"

### 决策 3：Ship Package 是 Engine-Specific DTO（适配层）

**决策**：ship_package.json 的格式 **按目标执行引擎定制**，而不是一个通用格式。Ship Pro 内部有一个"引擎适配器"模块，负责把 blueprint 翻译为特定引擎的 DTO。

**理由**：
- 不同的执行引擎有不同的能力边界（上下文窗口大小、工具链、AC 粒度）
- 一个"通用" ship_package 要么太抽象（引擎无法直接使用），要么太具体（无法适配新引擎）
- DTO per Consumer 模式：每个消费者有自己的数据格式
- 忠礼说"Ship Pro 是通用中间层"——通用性体现在 **理解任何 blueprint**，而不是 **产出一个万能格式**

**实施影响**：
```
ship_package_hermes.json    — 适配 Hermes 格式
ship_package_codex.json     — 适配 Codex 格式  
ship_package_claude_code.json — 适配 Claude Code 格式
```
- Ship Pro 需要一个 `engine_config.json` 来指定目标引擎
- 新增引擎 = 新增一个适配器，不改核心逻辑

---

## 五、最大风险

### 风险 1：Blueprint Schema 设计失败（最高风险）

**描述**：design_blueprint 的 schema 设计是一个 **需要反复迭代** 的过程。如果第一次设计就试图覆盖所有场景，会过度复杂；如果太简单，又回到信息丢失的老路。

**缓解策略**：
- 用 3-5 个真实项目案例驱动 schema 设计（不是凭空设计）
- Schema 版本化（v1, v2...），允许演进
- 每次 Solution Pro 跑完，自动验证 blueprint 是否符合 schema
- Ship Pro 消费 blueprint 时，如果缺信息，记录"missing field report"反馈给 schema 设计

### 风险 2：Solution Pro 的 10 阶段管线重构阻力

**描述**：当前 Solution Pro 的 10 阶段管线已经深度耦合了 final_result 的结构。要让它在"阶段10"输出一个全新的 design_blueprint（而不是现在的 frozen_blueprint），可能需要大量重构。

**缓解策略**：
- 不需要重构 10 阶段管线本身
- 只需要重构"阶段10 输出生成"的逻辑
- 可以先写一个 `blueprint_generator.js`，输入 final_result，输出 design_blueprint
- 验证通过后再集成进 Solution Pro

### 风险 3：Ship Pro "增值"定义不清导致范围蔓延

**描述**：把 Ship Pro 从"搬运工"升级为"项目经理"，很容易滑入"什么都做"的陷阱——比如让 Ship Pro 也做技术选型、也做架构决策。

**缓解策略**：
- 严格限定 Ship Pro 的输入只有 blueprint
- Ship Pro 不能"发明"新的架构决策，只能"翻译"和"细化"
- 如果 Ship Pro 需要做架构决策，说明 blueprint 不够完整 → 反馈给 Solution Pro

---

## 六、总结：一句话建议

> **不要修复 frozen_blueprint，重新设计 design_blueprint。不要搬运字段，翻译语义。不要一个通用格式，按引擎适配。**

当前架构的问题不是"哪个模块写得不好"，而是 **模块间的契约设计失败**。用 DDD 的话说：Bounded Context 之间的 Integration Pattern 选错了——用了最弱的 Shared Kernel（信息丢失的 frozen_blueprint），而不是应该用的 Published Language（设计良好的 design_blueprint）+ Anti-Corruption Layer（语义翻译，不是字段复制）。

---

## 附录：业界参考映射

| 业界模式 | DeepFlow 应用 |
|---------|-------------|
| DDD Published Language | design_blueprint.json — 两个 BC 之间的正式契约 |
| DDD Anti-Corruption Layer | ACL₁ (blueprint→ship_package) + ACL₂ (ship_package→engine) |
| DDD Context Map | Solution Pro → Ship Pro → Super Loop 的 Customer-Supplier 关系 |
| DTO/Domain Object/VO | final_result(DO) → blueprint(Published Lang) → ship_package(DTO) |
| Saga Orchestration | 整体流程是 Orchestration 模式，每个模块是一个 Saga Step |
| Saga Compensation | Ship Pro → Solution Pro 的反馈通道（当设计不可执行时） |
| Transactional Outbox | design_blueprint 的原子写入 + 事件通知 Ship Pro 开始工作 |
