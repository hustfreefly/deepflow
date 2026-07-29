# Solution Pro 质量评估指南

> **版本**: 4.0.0 | **更新日期**: 2026-07-27  
> **适用范围**: Solution Pro V4.0 简化管线的质量评估  
> **评估框架**: Module 内置 Harness + L0 post_validator（独立工具）+ L2 对抗审查（独立工具）

---

## 一、概述

Solution Pro V4.0 采用**模块化质量评估体系**：

1. **Module 内置 Harness** — 每个 Module Agent 内部的质量门禁
2. **L0 下限守卫** — post_validator.py（独立工具，非 orchestrator 内置）
3. **L2 上限提升** — 对抗 Agent（独立工具，非 orchestrator 内置）

### V4.0 质量架构变更

> **Note**: V4.0 中 post_validator.py 和对抗 Agent 不再是 orchestrator 管线的内置步骤。
> 它们作为独立工具可供外部调用或按需手动触发。

```
Orchestrator V4.0（简化管线）
  │
  ├── Planning Module Agent
  │   └── 内置 Harness（Gate A/B）
  │
  ├── Research Module Agent
  │   └── 内置 Harness（Gate A/B）
  │
  └── Summary Module Agent
      └── 内置 Harness（Gate A/B + Fix Loop）
  │
  ↓
.completed 标记文件

（可选）外部质量检查
  ├── L0: post_validator.py（独立调用）
  └── L2: adversarial_quality_reviewer + cross_module_consistency_checker（独立调用）
```

---

## 二、Module 内置 Harness

### 2.1 Harness 四维评分

| 维度 | 权重 | 评估内容 | 阈值 |
|------|------|---------|------|
| 完整性 (Completeness) | 30% | 方案覆盖范围，关键设计点无遗漏 | ≥0.70 |
| 必要性 (Necessity) | 20% | 方案适度，无过度设计 | ≥0.70 |
| 目标一致性 (Alignment) | 30% | 方案与原始目标的一致性 | ≥0.60 (特殊规则) |
| 全局影响 (Global Impact) | 20% | 成本、风险、集成、运维、长期演进 | ≥0.70 |

### 2.2 决策阈值

| 决策 | 分数范围 | 行为 |
|------|---------|------|
| PASS | ≥ 0.85 | 质量达标，进入下一阶段 |
| WARNING | 0.70-0.84 | 咨询意见，可继续 |
| CRITICAL_WARNING | 0.60-0.69 | 强烈建议修改 |
| BLOCK_RECOMMENDATION | < 0.60 | 建议重新规划 |

### 2.3 特殊规则

**目标一致性 < 0.6 → 至少 CRITICAL_WARNING**

即使其他维度评分很高，如果方案偏离原始目标，也会被标记为严重问题。

### 2.4 实现

详见 `domains/solution_pro/harness_scorer.py`

---

## 三、L0 下限守卫（独立工具）

### 3.1 post_validator.py

**职责**: Schema 验证 + 需求覆盖率 + 信息守恒检查

**调用方式**:
```python
from domains.solution_pro.post_validator import validate_solution_output
from core.blackboard.blackboard_manager import BlackboardManager

bb = BlackboardManager(session_id)
result = validate_solution_output(bb)

if result['passed']:
    print('L0 validation passed')
else:
    print(f'L0 validation failed: {result["failures"]}')
```

**检查项**:
1. **Schema 验证** — final_solution 结构和必要字段
2. **需求覆盖率** — requirement_index 中的需求是否在输出中被覆盖
3. **信息守恒** — semantic_anchors 是否保留

**返回值**:
```python
{
    "passed": bool,
    "failures": [{"severity": str, "check": str, "message": str}],
    "summary": {"total_checks": int, "passed": int, "failed": int}
}
```

### 3.2 使用场景

- **手动调用**: 在 E2E 测试后手动运行 L0 验证
- **CI/CD 集成**: 在自动化测试流程中调用
- **按需触发**: 在质量审查时调用

---

## 四、L2 上限提升（独立工具）

### 4.1 对抗 Agent

**Adversarial Quality Reviewer** — 语义质量审查

**调用方式**:
```python
from core.blackboard.blackboard_manager import BlackboardManager
from core.prompt_utils import render_prompt

bb = BlackboardManager(session_id)
result = render_prompt(
    'domains/solution_pro/prompts/adversarial_quality_reviewer.md',
    session_id=session_id,
    deepflow_root='/path/to/deepflow',
    module_name='summary',
    module_output_file='final_solution',
)
bb.write('adversarial_quality_reviewer.md', result.content, subdir='stages')

# spawn adversarial_reviewer agent
# sessions_spawn(...)
```

**输出**: `stages/adversarial_review_summary.json`

**Cross-Module Consistency Checker** — 跨模块数据流检查

**调用方式**:
```python
result = render_prompt(
    'domains/solution_pro/prompts/cross_module_consistency_checker.md',
    session_id=session_id,
    deepflow_root='/path/to/deepflow',
)
bb.write('cross_module_consistency_checker.md', result.content, subdir='stages')

# spawn consistency_checker agent
# sessions_spawn(...)
```

**输出**: `stages/consistency_check.json`

### 4.2 使用场景

- **质量审查**: 在关键交付前运行 L2 审查
- **问题诊断**: 在发现质量问题时运行 L2 诊断
- **持续改进**: 收集 L2 审查结果用于改进 prompt

---

## 五、15维质量宪法

### 5.1 宪法维度

| 类别 | 维度 | 说明 |
|------|------|------|
| **架构** | 1. 模块化 | 高内聚低耦合 |
| | 2. 可扩展性 | 未来扩展能力 |
| | 3. 可维护性 | 代码清晰易维护 |
| **功能** | 4. 完整性 | 覆盖所有需求 |
| | 5. 一致性 | 接口和数据一致 |
| | 6. 可用性 | 用户友好 |
| **性能** | 7. 响应时间 | 满足性能要求 |
| | 8. 吞吐量 | 处理容量足够 |
| | 9. 资源效率 | 资源使用合理 |
| **安全** | 10. 认证授权 | 安全机制完善 |
| | 11. 数据保护 | 数据加密和备份 |
| **运维** | 12. 可观测性 | 监控和日志完善 |
| | 13. 可部署性 | 部署流程清晰 |
| **成本** | 14. 开发成本 | 工时和复杂度合理 |
| | 15. 运维成本 | 长期运维成本可控 |

### 5.2 评估方法

每个维度评分 0-100，加权平均得到总分。

---

## 六、质量报告模板

### 6.1 Harness 评分报告

```json
{
  "completeness": {
    "score": 0.88,
    "level": "high",
    "reasoning": "方案覆盖所有关键设计点"
  },
  "necessity": {
    "score": 0.85,
    "level": "high",
    "reasoning": "方案适度，无过度设计"
  },
  "alignment": {
    "score": 0.92,
    "level": "high",
    "reasoning": "方案与目标完全对齐"
  },
  "global_impact": {
    "score": 0.86,
    "level": "high",
    "reasoning": "成本、风险、运维分析充分"
  },
  "overall_score": 0.88,
  "decision": "PASS",
  "improvements": []
}
```

### 6.2 需求追溯矩阵

```json
{
  "covered_req_ids": ["REQ-001", "REQ-002", "REQ-003"],
  "requirement_evidence": [
    {
      "req_id": "REQ-001",
      "status": "covered",
      "evidence": "设计方案中包含对应的模块和接口",
      "confidence": 0.95
    }
  ]
}
```

---

## 七、验证脚本

### 7.1 L0 验证

```bash
cd /Users/allen/.openclaw/workspace/.deepflow && PYTHONPATH=. python3 -c "
from domains.solution_pro.post_validator import validate_solution_output
from core.blackboard.blackboard_manager import BlackboardManager

bb = BlackboardManager('session_id')
result = validate_solution_output(bb)
print(f'Passed: {result[\"passed\"]}')
print(f'Summary: {result[\"summary\"]}')
"
```

### 7.2 传播检查

```bash
python3 domains/solution_pro/eval/propagation_checker.py <blackboard_path>
```

检查项:
- final_solution.md 存在性
- covered_req_ids 字段完整性
- requirement_evidence 传播

---

## 八、变更历史

| 版本 | 日期 | 变更内容 |
|------|------|---------|
| 4.0.0 | 2026-07-27 | V4.0 简化：L0/L2 从 orchestrator 内置步骤变为独立工具 |
| 2.0.0 | 2026-06-20 | Prompt 文件索引更新 |
| 2.0.0 | 2026-06-01 | 初始版本 |
