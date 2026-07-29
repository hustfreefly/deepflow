"""
Phase 2c: MD Track Extractor 扩展测试

测试覆盖：
1. _extract_semantic_anchors: 解析 `- [category] name: constraint` 列表
2. _extract_summary: 从表格行数计算统计
3. _extract_constraint_coverage: 从 requirement_coverage 章节提取覆盖
4. 无表格时 warning（不 raise ValueError）
5. 无 Gate 表时 warning（不 raise ValueError）
"""

import sys as _sys
from pathlib import Path as _Path

_p = _Path(__file__).resolve()
_r = next((d for d in _p.parents if (d / 'core' / 'blackboard').is_dir()), None)
if _r and str(_r) not in _sys.path:
    _sys.path.insert(0, str(_r))

import logging
import pytest

from core.md_track_extractor import (
    _extract_semantic_anchors,
    _extract_summary,
    _extract_constraint_coverage,
    extract_track_json,
)


# ============================================================================
# Test _extract_semantic_anchors
# ============================================================================

class TestExtractSemanticAnchors:
    def test_extract_semantic_anchors_list(self):
        """解析标准格式的 semantic anchor 列表项。"""
        md = """
## semantic_anchors

- [performance] 响应时间: < 200ms
- [security] 认证方式: OAuth2 + JWT
- [reliability] 可用性: 99.9%
- [cost] 预算上限: ¥50,000/月
"""
        result = _extract_semantic_anchors(md)
        
        assert len(result) == 4
        assert result[0] == {
            "category": "performance",
            "name": "响应时间",
            "constraint": "< 200ms",
        }
        assert result[1]["category"] == "security"
        assert result[1]["name"] == "认证方式"
        assert result[1]["constraint"] == "OAuth2 + JWT"
        assert result[2]["category"] == "reliability"
        assert result[3]["constraint"] == "¥50,000/月"

    def test_extract_semantic_anchors_empty(self):
        """没有匹配项时返回空列表。"""
        md = """
## some_section
普通文本，没有 anchor 列表。
"""
        result = _extract_semantic_anchors(md)
        assert result == []

    def test_extract_semantic_anchors_mixed_content(self):
        """混合内容中只提取匹配格式的项。"""
        md = """
- [perf] 延迟: < 100ms
- 普通列表项（无 category）
- [sec] 加密: AES-256
* 星号列表项
"""
        result = _extract_semantic_anchors(md)
        assert len(result) == 2
        assert result[0]["category"] == "perf"
        assert result[1]["category"] == "sec"


# ============================================================================
# Test _extract_summary
# ============================================================================

class TestExtractSummary:
    def test_extract_summary_counts(self):
        """从表格行数计算 key_decisions, phases, risks 计数。"""
        md = """
## 关键决策

| 决策项 | 选项A | 选项B | 选定 |
|--------|-------|-------|------|
| 架构 | 微服务 | 单体 | 微服务 |
| 数据库 | PG | MySQL | PG |
| 缓存 | Redis | Memcached | Redis |

## 实施计划

| 阶段 | 内容 | 时间 |
|------|------|------|
| Phase 1 | 基础搭建 | 2周 |
| Phase 2 | 核心开发 | 4周 |

## 风险

| 风险 | 影响 | 概率 | 缓解 |
|------|------|------|------|
| 人员不足 | 高 | 中 | 外包 |
"""
        result = _extract_summary(md)
        
        assert result["key_decisions_count"] == 3
        assert result["implementation_phases_count"] == 2
        assert result["risk_count"] == 1

    def test_extract_summary_empty(self):
        """没有匹配表格时返回零计数。"""
        md = """
## 其他章节
没有表格内容。
"""
        result = _extract_summary(md)
        assert result["key_decisions_count"] == 0
        assert result["implementation_phases_count"] == 0
        assert result["risk_count"] == 0


# ============================================================================
# Test _extract_constraint_coverage
# ============================================================================

class TestExtractConstraintCoverage:
    def test_extract_constraint_coverage_text_pattern(self):
        """从文本模式 'covered: X / total: Y' 提取覆盖率。"""
        md = """
## requirement_coverage

本章节统计需求覆盖情况。

covered: 18 / total: 20

| REQ-ID | 状态 |
|--------|------|
| REQ-001 | ✓ |
"""
        result = _extract_constraint_coverage(md)
        
        assert result["total"] == 20
        assert result["covered"] == 18
        assert result["ratio"] == 0.9

    def test_extract_constraint_coverage_table_counting(self):
        """从表格行数统计覆盖率（无文本模式时）。"""
        md = """
## requirement_coverage

| REQ-ID | 需求 | 覆盖 |
|--------|------|------|
| REQ-001 | 功能A | ✓ |
| REQ-002 | 功能B | ✅ |
| REQ-003 | 功能C | 否 |
| REQ-004 | 功能D | yes |
"""
        result = _extract_constraint_coverage(md)
        
        assert result["total"] == 4
        assert result["covered"] == 3  # ✓, ✅, yes
        assert result["ratio"] == 0.75

    def test_extract_constraint_coverage_no_section(self):
        """缺少 requirement_coverage 章节时返回零。"""
        md = """
## other_section
一些内容。
"""
        result = _extract_constraint_coverage(md)
        assert result == {"total": 0, "covered": 0, "ratio": 0.0}


# ============================================================================
# Test 放宽限制: 无表格 warning（不 raise）
# ============================================================================

class TestNoTablesWarning:
    def test_no_tables_warning(self, caplog):
        """MD 中无表格时，extract_track_json 不 raise，仅 warning。"""
        # 填充内容以满足 min_length=800
        padding = "详细描述内容。" * 70  # ~630 chars
        md = f"""---
version: "1.0"
session: test-session
created: "2026-07-29"
---

## meta_info

一些元信息。{padding}

## solution_structure

方案结构描述。这里是方案的详细说明，包含架构设计、模块划分、接口定义等内容。
这些内容用于填充到最小长度要求以上，确保结构校验能够通过。

## requirement_coverage

需求覆盖说明。本章节详细说明了所有需求的覆盖情况，确保每个需求都有对应的实现方案。
包括功能需求、非功能需求、约束条件等方面的覆盖分析。

## implementation_plan

实施计划说明。包含详细的阶段划分、里程碑、资源分配等内容。
确保项目可以按照计划有序推进，降低实施风险。
"""
        # 不应 raise ValueError
        with caplog.at_level(logging.WARNING):
            result = extract_track_json(md, "solution_pro")
        
        assert result["schema_version"] == "3.1.0"
        assert result["domain"] == "solution_pro"
        assert "summary" in result
        assert "semantic_anchors" in result
        # 验证 warning 被记录
        assert any("未找到任何表格" in record.message for record in caplog.records)


# ============================================================================
# Test 放宽限制: 无 Gate 表 warning（不 raise）
# ============================================================================

class TestNoGateTableWarning:
    def test_no_gate_table_warning(self, caplog):
        """有表格但无 Gate 决策表时，extract_track_json 不 raise，仅 warning。"""
        # 填充内容以满足 min_length=800
        padding = "方案详细说明内容，用于填充到最小长度要求。" * 20  # ~400 chars
        md = f"""---
version: "1.0"
session: test-session
created: "2026-07-29"
---

## meta_info

一些元信息。{padding}

## solution_structure

| 模块 | 说明 |
|------|------|
| 模块A | 核心模块 |
| 模块B | 辅助模块 |

方案架构的详细描述，包含各模块的职责划分和协作方式。

## requirement_coverage

covered: 5 / total: 5

本章节详细分析了所有需求的覆盖情况，确保每个需求都有对应的实现方案。
包括功能需求、非功能需求、约束条件等方面的覆盖分析。

## implementation_plan

| 阶段 | 内容 |
|------|------|
| Phase 1 | 搭建 |
| Phase 2 | 开发 |
| Phase 3 | 测试 |

实施计划的详细说明，包含各阶段的时间安排和交付物。
"""
        # 不应 raise ValueError
        with caplog.at_level(logging.WARNING):
            result = extract_track_json(md, "solution_pro")
        
        assert result["schema_version"] == "3.1.0"
        assert result["gate_summary"] == {}
        # 验证 warning 被记录
        assert any("Gate 决策表提取为空" in record.message for record in caplog.records)
