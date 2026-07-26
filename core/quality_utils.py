"""
QualityUtils — 质量门控工具函数集合

解决三域 Gate 标准不统一问题。
提供通用的 L1/L2 检查函数，各域自己组装 Gate 链。

契约笼子：
- 输入输出通过 Pydantic 验证
- fail-fast 策略
- 确定性逻辑（L1）+ LLM Judge 接口（L2）
"""
from __future__ import annotations

import re
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


# ============================================================================
# Pydantic 契约
# ============================================================================

class CheckResult(BaseModel):
    """单个检查项的结果"""
    check: str = Field(..., description="检查项名称")
    passed: bool = Field(..., description="是否通过")
    message: str = Field(default="", description="消息（失败原因或成功说明）")
    severity: str = Field(default="ERROR", description="严重度: ERROR | WARN | INFO | PASS | WARNING | CRITICAL")
    
    @field_validator("severity")
    @classmethod
    def severity_valid(cls, v: str) -> str:
        if v not in ("ERROR", "WARN", "INFO", "PASS", "WARNING", "CRITICAL"):
            raise ValueError(f"severity 必须是 ERROR|WARN|INFO|PASS|WARNING|CRITICAL，收到 {v!r}")
        return v


class GateResult(BaseModel):
    """Gate 综合结果（多个检查项的聚合）"""
    passed: bool = Field(..., description="是否全部通过")
    results: list[CheckResult] = Field(default_factory=list, description="各检查项结果")
    summary: dict[str, int] = Field(default_factory=dict, description="统计: total/passed/failed")
    
    @field_validator("summary")
    @classmethod
    def summary_consistent(cls, v: dict, info) -> dict:
        results = info.data.get("results", [])
        if results:
            total = len(results)
            passed = sum(1 for r in results if r.passed)
            failed = total - passed
            expected = {"total": total, "passed": passed, "failed": failed}
            if v != expected:
                raise ValueError(f"summary 不一致: 期望 {expected}，收到 {v}")
        return v


class CoverageResult(BaseModel):
    """需求覆盖率检查结果（支持双层阈值）"""
    total_reqs: int = Field(..., ge=0, description="总需求数")
    covered_reqs: int = Field(..., ge=0, description="已覆盖需求数")
    coverage_rate: float = Field(..., ge=0.0, le=1.0, description="覆盖率")
    uncovered: list[str] = Field(default_factory=list, description="未覆盖的需求 ID")
    passed: bool = Field(..., description="是否通过（覆盖率 >= critical_threshold）")
    severity: str = Field(default="PASS", description="严重度: PASS | WARNING | CRITICAL")
    
    @field_validator("severity")
    @classmethod
    def severity_valid(cls, v: str) -> str:
        if v not in ("PASS", "WARNING", "CRITICAL"):
            raise ValueError(f"severity 必须是 PASS|WARNING|CRITICAL，收到 {v!r}")
        return v
    
    @field_validator("coverage_rate")
    @classmethod
    def rate_consistent(cls, v: float, info) -> float:
        total = info.data.get("total_reqs", 0)
        covered = info.data.get("covered_reqs", 0)
        if total > 0:
            expected = round(covered / total, 3)
            if abs(v - expected) > 0.001:
                raise ValueError(f"coverage_rate 不一致: 期望 {expected}，收到 {v}")
        return v


# ============================================================================
# 核心函数
# ============================================================================

def check_schema(
    data: dict | str,
    required_fields: list[str],
    field_types: Optional[dict[str, type]] = None,
) -> CheckResult:
    """
    L1 Schema 验证。
    
    Args:
        data: 待验证数据（dict 或 JSON 字符串）
        required_fields: 必需字段列表
        field_types: 字段类型约束（可选）
        
    Returns:
        CheckResult(check="schema", passed, message)
    """
    # 解析 JSON 字符串
    if isinstance(data, str):
        try:
            import json
            data = json.loads(data)
        except json.JSONDecodeError as e:
            return CheckResult(
                check="schema",
                passed=False,
                message=f"JSON 解析失败: {e}",
                severity="ERROR",
            )
    
    if not isinstance(data, dict):
        return CheckResult(
            check="schema",
            passed=False,
            message=f"数据必须是 dict，收到 {type(data).__name__}",
            severity="ERROR",
        )
    
    # 检查必需字段
    missing = [f for f in required_fields if f not in data]
    if missing:
        return CheckResult(
            check="schema",
            passed=False,
            message=f"缺失必需字段: {missing}",
            severity="ERROR",
        )
    
    # 检查字段类型
    if field_types:
        type_errors = []
        for field, expected_type in field_types.items():
            if field in data and not isinstance(data[field], expected_type):
                actual_type = type(data[field]).__name__
                type_errors.append(f"{field}: 期望 {expected_type.__name__}，收到 {actual_type}")
        if type_errors:
            return CheckResult(
                check="schema",
                passed=False,
                message=f"字段类型错误: {type_errors}",
                severity="ERROR",
            )
    
    return CheckResult(
        check="schema",
        passed=True,
        message=f"Schema 验证通过（{len(required_fields)} 个必需字段）",
        severity="INFO",
    )


def check_coverage(
    requirements: list[str] | dict,
    output: str | dict | list,
    critical_threshold: float = 0.5,
    warning_threshold: float = 0.8,
) -> CoverageResult:
    """
    L2 需求覆盖率检查（支持双层阈值）。
    
    双层阈值逻辑（与原 post_validator 一致）：
    - coverage_rate < critical_threshold → CRITICAL (passed=False)
    - critical_threshold <= coverage_rate < warning_threshold → WARNING (passed=True)
    - coverage_rate >= warning_threshold → PASS (passed=True)
    
    Args:
        requirements: 需求列表（ID 列表或 dict）
        output: 输出内容（文本或结构化数据）
        critical_threshold: 严重阈值（默认 0.5，低于此值为 CRITICAL）
        warning_threshold: 警告阈值（默认 0.8，低于此值为 WARNING）
        
    Returns:
        CoverageResult(total_reqs, covered_reqs, coverage_rate, uncovered, passed, severity)
    """
    # 提取需求 ID
    if isinstance(requirements, dict):
        req_ids = list(requirements.keys())
    elif isinstance(requirements, list):
        req_ids = [str(r) for r in requirements]
    else:
        req_ids = []
    
    if not req_ids:
        return CoverageResult(
            total_reqs=0,
            covered_reqs=0,
            coverage_rate=0.0,
            uncovered=[],
            passed=False,
            severity="CRITICAL",
        )
    
    # 转换为文本
    output_text = _to_text(output).lower()
    
    # 检查覆盖
    covered = []
    uncovered = []
    
    for req_id in req_ids:
        # 简单匹配：需求 ID 是否出现在输出中
        if req_id.lower() in output_text:
            covered.append(req_id)
        else:
            uncovered.append(req_id)
    
    total = len(req_ids)
    covered_count = len(covered)
    rate = round(covered_count / total, 3) if total > 0 else 0.0
    
    # 双层阈值判定
    if rate < critical_threshold:
        passed = False
        severity = "CRITICAL"
    elif rate < warning_threshold:
        passed = True  # WARNING 不阻塞
        severity = "WARNING"
    else:
        passed = True
        severity = "PASS"
    
    return CoverageResult(
        total_reqs=total,
        covered_reqs=covered_count,
        coverage_rate=rate,
        uncovered=uncovered,
        passed=passed,
        severity=severity,
    )


def check_anchors(
    anchors: list[str] | dict,
    output: str | dict | list,
    critical_threshold: float = 0.5,
    warning_threshold: float = 0.8,
) -> CheckResult:
    """
    L1 锚点保留检查（支持双层阈值）。
    
    双层阈值逻辑：
    - alignment_rate < critical_threshold → CRITICAL (passed=False)
    - critical_threshold <= alignment_rate < warning_threshold → WARNING (passed=True)
    - alignment_rate >= warning_threshold → PASS (passed=True)
    
    Args:
        anchors: semantic_anchors 列表
        output: 输出内容
        critical_threshold: 严重阈值（默认 0.5）
        warning_threshold: 警告阈值（默认 0.8）
        
    Returns:
        CheckResult(check="anchors", passed, message, severity)
    """
    # 提取锚点
    if isinstance(anchors, dict):
        anchor_list = anchors.get("semantic_anchors", [])
    elif isinstance(anchors, list):
        anchor_list = anchors
    else:
        anchor_list = []
    
    if not anchor_list:
        return CheckResult(
            check="anchors",
            passed=False,
            message="无锚点可检查",
            severity="CRITICAL",
        )
    
    # 转换为文本
    output_text = _to_text(output).lower()
    
    # 检查保留
    preserved = sum(1 for a in anchor_list if str(a).lower() in output_text)
    total = len(anchor_list)
    rate = preserved / total if total > 0 else 0.0
    
    # 双层阈值判定
    if rate < critical_threshold:
        passed = False
        severity = "CRITICAL"
        message = f"锚点保留率 {rate:.1%} ({preserved}/{total}) < 严重阈值 {critical_threshold:.1%}"
    elif rate < warning_threshold:
        passed = True  # WARNING 不阻塞
        severity = "WARNING"
        message = f"锚点保留率 {rate:.1%} ({preserved}/{total}) < 警告阈值 {warning_threshold:.1%}"
    else:
        passed = True
        severity = "PASS"
        message = f"锚点保留率 {rate:.1%} ({preserved}/{total})"
    
    return CheckResult(
        check="anchors",
        passed=passed,
        message=message,
        severity=severity,
    )


def aggregate_gate_results(results: list[CheckResult | CoverageResult]) -> GateResult:
    """
    聚合多个检查结果为 GateResult。
    
    Args:
        results: 检查结果列表
        
    Returns:
        GateResult(passed, results, summary)
    """
    # 转换为 CheckResult
    check_results = []
    for r in results:
        if isinstance(r, CoverageResult):
            check_results.append(CheckResult(
                check="coverage",
                passed=r.passed,
                message=f"覆盖率 {r.coverage_rate:.1%} ({r.covered_reqs}/{r.total_reqs})",
                severity="ERROR" if not r.passed else "INFO",
            ))
        else:
            check_results.append(r)
    
    passed = all(r.passed for r in check_results)
    total = len(check_results)
    passed_count = sum(1 for r in check_results if r.passed)
    failed_count = total - passed_count
    
    return GateResult(
        passed=passed,
        results=check_results,
        summary={"total": total, "passed": passed_count, "failed": failed_count},
    )


# ============================================================================
# 内部辅助函数
# ============================================================================

def _to_text(data: str | dict | list) -> str:
    """将数据转换为文本"""
    if isinstance(data, str):
        return data
    elif isinstance(data, (dict, list)):
        import json
        return json.dumps(data, ensure_ascii=False)
    return str(data)


# ============================================================================
# 便捷类封装（可选）
# ============================================================================

class QualityUtils:
    """便捷类封装（可选）"""
    
    @staticmethod
    def schema(data, required_fields, **kwargs) -> CheckResult:
        return check_schema(data, required_fields, **kwargs)
    
    @staticmethod
    def coverage(requirements, output, **kwargs) -> CoverageResult:
        return check_coverage(requirements, output, **kwargs)
    
    @staticmethod
    def anchors(anchors, output, **kwargs) -> CheckResult:
        return check_anchors(anchors, output, **kwargs)
    
    @staticmethod
    def aggregate(results) -> GateResult:
        return aggregate_gate_results(results)
