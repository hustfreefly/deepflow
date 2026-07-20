# Deliver Pro V1 — 全角色规格说明书

> **版本**: V1.0.0 | **日期**: 2026-07-11 | **状态**: 设计稿
> **覆盖模块**: Orchestrator / Analyze / Worker / Integrate / Validate / Package

---

## 一、角色总览

### 1.1 流水线架构

```
WP (Work Package, 来自 Ship Pro)
  │
  ▼
Phase 1: Analyze Agent ──→ execution_plan.json
  │
  ▼
Phase 2: Worker × N (滑动窗口并发) ──→ worker_outputs/{task_id}/
  │
  ▼
Phase 3: SmartAssembler (Python) ──→ integrated_draft/
  │
  ▼
Phase 4: Validate Judge ←──→ SmartAssembler (单 Loop, ≤5 轮)
  │
  ▼
Phase 5: Package Agent ──→ final_deliverable/ + delivery_manifest.json
```

### 1.2 角色清单

| 模块 | 角色 | 类型 | 职责一句话 |
|------|------|------|-----------|
| Orchestrator | Orchestrator | 调度器 (depth-1) | 驱动 5 阶段流水线，管理 Validate Loop |
| Phase 1 | Analyze Agent | Worker (depth-2) | 解析 WP → 执行计划（任务分解 + 依赖图 + 并发建议） |
| Phase 2 | Worker × N | Worker (depth-2) | 执行单个子任务，产出代码/报告/文档 |
| Phase 3 | SmartAssembler | Python 确定性拼接 | 组装所有 Worker 输出为统一交付物草稿（零 LLM 调用） |
| Phase 4 | Validate Judge | Worker (depth-2) | 质量判定：PASS / FAIL + fix_directives |
| Phase 5 | Package Agent | Worker (depth-2) | 最终打包 + 组件级诚实交付 |

---

## 二、Orchestrator（调度器）

| 属性 | 值 |
|------|-----|
| **类型** | 调度器 (depth-1) |
| **职责** | 驱动 5 阶段流水线，管理 Validate Loop (≤5 轮)，验证每阶段输出 |

### ⚠️ Yield 唤醒规则（铁律）

Orchestrator 使用 `sessions_yield()` 等待子 Agent 完成时，**唤醒后第一个 action 必须是 `exec` 或 `read`，禁止直接生成文字。**

```
✅ 正确：yield 返回 → exec("cat blackboard/.../validation_result.json") → 分析结果
❌ 错误：yield 返回 → "看起来 Validate Judge 已经完成了..."（直接生成文字）
```

**原因**：yield 返回后如果 LLM 先生成文字而非 tool call，会导致 pipeline 中断（OpenClaw 将文字输出视为 turn 结束）。

**防御措施**：
1. yield 前在 task prompt 中写入 `exec cat {path}` 作为唤醒后第一个动作
2. 使用 cron wake 替代 sessions_yield（更可靠）
3. 每次 wake-up turn 必须输出可见文字（防止 NO_VISIBLE_REPLY 警告）

**输入（可读）**：
- `data/wp.json` — Work Package（原始需求）
- Blackboard 各 stage（验证用）

**权限**：
- ✅ spawn Phase 1-5 的 Agent
- ✅ 读 Blackboard 验证输出完整性
- ✅ 写 `delivery_state.json` 和 `.stage_progress`
- ✅ 写 `.failed` / `.completed` 标记
- ✅ LLM 判断 Worker 失败原因 + 生成恢复策略（废除 F1-F8 查表）
- ❌ 不能自己生成任何阶段的输出
- ❌ 不能修改 wp.json
- ❌ 不能跳过任何阶段

**调度逻辑**：

```
Phase 1: spawn Analyze → 验证 execution_plan
  → PASS → Phase 2
  → FAIL → 写 .failed

Phase 2: 按 execution_plan 依赖图 + 并发建议
         滑动窗口 spawn Worker（依赖检查 → spawn → 完成 → 填充）
  → Worker 失败 → LLM 诊断 + 生成恢复策略 → 重试（≤3 轮/WP）
  → 3 轮仍失败 → 标记 FAILED（不是 SKIP）

Phase 3: run SmartAssembler → 验证 integrated_draft
  → PASS → Phase 4 (Round 1)

Phase 4 Loop (≤5 轮):
  spawn Validate Judge → 读 validation_result
    → PASS → Phase 5
    → FAIL + fix_directives → SmartAssembler 定向重组 → 回到 Validate
    → LLM 判断"无改进空间" / 5 轮上限 → 进入 Phase 5（标记 unvalidated）

Phase 5: spawn Package → 验证 delivery_manifest
  → 全部 PASS → 完整交付
  → 部分 FAIL + 组件独立 → 交付成功部分 + 失败报告
  → 部分 FAIL + 核心依赖缺失 → 不交付 + 失败报告 + 行动选项
```

---

## 三、Phase 1 — Analyze Agent（分析器）

| 属性 | 值 |
|------|-----|
| **类型** | Worker (depth-2) |
| **职责** | 解析 WP → 执行计划（任务分解 + 依赖图 + 并发建议 + 场景判定） |

**输入**：`data/wp.json`
**权限**：
- ✅ `web_search`（技术可行性、最佳实践）
- ✅ `read`（WP 和约束文件）
- ✅ 写 Blackboard stage
- ❌ 不能 spawn 子 Agent
- ❌ 不能 `exec`

**输出**：`execution_plan.json`

```json
{
  "schema_version": "1.0.0",
  "wp_id": "WP-001",
  "scenario": "code | report | mixed",
  "task_graph": [
    {
      "task_id": "T-001",
      "title": "实现用户注册接口",
      "depends_on": [],
      "estimated_complexity": "low | medium | high",
      "expected_outputs": [
        {"path": "src/auth/register.py", "type": "code"},
        {"path": "tests/test_register.py", "type": "test"}
      ]
    }
  ],
  "concurrency_plan": {
    "suggested_parallelism": 3,
    "safety_cap": 8
  },
  "glossary": {},
  "quality_gates": {
    "code": ["lint_pass", "test_pass"],
    "report": ["data_verified", "source_cited"]
  }
}
```

---

## 四、Phase 2 — Worker（执行者）

| 属性 | 值 |
|------|-----|
| **类型** | Worker (depth-2) |
| **职责** | 执行单个子任务，产出交付物片段（代码/报告/文档） |

**输入**：
- `execution_plan.json`（获取自己的 task 定义）
- `data/wp.json`（完整 WP 上下文）
- 上游 Worker 输出（如果 `depends_on` 非空）

**权限**：
- ✅ `exec`（运行代码/测试/lint/安装依赖）
- ✅ `write`（交付物目录内）
- ✅ `read`（任何 Blackboard stage）
- ✅ `web_search` / `web_fetch`（技术信息/数据验证）
- ❌ 不能 spawn 子 Agent
- ❌ 不能修改其他 Worker 的输出
- ❌ 不能修改 wp.json / execution_plan

**输出**：`worker_outputs/{task_id}/` + 元数据 JSON

### 4.1 编程场景 Worker 必须动作

| 阶段 | 动作 | 最低次数 | 跳过后果 |
|------|------|---------|---------|
| 启动 | `read` 上游 MANIFEST.json | 每个 dep 1 次 | 接口不兼容 |
| 研究 | `web_search` 技术方案/API 文档 | ≥ 2 次 | 用错误 API |
| 编码 | `write` 代码 + 测试（同步） | ≥ 1 次 | 无产出 |
| 验证 | `exec` 安装依赖 + 运行测试 + lint | ≥ 2 次 | 代码可能不工作 |
| 交付 | `write` MANIFEST.json | 1 次 | 无法追踪 |

### 4.2 报告场景 Worker 必须动作

| 阶段 | 动作 | 最低次数 | 跳过后果 |
|------|------|---------|---------|
| 启动 | `read` 上游 Worker 输出 + glossary | 每个 dep 1 次 | 数据断层 |
| 研究 | `web_search` 行业数据/验证数据点 | ≥ 3 次 | 无数据支撑 |
| 分析 | `write` 分析报告 + data_model | ≥ 1 次 | 无产出 |
| 自检 | 事实性陈述逐条验证 | 全部 | 幻觉风险 |
| 交付 | `write` EVIDENCE.md + MANIFEST | 1 次 | 无法追溯 |

### 4.3 Worker 统一输出结构（4 文件）

```
worker_outputs/{task_id}/
├── DELIVERABLE.md      # 主产物（代码/报告/方案）
├── EVIDENCE.md         # 验证证据（搜索记录/测试输出/数据源）
├── ISSUES.md           # 阻塞/风险/未完成项（没有则写"无"）
└── MANIFEST.json       # 元数据（接口定义 + 自检结果）
```

### 4.4 Worker 失败时的输出规范

Worker 失败（3 轮恢复后仍失败）时，**必须产出以下内容**：

```
worker_outputs/{task_id}/
├── DELIVERABLE.md      # 部分产出（如有）+ 失败说明
├── EVIDENCE.md         # 已执行的尝试记录
├── ISSUES.md           # 必须包含：
│   ├── 失败原因（LLM 诊断结果）
│   ├── 已尝试的恢复策略（每轮做了什么）
│   ├── 未完成的 AC 列表
│   └── 建议的用户行动
└── MANIFEST.json       # status = "FAILED"
```

**关键**：失败的 Worker 不是"什么都没产出"，而是"产出了失败报告"。Integrate 阶段读取 ISSUES.md 获取失败上下文。

### 4.4 Worker 失败时的输出规范

Worker 失败（3 轮恢复后仍失败）时，**必须产出以下内容**：

```
worker_outputs/{task_id}/
├── DELIVERABLE.md      # 部分产出（如有）+ 失败说明
├── EVIDENCE.md         # 已执行的尝试记录
├── ISSUES.md           # 必须包含：
│   ├── 失败原因（LLM 诊断结果）
│   ├── 已尝试的恢复策略（每轮做了什么）
│   ├── 未完成的 AC 列表
│   └── 建议的用户行动
└── MANIFEST.json       # status = "FAILED"
```

**关键**：失败的 Worker 不是"什么都没产出"，而是"产出了失败报告"。Integrate 阶段读取 ISSUES.md 获取失败上下文。

---

## 五、Phase 3 — SmartAssembler（确定性拼接）

| 属性 | 值 |
|------|-----|
| **类型** | Python 确定性管线（零 LLM 调用） |
| **职责** | 组装所有 Worker 输出为统一交付物草稿 |

**设计动机**: LLM 合并导致 84% 信息丢失（264KB → 42KB）。根因是 deliver_integrate.md prompt 指示"合并章节"被 LLM 解读为"摘要"。

**解决方案**: SmartAssembler — 确定性 Python 拼接，零 LLM 调用。

**输入**：
- `execution_plan.json`（任务关系 + 依赖图）
- `worker_outputs/`（所有 Worker 输出，MD-first 格式）
- `data/ship_package.md`（来自 Ship Pro 的 MD source of truth，如有）
- `validation_result`（Loop 修复轮次时）

**SmartAssembler 管线**:
1. 读取所有 Worker 输出目录
2. 拓扑排序（依赖图）
3. Heading 规范化（H2→H3 降级）
4. 正文拼接（保留原始内容，不摘要）
5. TOC 生成
6. Appendix 编译

**权限**：
- ✅ `exec`（编程场景：运行集成测试/lint）
- ✅ `read`（所有 Worker 输出）
- ✅ `write`（`integrated_draft/` 目录）
- ❌ 不能修改 Worker 原始输出
- ❌ 不调用 LLM（确定性拼接）

**输出**：`integrated_draft/`

**不变量**: `len(final_deliverable) >= sum(len(worker.content))`（保留率 ≥100%）

**组装前检查**：
1. 所有 Worker 输出文件存在且格式合规
2. 编程场景：MANIFEST 接口对齐（provides vs requires 匹配）
3. 报告场景：术语一致性（glossary.json 对齐）、数据交叉引用一致

**组装后验证**：
- 编程场景：`exec` 运行集成测试 + 全局 lint
- 报告场景：术语扫描 + 数据一致性检查

**E2E 验证**:
- 报告场景: 11 Worker → 368KB（保留率 139.2%）→ 4.15/5.0
- 编程场景: 19 Python 文件 + 30 pytest passed（保留率 316.5%）→ 4.4/5.0

---

## 六、Phase 4 — Validate Judge（质量裁判）

| 属性 | 值 |
|------|-----|
| **类型** | Worker (depth-2) — **独立视角** |
| **职责** | 质量判定：PASS / FAIL + 定向修复指令 |

**输入**：
- `integrated_draft/`
- `execution_plan.json`（验收标准）
- `data/wp.json`（原始需求）

**权限**：
- ✅ `exec`（编程场景：独立运行测试验证）
- ✅ `web_search`（报告场景：抽样验证数据源）
- ✅ `read`（所有文件）
- ❌ 不能修改任何文件
- ❌ 不能 spawn 子 Agent

**输出**：`validation_result.json`

```json
{
  "verdict": "PASS | FAIL",
  "scores": {
    "completeness": 4,
    "correctness": 4,
    "consistency": 3,
    "credibility": 4,
    "actionability": 4,
    "professionalism": 3
  },
  "weighted_score": 3.8,
  "fix_directives": [
    {
      "target": "T-003",
      "issue": "缺少错误处理",
      "fix_instruction": "在 register() 中添加 try-except"
    }
  ],
  "has_fixable": true,
  "should_continue": true
}
```

**门禁规则**：
- PASS：加权平均 ≥ 3.5 且无维度 < 3
- CONDITIONAL：加权平均 ≥ 3.0 且无维度 < 2 → 修复后复审
- FAIL：加权平均 < 3.0 或任意维度 < 2

**门禁数值 vs LLM 判断冲突解决**：
- 门禁数值是**硬约束**：weighted_score < 3.0 → 必须 FAIL，不可被 LLM 覆盖
- LLM 判断是**软约束**：`should_continue` 可以覆盖门禁的默认行为
- 优先级：数值门禁（硬）> LLM 判断（软）> 轮次上限（硬）
- 特殊情况：CONDITIONAL 自动进入下一轮修复，除非 `should_continue = false`

**Loop 停止判断**（LLM 决定，非硬编码）：
- `should_continue = false` 当：无改进空间 / 修复已无进展 / 成本过高

**信息守恒验证**（Python + LLM 混合验证）：
```
Layer A（确定性，Python 辅助）：
  1. 提取 wp.json 中所有 acceptance_criteria ID
  2. 扫描 integrated_draft 中的 AC Mapping 表
  3. 计算覆盖率：covered / total
  4. 覆盖率 < 80% → 自动 FAIL

Layer B（语义，LLM 判断）：
  1. 检查 AC 是否被"表面覆盖"（提到了但没真正实现）
  2. 检查是否有"隐性需求"未被 AC 覆盖但 WP 暗含
  3. 输出语义层面的覆盖评估
```

---

## 七、Phase 5 — Package Agent（打包者）

| 属性 | 值 |
|------|-----|
| **类型** | Worker (depth-2) |
| **职责** | 最终打包 + 组件级诚实交付 |

**输入**：
- `integrated_draft/`（最终版本）
- `validation_result.json`（质量评估）
- `worker_outputs/`（含 FAILED 的 Worker）

**权限**：
- ✅ `read`（所有文件）
- ✅ `write`（`final_deliverable/`）
- ❌ 不能修改 integrated_draft

**输出**：`final_deliverable/` + `delivery_manifest.json`

**交付逻辑**：
```
全部 PASS → 完整交付 ✅
部分 FAIL + 组件独立 → 交付成功部分 + 失败报告
  失败报告包含：失败原因 + 系统尝试过的策略 + 用户行动选项
部分 FAIL + 核心依赖缺失 → 不交付 + 失败报告 + 行动选项
```

---

## 八、场景差异矩阵

| 维度 | 编程场景 | 报告场景 |
|------|---------|---------|
| **核心质量指标** | 代码能运行 + 测试通过 | 数据有来源 + 结论有论据 |
| **web_search 最低次数** | ≥ 2（技术验证） | ≥ 3（行业数据） |
| **exec 最低次数** | ≥ 2（测试 + lint） | 0（除非数据处理） |
| **EVIDENCE.md 内容** | 测试输出 + lint 结果 | 搜索 query + URL + 结果摘要 |
| **最小内容量** | 代码 ≥ 50 行 + 测试 ≥ 20 行 | 正文 ≥ 800 字 + 证据 ≥ 3 条 |
| **Integrate 验证** | exec 集成测试 + lint | 术语扫描 + 数据一致性 |
| **Validate 验证** | exec 独立运行测试 | web_search 抽样验证数据 |

---

## 九、铁律（不可违反）

| # | 铁律 | 违反后果 |
|---|------|---------|
| 1 | **无证据不交付** — 编程要有测试输出，报告要有数据源 | 产出作废 |
| 2 | **必须动作不可跳过** — 强制动作矩阵中标"必须"的 | 产出打回 |
| 3 | **不完整必须声明** — 未完成的 AC 必须写入 ISSUES.md | 视为隐瞒 |
| 4 | **不修改他人产出** — Worker 只改自己的 | 破坏协作 |
| 5 | **自检是交付前提** — 未自检的产出不得提交 | 退回补充 |
| 6 | **Validate 门禁不可绕过** — 所有产出必须过 Judge | 不可交付 |
| 7 | **诚实优于完美** — 宁可承认不足，不编造数据 | 严重违规 |
| 8 | **生成者 ≠ 验证者** — Integrate 和 Validate 必须独立 | 认知盲区 |

---

## 十、调度经验教训（从 Solution Pro 移植）

> 以下 7 条是 Solution Pro 多轮迭代中用 Bug 换来的知识。Deliver Pro 必须提前规避。

### 10.1 Yield 中断问题

**问题**：`sessions_yield()` 唤醒后，LLM 生成文字而非 tool call → pipeline 中断。

**根因**：OpenClaw 将文字输出视为 turn 结束，不再执行后续 tool call。

**预防**：yield 前在 prompt 中写入 `exec cat {path}` 作为唤醒后第一个动作。或使用 cron wake 替代。

### 10.2 Blackboard 路径嵌套

**问题**：Blackboard 路径嵌套过深（如 `blackboard/{project}/{domain}/stages/worker_outputs/{id}/`），导致 Worker 找不到文件。

**预防**：路径层级 ≤ 4 层，使用相对路径或环境变量。

### 10.3 信息流断裂

**问题**：上游 Agent 的输出未被下游 Agent 读取，数据在阶段间丢失。

**根因**：Agent 间通过 prompt 传递数据，而非文件 Blackboard。

**预防**：所有 Agent 间数据必须走 Blackboard 文件通道（见 02-system-constraints.md）。

### 10.4 JSON 压缩丢信息

**问题**：强制 Agent 输出 JSON schema，导致 65% 的信息保真率丢失。

**根因**：JSON schema 过滤掉了 LLM 的丰富语义输出。

**预防**：Worker 输出使用自由 markdown（DELIVERABLE.md），MANIFEST.json 只记录元数据。

### 10.5 Token 截断

**问题**：大文档（> 4000 tokens）作为 prompt 传入时，被截断。

**预防**：大输出拆分为多个文件，通过 Blackboard 路径引用。

### 10.6 运动员 = 裁判

**问题**：同一 Agent 既生成内容又审查质量 → 认知盲区。

**预防**：Validate Judge 必须独立于 Worker 和 Integrate（铁律 #4 + #8）。

### 10.7 Prompt 内联 vs 独立文件

**问题**：Prompt 内联在 Python 代码中 → 无法版本控制、无法审计。

**预防**：所有 prompt 使用独立 .md 文件，通过 Prompt Registry 加载。

---

## 十一、Prompt 编写规范

### 11.1 Worker Prompt 必须结构

每个 Worker prompt 必须包含以下元素：

| # | 元素 | 说明 | 示例 |
|---|------|------|------|
| 1 | **身份声明** | 角色 + 目标 | "你是 Deliver Pro 的 Worker。你的目标是完成分配的 WorkPackage。" |
| 2 | **静态约束** | 铁律 + 禁止行为 | 从 02-system-constraints.md 注入 |
| 3 | **动态任务** | WP 内容 + AC + 约束 | 从 execution_plan.json 注入 |
| 4 | **输入路径** | 依赖文件路径 | `read workers/T-001/MANIFEST.json` |
| 5 | **输出路径** | 产出文件路径 | `write workers/T-003/DELIVERABLE.md` |
| 6 | **强制动作** | 必须执行的工具调用 | `web_search ≥ 2 次` |
| 7 | **自检清单** | 提交前必须检查 | AC 覆盖 + 证据充分 + 格式合规 |
| 8 | **Preamble** | 环境初始化 | `cd /path/to/workspace && export PYTHONPATH=...` |

### 11.2 Spawn Task 模板

```python
sessions_spawn(
    task=f"""
你是 Deliver Pro Worker。

## 静态约束
{read("02-system-constraints.md")}

## 你的任务
{task_definition_from_execution_plan}

## 输入
- 依赖文件：{dependency_paths}
- WP 上下文：{wp_summary}

## 输出路径
- DELIVERABLE.md → workers/{task_id}/DELIVERABLE.md
- EVIDENCE.md → workers/{task_id}/EVIDENCE.md
- ISSUES.md → workers/{task_id}/ISSUES.md
- MANIFEST.json → workers/{task_id}/MANIFEST.json

## 强制动作
{forced_actions_for_scenario}

## Preamble
cd {workspace} && export PYTHONPATH={lib_path}

## 自检清单
提交前逐条检查：
- [ ] 所有 AC 已覆盖
- [ ] 证据充分（exec/web_search 记录）
- [ ] 格式合规（4 文件齐全）
- [ ] 无 ISSUES 遗漏
""",
    runtime="subagent",
    mode="run"
)
```

### 11.3 Prompt 禁忌

| ❌ 禁止 | ✅ 替代 | 原因 |
|---------|---------|------|
| 硬编码文件路径 | 使用 `{workspace}/workers/{task_id}/` | 路径必须可配置 |
| `import openclaw` | 使用 tool call | openclaw 不是 Python 包 |
| 强制 JSON 输出 | 自由 markdown + MANIFEST.json | 防信息丢失（教训 10.4） |
| 省略 preamble | 必须包含 cd + env | Worker 需要知道工作目录 |
| 省略自检清单 | 必须包含检查项 | 防遗漏 |

---

*文档结束。配合 02-system-constraints.md 和 03-protocols.md 使用。*
