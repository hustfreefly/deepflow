# Ship Pro V4.0 — Generator + Judge 两阶段闭环架构设计

> 版本: 4.0.0-draft | 日期: 2026-06-26 | 状态: 设计阶段

---

## 1. 问题陈述：V3.1 的 6-Agent 线性管线

### 1.1 现状架构

V3.1 采用 6 个 Agent 的线性管线：

```
Architect → Decomposer → Specifier → Packager → Reviewer → (循环回 Architect)
```

### 1.2 核心问题

| # | 问题 | 影响 |
|---|------|------|
| P1 | **信息逐级衰减** | Architect 的架构意图经过 4 次传递后，到 Packager 时已严重失真 |
| P2 | **职责碎片化** | Decomposer/Specifier/Packager 本质上都在做"细化"，却拆成 3 个 Agent |
| P3 | **循环成本高** | 一轮循环需要 5 次 LLM 调用，3 轮循环 = 15 次调用 |
| P4 | **收敛不可控** | Reviewer 发现问题后回退到 Architect，但 Architect 不一定能修复 Specifier 层面的问题 |
| P5 | **AC 质量无保障** | Acceptance Criteria 在 Specifier 生成，但 Reviewer 最后才检查，修复代价极高 |
| P6 | **回归无检测** | 第 N 轮修复可能引入第 N-1 轮已修复问题的回退，系统无感知 |

### 1.3 根因分析

**线性管线的本质缺陷**：每个 Agent 只能看到上游的输出，无法直接访问源头信息。当末端 Agent 发现问题时，修复信号需要逆着整条管线传播，每经过一个节点就衰减一次。

---

## 2. V4.0 架构：Generator + Judge 两阶段闭环

### 2.1 核心思路

将 6 个 Agent 压缩为 **2 个角色**：

- **Generator**：合并 Architect + Decomposer + Specifier + Packager 的全部职责，一次性输出完整的架构蓝图 + WP 规格 + 打包信息
- **Judge**：替代 Reviewer，增强 AC 质量检查、回归检测、fixable 标记

### 2.2 架构图

```
┌─────────────────────────────────────────────────────────────┐
│                      Ship Pro V4.0                          │
│                                                             │
│  ┌───────────┐    GeneratorOutput    ┌──────────────────┐  │
│  │           │ ───────────────────▶ │                  │  │
│  │ Generator │                      │      Judge       │  │
│  │           │ ◀─────────────────── │                  │  │
│  └───────────┘    FixContext        └──────────────────┘  │
│        ▲                                   │               │
│        │         fixable risks             │               │
│        └───────────────────────────────────┘               │
│                                                             │
│  闭环条件: verdict == "pass" || round >= max_rounds(3)      │
└─────────────────────────────────────────────────────────────┘
```

### 2.3 信息流

```
Round 1:
  Input → Generator → GeneratorOutput → Judge → {verdict, risks, ac_quality}
  
Round 2 (if verdict != "pass" and has fixable risks):
  GeneratorOutput + FixContext → Generator → GeneratorOutput' → Judge → ...
  
Round 3 (final, if still not passed):
  GeneratorOutput'' + FixContext' → Generator → GeneratorOutput'' → Judge → final verdict
```

---

## 3. V3.1 vs V4.0 对比

| 维度 | V3.1 (6-Agent 线性) | V4.0 (2-Agent 闭环) |
|------|---------------------|---------------------|
| Agent 数量 | 6 (Architect, Decomposer, Specifier, Packager, Reviewer, +循环) | 2 (Generator, Judge) |
| 单轮 LLM 调用 | 5 次 | 2 次 |
| 3 轮循环总调用 | 15 次 | 6 次 |
| 信息保真度 | 低（逐级衰减） | 高（Generator 直出全量） |
| 修复精度 | 粗（回退到 Architect 重做） | 精（FixContext 定向修复） |
| AC 质量保障 | 末端检查，修复代价高 | Judge 首轮即检查，Fixer 定向修复 |
| 回归检测 | 无 | 有（Judge 第 2+ 轮检查回退） |
| 收敛保障 | 隐式（依赖 Reviewer 判断） | 显式（fixable 标记 + max_rounds + 回归检测） |
| 契约复杂度 | 5 个独立契约 + 传递 | 2 个契约（GeneratorOutput, JudgeOutput）+ FixContext |

---

## 4. 信息流图

### 4.1 Generator 输入/输出

**输入**:
- 用户需求（原始文本/PRD/URL）
- FixContext（第 2+ 轮时，包含上轮 Judge 的修复指令）

**输出** (`GeneratorOutput`):
```
GeneratorOutput
├── _meta: ArchitectMeta           # 元数据（复用现有）
├── project_type: str              # 项目分类
├── project: Project               # 项目信息
├── modules: list[Module]          # 架构蓝图（from Architect）
├── dependencies: list[Dependency] # 模块依赖
├── architecture_principles        # 架构原则（from Architect）
├── platform_capabilities          # 平台能力（from Architect）
├── principle_coverage             # 原则覆盖（from Architect）
├── platform_reuse_map             # 平台复用（from Architect）
├── domain_details                 # 领域深度（from Architect）
├── sla_constraints                # SLA 约束（from Architect）
├── requirements                   # 需求列表（from Architect）
├── risks                          # 风险列表（from Architect）
├── implementation_hints           # 实施建议（from Architect）
├── work_packages: list[WorkPackageSpec]  # WP 包（from Decomposer+Specifier）
├── dependency_graph               # 依赖图（from Decomposer）
├── api_conventions                # API 约定（from Packager）
├── integration_tests              # 集成测试（from Packager）
├── error_handling_principles      # 错误处理（from Packager）
└── self_check                     # 自检结果
```

### 4.2 Judge 输入/输出

**输入**:
- GeneratorOutput（Generator 的输出）
- 原始需求（用于交叉验证）

**输出** (`JudgeOutput`):
```
JudgeOutput
├── _meta: JudgeMeta               # 元数据（含 round）
├── verdict: pass|fail|conditional # 裁定
├── risks: list[JudgeRisk]         # 风险列表（含 fixable 标记）
├── ac_quality: dict               # AC 质量评分
├── regressions: list[dict]        # 回归检测（第 2+ 轮）
├── consumability_score: float     # 可消费性评分
├── consumability_details          # 评分细节
└── summary: str                   # 总结
```

### 4.3 FixContext 传递

当 `verdict != "pass"` 时，Judge 输出转换为 `FixContext` 传递给 Generator：

```
FixContext
├── original_verdict: fail|conditional
├── current_round: int             # 当前轮次（1-3）
├── max_rounds: int                # 最大轮次（3）
├── instructions: list[FixInstruction]  # 修复指令
├── history: list[FixRoundResult]  # 历史修复记录
├── focus_areas: list[str]         # 本轮聚焦领域
└── regression_warnings: list[str] # 回归警告（上轮修复回退的问题）
```

---

## 5. 闭环机制

### 5.1 Judge → Generator → Judge 循环

```python
def run_v4_pipeline(input_data, max_rounds=3):
    fix_context = None
    generator_output = None
    
    for round in range(1, max_rounds + 1):
        # Phase 1: Generator 生成/修复
        generator_output = generator.generate(input_data, fix_context)
        
        # Phase 2: Judge 评审
        judge_output = judge.evaluate(generator_output, original_input=input_data)
        
        # 提前退出：通过
        if judge_output.verdict == "pass":
            return generator_output, judge_output
        
        # 检查是否有可修复的风险
        fixable_risks = [r for r in judge_output.risks if r.fixable]
        if not fixable_risks:
            # 所有风险都不可修复，提前退出
            return generator_output, judge_output
        
        # 构造 FixContext 进入下一轮
        fix_context = build_fix_context(judge_output, round=round)
    
    # 达到最大轮次，返回最后结果
    return generator_output, judge_output
```

### 5.2 轮次控制

| 轮次 | Generator 行为 | Judge 行为 |
|------|---------------|-----------|
| Round 1 | 从零生成完整输出 | 全量评审（AC质量 + 可消费性 + 风险） |
| Round 2 | 基于 FixContext 定向修复 | 全量评审 + **回归检测**（检查 R1 修复是否回退） |
| Round 3 | 最终修复（最后机会） | 全量评审 + 回归检测 + **收敛判定** |

### 5.3 fixable 标记

Judge 对每个 risk 标注 `fixable: bool`：

- `fixable=True`：Generator 可以在下一轮修复（如：AC 不够具体、缺少测试用例、依赖图有环）
- `fixable=False`：Generator 无法修复（如：需求本身有矛盾、技术选型根本不可行）

当所有未解决风险都是 `fixable=False` 时，循环提前退出（继续循环无意义）。

---

## 6. 收敛保障

### 6.1 回归检查（第 2+ 轮）

Judge 在 Round 2+ 执行回归检测：

```python
def detect_regressions(current_judge_output, previous_judge_output):
    """检查上轮已修复的风险是否在本轮重新出现"""
    regressions = []
    
    prev_fixed = {r.id for r in previous_judge_output.risks if r.severity in ("critical", "major")}
    curr_risks = {r.id: r for r in current_judge_output.risks}
    
    for risk_id in prev_fixed:
        if risk_id in curr_risks:
            regressions.append({
                "risk_id": risk_id,
                "description": f"Risk {risk_id} was fixed but has regressed",
                "was_fixed_in_round": previous_judge_output._meta.round,
                "regressed_in_round": current_judge_output._meta.round,
            })
    
    return regressions
```

回归检测确保修复过程不会"拆东墙补西墙"。

### 6.2 提前退出条件

循环在以下情况提前退出：

| 条件 | 退出原因 | 最终 verdict |
|------|---------|-------------|
| `verdict == "pass"` | 通过 | pass |
| 所有风险 `fixable=False` | 无法继续修复 | fail/conditional |
| `round >= max_rounds` | 达到最大轮次 | 最后一轮的 verdict |
| 连续 2 轮风险集合完全相同 | 收敛停滞 | fail |

### 6.3 FixContext 约束

FixContext 通过 `focus_areas` 和 `regression_warnings` 约束 Generator 行为：

- `focus_areas`：本轮只修复 instructions 中列出的问题，不要引入新功能
- `regression_warnings`：上轮修复后回退的问题，本轮**必须避免**

这确保 Generator 在修复模式下保持**最小变更原则**，降低引入新问题的风险。

### 6.4 收敛证明（非形式化）

- **有限状态空间**：GeneratorOutput 的字段是有限集合，每个字段的改进方向是确定的
- **单调递减风险**：每轮至少修复 1 个 fixable 风险（否则提前退出）
- **无回归**：回归检测确保已修复风险不重复出现
- **有界轮次**：max_rounds=3 保证终止

因此，系统保证在 ≤3 轮内终止，且每轮都有明确的改进目标。

---

## 附录 A: 契约文件清单

| 契约文件 | 角色 | 说明 |
|---------|------|------|
| `contracts/ship_generator.py` | Generator | 合并 architect+decomposer+specifier+packager |
| `contracts/judge_v4.py` | Judge | 增强 AC质量 + 回归检测 + fixable 标记 |
| `contracts/fix_context.py` | 闭环传递 | Judge→Generator 的修复上下文 |

## 附录 B: 迁移路径

从 V3.1 迁移到 V4.0 的步骤：

1. ✅ 定义新契约（本阶段）
2. 🔲 实现 Generator Agent（合并 4 个 Agent 的 prompt）
3. 🔲 实现 Judge Agent（增强 Reviewer 的 prompt）
4. 🔲 实现闭环控制器（FixContext 构造 + 轮次管理）
5. 🔲 集成测试（用 V3.1 的测试用例对比）
6. 🔲 灰度上线（V3.1/V4.0 并行运行，对比结果）
