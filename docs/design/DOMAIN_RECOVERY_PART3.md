# DeepFlow 按功能模块开发恢复手册 — Part 3: Spec Pro

---

## 3. Spec Pro（需求收集管线）

### 3.1 概述

苏格拉底式多轮对话，帮助用户梳理和结构化需求。产出 Living Spec，供 Solution Pro 等下游引擎消费。

核心架构: 主Agent → SpecProOrchestrator(depth-1) → Workers(depth-2)
对话范式: 苏格拉底六类问题 + 推断-验证机制
质量保障: 四层Harness (Input Guard / Process Guard / Output Guard / Safety Valve)

### 3.2 修改文件（10个）

| 文件 | 改动摘要 |
|:---|:---|
| coordinator.py | constraints权重分配变更：budget/timeline → platform/tech_stack/data_source |
| eval/harness.py | SemanticGate门控逻辑调整；SC4→SC5检查方法重命名 |
| merge_spec.py | success_metrics归一化逻辑：字符串→追加合并 |
| requirement_structuring.py | annotation prompt构建逻辑修改 |
| prompts/assess.md | constraints评分标准：budget/timeline → platform/tech_stack/data_source |
| prompts/guide.md | 需求问题列表微调 |
| prompts/parse.md | 新增Step 0概念确认（规则驱动）：专有名词提取 |
| prompts/parse_response.md | constraints字段结构：budget/timeline/tech_stack → platform/tech_stack[]/data_source |
| prompts/structure.md | 评分标准和展示格式更新 |
| QUALITY_GUIDE.md | 新增"Living Spec 数据结构参考"章节 |

### 3.3 关键决策

#### D1: Constraints字段重构（6/20）

旧字段: budget, timeline, tech_stack
新字段: platform, tech_stack(数组), data_source

原因: "资源导向"转向"约束导向"的评分体系。budget/timeline对AI项目约束力弱，platform/tech_stack/data_source更有实际指导意义。

影响: coordinator.py + prompts/assess.md + prompts/parse_response.md + prompts/structure.md

#### D2: AssessGuideWorker合并（6/3完成，已验证）

AssessWorker(质量评分) + QuestionWorker(问题生成) → AssessGuideWorker
管线步骤从5步→4步，LLM调用从3次/轮→2次/轮，省30-60s/轮

改动文件:
- prompts/assess_guide.md — 新建，Phase 1评分 + Phase 2提问
- coordinator.py — collecting管线更新
- worker_fallback.py — assess_guide双文件fallback

全部验证通过 ✅

#### D3: Parse Step 0概念理解（6/20）

新增Step 0: 专有名词提取（规则驱动），在LLM解析前先提取领域术语
目的: 让后续轮次能正确使用领域术语，减少误解

#### D4: Spec Pro V4.1修正（6/19）

问题: 禁止问题清单与评分规则存在内部矛盾（禁止问"技术栈"但技术栈约束占30分）
修复: 
- 从"资源导向"转向"约束导向"评分体系
- Step 0概念理解步骤保留但改进（限制搜索数量）
- 修复禁止问题清单的内部矛盾

#### D5: frozen_spec V2.0修复（6/3）

三个结构性遗漏修复，信息保留率从<5%提升到~100%:
1. constraints全量遍历（从硬编码3个key→遍历confirmed_constraints.items()）
2. guardrails.resolved提取（设计决策）
3. inferred提取（AI推断）

改动: frozen_spec.py一个文件，16行新增代码

### 3.4 Spec Pro→Solution Pro链路

| 文件 | 说明 |
|:---|:---|
| docs/design/spec_pro_to_solution_pro_link_upgrade.md | 链路升级设计 |
| docs/design/spec_solution_link_v2.md | 链路V2设计 |

### 3.5 待办

- [ ] constraints新字段(platform/tech_stack/data_source)验证覆盖所有prompt
- [ ] Step 0专有名词提取的可靠性测试
- [ ] V4.1禁止问题清单与评分规则一致性验证
