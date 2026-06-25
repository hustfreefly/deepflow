# Ship Pro AI Native 改造方案 V2

> **日期**: 2026-06-25  
> **版本**: V2（吸收第一轮 4 位专家评审意见）  
> **作者**: 小满（AI Agent）  
> **决策者**: 姬忠礼  
> **状态**: 待第二轮专家评审

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

### 3.1 命令清单（12 个命令）

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
python3 io_helper.py check-retry-limit <output_dir> <stage> --max <N>
```

**逻辑**：读取 `pipeline_state.json` 中该阶段的 `retry_count`，与 max 比较。  
**输出**：
```json
{"allowed": false, "current": 3, "max": 3, "action": "escalate"}
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
**与 validate-format 的区别**：
- `validate-format`：Pydantic 检查字段类型/必填/枚举
- `validate-quality`：Python 检查业务逻辑（依赖无环、模块覆盖率、需求映射完整性）

**输出**：
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

**逻辑**：
1. 读取 decisions.jsonl 中所有决策
2. 读取各阶段输出的摘要（前 500 字符 + schema 字段列表）
3. 生成结构化摘要 JSON

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
    "architect": {"modules": 8, "principles": 5, "file": "blackboard/architect/..."},
    "decomposer": {"work_packages": 16, "file": "blackboard/decomposer/..."}
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
    cwd="/Users/allen/.openclaw/workspace/.deepflow",  # ⚠️ 必须传 cwd
    runTimeoutSeconds=300  # Worker 超时 5 分钟
)
```

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
      cwd="/Users/allen/.openclaw/workspace/.deepflow",
      runTimeoutSeconds=300
  )
  ```
- Judge 评估维度：完整性、一致性、可行性、架构原则符合度、Schema 合规性
- Judge 输出：`{"verdict": "pass|fail|conditional", "score": 85, "issues": [...]}`

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

- 默认串行执行
- 如需并行：`io_helper.py can-parallel <stage1> <stage2> <output_dir>`
- 返回 `can_parallel: true` 才允许并行
- 并行 spawn 多个 Worker 后，多次 `sessions_yield()` 等待全部完成
- 并行阶段中某个失败 → 等待其他完成后统一处理

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

如果以上任一项不满足 → 停止，向用户确认。
```

### 8.3 验证计划

| 步骤 | 验证内容 | 通过标准 |
|------|---------|---------|
| 1 | io_helper.py 每个命令 | 12 命令全部可执行，输出符合 schema |
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

## 九、与 V1 对比（评审改进追踪）

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
| io_helper API 未完整定义 | §3.1 完整 12 命令清单 | OpenClaw |
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

---

## 十、不在本次范围

- ❌ Spec Pro / Solution Pro AI Native 改造（独立域）
- ❌ Dream Loop / Meta-Loop（后续，但 decisions.jsonl 提供数据基础）
- ❌ Hermes / Codex 集成（后续）
- ❌ Watcher 改造（已是 AI Native V3）
- ❌ Pydantic 模型重定义（保留现有）

---

*等待第二轮专家评审...*
