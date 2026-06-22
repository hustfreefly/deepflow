"""
ResumeFit Core Interfaces
==========================

核心接口契约定义，所有模块必须遵守。

Version: 1.0.0
Created: 2026-06-01
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Union
from enum import Enum
from datetime import datetime


# ============================================================================
# 枚举类型
# ============================================================================

class OptimizationLevel(Enum):
    """优化强度级别"""
    CONSERVATIVE = "conservative"  # 保守：保真度 ≥ 95%
    STANDARD = "standard"        # 标准：保真度 ≥ 92%
    AGGRESSIVE = "aggressive"    # 积极：保真度 ≥ 90%


class JDInputType(Enum):
    """JD 输入类型"""
    TEXT = "text"
    IMAGE = "image"
    PDF = "pdf"


class RiskLevel(Enum):
    """变更风险等级"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# ============================================================================
# 输入数据结构
# ============================================================================

@dataclass
class ResumeDocument:
    """基础简历文档"""
    content: str                          # 简历内容（Markdown 或纯文本）
    format: str = "markdown"              # 格式：markdown / plaintext / json
    metadata: Dict[str, any] = field(default_factory=dict)  # 元数据（姓名、联系方式等）


@dataclass
class JDInput:
    """职位描述输入"""
    content: str                          # JD 内容
    input_type: JDInputType               # 输入类型
    source_url: Optional[str] = None      # 来源 URL（可选）
    ocr_confidence: Optional[float] = None  # OCR 置信度（图片输入时）


@dataclass
class CompanyProfile:
    """公司信息"""
    name: str                             # 公司名称
    industry: Optional[str] = None        # 行业
    size: Optional[str] = None            # 规模
    description: Optional[str] = None     # 公司简介
    tech_stack: List[str] = field(default_factory=list)  # 技术栈


@dataclass
class ResumeFitRequest:
    """简历优化请求"""
    base_resume: ResumeDocument           # 基础简历
    job_description: JDInput              # 职位描述
    company_info: Optional[CompanyProfile] = None  # 公司信息（可选）
    optimization_level: OptimizationLevel = OptimizationLevel.STANDARD
    
    # 用户偏好
    preferred_language: str = "zh"        # 输出语言：zh / en
    max_pages: int = 2                    # 最大页数
    custom_instructions: Optional[str] = None  # 自定义指令


# ============================================================================
# JD Schema 结构
# ============================================================================

@dataclass
class JDRequirement:
    """JD 要求项"""
    text: str                             # 原始文本
    category: str                         # 分类：skill / experience / education / soft_skill
    priority: str                         # 优先级：must / should / nice_to_have
    weight: float = 1.0                   # 权重（0-1）


@dataclass
class JDSchema:
    """结构化 JD Schema"""
    job_title: str                        # 职位名称
    company: str                          # 公司名称
    hard_requirements: List[JDRequirement] = field(default_factory=list)  # 硬约束
    soft_requirements: List[JDRequirement] = field(default_factory=list)  # 软性要求
    keywords: List[str] = field(default_factory=list)  # 关键词列表
    weight_matrix: Dict[str, float] = field(default_factory=dict)  # 权重矩阵
    
    # 解析元数据
    confidence_score: float = 0.0         # 解析置信度
    parsing_notes: List[str] = field(default_factory=list)  # 解析备注


# ============================================================================
# 内容优化结构
# ============================================================================

@dataclass
class ResumeSection:
    """简历段落"""
    title: str                            # 段落标题（如"工作经历"）
    content: str                          # 段落内容
    section_type: str                     # 类型：experience / education / skills / projects / summary


@dataclass
class ContentChange:
    """内容变更记录"""
    section_title: str                    # 所属段落
    original_text: str                    # 原始文本
    optimized_text: str                   # 优化后文本
    change_type: str                      # 变更类型：rewrite / keyword_injection / reorder
    risk_level: RiskLevel                 # 风险等级
    reason: str                           # 变更原因
    affected_keywords: List[str] = field(default_factory=list)  # 影响的关键词


@dataclass
class OptimizationResult:
    """优化结果"""
    sections: List[ResumeSection]         # 优化后的段落
    changes: List[ContentChange]          # 变更日志
    fidelity_score: float                 # 保真度分数（0-100）
    optimization_level: OptimizationLevel  # 实际使用的优化强度


# ============================================================================
# 质量指标结构
# ============================================================================

@dataclass
class QualityMetrics:
    """质量指标"""
    fidelity_score: float                 # 保真度（0-100）
    jd_match_score: float                 # JD 匹配度（0-100）
    ats_compatibility: float              # ATS 兼容性（0-100）
    ai_screening_score: float             # AI 筛选通过率（0-100）
    
    # 详细指标
    keyword_coverage: float = 0.0         # 关键词覆盖率
    semantic_similarity: float = 0.0      # 语义相似度
    formatting_score: float = 0.0         # 排版质量
    naturalness_score: float = 0.0        # 自然度（AI 痕迹）
    
    # 阈值检查
    passed_thresholds: bool = True        # 是否通过所有阈值
    warnings: List[str] = field(default_factory=list)  # 告警信息


@dataclass
class QualityReport:
    """质量报告"""
    metrics: QualityMetrics               # 质量指标
    timestamp: datetime = field(default_factory=datetime.now)
    summary: str = ""                     # 摘要
    recommendations: List[str] = field(default_factory=list)  # 改进建议


# ============================================================================
# PDF 输出结构
# ============================================================================

@dataclass
class PDFOutput:
    """PDF 输出"""
    file_path: str                        # PDF 文件路径
    file_size_bytes: int                  # 文件大小（字节）
    page_count: int                       # 页数
    ats_compatible: bool                  # 是否 ATS 兼容
    text_extractable: bool                # 是否可提取文本（非纯图片）


# ============================================================================
# 完整响应结构
# ============================================================================

@dataclass
class ResumeFitResponse:
    """简历优化响应"""
    optimized_resume: PDFOutput           # 生成的 PDF
    quality_report: QualityReport         # 质量报告
    changes_summary: List[ContentChange]  # 变更日志
    
    # 中间产物（可选，用于调试）
    jd_schema: Optional[JDSchema] = None
    optimization_result: Optional[OptimizationResult] = None
    
    # 元数据
    processing_time_seconds: float = 0.0
    version: str = "1.0.0"


# ============================================================================
# 错误处理
# ============================================================================

class ResumeFitError(Exception):
    """基础异常类"""
    pass


class JDParsingError(ResumeFitError):
    """JD 解析错误"""
    pass


class OCRError(ResumeFitError):
    """OCR 错误"""
    pass


class FidelityViolationError(ResumeFitError):
    """保真度违规错误"""
    pass


class PDFGenerationError(ResumeFitError):
    """PDF 生成错误"""
    pass


# ============================================================================
# 常量定义
# ============================================================================

# 保真度阈值
FIDELITY_THRESHOLDS = {
    OptimizationLevel.CONSERVATIVE: 95.0,
    OptimizationLevel.STANDARD: 92.0,
    OptimizationLevel.AGGRESSIVE: 90.0,
}

# 质量阈值
QUALITY_THRESHOLDS = {
    "jd_match_score": 75.0,
    "ats_compatibility": 85.0,
    "ai_screening_score": 70.0,
    "naturalness_score": 70.0,
}

# 事实锚点类型（不可变更）
IMMUTABLE_ANCHORS = [
    "company_name",
    "job_title",
    "employment_dates",
    "education_institution",
    "education_degree",
    "education_dates",
    "quantitative_metrics",  # 数字指标（如"提升 30%"）
]

# 高风险变更类型（需用户确认）
HIGH_RISK_CHANGES = [
    "new_company_added",
    "new_project_added",
    "new_skill_added",
    "date_modification",
    "metric_modification",
]
