"""
ResearchPro 单元测试 — TierClassifier
契约: cage/active/research_pro_v1.0.yaml (L1: tier_classifier, RED-DC-006)
"""
import os
import json
import tempfile
import unittest
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'skills', 'deep-research'))
from lib.tier_classifier import TierClassifier


class TestTierClassifier(unittest.TestCase):
    """TierClassifier 单元测试。"""

    def setUp(self):
        self.tc = TierClassifier()

    # --- classify() ---

    def test_classify_returns_string(self):
        """classify() 返回 str (tier_1|tier_2|tier_3|unverified)。"""
        result = self.tc.classify('sec.gov')
        self.assertIsInstance(result, str)
        self.assertIn(result, ['tier_1', 'tier_2', 'tier_3', 'unverified'])

    def test_classify_tier_1_official(self):
        """Tier 1 官方域名正确分类。"""
        tier_1_domains = ['sec.gov', 'cninfo.com.cn', 'sse.com.cn', 'szse.cn', 'gov.cn']
        for domain in tier_1_domains:
            result = self.tc.classify(domain)
            self.assertEqual(result, 'tier_1', f"{domain} should be tier_1, got {result}")

    def test_classify_tier_1_academic(self):
        """Tier 1 学术域名正确分类。"""
        tier_1_domains = ['arxiv.org', 'nature.com']
        for domain in tier_1_domains:
            result = self.tc.classify(domain)
            self.assertEqual(result, 'tier_1', f"{domain} should be tier_1, got {result}")

    def test_classify_tier_2_media(self):
        """Tier 2 权威媒体正确分类。"""
        tier_2_domains = ['reuters.com', 'bloomberg.com', 'ft.com', 'finance.sina.com.cn']
        for domain in tier_2_domains:
            result = self.tc.classify(domain)
            self.assertEqual(result, 'tier_2', f"{domain} should be tier_2, got {result}")

    def test_classify_tier_3_community(self):
        """Tier 3 社区/论坛正确分类。"""
        tier_3_domains = ['xueqiu.com', 'reddit.com', 'weibo.com', 'zhihu.com']
        for domain in tier_3_domains:
            result = self.tc.classify(domain)
            self.assertEqual(result, 'tier_3', f"{domain} should be tier_3, got {result}")

    def test_classify_unverified_unknown(self):
        """未知域名返回 unverified。"""
        result = self.tc.classify('random-unknown-domain-12345.com')
        self.assertEqual(result, 'unverified')

    # --- get_weight() ---

    def test_get_weight_returns_float(self):
        """get_weight() 返回 float。"""
        result = self.tc.get_weight('tier_1')
        self.assertIsInstance(result, float)

    def test_get_weight_tier_1_is_1_0(self):
        """RED-DC-006: Tier 1 权重 1.0。"""
        result = self.tc.get_weight('tier_1')
        self.assertEqual(result, 1.0)

    def test_get_weight_tier_2_is_0_7(self):
        """Tier 2 权重 0.7。"""
        result = self.tc.get_weight('tier_2')
        self.assertEqual(result, 0.7)

    def test_get_weight_tier_3_is_0_4(self):
        """RED-DC-006: Tier 3 权重 0.4。"""
        result = self.tc.get_weight('tier_3')
        self.assertEqual(result, 0.4)

    def test_get_weight_unverified_default(self):
        """unverified 默认权重 0.5。"""
        result = self.tc.get_weight('unverified')
        self.assertEqual(result, 0.5)

    # --- RED-DC-006 合规 ---

    def test_red_dc_006_tier_1_higher_than_tier_3(self):
        """RED-DC-006: Tier 1 权重必须高于 Tier 3。"""
        w1 = self.tc.get_weight('tier_1')
        w3 = self.tc.get_weight('tier_3')
        self.assertGreater(w1, w3, f"Tier 1 ({w1}) must be > Tier 3 ({w3})")

    def test_red_dc_006_priority_order(self):
        """RED-DC-006: Tier 1 > Tier 2 > Tier 3。"""
        w1 = self.tc.get_weight('tier_1')
        w2 = self.tc.get_weight('tier_2')
        w3 = self.tc.get_weight('tier_3')
        self.assertGreater(w1, w2)
        self.assertGreater(w2, w3)

    # --- custom config ---

    def test_custom_config_load(self):
        """自定义配置文件加载。"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({
                'tier_1': {'weight': 1.0, 'domains': ['custom-official.com']},
                'tier_2': {'weight': 0.7, 'domains': ['custom-media.com']},
                'tier_3': {'weight': 0.4, 'domains': ['custom-forum.com']},
            }, f)
            config_path = f.name

        try:
            tc2 = TierClassifier(config_path=config_path)
            self.assertEqual(tc2.classify('custom-official.com'), 'tier_1')
            self.assertEqual(tc2.classify('custom-media.com'), 'tier_2')
            self.assertEqual(tc2.classify('custom-forum.com'), 'tier_3')
        finally:
            os.unlink(config_path)


if __name__ == '__main__':
    unittest.main()
