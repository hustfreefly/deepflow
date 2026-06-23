# DeepFlow Contract Layer 评审报告 — 平台工程与 CI/CD 视角

> **评审专家**: 平台工程专家（Subagent #2）
> **评审日期**: 2026-06-23
> **评审对象**: DeepFlow Contract Layer 提案
> **评审材料**: `deepflow_contract_layer_review_20260623.md` + 系统代码深度审查

---

## 一、核心判断（TL;DR）

**"缺少合同层"的诊断是对的，但不够深。真正的根因是：DeepFlow 是一个没有执行引擎的管线——5 个 Agent 的协作靠"人工程序员在主 Agent 里手写 spawn 逻辑"驱动，而不是靠声明式配置驱动。**

Contract Layer 的提议方向正确，但 Phase 1 的 `contract.yaml` 设计过于理想化，对 LLM 不确定性的约束有限。更务实的做法是先做"管线引擎化"（Phase 2），再逐步收敛合同定义（Phase 1）。

**我的优先级建议**：Phase 2（单一引擎）> Phase 1（合同注册表）> Phase 3（跨域合同）。

---

## 二、管线设计模式分析

### 2.1 DeepFlow 5 阶段管线 vs 传统 CI/CD Pipeline

| 维度 | 传统 CI/CD（Jenkins/GitLab CI/Tekton） | DeepFlow Ship Pro V3 | 关键差异 |
|------|----------------------------------------|----------------------|----------|
| **执行单元** | 确定性脚本/容器 | LLM Agent（非确定性） | 🔴 核心差异：输出不可预测 |
| **阶段定义** | `.yaml` 声明式（GitLab CI）或 Groovy 脚本（Jenkins） | Python 代码 + Markdown Prompt | 🔴 没有声明式管线定义 |
| **数据传递** | Artifact（文件/对象存储） | blackboard（文件系统） | ✅ 类似，但无版本化 |
| **质量门禁** | 脚本/测试用例（确定性） | Python gate + LLM Reviewer（混合） | 🟡 半确定性，Gate 与 Prompt 不同步 |
| **失败重试** | 配置 `retry` 字段 | 代码级 retry loop | ✅ 类似，但 retry 逻辑散落在各文件 |
| **状态管理** | CI 平台内置状态机 | `pipeline_status.json`（手动维护） | 🔴 状态机失效风险 |
| **可观测性** | 标准日志 + Metrics | 文件系统状态快照 | 🟡 可追溯但无统一视图 |

### 2.2 LLM 作为执行单元带来的新挑战

**挑战 1：输出 Schema 漂移（Output Schema Drift）**

传统 CI/CD 中，每个阶段的输出格式由工具链保证（如 `docker build` 输出镜像 ID，`pytest` 输出 JUnit XML）。DeepFlow 中，LLM 输出 JSON 的 schema 完全由 Prompt 中的示例决定，而 Prompt 是 Markdown 文本，没有编译时检查。

```
传统 CI/CD:  阶段输出格式 = 工具定义（强约束）
DeepFlow:     阶段输出格式 = Prompt 中的 JSON 示例（弱约束）
```

**挑战 2：Gate 的"假阳性通过"（False Positive Pass）**

`gate_architect()` 检查 `project_type` 和 `requirements[].mapped_components`，但 Architect Prompt 的输出 schema 中没有这两个字段。这意味着：
- Gate 永远无法 PASS（因为字段不存在 → 检查失败）
- 但 Gate 的 FAIL 又会触发 retry，形成无限循环
- 实际上线后可能表现为"偶尔通过"（LLM 偶尔幻觉出这些字段）

这在传统 CI/CD 中相当于：测试用例检查了一个构建产物中不存在的字段，但测试框架没有报错，而是静默失败并触发重试。

**挑战 3：Prompt 版本与代码版本的解耦**

`run_pipeline.py` 中通过 `_load_prompt(agent_name)` 读取 Markdown 文件，但没有版本校验机制。如果 Prompt 被修改而 Gate 未同步更新，就会出现"Gate 检查旧 schema"的问题。

传统 CI/CD 的解决方式：
- GitLab CI: `image: my-image:v1.2.3`（镜像版本锁定）
- Tekton: `Task` 定义在 Git 中，与 Pipeline 版本一起管理
- DeepFlow 现状: Prompt 文件无版本管理，Gate 代码无版本感知

### 2.3 管线设计模式建议

**模式 A：声明式管线定义（推荐）**

将管线定义从 Python 代码中提取到声明式配置中：

```yaml
# pipeline.yaml
stages:
  - name: architect
    agent: architect
    model: strong
    timeout: 300
    gate: gate_architect
    retries: 2
    output_schema: schemas/architect_output.schema.json
    
  - name: decomposer
    agent: decomposer
    model: strong
    timeout: 300
    gate: gate_decomposer
    retries: 2
    depends_on: [architect]
    output_schema: schemas/decomposer_output.schema.json
    
  # ...
```

**模式 B：Agent 即容器（Agent-as-Container）**

将每个 Agent 视为一个"容器"，有明确的输入/输出接口：

```python
class AgentStage:
    def __init__(self, config: StageConfig):
        self.config = config
        self.prompt = load_prompt(config.prompt_version)
        self.gate = load_gate(config.gate_version)
        self.schema = load_schema(config.schema_version)
    
    def run(self, input_data: dict) -> StageOutput:
        # 1. 验证输入
        self.validate_input(input_data)
        
        # 2. 生成 Prompt
        prompt = self.prompt.render(input_data)
        
        # 3. 调用 LLM
        output = llm_call(prompt, model=self.config.model)
        
        # 4. 验证输出 Schema
        self.schema.validate(output)
        
        # 5. 运行 Gate
        gate_result = self.gate.check(output)
        
        return StageOutput(output, gate_result)
```

这种模式的收益：
- **版本锁定**: `prompt_version`、`gate_version`、`schema_version` 可以独立演进
- **可测试性**: 每个 Stage 可以独立单元测试
- **可观测性**: 每个 Stage 的输入/输出/Gate 结果都被结构化记录

---

## 三、质量门禁（Gate）分析

### 3.1 当前 Gate 的问题诊断

**问题 1：Gate 与 Prompt 的契约断裂（P1-2）**

```python
# gates.py
def gate_architect(blueprint: dict) -> dict:
    # ...
    major["project_type_exists"] = bool(blueprint.get("project_type"))
    # ...
```

但 `architect.md` Prompt 的输出 schema 中完全没有 `project_type` 字段。

**根因**: Gate 和 Prompt 由不同的人在不同时间维护，没有共享的 schema 定义。

**问题 2：Gate 的阈值逻辑不一致**

```python
# gate_architect: Major 失败率 > 50% → CONDITIONAL
# gate_specifier: Major 失败率 > 30% → CONDITIONAL
# gate_packager: Major 失败率 > 50% → CONDITIONAL
```

不同 Gate 的阈值不一致，且这些阈值是硬编码的，没有集中管理。

**问题 3：Gate 无法区分"LLM 输出错误"和"输入数据不足"**

如果 Architect 的输入是 Format D（最小化输入），Gate 检查 `modules_non_empty` 会失败。但这不是 LLM 的错误，而是输入数据本身不足。当前 Gate 无法区分这两种情况。

### 3.2 质量门禁的成熟模式

**模式 1：Schema-Driven Gate（推荐用于 DeepFlow）**

```yaml
# contract.yaml
stages:
  architect:
    output:
      schema: schemas/architect_output.schema.json
      required_fields:
        - project_type
        - modules
        - requirements
      gates:
        - name: modules_non_empty
          check: len(modules) > 0
          severity: critical
        - name: project_type_exists
          check: project_type is not None
          severity: major
```

Gate 从 schema 定义自动生成，确保与 Prompt 的 schema 一致。

**模式 2：分层门禁（Hierarchical Gates）**

借鉴 Kubernetes 的 Admission Controller 模式：

```
L1: Schema Validation（结构检查）
  → 自动从 JSON Schema 生成
  
L2: Business Logic（业务规则）
  → 手动编写，如"模块覆盖率 100%"
  
L3: Semantic Review（语义审核）
  → LLM Reviewer（当前 Reviewer Agent 的角色）
```

当前 DeepFlow 的 Gate 混合了 L1 和 L2，但没有明确分层。建议：
- L1 完全自动化（从 schema 生成）
- L2 手动编写，但配置化（不要硬编码在 Python 中）
- L3 保留 LLM Reviewer

**模式 3：Gate 作为独立服务**

```python
# 当前：Gate 是函数调用
gate_result = gate_architect(output)

# 建议：Gate 是独立服务
response = requests.post("http://gate-service/check", json={
    "stage": "architect",
    "output": output,
    "schema_version": "v2.0"
})
```

对于个人项目过于复杂，但如果未来多人协作，这是必要的。

### 3.3 Gate 与 Prompt 一致性保障

**方案 A：单一 Schema 源（推荐）**

```
contract.yaml
  ├── schema: 定义所有字段
  ├── prompt: 从 schema 自动生成 Prompt 中的 JSON 示例
  └── gate: 从 schema 自动生成 Gate 检查逻辑
```

**方案 B：Prompt-Gate 双向校验**

```python
# CI 流程
1. 解析 Prompt 中的 JSON 示例 → 提取期望 schema
2. 解析 Gate 代码 → 提取检查字段
3. 对比两者 → 报告差异
```

对于个人项目，方案 A 更可行。

---

## 四、可观测性分析

### 4.1 当前可观测性问题

**问题 1：状态文件不一致（P1-3, P1-4）**

```
.completed.json       → status: completed
.stage_progress.json  → status: running
pipeline_status.json  → current_agent: specifier, state: running
```

三个文件维护三个独立的状态机，没有单一事实源。

**问题 2：进度无法追踪**

当前状态文件只记录"当前 Agent"和"状态"，缺乏：
- 每个 Agent 的执行时间
- Gate 检查的历史记录
- Retry 次数和原因
- LLM 调用参数（model, temperature, 等）

**问题 3：没有集中式日志**

每个 Agent 的日志散落在各自的输出文件中，没有一个统一的视图来回答"这次运行发生了什么"。

### 4.2 OpenTelemetry 的适用性分析

**Trace/Span 模型是否适用？**

```
Trace: 一次完整的 Ship Pro 运行
  ├── Span: architect (300s)
  │   ├── Event: gate_check (PASS)
  │   └── Event: retry (0/2)
  ├── Span: decomposer (300s)
  │   ├── Event: gate_check (FAIL)
  │   ├── Event: retry (1/2)
  │   └── Event: gate_check (PASS)
  ├── Span: specifier (300s)
  │   └── ...
  └── Span: packager (180s)
      └── Event: schema_validation (128 errors)
```

**适用性评估**:

| 维度 | 适用性 | 说明 |
|------|--------|------|
| **Trace** | ✅ 高 | 一次 Ship Pro 运行 = 一个 Trace |
| **Span** | ✅ 高 | 每个 Agent = 一个 Span |
| **Event** | ✅ 高 | Gate 检查、Retry、Schema 错误 = Event |
| **Metrics** | 🟡 中 | 可以收集"Gate 通过率"、"平均 Retry 次数"等 |
| **Logs** | 🟡 中 | 可以关联，但 LLM 的输入/输出体积太大 |

**实施建议**:

对于个人项目，完整的 OpenTelemetry 集成过重。建议采用**轻量级 Trace 模式**：

```python
# 简化的 Trace 记录
class PipelineTrace:
    def __init__(self, run_id: str):
        self.run_id = run_id
        self.spans = []
    
    def start_span(self, agent: str):
        span = {
            "agent": agent,
            "start_time": datetime.now(),
            "events": []
        }
        self.spans.append(span)
        return span
    
    def add_event(self, span, event_type: str, data: dict):
        span["events"].append({
            "type": event_type,
            "timestamp": datetime.now(),
            "data": data
        })
    
    def export(self) -> dict:
        return {
            "run_id": self.run_id,
            "spans": self.spans,
            "summary": self._compute_summary()
        }
```

输出到 `pipeline_trace.json`，供后续分析。

### 4.3 状态管理建议

**方案：单一状态机（Single State Machine）**

```python
# state_machine.py
from enum import Enum, auto

class PipelineState(Enum):
    PENDING = auto()
    RUNNING = auto()
    GATE_PASS = auto()
    GATE_CONDITIONAL = auto()
    GATE_FAIL = auto()
    RETRYING = auto()
    SKIPPED = auto()
    DONE = auto()

class AgentState:
    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        self.state = PipelineState.PENDING
        self.retry_count = 0
        self.max_retries = GATE_CONFIG[agent_name]["max_retries"]
        self.gate_history = []
        self.output_sha = None
    
    def transition(self, new_state: PipelineState, reason: str):
        old_state = self.state
        self.state = new_state
        # 记录状态转换
        self._log_transition(old_state, new_state, reason)
    
    def _log_transition(self, old, new, reason):
        # 写入统一的 trace 日志
        pass
```

**关键原则**：
- 只有一个状态文件（`pipeline_state.json`）
- 所有状态变更必须通过 `transition()` 方法
- 状态变更自动记录到 Trace

---

## 五、版本管理分析

### 5.1 SKILL.md V2 vs run_pipeline.py V3 的问题

**问题**: SKILL.md 描述 V2 流程（Pre-Scanner → Compiler → Reviewer），但 `run_pipeline.py` 实现 V3 流程（Architect → Decomposer → Specifier → Reviewer → Packager）。

**根因**: 
1. SKILL.md 是"给人看的文档"，run_pipeline.py 是"给机器执行的代码"
2. 两者没有版本关联机制
3. 更新代码时忘记同步更新文档

### 5.2 CI/CD 中的版本管理成熟模式

**模式 1：语义化版本 + 变更日志**

```
ship_pro/
  ├── VERSION  ← 单一版本文件
  ├── CHANGELOG.md
  ├── SKILL.md  ← 引用 VERSION
  └── scripts/
      └── run_pipeline.py  ← 引用 VERSION
```

**模式 2：版本兼容性矩阵**

```yaml
# versions.yaml
ship_pro:
  current: "3.1.0"
  compatible_with:
    solution_pro: ">=2.0.0"
    blackboard_manager: ">=2.0.0"
  
  components:
    skill_md: "3.1.0"
    run_pipeline: "3.1.0"
    gates: "1.0.0"
    prompts: "3.1.0"
```

**模式 3：Git Tag + Release**

每次发布时打 Tag：
```bash
git tag -a ship_pro_v3.1.0 -m "Ship Pro V3.1.0"
git push origin ship_pro_v3.1.0
```

### 5.3 对 DeepFlow 的建议

对于个人项目，建议采用**模式 1 + 模式 2 的简化版**：

```python
# version.py（单一事实源）
SHIP_PRO_VERSION = "3.1.0"
SHIP_PRO_COMPONENTS = {
    "skill_md": "3.1.0",
    "run_pipeline": "3.1.0",
    "gates": "1.0.0",
    "prompts": "3.1.0",
    "schemas": "3.0.0"
}

def check_version_compatibility():
    """检查各组件版本是否兼容"""
    # 在 run_pipeline.py 启动时运行
    pass
```

**关键检查点**：
- `run_pipeline.py` 启动时检查 `SKILL.md` 中的版本号
- 如果版本不匹配，打印警告或拒绝启动

---

## 六、务实建议：个人项目的最小可行方案（MVP）

### 6.1 当前问题优先级排序

| 优先级 | 问题 | 影响 | 修复成本 | 建议方案 |
|--------|------|------|----------|----------|
| **P0** | Gate 与 Prompt 契约断裂（P1-2） | 每次运行必触发 CONDITIONAL | 低 | 对齐 Gate 检查字段与 Prompt 输出 schema |
| **P0** | Schema 校验 128 个错误（P1-1） | Packager 输出不可用 | 中 | 修复 Packager prompt 中的 schema 示例 |
| **P0** | 状态文件不一致（P1-3, P1-4） | 无法判断运行状态 | 低 | 统一状态机，单一事实源 |
| **P1** | SKILL.md 与代码版本不一致（P2-1） | 主 Agent 困惑 | 低 | 添加版本校验 |
| **P1** | Prompt 占位符未替换（P2-4） | Reviewer 可能出错 | 低 | 修复模板变量 |
| **P2** | 缺少 Contract Layer | 长期维护困难 | 高 | 分阶段实施 |

### 6.2 最小可行治理方案（3 周实施计划）

**Week 1: 止血（Stop the Bleeding）**

目标：修复 P0 问题，让管线能稳定运行。

```
Day 1-2: 修复 Gate 与 Prompt 的契约断裂
  - 对比 gate_architect() 检查字段 vs architect.md 输出 schema
  - 要么在 architect.md 中添加缺失字段，要么从 gate 中移除多余检查
  - 同理修复 gate_specifier, gate_packager

Day 3-4: 修复 Schema 校验错误
  - 对比 packager.md 中的 schema 示例 vs ship_package_v3.schema.json
  - 修复 Packager prompt 中的示例（如 _meta 位置、model_tier 枚举值）

Day 5: 统一状态管理
  - 删除 .completed.json 和 .stage_progress.json
  - 只保留 pipeline_status.json 作为唯一状态源
  - 修改 completion_handler.py 和 run_pipeline.py 使用同一状态机
```

**Week 2: 管线引擎化（Pipeline-as-Code）**

目标：将管线定义从 Python 代码中提取到声明式配置。

```
Day 1-2: 创建 pipeline.yaml
  - 将 AGENT_ORDER, GATE_CONFIG, AGENT_MODELS, AGENT_TIMEOUTS 提取到 YAML
  - run_pipeline.py 读取 YAML 而非硬编码

Day 3-4: 实现 AgentStage 类
  - 封装 Prompt 加载、LLM 调用、Gate 检查、状态更新
  - 每个 Agent 一个 Stage 实例

Day 5: 集成测试
  - 运行完整管线，验证所有 P0 问题已修复
```

**Week 3: 轻量级 Contract Layer**

目标：建立 Prompt-Gate-Schema 的一致性保障。

```
Day 1-2: 创建 stage_contract.yaml
  - 为每个 Agent 定义输入/输出 schema
  - Gate 检查项从 schema 自动生成

Day 3-4: 实现 Contract Validator
  - 解析 Prompt 中的 JSON 示例
  - 解析 Gate 代码中的检查字段
  - 对比两者，报告差异

Day 5: 集成到 CI
  - 每次提交前自动运行 Contract Validator
  - 不一致时阻止提交
```

### 6.3 不需要做的事情（避免过度工程）

| 不要做的事 | 原因 |
|-----------|------|
| ❌ 完整的 OpenTelemetry 集成 | 个人项目，Trace 文件足够 |
| ❌ 分布式状态存储 | 单机运行，文件系统足够 |
| ❌ 复杂的版本兼容性矩阵 | 单人维护，Git history 足够 |
| ❌ 自动化的 Contract 生成 | 手动维护 YAML 更可控 |
| ❌ 多环境部署（dev/staging/prod） | 单机运行，不需要 |

---

## 七、盲点发现

### 盲点 1：Prompt 版本管理缺失

当前 Prompt 文件没有版本号，修改后无法追溯。建议：
- 每个 Prompt 文件头部添加版本注释
- 使用 Git 管理 Prompt 变更
- 在 `_meta.prompt_sha` 中记录 Prompt 的 SHA256（已实现，但未用于版本校验）

### 盲点 2：Gate 的"软失败"模式

当前 Gate 有 PASS / CONDITIONAL / FAIL 三种结果，但没有定义"CONDITIONAL 时如何处理"。建议：
- PASS: 继续下一阶段
- CONDITIONAL: 记录警告，继续下一阶段（或根据配置决定是否暂停）
- FAIL: 触发 retry 或跳过

### 盲点 3：LLM 调用参数的不可见性

当前没有记录每个 Agent 使用的具体模型、temperature、max_tokens 等参数。建议：
- 在 `_meta` 中记录 `model_id`（已实现）
- 在 `_meta` 中记录 `temperature`、`max_tokens` 等参数
- 便于后续分析"为什么这个 Agent 输出质量差"

### 盲点 4：跨域交接（Solution Pro → Ship Pro）的契约缺失

当前 Solution Pro 输出 `frozen_blueprint.json`，但 Ship Pro 的输入格式检测逻辑（`_detect_format`）是启发式的，没有正式的契约定义。建议：
- 定义 `solution_pro_output.schema.json`
- Ship Pro 的 `_detect_format` 基于 schema 而非启发式

### 盲点 5：测试覆盖率不足

当前 `tests/` 目录下的测试主要覆盖 `eval_code_checks.py`，但缺乏：
- Gate 与 Prompt 的一致性测试
- 管线端到端测试（使用 mock LLM）
- 状态机转换测试

---

## 八、总结

### 诊断准确性评估

| 诊断 | 准确性 | 说明 |
|------|--------|------|
| "缺少合同层" | ✅ 准确 | 是根因之一，但不是最深层的根因 |
| "5 份独立文档" | ✅ 准确 | Prompt/Gate/Schema/Orchestrator/SKILL.md 确实各自为政 |
| "打地鼠会无限循环" | ✅ 准确 | 每修一个问题，可能在其他地方引入新问题 |

### 方案可行性评估

| Phase | 可行性 | 优先级 | 说明 |
|-------|--------|--------|------|
| Phase 1: 合同注册表 | 🟡 中等 | P2 | `contract.yaml` 设计理想化，LLM 不确定性难以完全约束 |
| Phase 2: 单一执行引擎 | ✅ 高 | P0 | 最务实的改进，立即降低复杂度 |
| Phase 3: 跨域合同 | 🟡 中等 | P3 | 需要 Solution Pro 配合，短期内难以实施 |

### 最终建议

1. **立即修复 P0 问题**（Gate 契约断裂、Schema 错误、状态不一致）
2. **Week 2 实施管线引擎化**（声明式配置 + AgentStage 类）
3. **Week 3 建立轻量级 Contract Layer**（stage_contract.yaml + Contract Validator）
4. **长期**：如果团队扩大到 2 人以上，再考虑完整的 OpenTelemetry 和分布式状态管理

---

*评审完成。本报告基于对 DeepFlow 代码的深度审查，包括 `run_pipeline.py`、`gates.py`、`eval_code_checks.py`、所有 Prompt 文件、JSON Schema 和 SKILL.md。*
