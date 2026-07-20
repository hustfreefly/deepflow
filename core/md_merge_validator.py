"""
ADR-009: MD Merge Validator

验证 LLM merge 输出（current MD + new findings → updated MD）没有丢失关键信息。
分层 diff + 20% 阈值触发 LLM 语义兜底。

契约笼子:
- 输入必须是 str（MD 文本）
- 输出必须是 MergeValidationResult（Pydantic）
- 缺失 section → 自动标记为 missing
- 相似度 < 80% → semantic_review_needed = True
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# ─── 契约笼子: 数据结构 ─────────────────────────────────────────────────────

@dataclass
class SectionDiff:
    """单个 section 的 diff 结果"""
    section: str
    status: str  # "stable" | "modified" | "missing" | "new"
    old_lines: int = 0
    new_lines: int = 0
    similarity: float = 1.0  # 0.0 ~ 1.0

    def __post_init__(self):
        valid_statuses = {"stable", "modified", "missing", "new"}
        if self.status not in valid_statuses:
            raise ValueError(
                f"SectionDiff.status must be one of {valid_statuses}, got '{self.status}'"
            )
        if not (0.0 <= self.similarity <= 1.0):
            raise ValueError(
                f"SectionDiff.similarity must be 0.0~1.0, got {self.similarity}"
            )


@dataclass
class MergeValidationResult:
    """Merge 验证结果（契约笼子输出）"""
    passed: bool
    missing_sections: list[str] = field(default_factory=list)
    modified_sections: list[str] = field(default_factory=list)
    new_sections: list[str] = field(default_factory=list)
    semantic_review_needed: bool = False
    similarity_score: float = 1.0
    details: list[SectionDiff] = field(default_factory=list)
    message: str = ""

    def __post_init__(self):
        if not (0.0 <= self.similarity_score <= 1.0):
            raise ValueError(
                f"MergeValidationResult.similarity_score must be 0.0~1.0, "
                f"got {self.similarity_score}"
            )

    def summary(self) -> str:
        """一句话摘要"""
        parts = []
        if self.missing_sections:
            parts.append(f"missing {len(self.missing_sections)} sections")
        if self.modified_sections:
            parts.append(f"modified {len(self.modified_sections)} sections")
        if self.new_sections:
            parts.append(f"added {len(self.new_sections)} sections")
        if self.semantic_review_needed:
            parts.append("semantic review needed")
        return ", ".join(parts) if parts else "no changes"


# ─── 常量 ────────────────────────────────────────────────────────────────────

# 必需 sections（V2 Schema 定义）
REQUIRED_SECTIONS = frozenset([
    "meta_info",
    "confirmed_reqs",
    "capability_boundary",
    "constraints",
    "gate_decisions",
])

# 可选 sections（V2 Schema 定义）
OPTIONAL_SECTIONS = frozenset([
    "overview",
    "inferred",
    "quality_attrs",
    "user_directives",
    "open_questions",
    "guardrails",
    "traceability",
    "solution_pro_hints",
    "route_recommendation",
    "semantic_anchors",
    "conversation_summary",
])

# 所有合法 section 名
ALL_SECTIONS = REQUIRED_SECTIONS | OPTIONAL_SECTIONS

# 阈值: 相似度低于此值 → 触发 semantic review
SEMANTIC_REVIEW_THRESHOLD = 0.80


# ─── 核心函数 ────────────────────────────────────────────────────────────────

def parse_sections(md_content: str) -> dict[str, str]:
    """
    从 MD 文本中解析 sections。
    
    Returns:
        dict[section_name, section_content]
    
    契约: 
        - section_name 是 ## 后面的第一个单词（不含空格）
        - 忽略 # 一级标题
        - 忽略 YAML frontmatter
    """
    if not isinstance(md_content, str):
        raise TypeError(f"md_content must be str, got {type(md_content).__name__}")

    # 跳过 YAML frontmatter
    content = md_content
    if content.startswith("---"):
        end = content.find("---", 3)
        if end != -1:
            content = content[end + 3:]

    sections: dict[str, str] = {}
    current_section: Optional[str] = None
    current_lines: list[str] = []

    for line in content.split("\n"):
        # 匹配 ## section_name (可选的中文/英文标题)
        m = re.match(r"^##\s+(\S+)", line)
        if m:
            # 保存上一个 section
            if current_section is not None:
                sections[current_section] = "\n".join(current_lines).strip()

            # 提取 section name（取第一个 word，去掉特殊字符）
            raw_name = m.group(1)
            # 如果是中文标题，保留完整标题
            if re.search(r"[\u4e00-\u9fff]", raw_name):
                current_section = raw_name
            else:
                current_section = raw_name.lower().rstrip(":")
            current_lines = []
        elif line.startswith("# "):
            # 一级标题，忽略
            if current_section is not None:
                sections[current_section] = "\n".join(current_lines).strip()
                current_section = None
                current_lines = []
        else:
            if current_section is not None:
                current_lines.append(line)

    # 保存最后一个 section
    if current_section is not None:
        sections[current_section] = "\n".join(current_lines).strip()

    return sections


def _line_similarity(text_a: str, text_b: str) -> float:
    """
    计算两段文本的行级相似度（Jaccard）。
    
    简单高效：把每行当作集合元素，计算 Jaccard 系数。
    不做语义比较（那是 LLM 的事）。
    """
    if not text_a and not text_b:
        return 1.0
    if not text_a or not text_b:
        return 0.0

    lines_a = set(text_a.strip().split("\n"))
    lines_b = set(text_b.strip().split("\n"))

    # 去掉空行
    lines_a.discard("")
    lines_b.discard("")

    if not lines_a and not lines_b:
        return 1.0
    if not lines_a or not lines_b:
        return 0.0

    intersection = lines_a & lines_b
    union = lines_a | lines_b

    return len(intersection) / len(union)


def validate_merge(
    current_md: str,
    updated_md: str,
    threshold: float = SEMANTIC_REVIEW_THRESHOLD,
) -> MergeValidationResult:
    """
    验证 LLM merge 输出没有丢失关键信息。

    分层 diff:
        1. 解析两版 MD 的 sections
        2. 逐 section 对比（行级 Jaccard 相似度）
        3. 检查必需 section 是否都存在
        4. 计算整体相似度
        5. 低于阈值 → semantic_review_needed = True

    Args:
        current_md: 当前版本 MD 文本
        updated_md: LLM 更新后的 MD 文本
        threshold: 相似度阈值（默认 0.80）

    Returns:
        MergeValidationResult

    Raises:
        TypeError: 输入不是 str
        ValueError: threshold 不在 0~1 范围
    """
    # ─── 契约笼子: 输入验证 ──────────────────────────────────────────────
    if not isinstance(current_md, str):
        raise TypeError(f"current_md must be str, got {type(current_md).__name__}")
    if not isinstance(updated_md, str):
        raise TypeError(f"updated_md must be str, got {type(updated_md).__name__}")
    if not (0.0 <= threshold <= 1.0):
        raise ValueError(f"threshold must be 0.0~1.0, got {threshold}")
    if not current_md.strip():
        raise ValueError("current_md is empty")
    if not updated_md.strip():
        raise ValueError("updated_md is empty")

    # ─── Step 1: 解析 sections ───────────────────────────────────────────
    current_sections = parse_sections(current_md)
    updated_sections = parse_sections(updated_md)

    all_section_names = set(current_sections.keys()) | set(updated_sections.keys())

    # ─── Step 2: 逐 section diff ─────────────────────────────────────────
    details: list[SectionDiff] = []
    missing_sections: list[str] = []
    modified_sections: list[str] = []
    new_sections: list[str] = []

    for name in sorted(all_section_names):
        old_content = current_sections.get(name, "")
        new_content = updated_sections.get(name, "")

        if name in current_sections and name not in updated_sections:
            # Section 被删除
            diff = SectionDiff(
                section=name,
                status="missing",
                old_lines=len(old_content.split("\n")),
                new_lines=0,
                similarity=0.0,
            )
            missing_sections.append(name)

        elif name not in current_sections and name in updated_sections:
            # 新增 section
            diff = SectionDiff(
                section=name,
                status="new",
                old_lines=0,
                new_lines=len(new_content.split("\n")),
                similarity=1.0,
            )
            new_sections.append(name)

        else:
            # 两边都有，计算相似度
            sim = _line_similarity(old_content, new_content)
            status = "stable" if sim >= 0.95 else "modified"
            diff = SectionDiff(
                section=name,
                status=status,
                old_lines=len(old_content.split("\n")),
                new_lines=len(new_content.split("\n")),
                similarity=sim,
            )
            if status == "modified":
                modified_sections.append(name)

        details.append(diff)

    # ─── Step 3: 检查必需 section ────────────────────────────────────────
    for req in REQUIRED_SECTIONS:
        if req not in updated_sections:
            if req not in missing_sections:
                missing_sections.append(req)

    # ─── Step 4: 整体相似度 ──────────────────────────────────────────────
    if details:
        # 加权: 必需 section 权重 2x，可选 section 权重 1x
        total_weight = 0.0
        weighted_sum = 0.0
        for d in details:
            weight = 2.0 if d.section in REQUIRED_SECTIONS else 1.0
            total_weight += weight
            weighted_sum += d.similarity * weight
        overall_similarity = weighted_sum / total_weight if total_weight > 0 else 1.0
    else:
        overall_similarity = 1.0

    # ─── Step 5: 判定 ────────────────────────────────────────────────────
    semantic_review = overall_similarity < threshold
    has_missing_required = any(s in REQUIRED_SECTIONS for s in missing_sections)

    passed = not has_missing_required and not semantic_review

    if has_missing_required:
        msg = f"FAIL: missing required sections: {[s for s in missing_sections if s in REQUIRED_SECTIONS]}"
    elif semantic_review:
        msg = f"CONDITIONAL: similarity {overall_similarity:.2f} < {threshold:.2f}, semantic review needed"
    else:
        msg = f"PASS: similarity {overall_similarity:.2f}, no required sections missing"

    result = MergeValidationResult(
        passed=passed,
        missing_sections=missing_sections,
        modified_sections=modified_sections,
        new_sections=new_sections,
        semantic_review_needed=semantic_review,
        similarity_score=round(overall_similarity, 4),
        details=details,
        message=msg,
    )

    logger.info(
        "merge_validator: %s (missing=%d, modified=%d, new=%d, sim=%.2f)",
        "PASS" if passed else "FAIL",
        len(missing_sections),
        len(modified_sections),
        len(new_sections),
        overall_similarity,
    )

    return result


def detect_missing_content(
    current_md: str,
    updated_md: str,
) -> list[str]:
    """
    检测 updated_md 相比 current_md 丢失了哪些具体内容。

    返回丢失内容的描述列表，供 LLM 补回。
    如果没有丢失，返回空列表。

    这是 merge_validator 的辅助函数，用于生成"需要补回"的提示。
    """
    current_sections = parse_sections(current_md)
    updated_sections = parse_sections(updated_md)

    missing_items: list[str] = []

    for name, old_content in current_sections.items():
        new_content = updated_sections.get(name, "")

        if not new_content:
            # 整个 section 丢失
            missing_items.append(f"Section '{name}' is completely missing in updated version")
            continue

        # 检查 section 内的表格行是否丢失
        old_table_rows = _extract_table_rows(old_content)
        new_table_rows = _extract_table_rows(new_content)

        if old_table_rows and new_table_rows:
            missing_rows = old_table_rows - new_table_rows
            if missing_rows:
                for row in list(missing_rows)[:5]:  # 最多报告 5 行
                    missing_items.append(
                        f"Section '{name}': table row missing: {row[:80]}"
                    )

        # 检查 bullet points 是否丢失
        old_bullets = _extract_bullets(old_content)
        new_bullets = _extract_bullets(new_content)

        if old_bullets and new_bullets:
            missing_bullets = old_bullets - new_bullets
            if missing_bullets:
                for bullet in list(missing_bullets)[:5]:
                    missing_items.append(
                        f"Section '{name}': bullet point missing: {bullet[:80]}"
                    )

    return missing_items


# ─── 辅助函数 ────────────────────────────────────────────────────────────────

def _extract_table_rows(content: str) -> set[str]:
    """提取表格中的数据行（跳过头行和分隔行）"""
    rows = set()
    lines = content.strip().split("\n")
    in_table = False
    header_seen = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            if not in_table:
                in_table = True
                header_seen = False
                continue  # 跳过头行
            if not header_seen:
                # 分隔行（|---|---|）
                if re.match(r"^\|[\s\-:|]+\|$", stripped):
                    header_seen = True
                    continue
            if header_seen:
                # 数据行
                cells = [c.strip() for c in stripped.split("|")[1:-1]]
                rows.add(" | ".join(cells))
        else:
            in_table = False
            header_seen = False

    return rows


def _extract_bullets(content: str) -> set[str]:
    """提取无序列表项"""
    bullets = set()
    for line in content.strip().split("\n"):
        stripped = line.strip()
        if stripped.startswith("- ") or stripped.startswith("* "):
            bullets.add(stripped[2:].strip())
    return bullets
