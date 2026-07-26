"""
ConservationUtils 契约笼子测试

测试策略：
- L1 确定性检查：Pydantic 验证、格式、边界
- 每个函数覆盖：正常路径 + 异常路径 + 边界条件
"""
import pytest
import json

from core.conservation_utils import (
    verify_anchors,
    ConservationResult,
    _extract_anchors,
    _extract_keywords,
    _to_text,
    ConservationUtils,
)


# ============================================================================
# verify_anchors 测试
# ============================================================================

class TestVerifyAnchors:
    """verify_anchors() 契约测试"""
    
    def test_all_preserved(self):
        """所有锚点都保留 → PASS"""
        upstream = {"semantic_anchors": ["anchor1", "anchor2", "anchor3"]}
        downstream = "This contains anchor1 and anchor2 and anchor3"
        result = verify_anchors(upstream, downstream)
        
        assert isinstance(result, ConservationResult)
        assert result.ok is True
        assert result.verdict == "PASS"
        assert result.alignment_rate == 1.0
        assert len(result.preserved) == 3
        assert len(result.lost) == 0
    
    def test_partial_preserved_pass(self):
        """部分保留（>= 0.8）→ PASS"""
        upstream = {"semantic_anchors": ["a1", "a2", "a3", "a4", "a5"]}
        downstream = "Contains a1 a2 a3 a4"  # 4/5 = 0.8
        result = verify_anchors(upstream, downstream)
        
        assert result.ok is True
        assert result.verdict == "PASS"
        assert result.alignment_rate == 0.8
    
    def test_partial_preserved_fail(self):
        """部分保留（< 0.8）→ FAIL"""
        upstream = {"semantic_anchors": ["a1", "a2", "a3", "a4", "a5"]}
        downstream = "Contains a1 a2 a3"  # 3/5 = 0.6
        result = verify_anchors(upstream, downstream)
        
        assert result.ok is False
        assert result.verdict == "FAIL"
        assert result.alignment_rate == 0.6
        assert len(result.lost) == 2
    
    def test_none_preserved(self):
        """全部丢失 → FAIL"""
        upstream = {"semantic_anchors": ["anchor1", "anchor2"]}
        downstream = "No anchors here"
        result = verify_anchors(upstream, downstream)
        
        assert result.ok is False
        assert result.verdict == "FAIL"
        assert result.alignment_rate == 0.0
        assert len(result.lost) == 2
    
    def test_empty_upstream_anchors(self):
        """上游无锚点 → FAIL"""
        upstream = {"other_field": "value"}
        downstream = "Some text"
        result = verify_anchors(upstream, downstream)
        
        assert result.ok is False
        assert result.verdict == "FAIL"
        assert result.alignment_rate == 0.0
    
    def test_custom_threshold(self):
        """自定义阈值"""
        upstream = {"semantic_anchors": ["a1", "a2", "a3", "a4", "a5"]}
        downstream = "Contains a1 a2 a3"  # 3/5 = 0.6
        
        # 阈值 0.5 → PASS
        result = verify_anchors(upstream, downstream, threshold=0.5)
        assert result.ok is True
        
        # 阈值 0.9 → FAIL
        result = verify_anchors(upstream, downstream, threshold=0.9)
        assert result.ok is False
    
    def test_case_insensitive(self):
        """大小写不敏感"""
        upstream = {"semantic_anchors": ["Anchor1"]}
        downstream = "contains anchor1"
        result = verify_anchors(upstream, downstream)
        
        assert result.ok is True
        assert result.alignment_rate == 1.0
    
    def test_json_string_input(self):
        """JSON 字符串输入"""
        upstream = json.dumps({"semantic_anchors": ["a1", "a2"]})
        downstream = "Contains a1 a2"
        result = verify_anchors(upstream, downstream)
        
        assert result.ok is True
    
    def test_list_input(self):
        """列表输入"""
        upstream = [{"semantic_anchors": ["a1"]}, {"semantic_anchors": ["a2"]}]
        downstream = "Contains a1 a2"
        result = verify_anchors(upstream, downstream)
        
        assert result.ok is True
    
    def test_plain_text_input(self):
        """纯文本输入（自动提取关键词）"""
        upstream = "Important keywords are blockchain and AI"
        downstream = "This document discusses blockchain technology and AI applications"
        result = verify_anchors(upstream, downstream)
        
        # 应该能提取到关键词并验证
        assert isinstance(result, ConservationResult)
    
    def test_result_is_pydantic(self):
        """结果是 Pydantic 模型"""
        upstream = {"semantic_anchors": ["a1"]}
        downstream = "a1"
        result = verify_anchors(upstream, downstream)
        
        assert isinstance(result, ConservationResult)
        # 验证序列化
        d = result.model_dump()
        assert "ok" in d
        assert "preserved" in d
        assert "lost" in d
        assert "alignment_rate" in d
        assert "verdict" in d
    
    def test_verdict_consistency(self):
        """verdict 和 alignment_rate 一致性"""
        upstream = {"semantic_anchors": ["a1", "a2"]}
        
        # PASS 时 alignment_rate >= 0.8
        downstream = "a1 a2"
        result = verify_anchors(upstream, downstream)
        assert result.verdict == "PASS"
        assert result.alignment_rate >= 0.8
        
        # FAIL 时 alignment_rate < 0.8
        downstream = "nothing"
        result = verify_anchors(upstream, downstream)
        assert result.verdict == "FAIL"
        assert result.alignment_rate < 0.8


# ============================================================================
# _extract_anchors 测试
# ============================================================================

class TestExtractAnchors:
    """_extract_anchors() 契约测试"""
    
    def test_dict_with_semantic_anchors(self):
        data = {"semantic_anchors": ["a1", "a2"]}
        assert _extract_anchors(data) == ["a1", "a2"]
    
    def test_dict_with_string_anchor(self):
        data = {"semantic_anchors": "single_anchor"}
        assert _extract_anchors(data) == ["single_anchor"]
    
    def test_dict_without_anchors(self):
        data = {"other_field": "value"}
        assert _extract_anchors(data) == []
    
    def test_list_input(self):
        data = [{"semantic_anchors": ["a1"]}, {"semantic_anchors": ["a2"]}]
        result = _extract_anchors(data)
        assert "a1" in result
        assert "a2" in result
    
    def test_json_string(self):
        data = '{"semantic_anchors": ["a1", "a2"]}'
        result = _extract_anchors(data)
        assert result == ["a1", "a2"]
    
    def test_plain_text(self):
        data = "Some important text with keywords"
        result = _extract_anchors(data)
        assert len(result) > 0
    
    def test_empty_input(self):
        assert _extract_anchors({}) == []
        assert _extract_anchors([]) == []
        assert _extract_anchors("") == []


# ============================================================================
# _extract_keywords 测试
# ============================================================================

class TestExtractKeywords:
    """_extract_keywords() 契约测试"""
    
    def test_basic_extraction(self):
        text = "The quick brown fox jumps over the lazy dog"
        keywords = _extract_keywords(text)
        assert "quick" in keywords
        assert "brown" in keywords
        assert "fox" in keywords
    
    def test_stop_words_filtered(self):
        text = "The quick brown fox"
        keywords = _extract_keywords(text)
        assert "the" not in keywords
    
    def test_max_keywords(self):
        text = " ".join([f"word{i}" for i in range(20)])
        keywords = _extract_keywords(text, max_keywords=5)
        assert len(keywords) <= 5
    
    def test_deduplication(self):
        text = "test test test other"
        keywords = _extract_keywords(text)
        assert keywords.count("test") == 1


# ============================================================================
# _to_text 测试
# ============================================================================

class TestToText:
    """_to_text() 契约测试"""
    
    def test_string_input(self):
        assert _to_text("hello") == "hello"
    
    def test_dict_input(self):
        result = _to_text({"key": "value"})
        assert "key" in result
        assert "value" in result
    
    def test_list_input(self):
        result = _to_text([1, 2, 3])
        assert "1" in result


# ============================================================================
# ConservationUtils 类封装测试
# ============================================================================

class TestConservationUtilsClass:
    """ConservationUtils 便捷类测试"""
    
    def test_verify(self):
        upstream = {"semantic_anchors": ["a1"]}
        downstream = "a1"
        result = ConservationUtils.verify(upstream, downstream)
        assert isinstance(result, ConservationResult)
        assert result.ok is True
