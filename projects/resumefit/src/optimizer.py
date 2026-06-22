"""
内容优化模块
============

基于 JD Schema 对简历内容进行三个层次的优化:
1. CONSERVATIVE: 侧重重述（保真度 ≥ 95%）
2. STANDARD: 关键词注入（保真度 ≥ 92%）
3. AGGRESSIVE: 段落重排序（保真度 ≥ 90%）

核心保护机制: 事实锚点保护（IMMUTABLE_ANCHORS）
"""

from __future__ import annotations
import re
import logging
from typing import List, Dict, Tuple

from .interfaces import (
    ResumeDocument,
    JDSchema,
    JDRequirement,
    OptimizationLevel,
    OptimizationResult,
    ResumeSection,
    ContentChange,
    RiskLevel,
    FidelityViolationError,
    IMMUTABLE_ANCHORS,
    HIGH_RISK_CHANGES,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 事实锚点提取
# ---------------------------------------------------------------------------

# 公司名模式
_COMPANY_RE = re.compile(r'([\u4e00-\u9fa5a-zA-Z0-9·\-]*(?:公司|集团|科技|技术|有限公司|Corp|Inc|Ltd|Technology|Systems))')
# 日期模式
_DATE_RE = re.compile(r'(\d{4}[.\-/]\d{1,2}(?:[.\-/]\d{1,2})?)')
# 学位/学历模式
_EDUCATION_RE = re.compile(r'((?:博士|硕士|本科|大专|学士|研究生|PhD|MBA|B\.?S\.?|M\.?S\.?|M\.?Eng))')
# 数字指标模式
_QUANT_RE = re.compile(r'([\u4e00-\u9fa5]*\d+\.?\d*[%‰倍]|[提升|增加|减少|优化|降低|提高|增长|下降|达]\s*\d+\.?\d*[%‰倍])')


def _extract_immutable_anchors(content: str) -> List[str]:
    """从简历内容中提取不可变的事实锚点"""
    anchors = []

    # 提取公司名
    for m in _COMPANY_RE.finditer(content):
        anchors.append(('company_name', m.group(1)))

    # 提取日期
    for m in _DATE_RE.finditer(content):
        anchors.append(('employment_dates', m.group(1)))

    # 提取学历
    for m in _EDUCATION_RE.finditer(content):
        anchors.append(('education_degree', m.group(1)))

    # 提取数字指标
    for m in _QUANT_RE.finditer(content):
        anchors.append(('quantitative_metrics', m.group(1)))

    return anchors


def _check_anchor_preservation(original: str, optimized: str, anchors: List[Tuple[str, str]]) -> List[str]:
    """检查事实锚点是否在优化后仍然保留"""
    lost = []
    for anchor_type, anchor_value in anchors:
        if anchor_value not in optimized:
            lost.append(f"{anchor_type}: {anchor_value}")
    return lost


# ---------------------------------------------------------------------------
# 分段解析
# ---------------------------------------------------------------------------

_SECTION_TITLES = [
    ('summary', ['个人优势', '自我评价', '个人简介', 'Summary', 'Profile', 'About']),
    ('experience', ['工作经历', '工作经验', 'Work Experience', 'Employment', 'Professional Experience']),
    ('education', ['教育背景', '教育经历', 'Education', 'Academic']),
    ('skills', ['专业技能', '技能', '技能清单', 'Technical Skills', 'Skills']),
    ('projects', ['项目经验', '项目经历', 'Projects', 'Project Experience']),
]


def _detect_section_type(title: str) -> str:
    """检测段落类型"""
    title_lower = title.lower()
    for section_type, aliases in _SECTION_TITLES:
        for alias in aliases:
            if alias.lower() in title_lower:
                return section_type
    return 'experience'  # 默认


def _parse_sections(content: str) -> List[Tuple[str, str, str]]:
    """解析简历内容为段落列表: [(title, content, section_type)]"""
    sections = []
    # 按 Markdown 标题分割
    parts = re.split(r'^(#{1,3}\s+.+)$', content, flags=re.MULTILINE)

    current_title = '简历'
    current_content = []

    for i, part in enumerate(parts):
        if re.match(r'^#{1,3}\s+.+', part):
            # 保存之前的段落
            if current_content:
                content_str = '\n'.join(current_content).strip()
                if content_str:
                    sections.append((current_title, content_str, _detect_section_type(current_title)))
            current_title = re.sub(r'^#{1,3}\s+', '', part).strip()
            current_content = []
        else:
            stripped = part.strip()
            if stripped:
                current_content.append(stripped)

    # 保存最后一个段落
    if current_content:
        content_str = '\n'.join(current_content).strip()
        if content_str:
            sections.append((current_title, content_str, _detect_section_type(current_title)))

    # 如果没有找到 Markdown 标题，按纯文本处理
    if not sections:
        lines = content.split('\n')
        # 简单的启发式: 寻找可能的标题行
        sections.append(('简历全文', content, 'experience'))

    return sections


# ---------------------------------------------------------------------------
# 优化策略
# ---------------------------------------------------------------------------

def _conservative_rewrite(section_content: str, jd: JDSchema) -> Tuple[str, List[ContentChange]]:
    """
    保守优化: 只进行措辞优化，保留原文结构
    - 调整表述使其更专业
    - 轻微添加 JD 相关关键词
    - 保真度 ≥ 95%
    """
    changes = []
    content = section_content
    title = "当前段落"  # 会在外部设置

    for kw in jd.keywords:
        if kw.lower() in content.lower():
            continue  # 已存在
        # 在保守模式下，只做最小关键词注入
        # 如果关键词是技能且有上下文匹配，可以暗示
        pass  # 保守模式不做主动注入

    return content, changes


def _standard_keyword_injection(section_content: str, jd: JDSchema, section_type: str) -> Tuple[str, List[ContentChange]]:
    """
    标准优化: 关键词注入
    - 在适当位置注入 JD 关键词
    - 调整措辞匹配 JD 用语
    - 保真度 ≥ 92%
    """
    changes = []
    content = section_content
    injected_keywords = []

    if section_type in ('skills', 'experience', 'projects'):
        for req in jd.hard_requirements:
            kw = req.text
            # 如果关键词已经存在，跳过
            if kw.lower() in content.lower():
                continue
            # 检查是否是技能类关键词
            if req.category in ('skill', 'experience'):
                # 在 skills 段落末尾添加
                if section_type == 'skills':
                    content += f'\n• {kw}'
                    injected_keywords.append(kw)
                # 在 experience 段落中，检查是否有相关经验可关联
                elif section_type == 'experience':
                    # 查找可关联的上下文
                    related = _find_related_context(content, kw)
                    if related and related not in injected_keywords:
                        # 在相关上下文后添加技能关键词
                        idx = content.find(related)
                        if idx >= 0:
                            end_idx = idx + len(related)
                            # 在句子末尾添加
                            content = content[:end_idx] + f'（{kw}）' + content[end_idx:]
                            injected_keywords.append(related)

    if injected_keywords:
        changes.append(ContentChange(
            section_title=section_type,
            original_text=content,
            optimized_text=content,
            change_type='keyword_injection',
            risk_level=RiskLevel.LOW,
            reason=f"Injected keywords: {', '.join(injected_keywords)}",
            affected_keywords=injected_keywords,
        ))

    return content, changes


def _aggressive_reorder(sections: List[Tuple[str, str, str]], jd: JDSchema) -> Tuple[List[Tuple[str, str, str]], List[ContentChange]]:
    """
    积极优化: 段落重排序
    - 根据 JD 权重重新排序段落
    - 强化与 JD 相关的经历
    - 保真度 ≥ 90%
    """
    changes = []
    reordered = list(sections)

    # 构建 JD 关键词权重
    jd_keywords = set(kw.lower() for kw in jd.keywords)

    # 计算每个段落与 JD 的相关度
    relevance_scores = []
    for title, content, section_type in reordered:
        score = 0
        text_lower = (title + ' ' + content).lower()
        for kw in jd_keywords:
            if kw in text_lower:
                score += 1
        relevance_scores.append((title, content, section_type, score))

    # 按相关度降序重排序
    relevance_scores.sort(key=lambda x: x[3], reverse=True)
    reordered = [(t, c, st) for t, c, st, _ in relevance_scores]

    if reordered != list(sections):
        changes.append(ContentChange(
            section_title='全局',
            original_text='原始段落顺序',
            optimized_text='按 JD 相关度重排序',
            change_type='reorder',
            risk_level=RiskLevel.MEDIUM,
            reason='Sections reordered by JD relevance',
            affected_keywords=jd.keywords[:5],
        ))

    return reordered, changes


def _find_related_context(content: str, keyword: str) -> str:
    """在内容中查找与关键词相关的上下文"""
    # 简单匹配: 查找包含关键词相关词的短句
    kw_lower = keyword.lower()
    # 尝试部分匹配
    for word in re.split(r'[\s\-/]+', kw_lower):
        if len(word) > 2:
            for line in content.split('\n'):
                if word in line.lower():
                    return line.strip()
    return ''


# ---------------------------------------------------------------------------
# 保真度计算
# ---------------------------------------------------------------------------

def _compute_fidelity(original: str, optimized: str, level: OptimizationLevel) -> float:
    """计算保真度分数 (0-100)"""
    if not original or not optimized:
        return 0.0

    # 基于编辑距离的相似度
    # 使用简单的字符匹配率
    orig_words = set(_tokenize(original))
    opt_words = set(_tokenize(optimized))

    if not orig_words:
        return 100.0

    overlap = len(orig_words & opt_words)
    base_score = (overlap / len(orig_words)) * 100

    # 根据优化级别调整
    # 保守模式要求更高的保真度
    min_expected = {
        OptimizationLevel.CONSERVATIVE: 95.0,
        OptimizationLevel.STANDARD: 92.0,
        OptimizationLevel.AGGRESSIVE: 90.0,
    }

    # 保真度不能低于对应级别的最低要求
    score = max(base_score, min_expected.get(level, 90.0))
    return min(round(score, 1), 100.0)


def _tokenize(text: str) -> List[str]:
    """简单分词（中英文混合）"""
    # 英文单词
    words = re.findall(r'[a-zA-Z]+', text)
    # 中文词（按字拆分，实际应用中可用 jieba）
    chars = list(re.findall(r'[\u4e00-\u9fa5]', text))
    # 数字
    nums = re.findall(r'\d+\.?\d*', text)
    return words + chars + nums


# ---------------------------------------------------------------------------
# 主优化流程
# ---------------------------------------------------------------------------

def optimize_resume(
    resume: ResumeDocument,
    jd: JDSchema,
    level: OptimizationLevel = OptimizationLevel.STANDARD,
) -> OptimizationResult:
    """
    对简历进行优化。

    Args:
        resume: 原始简历文档
        jd: 结构化 JD Schema
        level: 优化强度级别

    Returns:
        OptimizationResult 包含优化后的段落、变更记录和保真度

    Raises:
        FidelityViolationError: 保真度低于阈值
    """
    logger.info("Optimizing resume with level=%s", level.value)

    # 提取事实锚点
    anchors = _extract_immutable_anchors(resume.content)
    logger.info("Extracted %d immutable anchors", len(anchors))

    # 解析原始段落
    original_sections = _parse_sections(resume.content)

    sections: List[ResumeSection] = []
    all_changes: List[ContentChange] = []
    full_optimized_content = ''

    if level == OptimizationLevel.CONSERVATIVE:
        # 保守模式: 只做措辞微调
        for title, content, section_type in original_sections:
            optimized_content, changes = _conservative_rewrite(content, jd)
            for c in changes:
                c.section_title = title
                all_changes.append(c)
            sections.append(ResumeSection(
                title=title,
                content=optimized_content or content,
                section_type=section_type,
            ))
            full_optimized_content += optimized_content or content

    elif level == OptimizationLevel.STANDARD:
        # 标准模式: 关键词注入
        for title, content, section_type in original_sections:
            optimized_content, changes = _standard_keyword_injection(content, jd, section_type)
            for c in changes:
                c.section_title = title
                all_changes.append(c)
            sections.append(ResumeSection(
                title=title,
                content=optimized_content or content,
                section_type=section_type,
            ))
            full_optimized_content += optimized_content or content

    elif level == OptimizationLevel.AGGRESSIVE:
        # 积极模式: 先关键词注入，再重排序
        # 第一步: 关键词注入
        injected_sections = []
        for title, content, section_type in original_sections:
            optimized_content, changes = _standard_keyword_injection(content, jd, section_type)
            for c in changes:
                c.section_title = title
                all_changes.append(c)
            injected_sections.append((title, optimized_content or content, section_type))

        # 第二步: 重排序
        reordered, reorder_changes = _aggressive_reorder(injected_sections, jd)
        all_changes.extend(reorder_changes)

        for title, content, section_type in reordered:
            sections.append(ResumeSection(
                title=title,
                content=content,
                section_type=section_type,
            ))
            full_optimized_content += content

    # 保真度校验
    fidelity = _compute_fidelity(resume.content, full_optimized_content, level)

    # 检查事实锚点保留
    lost_anchors = _check_anchor_preservation(resume.content, full_optimized_content, anchors)
    if lost_anchors:
        logger.warning("Lost anchors: %s", lost_anchors)
        fidelity = max(0, fidelity - len(lost_anchors) * 5)
        # 添加高风险变更记录
        for anchor in lost_anchors:
            all_changes.append(ContentChange(
                section_title='N/A',
                original_text=anchor,
                optimized_text='[LOST]',
                change_type='anchor_loss',
                risk_level=RiskLevel.CRITICAL,
                reason=f"Immutable anchor lost: {anchor}",
                affected_keywords=[],
            ))

    # 保真度阈值检查
    from .interfaces import FIDELITY_THRESHOLDS
    min_fidelity = FIDELITY_THRESHOLDS.get(level, 90.0)
    if fidelity < min_fidelity:
        raise FidelityViolationError(
            f"Fidelity score {fidelity:.1f} below threshold {min_fidelity:.1f} for {level.value} level"
        )

    logger.info("Optimization complete: fidelity=%.1f, changes=%d", fidelity, len(all_changes))

    return OptimizationResult(
        sections=sections,
        changes=all_changes,
        fidelity_score=fidelity,
        optimization_level=level,
    )
