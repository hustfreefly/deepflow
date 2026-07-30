"""Tests for ValidationVerdict — 六维质量门维度完整性检查。"""

import pytest

from domains.deliver_pro.contracts.validation_verdict import (
    REQUIRED_DIMENSIONS,
    ScoreDimension,
    ValidationVerdict,
)


def _make_dim(score: int = 4, weight: float = 0.2) -> ScoreDimension:
    return ScoreDimension(score=score, weight=weight)


def _full_scores(score: int = 4) -> dict[str, ScoreDimension]:
    """Construct a complete 6-dimension scores dict all at `score`."""
    return {dim: _make_dim(score=score, weight=w) for dim, w in
            zip(REQUIRED_DIMENSIONS, [0.25, 0.25, 0.20, 0.15, 0.10, 0.05])}


# --- C1: 单维度高分不应通过六维质量门 ---

class TestDimensionCompleteness:
    """缺失维度 → FAIL，无论分数多高。"""

    def test_single_dimension_high_score_fails(self):
        """单维度 score=5，weighted_score=5.0 → 必须 FAIL。"""
        scores = {"completeness": _make_dim(score=5, weight=1.0)}
        verdict = ValidationVerdict.compute_verdict(
            weighted_score=5.0, scores=scores,
        )
        assert verdict == "FAIL"

    def test_two_dimensions_high_score_fails(self):
        """两个维度高分 → 仍然 FAIL。"""
        scores = {
            "completeness": _make_dim(score=5, weight=0.5),
            "correctness": _make_dim(score=5, weight=0.5),
        }
        verdict = ValidationVerdict.compute_verdict(
            weighted_score=5.0, scores=scores,
        )
        assert verdict == "FAIL"

    def test_five_dimensions_fails(self):
        """缺一个维度 → FAIL。"""
        scores = _full_scores(score=4)
        del scores["professionalism"]  # 移除权重最低的维度
        weighted = ValidationVerdict.compute_weighted_score(scores)
        verdict = ValidationVerdict.compute_verdict(
            weighted_score=weighted, scores=scores,
        )
        assert verdict == "FAIL"

    def test_empty_scores_fails(self):
        """空 scores → FAIL。"""
        verdict = ValidationVerdict.compute_verdict(
            weighted_score=0.0, scores={},
        )
        assert verdict == "FAIL"


# --- 向后兼容：六维完整时行为不变 ---

class TestFullDimensionsBackwardCompat:
    """六维完整时，原有阈值逻辑不变。"""

    def test_all_high_scores_pass(self):
        scores = _full_scores(score=5)
        weighted = ValidationVerdict.compute_weighted_score(scores)
        verdict = ValidationVerdict.compute_verdict(
            weighted_score=weighted, scores=scores,
        )
        assert verdict == "PASS"

    def test_all_score_4_pass(self):
        """All score=4 → weighted=4.0 ≥ 3.5, min=4 ≥ 3 → PASS."""
        scores = _full_scores(score=4)
        weighted = ValidationVerdict.compute_weighted_score(scores)
        verdict = ValidationVerdict.compute_verdict(
            weighted_score=weighted, scores=scores,
        )
        assert verdict == "PASS"

    def test_all_score_3_conditional(self):
        """All score=3 → weighted=3.0 < 3.5 → CONDITIONAL (not PASS)."""
        scores = _full_scores(score=3)
        weighted = ValidationVerdict.compute_weighted_score(scores)
        verdict = ValidationVerdict.compute_verdict(
            weighted_score=weighted, scores=scores,
        )
        assert verdict == "CONDITIONAL"

    def test_all_score_2_fail(self):
        """All score=2 → weighted=2.0 < 3.0 → FAIL."""
        scores = _full_scores(score=2)
        weighted = ValidationVerdict.compute_weighted_score(scores)
        verdict = ValidationVerdict.compute_verdict(
            weighted_score=weighted, scores=scores,
        )
        assert verdict == "FAIL"

    def test_all_score_1_fail(self):
        scores = _full_scores(score=1)
        weighted = ValidationVerdict.compute_weighted_score(scores)
        verdict = ValidationVerdict.compute_verdict(
            weighted_score=weighted, scores=scores,
        )
        assert verdict == "FAIL"

    def test_mixed_high_scores_pass(self):
        """大部分高分，加权≥3.5 且 min≥3 → PASS。"""
        scores = _full_scores(score=4)
        scores["professionalism"] = _make_dim(score=3, weight=0.05)
        weighted = ValidationVerdict.compute_weighted_score(scores)
        verdict = ValidationVerdict.compute_verdict(
            weighted_score=weighted, scores=scores,
        )
        # weighted ≈ 3.95, min=3 → PASS
        assert verdict == "PASS"

    def test_mixed_low_scores_fail(self):
        """一个维度拉低到2，加权<3.0 → FAIL。"""
        scores = _full_scores(score=3)
        scores["correctness"] = _make_dim(score=2, weight=0.25)
        weighted = ValidationVerdict.compute_weighted_score(scores)
        verdict = ValidationVerdict.compute_verdict(
            weighted_score=weighted, scores=scores,
        )
        # weighted=2.75, min=2 → weighted < 3.0 → FAIL
        assert verdict == "FAIL"


# --- compute_weighted_score 不受影响 ---

class TestWeightedScore:
    def test_empty_scores_zero(self):
        assert ValidationVerdict.compute_weighted_score({}) == 0.0

    def test_single_dimension(self):
        scores = {"completeness": _make_dim(score=4, weight=1.0)}
        assert ValidationVerdict.compute_weighted_score(scores) == pytest.approx(4.0)

    def test_full_dimensions(self):
        scores = _full_scores(score=4)
        assert ValidationVerdict.compute_weighted_score(scores) == pytest.approx(4.0)
