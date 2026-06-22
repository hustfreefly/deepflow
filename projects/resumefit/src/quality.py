"""
质量报告模块
============

对优化后的简历进行 6 维度质量评分:
1. 关键词覆盖率
2. 语义相似度
3. 内容保真度
4. 排版保真度
5. ATS 兼容性
6. AI 痕迹（自然度）

阈值检查对照 QUALITY_THRESHOLDS。
"""

from __future__ import annotations
import re
import logging
from typing import List, Dict
from datetime import datetime

from .interfaces import (
    JDSchema,
    OptimizationResult,
    PDFOutput,
    QualityMetrics,
    QualityReport,
    QUALITY_THRESHOLDS,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 6 维度评分计算
# ---------------------------------------------------------------------------

def _compute_keyword_coverage(resume_text: str, jd: JDSchema) -> float:
    """
    关键词覆盖率: 简历中包含的 JD 关键词比例。
    """
    if not jd.keywords:
        return 100.0

    resume_lower = resume_text.lower()
    matched = 0
    for kw in jd.keywords:
        if kw.lower() in resume_lower:
            matched += 1

    coverage = (matched / len(jd.keywords)) * 100
    return round(min(coverage, 100.0), 1)


def _compute_semantic_similarity(resume_text: str, jd: JDSchema) -> float:
    """
    语义相似度: 基于词重叠的简化语义相似度。
    实际生产环境可替换为 embedding 模型。
    """
    resume_words = set(_tokenize(resume_text))
    jd_words = set()
    for req in jd.hard_requirements + jd.soft_requirements:
        jd_words.update(_tokenize(req.text))
    jd_words.update(_tokenize(jd.job_title))
    jd_words.update(jd.keywords)

    if not jd_words:
        return 100.0

    overlap = resume_words & jd_words
    # Jaccard 相似度
    union = resume_words | jd_words
    if not union:
        return 100.0

    similarity = (len(overlap) / len(union)) * 100
    return round(min(similarity * 1.5, 100.0), 1)  # 缩放以更合理


def _compute_fidelity_score(optimization_result: OptimizationResult) -> float:
    """内容保真度: 直接使用优化结果中的保真度分数。"""
    return round(optimization_result.fidelity_score, 1)


def _compute_formatting_score(pdf_output: PDFOutput) -> float:
    """排版保真度: 基于 PDF 生成质量的评分。"""
    score = 80.0  # 基础分

    # ATS 兼容加分
    if pdf_output.ats_compatible:
        score += 10

    # 文本可提取加分
    if pdf_output.text_extractable:
        score += 5

    # 文件大小合理加分
    if pdf_output.file_size_bytes < 1 * 1024 * 1024:  # < 1MB
        score += 5

    return round(min(score, 100.0), 1)


def _compute_ats_compatibility(pdf_output: PDFOutput, resume_text: str) -> float:
    """ATS 兼容性: 检查简历是否符合 ATS 解析标准。"""
    score = 85.0  # 基础分（使用 ATS 模板）

    # 检查是否包含表格（ATS 不友好）
    if '<table' in resume_text.lower():
        score -= 15

    # 检查是否包含图片引用
    if '<img' in resume_text.lower():
        score -= 10

    # 单列布局加分（我们的模板默认单列）
    score += 5

    # 标准字体加分
    score += 5

    return round(min(score, 100.0), 1)


def _compute_naturalness_score(optimization_result: OptimizationResult, resume_text: str) -> float:
    """
    AI 痕迹/自然度: 检测文本中 AI 生成痕迹。

    检测指标:
    - 过度使用套话
    - 句式单一
    - 关键词堆砌
    """
    score = 85.0  # 基础分

    # 检测过度套话
    ai_patterns = [
        '我是一位充满热情的', '我是一个充满激情的',
        'I am a passionate', 'I am highly motivated',
        '在...方面有着丰富的经验', '具备出色的',
    ]
    text_lower = resume_text.lower()
    ai_count = sum(1 for pat in ai_patterns if pat.lower() in text_lower)
    score -= ai_count * 5

    # 检测关键词堆砌（同一关键词出现超过 3 次）
    words = _tokenize(resume_text)
    word_freq: Dict[str, int] = {}
    for w in words:
        w_lower = w.lower()
        if len(w_lower) > 3:
            word_freq[w_lower] = word_freq.get(w_lower, 0) + 1

    keyword_stuffing = sum(1 for freq in word_freq.values() if freq > 3)
    score -= keyword_stuffing * 3

    # 变更数量过多可能不自然
    if len(optimization_result.changes) > 20:
        score -= (len(optimization_result.changes) - 20) * 0.5

    return round(max(min(score, 100.0), 0.0), 1)


def _tokenize(text: str) -> List[str]:
    """简单分词"""
    words = re.findall(r'[a-zA-Z]+', text)
    chars = list(re.findall(r'[\u4e00-\u9fa5]', text))
    nums = re.findall(r'\d+\.?\d*', text)
    return words + chars + nums


# ---------------------------------------------------------------------------
# 告警生成
# ---------------------------------------------------------------------------

def _generate_warnings(metrics: QualityMetrics) -> List[str]:
    """根据评分生成告警信息。"""
    warnings = []

    if metrics.keyword_coverage < QUALITY_THRESHOLDS.get('jd_match_score', 75.0):
        warnings.append(
            f"关键词覆盖率偏低 ({metrics.keyword_coverage:.1f}%), "
            f"建议增加 JD 相关关键词"
        )

    if metrics.semantic_similarity < 60.0:
        warnings.append(
            f"语义相似度较低 ({metrics.semantic_similarity:.1f}%), "
            f"简历内容与 JD 匹配度不足"
        )

    if metrics.fidelity_score < QUALITY_THRESHOLDS.get('jd_match_score', 75.0):
        warnings.append(
            f"保真度偏低 ({metrics.fidelity_score:.1f}%), "
            f"可能存在过度优化风险"
        )

    if metrics.ats_compatibility < QUALITY_THRESHOLDS.get('ats_compatibility', 85.0):
        warnings.append(
            f"ATS 兼容性不足 ({metrics.ats_compatibility:.1f}%), "
            f"可能影响简历解析"
        )

    if metrics.naturalness_score < QUALITY_THRESHOLDS.get('naturalness_score', 70.0):
        warnings.append(
            f"AI 痕迹较重 ({metrics.naturalness_score:.1f}%), "
            f"建议人工润色降低 AI 感"
        )

    if metrics.ai_screening_score < QUALITY_THRESHOLDS.get('ai_screening_score', 70.0):
        warnings.append(
            f"AI 筛选通过率偏低 ({metrics.ai_screening_score:.1f}%), "
            f"建议进一步优化关键词匹配"
        )

    return warnings


def _generate_recommendations(metrics: QualityMetrics, jd: JDSchema) -> List[str]:
    """生成改进建议。"""
    recommendations = []

    if metrics.keyword_coverage < 80:
        missing = [kw for kw in jd.keywords if kw.lower() not in _tokenize_text()]
        if missing:
            recommendations.append(
                f"建议补充以下关键词: {', '.join(missing[:5])}"
            )

    if metrics.naturalness_score < 80:
        recommendations.append(
            "建议人工润色，减少 AI 生成痕迹"
        )

    if metrics.fidelity_score < 95:
        recommendations.append(
            "部分原始内容被修改，建议复核事实锚点"
        )

    if metrics.semantic_similarity < 70:
        recommendations.append(
            "建议增加与 JD 要求直接相关的经历描述"
        )

    if not recommendations:
        recommendations.append("简历质量良好，可直接使用")

    return recommendations


def _tokenize_text() -> set:
    """占位: 实际使用时传入 resume_text"""
    return set()


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def generate_quality_report(
    jd: JDSchema,
    optimization_result: OptimizationResult,
    pdf_output: PDFOutput,
) -> QualityReport:
    """
    生成 6 维度质量报告。

    Args:
        jd: 结构化 JD Schema
        optimization_result: 优化结果
        pdf_output: PDF 输出

    Returns:
        QualityReport 包含评分、摘要和建议
    """
    logger.info("Generating quality report")

    # 构建简历完整文本
    resume_text = '\n'.join(s.content for s in optimization_result.sections)

    # 6 维度评分
    keyword_coverage = _compute_keyword_coverage(resume_text, jd)
    semantic_similarity = _compute_semantic_similarity(resume_text, jd)
    fidelity = _compute_fidelity_score(optimization_result)
    formatting = _compute_formatting_score(pdf_output)
    ats = _compute_ats_compatibility(pdf_output, resume_text)
    naturalness = _compute_naturalness_score(optimization_result, resume_text)

    # JD 匹配综合评分
    jd_match = round((keyword_coverage * 0.6 + semantic_similarity * 0.4), 1)

    # AI 筛选评分
    ai_screening = round(
        (jd_match * 0.4 + naturalness * 0.3 + ats * 0.3), 1
    )

    metrics = QualityMetrics(
        fidelity_score=fidelity,
        jd_match_score=jd_match,
        ats_compatibility=ats,
        ai_screening_score=ai_screening,
        keyword_coverage=keyword_coverage,
        semantic_similarity=semantic_similarity,
        formatting_score=formatting,
        naturalness_score=naturalness,
        passed_thresholds=True,
        warnings=[],
    )

    # 阈值检查
    for metric_name, threshold in QUALITY_THRESHOLDS.items():
        metric_value = getattr(metrics, metric_name, None)
        if metric_value is not None and metric_value < threshold:
            metrics.passed_thresholds = False

    # 生成告警
    metrics.warnings = _generate_warnings(metrics)

    # 生成摘要
    if metrics.passed_thresholds:
        summary = f"简历质量良好，综合评分 {jd_match:.1f}/100，通过所有质量阈值"
    else:
        summary = (
            f"简历存在 {len(metrics.warnings)} 项需要改进的地方，"
            f"综合评分 {jd_match:.1f}/100"
        )

    # 生成建议
    recommendations = _generate_recommendations(metrics, jd)

    report = QualityReport(
        metrics=metrics,
        timestamp=datetime.now(),
        summary=summary,
        recommendations=recommendations,
    )

    logger.info("Quality report generated: passed=%s, warnings=%d",
                metrics.passed_thresholds, len(metrics.warnings))

    return report
