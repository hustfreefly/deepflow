# Ship Pro V3.2 开发计划

> **日期**: 2026-06-18
> **架构**: AI Native 多 Agent 协作（5 Agent + 持续对话反馈闭环）
> **状态**: 待专家评审

---

## 一、开发目标

将 Ship Pro 从"确定性编译器"升级为"AI Native 多 Agent 协作系统"：
- **输入**: Solution Pro 输出的 final_result.json（多种格式）
- **处理**: 5 个 LLM Agent 协作（Architect→Decomposer→Specifier→Packager→Reviewer）
- **输出**: ship_package.json（适配 AI Coding 时代的 WP 结构）

---

## 二、开发阶段

### Phase 1: 基础设施搭建（3-5 天）

#### 1.1 目录结构调整
```
domains/ship_pro/
├── prompts/
│   ├── architect.md          # Architect Agent prompt
│   ├── decomposer.md         # Decomposer Agent prompt
│   ├── specifier.md          # Specifier Agent prompt
│   ├── packager.md           # Packager Agent prompt
│   └── reviewer.md           # Reviewer Agent prompt
├── orchestrator.py           # 5 Agent 编排逻辑
├── blackboard/               # Agent 间数据传递
│   ├── blueprint.json
│   ├── wp_structure.json
│   ├── wp_specs.json
│   ├── review_report.json
│   └── ship_package.json
└── examples/                 # Few-shot 示例
    ├── architect_examples/
    │   ├── format_1_final_result.json
    │   ├── format_1_blueprint.json
    │   ├── format_2_final_result.json
    │   └── format_2_blueprint.json
    └── specifier_examples/
        ├── good_ac.json
        └── bad_ac.json
```

#### 1.2 Prompt 设计（5 个 Agent）

**Architect Agent prompt**
- 核心任务：从任意格式的 final_result 提取统一架构描述
- 输入：final_result.json + requirements_traceability_matrix.json + execution_plan.json
- 输出：blueprint.json
- Few-shot：5 种格式的输入示例 + 对应的 blueprint 输出

**Decomposer Agent prompt**
- 核心任务：模块 → WP 拆分 + 依赖排序
- 输入：blueprint.json
- 输出：wp_structure.json（含 dependencies、priority、complexity）
- 规则：拆分粒度原则、依赖推导规则、优先级判定规则

**Specifier Agent prompt**
- 核心任务：为每个 WP 生成 AC + 技术约束 + 交付物
- 输入：blueprint.json + wp_structure.json
- 输出：wp_specs.json
- 规则："好 AC"和"坏 AC"对比示例、禁止废话规则

**Packager Agent prompt**
- 核心任务：组装 ship_package.json + 生成 summary.md
- 输入：wp_specs.json + blueprint.json + review_report.json
- 输出：ship_package.json + summary.md
- 规则：格式一致性检查、字段完整性验证

**Reviewer Agent prompt**
- 核心任务：审核质量、一致性、可执行性
- 输入：wp_specs.json + blueprint.json
- 输出：review_report.json（结构化反馈，标注 target_agent）
- 规则：审核维度（AC 可验证性、依赖合理性、技术约束完整性）、反馈格式

#### 1.3 编排逻辑设计

```python
# orchestrator.py 核心逻辑

def run_ship_pro(final_result_path: str):
    # Phase 1: 首次执行（全部 spawn）
    architect_key = sessions_spawn(task=architect_prompt, taskName="architect")
    sessions_yield()
    
    decomposer_key = sessions_spawn(task=decomposer_prompt, taskName="decomposer")
    sessions_yield()
    
    specifier_key = sessions_spawn(task=specifier_prompt, taskName="specifier")
    sessions_yield()
    
    packager_key = sessions_spawn(task=packager_prompt, taskName="packager")
    sessions_yield()
    
    reviewer_key = sessions_spawn(task=reviewer_prompt, taskName="reviewer")
    sessions_yield()
    
    # Phase 2: 反馈闭环（全部 sessions_send）
    max_rounds = calculate_max_rounds(token_budget=100000)
    
    for round in range(max_rounds):
        report = read("blackboard/review_report.json")
        
        if report.verdict == "PASS":
            # Packager 组装最终输出
            sessions_send(packager_key, "Reviewer PASS，请组装最终 ship_package.json")
            sessions_yield()
            break
        
        # 解析反馈，确定修改目标
        for issue in report.issues:
            target = issue.target_agent
            target_key = get_agent_key(target)
            sessions_send(target_key, f"请根据以下反馈修改：\n{issue.feedback}")
        
        sessions_yield()
        
        # 要求 Reviewer 重新审核
        sessions_send(reviewer_key, "以下 Agent 已修改，请重新审核")
        sessions_yield()
```

### Phase 2: Prompt 开发 + 单 Agent 测试（5-7 天）

#### 2.1 Architect Agent 开发
- [ ] 设计 prompt（含 5 种格式的 few-shot 示例）
- [ ] 用 3 个真实案例测试（跨境算力中转站、智能简历、电商订单）
- [ ] 评估 blueprint.json 质量（模块识别率、依赖推导准确率）
- [ ] 迭代优化 prompt

#### 2.2 Decomposer Agent 开发
- [ ] 设计 prompt（拆分原则 + 依赖推导规则）
- [ ] 用 3 个 blueprint.json 测试
- [ ] 评估 wp_structure.json 质量（拆分粒度、依赖合理性）
- [ ] 迭代优化 prompt

#### 2.3 Specifier Agent 开发
- [ ] 设计 prompt（"好 AC"vs"坏 AC"对比示例）
- [ ] 用 3 个 wp_structure.json 测试
- [ ] 评估 wp_specs.json 质量（AC 可验证性、技术约束完整性）
- [ ] 迭代优化 prompt

#### 2.4 Packager Agent 开发
- [ ] 设计 prompt（组装规则 + summary 生成规则）
- [ ] 用 3 个完整案例测试
- [ ] 评估 ship_package.json 质量（格式一致性、字段完整性）
- [ ] 迭代优化 prompt

#### 2.5 Reviewer Agent 开发
- [ ] 设计 prompt（审核维度 + 结构化反馈格式）
- [ ] 用 3 个完整案例测试（含故意植入的问题）
- [ ] 评估 review_report.json 质量（问题识别率、反馈精准度）
- [ ] 迭代优化 prompt

### Phase 3: 多 Agent 编排 + 集成测试（3-5 天）

#### 3.1 编排逻辑实现
- [ ] 实现 orchestrator.py（~200 行）
- [ ] 实现 sessionKey 管理
- [ ] 实现 sessions_send 反馈闭环
- [ ] 实现 token 预算管理

#### 3.2 集成测试
- [ ] 端到端测试 1：跨境算力中转站（已有 final_result）
- [ ] 端到端测试 2：智能简历生成系统
- [ ] 端到端测试 3：电商订单系统
- [ ] 评估 ship_package 质量（对比 V1 确定性编译器）
- [ ] 评估反馈闭环效果（修改轮数、修改质量）

### Phase 4: 用户验收 + 迭代优化（2-3 天）

#### 4.1 用户验收
- [ ] 忠礼审核 ship_package 质量
- [ ] 忠礼审核 summary.md 可读性
- [ ] 收集反馈

#### 4.2 迭代优化
- [ ] 根据反馈调整 prompt
- [ ] 优化反馈闭环策略
- [ ] 优化 token 预算管理

---

## 三、关键交付物

### 3.1 代码交付
- `orchestrator.py`：5 Agent 编排逻辑（~200 行）
- `prompts/architect.md`：Architect Agent prompt
- `prompts/decomposer.md`：Decomposer Agent prompt
- `prompts/specifier.md`：Specifier Agent prompt
- `prompts/packager.md`：Packager Agent prompt
- `prompts/reviewer.md`：Reviewer Agent prompt

### 3.2 测试交付
- 3 个端到端测试案例（跨境算力、智能简历、电商订单）
- 测试报告（ship_package 质量评估）

### 3.3 文档交付
- Ship Pro V3.2 架构说明
- Prompt 设计说明
- 用户指南

---

## 四、风险评估

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| Prompt 质量不稳定 | 高 | 中 | Few-shot 示例 + 多轮迭代 |
| sessions_send 反馈效果差 | 低 | 高 | 监控修改轮数，必要时降级为重新 spawn |
| Token 预算超支 | 中 | 中 | 动态预算管理，超支时输出当前最佳结果 |
| Reviewer 和生产 Agent 共谋 | 低 | 中 | 使用不同模型，增加审核维度 |

---

## 五、成功标准

1. **质量**: ship_package 质量 ≥ V1 确定性编译器（忠礼验收）
2. **效率**: 单次执行时间 < 5 分钟（含反馈闭环）
3. **成本**: 单次执行 token < 100K
4. **稳定性**: 3 个测试案例全部通过

---

## 六、时间估算

| 阶段 | 时间 | 累计 |
|------|------|------|
| Phase 1: 基础设施搭建 | 3-5 天 | 3-5 天 |
| Phase 2: Prompt 开发 + 单 Agent 测试 | 5-7 天 | 8-12 天 |
| Phase 3: 多 Agent 编排 + 集成测试 | 3-5 天 | 11-17 天 |
| Phase 4: 用户验收 + 迭代优化 | 2-3 天 | 13-20 天 |
| **总计** | **13-20 天** | — |

---

## 七、下一步行动

1. 让专家评审此开发计划
2. 根据反馈调整计划
3. 开始 Phase 1：基础设施搭建
