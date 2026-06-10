"""
ResearchPro 单元测试 — ResearchProOrchestrator
契约: cage/active/research_pro_v1.0.yaml (L1: orchestrator, RED-DC-002, RED-DC-003, RED-DC-005)
"""
import os
import json
import tempfile
import shutil
import unittest
import time
from datetime import datetime, timedelta
import threading

import domains.research_pro.orchestrator as orchestrator_module
from domains.research_pro.orchestrator import (
    DDGS_TIMEOUT_SECONDS,
    MAX_SUBTASKS,
    MODE_C_MAX_WORKERS,
    ORCH_FETCH_TIMEOUT,
    QUERY_MAX_LENGTH,
    QUERY_MIN_LENGTH,
    SUMMARY_MAX_LENGTH,
    ResearchProOrchestrator,
)

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
        self.assertEqual(len(result['state']['query']), QUERY_MAX_LENGTH)

    def test_input_and_fetch_defaults_use_module_constants(self):
        orch = ResearchProOrchestrator(mode='quick', base_path=self.bp)
        self.assertEqual(orch._fetcher.timeout, ORCH_FETCH_TIMEOUT)
        with self.assertRaisesRegex(ValueError, f"至少需要 {QUERY_MIN_LENGTH} 个字符"):
            orch.init_session("x" * (QUERY_MIN_LENGTH - 1))

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
        self.assertEqual(result['state']['stage_status'], 'cancelled')

    def test_confirm_plan_timeout_stage_status_cancelled(self):
        """确认超时取消时 stage_status 统一为 cancelled。"""
        orch = ResearchProOrchestrator(mode='quick', base_path=self.bp)
        orch.init_session(QUERY)
        orch._update_state({
            "confirmation_deadline_at": (datetime.now() - timedelta(seconds=1)).isoformat()
        })
        result = orch.confirm_plan({"action": "approve"})
        self.assertFalse(result["success"])
        self.assertEqual(result['state']['current_stage'], 'cancelled')
        self.assertEqual(result['state']['stage_status'], 'cancelled')

    def test_confirm_plan_modify(self):
        """P0-1: action=modify 应用修改后回到 confirming。"""
        orch = ResearchProOrchestrator(mode='quick', base_path=self.bp)
        orch.init_session(QUERY)
        mods = [{"field": "estimated_time_minutes", "value": 20}]
        result = orch.confirm_plan({"action": "modify", "modifications": mods})
        self.assertIn('message', result)
        self.assertIn('修改', result['message'])

    def test_confirm_plan_modify_rejects_too_many_subtasks(self):
        """modify 时 subtasks 最多 20 个。"""
        orch = ResearchProOrchestrator(mode='quick', base_path=self.bp)
        orch.init_session(QUERY)
        subtasks = [{"id": i, "topic": f"T{i}"} for i in range(MAX_SUBTASKS + 1)]
        with self.assertRaises(ValueError):
            orch.confirm_plan({
                "action": "modify",
                "modifications": [{"field": "subtasks", "value": subtasks}],
            })

    def test_confirm_plan_invalid_action(self):
        """P0-1: 无效 action 抛出 ValueError。"""
        orch = ResearchProOrchestrator(mode='quick', base_path=self.bp)
        orch.init_session(QUERY)
        with self.assertRaises(ValueError):
            orch.confirm_plan({"action": "invalid"})

    def test_confirm_plan_wrong_stage(self):
        """P1-1: 只能在 confirming 阶段确认计划。"""
        orch = ResearchProOrchestrator(mode='quick', base_path=self.bp)
        result = orch.confirm_plan({"action": "approve"})
        self.assertFalse(result["success"])
        self.assertIn("当前阶段是planning", result["error"])
        self.assertIn("只能在confirming阶段确认计划", result["error"])
        self.assertEqual(result["state"]["current_stage"], "planning")

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
        self.assertFalse(result["success"])
        self.assertIn('error', result)
        self.assertIn("只能在executing阶段执行研究", result["error"])

    def test_execute_research_enforces_search_and_fetch_budgets(self):
        """time_budgets.json 的 search/fetch 调用上限在搜索循环内生效。"""
        class FakeResponse:
            status = 200
            text = "ok"

        class FakeFetcher:
            def get(self, url):
                return FakeResponse()

        orch = ResearchProOrchestrator(mode='quick', base_path=self.bp)
        orch._max_search_calls = 1
        orch._max_web_fetch_calls = 1
        orch._fetcher = FakeFetcher()
        orch._search_ddgs = lambda query, max_results: [
            {"url": "https://www.sec.gov/a", "title": "A", "snippet": "a"},
            {"url": "https://www.sec.gov/b", "title": "B", "snippet": "b"},
        ]

        orch.init_session(QUERY)
        orch.confirm_plan({"action": "approve"})
        result = orch.execute_research()

        progress = result["state"]["progress"]
        self.assertLessEqual(progress["search_calls_used"], 1)
        self.assertLessEqual(progress["web_fetch_calls_used"], 1)
        self.assertEqual(result["sources_count"], 1)

    def test_execute_research_records_new_budget_fields(self):
        """time_budgets.json 新字段进入 execution_budget 和 progress。"""
        orch = ResearchProOrchestrator(mode='quick', base_path=self.bp)
        orch.init_session(QUERY)
        orch.confirm_plan({"action": "approve"})
        result = orch.execute_research()

        budget = result["state"]["execution_budget"]
        self.assertEqual(
            set(budget["phase_timeouts"].keys()),
            {"planning", "confirming", "executing", "reporting"},
        )
        self.assertEqual(budget["progress_report_interval_seconds"], 30)
        self.assertEqual(budget["user_confirmation_timeout_seconds"], 86400)
        self.assertEqual(budget["max_professional_data_calls"], 2)
        self.assertIn("professional_data_calls_used", result["state"]["progress"])

    def test_mode_c_runs_subtasks_concurrently(self):
        """Mode C 使用线程池并发执行子任务。"""
        def spawn_fn(task, mode):
            time.sleep(0.2)
            return {
                "sources": [{
                    "url": f"https://example.com/{abs(hash(task))}",
                    "title": "T",
                    "content": task,
                    "quality_tier": "tier_2",
                }]
            }

        orch = ResearchProOrchestrator(mode='standard', base_path=self.bp, spawn_fn=spawn_fn)
        subtasks = [
            {"id": 1, "topic": "A"},
            {"id": 2, "topic": "B"},
            {"id": 3, "topic": "C"},
        ]
        keyword_groups = [{"base": "k1"}, {"base": "k2"}, {"base": "k3"}]

        started = time.monotonic()
        result = orch._execute_mode_c(keyword_groups, subtasks)
        elapsed = time.monotonic() - started

        self.assertLess(elapsed, 0.45)
        self.assertEqual(len(result["batches"]), 3)
        self.assertEqual(len(orch.registry.sources), 3)

    def test_mode_c_subtask_timeout_uses_fallback(self):
        """Mode C 子任务有独立 timeout，超时后走本地降级。"""
        def spawn_fn(task, mode):
            time.sleep(0.2)
            return {"sources": []}

        orch = ResearchProOrchestrator(mode='standard', base_path=self.bp, spawn_fn=spawn_fn)
        orch._time_budgets["subagent_timeouts"]["mode_C_subagent"] = 0.01
        orch._fallback_mode_c_batches = lambda index, keyword_groups: [{
            "id": f"fallback_{index}",
            "results": [],
        }]

        subtasks = [
            {"id": 1, "topic": "A"},
            {"id": 2, "topic": "B"},
            {"id": 3, "topic": "C"},
        ]

        started = time.monotonic()
        result = orch._execute_mode_c([{"base": "k"}], subtasks)
        elapsed = time.monotonic() - started

        self.assertLess(elapsed, 0.15)
        self.assertEqual([batch["id"] for batch in result["batches"]], [
            "fallback_0",
            "fallback_1",
            "fallback_2",
        ])
        self.assertGreaterEqual(len(orch.state.get("warnings", [])), 3)

    def test_mode_c_skips_invalid_sources_without_crashing(self):
        """P1-2: Mode C 子 Agent 返回缺字段 source 时跳过并记录 warning。"""
        def spawn_fn(task, mode):
            return {
                "sources": [
                    {
                        "url": "https://example.com/missing-content",
                        "title": "缺少 content",
                        "quality_tier": "tier_2",
                    },
                    {
                        "url": "https://example.com/missing-title",
                        "content": "缺少 title",
                        "quality_tier": "tier_2",
                    },
                ]
            }

        orch = ResearchProOrchestrator(mode='standard', base_path=self.bp, spawn_fn=spawn_fn)
        subtasks = [{"id": 1, "topic": "invalid sources"}]
        result = orch._execute_mode_c([{"base": "k"}], subtasks)

        self.assertEqual(len(result["batches"]), 1)
        self.assertEqual(result["batches"][0]["results"], [])
        self.assertEqual(len(orch.registry.sources), 0)
        warnings = "\n".join(orch.state.get("warnings", []))
        self.assertIn("Mode C 跳过不合规 source", warnings)
        self.assertIn("Mode C 子任务所有 source 均不合规", warnings)

    def test_mode_c_caps_subtasks_and_workers(self):
        """Mode C 最多执行 MAX_SUBTASKS 个任务，线程池最多 MODE_C_MAX_WORKERS 个 worker。"""
        active = 0
        max_active = 0
        calls = []
        lock = threading.Lock()

        def spawn_fn(task, mode):
            nonlocal active, max_active
            with lock:
                active += 1
                max_active = max(max_active, active)
                calls.append(task)
            time.sleep(0.03)
            with lock:
                active -= 1
            return {"sources": []}

        orch = ResearchProOrchestrator(mode='standard', base_path=self.bp, spawn_fn=spawn_fn)
        subtasks = [{"id": i, "topic": f"T{i}"} for i in range(MAX_SUBTASKS + 5)]
        keyword_groups = [{"base": f"k{i}"} for i in range(MAX_SUBTASKS + 5)]

        result = orch._execute_mode_c(keyword_groups, subtasks)

        self.assertEqual(len(calls), MAX_SUBTASKS)
        self.assertEqual(len(result["batches"]), MAX_SUBTASKS)
        self.assertLessEqual(max_active, MODE_C_MAX_WORKERS)
        self.assertGreater(max_active, 1)

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

    def test_standard_mode_completion_criteria_uses_new_schema(self):
        """标准模式完成标准对齐 min_data_sources/min_tier_1_sources/min_citations。"""
        orch = ResearchProOrchestrator(mode='standard', base_path=self.bp)
        orch.init_session(QUERY)
        orch.confirm_plan({"action": "approve"})
        result = orch.execute_research()
        completion = result["completion_check"]
        self.assertEqual(completion["min_sources_required"], 5)
        self.assertEqual(completion["min_tier_1_sources_required"], 2)
        self.assertEqual(completion["min_citations_required"], 8)
        self.assertIn("url_reachability_pass", completion)
        self.assertIn("required_sections_pass", completion)
        self.assertIn("citation_suspect_rate_pass", completion)
        self.assertIn("timeout_marker_pass", completion)
        self.assertIn("degradation_rules_pass", completion)

    def test_generate_report_reject_citations_completed_with_warnings(self):
        """citation recommendation=reject 时不标记为干净完成。"""
        class FakeVerifier:
            def __init__(self, registry):
                self.registry = registry

            def verify_all(self, report_md):
                return {
                    "total_citations": 3,
                    "unique_citations": 3,
                    "verification_summary": {
                        "verified": 0,
                        "unreachable": 0,
                        "not_found": 0,
                        "content_mismatch": 3,
                    },
                    "citations": [],
                    "trust_score": 0.0,
                    "recommendation": "reject",
                }

        original_verifier = orchestrator_module.CitationVerifier
        orchestrator_module.CitationVerifier = FakeVerifier
        try:
            orch = ResearchProOrchestrator(mode='quick', base_path=self.bp)
            orch.init_session(QUERY)
            orch.confirm_plan({"action": "approve"})
            orch.execute_research()
            result = orch.generate_report()
        finally:
            orchestrator_module.CitationVerifier = original_verifier

        self.assertEqual(result["state"]["current_stage"], "completed")
        self.assertEqual(result["state"]["stage_status"], "completed_with_warnings")
        self.assertIn(
            "mark_report_as_unreliable",
            result["completion_check"]["degradation_actions"],
        )

    def test_report_stage_status_clean_completion_is_completed(self):
        orch = ResearchProOrchestrator(mode='quick', base_path=self.bp)
        status = orch._report_stage_status(
            {"recommendation": "accept"},
            {"overall_pass": True},
        )
        self.assertEqual(status, "completed")

    def test_summarize_content_uses_module_constant(self):
        summary = ResearchProOrchestrator._summarize_content("A" * (SUMMARY_MAX_LENGTH + 50))
        self.assertEqual(len(summary), SUMMARY_MAX_LENGTH)

    def test_ddgs_timeout_constant_exposed(self):
        self.assertEqual(DDGS_TIMEOUT_SECONDS, 12)

    def test_completion_timeout_requires_partial_report_marker(self):
        """timeout_reached 降级规则要求报告带 partial marker。"""
        orch = ResearchProOrchestrator(mode='quick', base_path=self.bp)
        orch._update_state({"execution_started_at": datetime.now().isoformat()})
        completion = orch._evaluate_completion(
            report_md="# ResearchPro 研究报告\n\n## 摘要\nx",
            citations={
                "total_citations": 0,
                "unique_citations": 0,
                "verification_summary": {},
            },
            timeout_reached=True,
        )
        self.assertFalse(completion["timeout_marker_pass"])
        self.assertIn("output_partial_report_with_marker", completion["degradation_actions"])

    def test_completion_quality_scoring_uses_configured_thresholds(self):
        """quality_scoring 的 trust score 和 Tier 1 ratio 参与完成判定。"""
        orch = ResearchProOrchestrator(mode='quick', base_path=self.bp)
        orch.registry.register('https://sec.gov/a', 'A', 'content-a', 'tier_1')
        orch.registry.register('https://example.com/b', 'B', 'content-b', 'tier_3')

        completion = orch._evaluate_completion(
            report_md="# ResearchPro 研究报告\n\n## 摘要\nx\n\n## 核心发现\nx\n\n## 风险提示\nx\n\n## 参考资料\nx",
            citations={
                "total_citations": 3,
                "unique_citations": 3,
                "verification_summary": {"verified": 3, "unreachable": 0},
                "trust_score": 0.69,
            },
        )

        self.assertEqual(completion["min_trust_score"], 0.7)
        self.assertEqual(completion["tier_1_ratio_min"], 0.3)
        self.assertFalse(completion["trust_score_pass"])
        self.assertTrue(completion["tier_1_ratio_pass"])

    def test_generate_report_meets_min_citations(self):
        """标准模式报告草稿生成足够引用数。"""
        orch = ResearchProOrchestrator(mode='standard', base_path=self.bp)
        orch.init_session(QUERY)
        orch.confirm_plan({"action": "approve"})
        orch.execute_research()
        result = orch.generate_report()
        with open(result['report_path']) as f:
            content = f.read()
        import re
        citations = re.findall(r'\[(\d+)\]', content)
        self.assertGreaterEqual(len(citations), 8)

    def test_generate_report_wrong_stage(self):
        """未执行研究就生成报告返回错误。"""
        orch = ResearchProOrchestrator(mode='quick', base_path=self.bp)
        orch.init_session(QUERY)
        orch.confirm_plan({"action": "approve"})
        result = orch.generate_report()
        self.assertFalse(result["success"])
        self.assertIn('error', result)
        self.assertIn("只能在reporting阶段生成报告", result["error"])

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
