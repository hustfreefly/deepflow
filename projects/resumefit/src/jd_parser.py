"""
JD 解析模块
============

从文本/图片/PDF 格式的职位描述中提取结构化信息。

支持:
- 文本 JD: 正则 + 规则提取硬约束/软性要求
- 图片 JD: PyMuPDF → PaddleOCR fallback
- PDF JD: 文本提取 + OCR fallback
"""

from __future__ import annotations
import re
import os
import logging
from typing import List, Dict, Optional, Tuple

from .interfaces import (
    JDInput,
    JDInputType,
    JDSchema,
    JDRequirement,
    OCRError,
    JDParsingError,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 关键词分类词典
# ---------------------------------------------------------------------------

# 硬约束关键词模式（技能/经验/学历要求）
HARD_KEYWORD_PATTERNS = [
    # 学历
    (r'(?:本科|硕士|博士|大专|学士|研究生|985|211|双一流)', 'education'),
    # 年限
    (r'(\d+)\s*(?:年|年以上|年经验)', 'experience'),
    # 编程语言
    (r'(?i)(Python|Java|JavaScript|TypeScript|C\+\+|Go|Rust|Swift|Kotlin|Scala|Ruby|PHP|SQL|R|MATLAB)', 'skill'),
    # 框架/工具
    (r'(?i)(React|Vue|Angular|Spring|Django|Flask|FastAPI|Node\.js|TensorFlow|PyTorch|Docker|Kubernetes|Git|Linux|AWS|Azure|GCP|MySQL|PostgreSQL|Redis|MongoDB|Elasticsearch|Kafka|Spark|Hadoop)', 'skill'),
    # 软技能
    (r'(?i)(沟通|协调|团队|领导|管理|创新|学习|抗压|表达|逻辑|分析|解决问题|self-motivated|communication|teamwork|leadership|collaboration)', 'soft_skill'),
]

# 软性要求关键词
SOFT_KEYWORDS = [
    '沟通', '协调', '团队', '领导', '管理', '创新', '学习', '抗压',
    '表达', '逻辑', '分析', '解决问题', '责任心', '主动性',
    'communication', 'teamwork', 'leadership', 'collaboration',
    'problem-solving', 'self-motivated', 'detail-oriented',
]

# 优先级关键词
MUST_KEYWORDS = ['必须', '要求', '需要', '至少', '必备', '精通', '熟练掌握',
                  'must', 'required', 'essential', 'mandatory']
SHOULD_KEYWORDS = ['优先', '最好', '建议', '熟悉', '了解',
                   'preferred', 'familiar', 'plus', 'bonus']
NICE_KEYWORDS = ['加分', '加分项', '有.*更好', 'nice to have', 'good to have']


def _classify_priority(text: str) -> str:
    """判断一条要求的优先级: must / should / nice_to_have"""
    text_lower = text.lower()
    for kw in MUST_KEYWORDS:
        if re.search(kw, text_lower):
            return 'must'
    for kw in SHOULD_KEYWORDS:
        if re.search(kw, text_lower):
            return 'should'
    for kw in NICE_KEYWORDS:
        if re.search(kw, text_lower):
            return 'nice_to_have'
    return 'should'  # 默认 should


def _categorize(text: str) -> str:
    """判断一条要求的类别"""
    text_lower = text.lower()
    for pattern, category in HARD_KEYWORD_PATTERNS:
        if re.search(pattern, text_lower):
            if category == 'soft_skill':
                return 'soft_skill'
            return category
    # 检测是否偏软技能
    for kw in SOFT_KEYWORDS:
        if kw.lower() in text_lower:
            return 'soft_skill'
    return 'skill'  # 默认归为 skill


def _extract_job_title(text: str) -> str:
    """从 JD 文本中提取职位名称"""
    patterns = [
        r'职位[名称称]*[:：\s]*(.+?)(?:\n|$)',
        r'岗位[:：\s]*(.+?)(?:\n|$)',
        r'招聘[:：\s]*(.+?)(?:\n|$)',
        r'Job\s*[Tt]itle[:\s]*(.+?)(?:\n|$)',
        r'Position[:\s]*(.+?)(?:\n|$)',
        r'Hiring[:\s]*(.+?)(?:\n|$)',
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            title = m.group(1).strip()
            if len(title) < 50:
                return title
    return '未知职位'


def _extract_company(text: str) -> str:
    """从 JD 文本中提取公司名称"""
    patterns = [
        r'公司[名称]*[:：\s]*(.+?)(?:\n|$)',
        r'企业[:：\s]*(.+?)(?:\n|$)',
        r'Company[:\s]*(.+?)(?:\n|$)',
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            name = m.group(1).strip()
            if len(name) < 50:
                return name
    return '未知公司'


def _split_into_lines(text: str) -> List[str]:
    """将 JD 文本拆分为独立的要求行"""
    # 按换行拆分
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    # 过滤太短或太长的行
    lines = [l for l in lines if 3 < len(l) < 300]
    return lines


def _extract_requirements(text: str) -> Tuple[List[JDRequirement], List[JDRequirement]]:
    """从 JD 文本中提取硬约束和软性要求"""
    lines = _split_into_lines(text)
    hard_reqs: List[JDRequirement] = []
    soft_reqs: List[JDRequirement] = []

    for line in lines:
        category = _categorize(line)
        priority = _classify_priority(line)

        req = JDRequirement(
            text=line,
            category=category,
            priority=priority,
            weight=0.9 if priority == 'must' else (0.7 if priority == 'should' else 0.5),
        )

        if category == 'soft_skill':
            soft_reqs.append(req)
        else:
            hard_reqs.append(req)

    return hard_reqs, soft_reqs


def _extract_keywords(text: str) -> List[str]:
    """从 JD 文本中提取关键词"""
    keywords = []
    # 提取技术关键词
    tech_patterns = [
        r'(?i)(Python|Java|JavaScript|TypeScript|C\+\+|Go|Rust|Swift|Kotlin|Scala|Ruby|PHP|SQL)',
        r'(?i)(React|Vue|Angular|Spring|Django|Flask|FastAPI|Node\.js)',
        r'(?i)(TensorFlow|PyTorch|Docker|Kubernetes|Git|Linux)',
        r'(?i)(AWS|Azure|GCP|MySQL|PostgreSQL|Redis|MongoDB|Elasticsearch|Kafka|Spark|Hadoop)',
        r'(?i)(AI|ML|机器学习|深度学习|NLP|CV|大模型|LLM)',
    ]
    for pat in tech_patterns:
        for m in re.finditer(pat, text):
            kw = m.group(0)
            if kw not in keywords:
                keywords.append(kw)

    # 提取软技能关键词
    for kw in SOFT_KEYWORDS:
        if kw.lower() in text.lower():
            if kw not in keywords:
                keywords.append(kw)

    return keywords


def _build_weight_matrix(hard: List[JDRequirement], soft: List[JDRequirement]) -> Dict[str, float]:
    """构建权重矩阵: category -> average weight"""
    matrix: Dict[str, float] = {}
    for req in hard + soft:
        if req.category not in matrix:
            matrix[req.category] = []
        matrix[req.category].append(req.weight)
    return {k: sum(v) / len(v) for k, v in matrix.items()}


def parse_text_jd(content: str) -> JDSchema:
    """解析文本格式的 JD"""
    logger.info("Parsing text JD, length=%d", len(content))

    job_title = _extract_job_title(content)
    company = _extract_company(content)
    hard_reqs, soft_reqs = _extract_requirements(content)
    keywords = _extract_keywords(content)
    weight_matrix = _build_weight_matrix(hard_reqs, soft_reqs)

    confidence = min(0.95, 0.5 + 0.01 * len(content) / 100) if content else 0.3
    if not hard_reqs and not soft_reqs:
        confidence *= 0.5

    return JDSchema(
        job_title=job_title,
        company=company,
        hard_requirements=hard_reqs,
        soft_requirements=soft_reqs,
        keywords=keywords,
        weight_matrix=weight_matrix,
        confidence_score=round(confidence, 3),
        parsing_notes=[],
    )


def _run_ocr(image_path: str) -> str:
    """运行 OCR 提取文本, 优先 PyMuPDF, fallback 到 PaddleOCR"""
    # Try PyMuPDF first
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(image_path)
        text_parts = []
        for page in doc:
            text_parts.append(page.get_text())
        doc.close()
        text = '\n'.join(text_parts).strip()
        if text:
            logger.info("PyMuPDF OCR extracted %d chars", len(text))
            return text
    except ImportError:
        logger.debug("PyMuPDF not available, trying PaddleOCR")
    except Exception as e:
        logger.debug("PyMuPDF failed: %s, trying PaddleOCR", e)

    # Try PaddleOCR
    try:
        from paddleocr import PaddleOCR
        ocr = PaddleOCR(use_angle_cls=True, lang='ch')
        result = ocr.ocr(image_path, cls=True)
        texts = []
        confidence = 0.0
        count = 0
        for line in result:
            if line:
                for word_info in line:
                    texts.append(word_info[1][0])
                    confidence += word_info[1][1]
                    count += 1
        text = '\n'.join(texts).strip()
        if text:
            avg_confidence = confidence / count if count > 0 else 0.0
            logger.info("PaddleOCR extracted %d chars, confidence=%.3f", len(text), avg_confidence)
            return text
    except ImportError:
        logger.debug("PaddleOCR not available")
    except Exception as e:
        logger.debug("PaddleOCR failed: %s", e)

    raise OCRError("OCR failed: neither PyMuPDF nor PaddleOCR could process the image")


def _extract_text_from_pdf(pdf_path: str) -> str:
    """从 PDF 提取文本, 优先直接提取, fallback 到 OCR"""
    # Try direct text extraction
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(pdf_path)
        text_parts = []
        for page in doc:
            text_parts.append(page.get_text())
        doc.close()
        text = '\n'.join(text_parts).strip()
        if text:
            logger.info("PyMuPDF extracted %d chars from PDF", len(text))
            return text
    except ImportError:
        logger.debug("PyMuPDF not available for PDF text extraction")
    except Exception as e:
        logger.debug("PyMuPDF PDF extraction failed: %s", e)

    # Try pdfplumber
    try:
        import pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            text_parts = []
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    text_parts.append(t)
            text = '\n'.join(text_parts).strip()
            if text:
                logger.info("pdfplumber extracted %d chars from PDF", len(text))
                return text
    except ImportError:
        logger.debug("pdfplumber not available")
    except Exception as e:
        logger.debug("pdfplumber failed: %s", e)

    raise OCRError("PDF text extraction failed: no available text extraction library")


def parse_image_jd(content: str, ocr_confidence: Optional[float] = None) -> JDSchema:
    """解析图片格式的 JD (通过 OCR)"""
    # content is file path for image
    logger.info("Parsing image JD from path: %s", content)

    if not os.path.exists(content):
        raise JDParsingError(f"Image file not found: {content}")

    text = _run_ocr(content)
    if not text:
        raise JDParsingError("OCR returned empty text")

    schema = parse_text_jd(text)
    schema.parsing_notes.append(f"OCR used for image input")
    if ocr_confidence is not None:
        schema.confidence_score = min(schema.confidence_score, ocr_confidence)

    return schema


def parse_pdf_jd(content: str) -> JDSchema:
    """解析 PDF 格式的 JD"""
    # content is file path for PDF
    logger.info("Parsing PDF JD from path: %s", content)

    if not os.path.exists(content):
        raise JDParsingError(f"PDF file not found: {content}")

    text = _extract_text_from_pdf(content)
    if not text:
        raise JDParsingError("PDF extraction returned empty text")

    schema = parse_text_jd(text)
    schema.parsing_notes.append("PDF text extraction used")

    return schema


def parse_jd(jd_input: JDInput) -> JDSchema:
    """
    统一 JD 解析入口。

    Args:
        jd_input: JDInput 包含内容、类型和可选元数据

    Returns:
        JDSchema 结构化职位描述

    Raises:
        JDParsingError: 解析失败
        OCRError: OCR 失败
    """
    logger.info("parse_jd called with type=%s", jd_input.input_type.value)

    if jd_input.input_type == JDInputType.TEXT:
        return parse_text_jd(jd_input.content)
    elif jd_input.input_type == JDInputType.IMAGE:
        return parse_image_jd(jd_input.content, jd_input.ocr_confidence)
    elif jd_input.input_type == JDInputType.PDF:
        return parse_pdf_jd(jd_input.content)
    else:
        raise JDParsingError(f"Unknown JD input type: {jd_input.input_type}")
