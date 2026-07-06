# DeepFlow 2.1.0 AI Native 合规诊断报告

> 诊断范围：Week 1 目标文件中硬编码语义判断、状态机硬编码、计数/字段完整性检查、阈值判断，以及缺少 Layer 2 LLM-as-Judge 的位置。
> 诊断原则：基于 AGENTS.md Zone 4（AI Native Execution）——LLM 做判断，代码做格式；禁止硬编码语义判断；判断类任务需至少 2 个独立 Agent 视角。

---

## 1. 违规总览

| 文件 | 违规数量 | 主要问题类别 | 严重度 |
|------|----------|--------------|--------|
| `domains/solution_pro/convergence_layer.py` | 8 | 硬编码评分/阈值、keyword-in-text、缺少 Layer 2 | 高 |
| `domains/solution_pro/ai_native_auditor.py` | 5 | 硬编码审计维度、阈值、扣分规则 | 高 |
| `domains/solution_pro/harness_scorer.py` | 7 | 硬编码权重/阈值、硬编码映射、fallback 规则判定 | 高 |
| `domains/solution_pro/information_conservation.py` | 7 | 硬编码阈值、字符串覆盖检查、keyword-in-text | 高 |
| `domains/spec_pro/coordinator.py` | 4 | 状态机硬编码、阈值硬编码、评分规则硬编码 | 中 |
| `domains/spec_pro/process_guard.py` | 4 | 状态机硬编码阈值、硬编码异常规则 | 中 |
| `domains/ship_pro/orchestrator/ship_orchestrator.py` | 7 | 字段完整性硬编码、计数阈值、regex 提取 | 高 |
| `domains/research_pro/orchestrator.py` | 5 | 阈值硬编码、完成标准硬编码、报告 section 硬编码 | 中 |
| `domains/research_pro/citation_verifier.py` | 2 | regex 提取、硬编码 trust_score 阈值 | 中 |
| `domains/research_pro/tier_classifier.py` | 3 | 硬编码域名分类、权重映射 | 中 |

**总计：52 项违规**

---

## 2. 详细违规清单

### 2.1 `domains/solution_pro/convergence_layer.py`

| 行号 | 问题描述 | 严重度 | 修复方向 |
|------|----------|--------|----------|
| 455-457 | 约束覆盖率阈值硬编码为 0.8（`coverage_rate < 0.8`） | 高 | 从 Gate 配置或 LLM 评估读取动态阈值 |
| 500-588 | `_evaluate_gate_a` 默认权重和阈值硬编码（completeness 0.30 / necessity 0.20 / alignment 0.30 / global_impact 0.20；PASS 0.85 / WARNING 0.70 / CRITICAL 0.60） | 高 | 全部权重/阈值来自 Meta-Planner 配置；删除代码默认值 |
| 590-678 | `_compute_gate_a_scores` 硬编码语义评分规则：约束数量基准 5、验证清单基准 5、MUST/SHOULD/MAY 映射到 necessity、0.75 基础分、alignment 按 covered_req_ids 数量加分、global_impact 按 conservation_status 加分 | 高 | 改为 LLM 直接对 compressed 数据做语义评分；代码只负责 I/O 和加权求和 |
| 680-725 | `_evaluate_gate_a_local` 硬编码阈值判定和特殊规则（ALIGNMENT_CRITICAL 0.60） | 高 | 删除 fallback；强制使用 LLM-as-Judge |
| 797-865 | `_evaluate_check_local` 使用关键词匹配（keyword-in-text）评估 Gate B 检查项：从 check name/description 提取关键词并在 corpus 中匹配 | **极高** | 删除 keyword-in-text；改为 LLM 直接评估 check 与 compressed 数据的语义满足度 |
| 808-830 | `_evaluate_check_via_harness` 调用 spawn_fn 后无法读取结果，直接返回 PASS，缺乏有效 LLM 验证 | 极高 | 实现 Harness Agent 结果读取机制；未返回明确结果时 fallback 到 LLM 重试而非默认 PASS |
| 962-994 | `_compress_outputs` 使用硬编码规则提取 findings/constraints/risks（前 5 个） | 中 | 改为 LLM 语义压缩；代码只负责 Schema 验证 |
| 106-107 | `_check_information_conservation` 只有代码 Layer 1 检查，无 Layer 2 LLM 语义验证 | 高 | 增加 LLM-as-Judge 对信息丢失的语义判断 |

### 2.2 `domains/solution_pro/ai_native_auditor.py`

| 行号 | 问题描述 | 严重度 | 修复方向 |
|------|----------|--------|----------|
| 15-20 | 硬编码审计维度（schema_compliance / expert_coverage / semantic_verification / degradation_risk） | 高 | 维度应由 LLM 根据任务类型动态判断 |
| 22-25 | 分数阈值硬编码（0.8 PASS / 0.5 WARNING / 0.0 FAIL；degraded 扣 0.3） | 高 | 阈值和扣分规则应由配置或 LLM 决定 |
| 15-20 | 各维度评分使用布尔式硬编码（如 `1.0 if planning.get("experts") else 0.0`） | 高 | 改为 LLM 评估语义质量 |
| 11-40 | 整个审计器为单 Agent 代码判定，无独立视角 | 高 | 拆分为两个独立 LLM Judge 投票 |
| 27-33 | recommendations 使用硬编码 if-else 生成 | 中 | 由 LLM 基于维度结果生成 |

### 2.3 `domains/solution_pro/harness_scorer.py`

| 行号 | 问题描述 | 严重度 | 修复方向 |
|------|----------|--------|----------|
| 34-46 | 硬编码权重和阈值常量（WEIGHT_COMPLETENESS 0.30 / THRESHOLD_PASS 0.85 等） | 高 | 完全从外部配置读取；删除硬编码常量 |
| 82-141 | `calculate_harness_score` 使用硬编码权重和阈值 | 高 | 废弃或改为仅做数学计算；语义判断由 LLM 完成 |
| 224-251 | `_generate_improvements` 根据分数区间硬编码改进建议 | 中 | 由 LLM 基于推理生成建议 |
| 254-261 | `level_to_score` 硬编码 high/medium/low 映射 | 中 | 等级转分数应由 LLM 或配置决定 |
| 293-337 | `_validate_harness_output_legacy` 硬编码字段存在性和 decision 值枚举 | 低 | 使用 Pydantic Schema；不要手写枚举 |
| 360-406 | `harness_to_scores` 使用 verdict 到分数的硬编码映射（STRONG_PASS→PASS 等） | 高 | 由 LLM 输出原始分数；不要映射 |
| 426-502 | 第二个 `calculate_harness_score_dynamic` 仍有硬编码默认值（THRESHOLD_PASS 等） | 高 | 删除所有默认值；强制传入配置 |
| 652-674 | `GateALayer2Calibration._rule_based_verdict` 在 llm_judge_fn 缺失时 fallback 到规则判定 | 高 | 删除 fallback；无 LLM Judge 时明确报错而非规则替代 |
| 677-726 | `evaluate_gate_b_critical` 硬编码 80% 通过率 | 高 | 从配置读取；或 LLM 判断是否满足 |

### 2.4 `domains/solution_pro/information_conservation.py`

| 行号 | 问题描述 | 严重度 | 修复方向 |
|------|----------|--------|----------|
| 14-34 | 硬编码 L2/L3 阈值（req_coverage_min 0.9/0.85/0.8 等） | 高 | 从配置读取；按模块动态调整 |
| 60-79 | 权重和分数阈值硬编码（0.35/0.30/0.15/0.20；0.8/0.5） | 高 | 配置化；语义判断是否守恒应由 LLM 完成 |
| 96-100 | `_check_req_coverage` 使用 `_id_in` 字符串包含检查需求覆盖 | 高 | 改为 LLM 语义判断需求是否被覆盖 |
| 104-118 | `_check_constraint_propagation` 使用字符串包含检查约束传播 | 高 | 改为 LLM 语义判断约束是否被传递 |
| 138-198 | `_check_research_utilization` 使用 expert_id 和 finding 关键词在方案文本中匹配 | **极高** | 删除 keyword-in-text；LLM 判断 research finding 是否被利用 |
| 226-296 | `validate_transition` 硬编码 L2/L3 阈值和权重（0.4/0.4/0.2） | 高 | 配置化；增加 LLM 语义验证 |
| 298-300 | `_id_in` 将对象转字符串后做子串匹配 | 极高 | 删除此 helper；使用 LLM 语义匹配 |

### 2.5 `domains/spec_pro/coordinator.py`

| 行号 | 问题描述 | 严重度 | 修复方向 |
|------|----------|--------|----------|
| 73-85 | 硬编码 mode 和 scenario 枚举验证 | 低 | 使用 Pydantic Enum 或配置驱动；当前非语义判断，可接受 |
| 139-146 | 输入长度硬编码限制（5/5000 字符） | 低 | 格式性验证，可保留但建议配置化 |
| 490-533 | `_compute_dynamic_threshold` 硬编码停滞阈值（delta<3 连续 2 轮降 10 分/3 轮降 15 分；最低 50） | 中 | 从配置读取动态参数；停滞语义由 LLM 判断更佳 |
| 700-714 | `_build_v3_round_task` 中硬编码评分规则（"参考业界最优实践"→70 分等） | 高 | 这些语义评分应由 LLM 完成，不应写在代码中 |
| 1173-1176 | 停滞检测条件硬编码（round>=3, delta<3, score>=50） | 中 | 配置化；停滞语义由 LLM 判断 |

### 2.6 `domains/spec_pro/process_guard.py`

| 行号 | 问题描述 | 严重度 | 修复方向 |
|------|----------|--------|----------|
| 26-30 | 硬编码 EXPECTED_DELTA 表 | 中 | 从配置读取；或 LLM 判断进度是否异常 |
| 40-59 | `check_progress_rate` 使用硬编码预期 delta 范围 | 中 | 配置化；异常由 LLM 判断 |
| 62-74 | `check_inference_integrity` 硬编码 3 轮和 0 确认规则 | 中 | 配置化；推断质量由 LLM 判断 |
| 77-100 | `check_conversation_balance` 硬编码 40 分维度差距 | 中 | 配置化；平衡性由 LLM 判断 |

### 2.7 `domains/ship_pro/orchestrator/ship_orchestrator.py`

| 行号 | 问题描述 | 严重度 | 修复方向 |
|------|----------|--------|----------|
| 23-90 | `extract_json_from_completion` 使用 regex 提取 JSON（虽然 JSON 提取是格式任务，但代码尝试修复截断 JSON 并做语义决策） | 中 | JSON 截断修复应保留；但代码不应做“修复成功”的语义判定 |
| 256-290 | `validate_ship_package_structure` 硬编码数量阈值（actual_count < expected_count * 0.8） | 高 | 完整性应由 LLM 语义判断；代码只做 Schema 检查 |
| 278-282 | 硬编码 WP 必需字段（id, title, description） | 低 | Schema 检查，可保留 |
| 718-808 | `validate_all_worker_outputs_l1` 硬编码内容深度检查（desc<100 字符, AC<2, deliverables<1） | 高 | 内容深度是语义判断，应由 LLM Judge 完成；代码只验证字段存在 |
| 993-1000 | `validate_ship_package_v8` 硬编码字段检查 | 低 | Schema 检查，可保留 |
| 1033-1045 | 硬编码 semantic anchors 50% 覆盖阈值 | 高 | 锚点覆盖是否充分应由 LLM 判断 |
| 747-766 | `_build_worker_prompt` 中硬编码最小要求（desc ≥100, AC ≥2, deliverables ≥1） | 中 | 这些是契约要求，但验收时应由 LLM Judge 判断质量而非代码硬性拦截 |
| 130-320 | 整个验证流程缺乏 Layer 2 LLM-as-Judge（L1 后直接判定） | 高 | 每个 Gate 增加 LLM 语义 Judge；合并时采用 Layer 3 综合 |

### 2.8 `domains/research_pro/orchestrator.py`

| 行号 | 问题描述 | 严重度 | 修复方向 |
|------|----------|--------|----------|
| 50-56 | 硬编码常量（DDGS_TIMEOUT 12, QUERY_MIN_LENGTH 10, SUMMARY_MAX_LENGTH 200, MAX_SUBTASKS 20） | 低 | 建议配置化 |
| 68-84 | `_load_completion_criteria` 硬编码完成标准（min_data_sources 3/5, min_tier_1 1/2, min_citations 3/8） | 中 | 配置化；但数量是格式检查，可保留 |
| 1093-1197 | `_evaluate_completion` 大量硬编码阈值（trust_score 0.7, tier_1_ratio 0.3, reachability 0.5, suspect_rate 1.0, max_time_seconds 等） | 高 | 全部从配置读取；语义质量由 LLM 判断 |
| 1147-1156 | 硬编码降级规则触发条件（verified_ratio<0.60, url_reachability<0.50） | 高 | 从配置读取；或 LLM 判断是否需要降级 |
| 1200-1207 | `_missing_report_sections` 硬编码检查 `## {section}` 是否存在 | 中 | Section 存在是格式检查，但语义完整性应由 LLM 判断 |
| 1219-1272 | `_generate_report_draft` 生成硬编码报告模板 | 中 | 报告生成是 LLM 任务，但当前为简化占位，应替换为 LLM 调用 |

### 2.9 `domains/research_pro/citation_verifier.py`

| 行号 | 问题描述 | 严重度 | 修复方向 |
|------|----------|--------|----------|
| 57-59 | 使用 regex 提取 `[N]` 引用标记 | 低 | 格式提取，可保留 |
| 228-234 | 硬编码 trust_score 阈值（0.9 accept / 0.7 review / 否则 reject） | 高 | 阈值配置化；引用质量是否可接受应由 LLM 判断 |
| 138-147 | 无 content_hash 时直接判定 content_mismatch | 中 | 缺失 hash 的处理策略应配置化；但非语义判断 |

### 2.10 `domains/research_pro/tier_classifier.py`

| 行号 | 问题描述 | 严重度 | 修复方向 |
|------|----------|--------|----------|
| 15-20 | 硬编码 TIER_WEIGHTS（tier_1 1.0, tier_2 0.7, tier_3 0.4, unverified 0.5） | 中 | 配置化；来源质量判断可保留代码，但需支持 LLM 辅助 |
| 60-123 | `_load_config` 和 `_bundled_config` 硬编码域名分类 | 中 | 域名分类是固定知识映射，可保留但需支持外部配置覆盖 |
| 125-160 | `classify` 基于硬编码域名列表返回 tier | 中 | 域名分类可代码化；但新域名应通过 LLM 判断或动态学习 |

---

## 3. 缺少 Layer 2 LLM-as-Judge 的位置

以下模块/函数仅有 Layer 1 代码门控，缺少 Layer 2 LLM 语义检查（按 AGENTS.md 4.3，判断类任务必须至少 2 个独立 Agent 视角）：

| 文件/位置 | 当前判定方式 | 风险 | 修复方向 |
|-----------|--------------|------|----------|
| `convergence_layer.py:_evaluate_gate_a` | 代码硬编码计算四维度分数 | 评分与语义脱节 | 增加 LLM 对 compressed 数据的语义评分 |
| `convergence_layer.py:_check_information_conservation` | 代码字符串匹配 | 误判需求/约束覆盖 | 增加 LLM 语义守恒 Judge |
| `convergence_layer.py:_evaluate_check_via_harness` | spawn 后默认 PASS | 虚假通过 | 读取 Harness Agent 结果并做 majority vote |
| `ai_native_auditor.py` | 单代码判定 | 无独立视角 | 改为双 LLM Judge 投票 |
| `harness_scorer.py:calculate_harness_score` | 代码硬编码 | 维度分数缺乏语义 | 用 LLM 输出分数和推理 |
| `information_conservation.py` 全部 | 代码字符串匹配 | 严重误判 | 增加 LLM 语义守恒 Judge |
| `spec_pro/coordinator.py` 评分逻辑 | 代码/规则混合 | 评分标准不统一 | 评分由独立 LLM 完成；coordinator 只做调度 |
| `process_guard.py` 全部 | 代码硬编码 | 异常检测僵化 | 增加 LLM 对轨迹的语义异常判断 |
| `ship_orchestrator.py:validate_ship_package_structure` | 代码计数 | 结构完整≠语义完整 | 增加 LLM 对 ShipPackage 语义的 Judge |
| `ship_orchestrator.py:validate_all_worker_outputs_l1` | 代码硬编码深度检查 | 100 字符/2 条 AC 不能代表质量 | 增加 LLM Judge 判断 WP 语义质量 |
| `research_pro/orchestrator.py:_evaluate_completion` | 代码硬编码阈值 | 完成标准僵化 | 增加 LLM 对报告质量的语义评估 |
| `citation_verifier.py:verify_all` | 代码硬编码 trust_score | 引用质量判断粗糙 | 增加 LLM 对引用与内容一致性的判断 |
| `tier_classifier.py:classify` | 代码硬编码域名 | 新域名无法正确分类 | 新域名走 LLM 判断或 fallback 到通用评估 |

---

## 4. 严重度定义

| 严重度 | 定义 |
|--------|------|
| 极高 | 使用 keyword-in-text / regex 做语义判断，或默认 PASS 导致安全门控失效 |
| 高 | 硬编码阈值/权重/评分规则直接影响质量判定；缺少 Layer 2 LLM-as-Judge |
| 中 | 硬编码阈值/规则影响流程控制，但非核心语义判断 |
| 低 | 格式验证或配置项建议配置化，风险较低 |

---

## 5. 修复优先级建议

### P0（立即修复）
1. `convergence_layer.py:_evaluate_check_local` 删除 keyword-in-text，改为 LLM 语义评估。
2. `convergence_layer.py:_evaluate_check_via_harness` 修复结果读取，禁止默认 PASS。
3. `information_conservation.py:_check_research_utilization` 删除 keyword-in-text，改为 LLM 语义评估。
4. `ai_native_auditor.py` 改为双 LLM Judge 架构。

### P1（本周修复）
1. `convergence_layer.py` Gate A 评分全部改为 LLM 输出。
2. `harness_scorer.py` 删除硬编码权重/阈值默认值。
3. `ship_orchestrator.py` 增加 Layer 2 LLM Judge（WP 质量、ShipPackage 语义完整性）。
4. `research_pro/orchestrator.py` 完成标准阈值配置化；增加 LLM 质量 Judge。

### P2（后续优化）
1. 将所有硬编码阈值迁移到配置或 Meta-Planner 输出。
2. 所有判断类任务默认采用 Layer 2 LLM-as-Judge + Layer 3 综合。
3. `tier_classifier.py` 支持 LLM 新域名分类 fallback。

---

## 6. 结论

DeepFlow 2.1.0 在核心判断路径上仍存在大量硬编码语义判断（评分、阈值、keyword-in-text、if-else 规则），尤其在 Convergence、Information Conservation、AI Native Auditor、Harness Scorer 和 Ship Orchestrator 中。大部分 Gate 只有 Layer 1 代码门控，缺少 Layer 2 LLM-as-Judge。建议按 P0/P1/P2 优先级逐步将语义判断迁移到 LLM，代码只负责格式验证、Schema 校验、调度和 I/O。
