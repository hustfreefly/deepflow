# Spec Pro 质量评估指南

> **版本**: V2.0.0 | **更新日期**: 2026-06-20  
> **适用范围**: Spec Pro 需求收集与结构化引擎  
> **评估框架**: 5维度 Output Guard + 3子门禁

---

## 一、概述

Spec Pro 采用**5维度 Output Guard**评估 Living Spec 的质量，确保输出可以被下游引擎（Solution Pro）有效消费。

### 质量评估架构

```
Living Spec (JSON)
    │
    ▼
┌─────────────────────────────────────┐
│ SemanticGate (5维度评估)            │
│  ├─ 清晰度 (25%)                    │
│  ├─ 完整度 (25%)                    │
│  ├─ 可执行度 (20%)                  │
│  ├─ 一致度 (15%)                    │
│  └─ 下游适配度 (15%)                │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│ 3个子门禁                           │
│  ├─ Spec Quality Gate               │
│  ├─ Inference Audit Gate            │
│  └─ Trajectory Audit Gate           │
└─────────────────────────────────────┘
    │
    ▼ 最终决策 = worst(3个子门禁)
```

---

## 二、5维度评估框架

### 2.1 清晰度 (Clarity) — 权重 25%

**评估内容**: 需求表述是否无歧义，下游能否准确理解

**检查项**:
- `confirmed` 层中的描述是否有量化指标？
  - "高性能" → 模糊（扣分）
  - "支持10000并发，P99 < 200ms" → 清晰（满分）
- 术语是否一致？
- 功能边界是否明确？

**评分标准**:
| 分数 | 标准 |
|------|------|
| 100 | 所有需求都有明确量化指标 |
| 75 | 大部分需求有量化，少数定性描述但足够清晰 |
| 50 | 混合量化和模糊描述 |
| 25 | 大部分描述模糊 |
| 0 | 全部是泛泛描述 |

### 2.2 完整度 (Completeness) — 权重 25%

**评估内容**: 关键需求维度是否都有覆盖

**评估方法**: 直接使用 `quality_report.json` 中的 7 维度评分，取加权平均

**7维度**:
1. 目标与愿景
2. 用户与角色
3. 功能需求
4. 非功能需求
5. 约束条件
6. 风险与假设
7. 验收标准

### 2.3 可执行度 (Executability) — 权重 20%

**评估内容**: 下游引擎能否直接消费这份 Spec

**检查项**:
- `capabilities` 是否有 always/should/never 分层？（有 → +40）
- `quality_attributes` 是否有具体数字？（有 → +30）
- `constraints` 是否有具体值（预算金额、时间节点）？（有 → +30）

### 2.4 一致度 (Consistency) — 权重 15%

**评估内容**: 需求之间是否有矛盾

**检查项**:
- 约束条件与功能需求是否兼容？
  - 例: "预算50万" + "全用AWS最贵方案" → 矛盾
- 质量属性之间是否兼容？
  - 例: "99.999%可用" + "不能做冗余部署" → 矛盾
- 能力要求是否有冲突？
  - 例: always_do: "开放所有API" + never_do: "不允许外部访问" → 矛盾

### 2.5 下游适配度 (Downstream Fitness) — 权重 15%

**评估内容**: 结构是否完整，是否适合下游消费

**检查项**:
- `living_spec.json` 结构是否符合标准？（必要字段存在 → +40）
- `solution_pro_hints` 是否存在且有 `focus_areas`？（有 → +30）
- `route_recommendation` 是否合理？（有 → +30）

---

## 三、3个子门禁

### 3.1 Spec Quality Gate

**计算公式**:
```
总分 = 清晰度×0.25 + 完整度×0.25 + 可执行度×0.20 + 一致度×0.15 + 适配度×0.15
```

**决策阈值**:
| 决策 | 分数 | 行为 |
|------|------|------|
| PASS | ≥ 75 | Spec 质量达标，可以交付下游 |
| WARN | 60-74 | 质量可用但有改进空间 |
| SOFT_BLOCK | 45-59 | 质量不足，建议补充（用户可 override） |
| HARD_BLOCK | < 45 | 质量严重不足 |

**特殊规则**:
- 清晰度 < 50 → 至少 WARN
- 一致度 < 40 → 至少 SOFT_BLOCK
- 可执行度 < 40 → 至少 WARN

### 3.2 Inference Audit Gate

**评估内容**: 推断处理完整性

| 检查项 | PASS 条件 | WARN 条件 |
|--------|----------|----------|
| 推断处理完整性 | pending 推断 ≤ 3 | pending 推断 > 3 |
| 推断拒绝影响 | 拒绝的推断不覆盖关键维度 | 拒绝导致某维度空白 |
| 推断 basis 清晰度 | 所有推断有 basis | 有推断无 basis |

### 3.3 Trajectory Audit Gate

**评估内容**: 对话轨迹质量

| 检查项 | PASS 条件 | WARN 条件 |
|--------|----------|----------|
| 轮次合理性 | 3-6 轮（standard） | < 3 轮（可能不充分） |
| 质量单调性 | 单调递增 | 有回退轮次 |
| 维度均衡性 | 所有维度都有提升 | 某维度始终为 0 |

---

## 四、最终决策

```
最终决策 = worst(spec_quality, inference_audit, trajectory_audit)
```

**用户 Override**:
- WARN/SOFT_BLOCK → 用户说"可以了" → 放行（标注风险）
- HARD_BLOCK → 用户确认 → 仍然放行（明确标注"用户强制放行"）

---

## 五、Living Spec 数据结构参考

### 5.1 顶层结构

```json
{
  "metadata": {
    "project_name": "项目名称",
    "version": "1.0",
    "created_at": "ISO时间",
    "updated_at": "ISO时间",
    "rounds": 4
  },
  "confirmed": {
    "objectives": [...],
    "users": [...],
    "capabilities": {...},
    "quality_attributes": {...},
    "constraints": {...},
    "risks": [...],
    "acceptance_criteria": [...]
  },
  "inferred": {
    "confirmed": [...],
    "pending": [...],
    "rejected": [...]
  },
  "solution_pro_hints": {
    "focus_areas": [...],
    "complexity_level": "medium",
    "recommended_mode": "standard"
  },
  "route_recommendation": "solution_pro"
}
```

### 5.2 confirmed 层详细结构

#### objectives（目标）
```json
[
  {
    "text": "支持10000并发用户",
    "type": "functional",
    "priority": "high",
    "quantified": true
  }
]
```

#### users（用户）
```json
[
  {
    "role": "普通用户",
    "count": "10000+",
    "key_needs": "快速响应、易用性"
  }
]
```

#### capabilities（能力）
```json
{
  "always_do": ["开放所有API", "支持多语言"],
  "should_do": ["提供文档", "支持监控"],
  "never_do": ["不允许外部访问数据库", "不存储敏感信息"]
}
```

#### quality_attributes（质量属性）
```json
{
  "performance": "P99 < 200ms",
  "availability": "99.9%",
  "scalability": "支持水平扩展",
  "security": "OAuth 2.0 + HTTPS"
}
```

#### constraints（约束）
```json
{
  "platform": "阿里云",
  "tech_stack": ["Python", "PostgreSQL", "Redis"],
  "data_source": ["用户行为日志", "业务数据库"]
}
```

### 5.3 inferred 层详细结构

```json
{
  "confirmed": [
    {
      "text": "需要负载均衡",
      "basis": "基于高并发需求推断",
      "confidence": 0.9
    }
  ],
  "pending": [
    {
      "text": "是否需要CDN",
      "basis": "基于全球用户推断",
      "confidence": 0.6,
      "reason": "用户分布未明确"
    }
  ],
  "rejected": [
    {
      "text": "需要微服务架构",
      "reason": "项目规模不适合"
    }
  ]
}
```

### 5.4 solution_pro_hints

```json
{
  "focus_areas": [
    {
      "area": "性能优化",
      "weight": 0.4,
      "reason": "高并发需求"
    },
    {
      "area": "安全设计",
      "weight": 0.3,
      "reason": "敏感数据处理"
    }
  ],
  "complexity_level": "high",
  "recommended_mode": "standard",
  "estimated_duration": "45分钟"
}
```

---

## 六、输出格式

### 6.1 harness_report.json

```json
{
  "harness_version": "2.1.0",
  "timestamp": "ISO时间",
  "dimensions": {
    "clarity": {
      "score": 75,
      "weight": 0.25,
      "reasoning": "量化指标覆盖率: 3/4",
      "issues": ["部分目标缺少量化"]
    },
    "completeness": {
      "score": 82,
      "weight": 0.25,
      "reasoning": "7维度加权平均: 82",
      "issues": []
    },
    "executability": {
      "score": 70,
      "weight": 0.20,
      "reasoning": "capabilities分层: ✓, quality_attrs: ✓",
      "issues": []
    },
    "consistency": {
      "score": 90,
      "weight": 0.15,
      "reasoning": "无明显矛盾",
      "issues": []
    },
    "fitness": {
      "score": 85,
      "weight": 0.15,
      "reasoning": "结构完整, hints存在",
      "issues": []
    }
  },
  "overall_score": 79.5,
  "gates": {
    "spec_quality": {
      "score": 79.5,
      "decision": "PASS"
    },
    "inference_audit": {
      "pending": 2,
      "decision": "PASS",
      "notes": "2个推断待确认"
    },
    "trajectory_audit": {
      "rounds": 4,
      "monotonic": true,
      "decision": "PASS"
    }
  },
  "final_decision": "PASS",
  "final_reasoning": "需求质量79.5分达到75分阈值，推断审计和对话轨迹均PASS",
  "improvements_if_more_time": [
    "可以补充风险与假设维度",
    "建议量化质量属性中的'易用性'指标"
  ],
  "warnings": [],
  "downstream_readiness": {
    "solution_pro": true,
    "readiness_notes": "Living Spec 可被 Solution Pro Standard 模式消费"
  }
}
```

---

## 七、验证脚本

### 7.1 命令行使用

```bash
python3 domains/spec_pro/eval/harness.py <blackboard_path>
```

**示例**:
```bash
python3 domains/spec_pro/eval/harness.py blackboard/my_project/
```

**输出**:
- 控制台打印评估结果
- 保存 `spec/harness_report.json`

### 7.2 Python API

```python
from domains.spec_pro.eval.harness import load_and_evaluate

report = load_and_evaluate("blackboard/my_project/")

print(f"总分: {report.overall_score}")
print(f"决策: {report.final_decision}")
```

---

## 八、最佳实践

### 8.1 提高清晰度的方法

1. **量化所有目标**: 使用具体数字（%、秒、个、条）
2. **定义术语表**: 至少 3 个关键术语
3. **明确边界**: 使用 always_do/should_do/never_do 分层

### 8.2 提高完整度的方法

1. **覆盖 7 维度**: 确保每个维度都有内容
2. **深入挖掘**: 不要停留在表面需求
3. **交叉验证**: 从不同角色视角检查

### 8.3 提高可执行度的方法

1. **分层 capabilities**: always/should/never 都要有
2. **量化质量属性**: 使用具体数字而非"高性能"
3. **明确约束**: 预算金额、时间节点、技术栈

### 8.4 提高一致度的方法

1. **交叉检查**: 约束 vs 功能、质量 vs 成本
2. **矛盾检测**: 自动检查 always_do vs never_do
3. **用户确认**: 发现潜在矛盾时询问用户

### 8.5 提高下游适配度的方法

1. **完整结构**: 确保所有必要字段存在
2. **添加 hints**: 提供 focus_areas 和复杂度评估
3. **推荐路由**: 明确指定下游引擎和模式

---

## 九、变更历史

| 版本 | 日期 | 变更内容 |
|------|------|---------|
| V2.0.0 | 2026-06-20 | 新增 "Living Spec 数据结构参考" 章节 |
| V1.0.0 | 2026-05-23 | 初始版本 |

---

## 十、相关文档

- **Harness Prompt**: `domains/spec_pro/prompts/harness.md`
- **Harness 实现**: `domains/spec_pro/eval/harness.py`
- **Coordinator**: `domains/spec_pro/coordinator.py`
- **全链路质量指南**: `QUALITY_GUIDE.md` (项目根目录)
