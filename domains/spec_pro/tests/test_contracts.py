"""Spec Pro 核心契约和数据流测试

覆盖：
1. LivingSpec Pydantic validators (core_summary, narrative, Term, ConfirmedLayer, SemanticAnchor)
2. Gate 函数 (compute_complexity_score, gate_harness_decision, gate_living_spec_density)
3. 数据合并 (merge_confirmed, _normalize_quality_dimensions)
4. 域上下文构建 (build_domain_context)
"""

import pytest
import sys
from pathlib import Path

# 确保 .deepflow 根目录在 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))


# ============================================================================
# 1. 契约验证器 (contracts/living_spec.py)
# ============================================================================

class TestLivingSpecValidators:
    """LivingSpec Pydantic 模型字段校验"""

    def test_core_summary_empty_passes(self):
        """空字符串 → 通过（兼容早期轮次）"""
        from domains.spec_pro.contracts.living_spec import LivingSpec, LivingSpecMeta, ConfirmedLayer
        spec = LivingSpec(
            meta=LivingSpecMeta(created_at="2026-01-01", updated_at="2026-01-01"),
            confirmed=ConfirmedLayer(),
            core_summary="",
        )
        assert spec.core_summary == ""

    def test_core_summary_too_short_raises(self):
        """太短（< 10 chars）→ raise ValueError"""
        from domains.spec_pro.contracts.living_spec import LivingSpec, LivingSpecMeta, ConfirmedLayer
        with pytest.raises(Exception):  # pydantic ValidationError
            LivingSpec(
                meta=LivingSpecMeta(created_at="2026-01-01", updated_at="2026-01-01"),
                confirmed=ConfirmedLayer(),
                core_summary="太短了",  # 3 chars < 10
            )

    def test_core_summary_normal_passes(self):
        """正常长度 → 通过"""
        from domains.spec_pro.contracts.living_spec import LivingSpec, LivingSpecMeta, ConfirmedLayer
        spec = LivingSpec(
            meta=LivingSpecMeta(created_at="2026-01-01", updated_at="2026-01-01"),
            confirmed=ConfirmedLayer(),
            core_summary="这是一个足够长的核心需求摘要，超过了十个字符的限制",
        )
        assert len(spec.core_summary) >= 10

    def test_narrative_empty_passes(self):
        """空字符串 → 通过"""
        from domains.spec_pro.contracts.living_spec import LivingSpec, LivingSpecMeta, ConfirmedLayer
        spec = LivingSpec(
            meta=LivingSpecMeta(created_at="2026-01-01", updated_at="2026-01-01"),
            confirmed=ConfirmedLayer(),
            narrative="",
        )
        assert spec.narrative == ""

    def test_narrative_too_short_raises(self):
        """太短（< 20 chars）→ raise ValueError"""
        from domains.spec_pro.contracts.living_spec import LivingSpec, LivingSpecMeta, ConfirmedLayer
        with pytest.raises(Exception):  # pydantic ValidationError
            LivingSpec(
                meta=LivingSpecMeta(created_at="2026-01-01", updated_at="2026-01-01"),
                confirmed=ConfirmedLayer(),
                narrative="太短了不够二十个字",  # < 20 chars
            )

    def test_narrative_normal_passes(self):
        """正常长度 → 通过"""
        from domains.spec_pro.contracts.living_spec import LivingSpec, LivingSpecMeta, ConfirmedLayer
        spec = LivingSpec(
            meta=LivingSpecMeta(created_at="2026-01-01", updated_at="2026-01-01"),
            confirmed=ConfirmedLayer(),
            narrative="这是一个足够长的用户需求叙述文档，超过了二十个字符的最小限制要求。",
        )
        assert len(spec.narrative) >= 20


class TestTermCategory:
    """Term category 字段（P1-3 新增）"""

    def test_term_with_category_preserved(self):
        """有 category → 保留"""
        from domains.spec_pro.contracts.living_spec import Term
        term = Term(name="Kubernetes", definition="容器编排平台", category="technical")
        assert term.category == "technical"

    def test_term_without_category_defaults_empty(self):
        """无 category → 默认 """""
        from domains.spec_pro.contracts.living_spec import Term
        term = Term(name="Kubernetes", definition="容器编排平台")
        assert term.category == ""


class TestConfirmedLayerUsers:
    """ConfirmedLayer users 验证器"""

    def test_users_normal_passes(self):
        """正常 users → 通过"""
        from domains.spec_pro.contracts.living_spec import ConfirmedLayer
        layer = ConfirmedLayer(
            users=[
                {"role": "开发者", "key_needs": "快速迭代"},
                {"role": "运维", "key_needs": "稳定性"},
            ]
        )
        assert len(layer.users) == 2

    def test_users_empty_role_raises(self):
        """空 role → raise ValueError"""
        from domains.spec_pro.contracts.living_spec import ConfirmedLayer
        with pytest.raises(Exception):  # pydantic ValidationError
            ConfirmedLayer(
                users=[{"role": "", "key_needs": "something"}]
            )

    def test_users_missing_role_raises(self):
        """User 模型 role 是必填字段，缺少 → Pydantic ValidationError"""
        from domains.spec_pro.contracts.living_spec import ConfirmedLayer
        with pytest.raises(Exception):  # pydantic ValidationError: role required
            ConfirmedLayer(users=[{"key_needs": "something"}])


class TestSemanticAnchorValidators:
    """SemanticAnchor 字段校验"""

    def test_category_illegal_short_raises(self):
        """category 太短（< 2 chars）→ raise ValueError"""
        from domains.spec_pro.contracts.living_spec import SemanticAnchor
        with pytest.raises(Exception):
            SemanticAnchor(
                name="test_anchor",
                category="x",  # 1 char < 2
                constraint="这是一个足够长的约束描述",
                source_quote="原文引用",
            )

    def test_category_valid_suggested(self):
        """合法的建议类别 → 通过"""
        from domains.spec_pro.contracts.living_spec import SemanticAnchor
        anchor = SemanticAnchor(
            name="sessions_spawn",
            category="platform_api",
            constraint="必须使用 sessions_spawn 工具进行子 Agent 创建",
            source_quote="原文引用内容",
        )
        assert anchor.category == "platform_api"

    def test_category_valid_custom(self):
        """自定义类别（不在建议列表中但 >= 2 chars）→ 通过（开放枚举）"""
        from domains.spec_pro.contracts.living_spec import SemanticAnchor
        anchor = SemanticAnchor(
            name="custom_thing",
            category="custom_category",
            constraint="这是一个足够长的约束描述信息",
            source_quote="原文引用",
        )
        assert anchor.category == "custom_category"

    def test_name_empty_raises(self):
        """name 空 → raise ValueError"""
        from domains.spec_pro.contracts.living_spec import SemanticAnchor
        with pytest.raises(Exception):
            SemanticAnchor(
                name="",
                category="platform_api",
                constraint="这是一个足够长的约束描述",
                source_quote="原文引用",
            )

    def test_name_too_short_raises(self):
        """name 太短（< 2 chars）→ raise ValueError"""
        from domains.spec_pro.contracts.living_spec import SemanticAnchor
        with pytest.raises(Exception):
            SemanticAnchor(
                name="x",
                category="platform_api",
                constraint="这是一个足够长的约束描述",
                source_quote="原文引用",
            )

    def test_constraint_too_short_raises(self):
        """constraint 太短（< 5 chars）→ raise ValueError"""
        from domains.spec_pro.contracts.living_spec import SemanticAnchor
        with pytest.raises(Exception):
            SemanticAnchor(
                name="test_anchor",
                category="platform_api",
                constraint="太短",  # < 5 chars
                source_quote="原文引用",
            )

    def test_valid_anchor_passes(self):
        """完全合法的 anchor → 通过"""
        from domains.spec_pro.contracts.living_spec import SemanticAnchor
        anchor = SemanticAnchor(
            name="sessions_spawn",
            category="platform_api",
            constraint="必须使用 sessions_spawn 工具进行子 Agent 创建，不可用 Python import",
            source_quote="sessions_spawn 是 Agent Tool，不是 Python 函数",
        )
        assert anchor.name == "sessions_spawn"
        assert anchor.confidence == 0.9  # default


# ============================================================================
# 2. Gate 函数 (contracts/gate.py)
# ============================================================================

class TestComputeComplexityScore:
    """compute_complexity_score 复杂度计算"""

    def test_simple_project(self):
        """简单项目（1 user, 1 cap）→ score < 30, engine=direct"""
        from domains.spec_pro.contracts.gate import compute_complexity_score
        spec = {
            "confirmed": {
                "users": [{"role": "开发者"}],
                "capabilities": {"always_do": ["快速响应"], "should_do": [], "never_do": []},
                "quality_attributes": [],
                "constraints": {},
            },
            "inferred": [],
            "semantic_anchors": [],
        }
        result = compute_complexity_score(spec)
        assert result["complexity_score"] < 30
        assert result["suggested_engine"] == "direct"
        assert result["suggested_mode"] == "simple"

    def test_medium_project(self):
        """中等项目（3 users, 5 caps, 3 qa）→ score 30-59, engine=solution_pro"""
        from domains.spec_pro.contracts.gate import compute_complexity_score
        spec = {
            "confirmed": {
                "users": [{"role": "A"}, {"role": "B"}, {"role": "C"}],
                "capabilities": {
                    "always_do": ["cap1", "cap2"],
                    "should_do": ["cap3", "cap4"],
                    "never_do": ["cap5"],
                },
                "quality_attributes": [{"category": "perf", "spec": "fast"}, {"category": "sec", "spec": "safe"}, {"category": "rel", "spec": "stable"}],
                "constraints": {},
            },
            "inferred": [],
            "semantic_anchors": [],
        }
        result = compute_complexity_score(spec)
        assert 30 <= result["complexity_score"] < 60, f"score={result['complexity_score']}"
        assert result["suggested_engine"] == "solution_pro"
        assert result["suggested_mode"] == "standard"

    def test_complex_project(self):
        """复杂项目（3+ users, 6+ caps, 3+ qa, 5+ inferred）→ score >= 60, mode=full"""
        from domains.spec_pro.contracts.gate import compute_complexity_score
        spec = {
            "confirmed": {
                "users": [{"role": "A"}, {"role": "B"}, {"role": "C"}, {"role": "D"}],
                "capabilities": {
                    "always_do": ["c1", "c2", "c3"],
                    "should_do": ["c4", "c5"],
                    "never_do": ["c6"],
                },
                "quality_attributes": [
                    {"category": "perf", "spec": "fast"},
                    {"category": "sec", "spec": "safe"},
                    {"category": "rel", "spec": "stable"},
                ],
                "constraints": {"perf": ["<100ms"], "sec": ["encrypt"], "rel": ["99.9%"]},
            },
            "inferred": [{"id": f"i{i}", "dimension": "d", "content": "c", "confidence": 0.8} for i in range(6)],
            "semantic_anchors": [{"name": f"a{i}", "category": "platform_api", "constraint": "long constraint", "source_quote": "q"} for i in range(3)],
        }
        result = compute_complexity_score(spec)
        assert result["complexity_score"] >= 60, f"score={result['complexity_score']}"
        assert result["suggested_engine"] == "solution_pro"
        assert result["suggested_mode"] == "full"

    def test_empty_spec(self):
        """空 spec → score=0, engine=direct"""
        from domains.spec_pro.contracts.gate import compute_complexity_score
        result = compute_complexity_score({})
        assert result["complexity_score"] == 0
        assert result["suggested_engine"] == "direct"


class TestGateHarnessDecision:
    """gate_harness_decision Layer 3 合并决策"""

    def test_l1_pass_l2_high_pass(self):
        """L1 pass + L2 >= 75 → PASS"""
        from domains.spec_pro.contracts.gate import gate_harness_decision
        l1 = {"passed": True}
        l2 = {"dimension_scores": {
            "clarity": 85, "completeness": 80, "executability": 80,
            "consistency": 75, "downstream_fitness": 80,
        }}
        result = gate_harness_decision(l1, l2)
        assert result["decision"] == "PASS"
        assert result["layer1_passed"] is True

    def test_l1_pass_l2_medium_warn(self):
        """L1 pass + L2 60-74 → WARN"""
        from domains.spec_pro.contracts.gate import gate_harness_decision
        l1 = {"passed": True}
        l2 = {"dimension_scores": {
            "clarity": 65, "completeness": 65, "executability": 65,
            "consistency": 65, "downstream_fitness": 65,
        }}
        result = gate_harness_decision(l1, l2)
        assert result["decision"] == "WARN"

    def test_l1_fail_l2_low_soft_block(self):
        """L1 fail + L2 < 60 → SOFT_BLOCK"""
        from domains.spec_pro.contracts.gate import gate_harness_decision
        l1 = {"passed": False}
        l2 = {"dimension_scores": {
            "clarity": 40, "completeness": 40, "executability": 40,
            "consistency": 40, "downstream_fitness": 40,
        }}
        result = gate_harness_decision(l1, l2)
        assert result["decision"] == "SOFT_BLOCK"

    def test_l1_pass_l2_very_low_hard_block(self):
        """L1 pass + L2 < 45 → HARD_BLOCK"""
        from domains.spec_pro.contracts.gate import gate_harness_decision
        l1 = {"passed": True}
        l2 = {"dimension_scores": {
            "clarity": 30, "completeness": 30, "executability": 30,
            "consistency": 30, "downstream_fitness": 30,
        }}
        result = gate_harness_decision(l1, l2)
        assert result["decision"] == "HARD_BLOCK"

    def test_l1_fail_l2_high_warn(self):
        """L1 fail + L2 >= 60 → WARN（L1 不通过至少 WARN）"""
        from domains.spec_pro.contracts.gate import gate_harness_decision
        l1 = {"passed": False}
        l2 = {"dimension_scores": {
            "clarity": 85, "completeness": 80, "executability": 80,
            "consistency": 75, "downstream_fitness": 80,
        }}
        result = gate_harness_decision(l1, l2)
        assert result["decision"] == "WARN"

    def test_l1_pass_l2_45_59_soft_block(self):
        """L1 pass + L2 45-59 → SOFT_BLOCK"""
        from domains.spec_pro.contracts.gate import gate_harness_decision
        l1 = {"passed": True}
        l2 = {"dimension_scores": {
            "clarity": 50, "completeness": 50, "executability": 50,
            "consistency": 50, "downstream_fitness": 50,
        }}
        result = gate_harness_decision(l1, l2)
        assert result["decision"] == "SOFT_BLOCK"

    def test_meta_quality_pass(self):
        """meta_quality 高分 → PASS，meta_quality_source='meta_quality'"""
        from domains.spec_pro.contracts.gate import gate_harness_decision
        result = gate_harness_decision(
            {"passed": True},
            {"meta_quality": {
                "clarity": {"score": 85, "reasoning": "clear"},
                "completeness": {"score": 80, "reasoning": "complete"},
                "executability": {"score": 75, "reasoning": "executable"},
                "consistency": {"score": 80, "reasoning": "consistent"},
                "downstream_fitness": {"score": 80, "reasoning": "fit"},
            }}
        )
        assert result["decision"] == "PASS", f"Expected PASS, got {result['decision']}"
        assert result["meta_quality_source"] == "meta_quality"

    def test_meta_quality_warn(self):
        """meta_quality 中等分 → WARN"""
        from domains.spec_pro.contracts.gate import gate_harness_decision
        result = gate_harness_decision(
            {"passed": True},
            {"meta_quality": {
                "clarity": {"score": 65, "reasoning": "ok"},
                "completeness": {"score": 60, "reasoning": "partial"},
                "executability": {"score": 65, "reasoning": "vague"},
                "consistency": {"score": 65, "reasoning": "ok"},
                "downstream_fitness": {"score": 60, "reasoning": "weak"},
            }}
        )
        assert result["decision"] == "WARN", f"Expected WARN, got {result['decision']}"
        assert result["meta_quality_source"] == "meta_quality"

    def test_meta_quality_fallback_to_dimension_scores(self):
        """无 meta_quality 时 fallback 到 dimension_scores"""
        from domains.spec_pro.contracts.gate import gate_harness_decision
        result = gate_harness_decision(
            {"passed": True},
            {"dimension_scores": {"objective": 80}}  # 旧格式，key 不匹配元维度
        )
        # fallback 到 dimension_scores，元维度全部 default=50 → SOFT_BLOCK
        assert result["meta_quality_source"] == "dimension_scores"
        assert result["decision"] == "SOFT_BLOCK"


class TestGateLivingSpecDensity:
    """gate_living_spec_density 需求密度 Gate
    
    gate_living_spec_density 接收 Pydantic LivingSpec 对象，
    使用 spec.confirmed.objective 属性访问。
    """

    def _make_spec(self, **overrides):
        """构造测试用 Pydantic LivingSpec 对象"""
        from domains.spec_pro.contracts.living_spec import LivingSpec, LivingSpecMeta, ConfirmedLayer
        confirmed = overrides.pop("confirmed", None)
        if confirmed is None:
            confirmed = ConfirmedLayer()
        meta = LivingSpecMeta(created_at="2026-01-01", updated_at="2026-01-01")
        spec = LivingSpec(meta=meta, confirmed=confirmed, **overrides)
        return spec

    def test_complete_spec_passes(self):
        """完整 living_spec → passed=True"""
        from domains.spec_pro.contracts.gate import gate_living_spec_density
        from domains.spec_pro.contracts.living_spec import ConfirmedLayer, SuccessMetric
        confirmed = ConfirmedLayer(
            objective="构建一个完整的软件系统来满足用户需求",
            success_metrics=[SuccessMetric(metric="响应时间", target="<100ms")],
        )
        spec = self._make_spec(
            confirmed=confirmed,
            requirement_index=[{"id": "REQ-1", "content": "test"}],
            core_summary="这是一个足够长的核心需求摘要，超过了十个字符",
        )
        result = gate_living_spec_density(spec)
        assert result["passed"] is True, f"issues: {result['issues']}"
        assert result["score"] >= 0.8

    def test_missing_objective_fails(self):
        """缺少 objective → passed=False"""
        from domains.spec_pro.contracts.gate import gate_living_spec_density
        from domains.spec_pro.contracts.living_spec import ConfirmedLayer, SuccessMetric
        confirmed = ConfirmedLayer(
            objective="",
            success_metrics=[SuccessMetric(metric="响应时间", target="<100ms")],
        )
        spec = self._make_spec(
            confirmed=confirmed,
            requirement_index=[{"id": "REQ-1", "content": "test"}],
            core_summary="这是一个足够长的核心需求摘要内容信息",
        )
        result = gate_living_spec_density(spec)
        assert result["passed"] is False
        assert any("objective" in i for i in result["issues"])

    def test_missing_narrative_and_core_summary_fails(self):
        """core_summary 和 narrative 都为空 → passed=False"""
        from domains.spec_pro.contracts.gate import gate_living_spec_density
        from domains.spec_pro.contracts.living_spec import ConfirmedLayer, SuccessMetric
        confirmed = ConfirmedLayer(
            objective="构建一个完整的软件系统来满足用户需求",
            success_metrics=[SuccessMetric(metric="响应时间", target="<100ms")],
        )
        spec = self._make_spec(
            confirmed=confirmed,
            requirement_index=[{"id": "REQ-1", "content": "test"}],
            core_summary="",
            narrative="",
        )
        result = gate_living_spec_density(spec)
        assert result["passed"] is False
        assert any("narrative" in i or "core_summary" in i for i in result["issues"])

    def test_missing_requirement_index_fails(self):
        """缺少 requirement_index → passed=False"""
        from domains.spec_pro.contracts.gate import gate_living_spec_density
        from domains.spec_pro.contracts.living_spec import ConfirmedLayer, SuccessMetric
        confirmed = ConfirmedLayer(
            objective="构建一个完整的软件系统来满足用户需求",
            success_metrics=[SuccessMetric(metric="响应时间", target="<100ms")],
        )
        spec = self._make_spec(
            confirmed=confirmed,
            requirement_index=[],
            core_summary="这是一个足够长的核心需求摘要内容信息",
        )
        result = gate_living_spec_density(spec)
        assert result["passed"] is False

    def test_missing_success_metrics_fails(self):
        """缺少 success_metrics → passed=False"""
        from domains.spec_pro.contracts.gate import gate_living_spec_density
        from domains.spec_pro.contracts.living_spec import ConfirmedLayer
        confirmed = ConfirmedLayer(
            objective="构建一个完整的软件系统来满足用户需求",
            success_metrics=[],
        )
        spec = self._make_spec(
            confirmed=confirmed,
            requirement_index=[{"id": "REQ-1", "content": "test"}],
            core_summary="这是一个足够长的核心需求摘要内容信息",
        )
        result = gate_living_spec_density(spec)
        assert result["passed"] is False


# ============================================================================
# 3. 数据合并 (merge_spec.py)
# ============================================================================

class TestMergeConfirmed:
    """merge_confirmed 合并逻辑"""

    def test_merge_terms_by_name_dedup(self):
        """合并 terms — 这里测的是 merge_confirmed 对 users 按 role 去重"""
        from domains.spec_pro.merge_spec import merge_confirmed
        spec = {"confirmed": {"users": [{"role": "开发者", "key_needs": "快速"}]}}
        updates = {"users": [{"role": "运维", "key_needs": "稳定"}]}
        merge_confirmed(spec, updates)
        roles = {u["role"] for u in spec["confirmed"]["users"]}
        assert roles == {"开发者", "运维"}

    def test_merge_users_duplicate_role_ignored(self):
        """重复 role 的 user 不会重复添加"""
        from domains.spec_pro.merge_spec import merge_confirmed
        spec = {"confirmed": {"users": [{"role": "开发者", "key_needs": "快速"}]}}
        updates = {"users": [{"role": "开发者", "key_needs": "新需求"}]}
        merge_confirmed(spec, updates)
        assert len(spec["confirmed"]["users"]) == 1

    def test_merge_capabilities(self):
        """合并 capabilities 子列表"""
        from domains.spec_pro.merge_spec import merge_confirmed
        spec = {"confirmed": {"capabilities": {"always_do": ["A"], "should_do": [], "never_do": []}}}
        updates = {"capabilities": {"always_do": ["B"], "should_do": ["C"], "never_do": []}}
        merge_confirmed(spec, updates)
        caps = spec["confirmed"]["capabilities"]
        assert "B" in caps["always_do"]
        assert "C" in caps["should_do"]

    def test_merge_empty_with_new_data(self):
        """空列表 + 新数据 → 正确合并"""
        from domains.spec_pro.merge_spec import merge_confirmed
        spec = {"confirmed": {}}
        updates = {
            "objective": "新项目目标",
            "pain_points": ["痛点1", "痛点2"],
            "users": [{"role": "管理员"}],
        }
        merge_confirmed(spec, updates)
        assert spec["confirmed"]["objective"] == "新项目目标"
        assert len(spec["confirmed"]["pain_points"]) == 2
        assert len(spec["confirmed"]["users"]) == 1

    def test_merge_constraints_dict(self):
        """constraints 按 key 合并"""
        from domains.spec_pro.merge_spec import merge_confirmed
        spec = {"confirmed": {"constraints": {"perf": "<100ms"}}}
        updates = {"constraints": {"sec": "encrypt", "perf": "<50ms"}}
        merge_confirmed(spec, updates)
        assert spec["confirmed"]["constraints"]["perf"] == "<50ms"  # 覆盖
        assert spec["confirmed"]["constraints"]["sec"] == "encrypt"  # 新增

    def test_merge_invalid_spec_raises(self):
        """spec 非 dict → raise ValueError"""
        from domains.spec_pro.merge_spec import merge_confirmed
        with pytest.raises(ValueError, match="spec must be dict"):
            merge_confirmed("not_a_dict", {})


class TestNormalizeQualityDimensions:
    """_normalize_quality_dimensions 数组→dict 转换（P1-4）"""

    def test_array_input_converts_to_dict(self):
        """数组输入 → dict 输出"""
        from domains.spec_pro.merge_spec import _normalize_quality_dimensions
        arr = [
            {"name": "clarity", "score": 85, "reasoning": "清晰"},
            {"name": "completeness", "score": 70, "reasoning": "较完整"},
        ]
        result = _normalize_quality_dimensions(arr)
        assert isinstance(result, dict)
        assert result["clarity"]["score"] == 85
        assert result["completeness"]["reasoning"] == "较完整"

    def test_dict_input_passthrough(self):
        """dict 输入 → 直接返回"""
        from domains.spec_pro.merge_spec import _normalize_quality_dimensions
        d = {"clarity": {"score": 85, "reasoning": "清晰"}}
        result = _normalize_quality_dimensions(d)
        assert result is d  # 同一个对象

    def test_empty_input_returns_empty_dict(self):
        """空输入 → 空 dict"""
        from domains.spec_pro.merge_spec import _normalize_quality_dimensions
        assert _normalize_quality_dimensions([]) == {}
        assert _normalize_quality_dimensions(None) == {}

    def test_array_with_dimension_key(self):
        """数组元素用 'dimension' 而非 'name' 作为 key"""
        from domains.spec_pro.merge_spec import _normalize_quality_dimensions
        arr = [{"dimension": "safety", "score": 90, "reasoning": "安全"}]
        result = _normalize_quality_dimensions(arr)
        assert "safety" in result
        assert result["safety"]["score"] == 90

    def test_array_missing_score_defaults(self):
        """数组元素缺少 score → 默认 50"""
        from domains.spec_pro.merge_spec import _normalize_quality_dimensions
        arr = [{"name": "perf", "reasoning": "性能"}]
        result = _normalize_quality_dimensions(arr)
        assert result["perf"]["score"] == 50


# ============================================================================
# 4. 域推断 (domain_context.py)
# ============================================================================

class TestBuildDomainContext:
    """build_domain_context 域上下文构建"""

    def test_software_returns_nonempty(self):
        """'software' → 非空字符串"""
        from domains.spec_pro.domain_context import build_domain_context
        result = build_domain_context("software")
        assert isinstance(result, str)
        assert len(result) > 0
        assert "软件" in result or "software" in result.lower() or "领域" in result

    def test_investment_returns_nonempty(self):
        """'investment' → 非空字符串"""
        from domains.spec_pro.domain_context import build_domain_context
        result = build_domain_context("investment")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_none_returns_empty(self):
        """None → 空字符串"""
        from domains.spec_pro.domain_context import build_domain_context
        result = build_domain_context(None)
        assert result == ""

    def test_unknown_falls_back_to_software(self):
        """'unknown' → 回退到 software 配置，返回非空字符串"""
        from domains.spec_pro.domain_context import build_domain_context
        result = build_domain_context("unknown")
        # domain_loader 对未知域回退到 software
        assert isinstance(result, str)
        assert len(result) > 0

    def test_empty_string_returns_empty(self):
        """'' → 空字符串"""
        from domains.spec_pro.domain_context import build_domain_context
        result = build_domain_context("")
        assert result == ""
