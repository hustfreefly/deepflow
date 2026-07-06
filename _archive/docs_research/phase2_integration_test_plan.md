# Phase 2 Integration Test Plan — Ship Pro V3

> **版本**: v1.0 | **创建时间**: 2026-06-19
> **状态**: 待执行
> **依赖**: Phase 1 (5 Agent prompt 设计完成)

---

## 1. 测试目标

Phase 2 的核心目标是验证 Ship Pro V3 的 5-Agent 管线在真实输入下的端到端行为。

### 1.1 验证维度

| 维度 | 目标 | 衡量方式 |
|------|------|----------|
| **管线完整性** | 5 个 Agent 全部完成执行 | 每个 Agent 输出合法 JSON |
| **格式兼容性** | Format A/B/C/D 都能处理 | 3 个案例覆盖 Format A + B |
| **质量门槛** | 输出通过 eval_code_checks | L2 checks 5/5 passed |
| **反馈闭环** | Reviewer 能发现问题并驱动修复 | 植入问题 → FAIL → 修复 → PASS |
| **规模适应性** | 1 组件到 12 组件都能处理 | Case 3 (1 组件) vs Case 1 (12 组件) |

### 1.2 非目标

- 不测试 LLM 的推理能力（prompt 质量是 Phase 1 的事）
- 不测试并发执行（Phase 2 是串行管线）
- 不测试失败恢复（Phase 3 考虑）

---

## 2. 测试案例

### 2.1 案例概览

| Case | 名称 | 格式 | 模块数 | 复杂度 | 目的 |
|------|------|------|--------|--------|------|
| 1 | 企业级 AI 智能客服系统 | B | 12 | 高 | 大系统、多层架构 |
| 2 | 智能简历生成系统 | A | 8 | 中 | Format A 嵌套结构 |
| 3 | 单模块 TODO 应用 | A | 1 | 低 | 边界案例（最小输入） |

### 2.2 Case 1: 企业级 AI 智能客服系统

- **输入路径**: `blackboard/设计一个企业级AI智能客服系统_支持多轮_architecture_87d026ce/final_result.json`
- **格式**: Format B（顶层扁平型）
- **架构**: 微服务分层（12 组件）
- **关键验证点**:
  - Architect 能否从 12 个 components 中正确提取所有模块
  - Decomposer 能否合理分组（不应产生 > 8 个 WP）
  - 依赖推导是否合理（数据流 request_flow 包含复杂调用链）

### 2.3 Case 2: 智能简历生成系统

- **输入路径**: `blackboard/智能简历生成系统_architecture_d99f733a/final_result.json`
- **格式**: Format A（final_solution 嵌套型）
- **架构**: 8 组件
- **关键验证点**:
  - Architect 能否正确解析 `final_solution.detailed_solution.architecture.components[]`
  - Specifier 能否为前端组件写出包含具体 UI 交互的 AC
  - 需求覆盖是否完整（covered_req_ids 映射）

### 2.4 Case 3: 单模块 TODO 应用（边界案例）

- **输入路径**: `blackboard/TC09_单模块TODO应用_architecture_simple/final_result.json`
- **格式**: Format A（final_solution 嵌套型）
- **架构**: 1 组件
- **关键验证点**:
  - Decomposer 是否只生成 1 个 WP（不应过度拆分）
  - Reviewer 不应因 WP 数量少而判 FAIL
  - Packager 的 dependency_graph 应为单节点

---

## 3. 每个 Agent 的验证标准

### 3.1 Architect Agent

| 检查项 | 标准 | 验证方式 |
|--------|------|----------|
| 模块召回率 | ≥ 90% | `validate_blueprint()` — 对比输入模块数 vs 输出模块数 |
| blueprint.json 格式 | 合法 JSON，含 modules 字段 | JSON parse + 字段检查 |
| 无编造信息 | 所有模块名在输入中有对应 | 人工抽检 |
| _meta 完整 | 含 prompt_sha, run_id | 字段存在性检查 |

### 3.2 Decomposer Agent

| 检查项 | 标准 | 验证方式 |
|--------|------|----------|
| 模块覆盖率 | ≥ 90% | `validate_wp_structure()` — source_modules 并集覆盖 blueprint modules |
| 无循环依赖 | 依赖图无环 | DFS cycle detection |
| 每个 WP 有 rationale | 100% WP 有非空 rationale | 字段检查 |
| WP 数量合理 | ≤ 2 × 模块数 | 数量对比 |

### 3.3 Specifier Agent

| 检查项 | 标准 | 验证方式 |
|--------|------|----------|
| AC 可验证性 | mean score ≥ 70 | `eval_code_checks.score_all_acs()` |
| 字段完整率 | ≥ 90% | `eval_code_checks.check_field_completeness()` |
| 每个 WP 有 AC | 100% WP 有 ≥ 2 条 AC | 字段检查 |
| WP 数量匹配 | = wp_structure 的 WP 数量 | 数量对比 |

### 3.4 Reviewer Agent

| 检查项 | 标准 | 验证方式 |
|--------|------|----------|
| verdict 合法 | PASS / FAIL / PASS_WITH_CONDITIONS | 枚举检查 |
| PASS 时有 quality_metrics | 字段存在 | 字段检查 |
| FAIL 时有 target_agent | 每个 issue 有 target_agent | 字段检查 |
| 有好案例判断 | Case 1/2 正常输出 → PASS | 人工验证 |

### 3.5 Packager Agent

| 检查项 | 标准 | 验证方式 |
|--------|------|----------|
| Schema 合规 | 通过 ship_package_v3.schema.json | `eval_code_checks.check_schema_compliance()` |
| eval 全通过 | 5/5 checks passed | `eval_code_checks.run_all_checks()` |
| summary.md 存在 | 文件存在且 > 100 bytes | 文件大小检查 |
| work_packages 非空 | ≥ 1 个 WP | 数量检查 |

---

## 4. 反馈闭环测试方案

### 4.1 目标

验证 Reviewer 能检测有问题的 Specifier 输出，并通过反馈驱动修复。

### 4.2 方法

**Step 1**: 准备一个"有缺陷"的 wp_specs.json（人工植入问题）

植入问题清单：
- WP-001 的 AC 全部为 L1 级别（"功能实现完成"、"测试通过"）
- WP-002 缺少 acceptance_criteria 字段
- 依赖图存在循环（WP-001 → WP-002 → WP-001）

**Step 2**: 将缺陷 wp_specs.json 放入 blackboard，运行 Reviewer

**Step 3**: 验证 Reviewer 输出
- verdict 应为 FAIL
- issues 中应包含 `target_agent: "specifier"`
- issues 应指出具体的 AC 质量问题

**Step 4**: 模拟修复
- 将修复后的 wp_specs.json 放入 blackboard
- 重新运行 Reviewer（round=1）

**Step 5**: 验证 Reviewer 第二轮输出
- verdict 应为 PASS
- round 应为 1
- 上轮 issues 不再出现

### 4.3 缺陷样本设计

```json
{
  "work_packages": [
    {
      "id": "WP-001",
      "title": "Bad WP",
      "acceptance_criteria": [
        "功能实现完成",
        "测试通过",
        "满足设计规格"
      ],
      "dependencies": ["WP-002"]
    },
    {
      "id": "WP-002",
      "title": "Missing AC WP",
      "acceptance_criteria": [],
      "dependencies": ["WP-001"]
    }
  ]
}
```

预期 Reviewer 检测到的问题：
1. WP-001 AC 全部 L1（空泛） → mean_score < 70
2. WP-002 AC 为空 → field_completeness 下降
3. WP-001 ↔ WP-002 循环依赖 → dependency_graph.has_cycles = true

---

## 5. 执行流程

### 5.1 Phase 2 执行步骤

```
1. python3 scripts/e2e_test.py prepare-all test_runs/
   → 为 3 个案例生成 run_plan.json

2. 对每个案例，主 Agent 读取 run_plan.json，按 execution_order 调用 sessions_spawn：
   a. spawn architect → 等待完成 → 写入 blueprint.json
   b. spawn decomposer → 等待完成 → 写入 wp_structure.json
   c. spawn specifier → 等待完成 → 写入 wp_specs.json
   d. spawn reviewer → 等待完成 → 写入 review_report.json
   e. 如果 reviewer verdict == FAIL:
      - 将 feedback 传给目标 Agent 修改
      - 重新运行 reviewer (round+1)
   f. spawn packager → 等待完成 → 写入 ship_package.json + summary.md

3. python3 scripts/e2e_test.py validate test_runs/<case>/
   → 生成 validation_report.json

4. python3 scripts/e2e_test.py report test_runs/<case>/
   → 打印人类可读报告
```

### 5.2 反馈闭环执行

```
1. 准备缺陷 wp_specs.json → 放入 blackboard
2. 运行 Reviewer → 验证 FAIL + 正确 target_agent
3. 修复 wp_specs.json → 放入 blackboard
4. 重新运行 Reviewer → 验证 PASS
```

---

## 6. 成功标准

### 6.1 管线完整性

- [ ] 3 个案例全部完成 5-Agent 串行执行
- [ ] 每个 Agent 输出合法 JSON
- [ ] 无 Agent 超时（timeout 内完成）

### 6.2 质量门槛

- [ ] Case 1: Architect 模块召回率 ≥ 90%（12 模块中 ≥ 11 个）
- [ ] Case 2: Architect 模块召回率 ≥ 90%（8 模块中 ≥ 8 个）
- [ ] Case 3: Architect 模块召回率 = 100%（1 模块）
- [ ] 所有案例: Specifier AC 可验证性 ≥ 70
- [ ] 所有案例: Packager eval_code_checks 5/5 passed

### 6.3 反馈闭环

- [ ] Reviewer 对缺陷样本判 FAIL
- [ ] Reviewer 正确识别 target_agent = specifier
- [ ] 修复后 Reviewer 判 PASS
- [ ] 修复轮次 round = 1

### 6.4 边界案例

- [ ] Case 3 (1 组件) 不崩溃
- [ ] Case 3 的 Decomposer 生成 1 个 WP
- [ ] Case 3 的 dependency_graph 为单节点无环

---

## 7. 工具清单

| 工具 | 路径 | 用途 |
|------|------|------|
| e2e_test.py | `scripts/e2e_test.py` | 环境准备 + 输出验证 |
| eval_code_checks.py | `eval/eval_code_checks.py` | L2 代码级检查 |
| orchestrator.py | `scripts/orchestrator.py` | 参考实现（e2e_test.py 独立于它） |
| Agent prompts | `prompts/*.md` | 5 个 Agent 的 system prompt |

---

## 8. 风险与缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| LLM 输出不稳定 | 同一输入多次运行结果不同 | 每个案例跑 2 次，取较好结果 |
| AC 可验证性波动 | L3 评分可能因措辞差异大 | 阈值设为 70（低于 Phase 1 的 80） |
| 超时 | 大案例可能超过 300s | 设置 600s 超时，记录实际耗时 |
| 格式解析失败 | Format B-tech 变体可能识别错误 | Architect prompt 已包含 B-tech 说明 |

---

*下一步: 主 Agent 读取 run_plan.json，按 execution_order 执行 5-Agent 管线。*
