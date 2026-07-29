# Agent DryRun V4 — Solution Pro 体检指令

> **背景**: ADR-009 MD-first 改造完成后首次体检。验证 MD-first 架构是否正确落地。
> **版本**: Solution Pro V4.0+ (post ADR-009)

---

## 架构主线（先画线）

```
Solution Pro 三模块架构:
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│  Planning   │ →  │  Research   │ →  │   Summary   │
│  Module     │    │   Module    │    │   Module    │
└─────────────┘    └─────────────┘    └─────────────┘
      ↓                   ↓                   ↓
meta_planning      research_experts     summary_*
convergence        research_digest      final_solution.md
                   knowledge_freshness  solution_document.md

跨域交付物 (MD-first):
- frozen_spec.md → Ship Pro 消费
- final_solution.md → 用户/下游消费
- solution_document.md → 用户可读文档

内部中间产物 (仍为 JSON):
- planning_convergence.json
- research_convergence.json
- expert_plans/*.json
- worker_*.json
```

---

## 四 Agent 并行审计任务

### Agent A 🔵 — 代码+约束验证

**检查项**:

1. **ADR-009 MD-first 代码落地**
   - `frozen_living_md.py`: render/parse round-trip 是否完整
   - `solution_living_md.py`: render/parse round-trip 是否完整
   - `blackboard_manager.py`: write_stage/read_stage 是否正确支持 MD
   - 检查: `grep -n "write_stage\|read_stage" core/blackboard/blackboard_manager.py`

2. **Schema 字段对齐**
   - `schemas/schemas.py` 中的字段 vs Prompt 中引用的字段
   - 检查: 字段名是否一致、enum 是否对齐

3. **Pydantic 调用链完整性**
   - 每个 Schema 的 `model_validate()` 是否在生产代码中被调用
   - 检查: `grep -rn "model_validate\|parse_obj" domains/solution_pro/*.py`

4. **字段漂移检测**
   - Schema 字段名 vs Prompt 字段名 vs 代码残留
   - 检查: 旧字段名（如 `frozen_spec.json` 作为主数据源）是否还有残留

5. **约束强制级别**
   - 每个 MUST 约束是否有代码强制（Pydantic/raise ValueError）
   - 统计可信约束占比

**输出格式**:
```
## Agent A 🔵 报告

### 1. MD-first 代码落地
| 检查项 | 状态 | 证据 |
|--------|:----:|------|

### 2. Schema 字段对齐
| 问题 | 分级 | 证据 |
|------|------|------|

### 3. Pydantic 调用链
| Schema | 调用位置 | 状态 |
|--------|---------|:----:|

### 4. 字段漂移
| 旧字段 | 新字段 | 残留位置 | 分级 |
|--------|--------|---------|------|

### 5. 约束强制级别
| 约束 | 强制方式 | 可信度 |
|------|---------|:------:|

### 总结
- BLOCKER: X 项
- 技术债: X 项
- 建议: X 项
```

---

### Agent B ⚫ — 测试+代码扫描

**检查项**:

1. **pytest 套件**
   - 运行: `python3 -m pytest domains/solution_pro/tests/ -v --tb=short`
   - 统计: passed/failed/skipped

2. **防回归测试**
   - 运行: `python3 -m pytest domains/solution_pro/tests/test_adr009_md_first_enforcement.py -v`
   - 验证 MD-first 行为是否正确测试

3. **死代码检测**
   - 扫描所有 `def` 定义
   - 检查调用次数 = 0 的函数
   - 检查: `grep -rn "def " domains/solution_pro/*.py | grep -v test | grep -v __`

4. **残留引用扫描**
   - 检查代码中是否还有 `frozen_spec.json` 作为主数据源的引用
   - 检查: `grep -rn "frozen_spec\.json\|final_solution\.json" domains/solution_pro/*.py | grep -v test | grep -v fallback`

5. **测试覆盖度**
   - frozen_living_md.py 是否有测试
   - solution_living_md.py 是否有测试
   - 跨域消费（Ship Pro 读 MD）是否有测试

**输出格式**:
```
## Agent B ⚫ 报告

### 1. pytest 结果
| 指标 | 数值 |
|------|------|
| passed | X |
| failed | X |
| skipped | X |

### 2. 防回归测试
| 测试 | 状态 |
|------|:----:|

### 3. 死代码
| 函数 | 文件 | 调用次数 | 分级 |
|------|------|---------|------|

### 4. 残留引用
| 位置 | 内容 | 分级 |
|------|------|------|

### 5. 测试覆盖度
| 模块 | 有测试 | 覆盖场景 |
|------|:------:|---------|

### 总结
- BLOCKER: X 项
- 技术债: X 项
```

---

### Agent C 🟡 — Prompt 语义质量

**检查项**:

1. **Prompt 基础设施检测**
   - Prompt 中引用的文件路径是否真实存在
   - Prompt 中引用的 API/函数名是否真实存在
   - 检查: `grep -rn "bb\.read\|bb\.write\|read_stage\|write_stage" domains/solution_pro/prompts/*.md`

2. **Prompt 内部一致性**
   - 文本指令 vs 代码示例是否一致
   - 同一 Prompt 中不同段落是否矛盾

3. **跨 Prompt 重复检测**
   - 多 Prompt 相同内容 >20 行 → 建议提取为引用
   - 检查: 对比主要 Prompt 文件的重复段落

4. **跨 Prompt 规则一致性**
   - 多 Prompt 引用同一规则（如评分标准）是否一致
   - 检查: 对比 reviewer 类 Prompt 的评分规则

5. **MD-first 一致性**
   - 所有 Prompt 是否一致引用 .md 而非 .json（交付物）
   - 检查: `grep -rn "frozen_spec\.json\|final_solution\.json" domains/solution_pro/prompts/*.md | grep -v _archive`

**输出格式**:
```
## Agent C 🟡 报告

### 1. 基础设施检测
| 引用 | 类型 | 存在 | 证据 |
|------|------|:----:|------|

### 2. 内部一致性
| Prompt | 问题 | 分级 |
|--------|------|------|

### 3. 重复检测
| 重复内容 | 涉及 Prompt | 建议 |
|---------|------------|------|

### 4. 规则一致性
| 规则 | 涉及 Prompt | 一致性 |
|------|------------|:------:|

### 5. MD-first 一致性
| Prompt | .json 引用 | 分级 |
|--------|-----------|------|

### 总结
- BLOCKER: X 项
- 技术债: X 项
```

---

### Agent D 🔴 — 契约+系统+分级

**检查项**:

1. **跨 Agent 契约对齐**
   - Planning Module 输出 → Research Module 输入：字段是否对齐
   - Research Module 输出 → Summary Module 输入：字段是否对齐
   - Summary Module 输出 → Ship Pro 输入：MD 格式是否对齐

2. **数据流闭合**
   - 每个阶段的输入是否有明确来源
   - 每个阶段的输出是否有明确消费方
   - 检查: 信息流是否有断裂点

3. **跨域数据流（Solution Pro → Ship Pro）**
   - frozen_spec.md 是否被 Ship Pro 正确消费
   - final_solution.md 是否被 Ship Pro 正确消费
   - 检查: `grep -rn "frozen_spec\|final_solution" domains/ship_pro/*.py | head -10`

4. **系统级检查**
   - Spawn Task 大小检测（§9.1）
   - 状态管理一致性（§9.2）
   - 调度状态生命周期（§9.3）— 如适用

5. **问题分级汇总**
   - 综合 A/B/C 的发现
   - 按 BLOCKER / 技术债 / 建议 分级
   - 给出最终判定（GO / CONDITIONAL / NO_GO）

**输出格式**:
```
## Agent D 🔴 报告

### 1. 跨 Agent 契约对齐
| 上游 | 下游 | 对齐 | 问题 |
|------|------|:----:|------|

### 2. 数据流闭合
| 阶段 | 输入来源 | 输出消费 | 闭合 |
|------|---------|---------|:----:|

### 3. 跨域数据流
| 交付物 | 生产方 | 消费方 | 状态 |
|--------|--------|--------|:----:|

### 4. 系统级检查
| 检查项 | 状态 | 证据 |
|--------|:----:|------|

### 5. 问题分级汇总
| # | 问题 | 来源 | 分级 | 修复方向 |
|---|------|------|------|---------|

### 最终判定
🟢 GO / 🟡 CONDITIONAL / 🔴 NO_GO

理由: ...
```

---

## 执行指令

1. 每个 Agent 独立执行检查，不互相等待
2. 发现问题时记录证据（grep 结果、代码行号、文件路径）
3. 完成后输出结构化报告
4. 主 Agent 综合 4 份报告，给出最终判定

---

## 特别关注（ADR-009 改造后）

1. **MD-first 是否真正落地**：代码、Prompt、测试三者是否一致
2. **跨域数据流是否闭合**：Ship Pro 是否能正确读取 MD
3. **防回归测试是否充分**：17 个测试是否覆盖关键行为
4. **旧 JSON 引用是否清理**：是否有残留的 `.json` 主数据源引用
