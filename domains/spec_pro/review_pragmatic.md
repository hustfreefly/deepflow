# Spec Pro 系统性修复计划 — 务实评审意见

> 评审人：务实工程评审专家（Subagent）
> 评审依据：REMEDIATION_PLAN.md + coordinator.py (991行) + merge_spec.py (31个setdefault/11个isinstance) + frozen_spec.py (已有部分防御) + 7个 Prompt (1187行)

---

## 总体评估

**30 个问题 → 5 个根因 → 5 个修复策略** 的归纳逻辑正确。但执行顺序、工作量估算、以及"代码改 vs Prompt 改"的分界需要调整。

---

## Phase 1 — S1: Schema 契约层

**评审: ⚠️ 调整建议**

### 问题 1: "schemas.py + 双向校验" 过重

计划说"Prompt 和 Code 都从这个 Schema 生成或校验"。实际上：

- **代码侧校验**（merge_spec.py 入口加 schema 校验）：值得做，但 7 个 setdefault 已经有 11 个 isinstance 守卫，说明代码侧防御已经部分存在。schema 校验应该做成"软校验"（warn 但不 throw），否则 Orchestrator Worker 输出轻微偏差就会导致整个 pipeline 崩溃。
- **Prompt 侧对齐**（更新 7 个 Prompt 的 schema 示例）：7 个 Prompt 文件共 1187 行，每个的 JSON 示例都嵌在 Markdown 模板里。**这是体力活，3h 估算偏低**。

### 问题 2: schemas.py 的设计决策风险

用一个 Python dict 定义所有 Schema 存在维护问题：
- Python dict 没有 JSON Schema 的 `required`、`type` 约束语义
- 如果未来需要真正的校验，应该用 `pydantic` 或 `jsonschema` 库

### 调整建议

| 项 | 原计划 | 建议 |
|---|--------|------|
| schemas.py 创建 | 完整定义 4 个 Schema | ✅ 保留，但只定义 **LIVING_SPEC_SCHEMA** 和 **ROUND_RESULT_SCHEMA**（解决 6/9 个问题） |
| 代码侧校验 | 严格校验 | 改为 **软校验**（`logging.warning` 而非 `raise`），保留现有 setdefault 行为 |
| Prompt 对齐 | 7 个 Prompt 全部更新 | 先对齐 **parse.md** 和 **parse_response.md**（P0-1/P0-2 根因），其余留到 S2/S4 时顺手做 |
| 工作量 | 3h | **4h**（schemas.py 创建 1.5h + 代码侧软校验 0.5h + 2 个 Prompt 对齐 1h + 测试 1h） |

### 可并行的机会

S1 中的 schemas.py 创建和 S3 中的 `_generate_session_id()` 改动 **完全独立**，可并行。

---

## Phase 2 — S2: Prompt 写入协议

**评审: ✅ 可行（但 1h 偏低）**

### 分析

`_init_phase_instructions()` 和 `_collecting_phase_instructions()` 是 coordinator.py 里最长的两个方法（分别 ~130 行和 ~250 行纯字符串）。在其中添加 `write`/`exec` 命令是**纯字符串插入**，不涉及逻辑变更。

**但 1h 估算忽略了**：
- 插入后需要验证模板变量的 `{Blackboard}` 替换是否在所有新增行中正确
- `_collecting_phase_instructions` 有 3 个分支（A/B/C），每个分支末尾都需要加
- 修改后需要跑一轮端到端验证（至少模拟 Round 1 → Round 2）

### 调整建议

工作量调整为 **1.5h**（编辑 40min + 验证 50min）。

### 依赖关系

计划说"依赖 S1（需要统一 quality schema）"——**实际上不依赖**。写入协议只关心"写什么文件"，不关心文件内容的 schema。S2 可以在 S1 之前或并行执行。

---

## Phase 3 — S3: 防御性编程

**评审: ⚠️ 调整建议 — 部分修复可用 Prompt 替代，部分被低估**

### 逐项评估

| # | 修复项 | 代码改? | 可 Prompt 替代? | 理由 |
|---|--------|---------|-----------------|------|
| 1 | `_generate_session_id()` 改 uuid4 | ✅ 代码改 | ❌ | 3 行代码改动，30s 的事。**高收益低成本，被严重低估** |
| 2 | ParseWorker fallback 补创建 living_spec.json | ✅ 代码改 | ❌ | worker_fallback.py 改动，~20 行 |
| 3 | `merge_confirmed()` setdefault 前加 isinstance | ⚠️ 部分 | ⚠️ | **已有 11 个 isinstance 守卫**。新增的应该是针对 `updates` 参数本身的结构校验，而不是每个字段。建议在 `merge_spec()` 入口做一次 `validate_response_structure(response)` 即可，不需要 31 个 setdefault 前都加 |
| 4 | `build_next_round_task()` 检查 KILLED 状态 | ✅ 代码改 | ❌ | 2 行 if 检查，30s 的事。**高收益低成本** |
| 5 | `spec_pro_api.py` json.load() 加 try/except | ✅ 代码改 | ❌ | 但 coordinator.py 的 `read_round_output()` 和 `is_done()` **已经有 try/except**，需要确认 spec_pro_api.py 是否真的缺（计划没列文件名） |
| 6 | FALLBACKS 补全缺失字段 | ⚠️ 视情况 | ❌ | 需要先确认具体缺哪些字段 |
| 7 | process_guard 负 delta 分支 + NaN 校验 | ✅ 代码改 | ❌ | 需要看 process_guard.py 现状才能准确估算 |

### Prompt 可替代的项

| 修复项 | Prompt 替代方案 | 评估 |
|--------|-----------------|------|
| P0-8 损坏字段类型崩溃 | 在 `parse_response.md` 的 Output Format 部分加强类型约束示例 | ⚠️ 可以辅助但不能替代——LLM 不可靠，最终需要代码兜底 |
| P1-18/19 API JSON 损坏 | 在 Worker Prompt 中强调 "必须输出合法 JSON，不要包含 markdown 代码块外的内容" | ⚠️ 同样的理由：需要代码 try/except 作为最后防线 |

**结论**：S3 中 **没有一项可以完全用 Prompt 替代代码改**。但第 3 项（31 个 setdefault 前加 isinstance）建议改为**入口一次校验**，大幅减少改动量。

### 调整建议

| 项 | 原计划 | 建议 |
|---|--------|------|
| merge_confirmed 逐字段校验 | 每个 setdefault 前加 isinstance | 改为 **merge_spec() 入口一次结构校验**（~30 行），减少 50% 改动量 |
| 工作量 | 2h | **1.5h**（入口校验 40min + uuid4/session_id 5min + KILLED 检查 5min + json 异常处理 20min + 其他 20min） |

---

## Phase 4 — S4: 下游消费 Adapter

**评审: ⚠️ 调整建议 — frozen_spec.py 已有部分消费，新增量被高估**

### 分析 frozen_spec.py 现状

`build_frozen_spec()` **已经在消费**：
- `confirmed` 的 10+ 个字段
- `guardrails`（顶层）
- `solution_pro_hints`
- `requirement_annotations`（通过 `_merge_annotations`）

**实际缺的消费**：
- `route_recommendation`（living_spec 顶层字段）
- `user_directives`（confirmed 层）
- `inferred_pending`（inferred 层）
- `layer2_hints`（如果存在）
- `anti_patterns`（如果存在）

### 工作量再评估

计划说 3h。实际是：
- `build_context_from_living_spec()` 函数编写：~40 行（1h）
- task_builder.py 改动（注入 deliberately_omitted_dimensions）：需要看 task_builder.py 现状（1h）
- 移除 hints 展平逻辑：5 行改动（15min）
- 验证（确认下游 Worker 能正确消费新字段）：30min

**工作量调整为 2.5h**（计划高估了 30min）。

### 依赖关系

依赖 S1 中 user_directives 的 schema 定义——**合理**。但如果不先定义 schema，adapter 也可以直接写，只需要加 isinstance 校验。

---

## Phase 5 — S5: 代码清理

**评审: ✅ 可行**

3 项改动都很小：
1. 删除 utils.py::check_process_guard()：1 行删 + 检查调用点
2. user_confirmation.md → user_confirmation.json：文件名改 + coordinator.py 中 1 处引用改
3. Round 1 QuestionWorker 删除自引用：需要确认具体是哪一行

**30min 估算合理**。

### 前置依赖

第 2 项（扩展名改）需要确认所有引用 `user_confirmation.md` 的地方（不止 coordinator.py），否则会有静默断裂。

---

## 验证标准评估

### ❌ "模拟完整 3 轮对话流程验证端到端" 不够具体

**问题**：
1. 谁提供 3 轮模拟数据？Mock？真实历史对话？
2. "验证"的定义是什么？不崩溃？产出符合预期的 frozen_spec？
3. 自动化程度？手动跑？写测试？

**建议的验证方案**：

| Phase | 验证方式 | 具体标准 |
|-------|---------|---------|
| S1 | 单元测试 | `merge_spec.py` 用 3 种畸形输入测试（缺字段/类型错误/null）→ 不崩溃且产生 warning |
| S2 | 集成测试 | `coordinator.init_session()` 返回的 orchestrator_task 字符串中 grep 确认包含 `write` 或 `exec` 命令 |
| S3 | 单元测试 | 直接调用 `_generate_session_id()` 100 次确认无碰撞；给 `merge_spec()` 传入非 JSON 文件确认返回 error |
| S4 | 集成测试 | 构造一个包含 route_recommendation/user_directives/inferred_pending 的 living_spec → `build_frozen_spec()` → 确认 frozen_spec 中包含对应字段 |
| S5 | 回归测试 | `grep -r "user_confirmation.md" .deepflow/` 返回 0 结果 |

**端到端验证**建议放在 **S5 完成后统一做一次**，而不是每个 Phase 各跑一遍。理由：
- 前 4 个 Phase 的验证用单元测试覆盖即可
- 端到端验证成本高（需要模拟完整流程），跑一次比跑 5 次更可靠
- 如果每个 Phase 后都跑，总验证时间会从 30min × 1 变成 30min × 5

---

## 最优执行顺序建议

原计划的顺序是 S1 → S2 → S3 → S4 → S5（串行 10h），我认为最优顺序是：

### 推荐顺序（并行化后 ~6.5h）

```
ParallelGroup A (1h):
  ├─ S5-1: _generate_session_id() → uuid4        [5min]
  ├─ S5-2: build_next_round_task KILLED 检查       [5min]
  └─ S5: 代码清理剩余项                             [50min]
     → 风险最低，先做可以释放心理负担

ParallelGroup B (4h):
  ├─ S1: Schema 契约层                             [4h]
  │   ├─ schemas.py 创建（2 Schema）                [1.5h]
  │   ├─ merge_spec.py 入口软校验                    [0.5h]
  │   ├─ parse.md + parse_response.md 对齐           [1h]
  │   └─ 测试                                       [1h]
  │
  └─ S2: Prompt 写入协议 (可并行，不依赖 S1)         [1.5h]
      ├─ init/collecting/confirmation 加 write 命令  [40min]
      └─ 验证模板变量替换                             [50min]

Sequential C (2h, 依赖 B 完成):
  ├─ S3: 防御性编程（精简版）                        [1.5h]
  │   ├─ merge_spec() 入口结构校验                    [40min]
  │   ├─ json 异常处理                               [20min]
  │   ├─ 其他小项                                    [20min]
  │   └─ 测试                                       [10min]
  │
  └─ S4: 下游 Adapter                               [2.5h]
      ├─ build_context_from_living_spec()           [1h]
      ├─ task_builder.py 改动                       [1h]
      ├─ 移除 hints 展平                             [15min]
      └─ 验证                                       [15min]

Sequential D (30min):
  └─ 端到端验证（完整 3 轮模拟）
```

### 为什么这个顺序更好？

| 维度 | 原计划 | 建议 | 理由 |
|------|--------|------|------|
| 总时间 | 10h 串行 | ~6.5h 部分并行 | B 组 S1/S2 可并行 |
| S3 位置 | 第 3 个（串行） | 在 S1 之后（利用 schema） | S3 的入口校验可以复用 S1 的 schema |
| S2 依赖 S1 | 依赖 | 不依赖 | S2 只加 write 命令，不涉及 schema |
| 验证策略 | 每个 Phase 各跑 | 单元各跑 + 端到端统一 1 次 | 减少重复劳动 |
| 风险顺序 | 大改 → 小改 | 小改(S5) → 中改(S1/S2) → 大改(S4) | 先做低风险改动建立信心 |

---

## 被低估的高收益修复

| 修复 | 工作量 | 影响 | 原因 |
|------|--------|------|------|
| `_generate_session_id()` → uuid4 | 30 秒 代码改 | 消除 P0-6 碰撞风险 | 1 行改，消除整个 P0 级 bug |
| `build_next_round_task()` KILLED 检查 | 30 秒 代码改 | 消除 P1-14 安全停止后仍可调用 | 2 行 if |
| S2 写入协议 | 1.5h | 消除 2 个 P0（round_result.json 缺失） | 纯字符串插入，零逻辑风险 |

**建议优先做这三个**。总共不到 2h，消除 3 个 P0 + 1 个 P1。

---

## 被高估的低收益修复

| 修复 | 原估 | 建议 | 原因 |
|------|------|------|------|
| 31 个 setdefault 前逐个加 isinstance | S3 中的主要工作量 | 改为入口一次校验 | 代码已有 11 个 isinstance 守卫；入口校验 + 软 warning 足够 |
| S1 中 7 个 Prompt 全部对齐 | 包含在 3h 内 | 先对齐 2 个核心 Prompt | 其余 5 个可以在 S2/S4 执行时顺手改，不需要专门做 |

---

*评审完成 | 2026-06-02 23:49*
