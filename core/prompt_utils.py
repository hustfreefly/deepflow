"""
PromptUtils — Prompt 工具函数集合

解决 V39 截断、V34-V37 灌入、重复代码问题。
纯函数设计，无状态，不依赖 LLM。

契约笼子：
- 输入输出通过 Pydantic 验证
- 阈值可配置（环境变量覆盖）
- fail-fast 策略（不静默降级）
"""
from __future__ import annotations

import os
import re
import hashlib
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, field_validator

# ============================================================================
# 配置（可环境变量覆盖）
# ============================================================================

TASK_SIZE_WARN_BYTES = int(os.getenv("TASK_SIZE_WARN_BYTES", "2048"))
TASK_SIZE_BLOCK_BYTES = int(os.getenv("TASK_SIZE_BLOCK_BYTES", "6000"))

# 已知危险模式（G2 防灌入）
DANGEROUS_PATTERNS = [
    r"ignore\s+previous\s+instructions",
    r"system\s*:\s*override",
    r"<script[^>]*>",
    r"javascript\s*:",
    r"data\s*:\s*text/html",
    r"you\s+are\s+now\s+(?:a|an)\s+",
    r"disregard\s+(?:all\s+)?(?:previous\s+)?(?:rules?|instructions?)",
]

# ============================================================================
# Pydantic 契约
# ============================================================================

class PromptRenderResult(BaseModel):
    """render_prompt() 返回结果"""
    content: str = Field(..., description="渲染后内容")
    size: int = Field(..., ge=0, description="字节数")
    content_hash: str = Field(..., description="内容哈希（前 8 位）")
    
    @field_validator("content")
    @classmethod
    def content_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("渲染后内容不能为空")
        return v


class TaskSizeCheckResult(BaseModel):
    """check_task_size() 返回结果"""
    ok: bool = Field(..., description="是否通过")
    size: int = Field(..., ge=0, description="实际大小")
    warn_threshold: int = Field(..., ge=0, description="警告阈值")
    block_threshold: int = Field(..., ge=0, description="阻断阈值")
    level: str = Field(..., description="级别: ok | warn | block")
    
    @field_validator("level")
    @classmethod
    def level_valid(cls, v: str) -> str:
        if v not in ("ok", "warn", "block"):
            raise ValueError(f"level 必须是 ok|warn|block，收到 {v!r}")
        return v


class InjectionCheckResult(BaseModel):
    """detect_injection() 返回结果"""
    clean: bool = Field(..., description="是否干净")
    matches: list[str] = Field(default_factory=list, description="匹配的危险模式")
    
    @field_validator("matches")
    @classmethod
    def matches_not_null(cls, v: list[str]) -> list[str]:
        return v or []


class ValidateAllResult(BaseModel):
    """validate_all() 返回结果"""
    ok: bool = Field(..., description="是否全部通过")
    errors: list[str] = Field(default_factory=list, description="错误列表")
    warnings: list[str] = Field(default_factory=list, description="警告列表")
    
    @field_validator("errors", "warnings")
    @classmethod
    def lists_not_null(cls, v: list[str]) -> list[str]:
        return v or []


# ============================================================================
# 核心函数
# ============================================================================

def load_prompt(prompt_path: str | Path) -> str:
    """
    加载 prompt 文件内容。
    
    Args:
        prompt_path: prompt 文件路径
        
    Returns:
        prompt 内容（已剥离 Front Matter）
        
    Raises:
        FileNotFoundError: 文件不存在
        ValueError: 文件为空
    """
    path = Path(prompt_path)
    if not path.exists():
        raise FileNotFoundError(f"Prompt 文件不存在: {path}")
    
    content = path.read_text(encoding="utf-8")
    if not content.strip():
        raise ValueError(f"Prompt 文件为空: {path}")
    
    # 剥离 YAML Front Matter
    content = _strip_front_matter(content)
    
    return content


def render_prompt(
    prompt_path: str | Path,
    **variables: str,
) -> PromptRenderResult:
    """
    渲染 prompt（变量替换）。
    
    模板语法：
    - {{variable}} 必需变量，缺失则 fail-fast
    - {variable} 可选变量，缺失则保留原文
    
    Args:
        prompt_path: prompt 文件路径
        **variables: 变量键值对
        
    Returns:
        PromptRenderResult(content, size, content_hash)
        
    Raises:
        FileNotFoundError: 文件不存在
        ValueError: 必需变量缺失
    """
    content = load_prompt(prompt_path)
    
    # 检查必需变量（双花括号）
    required_vars = re.findall(r"\{\{(\w+)\}\}", content)
    for var in required_vars:
        if var not in variables:
            raise ValueError(f"必需变量缺失: {var!r}")
    
    # 替换必需变量（双花括号）
    for key, value in variables.items():
        content = content.replace(f"{{{{{key}}}}}", str(value))
    
    # 替换可选变量（单花括号）— 只替换提供的变量
    for key, value in variables.items():
        content = content.replace(f"{{{key}}}", str(value))
    
    # 计算哈希
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:8]
    
    return PromptRenderResult(
        content=content,
        size=len(content.encode("utf-8")),
        content_hash=content_hash,
    )


def check_task_size(
    text: str,
    warn_bytes: Optional[int] = None,
    block_bytes: Optional[int] = None,
) -> TaskSizeCheckResult:
    """
    检查 task 大小。
    
    Args:
        text: task 文本
        warn_bytes: 警告阈值（默认从环境变量读取）
        block_bytes: 阻断阈值（默认从环境变量读取）
        
    Returns:
        TaskSizeCheckResult(ok, size, level)
    """
    warn = warn_bytes if warn_bytes is not None else TASK_SIZE_WARN_BYTES
    block = block_bytes if block_bytes is not None else TASK_SIZE_BLOCK_BYTES
    
    size = len(text.encode("utf-8"))
    
    if size >= block:
        level = "block"
        ok = False
    elif size >= warn:
        level = "warn"
        ok = True
    else:
        level = "ok"
        ok = True
    
    return TaskSizeCheckResult(
        ok=ok,
        size=size,
        warn_threshold=warn,
        block_threshold=block,
        level=level,
    )


def detect_injection(text: str) -> InjectionCheckResult:
    """
    检测 prompt 注入（已知危险模式）。
    
    Args:
        text: 待检测文本
        
    Returns:
        InjectionCheckResult(clean, matches)
    """
    matches = []
    text_lower = text.lower()
    
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, text_lower, re.IGNORECASE):
            matches.append(pattern)
    
    return InjectionCheckResult(
        clean=len(matches) == 0,
        matches=matches,
    )


def write_blackboard_prompt(
    blackboard_dir: str | Path,
    name: str,
    content: str,
    subdir: str = "stages",
) -> Path:
    """
    写入 prompt 到 blackboard（原子写）。
    
    Args:
        blackboard_dir: blackboard 根目录
        name: 文件名（不含扩展名）
        content: prompt 内容
        subdir: 子目录（默认 "stages"）
        
    Returns:
        写入的文件路径
        
    Raises:
        ValueError: name 包含路径分隔符
    """
    bb_path = Path(blackboard_dir)
    target_dir = bb_path / subdir
    
    # 安全检查：name 不能包含路径分隔符
    if "/" in name or "\\" in name:
        raise ValueError(f"name 不能包含路径分隔符: {name!r}")
    
    # 确保目录存在
    target_dir.mkdir(parents=True, exist_ok=True)
    
    # 原子写（.tmp + rename）
    target_file = target_dir / f"{name}.md"
    tmp_file = target_file.with_suffix(".tmp")
    
    tmp_file.write_text(content, encoding="utf-8")
    tmp_file.rename(target_file)
    
    return target_file


def validate_all(
    prompt_path: str | Path,
    variables: dict[str, str],
    check_size: bool = True,
    check_injection: bool = True,
    task_text: Optional[str] = None,
) -> ValidateAllResult:
    """
    spawn 前完整预检。
    
    Args:
        prompt_path: prompt 文件路径
        variables: 变量键值对
        check_size: 是否检查大小
        check_injection: 是否检查注入
        task_text: task 文本（用于大小检查，如果为 None 则用渲染后内容）
        
    Returns:
        ValidateAllResult(ok, errors, warnings)
    """
    errors = []
    warnings = []
    
    # 1. 检查文件存在
    path = Path(prompt_path)
    if not path.exists():
        errors.append(f"文件不存在: {path}")
        return ValidateAllResult(ok=False, errors=errors, warnings=warnings)
    
    # 2. 渲染（检查必需变量）
    try:
        result = render_prompt(prompt_path, **variables)
    except ValueError as e:
        errors.append(str(e))
        return ValidateAllResult(ok=False, errors=errors, warnings=warnings)
    
    # 3. 检查未替换变量（单花括号残留）
    unresolved = re.findall(r"\{(\w+)\}", result.content)
    if unresolved:
        warnings.append(f"可能存在未替换变量: {unresolved[:5]}")
    
    # 4. 大小检查
    if check_size:
        text_to_check = task_text if task_text else result.content
        size_result = check_task_size(text_to_check)
        if size_result.level == "block":
            errors.append(
                f"Task 大小 {size_result.size}B 超过阻断阈值 {size_result.block_threshold}B"
            )
        elif size_result.level == "warn":
            warnings.append(
                f"Task 大小 {size_result.size}B 超过警告阈值 {size_result.warn_threshold}B"
            )
    
    # 5. 注入检查
    if check_injection:
        injection_result = detect_injection(result.content)
        if not injection_result.clean:
            errors.append(
                f"检测到危险模式: {injection_result.matches}"
            )
    
    return ValidateAllResult(
        ok=len(errors) == 0,
        errors=errors,
        warnings=warnings,
    )


# ============================================================================
# 内部辅助函数
# ============================================================================

def _strip_front_matter(content: str) -> str:
    """剥离 YAML Front Matter"""
    if not content.startswith("---"):
        return content
    
    # 查找第二个 ---
    end_idx = content.find("---", 3)
    if end_idx == -1:
        return content
    
    # 返回 Front Matter 之后的内容
    return content[end_idx + 3:].lstrip()


# ============================================================================
# 便捷 API（可选类封装）
# ============================================================================

class PromptUtils:
    """
    便捷类封装（可选）。
    
    如果不需要实例化，可以直接使用模块级函数。
    此类仅提供命名空间和组织。
    """
    
    @staticmethod
    def load(prompt_path: str | Path) -> str:
        return load_prompt(prompt_path)
    
    @staticmethod
    def render(prompt_path: str | Path, **variables: str) -> PromptRenderResult:
        return render_prompt(prompt_path, **variables)
    
    @staticmethod
    def check_size(text: str, **kwargs) -> TaskSizeCheckResult:
        return check_task_size(text, **kwargs)
    
    @staticmethod
    def check_injection(text: str) -> InjectionCheckResult:
        return detect_injection(text)
    
    @staticmethod
    def write(bb_dir: str | Path, name: str, content: str, **kwargs) -> Path:
        return write_blackboard_prompt(bb_dir, name, content, **kwargs)
    
    @staticmethod
    def validate(prompt_path: str | Path, variables: dict, **kwargs) -> ValidateAllResult:
        return validate_all(prompt_path, variables, **kwargs)
