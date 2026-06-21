# Ship Pro V2 Quality Gate 设计

> **版本**: V2.0 | **最后更新**: 2026-06-15  
> **架构**: Compiler(确定性) → Reviewer(LLM) → Fixer(LLM) → Harness(LLM)  
> **与 V1 区别**: V2 预扫描已处理 WP 分解合理性和设计-执行一致性，QG 只做 2 项轻量检查

---

## 架构总览

```
主 Agent (SKILL.md)
  ├── Step 1: exec start_ship_pro.py
  │   → ship_package.json (确定性编译)
  │
  ├── Step 2: exec extract_ship_review_data.py
  │   → ship_review_data.json (提取关键数据 + 定量指标预计算)
  │
  ├── Step 3: LLM 质量门禁（闭环）
  │     ├── 3a. spawn Reviewer (fix_round=0) → 2项检查 → ship_review_result.json
  │     ├── 3b. passed? → 跳到 Step 4
  │     ├── 3c. spawn Fixer (fix_round=1) → 修复 → ship_package_fixed.json (原子写入)
  │     ├── 3d. JSON 有效性验证 (python3 -c json.load)
  │     ├── 3e. spawn Harness (fix_round=1) → 验证修复 → ship_harness_result.json
  │     └── 3f. passed? → Step 4 / failed? → 回到 3c (fix_round=2, 最多2轮)
  │                     passed_with_conditions? → Step 4 (降级通过)
  │
  ├── Step 4: 验证输出文件
  └── Step 5: 向用户报告结果
```

---

## fix_round 注入链

| 阶段 | 谁注入 | 注入方式 | 值 |
|------|--------|---------|-----|
| Reviewer | 主 Agent | 替换 prompt 中 `{fix_round}` | 固定 `0` |
| Fixer Round 1 | 主 Agent | 替换 prompt 中 `{fix_round}` | `1` |
| Harness Round 1 | 主 Agent | 替换 prompt 中 `{fix_round}` | `1` |
| Fixer Round 2 | 主 Agent | 替换 prompt 中 `{fix_round}` | `2` |
| Harness Round 2 | 主 Agent | 替换 prompt 中 `{fix_round}` | `2` |

所有输出 JSON 中携带 `round` 字段，便于追溯。

---

## Reviewer 检查项 (V2: 2项)

### Check 1: AC 质量验证

逐条检查每个 WP 的 acceptance_criteria：

**必须标记的问题**：
- 包含空泛表述："功能实现完成"、"满足设计规格"、"集成验证通过"、"文档完成"
- 包含 `[INSUFFICIENT_CONTEXT]` 标记（预扫描信息不足）
- AC 完全没有可验证的条件

**不需要标记的**：
- AC 包含具体的步骤/公式/流程名称 → 合格
- AC 包含具体的模块名和交互关系 → 合格

### Check 2: 依赖合理性验证

**必须标记的问题**：
- 依赖图存在循环（参考 `pre_checks.dependency_cycles`）
- 存在孤立模块（无依赖且不被依赖，且模块数 > 1）
- 预扫描标记为 `is_infrastructure: true` 但无人依赖

**不需要标记的**：
- 依赖数量多但合理（如集成层依赖多个底层模块）
- Phase 分配与依赖方向一致

> ⚠️ V1 的 Check 3（设计-执行一致性）和 Check 4（WP 分解合理性）已由预扫描 + 编译器处理，不再由 Reviewer 检查。

### suggested_fix 格式契约

每个 issue 的 `suggested_fix` 必须为结构化对象：

```json
{
  "action": "replace_text | add_dependency | remove_dependency | add_condition",
  "target_path": "work_packages[WP-001].acceptance_criteria[0]",
  "value": "具体的修复值"
}
```

| Issue type | action | target_path 模式 |
|-----------|--------|-----------------|
| vague_ac | replace_text | work_packages[{id}].acceptance_criteria[{idx}] |
| insufficient_context | add_condition | readiness.ship_specific_conditions |
| cycle | remove_dependency | work_packages[{id}].dependencies |
| orphan | add_dependency | work_packages[{id}].dependencies |
| infrastructure_isolated | add_dependency | work_packages[{dependent_id}].dependencies |

---

## Fixer 修复规则

### 修复指令消费

Fixer 读取 `suggested_fix` 的结构化指令，按 `action` 类型执行：

| action | 操作 |
|--------|------|
| replace_text | 定位 target_path，用 value 替换原文本 |
| add_dependency | 定位 target_path 数组，追加 value |
| remove_dependency | 定位 target_path 数组，删除 value |
| add_condition | 定位 target_path 数组，追加 value |

### Fallback 协议

如果 `suggested_fix` 无法执行（target_path 不存在/action 不识别/value 类型不匹配）：
1. 基于 `issue.type` + `issue.description` 自行制定修复方案
2. 在 `fix_notes` 数组中记录偏离
3. 完全无法修复 → 在 `readiness.ship_specific_conditions` 中标记 `deferred`

### 原子写入

1. 读取 `ship_package.json` 到内存
2. 应用修复
3. 写入 `ship_package_fixed.json`（不覆盖原文件）
4. JSON 有效性验证

### 可修改/不可修改字段

| 字段 | 权限 |
|------|------|
| `meta` | ❌ 不可修改 |
| `readiness.reason` | ❌ 不可修改 |
| `readiness.inherited_conditions` | ❌ 不可修改 |
| `readiness.status` | ✅ 可改为 `ready_with_conditions` |
| `readiness.ship_specific_conditions` | ✅ 可追加 |
| `work_packages[*].acceptance_criteria` | ✅ 可替换 |
| `work_packages[*].dependencies` | ✅ 可增删 |

---

## Harness 验证规则

### Step 1: 问题真实性回检（⛔ 必须先执行）

对每个 issue 检查其在原始数据中是否有证据：

| Issue 类型 | 验证方式 |
|-----------|---------|
| vague_ac | 原始 AC 文本是否确实包含空泛表述 |
| cycle | 依赖图是否确实存在循环 |
| orphan | 该 WP 是否确实无依赖且不被依赖 |
| infrastructure_isolated | 该基础设施模块是否确实无人依赖 |

无证据 → `hallucinated: true`，不计入 remaining_issues。

### Step 2: 逐条验证修复

对比修复前后的文本，确认每个非幻觉 issue 已被有效修复。

### Step 3: 回归检查

仅对 Fixer 修改过的 WP 检查：
- 是否引入新的循环依赖
- 未修复的 WP 是否保持不变
- JSON 结构是否完整有效

### Step 4: Reviewer 输出一致性校验

- `total_issues == len(所有 issues 数组)` → 否则 `unreliable: true`
- `status == passed iff total_issues == 0` → 否则 `unreliable: true`

### Step 5: 整体评估

| 条件 | 判定 |
|------|------|
| 所有非幻觉 issue 已修复，无回归 | `passed` |
| 有 issue 未修复或引入回归，round < 2 | `failed` |
| 有 issue 未修复，round == 2 | `passed_with_conditions` |

### remaining_issues schema

`remaining_issues` 中的每个条目必须包含与 Reviewer issues 相同的字段结构：

```json
{
  "type": "vague_ac",
  "wp_id": "WP-006",
  "description": "AC-0 仍可进一步具体化",
  "suggested_fix": {
    "action": "replace_text",
    "target_path": "work_packages[WP-006].acceptance_criteria[0]",
    "value": "建议替换文本"
  }
}
```

---

## 文件版本管理

| 文件 | 用途 | 生命周期 |
|------|------|---------|
| ship_package.json | 当前版本 | 编译生成 → Harness 通过后被覆盖 |
| ship_package_fixed.json | Fixer 输出 | 每轮生成，验证后覆盖原文件 |
| ship_package.original.json | 原始备份 | Harness 通过后创建 |
| ship_review_data.json | 提取的审查数据 | Step 2 生成 |
| ship_review_result.json | Reviewer 输出 | Step 3a 生成 |
| ship_harness_result.json | Harness 输出 | Step 3e 生成 |

---

## 降级策略

| Agent | 超时 | 降级行为 |
|-------|------|---------|
| Reviewer | 180s | 跳过 QG，标记 `quality_gate: "skipped"` |
| Fixer | 180s | 使用原始 ship_package.json |
| Harness | 120s | 视为 failed |

2 轮修复后仍有遗留 → `passed_with_conditions` 降级通过，不阻塞交付。

---

## 约束

- Fixer 写入 `ship_package_fixed.json`（不直接覆盖原文件）
- Harness 不修改任何文件，只验证
- 最多 2 轮修复循环
- 所有中间产物写入 `blackboard/{session}/` 目录
- `suggested_fix` 必须是结构化对象（action/target_path/value），不接受纯文本
