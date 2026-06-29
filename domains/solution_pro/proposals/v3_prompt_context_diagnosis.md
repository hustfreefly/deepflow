# V3 Prompt 上下文膨胀 + 引用系统缺失 + DeepFlow 契约违反诊断

> **版本**: 1.0.0
> **日期**: 2026-06-29
> **作者**: 调查 Subagent
> **状态**: 诊断完成，待修复

---

## 一、V3 vs V1 上下文传递方式对比

### 1.1 V3 方式（v2_planning_module.md — Layer 2 Convergence）

**问题：直接嵌入 expert 输出 JSON 到 prompt**

```
执行流程：
1. exec 读取所有 expert 输出 → 合并为 JSON 字符串
2. sessions_spawn 启动 Convergence Worker
3. task 参数中直接嵌入：
   ```
   ## Expert 输出
   [嵌入所有 expert 输出 JSON]    ← 🔴 上下文膨胀点
   
   ## Frozen Spec
   [嵌入 frozen_spec]             ← 🔴 二次膨胀
   ```
```

**问题量化**：
- 假设 3 个 expert，每个输出 2-3KB JSON
- 加上 frozen_spec (可能 5-10KB)
- **Convergence Worker 的 prompt 总量：15-25KB 纯数据嵌入**
- 再加上 prompt 本身的指令（~3KB），总 prompt 达 18-28KB

**违反的原则**：
- ❌ Worker 应该自己读文件，而不是被喂数据
- ❌ 上下文窗口被大量 JSON 占用，降低 LLM 推理质量
- ❌ 不可扩展（expert 数量增加 → prompt 爆炸）

### 1.2 V1 方式（convergence_planner.md）

**方案：告诉 Worker 文件路径，让它自己读**

```
你的输入

你会收到以下文件：
- `data/frozen_spec.json` — 冻结的需求规格（含 P0 REQ 列表）
- `stages/meta_planning.json` — Meta-Planner 输出（含专家配置）
- `stages/expert_plans/*.json` — 多个 Expert Plan（N 个文件）
```

**优势**：
- ✅ Prompt 轻量（只有指令，没有数据）
- ✅ Worker 按需读取，不浪费上下文
- ✅ 可扩展（expert 数量增加不影响 prompt 大小）
- ✅ 符合 Blackboard 架构（数据在 Blackboard，Worker 自取）

### 1.3 对比表

| 维度 | V3 方式 | V1 方式 |
|------|---------|---------|
| **数据传递** | 嵌入 prompt | 文件路径引用 |
| **Prompt 大小** | 15-28KB（含数据） | ~3KB（纯指令） |
| **上下文利用率** | 低（大量 JSON 占用） | 高（只有指令） |
| **可扩展性** | 差（expert↑ → prompt↑↑） | 好（expert↑ → 读取次数↑） |
| **Blackboard 一致性** | ❌ 绕过 Blackboard | ✅ 通过 Blackboard |
| **Worker 自主性** | 被动接收 | 主动读取 |

---

## 二、DeepFlow 引用系统是什么

### 2.1 V1 的 REQ-ID 引用系统

V1 有一套完整的**需求追溯引用系统**，核心是 REQ-ID：

```
frozen_spec.json
  └── requirements[]
        └── id: "REQ-001", "REQ-002", ... "REQ-P0-001"
              ↓ 贯穿全流程
        planning → reviewer → researcher → consolidator → harness
              ↓
        每个阶段的输出都标注 covered_req_ids
              ↓
        最终可追溯：哪个约束覆盖了哪个需求
```

**核心机制**：

1. **REQ-ID 作为权威标识**
   - frozen_spec.json 是唯一 REQ-ID 来源
   - 每个阶段输出必须包含 `covered_req_ids: ["REQ-001", ...]`
   - 跨阶段传递时，REQ-ID 不断裂

2. **约束 ID 系统（Convergence Planner 输出）**
   ```json
   {
     "constraint_id": "UC-001",
     "description": "所有 API 必须使用 HTTPS",
     "source_experts": ["security_expert"],
     "conflicts_resolved": []
   }
   ```
   - 每条约束有唯一 ID（UC-001, UC-002...）
   - 记录来源 expert（可追溯）
   - 记录冲突解决（可审计）

3. **语义去重（REQ_DEDUP_DESIGN.md）**
   - 同一需求的不同措辞 → 合并为一条，保留最低 REQ-ID
   - `covered_req_ids[]` 保留全部原始 ID（不丢失追溯）
   - 示例：
     ```
     "首月<$50" (REQ-011) + "月固定$6-26" (REQ-013) → 合并为 UC-011
     covered_req_ids: ["REQ-011", "REQ-013", "REQ-016", ...]
     ```

4. **P0 REQ 覆盖验证**
   - Convergence Planner 必须检查所有 P0 REQ 是否被覆盖
   - 未覆盖的 P0 REQ 必须在 `rejected_constraints` 中说明原因
   - Harness Final 用此做需求覆盖度评估

### 2.2 V1 引用系统的输出格式

**unified_constraints.json**：
```json
{
  "schema_version": "1.0.0",
  "unified_constraints": [
    {
      "constraint_id": "UC-001",
      "description": "所有 API 必须使用 HTTPS",
      "priority": "MUST",
      "source_experts": ["security_expert"],
      "conflicts_resolved": []
    }
  ],
  "rejected_constraints": [...],
  "meta": {
    "total_expert_plans": 3,
    "total_input_constraints": 45,
    "total_output_constraints": 30,
    "merge_ratio": 0.67
  },
  "covered_req_ids": ["REQ-P0-001", "REQ-P0-002", "REQ-P0-003"]
}
```

**verification_checklist.json**：
```json
{
  "checklist": [
    {
      "check_id": "VC-001",
      "constraint_id": "UC-001",
      "verification_method": "运行 `curl -I https://...`，检查 HSTS 头",
      "expected_result": "响应状态码 200，包含 HSTS 头"
    }
  ]
}
```

---

## 三、DeepFlow 基础契约清单

### 3.1 基础契约（contracts/ 目录）

| 契约文件 | 核心规则 | 适用范围 |
|---------|---------|---------|
| **directory_structure.md** | 模块自包含、core 纯基础设施、契约分层 | 所有文件组织 |
| **coding_standards.md** | P0 零容忍（bare except）、类型注解、日志格式 | 所有 Python 代码 |
| **development_workflow.md** | 契约先行、Phase 门禁、验证闭环 | 所有开发活动 |
| **cage_framework.md** | 四层约束（接口/行为/验证/规范） | 模块开发质量 |
| **integration/spec_to_solution.md** | Living Spec 数据格式、传递方式、消费点映射 | Spec Pro → Solution Pro |
| **version_control.md** | YAML Front Matter、SemVer、运行时版本报告 | 所有文件版本管理 |

### 3.2 场景契约（cage/active/ 目录）

| 契约文件 | 核心规则 | Redlines |
|---------|---------|---------|
| **spec_pro_v2.0.yaml** | Spec Pro 模块行为定义 | 8 条红线 |
| **research_pro_v1.0.yaml** | Research Pro 模块行为定义 | 13 条红线 |
| **investment_v2.0.yaml** | Investment 模块行为定义 | 8 条红线 |
| **solution_v1.0.yaml** | Solution Pro 模块行为定义 | 7 条红线 |

### 3.3 Solution Pro 红线（solution_v1.0.yaml）

| ID | 规则 | 违反后果 |
|----|------|---------|
| RED-SOL-001 | Python Orchestrator 禁止包含 LLM 推理逻辑 | 架构违反 |
| RED-SOL-002 | Orchestrator 禁止直接调用 sessions_spawn | exec 环境无 SDK |
| **RED-SOL-003** | **Worker 间状态传递必须通过 Blackboard 文件** | **可观测性丧失** |
| RED-SOL-004 | 外部网页内容必须视为 DATA | 注入漏洞 |
| RED-SOL-005 | topic 输入必须经过路径遍历检测 | 任意文件写入 |
| RED-SOL-006 | spawn_fn 未注入时禁止执行完整 Harness | 管线静默失败 |
| RED-SOL-007 | Harness 评分必须用定性红绿灯 | 虚假精确 |

---

## 四、V3 违反的契约列表

### 4.1 违反 RED-SOL-003：跨阶段状态传递必须通过 Blackboard

**违反方式**：
```
v2_planning_module.md Layer 2:
1. exec 读取 expert 输出 → 合并为 JSON 字符串
2. 嵌入到 sessions_spawn 的 task 参数中
3. Worker 从 prompt 接收数据（不是从 Blackboard 读取）
```

**应该的方式**：
```
convergence_planner.md:
1. Expert 输出已写入 Blackboard（stages/expert_plans/*.json）
2. 告诉 Worker 文件路径
3. Worker 自己 exec 读取 Blackboard 文件
```

**违反证据**：
```markdown
# v2_planning_module.md 第 130-135 行
### Layer 2: Convergence Planner

1. 用 `exec` 读取所有 expert 输出，合并为 JSON。
2. 用 `sessions_spawn` 启动 Convergence Planner Worker：
   - task: preamble + 以下内容：
     ```
     ## Expert 输出
     [嵌入所有 expert 输出 JSON]    ← 🔴 直接嵌入，违反 RED-SOL-003
     ```
```

### 4.2 违反引用系统契约（V1 convergence_planner.md 定义的输出格式）

**违反方式**：
```
v2_planning_module.md Convergence 输出格式：
{
  "unified_constraints": {...},
  "conflict_resolutions": [...],
  "covered_req_ids": [...],
  "requirement_evidence": {}
}
```

**V1 定义的输出格式**：
```json
{
  "schema_version": "1.0.0",
  "unified_constraints": [
    {
      "constraint_id": "UC-001",
      "description": "...",
      "priority": "MUST",
      "source_experts": ["..."],
      "conflicts_resolved": []
    }
  ],
  "rejected_constraints": [...],
  "meta": {
    "total_expert_plans": 3,
    "total_input_constraints": 45,
    "total_output_constraints": 30,
    "merge_ratio": 0.67
  },
  "covered_req_ids": ["REQ-P0-001", ...]
}
```

**缺失字段**：
- ❌ `constraint_id`（UC-001 格式）— 无法引用特定约束
- ❌ `source_experts` — 无法追溯来源
- ❌ `priority`（MUST/SHOULD）— 无法区分优先级
- ❌ `rejected_constraints` — 无法记录被拒绝的约束
- ❌ `meta.merge_ratio` — 无法评估合并质量
- ❌ `verification_checklist.json` — 完全缺失

### 4.3 违反开发流程契约（development_workflow.md）

**违反方式**：
- ❌ 未遵循"契约先行"原则（V3 prompt 没有引用场景契约）
- ❌ 未定义 Phase 门禁验证
- ❌ 未定义验证脚本

### 4.4 违反版本控制契约（version_control.md）

**违反方式**：
```markdown
# v2_planning_module.md 文件头
---
id: solution/v2_planning_module_v3
version: "3.0.0"
component: solution
updated: "2026-06-29"
---
```

- ❌ 文件名 `v2_planning_module.md` 与版本 `3.0.0` 不一致
- ❌ 缺少 `status: active` 字段
- ❌ 缺少 `role: planner` 字段

### 4.5 违反集成契约（spec_to_solution.md）

**违反方式**：
- ❌ 未使用 `covered_req_ids` 追溯机制
- ❌ 未实现 P0 REQ 覆盖验证
- ❌ 未生成 `verification_checklist.json`

---

## 五、修复建议

### 5.1 修复上下文膨胀（优先级：P0）

**问题**：Layer 2 Convergence Worker 的 prompt 嵌入大量 JSON 数据

**修复方案**：改为文件路径引用，让 Worker 自己读 Blackboard

**修改 v2_planning_module.md Layer 2 部分**：

```markdown
### Layer 2: Convergence Planner

1. 用 `exec` 确认所有 expert 输出已写入 Blackboard：
   ```bash
   cd /Users/allen/.openclaw/workspace/.deepflow && PYTHONPATH=. python3 -c "
   from core.blackboard.blackboard_manager import BlackboardManager
   bb = BlackboardManager('OpenClaw AI Native Loop Engineering Framework')
   experts = bb.read_stage('stages/expert_plans', default={})
   print('EXPERTS_READY' if experts else 'EXPERTS_MISSING')
   "
   ```

2. 用 `sessions_spawn` 启动 Convergence Planner Worker：
   - runtime: "subagent"
   - mode: "run"
   - label: "planning_convergence_planner"
   - cwd: "/Users/allen/.openclaw/workspace/.deepflow"
   - task: preamble + 以下内容（**不嵌入数据，只告诉路径**）：

```
你是 Convergence Planner。合并所有 Expert Planner 的输出，生成最终规划。

## 你的输入文件（从 Blackboard 读取）

执行以下命令读取数据：
```bash
cd /Users/allen/.openclaw/workspace/.deepflow && PYTHONPATH=. python3 -c "
from core.blackboard.blackboard_manager import BlackboardManager
import json
bb = BlackboardManager('OpenClaw AI Native Loop Engineering Framework')
frozen_spec = bb.read_stage('data/frozen_spec', default={})
meta_planning = bb.read_stage('stages/meta_planning', default={})
expert_plans = bb.read_stage('stages/expert_plans', default={})
print('=== FROZEN_SPEC ===')
print(json.dumps(frozen_spec, ensure_ascii=False, indent=2))
print('=== META_PLANNING ===')
print(json.dumps(meta_planning, ensure_ascii=False, indent=2))
print('=== EXPERT_PLANS ===')
print(json.dumps(expert_plans, ensure_ascii=False, indent=2))
"
```

## 输出格式（JSON，直接输出）

{
  "unified_constraints": [
    {
      "constraint_id": "UC-001",
      "description": "...",
      "priority": "MUST",
      "source_experts": ["..."],
      "conflicts_resolved": []
    }
  ],
  "rejected_constraints": [...],
  "meta": {
    "total_expert_plans": N,
    "total_input_constraints": N,
    "total_output_constraints": N,
    "merge_ratio": 0.XX
  },
  "covered_req_ids": ["REQ-P0-001", ...]
}

## ⚠️ 写回 Blackboard（必须执行）
cd /Users/allen/.openclaw/workspace/.deepflow && PYTHONPATH=. python3 -c "
from core.blackboard.blackboard_manager import BlackboardManager
import json
bb = BlackboardManager('OpenClaw AI Native Loop Engineering Framework')
result = { ... 你的 JSON 输出 ... }
bb.write_stage('stages/planning_convergence', result)
print('CONVERGENCE_WRITTEN')
"
```
```

**修复效果**：
- ✅ Prompt 从 15-28KB 降至 ~3KB
- ✅ Worker 按需读取，上下文利用率高
- ✅ 符合 RED-SOL-003（状态通过 Blackboard 传递）
- ✅ 可扩展（expert 数量增加不影响 prompt 大小）

### 5.2 恢复引用系统（优先级：P0）

**问题**：V3 丢失了 V1 的 REQ-ID 引用系统

**修复方案**：在 Convergence Planner prompt 中明确要求输出格式

**修改点**：
1. 在 Layer 2 Convergence Planner 的 task 中，明确要求输出包含：
   - `constraint_id`（UC-001 格式）
   - `source_experts`（来源追溯）
   - `priority`（MUST/SHOULD/MAY）
   - `conflicts_resolved`（冲突记录）
   - `covered_req_ids`（需求覆盖）
   - `meta`（统计信息）

2. 在 Layer 1 Expert Planner 的 task 中，要求输出包含：
   - `covered_req_ids`（每个约束覆盖的 REQ-ID）
   - `constraint_id`（expert 内部的约束 ID，如 C-001）

**修复效果**：
- ✅ 恢复需求追溯能力
- ✅ 支持语义去重（REQ_DEDUP_DESIGN.md）
- ✅ 支持 P0 REQ 覆盖验证
- ✅ 支持 verification_checklist 生成

### 5.3 补充 verification_checklist（优先级：P1）

**问题**：V3 完全缺失验证清单生成

**修复方案**：在 Convergence Planner 的输出中增加第二个文件

**修改 v2_planning_module.md**：

```markdown
### Layer 2 完成后：验证 verification_checklist

1. 用 `exec` 检查 `stages/planning_convergence` 是否包含 `verification_checklist`：
   ```bash
   cd /Users/allen/.openclaw/workspace/.deepflow && PYTHONPATH=. python3 -c "
   from core.blackboard.blackboard_manager import BlackboardManager
   bb = BlackboardManager('OpenClaw AI Native Loop Engineering Framework')
   conv = bb.read_stage('stages/planning_convergence', default={})
   vc = conv.get('verification_checklist', [])
   print('VC_READY' if vc else 'VC_MISSING')
   "
   ```

2. 如果 VC_MISSING，重新 spawn Convergence Planner 并强调必须生成 verification_checklist。
```

### 5.4 修复版本控制（优先级：P2）

**问题**：文件名与版本号不一致，缺少必要字段

**修复方案**：
1. 重命名文件：`v2_planning_module.md` → `planning_module.md`（去掉 v2 前缀）
2. 更新 YAML Front Matter：
   ```yaml
   ---
   id: solution/planning_module
   version: "3.0.0"
   component: solution
   role: planner
   updated: "2026-06-29"
   status: active
   ---
   ```

### 5.5 修复开发流程（优先级：P2）

**问题**：未遵循"契约先行"原则

**修复方案**：
1. 确认 `cage/active/solution_v1.0.yaml` 是否覆盖 Planning Module 行为
2. 如未覆盖，创建 `cage/active/planning_module_v3.0.yaml`
3. 定义接口、行为、边界条件
4. 创建验证脚本 `tests/contract/test_planning_module.py`

---

## 六、修复优先级总结

| 优先级 | 问题 | 修复工作量 | 影响范围 |
|--------|------|-----------|---------|
| **P0** | 上下文膨胀（嵌入 JSON） | 中（重写 Layer 2 task） | v2_planning_module.md |
| **P0** | 引用系统缺失 | 中（修改 Layer 1 + Layer 2 prompt） | v2_planning_module.md |
| **P1** | verification_checklist 缺失 | 小（增加输出要求） | v2_planning_module.md |
| **P2** | 版本控制违反 | 小（重命名 + 更新 Front Matter） | 文件名 + 头部 |
| **P2** | 开发流程违反 | 大（创建场景契约 + 验证脚本） | cage/active/ + tests/ |

---

## 七、附录：关键文件路径

| 文件 | 路径 | 用途 |
|------|------|------|
| V3 Planning Module | `domains/solution_pro/prompts/v2_planning_module.md` | 当前问题文件 |
| V1 Convergence Planner | `domains/solution_pro/prompts/convergence_planner.md` | 参考实现 |
| V1 REQ 去重设计 | `domains/solution_pro/prompts/REQ_DEDUP_DESIGN.md` | 引用系统设计 |
| DeepFlow 契约系统规范 | `CONTRACTS.md` | 契约定义 |
| Solution Pro 场景契约 | `cage/active/solution_v1.0.yaml` | 红线定义 |
| 集成契约 | `contracts/integration/spec_to_solution.md` | 数据交接规范 |
| 开发流程契约 | `contracts/development_workflow.md` | 开发规范 |
| 版本控制契约 | `contracts/version_control.md` | 版本管理规范 |

---

## 八、自检清单

- [x] V3 上下文传递方式已分析
- [x] V1 上下文传递方式已分析
- [x] 对比表已生成
- [x] DeepFlow 引用系统已描述
- [x] DeepFlow 基础契约清单已列出
- [x] V3 违反的契约已列出（含证据）
- [x] 修复建议已给出（含代码示例）
- [x] 修复优先级已排序

---

*诊断完成。等待修复实施。*
