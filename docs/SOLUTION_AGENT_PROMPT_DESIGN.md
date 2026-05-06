# Solution模块Agent与Prompt详细设计方案

> **版本**: v1.0  
> **日期**: 2026-04-28  
> **状态**: 待评审  
> **目标**: 定义Pro模式13个Agent的角色、职责和Prompt框架

---

## 1. Agent体系总览

### 1.1 8阶段Agent分布

```
Stage 1: Planner定任务
    └─ solution_planner_pro

Stage 2: 评审组并行
    ├─ solution_reviewer_completeness
    ├─ solution_reviewer_reasonableness
    └─ solution_reviewer_weight

Stage 3: Planner修复 + Harness
    └─ solution_fixer_planner

Stage 4: Research组并行
    ├─ solution_researcher_tech
    ├─ solution_researcher_practice
    └─ solution_researcher_risk

Stage 5: 专家汇总
    └─ solution_consolidator

Stage 6: 审计组并行
    ├─ solution_auditor_architecture
    ├─ solution_auditor_technology
    └─ solution_auditor_cost

Stage 7: 专家修复 + Harness
    └─ solution_fixer_expert

Stage 8: Summary输出
    └─ solution_summarizer_pro
```

### 1.2 Agent清单（13个）

| # | Agent ID | 角色名称 | 阶段 | 超时 | Search |
|:---:|:---|:---|:---:|:---:|:---:|
| 1 | planner_pro | Pro任务规划师 | 1 | 5min | ❌ |
| 2 | reviewer_completeness | 完备性评审 | 2 | 5min | ✅ |
| 3 | reviewer_reasonableness | 合理性评审 | 2 | 5min | ✅ |
| 4 | reviewer_weight | 权重评审 | 2 | 5min | ❌ |
| 5 | fixer_planner | Planner修复 | 3 | 5min | ❌ |
| 6 | researcher_tech | 技术方案研究 | 4 | 10min | ✅ |
| 7 | researcher_practice | 业界实践研究 | 4 | 10min | ✅ |
| 8 | researcher_risk | 风险合规研究 | 4 | 10min | ✅ |
| 9 | consolidator | 研究汇总专家 | 5 | 10min | ❌ |
| 10 | auditor_architecture | 架构审计 | 6 | 10min | ✅ |
| 11 | auditor_technology | 技术审计 | 6 | 10min | ✅ |
| 12 | auditor_cost | 成本审计 | 6 | 10min | ✅ |
| 13 | fixer_expert | 专家修复 | 7 | 10min | ❌ |
| 14 | summarizer_pro | Pro文档工程师 | 8 | 10min | ❌ |

---

## 2. Agent详细设计

### 2.1 Stage 1: planner_pro

**角色**: Pro任务规划师（元调度器）

**核心职责**:
1. 分析需求文档，提取关键特征
2. 确定任务复杂度（简单/中等/复杂）
3. 从Agent库选择合适的Agent组合
4. 为每个Agent定义focus和约束
5. 生成8阶段执行计划

**输入**:
- 用户需求文档（Markdown）
- 约束条件（可选）
- 利益相关者（可选）

**输出JSON**:
```json
{
  "role": "planner_pro",
  "session_id": "{session_id}",
  "plan": {
    "complexity": "complex",
    "estimated_duration": "70min",
    "stages": [
      {
        "stage": 2,
        "agents": [
          {"id": "reviewer_completeness", "focus": ["功能覆盖", "边界条件"]},
          {"id": "reviewer_reasonableness", "focus": ["技术可行性"]},
          {"id": "reviewer_weight", "focus": ["性能vs成本"]}
        ]
      },
      {
        "stage": 4,
        "agents": [
          {"id": "researcher_tech", "search_focus": ["微服务", "云原生"]},
          {"id": "researcher_practice", "search_focus": ["阿里架构", "AWS最佳实践"]},
          {"id": "researcher_risk", "search_focus": ["支付安全", "GDPR"]}
        ]
      }
    ]
  },
  "key_areas": [
    {"area": "高并发架构", "weight": 0.3, "rationale": "百万日活"},
    {"area": "数据安全", "weight": 0.25, "rationale": "金融级要求"}
  ],
  "constraints_summary": ["预算500万", "6个月上线"],
  "quality_score": 90
}
```

**Prompt核心要点**:
- 识别需求中的显性和隐性约束
- 根据约束选择轻量或深度研究
- 明确定义每个Agent的职责边界
- 设定Harness检查点

---

### 2.2 Stage 2: Reviewer组（3个）

#### reviewer_completeness - 完备性评审

**核心职责**:
- 功能需求是否全覆盖
- 非功能需求是否考虑
- 边界条件是否明确
- 异常场景是否识别

**Search重点**: 查找同类系统的需求清单做对比

**输出**:
```json
{
  "role": "reviewer_completeness",
  "completeness_score": 85,
  "issues": [
    {"level": "P0", "item": "缺少灾备恢复需求", "evidence": "文本未提及RTO/RPO"},
    {"level": "P1", "item": "日志策略不明确", "evidence": "未定义日志保留期"}
  ],
  "missed_categories": ["监控告警", "运维自动化"],
  "recommendations": ["补充..."]
}
```

#### reviewer_reasonableness - 合理性评审

**核心职责**:
- 技术选型是否合理
- 架构模式是否匹配场景
- 性能目标是否可达
- 成本预算是否合理

**Search重点**: 查找技术栈的适用场景和限制

**输出**:
```json
{
  "role": "reviewer_reasonableness",
  "reasonableness_score": 80,
  "issues": [
    {"level": "P0", "item": "技术选型不匹配", "detail": "用MySQL支撑千万级实时写入"},
    {"level": "P1", "item": "性能目标过高", "detail": "P99<10ms在跨区部署下不可达"}
  ]
}
```

#### reviewer_weight - 权重评审

**核心职责**:
- 重点领域权重分配是否合理
- 资源投入优先级是否得当
- 风险与收益是否平衡

**输出**:
```json
{
  "role": "reviewer_weight",
  "weight_score": 90,
  "issues": [
    {"level": "P2", "item": "测试权重偏低", "current": 0.05, "suggested": 0.15}
  ],
  "weight_distribution": {
    "合理性": "good",
    "建议调整": []
  }
}
```

---

### 2.3 Stage 3: fixer_planner

**角色**: Planner修复 + Harness检查

**核心职责**:
1. 根据评审意见修复P0/P1
2. 忽略P2/P3
3. 修复后进行自检
4. Harness检查质量和发散度

**Harness检查点**:
- 质量: P0修复率100%，P1修复率≥80%
- 发散: 是否引入新功能？复杂度是否超标？

**输出**:
```json
{
  "role": "fixer_planner",
  "fixes_applied": [
    {"issue_id": "P0-1", "action": "补充灾备需求", "status": "fixed"}
  ],
  "harness_check": {
    "P0_resolved": 3,
    "P1_resolved": 2,
    "new_features_added": 0,
    "complexity_match": "fit",
    "recommendation": "pass"
  },
  "final_plan": {...}
}
```

---

### 2.4 Stage 4: Researcher组（3个）

#### researcher_tech - 技术方案研究

**核心职责**:
- 技术栈对比分析
- 架构模式选择
- 开源方案调研
- 云原生实践

**Search关键词示例**:
- "2026微服务框架对比 Kubernetes vs Nomad"
- "云原生数据库选型 TiDB vs CockroachDB"

**输出**:
```json
{
  "role": "researcher_tech",
  "recommendations": {
    "architecture_pattern": "微服务+事件驱动",
    "tech_stack": {
      "backend": "Go+grpc",
      "database": "TiDB",
      "cache": "Redis Cluster",
      "message_queue": "Kafka"
    },
    "alternatives": [...],
    "tradeoffs": "..."
  },
  "references": [
    {"source": "InfoQ", "url": "...", "title": "..."}
  ]
}
```

#### researcher_practice - 业界实践研究

**核心职责**:
- 同类系统案例分析
- 大厂最佳实践
- 行业标准参考
- 最新技术趋势

**Search关键词示例**:
- "阿里巴巴电商架构演进 2025"
- "AWS微服务最佳实践"

**输出**:
```json
{
  "role": "researcher_practice",
  "case_studies": [
    {
      "company": "阿里巴巴",
      "scenario": "双11高并发",
      "architecture": "微服务+异地多活",
      "lessons": "..."
    }
  ],
  "best_practices": [...],
  "industry_standards": [...]
}
```

#### researcher_risk - 风险合规研究

**核心职责**:
- 安全风险识别
- 合规要求（GDPR/等保/PCI-DSS）
- 常见架构陷阱
- 应急预案参考

**Search关键词示例**:
- "电商系统安全风险 2026 OWASP"
- "GDPR合规技术要求"

**输出**:
```json
{
  "role": "researcher_risk",
  "risks": [
    {
      "category": "安全",
      "risk": "支付接口未做限流",
      "severity": "高",
      "mitigation": "..."
    }
  ],
  "compliance_requirements": [...],
  "common_pitfalls": [...]
}
```

---

### 2.5 Stage 5: consolidator

**角色**: 研究汇总专家

**核心职责**:
- 整合3份Research报告
- 解决冲突观点
- 去重合并
- 形成统一结论

**输入**: researcher_tech/practice/risk输出

**输出**:
```json
{
  "role": "consolidator",
  "consolidated_research": {
    "tech_recommendation": "...",
    "practice_insights": "...",
    "risk_summary": "...",
    "conflicts_resolved": [
      {"topic": "数据库选型", "researcher_tech": "TiDB", "researcher_practice": "MySQL", "resolution": "TiDB"}
    ]
  }
}
```

---

### 2.6 Stage 6: Auditor组（3个）

#### auditor_architecture - 架构审计

**核心职责**:
- 架构合理性
- 可扩展性评估
- 高可用设计
- 与Research结论一致性

**输出**:
```json
{
  "role": "auditor_architecture",
  "architecture_score": 85,
  "issues": [
    {"level": "P0", "item": "单点故障", "detail": "数据库无主备"},
    {"level": "P1", "item": "扩展性不足", "detail": "单体服务无法水平扩展"}
  ]
}
```

#### auditor_technology - 技术审计

**核心职责**:
- 技术可行性
- 性能达标性
- 安全合规性
- 技术债务风险

**输出**:
```json
{
  "role": "auditor_technology",
  "technology_score": 80,
  "issues": [
    {"level": "P0", "item": "技术栈不匹配团队技能", "detail": "团队熟悉Java，选型Go"},
    {"level": "P1", "item": "依赖组件成熟度不足", "detail": "某开源组件v0.x"}
  ]
}
```

#### auditor_cost - 成本审计

**核心职责**:
- 预算合理性
- ROI分析
- 资源利用率
- 长期运维成本

**输出**:
```json
{
  "role": "auditor_cost",
  "cost_score": 75,
  "issues": [
    {"level": "P1", "item": "云资源成本超预算30%", "detail": "..."},
    {"level": "P2", "item": "未考虑三年TCO", "detail": "..."}
  ],
  "cost_breakdown": {...}
}
```

---

### 2.7 Stage 7: fixer_expert

**角色**: 专家修复 + Harness检查

**核心职责**:
1. 根据审计意见修复P0/P1
2. 生成具体修复方案
3. Harness检查修复质量和发散度

**Harness检查点**:
- 质量: P0/P1全部修复，方案可执行
- 发散: 是否引入技术债务？是否保持架构一致性？

**输出**:
```json
{
  "role": "fixer_expert",
  "fixes": [
    {
      "issue_id": "P0-1",
      "original": "单点故障",
      "fix": "增加MySQL主从复制+自动切换",
      "validation": "RTO<30s, RPO<1min"
    }
  ],
  "harness_check": {
    "P0_resolved": 2,
    "P1_resolved": 4,
    "tech_debt_introduced": 0,
    "architecture_consistency": true,
    "recommendation": "pass"
  }
}
```

---

### 2.8 Stage 8: summarizer_pro

**角色**: Pro文档工程师

**核心职责**:
- 按模板格式化最终方案
- 固定部分（模板）+ 灵活部分（项目特定）
- 生成可交付的架构设计文档

**输出模板结构**:
```markdown
# [项目] 架构设计方案

## 1. 执行摘要
[固定格式：一句话总结方案核心]

## 2. 背景与目标
[灵活内容：基于需求文档]

## 3. 架构设计
### 3.1 整体架构（C4 L2）
[固定格式：容器图描述]

### 3.2 技术选型
[灵活内容：基于Research结论]

## 4. 关键设计决策
[灵活内容：ADR格式]

## 5. 实施路线图
[固定格式：甘特图/表格]

## 6. 风险评估与缓解
[灵活内容：基于Risk Research]

## 7. 附录
### 7.1 参考资料
[Research引用列表]

### 7.2 术语表
### 7.3 团队与资源
```

---

## 3. Prompt设计原则

### 3.1 通用结构（所有Agent）

```markdown
# {Agent名称} - Solution Pro Agent Prompt

## 角色定位
你是Solution Pro管线的{角色}，负责{一句话职责}。

## 核心职责
1. {职责1}
2. {职责2}
3. {职责3}

## 📊 数据读取（强制）

### 输入文件
- `{session_id}/{prev_stage}_output.json` → 前序阶段输出

### 读取步骤
1. 使用blackboard.read()或文件系统读取
2. 验证数据完整性

## 🔍 搜索工具（可选）

使用OpenClaw web_fetch工具：
```python
# 在Agent代码中使用web_fetch工具
# 注意：web_fetch是OpenClaw工具，非Python模块
# 由主Agent通过task参数传入或Agent内部调用

# 示例调用方式（在Agent Prompt中说明）：
# "请使用web_fetch工具搜索以下关键词的业界实践：
#  - '{技术栈} 最佳实践 2026'
#  - '{架构模式} 大厂案例'"
```

### Search策略
- 每个Agent最多3次web_fetch调用
- 关键词需具体（含年份、场景、对比维度）
- 结果需标注来源URL和可信度

### Search来源优先级
1. 官方文档（优先）
2. 技术博客/ medium / 大厂技术博客
3. GitHub / Stack Overflow
4. 行业报告（Gartner/Forrester等）

## 🚨 Blackboard 数据流规则

### 输出写入
```
输出路径: {session_id}/{role}_output.json
写入格式: JSON结构化数据
```

## 🚨 强制执行规则

### 执行前确认
- [ ] 我已读取输入数据
- [ ] 我将生成结构化JSON输出
- [ ] 我将写入指定路径

### 执行后验证
- [ ] 结果文件已创建
- [ ] 包含完整JSON结构

## 禁止行为
❌ 仅输出意图声明
❌ 未读取数据就处理
❌ 生成占位符内容
❌ 不写入文件直接返回

## 输出格式
{具体JSON结构}

## 任务指令
{{task_description}}

上下文：
- 需求主题：{{topic}}
- 会话ID：{{session_id}}
- 迭代轮次：{{iteration}}
```

### 3.2 Agent特有Prompt要点

| Agent | 特有要点 |
|:---|:---|
| planner_pro | 动态Agent选择逻辑、复杂度评估 |
| reviewer_* | 分级标准（P0/P1/P2/P3）、证据引用 |
| fixer_planner | Harness检查点、发散检测 |
| researcher_* | Search关键词生成、来源标注 |
| consolidator | 冲突解决策略、去重逻辑 |
| auditor_* | 审计视角、检查清单 |
| fixer_expert | 具体修复方案、技术债务识别 |
| summarizer_pro | 模板填充、格式规范 |

---

## 4. Harness检查规则

### 4.1 Stage 3 Harness（ScopeGuard）

**质量检查**:
- P0修复率 ≥ 100%
- P1修复率 ≥ 80%
- 无新增P0

**发散检查**:
```yaml
over_design_signals:
  - 引入计划外新功能
  - 技术复杂度超标（如简单需求用微服务）
  - 超出预算/周期约束
```

### 4.2 Stage 7 Harness（PragmaticGuard）

**质量检查**:
- P0/P1全部修复
- 修复方案具体可执行

**发散检查**:
```yaml
tech_debt_signals:
  - 临时补丁方案
  - 硬编码
  - 与架构不一致的组件
```

---

## 5. 待评审要点

### 5.1 需要评审的决策

| # | 决策项 | 建议方案 | 待确认 |
|:---:|:---|:---|:---:|
| 1 | Reviewer是否都需要Search | completeness和reasonableness需要，weight不需要 | 待确认 |
| 2 | Researcher并发时是否去重 | 由consolidator处理 | 待确认 |
| 3 | Auditor评分是否影响收敛 | **已确认**：仅P0/P1影响流程，评分(0-100)用于质量参考，不阻断 |
| 4 | Summarizer模板固定度 | 50%固定+50%灵活 | 待确认 |

---

## 附录：参考文档

- Investment Agent设计: `prompts/investment/`
- Solution模块设计: `docs/SOLUTION_MODULE_DESIGN.md`
- Pro模式设计: `docs/SOLUTION_PRO_MODE_DESIGN.md`

---

**文档版本**: v1.0  
**下次迭代**: 评审后根据意见修订
