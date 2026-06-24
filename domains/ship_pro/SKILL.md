# Ship Pro V3 - Agent 执行指南

> **版本**: V3.2 | **最后更新**: 2026-06-23  
> **架构**: Pydantic 契约笼子 → LLM Agent → 质量门禁  
> **核心理念**: Pydantic 模型 = 唯一真相源，改一处三处自动对齐  
> **执行引擎**: `run_pipeline.py` CLI（唯一入口）

---

## 📋 环境要求

| 环境 | 要求 |
|------|------|
| **操作系统** | macOS / Linux / Windows WSL |
| **Python** | 3.8+ |
| **工作目录** | `~/.openclaw/workspace/.deepflow/` 必须存在 |

---

## 触发模式

### 自动触发（默认）
Solution Pro 管线完成时，`completion_handler.py` 会自动编译 Ship Package。

### 手动触发
以下情况需要手动执行：
- 自动编译失败，需要重试
- Frozen Blueprint 被手动修改后需要重新编译

## SESSION_ID 获取方式

`SESSION_ID` 是 blackboard 目录名。获取方式：
1. **Solution Pro 完成输出**：Solution Pro 执行完毕时会打印 `SESSION_ID`
2. **blackboard 目录**：`ls ~/.openclaw/workspace/.deepflow/blackboard/` 下的目录名
3. **blueprint meta 字段**：`frozen_blueprint.json` 中 `meta.session_id` 字段

---

## 🚀 主 Agent 执行流程（V3 — 唯一入口）

> **铁律**: 主 Agent 只能通过 `run_pipeline.py` CLI 驱动管线，禁止手动 spawn。

### CLI 命令一览

```bash
# 1. 准备管线
PYTHONPATH=. python3 scripts/run_pipeline.py prepare <input_path> <output_dir>

# 2. 获取某个 Agent 的任务 prompt
PYTHONPATH=. python3 scripts/run_pipeline.py task <agent_name> <output_dir>

# 3. 运行质量门禁
PYTHONPATH=. python3 scripts/run_pipeline.py gate <agent_name> <output_dir>

# 4. 更新状态（每个 Agent 完成后必须调用）
PYTHONPATH=. python3 scripts/run_pipeline.py update-status <output_dir> <agent_name> <PASS|CONDITIONAL|FAIL> [feedback]

# 5. 查看管线状态
PYTHONPATH=. python3 scripts/run_pipeline.py status <output_dir>

# 6. 最终验证
PYTHONPATH=. python3 scripts/run_pipeline.py validate <output_dir>
```

### 执行顺序

```
prepare → [architect: task→spawn→gate→update-status]
        → [decomposer: task→spawn→gate→update-status]
        → [specifier: task→spawn→gate→update-status]
        → [reviewer: task→spawn→gate→update-status]  (无 code gate，自动 PASS)
        → [packager: task→spawn→gate→update-status]
        → validate
```

### 状态文件

管线状态统一由 `run_pipeline.py` 管理，写入 `pipeline_status.json`。
主 Agent **禁止直接写状态文件**，必须通过 `update-status` CLI 命令。

### 契约笼子

输出格式由 Pydantic 模型定义（`contracts/` 目录），Gate 使用 Pydantic 验证。
CI 检查: `PYTHONPATH=. python3 -m domains.ship_pro.contracts.generator --check`

---

<details>
<summary>📦 V2 三段式（已废弃，保留参考）</summary>

### 架构总览

```
Phase 1: LLM 预扫描
  Blueprint → LLM Pre-Scanner → domain_config.json (~30s)

Phase 2: 确定性编译
  Blueprint + domain_config.json → Compiler → Ship Package (~1s)

Phase 3: LLM 质量门禁
  Ship Package → Reviewer → Fixer → Harness (最多2轮, ~30s)
```

---

### Step 0: 检查 Frozen Blueprint

```python
import json, os, sys

fb_path = os.path.expanduser(f"~/.openclaw/workspace/.deepflow/blackboard/{SESSION_ID}/frozen_blueprint.json")

if not os.path.exists(fb_path):
    print("❌ Frozen Blueprint 不存在，请先运行 Solution Pro")
    sys.exit(1)

with open(fb_path, 'r') as f:
    fb = json.load(f)

readiness = fb.get('readiness', {})
status = readiness.get('status', 'unknown')

if status == 'blocked':
    print(f"❌ Frozen Blueprint 被 blocked:")
    for issue in readiness.get('blocking_issues', []):
        print(f"  - {issue}")
    sys.exit(1)
else:
    print(f"✅ Frozen Blueprint 状态: {status}")
```

---

### Step 1: 提取模块 ID

```bash
cd "$HOME/.openclaw/workspace/.deepflow" && PYTHONPATH=. python3 scripts/extract_module_ids.py \
  --session-id "{SESSION_ID}"
```

输出: stdout 打印逗号分隔的模块 ID 列表（如 `COMP-01, COMP-02, COMP-03`）。

**用途**: 将模块 ID 列表替换到 Pre-Scanner prompt 的 `{valid_module_ids}` 占位符中。

---

### Step 2: LLM 预扫描（Phase 1）

> **目标**: LLM 阅读 Blueprint，提取结构化领域知识供编译器消费。

#### 2a. Spawn Pre-Scanner sub-agent

读取 `domains/ship_pro/prompts/ship_pre_scanner.md` 模板，替换：
- `{base_path}` → 实际 blackboard 路径
- `{valid_module_ids}` → Step 1 提取的模块 ID 列表

```
sessions_spawn(
  runtime="subagent",
  mode="run",
  label="ship_pre_scanner",
  task=<ship_pre_scanner.md 内容，占位符已替换>
)
sessions_yield()
```

Pre-Scanner 输出: `blackboard/{SESSION_ID}/domain_config.json`

#### 2b. 验证 Pre-Scanner 输出

```bash
cd "$HOME/.openclaw/workspace/.deepflow" && PYTHONPATH=. python3 scripts/validate_domain_config.py \
  --session-id "{SESSION_ID}"
```

输出: JSON 格式 `{"valid": true/false, "errors": [...], "warnings": [...]}`

#### 2c. 3 级降级策略

```
Level 1: 重试（最多 1 次）
  └── 验证失败 → 将 errors 反馈给 LLM → 重新 spawn Pre-Scanner
Level 2: 简化版预扫描
  └── Level 1 仍失败 → 使用简化 prompt（仅生成 AC + 依赖，跳过 constraints/risks）
Level 3: 回退 V1 模式匹配
  └── Level 2 仍失败 → 跳过预扫描，编译器使用 domain_config=None
      → ship_package.json 中标记 "engine": "ship_pro_v1_fallback"
      → 向用户报告："V2 预扫描失败，已回退到 V1 模式匹配"
```

**超时降级**: Pre-Scanner 超时 → 直接进入 Level 3。

---

### Step 3: 编译 Ship Package（Phase 2）

```bash
cd "$HOME/.openclaw/workspace/.deepflow" && PYTHONPATH=. python3 scripts/start_ship_pro.py \
  --session-id "{SESSION_ID}" \
  --domain-config "{base_path}/domain_config.json"
```

- 如果 `domain_config.json` 存在且有效 → V2 数据驱动编译
- 如果 `domain_config.json` 不存在 → V1 模式匹配回退

**进度推送**: "编译 Ship Package..."

---

### Step 4: 提取审查数据

```bash
cd "$HOME/.openclaw/workspace/.deepflow" && PYTHONPATH=. python3 scripts/extract_ship_review_data.py \
  --session-id "{SESSION_ID}"
```

输出: `blackboard/{SESSION_ID}/ship_review_data.json`

---

### Step 5: LLM 质量门禁（Phase 3，闭环）

> **V2 简化**: 从 4 项检查减到 2 项（AC 质量 + 依赖合理性）。
> 预扫描已处理 WP 分解合理性和设计-执行一致性。

#### 5a. Spawn Reviewer sub-agent

读取 `domains/ship_pro/prompts/ship_reviewer.md` 模板，替换 `{base_path}` 和 `{fix_round}` 为 `0`：

```
sessions_spawn(
  runtime="subagent",
  mode="run",
  label="ship_reviewer",
  task=<ship_reviewer.md 内容，占位符已替换>
)
sessions_yield()
```

Reviewer 输出: `blackboard/{SESSION_ID}/ship_review_result.json`

**超时降级**: Reviewer 超时 → 跳过 QG，标记 `"quality_gate": "skipped"`，继续 Step 6。

#### 5b. 判断是否需要修复

```bash
python3 scripts/ship_qg_orchestrator.py --action check_review \
  --result-path "{base_path}/ship_review_result.json"
```

- `action == "pass"` → 跳到 Step 6
- `action == "fix"` → 继续 5c
- `action == "skip"` → 跳到 Step 6

#### 5c. Spawn Fixer sub-agent（最多 2 轮）

设置 `fix_round`（首轮=1，第二轮=2）：

```
sessions_spawn(
  runtime="subagent",
  mode="run",
  label="ship_fixer",
  task=<ship_fixer.md 内容，占位符已替换>
)
sessions_yield()
```

**超时降级**: Fixer 超时 → 使用原始 ship_package.json，继续 Step 6。

Fixer 写入 `ship_package_fixed.json`（不直接覆盖原文件）。

#### 5d. JSON 有效性验证

```bash
python3 -c "import json; json.load(open('{base_path}/ship_package_fixed.json'))" 2>&1
```
- 通过 → 继续 5e
- 失败 → 回到 5c（round < 2 时）或跳过（round >= 2 时）

#### 5e. Spawn Harness sub-agent

```
sessions_spawn(
  runtime="subagent",
  mode="run",
  label="ship_harness",
  task=<ship_harness.md 内容，占位符已替换>
)
sessions_yield()
```

Harness 输出: `blackboard/{SESSION_ID}/ship_harness_result.json`

#### 5f. 判断是否需要再修一轮

```bash
python3 scripts/ship_qg_orchestrator.py --action check_harness \
  --result-path "{base_path}/ship_harness_result.json" --round {current_round}
```

- `action == "pass"` → 备份原文件 + 覆盖 → Step 6
- `action == "done"` → 备份 + 覆盖 + 标记 `ready_with_conditions` → Step 6
- `action == "retry"` → 回到 5c（`fix_round` + 1）

**文件版本管理**：
```bash
cp {base_path}/ship_package.json {base_path}/ship_package.original.json
cp {base_path}/ship_package_fixed.json {base_path}/ship_package.json
```

**进度推送**: "LLM 质量门禁: Round {N}..."

---

### Step 6: 验证输出

```python
import json, os, sys

base_path = os.path.expanduser(f"~/.openclaw/workspace/.deepflow/blackboard/{SESSION_ID}")
sp_json = f"{base_path}/ship_package.json"

if not os.path.exists(sp_json):
    print("❌ ship_package.json 未生成")
    sys.exit(1)

with open(sp_json, 'r') as f:
    sp = json.load(f)

required_fields = ['meta', 'readiness', 'work_packages', 'acceptance_contract', 'risk_contract', 'harmony_brief']
missing = [f for f in required_fields if f not in sp]

if missing:
    print(f"❌ 缺少必填字段: {missing}")
    sys.exit(1)

print(f"✅ Ship Package 验证通过")
print(f"  - 状态: {sp['readiness']['status']}")
print(f"  - Work Packages: {len(sp['work_packages'])}")
print(f"  - Acceptance Contract: {len(sp['acceptance_contract'])}")
```

---

### Step 7: 向用户报告

```
✅ Ship Pro V2 编译完成
📋 项目: {SESSION_ID}
📊 状态: {readiness.status}
📦 Work Packages: {N}
📋 Acceptance Criteria: {N}
⚠️ Risk Register: {N}
🧠 预扫描: {成功 | 降级(Level N) | 回退V1}
🔍 质量门禁: {passed | passed_with_conditions (N issues fixed) | skipped}

输出文件:
- ship_package.json
- ship_package.md
- domain_config.json (预扫描输出)
- ship_review_result.json (Reviewer 输出)
- ship_harness_result.json (Harness 输出，如有修复)
```

---

## 🔍 Watcher 巡检（必须伴随启动）

> 🔴 **铁律**: 启动 Ship Pro 管线时，**必须同步创建 Watcher Cron**。
> 必须从 `start_ship_pro.py --print-watcher-prompt` 输出的 `watcher_wrapper_prompt_prefilled` 字段获取 prompt，原样用于 cron payload.message。禁止手动编写 prompt。

**流程**:
1. 运行 `start_ship_pro.py --print-watcher-prompt`
2. spawn orchestrator
3. 创建 Watcher Cron（直接用 `watcher_wrapper_prompt_prefilled`，无需回填 cron_job_id）
4. yield

**禁止**: 启动管线但不创建 Watcher = 违规

---

## 🔄 状态流转

```
ready_for_ship      → Ship Pro 编译 → ready_to_ship
ready_with_conditions → Ship Pro 编译 → ready_with_conditions
needs_clarification  → Ship Pro 编译 → needs_clarification
blocked             → Ship Pro 编译 → blocked（0 WP）
```

---

## 🛡️ 错误处理与降级策略

### 预扫描失败（3 级降级）

| Level | 触发条件 | 行为 | 标记 |
|-------|---------|------|------|
| 1 | 验证失败 | 重试 1 次（带错误反馈） | — |
| 2 | Level 1 仍失败 | 简化版预扫描 | `pre_scan: "simplified"` |
| 3 | Level 2 仍失败 | 回退 V1 模式匹配 | `engine: "ship_pro_v1_fallback"` |

### QG sub-agent 超时

| Agent | 超时时间 | 降级行为 |
|-------|---------|---------|
| Pre-Scanner | 180s | 直接进入 Level 3 |
| Reviewer | 180s | 跳过 QG，标记 `quality_gate: "skipped"` |
| Fixer | 180s | 使用原始 ship_package.json |
| Harness | 120s | 视为 failed |

### Frozen Blueprint 不存在
```
Solution: 先运行 Solution Pro 生成 Frozen Blueprint
```

### Frozen Blueprint 被 blocked
```
Solution: 检查 blocking_issues，修复后重新编译
```

---

## 🏗️ V2 架构总览

```
主 Agent
  ├── Step 0: 检查 Frozen Blueprint
  │
  ├── Phase 1: LLM 预扫描
  │   ├── Step 1: extract_module_ids.py → 模块 ID 列表
  │   ├── Step 2a: spawn Pre-Scanner → domain_config.json
  │   ├── Step 2b: validate_domain_config.py → 语义校验
  │   └── Step 2c: 降级策略（重试 → 简化 → 回退 V1）
  │
  ├── Phase 2: 确定性编译
  │   ├── Step 3: start_ship_pro.py → ship_package.json
  │   └── Step 4: extract_ship_review_data.py → ship_review_data.json
  │
  ├── Phase 3: LLM 质量门禁（2 项检查 + 闭环）
  │   ├── Step 5a: spawn Reviewer → ship_review_result.json
  │   ├── Step 5b: check_review → pass? fix? skip?
  │   ├── Step 5c: spawn Fixer → ship_package_fixed.json
  │   ├── Step 5d: JSON 有效性验证
  │   ├── Step 5e: spawn Harness → ship_harness_result.json
  │   └── Step 5f: check_harness → pass? retry? done?
  │
  ├── Step 6: 验证输出文件
  └── Step 7: 向用户报告结果

数据驱动编译器 (Phase 2)
  ├── 读取 domain_config.json（LLM 预扫描输出）
  ├── _decompose_work_packages(bp, domain_config) → 数据映射
  ├── AC / Deliverables / Constraints → 全部来自 domain_config profiles
  ├── Dependencies → domain_config.dependency_hints + 模块级声明
  └── 零硬编码：所有领域知识来自 LLM 预扫描

LLM 质量门禁 (Phase 3, V2 简化版)
  ├── Reviewer: AC 质量检查 + 依赖合理性检查（2 项）
  ├── Fixer: 根据 Reviewer issues 修复 ship_package.json
  └── Harness: 验证修复有效 + 防幻觉回检
```

</details>

---

## ⛔ 禁止

- ❌ 直接写 `pipeline_status.json`（必须用 `update-status` CLI）
- ❌ 手动 spawn Agent（必须用 `task` + `gate` CLI）
- ❌ 修改 Pydantic 模型不同步更新 Schema（必须跑 `generator --check`）
- ❌ 调用已废弃的 `orchestrator.py`
- ❌ 输出到非 blackboard 目录

---

## 🎯 记忆锚点

> "Pydantic 是笼子，LLM 输出必须过笼子"
> "run_pipeline.py 是唯一入口，禁止手动 spawn"
> "改一处 Pydantic → Schema/Gate/Prompt 自动对齐"
> "update-status 是状态更新的唯一方式"

---

## 📖 参考文档

- **契约模型**: `domains/ship_pro/contracts/` (Pydantic 真相源)
- **Schema**: `domains/ship_pro/schemas/ship_package_v3.schema.json`
- **Gate 代码**: `domains/ship_pro/eval/gates.py` (使用 Pydantic 验证)
- **V2 设计文档**(废弃): `domains/ship_pro/docs/ship_pro_v2_design.md`

*V3.2 | 2026-06-23 | Pydantic 契约笼子 + 单一执行引擎*
