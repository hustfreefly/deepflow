"""
ResearchPro 单元测试 — KeywordGenerator
契约: cage/active/research_pro_v1.0.yaml (L1: keyword_generator)
"""
import os
import unittest
from datetime import datetime

from domains.research_pro.keyword_generator import KeywordGenerator


class TestKeywordGenerator(unittest.TestCase):
    """KeywordGenerator 单元测试。"""

    def setUp(self):
        self.plan = {
            "research_dimensions": ["基本面分析", "技术面分析", "行业竞争"],
            "subtopics": ["贵州茅台", "白酒行业", "消费板块"],
        }
        self.kg = KeywordGenerator(self.plan)

    # --- generate() ---

    def test_generate_returns_list(self):
        """generate() 返回 list[dict]。"""
        result = self.kg.generate()
        self.assertIsInstance(result, list)
        self.assertTrue(all(isinstance(g, dict) for g in result))

    def test_generate_quick_mode_max_5(self):
        """快速模式 max_groups=5 返回 ≤5 组。"""
        result = self.kg.generate(max_groups=5)
        self.assertLessEqual(len(result), 5)

    def test_generate_standard_mode_max_15(self):
        """标准模式 max_groups=15 返回 ≤15 组。"""
        result = self.kg.generate(max_groups=15)
        self.assertLessEqual(len(result), 15)

    def test_generate_group_structure(self):
        """每组包含 base + variants + priority。"""
        result = self.kg.generate(max_groups=3)
        for group in result:
            self.assertIn('base', group)
            self.assertIn('variants', group)
            self.assertIn('priority', group)
            self.assertIsInstance(group['base'], str)
            self.assertIsInstance(group['variants'], list)
            self.assertIsInstance(group['priority'], int)
            self.assertGreaterEqual(group['priority'], 1)
            self.assertLessEqual(group['priority'], 5)

    def test_generate_variants_max_5(self):
        """每组变体最多 5 个。"""
        result = self.kg.generate(max_groups=10)
        for group in result:
            self.assertLessEqual(len(group['variants']), 5)

    def test_generate_empty_plan(self):
        """空 plan 返回空列表。"""
        kg = KeywordGenerator({"research_dimensions": [], "subtopics": []})
        result = kg.generate()
        self.assertIsInstance(result, list)

    # --- expand() ---

    def test_expand_returns_list(self):
        """expand() 返回 list[str]。"""
        result = self.kg.expand("贵州茅台")
        self.assertIsInstance(result, list)
        self.assertTrue(all(isinstance(v, str) for v in result))

    def test_expand_min_3_variants(self):
        """expand() 至少返回 3 个变体 (含原始)。"""
        result = self.kg.expand("基本面分析")
        self.assertGreaterEqual(len(result), 3)

    def test_expand_max_5_variants(self):
        """expand() 最多返回 5 个变体。"""
        result = self.kg.expand("基本面分析")
        self.assertLessEqual(len(result), 5)

    def test_expand_includes_original(self):
        """expand() 包含原始关键词。"""
        result = self.kg.expand("贵州茅台")
        self.assertIn("贵州茅台", result)

    def test_expand_adds_time_dimension(self):
        """expand() 添加当前年份时间维度。"""
        result = self.kg.expand("财报")
        has_time = any(str(datetime.now().year) in v for v in result)
        self.assertTrue(has_time, f"Expected time dimension in {result}")

    def test_expand_deduplication(self):
        """expand() 结果无重复。"""
        result = self.kg.expand("毛利率")
        self.assertEqual(len(result), len(set(result)))

    # --- edge cases ---

    def test_single_dimension(self):
        """单个维度也能生成关键词。"""
        kg = KeywordGenerator({"research_dimensions": ["财务分析"], "subtopics": []})
        result = kg.generate(max_groups=5)
        self.assertGreaterEqual(len(result), 1)

    def test_single_subtopic(self):
        """单个子主题也能生成关键词。"""
        kg = KeywordGenerator({"research_dimensions": [], "subtopics": ["腾讯"]})
        result = kg.generate(max_groups=5)
        self.assertGreaterEqual(len(result), 1)


if __name__ == '__main__':
    unittest.main()
