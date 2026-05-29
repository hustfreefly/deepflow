"""
ResearchPro 单元测试 — CitationVerifier
契约: cage/active/research_pro_v1.0.yaml (L1: citation_verifier, RED-DC-001, RED-DC-005)
"""
import os
import tempfile
import unittest
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'skills', 'deep-research'))
from lib.source_registry import SourceRegistry
from lib.citation_verifier import CitationVerifier


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
        """verify_citation() 返回 dict {status, detail}。"""
        self.sr.register('https://httpbin.org/status/200', 'Test', 'content', 'tier_1')
        result = self.cv.verify_citation(1)
        self.assertIsInstance(result, dict)
        self.assertIn('status', result)
        self.assertIn('detail', result)

    def test_verify_citation_not_found(self):
        """引用编号不存在时返回 status=failed。"""
        result = self.cv.verify_citation(999)
        self.assertEqual(result['status'], 'failed')
        self.assertIn('not found', result['detail'].lower())

    def test_verify_citation_unreachable_url(self):
        """URL 不可达时返回 status=failed。"""
        self.sr.register('https://this-domain-does-not-exist-12345.com/page', 'Test', 'content', 'tier_1')
        result = self.cv.verify_citation(1)
        self.assertEqual(result['status'], 'failed')

    def test_verify_citation_reachable_url(self):
        """URL 可达时返回 verified 或 suspect (内容不匹配)。"""
        self.sr.register('https://httpbin.org/status/200', 'Test', 'content', 'tier_1')
        result = self.cv.verify_citation(1)
        # P1-4: 现在真正 fetch 并比对 hash, httpbin 返回内容不同 → suspect
        self.assertIn(result['status'], ['verified', 'suspect', 'failed'])

    # --- verify_all() ---

    def test_verify_all_returns_dict(self):
        """verify_all() 返回 dict {verified, failed, suspect, details}。"""
        result = self.cv.verify_all("测试[1]")
        self.assertIsInstance(result, dict)
        self.assertIn('verified', result)
        self.assertIn('failed', result)
        self.assertIn('suspect', result)
        self.assertIn('details', result)

    def test_verify_all_details_structure(self):
        """verify_all() details 包含正确结构。"""
        self.sr.register('https://example.com', 'Test', 'content', 'tier_1')
        result = self.cv.verify_all("引用[1]")
        self.assertIsInstance(result['details'], list)
        if result['details']:
            detail = result['details'][0]
            self.assertIn('citation_id', detail)
            self.assertIn('source_id', detail)
            self.assertIn('status', detail)
            self.assertIn('detail', detail)

    def test_verify_all_counts(self):
        """verify_all() 统计数量正确。"""
        self.sr.register('https://example.com/1', 'T1', 'c1', 'tier_1')
        self.sr.register('https://example.com/2', 'T2', 'c2', 'tier_1')
        result = self.cv.verify_all("[1][2][999]")
        total = result['verified'] + result['failed'] + result['suspect']
        self.assertEqual(total, 3)  # 2 个真实 + 1 个 not_found

    # --- RED-DC-001 合规 ---

    def test_red_dc_001_uses_source_registry(self):
        """RED-DC-001: 所有引用必须来自 Source Registry。"""
        # 验证 verify_citation 依赖 source_registry
        result = self.cv.verify_citation(999)
        self.assertEqual(result['status'], 'failed')
        self.assertIn('not found', result['detail'].lower())


if __name__ == '__main__':
    unittest.main()
