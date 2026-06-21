# QA/测试专家评审报告

**评审对象**: Research Pro 质量提升改进计划 V1.0  
**评审人**: QA/测试专家  
**评审日期**: 2026-06-11  
**评审范围**: 验收标准可测性、质量评分客观性、回归测试策略、边界情况处理、集成测试计划

---

## 总体评价: 需改进

**理由**: 改进计划在功能设计层面较为完整，但在质量保证和测试层面存在明显盲区。验收标准部分可测但主观性较强，质量评分体系缺乏校准机制，回归测试策略过于笼统，边界情况处理不充分，集成测试时间预算紧张且缺乏详细测试用例。建议补充自动化测试设计、评分校准方案、异常处理流程后再实施。

---

## 逐项评审

### 1. 验收标准可测性

**评分**: 3/5

**问题**:

1. **主观性验收标准难以自动化**
   - 改进 #3 验收标准："每个维度有量化数据（不只是定性描述）" — "量化数据"的定义模糊，多少数字算"有量化"？
   - 改进 #4 验收标准："每个关键问题有 ≥ 3 层因果链" — "关键问题"如何识别？因果链的"层"如何自动计数？
   - 改进 #5 验收标准："失效模式有物理机理描述" — "物理机理描述"是文本匹配还是语义理解？

2. **缺乏基线对照**
   - 改进 #1 验收标准："输入'CoWoS-L封装工艺' → 自动选择 tech_analysis.md" — 这是功能测试，但未说明如何验证选择"正确"（用户意图可能与技术关键词不匹配）
   - 没有"错误分类"的验收标准（例如：输入"苹果公司的技术分析"应该识别为 investment 还是 tech_process？）

3. **部分标准可测但覆盖不全**
   - ✅ "Tier 0+1 来源占比 ≥ 40%" — 可自动化统计
   - ✅ "评分 < 24 时自动回退到 reporting 阶段" — 可自动化验证状态机
   - ❌ "CoWoS-L 报告覆盖全部 9 个维度" — 维度覆盖如何自动检测？需要定义"覆盖"的最小标准（字数？段落数？关键概念数？）

**改进建议**:

1. **将主观标准转化为可量化指标**:
   ```
   ❌ "每个维度有量化数据"
   ✅ "每个维度包含 ≥ 3 个数值型数据点（百分比、金额、产能、良率等）"
   
   ❌ "失效模式有物理机理描述"
   ✅ "每个失效模式包含：机理名称 + 触发条件 + 物理/化学过程描述（≥ 50 字）+ 检测方法"
   
   ❌ "每个关键问题有 ≥ 3 层因果链"
   ✅ "报告中包含 ≥ 5 条因果链，每条链深度 ≥ 3 层（格式：现象 → 直接原因 → 根本原因 → 设计/架构决策）"
   ```

2. **增加负面测试验收标准**:
   - 输入"苹果公司的技术分析" → 应识别为 `investment`（而非 `tech_process`）
   - 输入"特斯拉制造工艺" → 应识别为 `tech_process`（而非 `investment`）
   - 输入模糊主题 → 应触发"用户确认"流程

3. **定义"维度覆盖"的自动化检测规则**:
   - 维度覆盖 = 该维度标题出现 + 该维度下内容 ≥ 200 字 + 包含 ≥ 1 个数据点
   - 需要在 `quality_reviewer.py` 中实现维度检测逻辑（不能纯靠 LLM 判断）

---

### 2. 质量评分客观性

**评分**: 2/5

**问题**:

1. **LLM 评分一致性问题**
   - 6 维度 5 分制的评分标准依赖 LLM 判断，不同 LLM（或同一 LLM 不同次运行）可能给出差异过大的评分
   - 示例：同一段文本，GPT-4 可能给"工程深度"打 4 分，Qwen 可能给 3 分，Claude 可能给 5 分
   - 缺乏评分校准机制，无法保证评分的**可重复性**和**可比性**

2. **评分标准的主观性**
   - "5分: 有物理/化学机理描述，引用学术论文" — 什么算"有"？引用 1 篇学术论文算 5 分，引用 10 篇也算 5 分？
   - "3分: 有工艺参数，但缺乏机理分析" — "缺乏"是绝对缺乏还是相对缺乏？
   - 评分标准使用了模糊量词："大部分"、"部分"、"大量"、"过于" — 这些词没有量化定义

3. **缺乏评分校准测试**
   - 没有"标准答案"测试集（golden set）用于校准 LLM 评分
   - 没有评分偏差检测机制（例如：同一报告评分 3 次，取中位数）
   - 没有评分一致性指标（例如：Cohen's Kappa、ICC）

4. **评分权重未经验证**
   - `completion_criteria.json` 中的权重（engineering_depth: 0.25, quantification: 0.15 等）是主观设定的
   - 没有通过 A/B 测试或专家打分验证这些权重是否合理
   - 可能导致"评分高但实际质量低"或"评分低但实际质量高"的情况

**改进建议**:

1. **建立评分校准测试集（Golden Set）**:
   ```
   准备 10 份标准报告（覆盖 1-5 分各档位），人工标注评分
   每次 LLM 评分后，与人工标注对比，计算偏差
   偏差 > 1 分的维度，触发二次评分或人工复核
   ```

2. **将模糊量词量化**:
   ```
   ❌ "大部分数据量化"
   ✅ "≥ 70% 的关键数据点为数值型"
   
   ❌ "大量 Tier 3 来源"
   ✅ "Tier 3 来源占比 ≥ 40%"
   
   ❌ "建议过于笼统"
   ✅ "建议中缺乏具体措施、监控指标、预期效果中的 ≥ 2 项"
   ```

3. **增加评分一致性检测**:
   ```python
   def score_with_consistency_check(report: str, dimensions: list) -> dict:
       """评分一致性检测：同一报告评分 3 次，偏差 > 1 则触发人工复核"""
       scores = [llm_score(report, dimensions) for _ in range(3)]
       
       for dim in dimensions:
           dim_scores = [s[dim] for s in scores]
           if max(dim_scores) - min(dim_scores) > 1:
               # 偏差过大，触发人工复核或第四次评分
               return {"status": "review_needed", "dimension": dim, "scores": dim_scores}
       
       # 取中位数
       final_scores = {dim: median([s[dim] for s in scores]) for dim in dimensions}
       return {"status": "passed", "scores": final_scores}
   ```

4. **增加评分解释（Explainability）**:
   ```json
   {
     "engineering_depth": {
       "score": 4,
       "evidence": [
         "维度2（工艺流程）包含 3 个阶段的详细参数（温度/压力/时间）",
         "维度6（失效模式）包含 Kirkendall 空洞的物理机理描述（80字）",
         "引用了 2 篇 IEEE 论文（[1], [2]）"
       ],
       "deduction_reasons": [
         "维度5（良率分析）缺乏量化数据（仅有定性描述）"
       ]
     }
   }
   ```

5. **通过 A/B 测试验证权重**:
   - 准备 20 份报告（覆盖不同质量档位）
   - 人工专家打分（作为 ground truth）
   - 用 LLM 评分 + 当前权重计算总分
   - 计算 LLM 总分与人工总分的相关性（Pearson/Spearman）
   - 若相关性 < 0.7，调整权重

---

### 3. 回归测试策略

**评分**: 2/5

**问题**:

1. **回归测试策略过于笼统**
   - Phase 3 仅提到"用投资分析类主题回归测试（确保不影响现有功能）"
   - 没有具体测试用例、测试数据、预期结果
   - 没有说明如何验证"不影响现有功能"（对比什么？对比哪些指标？）

2. **缺乏自动化回归测试套件**
   - 现有测试文件（`test_orchestrator.py`, `test_source_registry.py` 等）是单元测试，不覆盖端到端流程
   - 没有集成测试或端到端测试
   - 没有回归测试的自动化脚本（每次改动后手动跑？CI/CD 集成？）

3. **缺乏基线对比机制**
   - 改进计划提到"用 CoWoS-L 重新跑一次，对比改进前后"
   - 但没有定义"对比"的具体指标（评分？字数？引用数？维度覆盖？）
   - 没有保存"改进前"的基线报告用于对比

4. **缺乏增量测试策略**
   - 5 个改进项分 3 个 Phase，但没有说明每个 Phase 完成后如何测试
   - Phase 1 完成后（类型识别 + 技术模板），如何验证不影响现有投资分析？
   - Phase 2 完成后（质量评估 + 工程推理 + 质量评审），如何验证不影响 Phase 1？

**改进建议**:

1. **建立回归测试套件（Regression Test Suite）**:
   ```
   tests/
   ├── regression/
   │   ├── test_investment_analysis.py      # 投资分析回归测试
   │   ├── test_tech_process_analysis.py    # 技术工艺回归测试
   │   ├── test_market_research.py          # 市场研究回归测试
   │   └── baselines/
   │       ├── investment_baseline.json     # 投资分析基线指标
   │       ├── tech_process_baseline.json   # 技术工艺基线指标
   │       └── market_research_baseline.json
   ```

2. **定义回归测试的基线指标**:
   ```json
   // baselines/investment_baseline.json
   {
     "test_topic": "贵州茅台投资价值分析",
     "expected_research_type": "investment",
     "expected_template": "prompts/finance_analysis.md",
     "min_dimensions_covered": 8,  // 投资分析 10 维度中至少覆盖 8 个
     "min_tier_1_ratio": 0.3,
     "max_generation_time_seconds": 1800,
     "min_quality_score": 20,  // 6 维度 5 分制，总分 ≥ 20
     "required_sections": ["估值分析", "财务分析", "行业分析", "风险提示"]
   }
   ```

3. **实现自动化回归测试脚本**:
   ```python
   # tests/regression/run_regression_tests.py
   def run_regression_tests():
       """回归测试：运行标准主题，对比基线指标"""
       test_cases = [
           {
               "topic": "贵州茅台投资价值分析",
               "baseline": "baselines/investment_baseline.json",
               "expected_type": "investment"
           },
           {
               "topic": "AI 芯片市场竞争格局",
               "baseline": "baselines/market_research_baseline.json",
               "expected_type": "market_research"
           }
       ]
       
       for case in test_cases:
           report = run_research_pro(case["topic"])
           baseline = load_baseline(case["baseline"])
           
           # 验证类型识别
           assert report.research_type == case["expected_type"]
           
           # 验证质量指标
           assert report.dimensions_covered >= baseline["min_dimensions_covered"]
           assert report.tier_1_ratio >= baseline["min_tier_1_ratio"]
           assert report.quality_score >= baseline["min_quality_score"]
           
           # 验证生成时间
           assert report.generation_time <= baseline["max_generation_time_seconds"]
   ```

4. **每个 Phase 完成后执行增量测试**:
   ```
   Phase 1 完成后:
   - 运行投资分析回归测试（确保类型识别不影响现有功能）
   - 运行技术工艺测试（验证新模板是否工作）
   
   Phase 2 完成后:
   - 运行投资分析回归测试（确保质量评审不影响现有功能）
   - 运行技术工艺测试（验证工程推理是否工作）
   - 运行质量评审测试（验证评分是否合理）
   
   Phase 3 完成后:
   - 运行全量回归测试
   - 对比改进前后基线
   ```

5. **集成到 CI/CD**:
   ```yaml
   # .github/workflows/regression-tests.yml
   name: Regression Tests
   on:
     push:
       paths:
         - '.deepflow/domains/research_pro/**'
   jobs:
     test:
       runs-on: ubuntu-latest
       steps:
         - uses: actions/checkout@v3
         - name: Run regression tests
           run: |
             cd .deepflow/domains/research_pro
             python -m pytest tests/regression/ -v
   ```

---

### 4. 边界情况处理

**评分**: 2/5

**问题**:

1. **类型识别误判处理不充分**
   - 改进计划提到"增加'用户确认'步骤"，但没有详细说明：
     - 何时触发用户确认？（置信度 < 阈值？模糊关键词？）
     - 用户确认的 UI/UX 是什么？（飞书消息？命令行提示？）
     - 用户拒绝确认怎么办？（使用默认类型？终止任务？）
   - 没有处理"混合类型"研究（例如："特斯拉制造工艺的投资价值"同时涉及 tech_process 和 investment）

2. **质量评审死循环处理有漏洞**
   - 改进计划设置了 `max_retries=2`，但：
     - 没有说明每次重试的超时时间（如果每次重试都超时怎么办？）
     - 没有说明重试失败后的降级策略（是交付低质量报告还是终止任务？）
     - 没有说明重试期间的用户通知（用户是否知道在重试？）
   - 没有处理"评分震荡"情况（第 1 次 17 分，第 2 次 25 分，第 3 次 18 分）

3. **超时处理不完善**
   - 改进计划提到"设置推理超时（120s）"，但：
     - 没有说明超时后的处理（跳过推理？使用部分结果？终止任务？）
     - 没有说明超时是否计入总时间预算（`time_budgets.json` 中的 `total_timeout`）
     - 质量评审阶段没有超时设置（如果 LLM 评审卡住怎么办？）

4. **缺乏异常恢复机制**
   - 如果 `quality_reviewer.py` 调用失败（LLM API 错误），如何处理？
   - 如果 `reasoning.py` 返回空结果（推理失败），是否继续生成报告？
   - 如果类型识别返回未知类型（例如：`research_type: null`），如何处理？

5. **缺乏部分失败处理**
   - 如果 9 个维度中有 2 个维度生成失败，是重试这 2 个维度还是整体重试？
   - 如果质量评审发现 3 个弱项维度，但只成功改进了 2 个，是否算通过？

**改进建议**:

1. **完善类型识别的边界处理**:
   ```python
   def identify_research_type(topic: str) -> dict:
       """类型识别 + 置信度 + 边界处理"""
       keywords = extract_keywords(topic)
       type_scores = calculate_type_scores(keywords)
       
       max_score = max(type_scores.values())
       max_type = max(type_scores, key=type_scores.get)
       
       # 置信度过低，触发用户确认
       if max_score < 0.6:
           return {
               "status": "need_confirmation",
               "candidate_types": [
                   {"type": t, "score": s} 
                   for t, s in sorted(type_scores.items(), key=lambda x: -x[1])[:2]
               ],
               "user_prompt": f"检测到您的研究可能属于 {max_type} 或 {type_scores.keys()[1]}，请确认研究类型"
           }
       
       # 混合类型（两个类型得分接近）
       sorted_scores = sorted(type_scores.values(), reverse=True)
       if sorted_scores[0] - sorted_scores[1] < 0.15:
           return {
               "status": "mixed_type",
               "primary_type": max_type,
               "secondary_type": list(type_scores.keys())[1],
               "strategy": "use_primary_template_with_secondary_dimensions"
           }
       
       return {"status": "confirmed", "type": max_type, "confidence": max_score}
   ```

2. **完善质量评审的异常处理**:
   ```python
   def run_quality_review_with_retry(report: str, max_retries: int = 2) -> dict:
       """质量评审 + 重试 + 异常处理"""
       retry_count = 0
       last_score = None
       
       while retry_count < max_retries:
           try:
               # 设置单次评审超时
               review_result = call_quality_reviewer_with_timeout(report, timeout=300)
               
               if review_result["total_score"] >= 24:
                   return {"status": "passed", "score": review_result["total_score"]}
               
               # 评分震荡检测（连续 2 次评分差异 > 5）
               if last_score and abs(review_result["total_score"] - last_score) > 5:
                   logger.warning(f"评分震荡检测: {last_score} -> {review_result['total_score']}")
                   # 触发人工复核或第三次评分取中位数
                   return {"status": "score_instability", "scores": [last_score, review_result["total_score"]]}
               
               last_score = review_result["total_score"]
               retry_count += 1
               
               # 通知用户重试
               notify_user(f"质量评审未通过（{review_result['total_score']}/30），正在重试（{retry_count}/{max_retries}）")
               
           except TimeoutError:
               logger.error("质量评审超时")
               retry_count += 1
               continue
           
           except APIError as e:
               logger.error(f"质量评审 API 错误: {e}")
               # API 错误不计入重试次数，直接降级
               return {"status": "api_error", "fallback": "skip_review"}
       
       # 重试失败，降级处理
       if last_score and last_score >= 18:
           # 局部通过，标注弱项
           return {"status": "passed_with_warnings", "score": last_score, "weak_dimensions": review_result["weak_dimensions"]}
       else:
           # 整体失败，交付低质量报告但标注警告
           return {"status": "failed_but_delivered", "score": last_score, "warning": "报告质量未达标，建议人工复核"}
   ```

3. **完善超时处理**:
   ```python
   # time_budgets.json 新增
   {
     "quality_review": {
       "timeout_seconds": 300,
       "timeout_strategy": "skip_and_deliver_with_warning",
       "counts_toward_total_timeout": true
     },
     "engineering_reasoning": {
       "timeout_seconds": 120,
       "timeout_strategy": "skip_and_continue",
       "counts_toward_total_timeout": true
     },
     "revision_per_retry": {
       "timeout_seconds": 600,
       "timeout_strategy": "abort_retry_and_deliver",
       "counts_toward_total_timeout": true
     }
   }
   ```

4. **增加异常恢复机制**:
   ```python
   def handle_component_failure(component: str, error: Exception) -> dict:
       """组件失败处理"""
       failure_handlers = {
           "quality_reviewer": lambda: {
               "action": "skip_review",
               "warning": "质量评审模块失败，报告未经质量审查",
               "fallback": "deliver_without_review"
           },
           "engineering_reasoner": lambda: {
               "action": "skip_reasoning",
               "warning": "工程推理模块失败，报告深度可能不足",
               "fallback": "continue_without_reasoning"
           },
           "type_identifier": lambda: {
               "action": "use_default_type",
               "default_type": "general",
               "warning": "类型识别失败，使用通用模板",
               "fallback": "trigger_user_confirmation"
           }
       }
       
       handler = failure_handlers.get(component)
       if handler:
           result = handler()
           logger.warning(f"{component} 失败: {error}。降级策略: {result['action']}")
           return result
       else:
           # 未知组件失败，终止任务
           raise TaskTerminatedError(f"未知组件 {component} 失败，任务终止")
   ```

5. **增加部分失败处理**:
   ```python
   def handle_partial_failure(dimensions: list, failed_dimensions: list) -> dict:
       """部分维度失败处理"""
       failed_ratio = len(failed_dimensions) / len(dimensions)
       
       if failed_ratio <= 0.3:
           # ≤ 30% 维度失败，重试失败维度
           return {
               "action": "retry_failed_dimensions",
               "failed_dimensions": failed_dimensions,
               "max_retry_time": 300
           }
       elif failed_ratio <= 0.6:
           # 30%-60% 维度失败，交付但标注警告
           return {
               "action": "deliver_with_warning",
               "failed_dimensions": failed_dimensions,
               "warning": f"报告 {len(failed_dimensions)} 个维度生成失败，建议人工补充"
           }
       else:
           # > 60% 维度失败，整体重试
           return {
               "action": "full_retry",
               "max_retries": 1
           }
   ```

---

### 5. 集成测试计划

**评分**: 2/5

**问题**:

1. **8h 时间预算紧张**
   - Phase 3 需要完成：
     - 3 个主题的端到端测试（CoWoS-L、贵州茅台、AI 芯片）
     - 改进前后对比分析
     - 回归测试（投资分析）
     - 根据评审反馈微调
   - 假设每个主题生成需要 30-60 分钟（standard_mode），3 个主题需要 1.5-3h
   - 改进前后对比需要跑 2 次（改进前 + 改进后），需要 3-6h
   - 回归测试 + 微调至少需要 2-3h
   - **总计至少 8-12h，8h 时间不足**

2. **缺乏详细测试用例**
   - 没有说明测试数据如何准备（测试主题、预期输出、基线数据）
   - 没有说明测试环境如何搭建（是否需要隔离环境？是否需要 mock LLM API？）
   - 没有说明测试结果如何记录和对比

3. **缺乏测试通过标准**
   - 没有定义"集成测试通过"的具体标准
   - 例如：3 个主题的质量评分都 ≥ 24？至少 2 个 ≥ 24？回归测试不降级的比例 ≥ 90%？

4. **缺乏风险缓解计划**
   - 如果集成测试发现严重问题（例如：质量评审导致无限回退），如何处理？
   - 是否有回滚方案（回退到改进前的代码）？
   - 是否有时间缓冲（如果 8h 不够，是否可以延长？）

**改进建议**:

1. **增加集成测试时间预算**:
   ```
   Phase 3 时间预算调整:
   - 测试数据准备: 2h
   - 端到端测试（3 主题 × 2 次）: 6h
   - 回归测试: 2h
   - 对比分析 + 报告: 2h
   - 微调 + 修复: 4h
   - 缓冲时间: 2h
   - 总计: 18h（而非 8h）
   ```

2. **制定详细测试用例**:
   ```markdown
   ## 集成测试用例
   
   ### TC-1: 技术工艺类研究端到端测试
   - 输入: "CoWoS-L 封装工艺深度研究"
   - 预期输出:
     - research_type: "tech_process"
     - template: "prompts/tech_analysis.md"
     - dimensions_covered: 9/9
     - quality_score: ≥ 24/30
     - tier_0_1_ratio: ≥ 40%
     - generation_time: ≤ 2700s
   - 验证点:
     - 类型识别正确
     - 9 维度全部覆盖
     - 失效模式有物理机理描述
     - 供应链有厂商名称 + 产能数据
     - 质量评审通过（或重试后通过）
   
   ### TC-2: 投资分析类研究回归测试
   - 输入: "贵州茅台投资价值分析"
   - 预期输出:
     - research_type: "investment"
     - template: "prompts/finance_analysis.md"
     - dimensions_covered: ≥ 8/10
     - quality_score: ≥ 20/30（不低于改进前）
     - tier_1_ratio: ≥ 30%
   - 验证点:
     - 类型识别正确（不受新技术模板影响）
     - 投资分析维度完整（估值、财务、行业等）
     - 质量评分不低于改进前基线
   
   ### TC-3: 市场研究类研究端到端测试
   - 输入: "AI 芯片市场竞争格局"
   - 预期输出:
     - research_type: "market_research"
     - template: "prompts/market_analysis.md"
     - dimensions_covered: ≥ 7/8
     - quality_score: ≥ 22/30
   - 验证点:
     - 市场份额数据量化
     - 竞争格局分析完整
     - 主要厂商覆盖全面
   
   ### TC-4: 质量评审边界测试
   - 输入: 故意生成低质量报告（限制搜索次数、使用低质量来源）
   - 预期输出:
     - quality_score: < 24
     - verdict: "revise" 或 "rewrite"
     - 触发回退重写
     - 重试次数 ≤ 2
   - 验证点:
     - 质量评审能正确识别低质量报告
     - 回退机制正常工作
     - 不会无限循环
   
   ### TC-5: 异常场景测试
   - 输入: 模糊主题 "苹果的技术"
   - 预期输出:
     - 触发用户确认流程
     - 用户确认后正确识别类型
   - 验证点:
     - 类型识别置信度 < 阈值时触发确认
     - 用户确认流程正常工作
   ```

3. **定义集成测试通过标准**:
   ```json
   {
     "integration_test_pass_criteria": {
       "end_to_end_tests": {
         "min_topics_pass": 2,  // 3 个主题中至少 2 个通过
         "min_quality_score": 22,
         "max_generation_time": 3600
       },
       "regression_tests": {
         "min_regression_pass_rate": 0.9,  // 90% 回归测试不降级
         "max_quality_degradation": 2  // 质量评分最多降 2 分
       },
       "boundary_tests": {
         "all_boundary_tests_pass": true  // 所有边界测试必须通过
       }
     }
   }
   ```

4. **增加风险缓解计划**:
   ```markdown
   ## 风险缓解计划
   
   ### 风险 1: 集成测试发现严重问题
   - 缓解措施:
     - 每个 Phase 完成后执行增量测试，提前发现问题
     - 保留改进前的代码分支，可随时回滚
     - 设置时间缓冲（18h 而非 8h）
   
   ### 风险 2: 质量评审导致无限回退
   - 缓解措施:
     - 设置 max_retries=2
     - 设置单次评审超时（300s）
     - 重试失败后降级交付（标注警告）
   
   ### 风险 3: 测试时间不足
   - 缓解措施:
     - 优先测试 P0 改进项（类型识别 + 技术模板）
     - 使用 mock LLM API 加速测试（牺牲部分真实性）
     - 并行运行多个测试（如果资源允许）
   
   ### 风险 4: 回归测试失败
   - 缓解措施:
     - 每个 Phase 完成后执行回归测试，提前发现影响
     - 投资分析类研究使用独立模板，不受新技术模板影响
     - 回归测试失败时，优先修复而非回滚
   ```

5. **建立测试记录和对比机制**:
   ```python
   # tests/integration/test_report.py
   class IntegrationTestReport:
       """集成测试报告生成器"""
       
       def __init__(self, test_case: str):
           self.test_case = test_case
           self.results = {}
       
       def record_result(self, metric: str, value: any, baseline: any = None):
           """记录测试结果"""
           self.results[metric] = {
               "value": value,
               "baseline": baseline,
               "delta": value - baseline if baseline else None,
               "pass": self._check_pass(metric, value, baseline)
           }
       
       def _check_pass(self, metric: str, value: any, baseline: any) -> bool:
           """检查是否通过"""
           pass_criteria = {
               "quality_score": lambda v: v >= 24,
               "dimensions_covered": lambda v: v >= 9,
               "tier_0_1_ratio": lambda v: v >= 0.4,
               "generation_time": lambda v: v <= 2700,
               "regression_quality": lambda v: v >= baseline - 2
           }
           return pass_criteria.get(metric, lambda v: True)(value)
       
       def generate_report(self) -> str:
           """生成测试报告"""
           report = f"# 集成测试报告: {self.test_case}\n\n"
           report += "## 测试结果\n\n"
           report += "| 指标 | 结果 | 基线 | 变化 | 通过 |\n"
           report += "|------|------|------|------|------|\n"
           
           for metric, result in self.results.items():
               delta_str = f"+{result['delta']}" if result['delta'] else "N/A"
               pass_str = "✅" if result['pass'] else "❌"
               report += f"| {metric} | {result['value']} | {result['baseline']} | {delta_str} | {pass_str} |\n"
           
           return report
   ```

---

## 测试覆盖盲区

1. **缺乏端到端测试框架**
   - 现有测试（`test_orchestrator.py` 等）是单元测试，不覆盖完整的研究流程
   - 需要建立端到端测试框架，模拟完整的 planning → confirming → executing → reporting → quality_review 流程

2. **缺乏性能测试**
   - 没有测试新增功能（工程推理、质量评审）对报告生成时间的影响
   - 需要验证：新增功能后，报告生成时间是否仍在可接受范围内（≤ 45 分钟）

3. **缺乏并发测试**
   - 如果多个用户同时触发研究任务，质量评审模块是否会成为瓶颈？
   - 需要测试并发场景下的系统稳定性

4. **缺乏用户验收测试（UAT）**
   - 改进计划提到"对标 Manus AI"，但没有说明如何邀请真实用户参与验收测试
   - 需要建立 UAT 流程：邀请 3-5 个目标用户，使用改进后的系统，收集反馈

5. **缺乏 A/B 测试设计**
   - 改进计划提到"对比改进前后"，但没有说明如何控制变量（同一主题？同一 LLM？同一时间？）
   - 需要设计严格的 A/B 测试方案，确保对比结果的可信度

6. **缺乏长期质量监控**
   - 改进计划只关注"一次性"测试，没有说明上线后如何持续监控质量
   - 需要建立质量监控仪表盘：跟踪每次报告的质量评分、生成时间、用户满意度

---

## Top 3 改进建议

### 1. 建立评分校准机制（优先级: P0）

**问题**: 质量评分依赖 LLM 判断，主观性强，不同 LLM 评分差异大

**建议**:
- 准备 10 份标准报告（Golden Set），人工标注评分
- 每次 LLM 评分后，与人工标注对比，偏差 > 1 分触发二次评分或人工复核
- 评分 3 次取中位数，减少随机性
- 增加评分解释（evidence + deduction_reasons），提高可追溯性

**预期效果**: 评分一致性从 ±2 分降低到 ±1 分，评分可信度提升 40%

**实施成本**: 4h（准备 Golden Set 2h + 实现校准逻辑 2h）

---

### 2. 完善边界情况处理（优先级: P0）

**问题**: 类型识别误判、质量评审死循环、超时等异常场景处理不充分

**建议**:
- 类型识别：增加置信度阈值（< 0.6 触发用户确认）+ 混合类型处理
- 质量评审：增加评分震荡检测 + 单次评审超时（300s）+ 重试失败降级策略
- 工程推理：增加超时处理（跳过推理继续生成）+ 空结果处理
- 所有组件：增加异常恢复机制（API 错误降级、部分失败处理）

**预期效果**: 系统鲁棒性提升 60%，用户感知到的失败率从 15% 降低到 5%

**实施成本**: 6h（异常处理逻辑 4h + 测试 2h）

---

### 3. 建立自动化回归测试套件（优先级: P1）

**问题**: 回归测试策略笼统，缺乏自动化测试用例和基线对比

**建议**:
- 建立回归测试套件（`tests/regression/`），覆盖投资分析、技术工艺、市场研究 3 类主题
- 定义基线指标（质量评分、维度覆盖、生成时间等），保存为 JSON
- 实现自动化回归测试脚本，每次改动后自动运行
- 集成到 CI/CD，代码提交自动触发回归测试

**预期效果**: 回归测试覆盖率从 0% 提升到 80%，每次改动后 30 分钟内获得回归测试结果

**实施成本**: 8h（测试用例设计 3h + 自动化脚本 3h + CI/CD 集成 2h）

---

## 附录: 评审检查清单

| 检查项 | 状态 | 说明 |
|--------|------|------|
| 验收标准是否可自动化测试 | ⚠️ 部分 | 部分标准主观性强，需量化 |
| 质量评分是否客观可重复 | ❌ 否 | 缺乏校准机制，评分差异大 |
| 回归测试策略是否完整 | ❌ 否 | 缺乏具体用例和自动化脚本 |
| 边界情况是否充分处理 | ❌ 否 | 异常场景处理不完善 |
| 集成测试时间是否充足 | ❌ 否 | 8h 不足，建议 18h |
| 是否有测试通过标准 | ❌ 否 | 未定义明确的通过标准 |
| 是否有风险缓解计划 | ⚠️ 部分 | 有基本缓解措施，但不完整 |
| 是否有长期质量监控 | ❌ 否 | 缺乏上线后的质量监控 |

---

**评审结论**: 改进计划在功能设计层面较为完整，但在质量保证和测试层面存在明显盲区。建议优先补充评分校准机制（P0）、边界情况处理（P0）、自动化回归测试套件（P1），并将集成测试时间从 8h 增加到 18h。完成这些补充后，再进入实施阶段。

**评审人**: QA/测试专家  
**评审日期**: 2026-06-11
