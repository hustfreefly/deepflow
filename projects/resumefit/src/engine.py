"""
核心引擎
========

编排完整的简历优化流程:
JD解析 → 内容优化 → 保真度校验 → PDF渲染 → 质量报告

错误处理: 捕获所有 ResumeFitError 子类
"""

from __future__ import annotations
import time
import logging
from typing import Optional

from .interfaces import (
    ResumeFitRequest,
    ResumeFitResponse,
    ResumeFitError,
    JDParsingError,
    OCRError,
    FidelityViolationError,
    PDFGenerationError,
)
from .jd_parser import parse_jd
from .optimizer import optimize_resume
from .fidelity import validate_fidelity
from .pdf_renderer import render_pdf
from .quality import generate_quality_report

logger = logging.getLogger(__name__)


def process_resume(request: ResumeFitRequest) -> ResumeFitResponse:
    """
    完整简历优化流程。

    流程:
    1. JD 解析 (文本/图片/PDF → JDSchema)
    2. 内容优化 (简历 + JD → OptimizationResult)
    3. 保真度校验 (原始简历 vs 优化结果)
    4. PDF 渲染 (OptimizationResult → PDFOutput)
    5. 质量报告 (6 维度评分)

    Args:
        request: ResumeFitRequest 包含所有输入

    Returns:
        ResumeFitResponse 包含 PDF、质量报告和变更摘要

    Raises:
        ResumeFitError: 任何子错误（JDParsingError, OCRError,
                        FidelityViolationError, PDFGenerationError）
    """
    start_time = time.time()
    logger.info("=" * 60)
    logger.info("ResumeFit processing started")
    logger.info("  Optimization level: %s", request.optimization_level.value)
    logger.info("  JD input type: %s", request.job_description.input_type.value)
    logger.info("  Language: %s", request.preferred_language)
    logger.info("=" * 60)

    jd_schema = None
    optimization_result = None
    pdf_output = None
    quality_report = None

    try:
        # ============================================================
        # Step 1: JD 解析
        # ============================================================
        logger.info("[1/5] Parsing job description...")
        try:
            jd_schema = parse_jd(request.job_description)
            logger.info(
                "  ✓ JD parsed: title=%s, company=%s, hard_reqs=%d, soft_reqs=%d, "
                "keywords=%d, confidence=%.3f",
                jd_schema.job_title,
                jd_schema.company,
                len(jd_schema.hard_requirements),
                len(jd_schema.soft_requirements),
                len(jd_schema.keywords),
                jd_schema.confidence_score,
            )
        except (JDParsingError, OCRError) as e:
            logger.error("  ✗ JD parsing failed: %s", e)
            raise

        # ============================================================
        # Step 2: 内容优化
        # ============================================================
        logger.info("[2/5] Optimizing resume content...")
        try:
            optimization_result = optimize_resume(
                resume=request.base_resume,
                jd=jd_schema,
                level=request.optimization_level,
            )
            logger.info(
                "  ✓ Optimization complete: fidelity=%.1f, changes=%d, "
                "sections=%d",
                optimization_result.fidelity_score,
                len(optimization_result.changes),
                len(optimization_result.sections),
            )
        except FidelityViolationError as e:
            logger.error("  ✗ Fidelity violation: %s", e)
            raise
        except ResumeFitError as e:
            logger.error("  ✗ Optimization error: %s", e)
            raise

        # ============================================================
        # Step 3: 保真度校验
        # ============================================================
        logger.info("[3/5] Validating fidelity...")
        try:
            fidelity_score, high_risk = validate_fidelity(
                original_resume=request.base_resume,
                optimization_result=optimization_result,
            )
            logger.info(
                "  ✓ Fidelity validation passed: score=%.1f, high_risk=%d",
                fidelity_score,
                len(high_risk),
            )
            if high_risk:
                logger.warning("  ⚠ %d high-risk changes detected", len(high_risk))
                for hr in high_risk:
                    logger.warning("    - %s: %s", hr.section_title, hr.reason)
        except FidelityViolationError as e:
            logger.error("  ✗ Fidelity validation failed: %s", e)
            raise

        # ============================================================
        # Step 4: PDF 渲染
        # ============================================================
        logger.info("[4/5] Rendering PDF...")
        try:
            pdf_output = render_pdf(
                optimization_result=optimization_result,
                max_pages=request.max_pages,
            )
            logger.info(
                "  ✓ PDF rendered: path=%s, size=%d bytes, "
                "pages=%d, ats=%s, text=%s",
                pdf_output.file_path,
                pdf_output.file_size_bytes,
                pdf_output.page_count,
                pdf_output.ats_compatible,
                pdf_output.text_extractable,
            )
        except PDFGenerationError as e:
            logger.error("  ✗ PDF generation failed: %s", e)
            raise

        # ============================================================
        # Step 5: 质量报告
        # ============================================================
        logger.info("[5/5] Generating quality report...")
        try:
            quality_report = generate_quality_report(
                jd=jd_schema,
                optimization_result=optimization_result,
                pdf_output=pdf_output,
            )
            logger.info(
                "  ✓ Quality report: jd_match=%.1f, ats=%.1f, "
                "naturalness=%.1f, passed=%s",
                quality_report.metrics.jd_match_score,
                quality_report.metrics.ats_compatibility,
                quality_report.metrics.naturalness_score,
                quality_report.metrics.passed_thresholds,
            )
            if quality_report.metrics.warnings:
                for w in quality_report.metrics.warnings:
                    logger.warning("  ⚠ %s", w)
        except ResumeFitError as e:
            logger.error("  ✗ Quality report failed: %s", e)
            raise

        # ============================================================
        # 完成
        # ============================================================
        processing_time = time.time() - start_time

        response = ResumeFitResponse(
            optimized_resume=pdf_output,
            quality_report=quality_report,
            changes_summary=optimization_result.changes,
            jd_schema=jd_schema,
            optimization_result=optimization_result,
            processing_time_seconds=round(processing_time, 3),
            version="1.0.0",
        )

        logger.info("=" * 60)
        logger.info("ResumeFit processing completed in %.3f seconds", processing_time)
        logger.info("=" * 60)

        return response

    except ResumeFitError:
        # 重新抛出已知的 ResumeFitError 子类
        raise
    except Exception as e:
        # 捕获所有未知异常，包装为 ResumeFitError
        logger.error("Unexpected error: %s", e, exc_info=True)
        raise ResumeFitError(f"Unexpected error during processing: {e}")
