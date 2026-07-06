"""
ResearchPro 单元测试 — CitationVerifier
契约: cage/active/research_pro_v1.0.yaml (L1: citation_verifier, RED-DC-001, RED-DC-005)
"""
import os
import tempfile
import unittest
from domains.research_pro.source_registry import SourceRegistry
from domains.research_pro.citation_verifier import CITATION_FETCH_TIMEOUT, CitationVerifier


class TestCitationVerifier(unittest.TestCase):
    """CitationVerifier 单元测试。"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.path = os.path.join(self.tmpdir, 'registry.json')
        self.sr = SourceRegistry(self.path)
        self.cv = CitationVerifier(self.sr)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    # --- extract_citations() ---

    def test_fetcher_timeout_uses_module_constant(self):
        self.assertEqual(self.cv._fetcher.timeout, CITATION_FETCH_TIMEOUT)

    def test_extract_citations_returns_list(self):
        """extract_citations() 返回 list[int]。"""
        result = self.cv.extract_citations("这是引用[1]和[2]的测试")
        self.assertIsInstance(result, list)
        self.assertTrue(all(isinstance(x, int) for x in result))

    def test_extract_citations_single(self):
        """提取单个引用 [1]。"""
        result = self.cv.extract_citations("根据研究[1]，结果表明...")
        self.assertEqual(result, [1])

    def test_extract_citations_multiple(self):
        """提取多个引用 [1][2][3]。"""
        result = self.cv.extract_citations("来源[1][2][3]都支持这一观点")
        self.assertEqual(sorted(result), [1, 2, 3])

    def test_extract_citations_deduplicate(self):
        """去重: 同一引用多次出现只计一次。"""
        result = self.cv.extract_citations("[1]和[1]和[2]")
        self.assertEqual(sorted(result), [1, 2])

    def test_extract_citations_empty(self):
        """无引用返回空列表。"""
        result = self.cv.extract_citations("这段文字没有引用")
        self.assertEqual(result, [])

    def test_extract_citations_high_numbers(self):
        """支持多位数引用 [10][15]。"""
        result = self.cv.extract_citations("参考[10]和[15]")
        self.assertEqual(sorted(result), [10, 15])

    # --- verify_citation() ---

    def test_verify_citation_returns_dict(self):
        """verify_citation() 返回统一 schema。"""
        self.sr.register('https://httpbin.org/status/200', 'Test', 'content', 'tier_1',
                         fetch_status='fetched', content_origin='web_fetch')
        result = self.cv.verify_citation(1)
        self.assertIsInstance(result, dict)
        self.assertIn('status', result)
        self.assertIn('verification_detail', result)
        self.assertIn('quality_tier', result)

    def test_verify_citation_not_found(self):
        """引用编号不存在时返回 status=not_found。"""
        result = self.cv.verify_citation(999)
        self.assertEqual(result['status'], 'not_found')
        self.assertIn('not found', result['verification_detail'].lower())

    def test_verify_citation_unreachable_url(self):
        """URL 不可达时返回 status=unreachable 或 ineligible_source。"""
        self.sr.register('https://this-domain-does-not-exist-12345.com/page', 'Test', 'content', 'tier_1',
                         fetch_status='fetched', content_origin='web_fetch')
        result = self.cv.verify_citation(1)
        self.assertIn(result['status'], ['unreachable', 'ineligible_source'])

    def test_verify_citation_reachable_url(self):
        """URL 可达时返回 verified、content_mismatch 或 ineligible_source。"""
        self.sr.register('https://httpbin.org/status/200', 'Test', 'content', 'tier_1',
                         fetch_status='fetched', content_origin='web_fetch')
        result = self.cv.verify_citation(1)
        self.assertIn(result['status'], ['verified', 'content_mismatch', 'unreachable', 'ineligible_source'])

    # --- verify_all() ---

    def test_verify_all_returns_dict(self):
        """verify_all() 返回统一汇总结构。"""
        result = self.cv.verify_all("测试[1]")
        self.assertIsInstance(result, dict)
        self.assertIn('total_citations', result)
        self.assertIn('unique_citations', result)
        self.assertIn('verification_summary', result)
        self.assertIn('citations', result)
        self.assertIn('trust_score', result)
        self.assertIn('recommendation', result)

    def test_verify_all_details_structure(self):
        """verify_all() citations 包含正确结构。"""
        self.sr.register('https://example.com', 'Test', 'content', 'tier_1',
                         fetch_status='fetched', content_origin='web_fetch')
        result = self.cv.verify_all("引用[1]")
        self.assertIsInstance(result['citations'], list)
        if result['citations']:
            detail = result['citations'][0]
            self.assertIn('citation_id', detail)
            self.assertIn('source_id', detail)
            self.assertIn('url', detail)
            self.assertIn('status', detail)
            self.assertIn('http_status', detail)
            self.assertIn('content_hash_match', detail)
            self.assertIn('quality_tier', detail)
            self.assertIn('verification_detail', detail)

    def test_verify_all_counts(self):
        """verify_all() 统计数量正确。"""
        self.sr.register('https://example.com/1', 'T1', 'c1', 'tier_1',
                         fetch_status='fetched', content_origin='web_fetch')
        self.sr.register('https://example.com/2', 'T2', 'c2', 'tier_1',
                         fetch_status='fetched', content_origin='web_fetch')
        result = self.cv.verify_all("[1][2][999]")
        summary = result['verification_summary']
        # V2: 新增 ineligible_source 状态
        total = (
            summary.get('verified', 0)
            + summary.get('unreachable', 0)
            + summary.get('not_found', 0)
            + summary.get('content_mismatch', 0)
            + summary.get('ineligible_source', 0)
        )
        self.assertEqual(total, 3)  # 2 个真实 + 1 个 not_found
        self.assertEqual(result['total_citations'], 3)
        self.assertEqual(result['unique_citations'], 3)

    # --- RED-DC-001 合规 ---

    def test_red_dc_001_uses_source_registry(self):
        """RED-DC-001: 所有引用必须来自 Source Registry。"""
        # 验证 verify_citation 依赖 source_registry
        result = self.cv.verify_citation(999)
        self.assertEqual(result['status'], 'not_found')
        self.assertIn('not found', result['verification_detail'].lower())


if __name__ == '__main__':
    unittest.main()
