"""
ResearchPro 单元测试 — SourceRegistry
契约: cage/active/research_pro_v1.0.yaml (L1: source_registry)
"""
import json
import os
import tempfile
import unittest
import glob

import core.bootstrap
from domains.research_pro.source_registry import SourceRegistry, SUMMARY_MAX_LENGTH


class TestSourceRegistry(unittest.TestCase):
    """SourceRegistry 单元测试。"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.path = os.path.join(self.tmpdir, 'registry.json')
        self.sr = SourceRegistry(self.path)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    # --- register() ---

    def test_register_returns_incrementing_int(self):
        """register() 返回递增 ID (从 1 开始)。"""
        id1 = self.sr.register('https://a.com/1', 'Title1', 'content1', 'tier_1')
        id2 = self.sr.register('https://b.com/2', 'Title2', 'content2', 'tier_2')
        self.assertEqual(id1, 1)
        self.assertEqual(id2, 2)

    def test_register_stores_all_fields(self):
        """register() 存储完整 schema。"""
        self.sr.register('https://sec.gov/test', 'SEC Filing', 'full content here', 'tier_1', '摘要文本')
        source = self.sr.get(1)
        self.assertIsNotNone(source)
        self.assertEqual(source['id'], 1)
        self.assertEqual(source['url'], 'https://sec.gov/test')
        self.assertEqual(source['title'], 'SEC Filing')
        self.assertEqual(source['domain'], 'sec.gov')
        self.assertEqual(source['quality_tier'], 'tier_1')
        self.assertEqual(source['summary'], '摘要文本')
        self.assertEqual(source['verification_status'], 'pending')
        self.assertIsNone(source['verification_detail'])
        self.assertIn('content_hash', source)
        self.assertIn('fetched_at', source)

    def test_register_content_hash_sha256_16(self):
        """content_hash 是 sha256 前 16 位 hex。"""
        self.sr.register('https://a.com', 'T', 'hello world', 'tier_1')
        source = self.sr.get(1)
        self.assertEqual(len(source['content_hash']), 16)
        # sha256('hello world')[:16] = 'b94d27b9934d3e08'
        import hashlib
        expected = hashlib.sha256('hello world'.encode('utf-8')).hexdigest()[:16]
        self.assertEqual(source['content_hash'], expected)

    def test_register_domain_extraction(self):
        """domain 从 URL 正确提取。"""
        self.sr.register('https://finance.sina.com.cn/stock/123', 'T', 'c', 'tier_2')
        source = self.sr.get(1)
        self.assertEqual(source['domain'], 'finance.sina.com.cn')

    def test_register_summary_truncated_200(self):
        """summary 截断到 SUMMARY_MAX_LENGTH。"""
        long_summary = 'A' * 300
        self.sr.register('https://a.com', 'T', 'c', 'tier_1', long_summary)
        source = self.sr.get(1)
        self.assertEqual(len(source['summary']), SUMMARY_MAX_LENGTH)

    # --- get() ---

    def test_get_existing_source(self):
        """get() 返回正确条目。"""
        self.sr.register('https://a.com', 'Title', 'content', 'tier_1')
        source = self.sr.get(1)
        self.assertEqual(source['title'], 'Title')

    def test_get_nonexistent_source(self):
        """get() 不存在时返回 None。"""
        result = self.sr.get(999)
        self.assertIsNone(result)

    def test_get_returns_deep_copy(self):
        """get() 返回深拷贝，调用方不能修改 Registry 内部状态。"""
        self.sr.register('https://a.com', 'Title', 'content', 'tier_1')
        source = self.sr.get(1)
        source['title'] = 'mutated'
        self.assertEqual(self.sr.get(1)['title'], 'Title')

    # --- verify_all() ---

    def test_verify_all_returns_dict(self):
        """verify_all() 返回 dict {verified, failed, suspect}。"""
        result = self.sr.verify_all()
        self.assertIsInstance(result, dict)
        self.assertIn('verified', result)
        self.assertIn('failed', result)
        self.assertIn('suspect', result)

    def test_verify_all_empty_registry(self):
        """verify_all() 空 Registry 返回全 0。"""
        result = self.sr.verify_all()
        self.assertEqual(result, {'verified': 0, 'failed': 0, 'suspect': 0})

    def test_verify_all_counts_pending(self):
        """verify_all() 正确统计 pending 状态 (不计入 verified/failed/suspect)。"""
        self.sr.register('https://a.com', 'T', 'c', 'tier_1')
        result = self.sr.verify_all()
        # pending 不在 verified/failed/suspect 中
        self.assertEqual(result['verified'], 0)
        self.assertEqual(result['failed'], 0)
        self.assertEqual(result['suspect'], 0)

    # --- to_json() ---

    def test_to_json_returns_valid_json(self):
        """to_json() 返回合法 JSON。"""
        self.sr.register('https://a.com', 'T', 'c', 'tier_1')
        json_str = self.sr.to_json()
        data = json.loads(json_str)
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 1)

    def test_sources_returns_deep_copy(self):
        """sources 属性返回深拷贝列表。"""
        self.sr.register('https://a.com', 'T', 'c', 'tier_1')
        sources = self.sr.sources
        sources[0]['title'] = 'mutated'
        self.assertEqual(self.sr.get(1)['title'], 'T')

    # --- persistence ---

    def test_persistence_save_and_load(self):
        """保存后重新加载, 数据完整。"""
        self.sr.register('https://a.com', 'Title', 'content', 'tier_1')
        self.sr.register('https://b.com', 'Title2', 'content2', 'tier_2')

        # 重新加载
        sr2 = SourceRegistry(self.path)
        self.assertEqual(len(sr2.sources), 2)
        self.assertEqual(sr2.get(1)['url'], 'https://a.com')
        self.assertEqual(sr2.get(2)['url'], 'https://b.com')

    def test_corrupt_registry_is_backed_up_and_reset(self):
        """损坏 JSON 会备份为 .corrupt.{timestamp} 并空初始化。"""
        registry_path = os.path.join(self.tmpdir, 'source_registry.json')
        with open(registry_path, 'w', encoding='utf-8') as f:
            f.write('{invalid json')

        sr2 = SourceRegistry(registry_path)

        self.assertEqual(sr2.sources, [])
        backups = glob.glob(registry_path + '.corrupt.*')
        self.assertEqual(len(backups), 1)
        self.assertFalse(os.path.exists(registry_path))

    def test_atomic_write_no_tmp_remains(self):
        """原子写入后 .tmp 文件不存在。"""
        self.sr.register('https://a.com', 'T', 'c', 'tier_1')
        tmp_path = self.path + '.tmp'
        self.assertFalse(os.path.exists(tmp_path))


if __name__ == '__main__':
    unittest.main()
