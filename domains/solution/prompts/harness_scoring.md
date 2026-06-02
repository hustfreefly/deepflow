---
id: solution/harness_scoring
version: "1.0.0"
component: solution
updated: "2026-06-02"
---

## 统一 Harness 评分标准

所有 Solution Pro 阶段只使用同一套 4 维评分，分数范围为 0.0-1.0。

| 维度 | 权重 | 含义 |
|:---|:---:|:---|
| completeness 完整性 | 30% | 是否覆盖关键需求、边界、数据流、测试、运维和交付物 |
| necessity 必要性 | 20% | 方案是否贴合实际，避免过度设计、过度审计和无关复杂度 |
| alignment 目标一致性 | 30% | 所有设计决策是否服务于用户原始目标和 confirmed 需求 |
| global_impact 全局影响 | 20% | 是否考虑成本、风险、组织、集成、长期演进和跨阶段影响 |

总分公式：

```text
overall_score = completeness*0.30 + necessity*0.20 + alignment*0.30 + global_impact*0.20
```

决策阈值：

| decision | 条件 |
|:---|:---|
| PASS | overall_score >= 0.85 |
| PASS_WITH_CONDITIONS | 0.75 <= overall_score < 0.85 |
| WARNING | 0.70 <= overall_score < 0.75 |
| CRITICAL_WARNING | 0.60 <= overall_score < 0.70 |
| BLOCK_RECOMMENDATION | overall_score < 0.60 |

输出 JSON 中的 `harness_check` 必须包含：

```json
{
  "completeness": {"score": 0.0, "level": "high|medium|low", "reasoning": "..."},
  "necessity": {"score": 0.0, "level": "high|medium|low", "reasoning": "..."},
  "alignment": {"score": 0.0, "level": "high|medium|low", "reasoning": "..."},
  "global_impact": {"score": 0.0, "level": "high|medium|low", "reasoning": "..."},
  "overall_score": 0.0,
  "decision": "PASS|WARNING|CRITICAL_WARNING|BLOCK_RECOMMENDATION",
  "improvements": ["..."]
}
```
