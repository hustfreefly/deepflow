"""
ResearchPro 单元测试 — ResearchProOrchestrator
契约: cage/active/research_pro_v1.0.yaml (L1: orchestrator, RED-DC-002, RED-DC-003, RED-DC-005)
"""
import os
import json
import tempfile
import shutil
import unittest
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'skills', 'deep-research'))
from lib.orchestrator import ResearchProOrchestrator

# 向后兼容别名
Orchestrator = ResearchProOrchestrator

QUERY = "分析贵州茅台2024年投资价值与风险评估"


class TestOrchestrator(unittest.TestCase):
    """ResearchProOrchestrator 单元测试。"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.bp = os.path.join(self.tmpdir, 'test_session')

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    # --- __init__() ---

    def test_init_creates_directories(self):
        """__init__() 创建必要目录。"""
        orch = ResearchProOrchestrator(mode='quick', base_path=self.bp)
        self.assertTrue(os.path.isdir(self.bp))
        self.assertTrue(os.path.isdir(os.path.join(self.bp, 'research')))
        self.assertTrue(os.path.isdir(os.path.join(self.bp, 'report')))

    def test_init_creates_state_json(self):
        """__init__() 创建 state.json。"""
        orch = ResearchProOrchestrator(mode='quick', base_path=self.bp)
        state_path = os.path.join(self.bp, 'state.json')
        self.assertTrue(os.path.exists(state_path))
        with open(state_path) as f:
            state = json.load(f)
        self.assertEqual(state['mode'], 'quick')
        self.assertEqual(state['current_stage'], 'planning')

    def test_init_quick_mode(self):
        """快速模式初始化。"""
        orch = ResearchProOrchestrator(mode='quick', base_path=self.bp)
        self.assertEqual(orch.mode, 'quick')

    def test_init_standard_mode(self):
        """标准模式初始化。"""
        orch = ResearchProOrchestrator(mode='standard', base_path=self.bp)
        self.assertEqual(orch.mode, 'standard')

    def test_init_default_mode_is_standard(self):
        """P0-3: 默认 mode 是 standard。"""
        orch = ResearchProOrchestrator(base_path=self.bp)
        self.assertEqual(orch.mode, 'standard')

    # --- init_session() ---

    def test_init_session_returns_dict(self):
        """init_session() 返回 dict。"""
        orch = ResearchProOrchestrator(mode='quick', base_path=self.bp)
        result = orch.init_session(QUERY)
        self.assertIsInstance(result, dict)
        self.assertIn('analysis_plan', result)
        self.assertIn('state', result)

    def test_init_session_stage_confirming(self):
        """init_session() 后 state 变为 confirming。"""
        orch = ResearchProOrchestrator(mode='quick', base_path=self.bp)
        result = orch.init_session(QUERY)
        self.assertEqual(result['state']['current_stage'], 'confirming')

    def test_init_session_saves_plan(self):
        """init_session() 保存 analysis_plan.json。"""
        orch = ResearchProOrchestrator(mode='quick', base_path=self.bp)
        orch.init_session(QUERY)
        plan_path = os.path.join(self.bp, 'analysis_plan.json')
        self.assertTrue(os.path.exists(plan_path))
        with open(plan_path) as f:
            plan = json.load(f)
        self.assertIn('keyword_groups', plan)
        self.assertIn('subtasks', plan)

    def test_init_session_empty_query_raises(self):
        """空查询抛出 ValueError (Input Guard)。"""
        orch = ResearchProOrchestrator(mode='quick', base_path=self.bp)
        with self.assertRaises(ValueError):
            orch.init_session("")

    def test_init_session_short_query_raises(self):
        """过短查询抛出 ValueError (Input Guard, ≥10字符)。"""
        orch = ResearchProOrchestrator(mode='quick', base_path=self.bp)
        with self.assertRaises(ValueError):
            orch.init_session("abc")

    def test_init_session_long_query_truncated(self):
        """超长查询被截断 (Input Guard)。"""
        orch = ResearchProOrchestrator(mode='quick', base_path=self.bp)
        long_query = "测试" * 3000
        result = orch.init_session(long_query)
        self.assertEqual(result['state']['current_stage'], 'confirming')

    # --- confirm_plan() (P0-1: action enum) ---

    def test_confirm_plan_approve(self):
        """P0-1: action=approve 后 state 变为 executing。"""
        orch = ResearchProOrchestrator(mode='quick', base_path=self.bp)
        orch.init_session(QUERY)
        result = orch.confirm_plan({"action": "approve"})
        self.assertEqual(result['state']['current_stage'], 'executing')

    def test_confirm_plan_cancel(self):
        """P0-1: action=cancel 后 state 变为 cancelled。"""
        orch = ResearchProOrchestrator(mode='quick', base_path=self.bp)
        orch.init_session(QUERY)
        result = orch.confirm_plan({"action": "cancel"})
        self.assertEqual(result['state']['current_stage'], 'cancelled')

    def test_confirm_plan_modify(self):
        """P0-1: action=modify 应用修改后回到 confirming。"""
        orch = ResearchProOrchestrator(mode='quick', base_path=self.bp)
        orch.init_session(QUERY)
        mods = [{"field": "estimated_time_minutes", "value": 20}]
        result = orch.confirm_plan({"action": "modify", "modifications": mods})
        self.assertIn('message', result)
        self.assertIn('修改', result['message'])

    def test_confirm_plan_invalid_action(self):
        """P0-1: 无效 action 抛出 ValueError。"""
        orch = ResearchProOrchestrator(mode='quick', base_path=self.bp)
        orch.init_session(QUERY)
        with self.assertRaises(ValueError):
            orch.confirm_plan({"action": "invalid"})

    # --- execute_research() ---

    def test_execute_research_quick_mode(self):
        """快速模式执行研究。"""
        orch = ResearchProOrchestrator(mode='quick', base_path=self.bp)
        orch.init_session(QUERY)
        orch.confirm_plan({"action": "approve"})
        result = orch.execute_research()
        self.assertIn('sources_count', result)
        self.assertIn('batches', result)
        self.assertGreaterEqual(result['sources_count'], 1)

    def test_execute_research_standard_mode(self):
        """标准模式执行研究 (更多 sources)。"""
        orch = ResearchProOrchestrator(mode='standard', base_path=self.bp)
        orch.init_session(QUERY)
        orch.confirm_plan({"action": "approve"})
        result = orch.execute_research()
        self.assertGreaterEqual(result['sources_count'], 3)

    def test_execute_research_wrong_stage(self):
        """未确认就执行研究返回错误。"""
        orch = ResearchProOrchestrator(mode='quick', base_path=self.bp)
        orch.init_session(QUERY)
        result = orch.execute_research()
        self.assertIn('error', result)

    # --- generate_report() ---

    def test_generate_report(self):
        """生成报告。"""
        orch = ResearchProOrchestrator(mode='quick', base_path=self.bp)
        orch.init_session(QUERY)
        orch.confirm_plan({"action": "approve"})
        orch.execute_research()
        result = orch.generate_report()
        self.assertIn('report_path', result)
        self.assertIn('citations', result)
        self.assertEqual(result['state']['current_stage'], 'completed')

    def test_generate_report_file_exists(self):
        """报告文件存在。"""
        orch = ResearchProOrchestrator(mode='quick', base_path=self.bp)
        orch.init_session(QUERY)
        orch.confirm_plan({"action": "approve"})
        orch.execute_research()
        result = orch.generate_report()
        self.assertTrue(os.path.exists(result['report_path']))

    def test_generate_report_contains_citations(self):
        """报告包含 [N] 引用标记。"""
        orch = ResearchProOrchestrator(mode='quick', base_path=self.bp)
        orch.init_session(QUERY)
        orch.confirm_plan({"action": "approve"})
        orch.execute_research()
        result = orch.generate_report()
        with open(result['report_path']) as f:
            content = f.read()
        import re
        citations = re.findall(r'\[\d+\]', content)
        self.assertGreater(len(citations), 0)

    def test_generate_report_wrong_stage(self):
        """未执行研究就生成报告返回错误。"""
        orch = ResearchProOrchestrator(mode='quick', base_path=self.bp)
        orch.init_session(QUERY)
        orch.confirm_plan({"action": "approve"})
        result = orch.generate_report()
        self.assertIn('error', result)

    # --- get_status() ---

    def test_get_status(self):
        """get_status() 返回当前状态。"""
        orch = ResearchProOrchestrator(mode='quick', base_path=self.bp)
        status = orch.get_status()
        self.assertIn('current_stage', status)
        self.assertEqual(status['current_stage'], 'planning')

    # --- resume_from_state() ---

    def test_resume_from_state(self):
        """resume_from_state() 返回下一步操作。"""
        orch = ResearchProOrchestrator(mode='quick', base_path=self.bp)
        orch.init_session(QUERY)
        result = orch.resume_from_state()
        self.assertIn('state', result)
        self.assertIn('next_action', result)
        self.assertEqual(result['next_action'], 'confirm_plan')

    # --- RED-DC-002 合规 ---

    def test_red_dc_002_quick_no_spawn(self):
        """RED-DC-002: 快速模式不 spawn 子 Agent。"""
        orch = ResearchProOrchestrator(mode='quick', base_path=self.bp)
        orch.init_session(QUERY)
        orch.confirm_plan({"action": "approve"})
        result = orch.execute_research()
        self.assertNotIn('subagents', orch.state)

    # --- RED-DC-003 合规 ---

    def test_red_dc_003_atomic_write(self):
        """RED-DC-003: state.json 原子写入。"""
        orch = ResearchProOrchestrator(mode='quick', base_path=self.bp)
        orch.init_session(QUERY)
        tmp_path = os.path.join(self.bp, 'state.json.tmp')
        self.assertFalse(os.path.exists(tmp_path))
        state_path = os.path.join(self.bp, 'state.json')
        with open(state_path) as f:
            state = json.load(f)
        self.assertIsInstance(state, dict)

    # --- RED-DC-005 合规 ---

    def test_red_dc_005_citation_verification(self):
        """RED-DC-005: 报告生成前执行引用验证。"""
        orch = ResearchProOrchestrator(mode='quick', base_path=self.bp)
        orch.init_session(QUERY)
        orch.confirm_plan({"action": "approve"})
        orch.execute_research()
        result = orch.generate_report()
        self.assertIn('citations', result)

    # --- P0-5: state.json JSON 异常处理 ---

    def test_corrupted_state_json_handled(self):
        """P0-5: 损坏的 state.json 不崩溃。"""
        os.makedirs(self.bp, exist_ok=True)
        os.makedirs(os.path.join(self.bp, 'research'), exist_ok=True)
        os.makedirs(os.path.join(self.bp, 'report'), exist_ok=True)
        with open(os.path.join(self.bp, 'state.json'), 'w') as f:
            f.write('{invalid json}}}')
        orch = ResearchProOrchestrator(mode='quick', base_path=self.bp)
        # Should not raise, should create fresh state
        self.assertEqual(orch.state['current_stage'], 'planning')


class TestOrchestratorFullPipeline(unittest.TestCase):
    """ResearchProOrchestrator 完整管线集成测试。"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_full_pipeline_quick(self):
        """快速模式完整管线。"""
        bp = os.path.join(self.tmpdir, 'quick_test')
        orch = ResearchProOrchestrator(mode='quick', base_path=bp)

        r1 = orch.init_session(QUERY)
        self.assertEqual(r1['state']['current_stage'], 'confirming')

        r2 = orch.confirm_plan({"action": "approve"})
        self.assertEqual(r2['state']['current_stage'], 'executing')

        r3 = orch.execute_research()
        self.assertGreater(r3['sources_count'], 0)

        r4 = orch.generate_report()
        self.assertEqual(r4['state']['current_stage'], 'completed')
        self.assertTrue(os.path.exists(r4['report_path']))

    def test_full_pipeline_standard(self):
        """标准模式完整管线。"""
        bp = os.path.join(self.tmpdir, 'standard_test')
        orch = ResearchProOrchestrator(mode='standard', base_path=bp)

        r1 = orch.init_session(QUERY)
        self.assertEqual(r1['state']['current_stage'], 'confirming')

        r2 = orch.confirm_plan({"action": "approve"})
        self.assertEqual(r2['state']['current_stage'], 'executing')

        r3 = orch.execute_research()
        self.assertGreater(r3['sources_count'], 0)

        r4 = orch.generate_report()
        self.assertEqual(r4['state']['current_stage'], 'completed')

    def test_cancel_pipeline(self):
        """取消管线。"""
        bp = os.path.join(self.tmpdir, 'cancel_test')
        orch = ResearchProOrchestrator(mode='quick', base_path=bp)

        orch.init_session(QUERY)
        r2 = orch.confirm_plan({"action": "cancel"})
        self.assertEqual(r2['state']['current_stage'], 'cancelled')


if __name__ == '__main__':
    unittest.main()
