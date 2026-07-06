# Solution Pro 修复方案 — 专家共识综合报告

> **生成日期**: 2026-07-06
> **决策方法**: AI Native 多专家并行评估（3 专家独立视角 + 综合裁决）
> **问题总数**: 15 个 DryRun 发现 → 验证后 13 个真实问题 → 专家评估后 4 个 Must Fix

---

## 一、问题验证结果（真实存在 vs 误报）

| 问题 | 原严重度 | 验证结果 | 说明 |
|------|----------|----------|------|
| P0-1 ReviewQCOrchestrator 无调用方 | 🔴 P0 | ❌ **误报** | 用户确认 Master 应调用 SummaryOrchestrator，这是设计意图 |
| P2-9 harness_agent.md 无调用入口 | 🟡 P2 | ❌ **误报** | 代码验证: planning_orchestrator.py 使用 harness_agent.md |
| P0-2 Research 无质量门禁 | 🔴 P0 | ✅ **真实** | 代码验证: gate_a_scores 硬编码 score=0.0/verdict=PASS |
| P0-3 V1/V2 两套 Pipeline | 🔴 P0 | ✅ **真实** | 代码验证: task_builder.py 使用所有 8 个 *_harness.md |
| P1-4 71% 约束无代码强制 | 🟡 P1 | ✅ **真实** | 85 条约束中 60 条无代码验证 |
| P1-5 46 Schemas 仅 3 有 validators | 🟡 P1 | ✅ **真实** | 43 个 Schema 只有字段定义 |
| P1-6 5 个 fallback bypass | 🟡 P1 | ✅ **真实** | 静默降级无告警 |
| P1-7 platform_capabilities 跨域断裂 | 🟡 P1 | ✅ **真实** | 无跨域传递机制 |
| P2-8~15 | 🟢 P2 | 部分真实 | 详见专家评估 |

**验证后真实问题数**: 13 个（排除 2 个误报）

---

## 二、专家评估结果

### 专家 1: ROI Judge（修复价值评估）

| 问题 | 影响 | 成本 | 风险 | 价值 | 修复决策 |
|------|------|------|------|------|----------|
| P1-6 Fallback | 8 | 3 | 8 | **21.33** | ✅ Must Fix |
| P0-2 Research gate | 9 | 4 | 9 | **20.25** | ✅ Must Fix |
| P1-4 约束验证 | 8 | 6 | 8 | **10.67** | ✅ Must Fix |
| P1-5 Schema validators | 7 | 5 | 7 | **9.8** | ✅ Must Fix |
| P2-11 digest | 6 | 3 | 5 | 10.0 | 🟡 Should Fix |
| P2-12 契约漂移 | 5 | 2 | 4 | 10.0 | 🟡 Should Fix |
| P2-8 命名断裂 | 5 | 3 | 5 | 8.33 | 🟡 Should Fix |
| P2-14 双重评级 | 4 | 2 | 4 | 8.0 | 🟡 Should Fix |
| P0-3 V1/V2 | 7 | 8 | 6 | 5.25 | ❌ Won't Fix（等 V2 稳定） |
| P1-7 跨域 | 6 | 7 | 6 | 5.14 | ❌ Won't Fix（等 platform 频繁时） |
| P2-10 Summarizer | 6 | 5 | 5 | 6.0 | ❌ Won't Fix（P0-3 子问题） |
| P2-13 重复 | 4 | 3 | 3 | 4.0 | ❌ Won't Fix（不影响功能） |
| P2-15 冗余 | 3 | 2 | 2 | 3.0 | ❌ Won't Fix（下次重构顺带） |

### 专家 2: Architecture Impact（架构影响评估）

| 问题 | 向后兼容 | 部署风险 | 安全修复 | 关键风险 |
|------|----------|----------|----------|----------|
| P0-2 Research gate | ✅ 是 | MEDIUM | ✅ | Gate FAIL 时 pipeline 可能卡死（需设计降级路径） |
| P1-4 约束验证 | ✅ 是 | LOW | ✅ | 现有测试 fixture 可能失效 |
| P1-5 Schema validators | ❌ 否 | MEDIUM | ✅ | LLM 输出可能失效，需 baseline 测试 |
| P1-6 Fallback | ❌ 否 | HIGH | ❌ | 消除后 LLM 不可用时 pipeline 直接失败 |
| P0-3 V1/V2 | ❌ 否 | HIGH | ❌ | task_builder.py 和 control_contract.py 被两套共享 |

### 专家 3: Cage Designer（契约笼子设计）

设计了 5 个问题的具体修复方案：
- P0-2: 6 维度 Gate A 评估 + `_compute_gate_a_scores()` 替换硬编码
- P1-4: 三层验证架构（Schema L1 + Runner L2 + Post-processing L3）
- P1-5: 4 个 Schema 新增 7 个 validators
- P1-6: 5 个 fallback 逐一修复，通用降级标记协议
- P1-7: 三步跨域传递链 + PlatformCapabilities Pydantic model

---

## 三、专家共识与冲突

### ✅ 共识

1. **P0-2 Research 无质量门禁**: 三方一致同意修复。ROI 最高之一，基础设施已存在（ConvergenceLayer._evaluate_gates()），只需接线。

2. **P1-4 约束无代码强制**: 三方一致同意修复。成本低，风险低，确定性验证比 Prompt 声明可靠。

3. **P1-5 Schema 缺少 validators**: 三方一致同意修复。需先 baseline 测试，但价值明确。

4. **P0-3 V1/V2 并存**: 三方一致同意**现在不修复**。修复成本高、风险大，等 V2 稳定后集中清理。

### ⚠️ 冲突

**P1-6 Fallback bypass**:
- ROI Judge: 最高价值（value=21.33），必须修复
- Architecture Impact: HIGH risk，backward incompatible，不安全
- **冲突根因**: ROI 从收益角度评估，Architecture 从风险角度评估

**冲突解决方案**:
> 不要消除 fallback，而是**让 fallback 被检测到**。
> - 保留 fallback 作为降级路径（避免 LLM 不可用时 pipeline 失败）
> - 所有降级输出必须包含 `_degraded: true` + `_degradation_reason`
> - 下游 Agent 检测到 `_degraded` 标记即 raise ValueError（除非显式允许）
> - 这样既没有破坏现有容错能力，又消除了"静默降级"问题

---

## 四、最终修复决策（经 AI Native 方法确认）

### Phase 1: 立即修复（Must Fix，4 个）

#### 1. P0-2 Research 无质量门禁
**决策**: ✅ 修复（三方一致）
**方法**: 契约笼子
**代码修改**:
```python
# research_orchestrator.py 替换硬编码 gate
# 从：
gate_a_scores = {"score": 0.0, "verdict": "PASS"}
# 改为：
from convergence_layer import ConvergenceLayer

def _compute_gate_a_scores(self, expert_outputs, consolidated) -> dict:
    """6 维度评估：Finding 数量/深度、Evidence 覆盖率、Confidence 分布、REQ 覆盖度、Expert 数量"""
    findings = consolidated.get("consolidated_findings", [])
    n_findings = len(findings)
    n_experts = len(expert_outputs)
    
    # 维度 1: Finding 数量 (权重 0.2)
    finding_score = min(n_findings / 3, 1.0)  # 至少 3 个 findings = 满分
    
    # 维度 2: Evidence 覆盖率 (权重 0.2)
    findings_with_evidence = sum(1 for f in findings if f.get("evidence_url"))
    evidence_score = findings_with_evidence / n_findings if n_findings > 0 else 0.0
    
    # 维度 3: Confidence 分布 (权重 0.2)
    confidences = [f.get("confidence", 0.5) for f in findings]
    avg_confidence = sum(confidences) / len(confidences) if confidences else 0.5
    confidence_score = avg_confidence
    
    # 维度 4: REQ 覆盖度 (权重 0.2)
    covered_reqs = set()
    for f in findings:
        covered_reqs.update(f.get("covered_req_ids", []))
    # 从 planning_convergence 获取所有 P0 REQ
    all_p0_reqs = self._get_p0_req_ids()
    req_coverage = len(covered_reqs) / len(all_p0_reqs) if all_p0_reqs else 1.0
    
    # 维度 5: Expert 数量 (权重 0.1)
    expert_score = min(n_experts / 2, 1.0)  # 至少 2 个 experts = 满分
    
    # 维度 6: 深度检查 (权重 0.1)
    deep_findings = sum(1 for f in findings if len(f.get("description", "")) >= 200)
    depth_score = deep_findings / n_findings if n_findings > 0 else 0.0
    
    total = (finding_score * 0.2 + evidence_score * 0.2 + 
             confidence_score * 0.2 + req_coverage * 0.2 + 
             expert_score * 0.1 + depth_score * 0.1)
    
    verdict = "PASS" if total >= 0.7 else "FAIL"
    return {"score": round(total, 2), "verdict": verdict, "breakdown": {...}}
```
**契约笼子**:
- Pydantic validator: 检查 gate score 不是硬编码的 0.0
- 失败行为: `total < 0.7` → raise ValueError，不允许降级（质量不达标不能继续）
- 回滚: 添加 `research_quality_gate_enabled` flag，默认关闭

#### 2. P1-4 约束无代码强制（Top-10 约束）
**决策**: ✅ 修复（三方一致）
**方法**: 契约笼子（三层验证）
**代码修改**:
```python
# schemas/schemas.py — 新增 validators

class Constraint(BaseModel):
    id: str  # C-XXX 格式
    description: str  # 非空且长度 >= 20
    priority: Literal["MUST", "SHOULD", "MAY"]
    rationale: str  # 非空且长度 >= 30
    
    @field_validator("id")
    def validate_constraint_id(cls, v):
        if not re.match(r"^C-\d{3}$", v):
            raise ValueError(f"Constraint ID must be C-XXX format, got: {v}")
        return v
    
    @field_validator("rationale")
    def validate_rationale(cls, v):
        if len(v.strip()) < 30:
            raise ValueError(f"Rationale must be >= 30 chars, got: {len(v)} chars")
        return v

class ResearchFinding(BaseModel):
    description: str
    evidence_url: Optional[str] = None
    confidence: float = Field(ge=0.0, le=1.0)
    
    @field_validator("description")
    def validate_description_length(cls, v):
        if len(v.strip()) < 200:
            raise ValueError(f"Finding description must be >= 200 chars, got: {len(v)}")
        return v
    
    @field_validator("evidence_url")
    def validate_evidence(cls, v):
        if v and not v.startswith(("http://", "https://")):
            raise ValueError(f"Evidence URL must be valid URL, got: {v}")
        return v

# Runner 代码验证（Stage 4.4）
def _validate_research_constraints(self, expert_output: dict) -> dict:
    """验证 Top-10 关键约束"""
    issues = []
    
    # 1. Finding 数量 >= 3
    findings = expert_output.get("findings", [])
    if len(findings) < 3:
        issues.append(f"Finding count {len(findings)} < 3")
    
    # 2. 每个 Finding >= 200 字
    for i, f in enumerate(findings):
        if len(f.get("description", "")) < 200:
            issues.append(f"Finding {i} description < 200 chars")
    
    # 3. 至少 50% Finding 有 evidence URL
    with_evidence = sum(1 for f in findings if f.get("evidence_url"))
    if len(findings) > 0 and with_evidence / len(findings) < 0.5:
        issues.append(f"Evidence coverage {with_evidence}/{len(findings)} < 50%")
    
    # 4. 至少 15 次 web_search（从 search_history 计数）
    searches = expert_output.get("search_history", [])
    if len(searches) < 15:
        issues.append(f"web_search count {len(searches)} < 15")
    
    # 5. P0 REQ 100% 覆盖（检查 covered_req_ids）
    all_p0 = self._get_p0_req_ids()
    covered = set()
    for f in findings:
        covered.update(f.get("covered_req_ids", []))
    missing = set(all_p0) - covered
    if missing:
        issues.append(f"P0 REQ not covered: {missing}")
    
    return {"valid": len(issues) == 0, "issues": issues}
```
**契约笼子**:
- Layer 1: Schema validators（Pydantic 自动触发）
- Layer 2: Runner 验证（Stage 4.4 新增）
- Layer 3: Post-processing 交叉验证（P0 REQ 覆盖矩阵）
- 失败行为: 先 warning 模式（1 周），再切换 strict 模式

#### 3. P1-5 Schema 缺少 validators
**决策**: ✅ 修复（三方一致）
**方法**: 契约笼子
**代码修改**:
```python
# schemas/schemas.py — 新增 validators

class ExpertPlanSchema(BaseModel):
    # ... 现有字段 ...
    
    @model_validator(mode="after")
    def validate_constraints_quality(self):
        constraints = self.constraints or []
        ids = [c.id for c in constraints]
        
        # 检查 ID 唯一性
        if len(ids) != len(set(ids)):
            duplicates = {id for id in ids if ids.count(id) > 1}
            raise ValueError(f"Duplicate constraint IDs: {duplicates}")
        
        # 检查 rationale 非空
        for c in constraints:
            if not c.rationale or len(c.rationale.strip()) < 30:
                raise ValueError(f"Constraint {c.id} rationale too short or empty")
        
        # 检查 MUST 约束占比 < 50%
        must_count = sum(1 for c in constraints if c.priority == "MUST")
        if constraints and must_count / len(constraints) > 0.5:
            raise ValueError(f"MUST constraints {must_count}/{len(constraints)} > 50%")
        
        return self

class ResearchExpertSchema(BaseModel):
    # ... 现有字段 ...
    
    @field_validator("research_findings")
    def validate_findings_count(cls, v):
        if len(v) < 3:
            raise ValueError(f"Research findings count {len(v)} < 3 minimum")
        return v
    
    @model_validator(mode="after")
    def validate_confidence_distribution(self):
        findings = self.research_findings or []
        confidences = [f.confidence for f in findings if hasattr(f, "confidence")]
        if confidences:
            avg = sum(confidences) / len(confidences)
            if avg < 0.3:
                raise ValueError(f"Average confidence {avg:.2f} < 0.3, research too speculative")
        return self

class UnifiedConstraintsSchema(BaseModel):
    # ... 现有 F6/F7 ...
    
    @model_validator(mode="after")
    def validate_merge_ratio(self):
        """F8: merge_ratio 0.5-0.8"""
        meta = self.meta or {}
        merge_ratio = meta.get("merge_ratio")
        if merge_ratio is not None and not (0.5 <= merge_ratio <= 0.8):
            raise ValueError(f"merge_ratio {merge_ratio} not in [0.5, 0.8]")
        return self
    
    @model_validator(mode="after")
    def validate_p0_traceability(self):
        """F9: P0 REQ 100% 覆盖"""
        p0_reqs = self.p0_requirements or []
        covered = set()
        for uc in self.use_cases or []:
            covered.update(uc.covered_req_ids or [])
        missing = set(r.id for r in p0_reqs) - covered
        if missing:
            raise ValueError(f"P0 REQ not covered: {missing}")
        return self
```
**契约笼子**:
- 每个 validator 一个独立 PR
- 添加 `SCHEMA_STRICT_MODE` 环境变量控制
- 先用 20 个真实 pipeline 输出做 baseline 测试

#### 4. P1-6 Fallback bypass（冲突问题的折中方案）
**决策**: ✅ 修复（但**不消除 fallback**，而是让 fallback **可检测**）
**方法**: 契约笼子（降级标记协议）
**代码修改**:
```python
# 通用降级标记协议
DEGRADATION_PROTOCOL = {
    "required_fields": ["_degraded", "_degradation_reason"],
    "degraded_must_be": True,
    "reason_min_length": 10
}

# control_contract.py — 修改 fallback 行为
@field_validator("control_contract")
def validate_no_silent_fallback(cls, v):
    if v.get("_fallback_used"):
        raise ValueError(
            f"Fallback detected: {v.get('_degradation_reason')}. "
            f"All fallback outputs must set _degraded=True"
        )
    return v

# research_orchestrator.py — 修改 fallback 行为
@field_validator("knowledge_freshness")
def validate_freshness_quality(cls, v):
    if v.get("_degraded"):
        # 允许降级，但必须有明确原因
        if not v.get("_degradation_reason"):
            raise ValueError("Degraded output must have _degradation_reason")
    else:
        # 非降级时，要求 LLM 查询比例 >= 50%
        llm_queries = v.get("llm_query_count", 0)
        total_queries = v.get("total_query_count", 1)
        if llm_queries / total_queries < 0.5:
            raise ValueError(
                f"LLM query ratio {llm_queries}/{total_queries} < 50%. "
                f"Keyword fallback used without marking _degraded=True"
            )
    return v

# master_orchestrator.py — 修改 fallback 行为
@model_validator(mode="after")
def validate_frozen_spec_source(self):
    if self._source == "fallback_dict":
        raise ValueError(
            "Frozen spec built from fallback dict. "
            "Must have explicit _degraded=True and _degradation_reason"
        )
    return self

# 下游检测 — 在 orchestrator 或 Ship Pro 入口处
def validate_input_quality(data: dict):
    """检测降级输入"""
    if data.get("_degraded"):
        reason = data.get("_degradation_reason", "unknown")
        logger.error(f"DEGRADED INPUT: {reason}")
        raise ValueError(f"Degraded input rejected: {reason}")
```
**契约笼子**:
- 所有降级输出必须包含 `_degraded: true` + `_degradation_reason`
- Pydantic validator 检测降级标记缺失
- 下游检测到降级即 raise（除非显式允许）
- 保留了 fallback 的容错能力，但消除了"静默"

### Phase 2: 条件修复（Should Fix，4 个）

| 问题 | 决策 | 方法 | 条件 |
|------|------|------|------|
| P2-11 conversation_digest | 🟡 修复 | 代码 | 低工作量，可立即做 |
| P2-12 Prompt-Runner 契约 | 🟡 修复 | 代码 | 同步文档+代码 |
| P2-8 命名断裂 | 🟡 修复 | 代码 | 统一 naming |
| P2-14 双重评级 | 🟡 修复 | 代码 | 统一为 PASS/WARN/FAIL |

### Phase 3: 不修复（Won't Fix，6 个）

| 问题 | 决策 | 原因 |
|------|------|------|
| P0-3 V1/V2 | ❌ 不修复 | 修复成本高（8），等 V2 稳定后集中清理 |
| P1-7 跨域 | ❌ 不修复 | 需 Ship Pro 配合，等 platform 约束频繁时 |
| P2-10 Summarizer | ❌ 不修复 | P0-3 子问题，V2 统一后自动消失 |
| P2-13 重复 | ❌ 不修复 | 纯 DRY 问题，不影响功能 |
| P2-15 冗余 | ❌ 不修复 | 下次重构顺带 |
| P2-9 误报 | ❌ 不修复 | 已确认 harness_agent.md 被使用 |

---

## 五、实施计划

### Phase 1: 立即修复（1-2 天）

**Day 1**:
1. P0-2: 添加 `_compute_gate_a_scores()` 替换硬编码 gate
2. P1-5: 添加 ExpertPlanSchema validators（ID 格式、rationale 长度）

**Day 2**:
3. P1-4: 添加 ResearchFinding 长度验证 + evidence URL 检查
4. P1-6: 实现降级标记协议（`_degraded` + `_degradation_reason`）
5. 运行 DryRun 回归验证

### Phase 2: 渐进增强（1 周）

**Week 1**:
6. P1-5: 添加剩余 Schema validators（ResearchExpertSchema、UnifiedConstraintsSchema）
7. P1-4: 添加 Runner 层验证（Stage 4.4）
8. P2-11~14: 条件修复项

### Phase 3: 观察与调整（1 周）

- 观察新 validators 是否导致 pipeline 失败率上升
- 收集 LLM 输出数据，调整验证阈值
- 从 warning 模式切换为 strict 模式

### Phase 4: 长期清理（V2 稳定后）

- P0-3: V1/V2 统一清理
- P1-7: 跨域传递机制（如果 platform 约束频繁出现）

---

## 六、修复验证清单

每个修复完成后必须验证：

- [ ] Pydantic validator 在真实 LLM 输出上通过
- [ ] 在回归测试集（20 个历史 pipeline 输出）上通过
- [ ] 在降级测试（注入有缺陷的输入）上正确触发
- [ ] 回滚策略可工作（feature flag / env var）
- [ ] 文档已更新（Schema 契约、Prompt 数据流声明）
- [ ] 日志可观测（validator 失败信息清晰）

---

## 七、关键设计决策

### 1. 为什么 P1-6 不消除 fallback？

**冲突**: ROI Judge 说消除 fallback 价值最高，Architecture Impact 说风险最高。

**决策**: 折中方案 — 保留 fallback 但强制检测。

**理由**:
- LLM 不可用是真实场景（API 限流、超时），完全消除 fallback 会使 pipeline 在边缘情况下失败
- 真正的反模式不是"有 fallback"，而是"fallback 静默发生而不被检测"
- 降级标记协议既保留了容错能力，又消除了质量黑洞

### 2. 为什么 P0-3 V1/V2 现在不修复？

**理由**:
- task_builder.py 和 control_contract.py 被 V1/V2 共享，清理会意外破坏 V2
- V2 尚未完全稳定，现在投入高成本清理可能因 V2 后续变化而浪费
- 建议 V2 稳定后（至少 3 个成功 E2E）做一次集中清理

### 3. 为什么 P1-7 跨域现在不修复？

**理由**:
- 需要 Ship Pro 配合修改，跨域协调成本高
- 当前 platform 约束在任务中出现频率低
- 当 platform 约束出现频率 > 20% 时启动修复

---

*报告生成: 2026-07-06 | AI Native 决策方法: 3 专家并行评估 + 综合裁决 | 问题验证: 代码级检查 + 用户确认 | 契约笼子设计: Pydantic validators + 降级标记协议*
