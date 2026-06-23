# Solution模块设计文档（V3.0）

> **版本**: v3.0  
> **日期**: 2026-04-28  
> **状态**: 设计中  
> **目标**: 通用解决方案设计模块，支持 Standard/Rigorous 两种模式

---

## 1. 模块定位

### 1.1 三种模式

| 模式 | 适用场景 | 执行时间 | Agent数 | 特点 |
|:---|:---|:---:|:---:|:---|
| **Standard** | 一般架构设计 | 10-15分钟 | 8-10个 | 平衡质量与时效，完整10阶段 |
| **Rigorous** | 复杂企业级方案 | 20-30分钟 | 12+个 | 深度研究、Harness V2 质量保障 |

> ⚠️ Quick 模式已删除（2026-05），所有运行都使用完整 10 阶段 Harness V2 管线。详见 `domains/solution_pro/orchestrator_agent.py:258`。

### 1.2 输入模式

- **用户提供**: 完备的需求文档（非主动搜集）
- **可选提取**: 前缀（用于session命名）
- **约束条件**: 可选（预算、周期、合规等）
- **利益相关者**: 可选

---

## 2. 整体架构

### 2.1 架构层次

```
┌─────────────────────────────────────────────────────────────┐
│  主Agent（depth-0）                                          │
│  └─ sessions_spawn → SolutionExecutor Agent                  │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  SolutionExecutor（depth-1）                                 │
│  ├─ 模式选择（Standard/Rigorous）—— Quick 已删除，所有模式走完整10阶段
│  ├─ Agent调度（动态选择Agent组合）                          │
│  └─ sessions_spawn → Workers（depth-2）                     │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  Workers（depth-2）                                          │
│  └─ 真实执行 + Blackboard写入                               │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 核心组件

| 组件 | 职责 | 文件 |
|:---|:---|:---|
| **SolutionOrchestratorV21** | 入口、10阶段管线调度 | `domains/solution_pro/orchestrator_agent.py` |
| **TaskBuilder** | 动态任务构建 | `domains/solution_pro/task_builder.py` |
| **HarnessV2OrchestratorHelper** | 两阶段执行、约束传递、验证闭环 | `domains/solution_pro/orchestrator_v21_harness.py` |
| **Harness Scorer** | 质量评分（完整性+适度性） | `domains/solution_pro/harness_scorer.py` |
| **Blackboard** | 数据持久化、跨阶段状态共享 | `core/blackboard_manager.py` |
| **PromptRegistry** | Prompt 统一注册管理 | `core/prompt_registry.py` |

---

## 3. Pro模式详细设计（V2.1 - Harness V2）

### 3.1 10阶段流程

```
Stage 1: Data Collection（数据收集，3分钟）
    ├─ 输入：任务主题、约束条件
    ├─ 执行：Web搜索收集行业信息、成本参考、实施案例
    ├─ 输出：data_collection.json
    └─ 写入：Blackboard/data/collection.json

Stage 2: Planning（规划，5分钟）
    ├─ 输入：需求文档 + Data Collection 结果
    ├─ 分析：任务特征、复杂度、关键领域
    ├─ 输出：任务计划 + 动态Agent选择 + Layer 2 约束
    └─ 写入：Blackboard/stages/planning.json

Stage 3: Reviewers（评审组并行，3 Agent，5分钟）
    ├─ Technical Reviewer：技术架构评审
    ├─ Business Reviewer：商业价值评审
    ├─ Risk Reviewer：风险评估
    └─ 输出：评审意见（PASS/WARNING/BLOCK）

Stage 4: Researchers（研究组并行，3-4 Agent，10分钟）
    ├─ 多领域深度研究
    ├─ 带 Layer 2 约束验证（verification_checklist）
    ├─ 输出：研究报告（含约束验证结果）
    └─ 写入：Blackboard/stages/research_*.json

Stage 5: Consolidator（成果整合，5分钟）
    ├─ 整合 Reviewers + Researchers 输出
    ├─ 形成统一架构设计方案
    └─ 输出：consolidator.json

Stage 6: Audit（审计，5分钟）
    ├─ 可行性审计
    ├─ 风险审计
    ├─ 完整性审计
    ├─ 安全审计
    └─ 输出：审计意见

Stage 7: Fix（修正，5分钟）
    ├─ 根据审计意见修正方案
    └─ 输出：fix.json

Stage 8: Fixer Expert（深度修正，5分钟）
    ├─ 处理 Critical/Major 问题
    └─ 输出：fixer_expert.json

Stage 9: Harness V2 Final（最终质量门禁，3分钟）
    ├─ 完整性评分（60%权重）
    ├─ 适度性评分（40%权重）
    ├─ 阈值：≥0.85 PASS，<0.70 BLOCK
    └─ 输出：harness_final.json

Stage 10: Summarizer（最终总结，5分钟）
    ├─ 生成最终方案文档（Markdown）
    ├─ 整合全流程输出
    └─ 输出：final_report.md
```

### 3.2 Layer 2 约束验证机制

**核心设计**: Planning 阶段动态生成约束，Researcher 阶段显式验证

**流程**:
```
Planning (Stage 2)
  ├─ 生成 layer2_constraints
  │   ├─ reviewer: {constraints: [...]}
  │   ├─ researcher: {constraints: [...]}
  │   └─ consolidator: {constraints: [...]}
  └─ 写入 Blackboard/stages/planning.json
           ↓
HarnessV2OrchestratorHelper
  ├─ read_layer2_constraints()
  └─ 注入到后续 Worker Task
           ↓
Researchers (Stage 4)
  ├─ 接收 layer2_constraints
  ├─ 执行研究任务
  └─ 输出 verification_checklist
     {
       "C1": {
         "constraint": "必须调研国产AGV价格",
         "satisfied": true,
         "evidence": "海康8-10万/台..."
       }
     }
```

### 3.2 并发控制

**最大并发**：8个Agent

**并发分配**:
- Stage 3（Reviewers）: 3个并行
- Stage 4（Researchers）: 3-4个并行
- Stage 6（Audit）: 串行（4维度审计）
- 其他阶段：串行

**Harness V2 两阶段执行**:
```python
# Phase 1: Planning 先执行
planning_task = build_planner_task(...)
# spawn planning worker → 写入 Layer 2 约束

# Phase 2: 读取约束，构建其他任务
layer2_constraints = helper.read_layer2_constraints()
phase2_tasks = helper.build_phase2_tasks(
    ..., 
    layer2_constraints=layer2_constraints  # 注入约束
)
```

**实现**:
```python
MAX_CONCURRENT_AGENTS = 6
semaphore = asyncio.Semaphore(MAX_CONCURRENT_AGENTS)
```

---

## 4. Agent库设计

### 4.1 Agent分类

```yaml
agent_library:
  review_agents:
    - id: completeness_reviewer
      name: 完备性评审
      focus: [功能完整性, 非功能需求, 边界条件]
      
    - id: reasonableness_reviewer
      name: 合理性评审
      focus: [技术可行性, 架构匹配度, 成本合理性]
      
    - id: weight_reviewer
      name: 权重评审
      focus: [重点领域权重, 资源分配, 优先级]

  research_agents:
    - id: technology_researcher
      name: 技术方案研究
      search_focus: [技术栈, 架构模式, 开源方案]
      
    - id: practice_researcher
      name: 业界实践研究
      search_focus: [大厂案例, 最佳实践, 行业标准]
      
    - id: risk_researcher
      name: 风险合规研究
      search_focus: [安全风险, 合规要求, 常见陷阱]

  audit_agents:
    - id: architecture_auditor
      name: 架构审计
      focus: [架构合理性, 可扩展性, 高可用性]
      
    - id: technology_auditor
      name: 技术审计
      focus: [技术可行性, 性能达标性, 安全合规性]
      
    - id: cost_auditor
      name: 成本审计
      focus: [预算合理性, ROI, 运维成本]

  expert_agents:
    - id: research_consolidator
      name: 研究汇总专家
      
    - id: fix_expert
      name: 修复专家
      
    - id: summary_writer
      name: 文档工程师
```

### 4.2 Planner元调度

**Planner职责**:
1. 分析任务特征
2. 从Agent库选择合适的Agent组合（3-6个）
3. 为每个Agent确定focus和约束
4. 生成动态任务计划

**示例**:
```python
# 电商平台架构设计
planner.select_agents({
    "stage_02_review": [
        {"agent": "completeness_reviewer", "focus": ["全球化", "高并发"]},
        {"agent": "reasonableness_reviewer", "focus": ["微服务", "云原生"]},
        {"agent": "weight_reviewer", "focus": ["性能", "成本平衡"]}
    ],
    "stage_04_research": [
        {"agent": "technology_researcher", "search": ["微服务框架对比"]},
        {"agent": "practice_researcher", "search": ["亚马逊/阿里架构"]},
        {"agent": "risk_researcher", "search": ["支付安全", "数据合规"]}
    ]
})
```

---

## 5. Harness设计

### 5.1 Harness定位

**位置**: Stage 3和Stage 7的修复环节内嵌

**双重职责**:
1. **质量检查**: 修复是否完整、是否引入新问题
2. **防发散检查**: 是否over design、是否偏离需求

### 5.2 Stage 3 Harness - ScopeGuard

**质量检查**:
- P0修复率 ≥ 100%
- P1修复率 ≥ 80%
- 无新增P0

**防发散检查**:
```yaml
scope_guard:
  # 范围约束
  - check: 是否引入计划外新功能
    action: 标记发散，要求回退
    
  # 复杂度约束
  - check: 技术方案是否超出需求
    example: 
      - 简单电商 → 微服务+K8s = 过度设计
      - 日活100万 → 单体+Redis = 合理
      
  # 资源约束
  - check: 是否符合预算/周期
    action: 超出则标记风险
```

### 5.3 Stage 7 Harness - PragmaticGuard

**质量检查**:
- P0/P1全部修复
- 修复方案可执行

**防发散检查**:
```yaml
pragmatic_guard:
  # 架构一致性
  - check: 修复是否保持架构一致性
    
  # 技术债务
  - check: 修复是否引入技术债务
    
  # 可维护性
  - check: 修复方案是否易于维护
    counter_example: [临时补丁, 硬编码, 魔法数字]
    
  # 业务价值
  - check: P2/P3是否被当成P0/P1修复
    action: 标记资源浪费
```

### 5.4 Harness输出

```json
{
  "harness_check": {
    "stage": "planner_fix",
    "quality": {
      "P0_resolved": 3,
      "P1_resolved": 2,
      "score": 85,
      "status": "pass"
    },
    "scope": {
      "new_features_added": 0,
      "complexity_match": "fit",
      "budget_fit": true,
      "recommendation": "pass"
    }
  }
}
```

---

## 6. 与OpenClaw架构兼容性

### 6.1 兼容点

| 机制 | 状态 | 说明 |
|:---|:---:|:---|
| sessions_spawn | ✅ | 完全兼容，两层spawn架构 |
| sessions_yield | ✅ | 完全兼容 |
| Blackboard | ✅ | 复用现有实现 |
| asyncio.Semaphore | ✅ | Python原生，无需OpenClaw支持 |

### 6.2 实现策略

**简化版Harness**（当前设计）:
- Harness作为修复Agent内部逻辑
- 不增加新Agent
- 不增加通信机制
- **100%兼容**

**过程监控Harness**（未来可选）:
- 需要OpenClaw支持Agent间消息
- 或：Blackboard轮询机制
- **当前不采用**

---

## 7. 验收标准

### 7.1 功能验收

- [ ] Standard 模式完整执行（原 Quick/Standard/Pro 合并为 Standard/Rigorous）
- [ ] Planner动态Agent选择
- [ ] Harness质量+防发散检查
- [ ] Agent库配置化
- [ ] Search集成（复用Investment）

### 7.2 质量验收

- [ ] Pro模式输出质量达到Investment水平
- [ ] Harness有效拦截过度设计
- [ ] 复杂方案（银行/电商）验收通过

### 7.3 性能验收

- [ ] Standard 模式 ≤ 15分钟（原 Quick 模式已删除）
- [ ] Standard模式 ≤ 15分钟
- [ ] Pro模式 ≤ 90分钟（含容错）

---

## 8. 核心设计细节

### 8.1 复用组件

| 组件 | 来源 | 复用方式 | 具体实现 |
|:---|:---|:---|:---|
| **SolutionExecutor** | 本次重构 | 扩展支持Pro模式 | 新增Pro模式分支，调用ProPipeline |
| **SolutionOrchestratorV3** | 现有 | Planner阶段使用 | 复用get_tasks()方法，扩展Agent选择逻辑 |
| **BlackboardManager** | 现有 | 统一存储 | 复用write/read方法，路径：`blackboard/{session_id}/` |
| **web_fetch工具** | OpenClaw | Search替代方案 | Agent通过Prompt指令使用，非代码import |

### 8.2 待决策事项

| 事项 | 建议 | 状态 |
|:---|:---|:---:|
| Search具体实现 | 使用OpenClaw web_fetch工具（见SOLUTION_PRO_MODE_DESIGN.md第4节） | 已明确 |
| 固定模板详细设计 | 需单独设计文档 | 待开发 |
| Agent库完整配置 | 需填充20+ Agent详细配置 | 待开发 |

---

## 附录：参考文档

- Investment模块: `domains/investment/`
- 安全机制: `.deepflow/docs/CAGE_PREREQUISITE_BANS.md`
- 原Pro模式设计: `.deepflow/docs/SOLUTION_PRO_MODE_DESIGN.md`

---

**文档版本历史**:
| 版本 | 日期 | 修改 | 作者 |
|:---|:---|:---|:---|
| v3.0 | 2026-04-28 | 整合Pro模式、Harness、Agent库设计 | 小满 |
