"""
Phase 0 单元测试 — WorkerResult + FeedbackStream + ContextCompactor

运行: cd ~/.openclaw/workspace/.deepflow && python3 -m pytest tests/test_ai_native_phase0.py -v
或:   cd ~/.openclaw/workspace/.deepflow && python3 tests/test_ai_native_phase0.py
"""

import json
import sys
import os
from pathlib import Path

# Bootstrap
DEEPFLOW_HOME = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(DEEPFLOW_HOME))

from contracts.shared.worker_result import (
    WorkerResult, HelpRequest,
    parse_worker_result, parse_worker_result_safe,
    format_output_suffix,
)
from scripts.feedback_stream import FeedbackStream, ProgressReport
from scripts.context_compactor import ContextCompactor, CompactedContext


# ── WorkerResult Tests ────────────────────────────────────────────

def test_worker_result_basic():
    """基本创建"""
    r = WorkerResult(
        status="success",
        phase=3,
        phase_name="reviewers",
        artifacts={"tech_review": "stages/reviewer_technical.json"},
        summary="完成技术评审，发现 3 个架构风险",
        confidence=0.85,
        issues=["API 响应时间未定义"],
    )
    assert r.status == "success"
    assert r.phase == 3
    assert r.confidence == 0.85
    assert len(r.issues) == 1
    print("✅ test_worker_result_basic PASS")


def test_worker_result_defaults():
    """默认值"""
    r = WorkerResult()
    assert r.status == "success"
    assert r.phase == 0
    assert r.confidence == 0.5
    assert r.artifacts == {}
    assert r.issues == []
    assert r.help_needed is None
    print("✅ test_worker_result_defaults PASS")


def test_worker_result_with_help():
    """带协作请求"""
    r = WorkerResult(
        status="partial",
        phase=2,
        phase_name="architecture",
        help_needed=[
            HelpRequest(
                type="research",
                description="需要对比 Kafka vs RabbitMQ",
                priority="high",
            )
        ],
    )
    assert r.help_needed is not None
    assert len(r.help_needed) == 1
    assert r.help_needed[0].type == "research"
    print("✅ test_worker_result_with_help PASS")


def test_parse_worker_result_from_text():
    """从文本中解析 WorkerResult"""
    text = """
这是 Worker 的详细输出...
做了一些分析工作...

```json
{
    "status": "success",
    "phase": 5,
    "phase_name": "consolidator",
    "artifacts": {"report": "stages/consolidator.json"},
    "summary": "整合了 3 位评审专家的意见",
    "confidence": 0.9,
    "issues": [],
    "warnings": ["某些建议可能冲突"],
    "metrics": {"coverage": 0.85},
    "help_needed": null
}
```
"""
    result = parse_worker_result(text)
    assert result is not None
    assert result.phase == 5
    assert result.phase_name == "consolidator"
    assert result.confidence == 0.9
    assert len(result.warnings) == 1
    print("✅ test_parse_worker_result_from_text PASS")


def test_parse_worker_result_no_json():
    """无 JSON 块时返回 None"""
    text = "这是普通文本，没有 JSON 块。"
    result = parse_worker_result(text)
    assert result is None
    print("✅ test_parse_worker_result_no_json PASS")


def test_parse_worker_result_invalid_json():
    """无效 JSON 返回 None"""
    text = """
```json
{invalid json here}
```
"""
    result = parse_worker_result(text)
    assert result is None
    print("✅ test_parse_worker_result_invalid_json PASS")


def test_parse_worker_result_safe():
    """安全解析：失败时返回默认值"""
    text = "没有 JSON 的普通文本"
    result = parse_worker_result_safe(text, fallback_phase=3, fallback_name="test")
    assert result is not None
    assert result.phase == 3
    assert result.confidence == 0.3
    assert "解析失败" in result.warnings[0]
    print("✅ test_parse_worker_result_safe PASS")


def test_format_output_suffix():
    """输出后缀格式化"""
    suffix = format_output_suffix(5, "consolidator")
    assert "5" in suffix
    assert "consolidator" in suffix
    assert "```json" in suffix
    print("✅ test_format_output_suffix PASS")


def test_parse_multiple_json_blocks():
    """多个 JSON 块时取最后一个"""
    text = """
中间输出:
```json
{"status": "partial", "phase": 1, "phase_name": "early", "summary": "中间结果"}
```

最终输出:
```json
{"status": "success", "phase": 1, "phase_name": "data_collection", "summary": "最终结果", "confidence": 0.8}
```
"""
    result = parse_worker_result(text)
    assert result is not None
    assert result.status == "success"
    assert result.summary == "最终结果"
    print("✅ test_parse_multiple_json_blocks PASS")


# ── FeedbackStream Tests ─────────────────────────────────────────

def test_feedback_stream_healthy():
    """健康 Worker 的进度报告"""
    stream = FeedbackStream(total_phases=10)
    result = WorkerResult(
        status="success", phase=4, phase_name="research",
        summary="调研完成", confidence=0.85,
    )
    report = stream.on_worker_complete(result)

    assert report.health == "healthy"
    assert report.recommendation_action == "continue"
    assert report.progress == "4/10"
    assert "████" in report.progress_bar
    print("✅ test_feedback_stream_healthy PASS")


def test_feedback_stream_warning():
    """低置信度触发 warning"""
    stream = FeedbackStream(total_phases=10)
    result = WorkerResult(
        status="success", phase=3, phase_name="reviewers",
        summary="评审完成但不确定", confidence=0.6,
    )
    report = stream.on_worker_complete(result)

    assert report.health == "warning"
    print("✅ test_feedback_stream_warning PASS")


def test_feedback_stream_critical():
    """失败触发 critical"""
    stream = FeedbackStream(total_phases=10)
    result = WorkerResult(
        status="failed", phase=7, phase_name="fix",
        summary="修复失败", confidence=0.2,
        issues=["编译错误无法解决"],
    )
    report = stream.on_worker_complete(result)

    assert report.health == "critical"
    assert report.recommendation_action == "recover"
    print("✅ test_feedback_stream_critical PASS")


def test_feedback_stream_issues_warning():
    """有 issues 触发 warning"""
    stream = FeedbackStream(total_phases=10)
    result = WorkerResult(
        status="success", phase=5, phase_name="consolidator",
        summary="整合完成", confidence=0.8,
        issues=["部分建议冲突"],
    )
    report = stream.on_worker_complete(result)

    assert report.health == "warning"
    print("✅ test_feedback_stream_issues_warning PASS")


def test_feedback_stream_markdown():
    """Markdown 格式输出"""
    stream = FeedbackStream(total_phases=10)
    result = WorkerResult(
        status="success", phase=4, phase_name="research",
        summary="调研完成", confidence=0.85,
    )
    report = stream.on_worker_complete(result)
    md = report.to_markdown()

    assert "📊" in md
    assert "Phase 4" in md
    assert "research" in md
    assert "🟢" in md  # healthy
    print("✅ test_feedback_stream_markdown PASS")


def test_feedback_stream_pipeline_complete():
    """管线完成总结"""
    stream = FeedbackStream(total_phases=3)
    results = [
        WorkerResult(status="success", phase=1, confidence=0.9),
        WorkerResult(status="partial", phase=2, confidence=0.7, issues=["X"]),
        WorkerResult(status="success", phase=3, confidence=0.85),
    ]
    summary = stream.on_pipeline_complete(results)

    assert summary["summary"]["success"] == 2
    assert summary["summary"]["partial"] == 1
    assert summary["summary"]["failed"] == 0
    assert summary["verdict"] == "partial"
    print("✅ test_feedback_stream_pipeline_complete PASS")


# ── ContextCompactor Tests ───────────────────────────────────────

def test_compactor_should_compact():
    """压缩触发条件"""
    c = ContextCompactor(compact_every_n=3, token_threshold=60000)

    assert not c.should_compact(0)
    assert not c.should_compact(1)
    assert not c.should_compact(2)
    assert c.should_compact(3)  # 3 % 3 == 0
    assert not c.should_compact(4)
    assert c.should_compact(6)  # 6 % 3 == 0
    assert c.should_compact(1, estimated_tokens=70000)  # 超阈值
    print("✅ test_compactor_should_compact PASS")


def test_compactor_deterministic():
    """确定性压缩（不调 LLM）"""
    results = [
        WorkerResult(status="success", phase=1, phase_name="data_collection",
                     summary="收集了市场数据", artifacts={"data": "data/collection.json"}, confidence=0.9),
        WorkerResult(status="success", phase=2, phase_name="planning",
                     summary="制定了 5 步执行计划", artifacts={"plan": "planning.json"}, confidence=0.85),
        WorkerResult(status="partial", phase=3, phase_name="reviewers",
                     summary="3 位评审完成", confidence=0.75,
                     issues=["技术评审发现 2 个风险"]),
    ]

    c = ContextCompactor()
    ctx = c.compact_from_results(
        results=results,
        next_phase=4,
        next_phase_name="research",
        total_phases=10,
    )

    assert len(ctx.completed_phases) == 3
    assert ctx.completed_phases[2]["status"] == "partial"
    assert "技术评审发现 2 个风险" in ctx.open_issues
    assert "Phase 4" in ctx.next_phase_brief
    assert "3/10" in ctx.goal_alignment
    print("✅ test_compactor_deterministic PASS")


def test_compactor_to_prompt():
    """生成可注入 prompt 的文本"""
    ctx = CompactedContext(
        completed_phases=[
            {"phase": 1, "name": "data", "status": "success",
             "key_decisions": "收集了市场数据", "artifacts": ["data.json"]},
        ],
        open_issues=["API 延迟未定义"],
        next_phase_brief="继续执行架构设计",
        goal_alignment="已完成 1/10 phases",
    )
    text = ctx.to_prompt_text()

    assert "Phase 1" in text
    assert "data" in text
    assert "API 延迟未定义" in text
    assert "架构设计" in text
    print("✅ test_compactor_to_prompt PASS")


def test_compactor_parse_llm_response():
    """解析 LLM 压缩结果"""
    c = ContextCompactor()
    llm_response = """
分析完成，以下是压缩结果：

```json
{
    "completed_phases": [
        {"phase": 1, "name": "data", "status": "success", "key_decisions": "市场数据收集完毕", "artifacts": ["data.json"]}
    ],
    "open_issues": ["性能需求未明确"],
    "next_phase_brief": "开始架构设计",
    "goal_alignment": "与目标高度对齐"
}
```
"""
    ctx = c._parse_llm_response(llm_response, "2026-06-25T00:00:00+08:00")
    assert len(ctx.completed_phases) == 1
    assert "性能需求" in ctx.open_issues[0]
    assert "架构设计" in ctx.next_phase_brief
    print("✅ test_compactor_parse_llm_response PASS")


def test_compactor_build_prompt():
    """构建压缩 prompt"""
    results = [
        WorkerResult(status="success", phase=1, phase_name="data",
                     summary="数据收集", artifacts={"d": "data.json"}),
    ]
    c = ContextCompactor()
    prompt = c.build_compaction_prompt(
        results=results,
        next_phase=2,
        next_phase_name="planning",
        total_phases=10,
    )

    assert "Phase 1" in prompt or "data" in prompt
    assert "planning" in prompt
    assert "1/10" in prompt
    print("✅ test_compactor_build_prompt PASS")


# ── Runner ────────────────────────────────────────────────────────

def run_all():
    tests = [
        # WorkerResult
        test_worker_result_basic,
        test_worker_result_defaults,
        test_worker_result_with_help,
        test_parse_worker_result_from_text,
        test_parse_worker_result_no_json,
        test_parse_worker_result_invalid_json,
        test_parse_worker_result_safe,
        test_format_output_suffix,
        test_parse_multiple_json_blocks,
        # FeedbackStream
        test_feedback_stream_healthy,
        test_feedback_stream_warning,
        test_feedback_stream_critical,
        test_feedback_stream_issues_warning,
        test_feedback_stream_markdown,
        test_feedback_stream_pipeline_complete,
        # ContextCompactor
        test_compactor_should_compact,
        test_compactor_deterministic,
        test_compactor_to_prompt,
        test_compactor_parse_llm_response,
        test_compactor_build_prompt,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"❌ {test.__name__} FAIL: {e}")
            failed += 1

    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed, {passed + failed} total")
    print(f"{'='*50}")

    return failed == 0


if __name__ == "__main__":
    success = run_all()
    sys.exit(0 if success else 1)
