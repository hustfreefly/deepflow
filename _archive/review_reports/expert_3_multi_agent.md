# DeepFlow 契约断裂问题 — 多 Agent 系统专家视角评审报告

> **评审人**: 多 Agent 系统研究者（LLM Agent 编排、工具使用、多 Agent 协作）
> **评审日期**: 2026-06-23
> **评审对象**: DeepFlow Contract Layer 方案可行性

---

## 一、核心判断（Executive Summary）

**结论：诊断准确，但归因不够深；方案方向正确，但实施顺序需要调整。**

"缺少合同层"是**症状级**诊断，准确但不够根本。更深层的根因是：**DeepFlow 混淆了"设计时契约"与"运行时契约"，且没有将契约作为一等公民（First-Class Citizen）**。当前 5 份文档（Prompt、Gate、Schema、Orchestrator、SKILL.md）的割裂，本质上是架构设计时缺少"契约即代码"（Contract as Code）的理念。

**关键判断**：
- ✅ 合同层是必要的，但不是第一步该做的事
- ⚠️ LLM 不确定性不是根因，但它是**放大器**——让本可容忍的契约偏差变成系统崩溃
- 🎯 最优先修复的是"必然失败"（P1-2：Prompt ↔ Gate 断裂），而非"可能失败"（P1-1：Schema 校验）
- 💡 存在一个比 Contract Layer 更轻量、更先验的解决方案：**结构化输出 + Pydantic 验证**

---

## 二、深度分析：六个核心问题

### 2.1 LLM 输出的不确定性：是根因还是放大器？

**提案人观点**："即使 LLM 100% 确定性输出，问题也会出现。"

**我的判断：同意，但需要区分两种失败模式。**

| 失败模式 | 代表问题 | LLM 不确定性是否相关？ | 本质 |
|:---|:---|:---:|:---|
| **契约设计错误** | P1-2（Architect Prompt 缺少 `project_type`） | ❌ 无关 | 人设计的 Prompt 和 Gate 自相矛盾，LLM 无论怎么输出都失败 |
| **契约执行偏差** | P1-1（Packager 输出 128 个 schema 错误） | ⚠️ 部分相关 | Prompt 和 Schema 基本对齐，但 LLM 输出偏离（添加字段、类型错误、遗漏必填） |
| **状态管理缺失** | P1-3, P1-4（状态机失效、文件不一致） | ❌ 无关 | 系统工程问题，与 LLM 无关 |
| **流程文档漂移** | P2-1（SKILL.md vs run_pipeline.py） | ❌ 无关 | 工程文档管理问题 |

**关键洞察**：
P1-2 是最能说明问题的案例。`gate_architect()` 检查 `project_type` 和 `requirements[].mapped_components`，但 `architect.md` 的 Prompt 完全没有这两个字段。这意味着：**Gate 是在检查一个 LLM 从未被 instruct 过的输出**。这不是 LLM 不确定性问题，这是**系统设计中的人为错误**。

但 P1-1 则不同。Packager 的 Prompt 和 Schema 基本对齐（提案人认为"根因是 Packager prompt 的输出 schema 与 JSON schema 文件不同步"），但 LLM 仍然输出 `_meta` 在顶层、用 `"standard"` 代替枚举值、添加 `constraints` 等额外字段。这是**LLM 在"理解并执行 schema"时的偏差**。

**结论**：LLM 不确定性不是根因，但它是**关键的放大器**。在一个有明确契约的系统中，LLM 的微小偏差可以被容错机制吸收；但在 DeepFlow 当前没有契约保护的情况下，这些偏差直接击穿系统。

---

### 2.2 Prompt 作为契约：弱契约的根本矛盾

**核心矛盾**：Prompt 本质是**建议（Suggestion）**，不是**约束（Constraint）**。Contract Layer 试图从 Prompt 自动生成 schema，但 LLM 输出仍然可能偏离。

**这个矛盾能否解决？**

答案是：**不能完全解决，但可以大幅降低风险**。方法是分层策略：

```
Layer 1: LLM 层强制（Structured Output / JSON Mode / Function Calling）
         ↓ 将"弱契约"转化为"强约束"
Layer 2: 运行时验证（Schema / Pydantic Validation）
         ↓ 捕获残余偏差
Layer 3: 修复循环（Retry + Repair Agent）
         ↓ 自动修复可修复的偏差
Layer 4: 降级与人工（Escalation）
         ↓ 不可修复的偏差人工介入
```

**提案人的 Contract Layer 只覆盖了 Layer 2（运行时验证）的"定义"部分**，但没有解决 Layer 1（如何让 LLM 真正遵守）和 Layer 3（当 LLM 不遵守时怎么办）。

**具体建议**：
1. **优先使用 LLM 的原生结构化输出能力**。如果 DeepFlow 使用的是支持 JSON mode 的模型（如 GPT-4、Claude、Kimi），应该强制使用 JSON mode 并传入 schema。这是**从 Prompt 弱契约到 API 强约束**的最直接转换。
2. **Pydantic 比 JSON Schema 更适合**。JSON Schema 是"验证语言"，Pydantic 是"建模语言"。Pydantic 可以：
   - 定义模型时自动生成 schema
   - 运行时验证 + 自动错误信息
   - 与 Python 类型系统深度集成
   - 支持 `model_validator` 做跨字段业务验证
3. **Contract Layer 不应该从 Prompt 生成 schema，而应该从 Pydantic 模型生成 Prompt**。提案人的方向反了。正确的顺序是：
   ```
   Pydantic Model（真相源） → 生成 Prompt 的 schema 段落
                          → 生成 Gate 检查代码
                          → 生成 JSON Schema
                          → 生成运行时验证
   ```

---

### 2.3 Agent 间通信：Blackboard 模式的已知陷阱

DeepFlow 使用文件系统作为 Blackboard，这在 Multi-Agent 系统中**确实是经典模式**（Blackboard Architecture，1980s 从 Hearsay-II 语音系统开始）。但经典模式不代表没有问题。

**Blackboard 的经典结构**：
```
+--------------------------------------------------+
|                 Blackboard（全局状态）              |
|  - 数据层（共享数据）                               |
|  - 控制层（调度/聚焦）                              |
+--------------------------------------------------+
         ↑↓                           ↑↓
    Agent A（知识源）            Agent B（知识源）
    - 读取/写入条件               - 读取/写入条件
    - 触发规则                    - 触发规则
```

**DeepFlow 的实现与经典模式的差距**：

| 经典 Blackboard 组件 | DeepFlow 现状 | 问题 |
|:---|:---|:---|
| **集中式控制（Controller）** | 缺失。主 Agent 手动 spawn，没有统一调度器 | P1-3：状态机失效 |
| **数据层版本控制** | 缺失。文件被覆盖，没有版本历史 | 无法追踪"谁写了什么" |
| **事务性写入** | 缺失。文件写一半 crash | 数据损坏风险 |
| **Agent 触发规则** | 缺失。Agent 不知道何时该读写 | 竞态条件 |
| **聚焦策略（Focus）** | 缺失。所有数据对所有 Agent 可见 | 信息过载、隐私问题 |

**已知的 Pitfall（在 DeepFlow 中全部出现）**：

1. **Schema 漂移（Schema Drift）**：Blackboard 上的数据格式没有版本控制。Agent A 写入 v2 格式，Agent B 按 v1 读取。
   - 对应问题：P1-1（Packager 输出格式变化）

2. **状态竞争（State Races）**：多个 Agent 同时读写状态文件。
   - 对应问题：P1-4（两个状态文件内容不一致）

3. **缺乏可观测性**：无法追踪"哪个 Agent 在什么时候写了什么"。
   - 对应问题：调试困难，问题定位慢

4. **信息过载**：每个 Agent 都能看到所有数据，Prompt 需要过滤。
   - 对应问题：Prompt 过长，LLM 注意力分散

**更好的替代方案**：
- **消息总线（Message Bus）**：Agent 不直接读写文件，而是发布/订阅消息。每个 Agent 只收到它需要的数据。
- **状态数据库（State DB）**：用 SQLite 或 Redis 替代文件系统，支持事务、版本、查询。
- **流式 Blackboard（版本化）**：每个写入都是一个版本，Agent 可以读取特定版本。

**但说实话**：对于一个已经用文件系统的项目，**不需要立即重构通信层**。文件系统的问题可以通过"契约层 + 版本控制 + 日志"来缓解。通信层的重构是高成本、中收益，应该排在后面。

---

### 2.4 Gate 检查设计：确定性代码 vs LLM-as-Judge

**当前设计**：Gate 是确定性 Python 代码检查 LLM 输出。

**这是否是最佳实践？**

**不是**。当前的 Gate 设计存在三个问题：

1. **混合了结构验证和业务验证**：`gate_architect()` 检查 `project_type`（业务字段）和 `requirements[].mapped_components`（结构字段）。结构验证应该自动化（Pydantic），业务验证应该显式定义。
2. **与 Prompt 不同步**：Gate 检查的内容在 Prompt 中找不到（P1-2）。
3. **没有修复机制**：Gate 失败后只是标记 CONDITIONAL，没有告诉 LLM 如何修复。

**最佳实践应该是分层验证**：

```python
# Layer 1: 结构验证（自动、确定性）
try:
    output = PydanticModel.parse_raw(llm_output)  # 自动检查类型、必填、枚举
except ValidationError as e:
    return SchemaViolation(errors=e.errors())

# Layer 2: 业务验证（半自动，可配置）
if output.project_type not in ALLOWED_TYPES:
    return BusinessRuleViolation(field="project_type", ...)

# Layer 3: 语义验证（LLM-as-Judge，用于质量评估）
quality_score = llm_judge.evaluate(output, criteria=QUALITY_CRITERIA)
if quality_score < THRESHOLD:
    return QualityInsufficient(score=quality_score, feedback=...)
```

**什么时候用 LLM-as-Judge？**

| 验证类型 | 方法 | 示例 |
|:---|:---|:---|
| 结构验证 | 确定性代码（Pydantic） | 字段存在、类型正确、枚举值 |
| 格式验证 | 确定性代码（Regex/JSON） | JSON 格式、Markdown 格式 |
| 业务规则 | 确定性代码 + 配置 | 值范围、关联关系 |
| 内容质量 | **LLM-as-Judge** | "方案是否完整？""设计是否合理？" |
| 一致性检查 | **LLM-as-Judge** | "输出是否与需求一致？" |
| 安全性检查 | 混合 | 敏感信息泄露 |

**DeepFlow 的 Gate 应该改造为**：
- 结构验证：100% 自动化，由 Pydantic 完成
- 业务验证：从 Contract 配置生成，不是硬编码
- 质量验证：引入 LLM-as-Judge，但仅在需要时（如 Reviewer 阶段）

---

### 2.5 对比主流框架：它们如何解决契约一致性问题？

#### **LangGraph**

```python
from langgraph.graph import StateGraph
from typing import TypedDict

class AgentState(TypedDict):
    project_type: str
    modules: list[Module]
    # 所有 Agent 共享这个 State

graph = StateGraph(AgentState)
graph.add_node("architect", architect_agent)
graph.add_node("decomposer", decomposer_agent)
graph.add_edge("architect", "decomposer")
```

**契约机制**：
- **TypedDict/Pydantic** 定义共享 State，编译时类型检查
- 每个 Agent 的输入/输出必须匹配 State 类型
- 状态流转由 Graph 显式定义，不能随意 spawn

**优点**：强类型、编译时检查、状态流转可视化
**缺点**：State 是全局的，所有 Agent 共享，信息过载；Agent 内部输出格式无法约束

**与 DeepFlow 对比**：
LangGraph 的 State 相当于 DeepFlow 的 Blackboard，但 LangGraph 用类型系统保证了 Blackboard 的 Schema 一致性。DeepFlow 的 Blackboard 是文件系统，没有任何类型约束。

#### **CrewAI**

```python
from crewai import Agent, Task
from pydantic import BaseModel

class ArchitectOutput(BaseModel):
    project_type: str
    modules: list[str]

architect = Agent(...)
task = Task(
    description="...",
    expected_output="JSON with project_type and modules",
    output_json=ArchitectOutput,  # Pydantic 模型
    agent=architect
)
```

**契约机制**：
- **Task 级别定义 Pydantic Output Model**
- Agent 输出必须匹配 Pydantic 模型
- 如果输出不匹配，CrewAI 自动重试（Retry + Repair）

**优点**：每个 Task 独立定义输出格式，Agent 复用性高
**缺点**：Task 描述和 Output Model 之间没有强制关联（描述说输出 A，模型定义 B，可能不一致）

**与 DeepFlow 对比**：
CrewAI 的 Task-Output 绑定类似于 DeepFlow 的 Prompt-Gate 绑定，但 CrewAI 用 Pydantic 自动化了验证。DeepFlow 的 Gate 是手工 Python 代码，容易与 Prompt 不同步。

#### **AutoGen**

```python
from autogen import ConversableAgent

agent = ConversableAgent(
    name="architect",
    system_message="...",
    llm_config={...}
)
# 通过对话历史传递状态
```

**契约机制**：
- **对话历史（Conversation）** 是共享状态
- 没有显式的 Schema 约束，靠 Prompt 和 LLM 理解
- 有 GroupChat 管理器负责选择下一个发言者

**优点**：灵活、自然语言交互
**缺点**：没有结构化输出保证，全靠 LLM 自律

**与 DeepFlow 对比**：
AutoGen 比 DeepFlow 更"松耦合"，但也更不可靠。DeepFlow 试图引入结构化输出，这是正确的方向，但实现方式有问题。

#### **OpenAI Swarm**

```python
from swarm import Swarm, Agent

agent = Agent(
    name="architect",
    instructions="...",
    functions=[transfer_to_decomposer]  # 显式 Handoff
)
```

**契约机制**：
- **Function Calling 作为 Handoff**
- 每个 Agent 定义可调用的函数（转移到其他 Agent）
- 输出通过函数参数传递，天然有 schema（Function Schema）

**优点**：Handoff 显式、可追踪；Function Calling 天然有 schema
**缺点**：需要模型支持 Function Calling

**与 DeepFlow 对比**：
Swarm 的 Handoff 机制值得 DeepFlow 借鉴。当前 DeepFlow 的主 Agent 手动 spawn 子 Agent，类似于"隐式 Handoff"，没有调用栈记录。Swarm 的 Function Calling 方式让 Agent 间的调用关系变得可追踪。

---

### 2.6 替代方案：不用 Contract Layer，还能怎么做？

**方案 A：Pydantic-First（最推荐，轻量、先验）**

不引入 Contract Layer，而是：
1. 每个 Agent 定义一个 Pydantic 模型（`architect_output.py`）
2. 从 Pydantic 模型自动生成：
   - Prompt 的 schema 段落（`model_json_schema()`）
   - Gate 验证代码（`model_validate()`）
   - JSON Schema（`model_json_schema()`）
3. 运行时强制使用 LLM 的 JSON mode，传入 Pydantic 模型的 schema
4. 验证失败时自动 Retry（让 LLM 修复错误）

```python
# architect_output.py
from pydantic import BaseModel, Field

class ArchitectOutput(BaseModel):
    project_type: str = Field(..., enum=["web_app", "data_pipeline", ...])
    modules: list[Module] = Field(..., min_length=1)
    
    @model_validator(mode='after')
    def check_modules(self):
        # 业务验证
        if len(self.modules) > 10:
            raise ValueError("too many modules")
        return self
```

**优点**：
- 利用 Python 已有生态，不引入新抽象
- 真相源单一（Pydantic 模型）
- 自动生成所有验证代码
- 与 LangGraph/CrewAI 生态兼容

**缺点**：
- 不如 YAML 声明式直观
- 需要 Python 能力

**方案 B：测试驱动（Test-Driven）**

不为所有 Agent 建立统一契约，而是：
1. 为每个 Agent 写**单元测试**：给定输入，输出必须符合格式
2. 运行时执行测试，失败时 Retry
3. 测试即契约

```python
def test_architect_output():
    output = run_agent("architect", input=TEST_INPUT)
    assert "project_type" in output
    assert output["project_type"] in ALLOWED_TYPES
    assert "modules" in output
    assert len(output["modules"]) > 0
```

**优点**：
- 快速发现问题
- 测试可以渐进式增加（不需要一次性定义完整契约）
- 与 CI/CD 集成

**缺点**：
- 没有统一真相源
- 测试和实现可能不同步

**方案 C：监控优先（Observability-First）**

不追求完美契约，而是：
1. 运行时收集所有 Agent 输入/输出
2. 自动检测异常（schema 变化、字段缺失）
3. 异常时告警 + 人工修复

**优点**：
- 最低实施成本
- 渐进式改进

**缺点**：
- 不能预防问题，只能检测问题
- 需要人工介入

**方案 D：简化架构（KISS）**

减少 Agent 数量，合并职责：
- Architect + Decomposer → 一个 Agent
- Specifier + Reviewer → 一个 Agent
- 减少接口数量，减少契约数量

**优点**：
- 从根本上减少问题

**缺点**：
- 可能牺牲模块化
- 需要重新设计

---

## 三、对 Contract Layer 方案的完整评估

### 3.1 方案可行性：可行，但有限制

Contract Layer 在 LLM Agent 场景下**可行，但只能解决"结构契约"问题，不能解决"语义契约"问题**。

**能解决的**：
- ✅ 字段存在/缺失
- ✅ 类型正确性
- ✅ 枚举值范围
- ✅ 必填/可选
- ✅ 数组长度

**不能解决的**：
- ❌ "方案是否合理"
- ❌ "设计是否完整"
- ❌ "输出是否符合业务需求"
- ❌ "模块划分是否恰当"

**LLM 输出天然不确定，Contract Layer 能约束到什么程度？**

- 如果配合 **LLM JSON mode + Contract Schema**：可以约束到 95%+ 的结构正确性（剩余 5% 是 LLM 不遵守 JSON mode 的极端情况）。
- 如果只用 **Prompt + Contract Layer**：约束效果有限（LLM 可能忽略 Prompt 中的 schema）。
- 如果配合 **Retry + Repair**：接近 100% 结构正确性（多次 Retry 后仍然失败的概率极低）。

### 3.2 方案完整性：遗漏了三个关键维度

提案人的 Contract Layer 方案缺少：

1. **版本管理与迁移**：当契约演进时（如添加新字段），如何保证向后兼容？旧版 Agent 输出如何被新版 Agent 读取？
   ```yaml
   # 建议增加
   version: "2.0"
   compatibility:
     - version: "1.0"  # 支持读取旧版输出
       migration: "add_field_x_with_default"
   ```

2. **运行时修复策略**：当验证失败时怎么办？
   - 自动 Retry（让 LLM 修复）？
   - 跳过当前 Agent（ graceful degradation）？
   - 人工介入？
   - 回滚到上一个阶段？

3. **可观测性**：如何追踪契约冲突？
   - 每次验证失败应该记录：预期值、实际值、Agent 名称、输入上下文
   - 契约变更历史（谁改了什么、什么时候改的）

### 3.3 实施顺序：建议调整

提案人的顺序：Phase 1（Contract Registry）→ Phase 2（单一引擎）→ Phase 3（跨域合同）

**我的建议顺序**：

```
Phase 0: 止血（立即做，1-2 天）
  - 修复 P1-2（Prompt ↔ Gate 断裂）：给 Prompt 加缺失字段，或从 Gate 删除不存在检查
  - 修复 P1-3（状态机）：统一状态更新逻辑，禁止手动 spawn 绕过
  - 修复 P1-4（状态文件不一致）：统一 completion_handler 状态更新
  - 修复 P2-1（SKILL.md 版本不一致）：SKILL.md 作为文档，run_pipeline.py 作为真相源

Phase 1: 结构化输出（1-2 周）
  - 为每个 Agent 引入 Pydantic Output Model
  - 强制使用 LLM JSON mode
  - 自动 Retry（schema 验证失败时让 LLM 修复）
  - 此时 90% 的 P1-1 问题会被自动解决

Phase 2: 统一验证层（2-3 周）
  - 用 Pydantic 替代手工 Gate 代码
  - 从 Pydantic 模型生成所有验证逻辑
  - 引入 LLM-as-Judge 用于质量评估（可选）

Phase 3: Contract Layer（重构级，1-2 个月）
  - 如果 Phase 1-2 证明有效，再考虑是否需要一个声明式的 Contract Registry
  - 如果 Pydantic 方案已经足够，Contract Layer 可能不需要
```

**关键论点**：先验证"结构化输出 + Pydantic"是否足够，再决定是否引入 Contract Layer。Contract Layer 是一个重型方案，如果 Pydantic 能解决 90% 的问题，那 Contract Layer 的收益/成本比就不够高。

### 3.4 风险与代价

**实施 Contract Layer 的风险**：

1. **引入新的不一致**：Contract YAML 与实际 Prompt 的偏差。如果开发者修改了 Prompt 但忘了改 Contract YAML，就会出现新的不一致。
   - 缓解：从 Contract YAML 生成 Prompt，而不是反过来

2. **过度工程**：YAML 抽象层可能变得过于复杂，难以维护。
   - 缓解：保持简单，只定义结构不定义语义

3. **版本地狱**：5 个 Agent × 3 个版本 = 15 个契约版本，管理复杂。
   - 缓解：明确版本策略（SemVer），自动化兼容性测试

4. **实施成本高**：需要重写所有 Agent 的契约定义、Gate 逻辑、Prompt 模板。
   - 缓解：渐进式实施，从最核心的 Agent 开始

---

## 四、优先级判断：在有限资源下，先修什么？

**按影响 × 修复成本排序**：

| 优先级 | 问题 | 影响 | 修复成本 | 建议动作 |
|:---:|:---|:---:|:---:|:---|
| 🚨 P0 | P1-2（Prompt ↔ Gate 断裂） | **100% 失败** | **5分钟** | 立即给 Prompt 加 `project_type` 字段，或从 Gate 删除不存在检查 |
| 🚨 P0 | P1-3（状态机失效） | 系统不可观测 | 2小时 | 禁止手动 spawn，强制通过 run_pipeline.py |
| 🔴 P1 | P1-1（Schema 校验 128 错误） | 高概率失败 | 1天 | 引入 Pydantic + JSON mode |
| 🔴 P1 | P1-4（状态文件不一致） | 状态不可信 | 2小时 | 统一 completion_handler 状态更新逻辑 |
| 🟡 P2 | P2-1（SKILL.md 版本不一致） | 开发者困惑 | 2小时 | 明确 SKILL.md 仅作为文档，run_pipeline.py 是真相源 |
| 🟡 P2 | P2-2（frozen_blueprint.json 未生成） | 交接失败 | 2小时 | 在 completion_handler 中生成 |
| 🟡 P2 | P2-3（缺失 final_solution.md） | 产物缺失 | 2小时 | 在 completion_handler 中生成 |
| 🟡 P2 | P2-4（Reviewer 占位符未替换） | 质量下降 | 30分钟 | 修复模板变量替换 |
| 🟢 P3 | P3-1（control_contract.json 降级） | 警告噪音 | 1天 | 分析是否必要，可能移除 |
| 🟢 P3 | P3-2（Cron Watcher 未设置） | 无自动触发 | 2小时 | 配置 cron |
| 📋 P4 | Contract Layer | 系统性预防 | 1-2个月 | 观察 Phase 1-2 效果后再决定 |

**核心原则**：
- 先修"必然失败"（P0），再修"可能失败"（P1）
- 先止血（让系统能跑起来），再重构（让系统能优雅地跑）
- 先验证轻量方案（Pydantic），再考虑重型方案（Contract Layer）

---

## 五、总结与建议

### 核心结论

1. **诊断准确**："缺少合同层"是正确诊断，但不够深。更深层的根因是**没有区分设计时契约和运行时契约，且没有将契约作为一等公民**。

2. **LLM 不确定性不是根因**：当前问题中，至少 50%（P1-2, P1-3, P1-4, P2-1）与 LLM 不确定性无关，是系统工程问题。LLM 不确定性是放大器，不是根因。

3. **Prompt 作为弱契约的矛盾可以解决**：通过**结构化输出（JSON mode）+ Pydantic 验证 + Retry 修复**，可以将结构正确性提升到 95%+。但语义契约（"设计是否合理"）仍然需要 LLM-as-Judge 或人工评审。

4. **Blackboard 模式可行，但需要增强**：当前文件系统 Blackboard 缺少版本控制、事务性和可观测性。短期内不需要重构通信层，但需要增加日志和版本追踪。

5. **Gate 设计需要分层**：结构验证 → Pydantic（自动）；业务验证 → 配置化；质量验证 → LLM-as-Judge（可选）。

6. **Contract Layer 不是第一步**：先实施"Pydantic-First + 结构化输出"，如果证明不够，再引入 Contract Layer。Contract Layer 是一个重型方案，只有在轻量方案不足时才值得投入。

### 给提案人的建议

1. **立即做（今天）**：修复 P1-2（给 Architect Prompt 加 `project_type` 和 `mapped_components`，或从 Gate 删除这些检查）。这是"5 分钟修复，消除 100% 失败"的问题。

2. **本周做**：引入 Pydantic Output Model 给 Packager 和 Architect。强制使用 JSON mode。自动 Retry schema 验证失败的情况。

3. **本月做**：评估 Pydantic 方案是否足够。如果 Packager 的 128 个错误被自动解决 95% 以上，Contract Layer 可以暂缓。

4. **如果必须做 Contract Layer**：
   - 真相源应该是 Pydantic 模型，不是 YAML
   - 从模型生成 Prompt schema、Gate 验证、JSON Schema
   - 不要试图从 Prompt 反向生成 Schema（方向错了）
   - 包含版本管理和运行时修复策略

---

> **"不要把完美当成进步的敌人。先让 Pydantic 解决 90% 的问题，再决定是否需要一个重型 Contract Layer 来解决剩下的 10%。"**

---

*评审完成。*
