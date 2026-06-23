# Solution Pro 质量评估指南

> **版本**: V2.0.0 | **更新日期**: 2026-06-20  
> **适用范围**: Solution Pro 10 阶段管线的质量评估  
> **评估框架**: Harness 四维评分 + 15维宪法 + Multi-Reviewer 机制

---

## 一、概述

Solution Pro 采用**三层质量评估体系**：

1. **Harness 四维评分** — 每个阶段输出的质量门禁
2. **15维质量宪法** — 方案设计的核心质量标准
3. **Multi-Reviewer 机制** — 3路并行评审（技术/业务/风险）

### 质量评估流程

```
Stage Output (JSON)
    │
    ▼
┌─────────────────────────────────────┐
│ Harness Scorer (4维度)              │
│  ├─ 完整性 (30%)                    │
│  ├─ 必要性 (20%)                    │
│  ├─ 目标一致性 (30%)                │
│  └─ 全局影响 (20%)                  │
└─────────────────────────────────────┘
    │
    ▼ PASS (≥0.85) / WARNING / CRITICAL / BLOCK
    │
    ▼
┌─────────────────────────────────────┐
│ Multi-Reviewer (3路并行)            │
│  ├─ Reviewer Technical              │
│  ├─ Reviewer Business               │
│  └─ Reviewer Risk                   │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│ Consolidator (合并评审意见)         │
└─────────────────────────────────────┘
```

---

## 二、Harness 四维评分

### 2.1 评分维度

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

## 三、15维质量宪法

### 3.1 宪法维度

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

### 3.2 评估方法

每个维度评分 0-100，加权平均得到总分。

---

## 四、Multi-Reviewer 机制

### 4.1 三路并行评审

| Reviewer | 关注点 | 输出 |
|----------|--------|------|
| Technical | 技术可行性、架构合理性、性能瓶颈 | `stages/reviewer_technical.json` |
| Business | 业务价值、用户需求匹配、市场定位 | `stages/reviewer_business.json` |
| Risk | 风险识别、缓解策略、应急预案 | `stages/reviewer_risk.json` |

### 4.2 评审合并

Consolidator 合并三路评审意见，生成统一的改进建议列表。

---

## 五、Prompt 文件索引

### 5.1 核心 Prompt

| Prompt | 用途 | 版本 |
|--------|------|------|
| `pipeline_orchestrator.md` | 管线编排器 | 5.4.0 |
| `planner.md` | 规划阶段 | 5.4.0 |
| `designer.md` | 设计阶段 | 5.4.0 |
| `deliver.md` | 交付阶段 | 5.4.0 |
| `summarizer.md` | 总结阶段 | 5.5.0 |

### 5.2 评审 Prompt

| Prompt | 用途 | 版本 |
|--------|------|------|
| `reviewer.md` | 评审阶段 | 5.4.1 |
| `consolidator.md` | 合并评审 | 5.4.1 |
| `auditor.md` | 审计阶段 | 5.4.0 |
| `fixer.md` | 修复阶段 | 5.4.0 |

### 5.3 Harness Prompt

| Prompt | 用途 | 版本 |
|--------|------|------|
| `harness_v3.md` | Harness 评分 | 3.0.0 |
| `harness_scoring.md` | 评分规则 | 2.1.0 |

### 5.4 专家 Prompt

| Prompt | 用途 | 版本 |
|--------|------|------|
| `researcher_v2_harness.md` | 研究专家 | 2.1.0 |
| `planner_v2_harness.md` | 规划专家 | 2.1.0 |
| `consolidator_v2_harness.md` | 合并专家 | 2.1.0 |
| `auditor_v2_harness.md` | 审计专家 | 2.1.0 |
| `fixer_v2_harness.md` | 修复专家 | 2.1.0 |
| `reviewer_v2_harness.md` | 评审专家 | 2.1.0 |
| `summarizer_v2_harness.md` | 总结专家 | 2.1.0 |
| `fixer_expert_v2_harness.md` | 修复专家 V2 | 2.1.0 |

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

### 7.1 V6 改进测试

```bash
python3 domains/solution_pro/eval/test_v6_improvements.py <path_to_final_result.json>
```

测试项:
- Summarizer 单文件输出
- REQ-ID 传播完整性
- Schema 合规性
- 数据传播一致性

### 7.2 传播检查

```bash
python3 domains/solution_pro/eval/propagation_checker.py <blackboard_path>
```

检查项:
- final_result.json 存在性
- covered_req_ids 字段完整性
- requirement_evidence 传播

---

## 八、变更历史

| 版本 | 日期 | 变更内容 |
|------|------|---------|
| V2.0.0 | 2026-06-20 | Prompt 文件索引更新（pipeline_orchestrator_v6 → pipeline_orchestrator） |
| V1.0.0 | 2026-06-01 | 初始版本 |
