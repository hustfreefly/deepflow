# 评审报告：管线工程专家

> **评审人**: 管线工程专家（管线工程质量评审）  
> **评审日期**: 2026-06-25  
> **评审对象**: `SHIP_PRO_AI_NATIVE_PROPOSAL.md`  
> **评审范围**: 管线工程质量（阶段完整性、质量门控、数据流、并行安全、可观测性）

---

## 总评

- **总评分**: 5.5/10
- **核心判断**: 方案在 I/O 层拆分上设计清晰（io_helper.py 纯 I/O + Pydantic 保留格式校验），但将控制流完全交给 LLM 后，**阶段完整性、质量门控、数据传递、并行安全**四个核心工程保障均缺乏可执行的兜底机制，存在从"工程化管线"退化为"LLM 即兴发挥"的实质性风险。

---

## 逐维度评审

### 1. 阶段完整性保证 (4/10)

**问题**：方案明确写道"不一定要全部 5 个"，但没有机制防止 LLM 跳过关键阶段。

**当前实现**：
- `AGENT_ORDER = ["architect", "decomposer", "specifier", "reviewer", "packager"]` 硬编码，Python 循环保证每个阶段至少执行一次
- `GATE_CONFIG` 为每个阶段定义 `max_retries`，失败后强制重试

**AI Native 后**：
- Orchestrator LLM 自主决定"需要哪些阶段"
- Prompt 约束 + 最终评估阶段强制全量检查（方案第五节）

**风险**：
1. **LLM 可能跳过 Reviewer**：Reviewer 是质量守门人，如果 LLM 认为"这个任务简单，不需要 review"，直接跳过，下游 Packager 拿到的就是未经审计的输出
2. **LLM 可能跳过 Decomposer/Specifier**：对于复杂任务，这两个阶段是工作分解的核心，跳过会导致 Packager 直接生成粗粒度 WP
3. **最终评估无法弥补**：最终评估是"事后检查"，如果中间阶段缺失，最终评估发现的问题已经无法回溯补充（除非重试整个流程）

**建议**：
- **P0**: 在 `io_helper.py` 中增加 `required-stages` 参数，Orchestrator 规划阶段后调用 `io_helper.py validate-plan --required architect,reviewer,packager`，Python 侧强制校验关键阶段不能跳过
- **P1**: 最终评估阶段如果发现阶段缺失，应能触发"补执行"而非"整体重试"

### 2. 质量门控有效性 (5/10)

**问题**：Pydantic 格式校验保留（好），但质量判断从"固定 retry + gate_fn"变为"LLM 评估"，存在退化为"橡皮图章"的风险。

**当前实现**：
- `gate_architect`, `gate_reviewer`, `gate_packager` 是确定性 Python 函数
- 检查具体字段：`modules (non-empty)`, `dependencies (acyclic)`, `requirements[].mapped_components (all present)`
- 失败后固定 retry，max_retries 硬编码

**AI Native 后**：
- `io_helper.py validate-format` 只做 Pydantic 格式校验（pass/fail + errors）
- 内容质量由 Orchestrator LLM "自己的判断"

**风险**：
1. **格式通过 ≠ 质量通过**：Pydantic 只能检查 `modules: list[Module]` 非空，不能检查模块划分是否合理、依赖是否循环、需求是否覆盖所有组件
2. **LLM 评估过松**：方案自己也承认"LLM 质量评估过松（垃圾输出通过）"是中等概率风险
3. **无 retry 上限**：当前 `max_retries=5` 是硬编码，AI Native 后 Orchestrator "最多 3 次"是 prompt 约束，LLM 可能不遵守

**建议**：
- **P0**: 保留关键 gate 函数（`gate_architect`, `gate_reviewer`）作为 Python 侧的硬校验，LLM 评估不能替代
- **P1**: `io_helper.py validate-format` 应扩展为 `validate-quality`，除了 Pydantic 格式校验，还调用 Python 实现的语义检查（如依赖无环、需求覆盖率计算）
- **P2**: retry 上限应由 Python 侧强制（`io_helper.py check-retry-limit <stage> <max>`），而非 prompt 约束

### 3. 阶段间数据流 (6/10)

**问题**：当前 `STAGE_PATH_REGISTRY` 精确管理阶段间数据传递，AI Native 后由 `io_helper.py` 接管，但方案未明确数据传递的完整机制。

**当前实现**：
- `STAGE_PATH_REGISTRY` 定义每个阶段的输入/输出路径
- `read_stage_output()`, `write_stage_output()` 精确读写 blackboard 文件
- 阶段间数据依赖由 Python 控制流保证（architect 输出 → decomposer 输入）

**AI Native 后**：
- `io_helper.py read-output <stage> <output_dir>` 读取某阶段输出
- Orchestrator LLM 负责"为每个阶段提供上下文"

**风险**：
1. **LLM 可能遗漏上下文**：Orchestrator 构建 worker prompt 时，可能忘记传递某个前置阶段的输出（如忘记把 Architect 的 `architecture_principles` 传给 Specifier）
2. **数据依赖不透明**：当前 `STAGE_PATH_REGISTRY` 是显式声明，AI Native 后数据依赖隐式存在于 LLM 的规划中，难以审计
3. **上下文窗口限制**：如果 Orchestrator 把所有阶段输出都塞进 worker prompt，可能超出上下文窗口

**建议**：
- **P0**: `io_helper.py` 应保留 `STAGE_PATH_REGISTRY` 的等价物（如 `stage-dependencies.json`），明确声明每个阶段的输入/输出依赖
- **P1**: `io_helper.py build-prompt` 应自动注入前置阶段的输出（基于依赖声明），而非依赖 LLM 手动传递
- **P2**: 增加 `io_helper.py list-dependencies <stage>` 命令，帮助 Orchestrator 理解数据依赖

### 4. 并行安全性 (3/10)

**问题**：方案提到"支持并行阶段"，但没有具体机制说明 LLM 如何判断哪些阶段可以并行。

**当前实现**：
- 串行执行，无并行问题
- `DependencyGraph.parallel_groups` 在 ShipPackage 中定义，但这是最终输出，不是执行时的并行控制

**AI Native 后**：
- Orchestrator LLM "决定哪些阶段可以并行"
- `sessions_spawn(worker)` 启动 Worker，可并行

**风险**：
1. **LLM 误判并行安全性**：如果 LLM 认为 Architect 和 Decomposer 可以并行（实际上 Decomposer 依赖 Architect 输出），会导致数据竞争
2. **blackboard 文件冲突**：多个 Worker 同时写 blackboard 文件，可能导致数据损坏
3. **无锁机制**：当前无文件锁或并发控制，并行写入无保护

**建议**：
- **P0**: `io_helper.py` 应提供 `can-parallel <stage1> <stage2>` 命令，基于 `stage-dependencies.json` 判断两个阶段是否可并行
- **P1**: blackboard 文件应增加写入锁（如 `.lock` 文件或原子写入）
- **P2**: Orchestrator prompt 应明确说明"默认串行，除非 io_helper.py can-parallel 返回 true"

### 5. 可观测性 (7/10)

**问题**：当前 `pipeline_state.json` + `.stage_progress.json` 提供可观测性，AI Native 后 `pipeline_state.json` 保留，但 `.stage_progress.json` 未提及。

**当前实现**：
- `pipeline_state.json` 记录每个阶段的状态（pending/running/gate_pass/gate_fail/done）
- `.stage_progress.json` 记录阶段的中间进度（给 Watcher 用）
- `decisions.jsonl` 未提及，但方案新增

**AI Native 后**：
- `pipeline_state.json` 保留（通过 `io_helper.py write-status`）
- `decisions.jsonl` 新增（记录 LLM 决策）
- `.stage_progress.json` 未提及

**风险**：
1. **LLM 决策不透明**：如果 `decisions.jsonl` 记录不完整，难以审计 LLM 为什么跳过某个阶段或为什么认为输出质量合格
2. **Watcher 兼容性**：Watcher 依赖 `.stage_progress.json`，如果移除会导致 Watcher 失效
3. **调试困难**：LLM 控制流的调试比 Python 控制流困难，需要更详细的日志

**建议**：
- **P0**: 保留 `.stage_progress.json`，确保 Watcher 兼容性
- **P1**: `decisions.jsonl` 应结构化（JSON 格式），包含时间戳、决策类型、输入、输出、理由
- **P2**: 增加 `io_helper.py dump-state` 命令，输出当前管线状态的完整快照（便于调试）

---

## 必须修改的问题（P0/P1）

| # | 严重度 | 问题 | 建议 |
|---|--------|------|------|
| 1 | P0 | LLM 可能跳过关键阶段（Reviewer/Decomposer） | `io_helper.py validate-plan --required` 强制校验关键阶段不能跳过 |
| 2 | P0 | 质量门控退化为"橡皮图章" | 保留 Python 侧 gate 函数（`gate_architect`, `gate_reviewer`），LLM 评估不能替代 |
| 3 | P0 | 阶段间数据依赖不透明 | `io_helper.py` 保留 `stage-dependencies.json`，`build-prompt` 自动注入前置阶段输出 |
| 4 | P0 | 并行安全性无保障 | `io_helper.py can-parallel` 命令 + blackboard 文件写入锁 |
| 5 | P1 | retry 上限由 prompt 约束，LLM 可能不遵守 | `io_helper.py check-retry-limit` 强制校验 |
| 6 | P1 | `.stage_progress.json` 未提及，Watcher 可能失效 | 保留 `.stage_progress.json`，确保 Watcher 兼容性 |

---

## 建议改进（P2）

1. **`io_helper.py` 命令扩展**：
   - `validate-plan --required`：校验执行计划包含必要阶段
   - `validate-quality`：扩展格式校验为语义校验（依赖无环、需求覆盖率）
   - `check-retry-limit`：强制校验 retry 上限
   - `can-parallel`：判断阶段是否可并行
   - `list-dependencies`：输出阶段数据依赖
   - `dump-state`：输出管线状态完整快照

2. **`decisions.jsonl` 结构化**：
   ```json
   {
     "timestamp": "2026-06-25T20:00:00Z",
     "decision_type": "skip_stage|retry|pass_quality|fail_quality",
     "stage": "reviewer",
     "input_summary": "...",
     "output_summary": "...",
     "reasoning": "..."
   }
   ```

3. **混合控制流**：
   - 关键路径（Architect → Reviewer → Packager）由 Python 强制保证顺序
   - 非关键路径（Decomposer/Specifier）由 LLM 动态规划
   - 这样既保留 AI Native 的灵活性，又保证核心工程保障

---

## 亮点

1. **I/O 层拆分清晰**：`io_helper.py` 纯 I/O + Pydantic 格式校验，职责单一，易于测试
2. **保留 Pydantic 契约**：没有因为 AI Native 而抛弃格式校验，这是正确的
3. **`decisions.jsonl` 设计**：记录 LLM 决策，为未来 Dream Loop 提供数据，有前瞻性
4. **回滚方案**：保留旧 `run_pipeline.py` 作为 backup，风险可控
5. **迁移策略稳健**：不删旧的，新建并行，逐步验证

---

## 总结

方案在 I/O 层设计上有工程思维，但在控制流层（LLM 动态规划）缺乏工程保障。**核心问题是：把控制流完全交给 LLM 后，谁来保证 LLM 不做蠢事？**

建议采用**混合控制流**：关键路径由 Python 强制保证，非关键路径由 LLM 动态规划。这样既保留 AI Native 的灵活性，又保证管线工程质量。

**评分依据**：
- 阶段完整性保证 4/10：缺乏强制机制，LLM 可能跳过关键阶段
- 质量门控有效性 5/10：Pydantic 保留但语义检查缺失，LLM 评估可能过松
- 阶段间数据流 6/10：io_helper.py 设计合理但依赖 LLM 手动传递上下文
- 并行安全性 3/10：无具体机制，存在数据竞争风险
- 可观测性 7/10：pipeline_state.json 保留，decisions.jsonl 有前瞻性，但 .stage_progress.json 未提及

**总评分**: 5.5/10
