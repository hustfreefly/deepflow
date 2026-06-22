"""
保真度校验模块
================

对优化后的简历内容进行双重校验:
1. 生成前: 事实锚点锁定（Immutable Anchor Set）
2. 生成后: diff + NER 双重校验

高风险变更标记（HIGH_RISK_CHANGES）
"""

from __future__ import annotations
import re
import difflib
import logging
from typing import List, Dict, Set, Tuple, Optional

from .interfaces import (
    ResumeDocument,
    OptimizationResult,
    ContentChange,
    RiskLevel,
    FidelityViolationError,
    IMMUTABLE_ANCHORS,
    HIGH_RISK_CHANGES,
    FIDELITY_THRESHOLDS,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 事实锚点提取（与 optimizer 共享逻辑）
# ---------------------------------------------------------------------------

_COMPANY_RE = re.compile(r'([\u4e00-\u9fa5a-zA-Z0-9·\-]*(?:公司|集团|科技|技术|有限公司|Corp|Inc|Ltd|Technology|Systems))')
_DATE_RE = re.compile(r'(\d{4}[.\-/]\d{1,2}(?:[.\-/]\d{1,2})?)')
_EDUCATION_RE = re.compile(r'((?:博士|硕士|本科|大专|学士|研究生|PhD|MBA|B\.?S\.?|M\.?S\.?|M\.?Eng))')
_QUANT_RE = re.compile(r'([\u4e00-\u9fa5]*\d+\.?\d*[%‰倍]|[提升|增加|减少|优化|降低|提高|增长|下降|达]\s*\d+\.?\d*[%‰倍])')


def extract_anchors(content: str) -> Dict[str, List[str]]:
    """
    从简历内容中提取不可变事实锚点。

    Returns:
        Dict[anchor_type -> [values]]
    """
    anchors: Dict[str, List[str]] = {
        'company_name': [],
        'employment_dates': [],
        'education_degree': [],
        'education_institution': [],
        'quantitative_metrics': [],
    }

    for m in _COMPANY_RE.finditer(content):
        anchors['company_name'].append(m.group(1))

    for m in _DATE_RE.finditer(content):
        anchors['employment_dates'].append(m.group(1))

    for m in _EDUCATION_RE.finditer(content):
        anchors['education_degree'].append(m.group(1))

    for m in _QUANT_RE.finditer(content):
        anchors['quantitative_metrics'].append(m.group(1))

    return anchors


# ---------------------------------------------------------------------------
# Diff 校验
# ---------------------------------------------------------------------------

def compute_diff(original: str, optimized: str) -> List[str]:
    """计算两段文本的 diff，返回变更行列表"""
    orig_lines = original.splitlines(keepends=True)
    opt_lines = optimized.splitlines(keepends=True)

    differ = difflib.Differ()
    diff_result = list(differ.compare(orig_lines, opt_lines))

    changed_lines = []
    for line in diff_result:
        if line.startswith('+ ') or line.startswith('- '):
            changed_lines.append(line.strip())

    return changed_lines


# ---------------------------------------------------------------------------
# NER 校验（简化版命名实体识别）
# ---------------------------------------------------------------------------

def _extract_entities(text: str) -> Set[str]:
    """简化版 NER: 提取关键实体"""
    entities = set()
    # 公司名
    entities.update(m.group(1) for m in _COMPANY_RE.finditer(text))
    # 日期
    entities.update(m.group(1) for m in _DATE_RE.finditer(text))
    # 学历
    entities.update(m.group(1) for m in _EDUCATION_RE.finditer(text))
    # 数字指标
    entities.update(m.group(1) for m in _QUANT_RE.finditer(text))
    return entities


def ner_check(original: str, optimized: str) -> Dict[str, List[str]]:
    """
    NER 校验: 检查优化后是否丢失了关键实体。

    Returns:
        {'added': [...], 'removed': [...], 'modified': [...]}
    """
    orig_entities = _extract_entities(original)
    opt_entities = _extract_entities(optimized)

    removed = orig_entities - opt_entities
    added = opt_entities - orig_entities

    return {
        'added': list(added),
        'removed': list(removed),
        'modified': [],  # 简化版不做精确修改追踪
    }


# ---------------------------------------------------------------------------
# 高风险变更检测
# ---------------------------------------------------------------------------

def _detect_high_risk_changes(
    original: str,
    optimized: str,
    changes: List[ContentChange],
) -> List[ContentChange]:
    """
    检测高风险变更。

    基于 HIGH_RISK_CHANGES 定义的变更类型进行标记。
    """
    high_risk = []

    # 检查现有变更中是否有高风险类型
    for change in changes:
        # 检查变更是否涉及高风险操作
        risk_reasons = []

        # 检查是否添加了新公司
        orig_companies = set(m.group(1) for m in _COMPANY_RE.finditer(original))
        opt_companies = set(m.group(1) for m in _COMPANY_RE.finditer(optimized))
        new_companies = opt_companies - orig_companies
        if new_companies:
            risk_reasons.append('new_company_added')

        # 检查是否修改了日期
        orig_dates = set(m.group(1) for m in _DATE_RE.finditer(original))
        opt_dates = set(m.group(1) for m in _DATE_RE.finditer(optimized))
        modified_dates = orig_dates ^ opt_dates
        if modified_dates:
            risk_reasons.append('date_modification')

        # 检查是否修改了数字指标
        orig_metrics = set(m.group(1) for m in _QUANT_RE.finditer(original))
        opt_metrics = set(m.group(1) for m in _QUANT_RE.finditer(optimized))
        modified_metrics = orig_metrics ^ opt_metrics
        if modified_metrics:
            risk_reasons.append('metric_modification')

        if risk_reasons:
            change.risk_level = RiskLevel.HIGH if change.risk_level.value in ('low', 'medium') else change.risk_level
            change.reason += f' [HIGH_RISK: {", ".join(risk_reasons)}]'
            high_risk.append(change)

    return high_risk


# ---------------------------------------------------------------------------
# 保真度计算
# ---------------------------------------------------------------------------

def compute_fidelity_score(
    original: str,
    optimized: str,
    changes: List[ContentChange],
) -> float:
    """
    计算保真度分数 (0-100)。

    综合考虑:
    - 文本相似度
    - 事实锚点保留率
    - 高风险变更数量
    """
    if not original or not optimized:
        return 0.0

    # 1. 文本相似度（基于词集合）
    orig_words = set(_tokenize(original))
    opt_words = set(_tokenize(optimized))

    if not orig_words:
        return 100.0

    similarity = len(orig_words & opt_words) / len(orig_words)

    # 2. 事实锚点保留率
    orig_anchors = extract_anchors(original)
    opt_anchors = extract_anchors(optimized)

    total_anchors = sum(len(v) for v in orig_anchors.values())
    preserved_anchors = 0
    for anchor_type, values in orig_anchors.items():
        opt_values = set(opt_anchors.get(anchor_type, []))
        for v in values:
            if v in opt_values:
                preserved_anchors += 1

    anchor_rate = preserved_anchors / total_anchors if total_anchors > 0 else 1.0

    # 3. 高风险变更惩罚
    high_risk_count = sum(1 for c in changes if c.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL))
    risk_penalty = min(high_risk_count * 3, 20)  # 最多扣 20 分

    # 综合评分
    score = (similarity * 0.6 + anchor_rate * 0.4) * 100 - risk_penalty
    return max(round(score, 1), 0.0)


def _tokenize(text: str) -> List[str]:
    """简单分词"""
    words = re.findall(r'[a-zA-Z]+', text)
    chars = list(re.findall(r'[\u4e00-\u9fa5]', text))
    nums = re.findall(r'\d+\.?\d*', text)
    return words + chars + nums


# ---------------------------------------------------------------------------
# 主校验流程
# ---------------------------------------------------------------------------

def validate_fidelity(
    original_resume: ResumeDocument,
    optimization_result: OptimizationResult,
) -> Tuple[float, List[ContentChange]]:
    """
    对优化结果进行保真度校验。

    Args:
        original_resume: 原始简历
        optimization_result: 优化结果

    Returns:
        (fidelity_score, high_risk_changes)

    Raises:
        FidelityViolationError: 保真度低于阈值
    """
    logger.info("Validating fidelity for optimization level=%s",
                optimization_result.optimization_level.value)

    # 构建优化后完整文本
    optimized_text = '\n'.join(s.content for s in optimization_result.sections)

    # 1. Diff 校验
    diff_changes = compute_diff(original_resume.content, optimized_text)
    logger.info("Diff detected %d changed lines", len(diff_changes))

    # 2. NER 校验
    ner_result = ner_check(original_resume.content, optimized_text)
    logger.info("NER check: %d added, %d removed entities",
                len(ner_result['added']), len(ner_result['removed']))

    # 3. 检测高风险变更
    high_risk = _detect_high_risk_changes(
        original_resume.content,
        optimized_text,
        optimization_result.changes,
    )

    # 4. 计算保真度分数
    fidelity = compute_fidelity_score(
        original_resume.content,
        optimized_text,
        optimization_result.changes,
    )

    # 5. 更新优化结果中的保真度分数
    optimization_result.fidelity_score = fidelity

    # 6. 阈值检查
    level = optimization_result.optimization_level
    min_threshold = FIDELITY_THRESHOLDS.get(level, 90.0)

    if fidelity < min_threshold:
        error_msg = (
            f"Fidelity score {fidelity:.1f} below threshold {min_threshold:.1f} "
            f"for {level.value} level. "
            f"NER removed entities: {ner_result['removed']}"
        )
        logger.error(error_msg)
        raise FidelityViolationError(error_msg)

    logger.info("Fidelity validation passed: score=%.1f, threshold=%.1f, high_risk=%d",
                fidelity, min_threshold, len(high_risk))

    return fidelity, high_risk
