# Solution Pro模式详细设计文档

> **版本**: v2.1  
> **日期**: 2026-05-03  
> **状态**: ✅ 已实现（Harness V2 + Layer 2约束验证）  
> **目标**: 高质量架构设计，适合复杂企业级场景

---

## 1. 模式定位

### 1.1 三种模式对比

| 模式 | 适用场景 | 执行时间 | Agent数量 | 特点 |
|:---|:---|:---:|:---:|:---|
| **Quick** | 简单方案预览 | 2-3分钟 | 3个 | 快速输出，初步思路 |
| **Standard** | 一般架构设计 | 8-15分钟 | 3-4个 | 平衡质量与时效 |
| **Pro** | 复杂企业级架构 | 20-30分钟 | 12+个 | 深度研究，Harness V2 质量保障 |

### 1.2 Pro模式核心价值

- **任务规划评审**：避免研究方向错误
- **业界最佳实践**：Search获取最新技术趋势
- **Harness V2 质量门控**：中期检查（Reviewers）+ 最终把关（Harness Final）
- **Layer 2 约束验证**：Planning 动态生成约束，Researcher 显式验证
- **两阶段执行**：Planning 先执行，约束注入后续 Worker
- **修复闭环**：Audit → Fix → Fixer Expert 递进修正

---

## 2. 整体架构

### 2.1 10阶段流程图（Harness V2）

```
┌─────────────────────────────────────────────────────────────────┐
│ Stage 1: Planner定任务 (5分钟)                                    │
│ ├─ 输入: 用户需求文档                                             │
│ ├─ 输出: 任务计划（含重点领域权重）                                │
│ └─ 要求: 完备性、合理性、权重分配                                  │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ Stage 2: 评审组并行 (3 Agent, 5分钟, 并发)                        │
│ ├─ 完备性评审Agent + Search                                      │
│ ├─ 合理性评审Agent + Search                                      │
│ └─ 权重评审Agent + Search                                        │
│ 输出: 评审意见（P0/P1/P2/P3分级）                                 │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ Stage 3: Planner修复 (5分钟)                                     │
│ ├─ 输入: 评审意见                                                 │
│ ├─ 处理: 只修复P0/P1                                              │
│ └─ 输出: 修复后的最终计划                                         │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ Stage 4: Research组并行 (3 Agent, 10分钟, 并发)                   │
│ ├─ 技术方案Research + Search                                     │
│ ├─ 业界实践Research + Search                                     │
│ └─ 风险合规Research + Search                                     │
│ 输出: 研究报告（带引用来源）                                      │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ Stage 5: 专家汇总 (1 Agent, 10分钟)                              │
│ ├─ 输入: 3份Research报告                                          │
│ ├─ 处理: 整合、去重、冲突解决                                     │
│ └─ 输出: 统一研究报告                                             │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ Stage 6: 审计组并行 (3 Agent, 10分钟, 并发)                       │
│ ├─ 架构审计Agent + Search                                        │
│ ├─ 技术审计Agent + Search                                        │
│ └─ 成本审计Agent + Search                                        │
│ 输出: 审计意见（P0/P1/P2/P3分级）                                 │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ Stage 7: Fix（修正）(5分钟)                                      │
│ ├─ 输入: 审计意见                                                 │
│ ├─ 处理: 修正方案中的问题                                         │
│ └─ 输出: 修正后的方案                                             │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ Stage 8: Fixer Expert（深度修正）(5分钟)                         │
│ ├─ 输入: 审计意见中的 Critical/Major 问题                        │
│ ├─ 处理: 深度修正和优化                                           │
│ └─ 输出: 深度修正后的方案                                         │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ Stage 9: Harness V2 Final（最终质量门禁）(3分钟)                  │
│ ├─ 输入: 最终方案                                                 │
│ ├─ 评分: 完整性（60%）+ 适度性（40%）                             │
│ ├─ 阈值: ≥0.85 PASS, <0.70 BLOCK                                  │
│ └─ 输出: harness_final.json（含反馈和改进建议）                   │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ Stage 10: Summarizer（最终总结）(5分钟)                          │
│ ├─ 输入: 全流程输出                                               │
│ ├─ 处理: 按模板格式化生成最终报告                                 │
│ └─ 输出: final_report.md（Markdown格式）                          │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 Layer 2 约束验证机制

**设计目标**: 确保 Planning 阶段定义的约束在后续阶段被满足

**流程**:
```
Planning (Stage 2)
  ├─ 分析任务特征
  ├─ 生成 layer2_constraints
  │   ├─ reviewer.constraints: [...]
│   ├─ researcher.constraints: [...]
│   └─ consolidator.constraints: [...]
  └─ 写入 Blackboard/stages/planning.json

HarnessV2OrchestratorHelper
  ├─ read_layer2_constraints()
  └─ build_phase2_tasks(layer2_constraints=...)

Researchers (Stage 4)
  ├─ 接收 layer2_constraints
  ├─ 执行研究
  └─ 输出 verification_checklist
     {
       "C1": {
         "constraint": "必须调研国产AGV价格",
         "satisfied": true,
         "evidence": "海康8-10万/台，快仓9-12万/台"
       }
     }
```

### 2.3 并发控制

**最大并发数**: 8个Agent

**并发分配**:
- Stage 3（Reviewers）: 3个并行
- Stage 4（Researchers）: 3-4个并行
- Stage 6（Audit）: 串行（4维度审计）
- Stage 7-8（Fix）: 串行
- 其他阶段: 串行执行

**并发策略**:
```python
# 使用asyncio.Semaphore控制
MAX_CONCURRENT_AGENTS = 8
semaphore = asyncio.Semaphore(MAX_CONCURRENT_AGENTS)

async def run_worker(worker_config):
    async with semaphore:
        # 执行Agent任务
        pass
```

---

## 3. Agent详细设计

### 3.1 Stage 1: Data Collection（数据收集）

**角色**: 数据收集员  
**超时**: 3分钟  
**Search**: 启用（Web搜索）

**任务**:
- 基于任务主题生成搜索关键词
- 执行 Web 搜索收集行业信息
- 整理关键发现、成本参考、实施案例

**输出**:
```json
{
  "status": "completed",
  "search_keywords": ["关键词1", "关键词2"],
  "search_results_summary": {
    "industry_trends": "行业趋势摘要",
    "key_technologies": ["技术1", "技术2"],
    "cost_references": "成本参考信息",
    "implementation_cases": "实施案例参考"
  },
  "for_planner": {
    "recommended_focus": ["建议关注点1"],
    "risk_hints": ["风险提示1"]
  }
}
```

---

### 3.2 Stage 2: Planning（规划）
**注意**: 原 Stage 1 现调整为 Stage 2，增加 Data Collection 作为 Stage 1

**角色**: 任务规划师
**超时**: 5分钟
**模型**: 主力模型（如Claude-4）

**输入**:
- 用户需求文档（Markdown格式）
- 约束条件（可选）
- 利益相关者（可选）

**输出格式**:
```json
{
  "task_plan": {
    "overview": "任务概述",
    "key_areas": [
      {"area": "领域1", "weight": 0.3, "rationale": "权重理由"},
      {"area": "领域2", "weight": 0.25, "rationale": "权重理由"},
      {"area": "领域3", "weight": 0.2, "rationale": "权重理由"}
    ],
    "deliverables": ["交付物1", "交付物2"],
    "constraints": ["约束1", "约束2"],
    "success_criteria": ["成功标准1", "成功标准2"]
  }
}
```

**Prompt要点**:
- 提取需求核心要点
- 识别关键领域和权重
- 定义明确的交付标准
- 识别潜在风险和约束

### 3.3 Stage 3: 评审组（3个Agent）
**注意**: 原 Stage 2 现调整为 Stage 3

#### 2.1 完备性评审Agent

**角色**: 完备性检查员
**超时**: 5分钟
**Search**: 启用（验证需求覆盖度）

**评审维度**:
- 功能需求是否全覆盖
- 非功能需求是否考虑
- 边界条件是否明确
- 异常场景是否考虑

**输出**:
```json
{
  "review": {
    "completeness_score": 85,
    "issues": [
      {"level": "P0", "description": "缺少支付安全需求"},
      {"level": "P1", "description": "日志策略不明确"}
    ],
    "recommendations": ["建议补充..."]
  }
}
```

#### 2.2 合理性评审Agent

**角色**: 合理性评估员
**超时**: 5分钟
**Search**: 启用（验证技术可行性）

**评审维度**:
- 技术选型是否合理
- 架构模式是否匹配
- 性能目标是否可达
- 成本预算是否合理

#### 2.3 权重评审Agent

**角色**: 权重优化师
**超时**: 5分钟

**评审维度**:
- 重点领域权重分配
- 资源投入优先级
- 风险与收益平衡

### 3.4 Stage 4: Researchers（研究组）
**注意**: 原 Stage 4 现调整为 Stage 4，增加 Layer 2 约束验证要求

**角色**: 任务规划师（修复版）
**超时**: 5分钟
**修复范围**: 只修P0/P1

**输入**:
- 原任务计划
- 评审意见（P0/P1/P2/P3）

**修复策略**:
- P0: 必须修复（阻塞性问题）
- P1: 建议修复（重要问题）
- P2/P3: 忽略（可在后续阶段处理）

### 3.4 Stage 4: Research组（3个Agent）

#### 4.1 技术方案Research

**角色**: 技术研究员
**超时**: 10分钟
**Search**: 启用

**研究方向**:
- 主流技术栈对比
- 架构模式选择
- 开源方案调研
- 云原生实践

**输出**:
```json
{
  "research": {
    "technology_stack": {
      "recommendation": "推荐方案",
      "alternatives": ["备选1", "备选2"],
      "tradeoffs": "优劣对比"
    },
    "references": [
      {"source": "来源", "url": "链接", "relevance": 0.9}
    ]
  }
}
```

#### 4.2 业界实践Research

**角色**: 行业研究员
**超时**: 10分钟
**Search**: 启用

**研究方向**:
- 同类系统案例
- 大厂最佳实践
- 行业标准参考
- 最新技术趋势

#### 4.3 风险合规Research

**角色**: 风控研究员
**超时**: 10分钟
**Search**: 启用

**研究方向**:
- 安全风险识别
- 合规要求（GDPR/等保等）
- 常见陷阱
- 应急预案

### 3.5 Stage 5: 专家汇总

**角色**: 研究汇总专家
**超时**: 10分钟

**任务**:
- 整合3份Research报告
- 解决冲突观点
- 去重合并
- 形成统一结论

**输出**:
```json
{
  "consolidated_research": {
    "technology_recommendations": "技术建议",
    "industry_insights": "行业洞察",
    "risk_assessment": "风险评估",
    "references": ["引用列表"]
  }
}
```

### 3.6 Stage 6: 审计组（3个Agent）

#### 6.1 架构审计Agent

**角色**: 架构审计师
**超时**: 10分钟
**Search**: 启用

**审计维度**:
- 架构合理性
- 可扩展性
- 可维护性
- 高可用设计

#### 6.2 技术审计Agent

**角色**: 技术审计师
**超时**: 10分钟
**Search**: 启用

**审计维度**:
- 技术可行性
- 性能达标性
- 安全合规性
- 技术债务风险

#### 6.3 成本审计Agent

**角色**: 成本审计师
**超时**: 10分钟
**Search**: 启用

**审计维度**:
- 预算合理性
- ROI分析
- 资源利用率
- 长期运维成本

### 3.7 Stage 7: 专家修复

**角色**: 架构修复专家
**超时**: 10分钟
**修复范围**: 只修P0/P1

**输入**:
- 当前架构方案
- 审计意见

**修复策略**:
- 针对性修复P0/P1问题
- 保留P2/P3作为已知风险

### 3.8 Stage 8: Summary输出

**角色**: 文档工程师
**超时**: 10分钟

**输出格式**:
- 固定模板（共性部分）
- 灵活内容（项目特定）

**模板结构**:
```markdown
# [项目名称] 架构设计方案

## 1. 执行摘要
[固定格式：一句话总结]

## 2. 背景与目标
[灵活内容]

## 3. 架构设计
### 3.1 整体架构
[固定格式：C4模型]

### 3.2 技术选型
[灵活内容]

## 4. 关键设计决策
[灵活内容，含ADR]

## 5. 实施路线图
[固定格式：甘特图/表格]

## 6. 风险评估
[灵活内容]

## 7. 附录
### 7.1 参考资料
[Research引用]

### 7.2 术语表

### 7.3 团队与资源
```

---

## 4. Search配置

### 4.1 Search来源

Solution模块Search配置（基于OpenClaw web_fetch工具）：

```yaml
search_config:
  tool: "web_fetch"  # OpenClaw内置工具
  
  # 每个Agent调用限制
  per_agent_limits:
    max_calls: 3
    timeout_per_call: 30s
    
  # 关键词模板（Agent根据任务填充）
  query_templates:
    technology: "{tech_stack} 最佳实践 2026 site:medium.com OR site:github.com"
    practice: "{company} {scenario} 架构设计案例"
    risk: "{domain} 安全风险 OWASP 2026"
    
  # 来源优先级（用于结果排序）
  source_priority:
    - official_docs      # 官方文档权重最高
    - tech_blogs         # 技术博客
    - github             # 开源项目
    - industry_reports   # Gartner/Forrester等
```

**调用方式**（在Agent Prompt中明确）：
```markdown
## 搜索任务
请使用web_fetch工具搜索以下信息：
1. "{技术栈} 最佳实践 2026"
2. "{架构模式} 大厂案例"
3. "{安全风险} OWASP"

要求：
- 每次搜索返回前3条结果
- 标注来源URL
- 评估可信度（高/中/低）
```

**注意**：不使用Tushare（股票专用API，Solution模块无需财务数据）
    # 内部最佳实践库
```

### 4.2 Search策略

**每Agent每轮Search次数**: 最多3次
**Search关键词生成**: Agent自动提取
**结果验证**: 交叉验证至少2个来源

---

## 5. 质量分级标准

### 5.1 P0（阻塞性）
- 架构方向错误
- 关键技术不可行
- 安全风险极高
- **必须修复**

### 5.2 P1（重要）
- 重要需求遗漏
- 性能目标不可达
- 合规风险
- **建议修复**

### 5.3 P2（一般）
- 优化建议
- 备选方案
- **可选修复**

### 5.4 P3（提示）
- 参考信息
- 改进建议
- **忽略**

---

## 6. 超时与容错

### 6.1 超时配置

| 阶段 | 超时 | 超时处理 |
|:---|:---:|:---|
| Planner | 5分钟 | 使用简化方案继续 |
| 评审组 | 5分钟 | 部分结果+标记超时 |
| Planner修复 | 5分钟 | 原方案+标记未修复 |
| Research | 10分钟 | 部分结果+标记不完整 |
| 专家汇总 | 10分钟 | 简化汇总 |
| 审计组 | 10分钟 | 部分审计+标记超时 |
| 专家修复 | 10分钟 | 原方案+标记未修复 |
| Summary | 10分钟 | 简化输出 |

### 6.2 熔断机制

- 连续3个Agent超时 → 降级为Standard模式
- 关键阶段（Planner/Research）失败 → 终止并报告

---

## 7. 数据流与Blackboard

### 7.1 Blackboard结构

```
blackboard/{session_id}/
├── stage_01_planner/
│   └── task_plan.json
├── stage_02_review/
│   ├── completeness_review.json
│   ├── reasonableness_review.json
│   └── weight_review.json
├── stage_03_planner_fix/
│   └── task_plan_fixed.json
├── stage_04_research/
│   ├── technology_research.json
│   ├── industry_research.json
│   └── risk_research.json
├── stage_05_consolidation/
│   └── consolidated_research.json
├── stage_06_audit/
│   ├── architecture_audit.json
│   ├── technology_audit.json
│   └── cost_audit.json
├── stage_07_fix/
│   └── architecture_fixed.json
├── stage_08_summary/
│   └── final_document.md
└── execution_log.json
```

### 7.2 数据传递

- 每个Stage读取上一个Stage的输出
- 中间结果持久化到Blackboard
- 支持中断恢复

---

## 8. 与现有架构集成

### 8.1 复用组件

| 组件 | 来源 | 复用方式 |
|:---|:---|:---|
| SolutionExecutor | 本次重构 | 扩展支持Pro模式 |
| SolutionOrchestratorV3 | 现有 | Planner阶段使用 |
| BlackboardManager | 现有 | 统一存储 |
| Search模块 | Investment | 移植并扩展 |

### 8.2 新增组件

- ProModePipeline: Pro模式专用管线
- ReviewAgent: 评审专用Agent
- ResearchAgent: 研究专用Agent
- AuditAgent: 审计专用Agent

---

## 9. 待决策事项

| 事项 | 建议 | 状态 |
|:---|:---|:---:|
| Search具体实现 | 复用Investment search模块 | 待确认 |
| 固定模板详细设计 | 需单独设计文档 | 待开发 |
| 成本预估功能 | 可选增强 | 待评估 |
| 可视化输出 | 架构图自动生成 | 待评估 |

---

## 10. 验收标准

### 10.1 功能验收

- [ ] 8阶段流程完整执行
- [ ] 最多6 Agent并发控制
- [ ] Search功能正常
- [ ] P0/P1修复闭环
- [ ] 固定模板输出

### 10.2 质量验收

- [ ] 复杂需求（如银行核心系统）输出质量达标
- [ ] 与Investment模块输出质量对比不逊色
- [ ] 用户满意度>90%

### 10.3 性能验收

- [ ] 总执行时间<90分钟（含超时容错）
- [ ] 单阶段超时率<10%
- [ ] 内存占用<4GB

---

## 附录A: 参考文档

- Investment模块设计: `domains/investment/`
- Solution V3重构: `memory/2026-04-28.md`
- 安全机制: `.deepflow/docs/CAGE_PREREQUISITE_BANS.md`

## 附录B: 术语表

| 术语 | 说明 |
|:---|:---|
| Pro模式 | 高质量、多Agent、带Search的深度分析模式 |
| P0/P1/P2/P3 | 问题分级标准 |
| ADR | Architecture Decision Record 架构决策记录 |
| C4模型 | 上下文/容器/组件/代码四级架构图 |

---

**文档版本历史**:
| 版本 | 日期 | 修改 | 作者 |
|:---|:---|:---|:---|
| v1.0 | 2026-04-28 | 初始版本 | 小满 |
