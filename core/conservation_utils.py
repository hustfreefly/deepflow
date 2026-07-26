"""
ConservationUtils — 信息守恒验证工具

解决跨域信息流断裂问题（P2 原则：信息守恒）。
验证 semantic_anchors 在上游→下游传递中是否保留。

契约笼子：
- 输入输出通过 Pydantic 验证
- fail-fast 策略（空输入 FAIL）
- 确定性逻辑（不依赖 LLM）
"""
from __future__ import annotations

import re
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


# ============================================================================
# Pydantic 契约
# ============================================================================

class ConservationResult(BaseModel):
    """verify_anchors() 返回结果"""
    ok: bool = Field(..., description="是否通过")
    preserved: list[str] = Field(default_factory=list, description="保留的锚点")
    lost: list[str] = Field(default_factory=list, description="丢失的锚点")
    alignment_rate: float = Field(..., ge=0.0, le=1.0, description="保留率")
    verdict: str = Field(..., description="判定: PASS | FAIL")
    
    @field_validator("verdict")
    @classmethod
    def verdict_valid(cls, v: str) -> str:
        if v not in ("PASS", "FAIL"):
            raise ValueError(f"verdict 必须是 PASS|FAIL，收到 {v!r}")
        return v
    
    @field_validator("alignment_rate")
    @classmethod
    def rate_consistent(cls, v: float, info) -> float:
        # verdict 和 alignment_rate 必须一致
        verdict = info.data.get("verdict")
        if verdict == "PASS" and v < 0.8:
            raise ValueError(f"verdict=PASS 但 alignment_rate={v} < 0.8")
        if verdict == "FAIL" and v >= 0.8:
            raise ValueError(f"verdict=FAIL 但 alignment_rate={v} >= 0.8")
        return v


# ============================================================================
# 核心函数
# ============================================================================

def verify_anchors(
    upstream_data: str | dict | list,
    downstream_data: str | dict | list,
    threshold: float = 0.8,
) -> ConservationResult:
    """
    验证 semantic_anchors 在上游→下游传递中是否保留。
    
    Args:
        upstream_data: 上游数据（包含 semantic_anchors）
        downstream_data: 下游数据（应该包含 anchors）
        threshold: 保留率阈值（默认 0.8）
        
    Returns:
        ConservationResult(ok, preserved, lost, alignment_rate, verdict)
        
    Raises:
        ValueError: 输入为空
    """
    # 1. 提取 anchors
    upstream_anchors = _extract_anchors(upstream_data)
    
    # 2. 空输入 FAIL
    if not upstream_anchors:
        return ConservationResult(
            ok=False,
            preserved=[],
            lost=[],
            alignment_rate=0.0,
            verdict="FAIL",
        )
    
    # 3. 检查保留
    downstream_text = _to_text(downstream_data)
    preserved = []
    lost = []
    
    for anchor in upstream_anchors:
        if anchor.lower() in downstream_text.lower():
            preserved.append(anchor)
        else:
            lost.append(anchor)
    
    # 4. 计算保留率
    alignment_rate = len(preserved) / len(upstream_anchors)
    
    # 5. 判定
    ok = alignment_rate >= threshold
    verdict = "PASS" if ok else "FAIL"
    
    return ConservationResult(
        ok=ok,
        preserved=preserved,
        lost=lost,
        alignment_rate=round(alignment_rate, 3),
        verdict=verdict,
    )


# ============================================================================
# 内部辅助函数
# ============================================================================

def _extract_anchors(data: str | dict | list) -> list[str]:
    """从数据中提取 semantic_anchors"""
    if isinstance(data, str):
        # 尝试解析 JSON
        try:
            import json
            parsed = json.loads(data)
            return _extract_anchors(parsed)
        except (json.JSONDecodeError, TypeError):
            # 纯文本，提取关键词（简单实现）
            return _extract_keywords(data)
    
    elif isinstance(data, dict):
        # 查找 semantic_anchors 字段
        if "semantic_anchors" in data:
            anchors = data["semantic_anchors"]
            if isinstance(anchors, list):
                return [str(a) for a in anchors]
            elif isinstance(anchors, str):
                return [anchors]
        # 递归查找
        for key, value in data.items():
            if "anchor" in key.lower() or "semantic" in key.lower():
                return _extract_anchors(value)
        return []
    
    elif isinstance(data, list):
        # 列表中的每个元素
        anchors = []
        for item in data:
            anchors.extend(_extract_anchors(item))
        return anchors
    
    return []


def _extract_keywords(text: str, max_keywords: int = 10) -> list[str]:
    """从文本中提取关键词（简单实现）"""
    # 移除常见停用词
    stop_words = {"the", "a", "an", "is", "are", "was", "were", "in", "on", "at", "to", "for", "of", "and", "or"}
    
    # 提取单词
    words = re.findall(r'\b[A-Za-z]{3,}\b', text.lower())
    
    # 过滤停用词
    keywords = [w for w in words if w not in stop_words]
    
    # 去重并限制数量
    unique_keywords = list(dict.fromkeys(keywords))[:max_keywords]
    
    return unique_keywords


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

class ConservationUtils:
    """便捷类封装（可选）"""
    
    @staticmethod
    def verify(upstream, downstream, threshold: float = 0.8) -> ConservationResult:
        return verify_anchors(upstream, downstream, threshold)
