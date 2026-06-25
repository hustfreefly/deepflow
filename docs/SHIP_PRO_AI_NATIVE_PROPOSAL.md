# Ship Pro AI Native 改造方案 V3

> **日期**: 2026-06-25  
> **版本**: V3（基于 V2 + 第二轮 4 位专家评审 17 个 P2 全部修复）  
> **作者**: 小满（AI Agent）  
> **决策者**: 姬忠礼  
> **状态**: 待第三轮专家评审（3 位新专家）  
> **V2 备份**: `SHIP_PRO_AI_NATIVE_PROPOSAL_V2.md`  
> **P2 修复追踪**: `P2_FIXES_V3.md`

---

## 一、背景

### 1.1 当前问题

Ship Pro V3/V4 存在根本性问题：**架构不是 AI Native**。

| 维度 | 当前实现 | 忠礼决策（2026-06-25 研讨会） |
|------|---------|---------------------------|
| 阶段定义 | 硬编码 5 阶段 `AGENT_ORDER` | LLM 动态生成任务 DAG |
| 执行顺序 | Python 串行循环 | LLM Phase Selector，支持并行 |
| 质量判断 | Pydantic 门控 + 固定 retry | LLM 评估 + Python 护栏 |
| Worker 选择 | 固定模型映射 | LLM 根据任务选工具 |
| 错误恢复 | max_retries 计数器 | LLM Error Analyzer + 代码强制上限 |

### 1.2 忠礼决策（AI Native Loop 研讨会）

> "全 LLM 控制，Python 不做控制流"  
> "一步到位，不分阶段演进"

### 1.3 V1 → V2 核心改进（基于专家评审）

| 评审问题 | V1 | V2 修复 |
|---------|-----|---------|
| 可靠性裸奔 | 重试/超时全靠 prompt | Python 护栏命令（check-retry-limit, check-budget） |
| cwd 踩坑未规避 | spawn_params 无 cwd | 所有 spawn 强制 cwd + PYTHONPATH |
| 质量门控退化 | Pydantic 只做格式 | 保留 Python gate 函数 + LLM 评估双层 |
| 阶段可跳过 | LLM 随意跳过 | validate-plan 强制关键阶段存在 |
| 并行安全无保障 | LLM 猜测 | can-parallel 基于依赖图判断 |
| Prompt 粗放 | 缺少依赖图/质量维度 | 注入依赖图 + 5 维质量标准 + 恢复策略菜单 |
| 无断点恢复 | 未设计 | resume-context + checkpoint 机制 |
| Context 膨胀 | 未设计 | compact-history 命令 |
| Goal Judge 缺失 | Orchestrator 自评 | 独立 Judge Worker |

---

## 二、设计原则

> **"LLM 做决策，代码做护栏。没有护栏的 LLM 控制流 = 生产事故。"**

```
┌─────────────────────────────────────────┐
│  LLM 控制层（灵活、自适应）              │
│  - 阶段规划  - 质量评估  - 错误恢复     │
│  - 工具选择  - 并行决策  - 最终判断     │
└─────────────────────────────────────────┘
          │                    │
          ▼                    ▼
┌─────────────────────────────────────────┐
│  Python 护栏层（确定性、不可绕过）       │
│  - retry-limit  - budget-check          │
│  - plan-validate  - can-parallel        │
│  - state-validate  - atomic-write       │
└─────────────────────────────────────────┘
          │                    │
          ▼                    ▼
┌─────────────────────────────────────────┐
│  Python I/O 层（文件读写、格式校验）     │
│  - read/write  - pydantic-validate      │
│  - checkpoint  - resume-context         │
└─────────────────────────────────────────┘
```

---

## 三、io_helper.py 完整设计

### 3.1 命令清单（16 个命令） <!-- V3 FIX #1 -->

| 命令 | 类型 | 用途 |
|------|------|------|
| `read-input` | I/O | 读取输入（Living Spec 或原始需求），输出 JSON |
| `read-output` | I/O | 读取某阶段输出 |
| `build-prompt` | I/O | 用 LLM 提供的内容 + 模板 + 依赖注入，构建 worker prompt |
| `write-status` | I/O | 更新 pipeline_state.json（枚举校验 + 原子写入） |
| `write-completed` | I/O | 写 .completed 标记 |
| `validate-format` | 护栏 | Pydantic 格式校验（pass/fail + errors + suggestions） |
| `validate-quality` | 护栏 | 调用 Python gate 函数做语义校验（依赖无环、覆盖率等） |
| `validate-plan` | 护栏 | 校验执行计划包含必要阶段（`--required architect,reviewer,packager`） |
| `check-retry-limit` | 护栏 | 检查某阶段重试次数是否超限（代码强制，不可绕过） |
| `check-budget` | 护栏 | 检查总时间/token 是否超预算 |
| `can-parallel` | 护栏 | 基于 stage-dependencies.json 判断阶段是否可并行 |
| `log-decision` | I/O | 结构化写入 decisions.jsonl（timestamp, type, stage, reason, outcome） |
| `resume-context` | 恢复 | 输出断点恢复所需上下文（已完成/进行中/失败阶段） |
| `compact-history` | 恢复 | 压缩历史决策和输出为结构化摘要，减少上下文膨胀 |
| `dump-state` | 调试 | 输出管线状态完整快照 |
| `list-dependencies` | 调试 | 输出阶段数据依赖图 |

### 3.2 护栏命令详细设计

> **V3 新增：io_helper.py 文件头强化约束** <!-- V3 FIX #9 -->
> ```python
> #!/usr/bin/env python3
> """
> ⛔ 此文件禁止 `from openclaw import ...`
> ⛔ 此文件仅在 OpenClaw Agent 的 exec 环境中运行
> ⛔ 如需 OpenClaw SDK，请在 Agent 内直接调用，而不是通过此脚本
> """
> ```

#### validate-plan

```bash
python3 io_helper.py validate-plan <output_dir> --required architect,reviewer,packager
```

**输入**：Orchestrator 生成的执行计划 JSON（stdin 或 --plan-file）  
**校验**：
- 必须包含所有 `--required` 指定的阶段
- 阶段间依赖关系不能成环
- 每个阶段必须有输入来源

**输出**：
```json
{"valid": true, "missing_required": [], "warnings": ["specifier skipped (allowed)"]}
```

#### check-retry-limit

```bash
python3 io_helper.py check-retry-limit <output_dir> <stage>
```

**逻辑**：
- 从 `stage-dependencies.json` 读取该阶段的 `max_retries` 字段（**不可被 Orchestrator 覆盖**，防止绕过） <!-- V3 FIX #15（可靠性专家） -->
- 从 `pipeline_state.json` 读取该阶段的 `retry_count`
- 比较 retry_count vs max_retries，返回是否允许重试

**输出**：
```json
{"allowed": false, "current": 3, "max": 3, "source": "stage-dependencies.json", "action": "escalate"}
```

Orchestrator **每次重试前必须调用此命令**。返回 `allowed: false` 时，Orchestrator 必须上报主 Agent，不得继续重试。

#### check-budget

```bash
python3 io_helper.py check-budget <output_dir> --max-minutes 30 --max-retries-total 10
```

**输出**：
```json
{"within_budget": true, "elapsed_minutes": 12, "total_retries": 3}
```

#### can-parallel

```bash
python3 io_helper.py can-parallel <stage1> <stage2> <output_dir>
```

**逻辑**：基于 `stage-dependencies.json` 判断两个阶段是否有数据依赖。  
**输出**：
```json
{"can_parallel": false, "reason": "decomposer depends on architect output"}
```

#### validate-quality

```bash
python3 io_helper.py validate-quality <stage> <output_dir>
```

**逻辑**：调用保留的 Python gate 函数（gate_architect, gate_decomposer 等），做语义级校验。

**与 validate-format、LLM 评估的分工（三层验证）**： <!-- V3 FIX #4 -->
| 层 | 命令 | 职责 | 性质 |
|---|------|------|------|
| 1 | `validate-format` | Pydantic 检查字段类型/必填/枚举 | **硬约束**（格式正确性） |
| 2 | `validate-quality` | Python gate 检查业务逻辑（依赖无环、模块覆盖率、需求映射） | **硬约束**（架构合规） |
| 3 | Orchestrator 自评 | LLM 评估内容质量、合理性、完整性 | **软约束**（内容质量） |

**互补关系**：gate 函数负责"结构是否正确"，LLM 评估负责"内容是否合理"，两者不冲突。

**未知 stage 的容错处理**： <!-- V3 FIX #10 -->
- 如果 Orchestrator 自创了一个不在 `stage-dependencies.json` 中的阶段名，`validate-quality` 不会报错
- 返回：`{"pass": null, "warning": "no gate_fn defined for stage '<stage>', fallback to format-only validation"}`
- Orchestrator 可继续执行，但需在 decisions.jsonl 中记录"跳过 quality 校验"的原因

**输出（已知 stage）**：
```json
{"pass": true, "checks": [{"name": "dependency_acyclic", "pass": true}, {"name": "module_coverage", "pass": true, "score": 0.85}]}
```

### 3.3 状态写入安全设计

#### write-status 枚举校验

```python
VALID_STAGES = ["architect", "decomposer", "specifier", "reviewer", "packager"]
VALID_STATUSES = ["pending", "running", "gate_pass", "gate_conditional", "gate_fail", "skipped", "done"]

def write_status(output_dir, stage, status):
    if stage not in VALID_STAGES:
        raise ValueError(f"Invalid stage: {stage}. Must be one of {VALID_STAGES}")
    if status not in VALID_STATUSES:
        raise ValueError(f"Invalid status: {status}. Must be one of {VALID_STATUSES}")
    # 原子写入: write-to-temp + os.rename
```

#### 原子写入

```python
import tempfile, os

def atomic_write(path, data):
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(data, f, indent=2)
        os.rename(tmp, path)
    except:
        os.unlink(tmp)
        raise
```

### 3.4 断点续接设计

#### resume-context 命令

```bash
python3 io_helper.py resume-context <output_dir>
```

**输出**：
```json
{
  "completed_stages": ["architect", "decomposer"],
  "failed_stages": [{"stage": "specifier", "retries": 2, "last_error": "Pydantic validation failed"}],
  "pending_stages": ["reviewer", "packager"],
  "pipeline_state": {...},
  "decisions_summary": "12 decisions made, 2 retries, 0 escalations",
  "elapsed_minutes": 8,
  "context_files": [
    "blackboard/architect/architect_output.json",
    "blackboard/decomposer/decomposition.json"
  ]
}
```

Orchestrator prompt 中要求：**启动时必须先调用 resume-context，如果有未完成阶段，从断点继续**。

**文件扫描 + 自动修正状态（V3 新增）**： <!-- V3 FIX #16 -->
- resume-context 不仅读 `pipeline_state.json`，还扫描 `blackboard/` 目录的实际输出文件
- 如果发现某阶段有输出文件（如 `blackboard/architect/architect_output.json`）但 `pipeline_state.json` 状态未更新（仍为 `pending`），自动修正为 `done`
- 输出中增加 `state_corrections: [{stage: "architect", from: "pending", to: "done", reason: "output file exists"}]`
- 解决 write-status 时序窗口问题：Orchestrator 在 Worker 完成后、调用 write-status 前崩溃，状态可被自动修正

#### .heartbeat 文件

Orchestrator 每完成一个阶段，写入 `.heartbeat`：
```json
{"timestamp": "2026-06-25T20:15:00Z", "stage": "decomposer", "status": "completed"}
```

Watcher 用 .heartbeat 判断 Orchestrator 是否存活（而非仅依赖文件变化）。

### 3.5 上下文管理

#### compact-history 命令

```bash
python3 io_helper.py compact-history <output_dir>
```

**实现机制（V3 明确）**： <!-- V3 FIX #2 -->
- **纯提取 + 结构化 JSON**，不调用额外 LLM
- Orchestrator 自身就是 LLM，可直接阅读结构化摘要，无需再生成自然语言摘要
- 所有字段值直接从 blackboard 输出文件中提取（读取 JSON，不截断）

**摘要策略（V3 改进）**： <!-- V3 FIX #11 -->
- ~~前 500 字符~~ → 改为 **schema 字段列表 + 字段值完整列表**
- io_helper 负责提取所有字段和值，不做截断
- 截断策略由 Orchestrator 在 prompt 中控制（如上下文紧张时，Orchestrator 自行决定保留哪些字段的完整值）
- 确保关键字段（如架构原则、模块覆盖率）不丢失
- 失败场景下，保留所有失败阶段的完整记录（详见下方）

**失败细节保留策略（V3 新增）**： <!-- V3 FIX #14 -->
- 所有 `gate_fail` 和 `gate_conditional` 状态的阶段：**完整保留**失败记录（error message、stack trace、retry 历史）
- `gate_pass` 状态的早期阶段：压缩为 `{stage, fields_summary, key_metrics}` 结构化摘要
- 按状态筛选而非按位置筛选——确保所有失败教训都不丢失
- 目的：防止 Orchestrator 忘记之前的错误，重复走同一条失败路径

**输出**：
```json
{
  "total_decisions": 12,
  "stages_completed": ["architect", "decomposer"],
  "key_decisions": [
    {"stage": "architect", "decision": "use_microservices", "reason": "..."},
    {"stage": "decomposer", "decision": "retry_with_feedback", "reason": "coverage < 80%"}
  ],
  "output_summaries": {
    "architect": {
      "modules": 8, "principles": 5,
      "fields": {"modules": ["user_service", "order_service", "..."], "principles": ["DDD", "CQRS", "..."]},
      "file": "blackboard/architect/..."
    },
    "decomposer": {
      "work_packages": 16,
      "fields": {"packages": [{"id": "wp-1", "owner": "..."}, {"id": "wp-2", "..."}], "...": "..."},
      "file": "blackboard/decomposer/..."
    }
  },
  "failure_history": {
    "recent_2_stages": [
      {"stage": "specifier", "error": "Pydantic validation failed", "details": "...", "retries": 2, "outcome": "escalated"}
    ],
    "older_stages": [
      {"stage": "architect", "error_type": "format_error", "outcome": "fixed_on_retry"}
    ]
  }
}
```

Orchestrator 每完成 2 个阶段后调用一次，用摘要替代完整历史，防止上下文膨胀。

---

## 四、stage-dependencies.json 设计

### 4.1 文件内容

```json
{
  "stages": {
    "architect": {
      "inputs": ["living_spec"],
      "outputs": ["architecture_output"],
      "depends_on": [],
      "required": true,
      "gate_fn": "gate_architect",
      "max_retries": 2
    },
    "decomposer": {
      "inputs": ["architecture_output"],
      "outputs": ["decomposition"],
      "depends_on": ["architect"],
      "required": false,
      "gate_fn": "gate_decomposer",
      "max_retries": 2
    },
    "specifier": {
      "inputs": ["architecture_output", "decomposition"],
      "outputs": ["specifications"],
      "depends_on": ["architect", "decomposer"],
      "required": false,
      "gate_fn": "gate_specifier",
      "max_retries": 2
    },
    "reviewer": {
      "inputs": ["architecture_output", "decomposition", "specifications"],
      "outputs": ["review_report"],
      "depends_on": ["architect"],
      "required": true,
      "gate_fn": "gate_reviewer",
      "max_retries": 5
    },
    "packager": {
      "inputs": ["architecture_output", "decomposition", "specifications", "review_report"],
      "outputs": ["ship_package"],
      "depends_on": ["reviewer"],
      "required": true,
      "gate_fn": "gate_packager",
      "max_retries": 2
    }
  }
}
```

### 4.2 用途

- `validate-plan`：检查 `required: true` 的阶段是否在执行计划中
- `can-parallel`：检查两个阶段的 `depends_on` 是否有交集
- `build-prompt`：自动注入 `inputs` 对应的前置阶段输出文件路径
- `list-dependencies`：输出依赖图供 Orchestrator 参考
- `check-retry-limit`：读取每个阶段的 `max_retries` 作为代码强制上限（不可被 Orchestrator 覆盖）
- `validate-quality`：读取每个阶段的 `gate_fn` 字段，映射到对应的 Python gate 函数

**并行写入安全备注（V3 新增）**： <!-- V3 FIX #13 -->
> 当前依赖图是树状结构，can-parallel 确保不会有并发写入同一文件。若未来依赖图复杂化（两个并行阶段写同一共享文件），需引入 blackboard 文件级 `.lock` 机制。**TODO: 当出现此类场景时再实现。**

---

## 五、Orchestrator Prompt 设计（V2）

### 5.1 完整 Prompt

```markdown
# Ship Pro Orchestrator（AI Native V2）

你是 Ship 打包管线的 Orchestrator。你的任务是：将 Living Spec 转化为可交付的 Ship Package。

## ⚠️ 启动前强制检查

1. 调用 `io_helper.py resume-context <output_dir>`
2. 如果有已完成阶段 → 从断点继续，不重做
3. 如果无历史 → 从头开始

## 你的工具

| 工具 | 用途 |
|------|------|
| `exec` | 运行 `io_helper.py` 命令 |
| `sessions_spawn` | 启动 Worker Agent |
| `sessions_yield` | 等待 Worker 完成 |
| `read` | 读取文件 |

**⛔ exec 中禁止 `from openclaw import ...`。只能用 CLI 命令。**

## sessions_spawn 规范（强制）

每次 spawn Worker 时，**必须**包含以下参数：

```python
sessions_spawn(
    runtime="subagent",
    mode="run",
    label="ship-<stage_name>",
    task=<worker_task_prompt>,
    cwd="$DEEPFLOW_HOME",  # ⚠️ 必须传 cwd，使用环境变量，禁止硬编码绝对路径
    runTimeoutSeconds=300  # Worker 超时 5 分钟
)
```

> **V3 改进**：`cwd` 使用 `$DEEPFLOW_HOME` 环境变量（由 `start_ship_pro.py` 注入），不再硬编码 `/Users/allen/...`，提高可移植性。 <!-- V3 FIX #8 -->

## 阶段依赖图（参考，非硬约束）

```
architect (required)
  ├── decomposer (optional, depends: architect)
  │     └── specifier (optional, depends: architect + decomposer)
  └── reviewer (required, depends: architect)
        └── packager (required, depends: reviewer)
```

**你可以偏离此图，但必须满足**：
1. `required: true` 的阶段（architect, reviewer, packager）不能跳过
2. 有依赖关系的阶段不能并行（用 `io_helper.py can-parallel` 检查）
3. 偏离时调用 `io_helper.py log-decision` 记录原因

## 执行流程

### Phase 1: 理解输入
- `exec: io_helper.py read-input <output_dir>` → 读取 Living Spec
- `exec: io_helper.py list-dependencies <output_dir>` → 理解阶段依赖

### Phase 2: 规划执行
- 分析 Living Spec 内容
- 生成执行计划 JSON（包含阶段列表、顺序、工具选择）
- `exec: io_helper.py validate-plan <output_dir> --required architect,reviewer,packager`
- 如果 validate 失败 → 修改计划重新 validate
- `exec: io_helper.py log-decision <output_dir> plan "<计划摘要>"`

### Phase 3: 执行阶段

对每个阶段：

1. **构建 Worker Prompt**：
   - `exec: io_helper.py build-prompt <stage> <output_dir> --context-file <path>`
   - io_helper 会自动注入前置阶段输出 + Pydantic schema + 输出路径

2. **Spawn Worker**：
   - `sessions_spawn(...)` 必须包含 cwd（见上方规范）

3. **等待完成**：
   - `sessions_yield()` 等待 Worker auto-announce

4. **双重验证**：
   - `exec: io_helper.py validate-format <stage> <output_dir>` → Pydantic 格式校验
   - `exec: io_helper.py validate-quality <stage> <output_dir>` → Python gate 语义校验
   - **你自己的质量评估**：内容是否满足 Living Spec 要求？

5. **处理结果**：
   - 全部通过 → `io_helper.py write-status <output_dir> <stage> gate_pass`
   - 格式失败 → 带 schema 反馈重试（先 `check-retry-limit`）
   - 质量失败 → 带具体 feedback 重试（先 `check-retry-limit`）
   - 重试耗尽 → `io_helper.py write-status <output_dir> <stage> gate_fail` → 上报主 Agent

6. **上下文管理**：
   - 每完成 2 个阶段 → `io_helper.py compact-history <output_dir>`
   - 用摘要替代完整历史，防止上下文膨胀

7. **心跳**：
   - `exec: echo '{"timestamp":"...","stage":"...","status":"completed"}' > <output_dir>/.heartbeat`

### Phase 4: 最终评估（Goal Judge）

- Spawn 一个独立的 Judge Worker（不是你自己评估自己）：
  ```python
  sessions_spawn(
      runtime="subagent",
      mode="run",
      label="ship-judge",
      task="你是 Ship Package 质量 Judge。请评估以下 Ship Package 是否满足 Living Spec 的要求：...",
      cwd="$DEEPFLOW_HOME",
      runTimeoutSeconds=300
  )
  ```
- Judge 评估维度：完整性、一致性、可行性、架构原则符合度、Schema 合规性
- Judge 输出：`{"verdict": "pass|fail|conditional", "score": 85, "issues": [...]}`

**Judge Worker 失败处理（V3 新增）**： <!-- V3 FIX #3, #12 -->
- **Judge 输出 `verdict: fail`** → Orchestrator 根据 `issues` 列表定位问题阶段，重做该阶段，然后重新 spawn Judge
- **Judge 输出 `verdict: conditional`** → Orchestrator 修复 `issues` 中标记为 `critical` 的问题，重新 spawn Judge
- **Judge Worker 自身崩溃/超时/输出不合规** → Orchestrator 自行评估，但必须标记 `verdict: "self-assessed"`（非独立评估），并在 decisions.jsonl 中记录 "judge_worker_failed"
- **Judge 评估 vs Python gate 交叉验证（强制）**： <!-- V3 FIX #17 -->
  - 如果 Judge 说 `pass` 但 `validate-quality` 对 packager 阶段报 `fail` → **以 validate-quality 为准**，判定为 `fail`
  - 原因：Judge 是 LLM，可能给出乐观评估；Python gate 是确定性校验，更可靠

### Phase 5: 完成
- `exec: io_helper.py write-completed <output_dir>`
- announce 结果给主 Agent

## 错误恢复策略菜单

遇到 Worker 失败时，按以下菜单选择恢复策略：

| 错误类型 | 恢复策略 |
|---------|---------|
| Pydantic 格式错误 | 带 schema + 错误信息重试（feedback 包含具体字段修正） |
| Python gate 语义错误 | 带 gate 反馈重试（feedback 包含具体检查项修正） |
| 内容质量差（你的评估） | 提供更详细上下文重试 |
| Worker 超时 | 拆分任务 或 降级到更简单 prompt |
| 连续 3 次同一阶段失败 | 切换模型（如 strong → max）重试 |
| 重试耗尽（check-retry-limit 返回 false） | 上报主 Agent，不得继续重试 |
| 总预算超限（check-budget 返回 false） | 立即终止，上报主 Agent |

## 质量评估 5 维度

评估 Worker 输出时，从以下 5 个维度打分：

1. **完整性**：所有必需字段是否填写？是否有遗漏？
2. **一致性**：与前置阶段输出是否矛盾？内部是否自洽？
3. **可行性**：工作包是否可执行？依赖关系是否合理？
4. **架构原则符合度**：是否符合 Living Spec 中的架构原则？
5. **Schema 合规性**：是否满足 Pydantic schema 约束？

## 并行执行规则

- **默认串行执行**（推荐，除非有明确性能需求）
- 如需并行：`io_helper.py can-parallel <stage1> <stage2> <output_dir>`
- 返回 `can_parallel: true` 才允许并行
- **并行阶段数**：由 `can-parallel` 命令的返回结果决定，Orchestrator 不得手动绕过 can-parallel 的判断结果。多个阶段是否可并行，完全取决于 stage-dependencies.json 的依赖图 <!-- V3 FIX #6 -->
- **sessions_yield 语义明确**：多个 `sessions_spawn` 后，**一次 `sessions_yield()` 即可等待全部完成**（auto-announce 机制会逐个通知），禁止多次 yield
- **并行失败处理策略（V3 明确）**： <!-- V3 FIX #15 -->
  - 某个并行阶段失败时，**等待其他并行阶段全部完成**（不立即中断）
  - 已完成的并行阶段结果**保留**（不重做）
  - 仅重做失败阶段，重试前先 `check-retry-limit`
  - 如果失败阶段 `required: true` 且重试耗尽 → 阻塞管线，上报主 Agent
  - 如果失败阶段 `required: false` 且重试耗尽 → 标记 `skipped`，继续后续阶段

## 约束

- 你自主决定执行计划，不要问主 Agent（除非重试/预算耗尽）
- 每次决策后调用 `log-decision` 记录
- 启动时先 `resume-context` 检查断点
- 所有 spawn 必须传 `cwd`
- 重试前必须 `check-retry-limit`
- 每 2 阶段 `compact-history` 压缩上下文
```

### 5.2 Worker Prompt 模板（LLM 动态填充）

```markdown
# {stage_name} Worker

## 输入上下文
{auto_injected_dependencies}  ← io_helper.py 自动注入前置阶段输出
{orchestrator_context}        ← Orchestrator 通过 --context-file 提供

## 任务
{orchestrator_task}           ← Orchestrator 通过 --context-file 提供

## 期望输出格式
Pydantic Schema:
{schema_json}                 ← io_helper.py 自动注入

## 质量要求
{orchestrator_quality_criteria}  ← Orchestrator 通过 --context-file 提供

评估维度：完整性、一致性、可行性、架构原则符合度、Schema 合规性

## 输出路径
将结果写入: {output_path}    ← io_helper.py 自动注入
```

**与 V1 的区别**：
- Worker Prompt 模板中 `{stage_name}` 不再预定义为 5 个固定阶段，Orchestrator 可以自创阶段名
- `auto_injected_dependencies` 由 io_helper.py 基于 stage-dependencies.json 自动注入
- `--context-file` 替代 `--context`（避免命令行参数过长）

**`--context-file` 格式定义（V3 新增）**： <!-- V3 FIX #5 -->
- 文件类型：**JSON**（`.json`）
- 字段结构：
  ```json
  {
    "task": "本阶段要完成的具体任务描述（Orchestrator 填写）",
    "context": "补充上下文：为什么这样设计、与前阶段的关系（可选）",
    "quality_criteria": "本阶段质量评估标准（完整性、一致性等，Orchestrator 填写）"
  }
  ```
- Orchestrator 用 `exec: echo '{...}' > /tmp/ctx-<stage>.json` 写临时文件，然后传给 `build-prompt`
- `io_helper.py build-prompt` 读取该 JSON 并填充到 Worker Prompt 模板的对应占位符

---

## 六、可靠性保障（代码强制）

### 6.1 超时保护

| 层级 | 超时 | 机制 |
|------|------|------|
| Worker | 300s（5min） | `sessions_spawn(runTimeoutSeconds=300)` |
| Orchestrator | 1800s（30min） | `sessions_spawn(runTimeoutSeconds=1800)` |
| 管线总预算 | 30min | `io_helper.py check-budget --max-minutes 30` |
| Watcher 超时 | 30min | `max_runs: 15 × 3min`（已有） |

### 6.2 重试保护

```python
# io_helper.py check-retry-limit
def check_retry_limit(output_dir, stage, max_retries):
    state = load_pipeline_state(output_dir)
    current = state.get("stages", {}).get(stage, {}).get("retry_count", 0)
    return {
        "allowed": current < max_retries,
        "current": current,
        "max": max_retries,
        "action": "retry" if current < max_retries else "escalate"
    }
```

Orchestrator **每次重试前必须调用**。返回 `allowed: false` 时禁止重试。

### 6.3 三层退出机制（保留）

```
第一层：Orchestrator 写 .completed → Watcher 检测 → 通知 → cron 自杀
第二层：check-budget 超限 → Orchestrator 终止 → 上报
第三层：Watcher max_runs 超限 → 超时告警 → cron 自杀
```

### 6.4 断点恢复流程

```
Orchestrator 启动
  ↓
io_helper.py resume-context <output_dir>
  ↓
有已完成阶段？ → 是 → 从下一个待执行阶段继续
                → 否 → 从头开始
  ↓
有失败阶段？ → 是 → 检查 retry_count，未超限则重试，超限则上报
```

---

## 七、文件改造清单

| 文件 | 改造前 | 改造后 |
|------|--------|--------|
| `run_pipeline.py` (1053行) | 控制流 + I/O 混合 | 保留不删（回滚用） |
| `io_helper.py` (新建, ~400行) | 无 | 12 命令：I/O + 护栏 + 恢复 + 调试 |
| `stage-dependencies.json` (新建) | 硬编码在 run_pipeline.py | 显式声明阶段依赖 |
| Orchestrator prompt | "按固定列表循环" | 完整 AI Native prompt（见第五节） |
| `start_ship_pro.py` | 生成固定 spawn_params | 精简：路径准备 + spawn_params（含 cwd）+ watcher payload |
| `SKILL.md` V5.0 | V4.0 CLI 命令参考 | AI Native Orchestrator 指南 + 入口守卫 |
| `contracts/*.py` | Pydantic 模型 | 保留不改 |
| Watcher | V3 AI Native | 保留不改 |

---

## 八、迁移策略

### 8.1 步骤

| 步骤 | 动作 | 风险 |
|------|------|------|
| 1 | 创建 `stage-dependencies.json` | 零 |
| 2 | 从 `run_pipeline.py` 提取 I/O + 护栏 → `io_helper.py` | 低（纯提取） |
| 3 | 写 Orchestrator prompt（V2 完整版） | 低 |
| 4 | 更新 `start_ship_pro.py`（含 cwd） | 低 |
| 5 | 写 `SKILL.md` V5.0（含入口守卫） | 低 |
| 6 | 保留 `run_pipeline.py` 不删 | 零 |

### 8.2 入口守卫（SKILL.md Step 0）

```markdown
## Step 0: 防偏检查（强制）

在开始任何 Ship Pro 操作前，确认：
- [ ] 你不是在直接写代码或修改文件
- [ ] 你是在按 SKILL.md 的步骤启动管线
- [ ] 你有正确的输入路径（Living Spec 或 final_result.json）
- [ ] `openclaw config get maxSpawnDepth` ≥ 2（Orchestrator → Worker 需 2 层嵌套） <!-- V3 FIX #7 -->
- [ ] `DEEPFLOW_HOME` 环境变量已设置（默认 `~/.openclaw/workspace/.deepflow`）

如果以上任一项不满足 → 停止，向用户确认。
```

### 8.3 验证计划

| 步骤 | 验证内容 | 通过标准 |
|------|---------|---------|
| 1 | io_helper.py 每个命令 | 16 命令全部可执行，输出符合 schema |
| 2 | 单阶段执行 | Architect spawn → 完成 → validate-format + validate-quality pass |
| 3 | 多阶段串行 | 5 阶段全部完成，pipeline_state.json 正确 |
| 4 | 断点恢复 | 中途 kill Orchestrator → 重启 → 从断点继续 |
| 5 | 超时保护 | Orchestrator 超时 → 自动终止 → Watcher 超时告警 |
| 6 | 回滚 | 切回 V4 → 正常运行 |

### 8.4 回滚 SOP

```
1. 停止 AI Native Orchestrator（如运行中）
2. SKILL.md 切回 V4.0（git checkout）
3. start_ship_pro.py 切回 V4 版本
4. pipeline_state.json 增加 "version": "ai_native" 标记
5. V4 prepare_pipeline --resume 模式：不清理已有阶段输出
6. 重新运行
```

---

## 九、评审改进追踪

### V1 → V2（4 位专家，27/28 P0/P1 修复，96%）

| V1 评审问题 | V2 修复 | 对应专家 |
|------------|---------|---------|
| Prompt 缺少阶段依赖图 | §5.1 注入依赖图 + can-parallel 命令 | AI Native |
| Prompt 缺少质量评估维度 | §5.1 五维度质量标准 | AI Native |
| io_helper 缺 read-dependencies | list-dependencies 命令 | AI Native |
| io_helper 缺 log-decision | log-decision 命令（结构化 JSON） | AI Native |
| build-prompt --context 长度限制 | 改为 --context-file | AI Native |
| 缺少 Context Compaction | compact-history 命令 | AI Native |
| 缺少 Goal Judge | 独立 Judge Worker | AI Native |
| spawn_params 缺 cwd | §5.1 强制 cwd 规范 | OpenClaw |
| Worker spawn 未要求 cwd | §5.1 sessions_spawn 规范 | OpenClaw |
| io_helper API 未完整定义 | §3.1 完整 **16** 命令清单 | OpenClaw |
| SKILL.md 缺入口守卫 | §8.2 Step 0 防偏检查 | OpenClaw |
| 无超时保护 | §6.1 四层超时机制 | Reliability |
| 重试无代码强制 | §6.2 check-retry-limit 命令 | Reliability |
| 无断点恢复 | §3.4 resume-context + checkpoint | Reliability |
| write-status 无枚举校验 | §3.3 枚举校验 + 原子写入 | Reliability |
| 并行安全无保障 | §4 stage-dependencies + can-parallel | Pipeline |
| 质量门控退化 | validate-quality 保留 Python gate | Pipeline |
| 阶段可跳过 | validate-plan --required | Pipeline |
| 阶段间数据依赖不透明 | stage-dependencies.json + 自动注入 | Pipeline |
| .stage_progress.json 未提及 | 保留，确保 Watcher 兼容 | Pipeline |

### V2 → V3（4 位专家，17 P2 + 1 P3 全部修复，100%）

| V2 问题 | V3 修复 | 来源 |
|---------|---------|------|
| 命令数量不一致 | §3.1 标题改为 16 个 | 架构师 |
| compact-history 实现未明确 | 纯提取 + 结构化 JSON | 架构师 |
| Judge Worker 失败处理 | fail 分支 + 重 Judge + 上报 | 架构师 |
| validate-quality 与 gate 关系 | 三层验证分工表 | 架构师 |
| context-file 格式未定义 | JSON schema 三字段 | 架构师 |
| sessions_yield 语义不明 | 默认串行 + 单次 yield | 架构师 |
| maxSpawnDepth 未确认 | 入口守卫增加配置检查 | 平台 |
| cwd 硬编码 | 改用 DEEPFLOW_HOME | 平台 |
| exec 约束仅在 prompt | io_helper 文件头强化 | 平台 |
| 自创阶段 gate_fn 缺失 | fallback 到 format-only | 管线 |
| compact-history 信息丢失 | 字段级摘要 + top-3 值 | 管线 |
| Judge 失败降级 | Orchestrator 自评（标记） | 管线 |
| 并行 blackboard 冲突 | TODO（树状图无风险） | 管线 |
| compact-history 丢失败细节 | 保留最近 2 阶段完整记录 | 可靠性 |
| 并行失败策略模糊 | 保留成功 + 仅重做失败 | 可靠性 |
| write-status 时序窗口 | resume-context 文件扫描 | 可靠性 |
| Judge 评估可靠性 | 与 Python gate 交叉验证 | 可靠性 |

> 完整追踪详见 `P2_FIXES_V3.md`

---

## 十、不在本次范围

- ❌ Spec Pro / Solution Pro AI Native 改造（独立域）
- ❌ Dream Loop / Meta-Loop（后续，但 decisions.jsonl 提供数据基础）
- ❌ Hermes / Codex 集成（后续）
- ❌ Watcher 改造（已是 AI Native V3）
- ❌ Pydantic 模型重定义（保留现有）
- ❌ 并行 blackboard 文件锁（当前树状依赖图无风险，待未来场景需要时再实现）

---

*等待第三轮专家评审（3 位新专家：AI Native 工程师 / 分布式系统专家 / 开发者体验专家）...*
