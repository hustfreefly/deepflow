# Ship Pro V2 — LLM 引导 + 确定性编译 + 质量门禁

> **版本**: V2.0 | **日期**: 2026-06-15 | **状态**: ✅ 已验证

---

## 设计背景

### V1 的问题
Ship Pro V1 的编译器（decomposer.py）存在 5 个 bug：
1. AC 空泛（66% 含"功能实现完成"等模板文本）
2. Constraints 模板化（7 个 WP 只有 1 种 constraint）
3. Deliverables 模板化（只有 2 种模式）
4. 数据层依赖缺失（5 个 WP 未依赖数据层）
5. verification_method 单一

### V1.5 尝试（泛化模式匹配）
尝试用通用结构特征（数字+量词、公式、流程箭头等）替代硬编码模板。
- **结果**：5 个 bug 全部修复，两个不同领域验证通过
- **问题**：本质仍是穷举，只是粒度更通用。换领域可能失效
- **用户洞察**：「你这个泛化性其实还是穷举，只是泛化性比较高的穷举」

### V2 突破（用户提出的核心思路）
用户提出：**让 LLM 先读 Blueprint 输出领域关键词，编译器消费 LLM 的理解结果**

这从根本上解决了泛化性问题：
- LLM 理解任何领域的 Blueprint → 输出结构化领域知识
- 编译器零硬编码 → 纯粹的数据映射引擎
- 换任何领域都能工作

---

## 架构总览

```
Phase 1: LLM 预扫描（~30s）
  Blueprint → LLM Pre-Scanner → domain_config.json
  职责：LLM 理解领域语义，输出结构化关键词

Phase 2: 确定性编译（~1s）
  Blueprint + domain_config.json → Compiler → Ship Package
  职责：数据驱动分解，所有模式/关键词来自预扫描

Phase 3: LLM 质量门禁（~30s，最多2轮）
  Ship Package → Reviewer(2项检查) → Fixer → Harness
  职责：语义级兜底，捕获编译器遗漏的问题
```

### 3 级降级策略

```
Level 1: 重试（最多 1 次，带错误反馈）
Level 2: 简化版预扫描（仅 AC + 依赖）
Level 3: 回退 V1 模式匹配（标记 engine: ship_pro_v1_fallback）
```

---

## 文件清单

| 文件 | 大小 | 角色 |
|------|------|------|
| `prompts/ship_pre_scanner.md` | 5.7 KB | LLM 预扫描 Prompt（6步 CoT） |
| `prompts/ship_reviewer.md` | 3.1 KB | Reviewer Prompt（2项检查） |
| `prompts/ship_fixer.md` | 3.0 KB | Fixer Prompt（原子写入） |
| `prompts/ship_harness.md` | 3.7 KB | Harness Prompt（防幻觉+降级） |
| `decomposer.py` | 15.6 KB | 数据驱动编译器（零硬编码） |
| `SKILL.md` | 12.3 KB | Agent 执行指南（V2 流程） |
| `scripts/extract_module_ids.py` | 1.7 KB | 模块 ID 提取 |
| `scripts/validate_domain_config.py` | 6.6 KB | domain_config 语义校验 |
| `scripts/ship_qg_orchestrator.py` | 4.6 KB | QG 控制脚本 |
| `scripts/extract_ship_review_data.py` | 9.5 KB | 审查数据提取 |

---

## domain_config.json Schema

```json
{
  "schema_version": "1.0",
  "project_summary": "一句话概述",
  "overall_confidence": "high|medium|low",
  "work_package_profiles": [
    {
      "module_id": "COMP-XX",
      "module_name": "模块名",
      "confidence": "high|medium|low",
      "suggested_ac": ["可验证的AC..."],
      "suggested_deliverables": ["具体交付物..."],
      "suggested_constraints": ["具体约束..."],
      "is_infrastructure": false,
      "infrastructure_reason": ""
    }
  ],
  "dependency_hints": [
    {"from": "COMP-XX", "to": "COMP-YY", "reason": "..."}
  ],
  "compilation_order": ["COMP-XX", ...],
  "derived_requirements": [...],
  "derived_risks": [...],
  "_metadata": {
    "blueprint_module_count": N,
    "modules_with_rich_summary": N,
    "data_flow_analysis": "..."
  }
}
```

### 语义校验项（validate_domain_config.py）
1. JSON Schema 格式校验
2. module_id 存在于 Blueprint 中（enum 约束）
3. dependency_hints 的 from/to 合法
4. 拓扑排序验证（无循环依赖）
5. 模块覆盖率（所有 Blueprint 模块都有 profile）
6. compilation_order 与 dependency_hints 一致性

---

## 端到端验证结果

### Serenity 场景（金融 Skills 迁移，7 模块）

| 指标 | V1 原始 | V1.5 泛化 | V2 LLM引导 |
|------|---------|----------|------------|
| AC 空泛率 | 66% | 0% | **0%** |
| Constraints 种类 | 1 | 5 | **14** |
| Deliverables 种类 | 2 | 8 | **22** |
| 依赖正确性 | 5 缺失 | 全正确 | **全正确+多层** |
| Requirements 覆盖 | 部分空 | 全有 | **全有+3推导** |

### 跨境AI 场景（API 网关平台，6 模块）

| 指标 | V1 原始 | V1.5 泛化 | 备注 |
|------|---------|----------|------|
| AC 空泛率 | 66% | 0% | V2 未跑（无 end-to-end） |
| Constraints 种类 | 1 | 5 | — |
| Deliverables 种类 | 2 | 2→8 | 泛化改进 |

### V2 Deliverables 质量对比

```
V1 模式匹配: "serenity-method 核心实现", "单元测试"
V2 LLM 引导: "9步研究工作流端到端测试", "bottleneck_score 计算验证脚本",
             "OpenClaw Skill 格式兼容性测试"

V1 模式匹配: "gf-dma-health-index 核心实现"
V2 LLM 引导: "HealthScore 四维度计算验证", "T+1/涨跌停板 DMA 适配测试",
             "数据泄露检测测试"
```

---

## 专家评审记录

### V1 评审（3 路专家，2026-06-14）
- **Prompt 专家**：16 项发现，4 个 P0
- **架构专家**：16 项发现，4 个 P0
- **领域专家**：17 个问题的根因分类（47% 编译器 bug / 35% Solution Pro / 18% QG）

### V2 评审（3 路专家，2026-06-15）
- **架构专家**：3 个 P0（Phase 边界模糊 / 容错缺失 / QG 简化过度）→ 全部已修复
- **Pre-Scanner 专家**：3 个 P0（Schema 校验 / data_flows 缺失 / 模块 ID 枚举）→ 全部已修复
- **泛化性专家**：3 个 P0（prompt 未公开 / 语义校验 / summary fallback）→ 全部已修复

### 评审报告位置
```
blackboard/Serenity_Skills_迁移到_architecture_7b1e7f39/
├── review_ship_qg_prompt.md        # V1 Prompt 评审
├── review_ship_qg_architecture.md  # V1 架构评审
├── review_ship_qg_domain.md        # V1 领域评审
├── review_v2_architecture.md       # V2 架构评审
├── review_v2_prescanner.md         # V2 Pre-Scanner 评审
└── review_v2_generalization.md     # V2 泛化性评审
```

---

## 设计决策记录

### D1: LLM 预扫描 vs 模式匹配
- **决策**：采用 LLM 预扫描
- **理由**：模式匹配本质是穷举，无法真正泛化。LLM 理解语义，编译器消费理解结果
- **代价**：新增 1 次 LLM 调用（~30s），但 QG 简化后净调用次数持平

### D2: 3 级降级策略
- **决策**：重试 → 简化版 → 回退 V1
- **理由**：确保 pipeline 永远不会因预扫描失败而完全失败
- **来源**：V2 架构专家 P0 建议

### D3: QG 从 4 项检查简化到 2 项
- **决策**：保留 AC 质量 + 依赖合理性，移除空泛检测和 WP 分解合理性
- **理由**：预扫描已处理 WP 分解和设计-执行一致性
- **风险**：如果预扫描生成了空泛 AC，QG 仍能捕获（保留的 AC 质量检查）

### D4: domain_config.json 语义校验
- **决策**：在编译器消费前做 6 项语义校验
- **理由**：防止 LLM 幻觉（虚构 module_id / 循环依赖）传播到编译器
- **来源**：V2 Pre-Scanner 专家 P0 建议

### D5: 编译器零硬编码
- **决策**：decomposer.py 不包含任何领域关键词或模式匹配
- **理由**：所有领域知识来自 domain_config.json，编译器是纯粹的数据映射引擎
- **验证**：grep 确认无 "功能实现完成"、"_SUMMARY_PATTERNS" 等 V1 代码残留

---

## 已知限制

1. **Blueprint 数据稀疏**：两个实际 Blueprint 中 data_flows、responsibilities、module_boundaries 等字段全空。Pre-Scanner 实质上只能从"模块名 + summary"推导
2. **30+ 模块未验证**：LLM 单次调用的 token 预算可能不足，需要分层预扫描
3. **非软件领域未验证**：Schema 字段名（module_id, work_package_profiles）隐含软件工程假设
4. **V2 端到端仅验证 1 个场景**：跨境AI 场景尚未跑 V2 全流程

---

*V2.0 | 2026-06-15 | LLM 引导 + 确定性编译 + 质量门禁*
