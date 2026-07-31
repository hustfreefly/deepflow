"""
SpawnParamsContract — E2E 测试的 spawn_params 契约笼子

铁律：
  1. spawn_params 必须包含 runtime, mode, task, cwd
  2. task 大小必须在 100B-6000B 之间（bootstrap 保证）
  3. 不符合契约 → raise ValidationError

Version: 1.0.0
Date: 2026-07-13
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class SpawnParamsContract(BaseModel):
    """
    spawn_params 契约 — 验证 run_*_pro() 返回值的结构完整性。

    用于 E2E 测试的 Layer 1 验证。
    """

    runtime: Literal["subagent"] = Field(
        description="必须是 subagent runtime"
    )
    mode: Literal["run"] = Field(
        description="必须是 run 模式（一次性执行）"
    )
    task: str = Field(
        min_length=50,
        description="task 文本（bootstrap 引用或内联），最小 50B"
    )
    cwd: str = Field(
        min_length=1,
        description="工作目录（deepflow root）"
    )
    label: str = Field(
        default="",
        description="子 Agent 标签"
    )
    lightContext: bool = Field(
        default=True,
        description="轻量上下文（减少 token 消耗）"
    )

    @field_validator("task")
    @classmethod
    def task_size_check(cls, v: str) -> str:
        """契约笼子：task 大小必须在 50B-6000B 之间"""
        size = len(v.encode("utf-8"))
        if size < 50:
            raise ValueError(
                f"task 过短 ({size}B)，可能是空引用。最小 50B。"
            )
        if size > 6000:
            raise ValueError(
                f"task 超过 6KB ({size}B)，bootstrap 未触发。最大 6000B。"
            )
        return v

    @field_validator("cwd")
    @classmethod
    def cwd_must_exist(cls, v: str) -> str:
        """契约笼子：cwd 目录必须存在"""
        from pathlib import Path
        if not Path(v).is_dir():
            raise ValueError(f"cwd 目录不存在: {v}")
        return v

    class Config:
        extra = "allow"  # 允许额外字段（如 model, thinking 等）


class CrossDomainContract(BaseModel):
    """
    跨域数据流契约 — 验证域间数据传递完整性。

    ADR-009 Phase 3 后，Solution Pro 的跨域输入是 data/living_spec.md；
    frozen_spec.* 已废弃，不再作为契约事实源。
    """

    living_spec_md_exists: bool = Field(
        description="data/living_spec.md 是否存在"
    )
    living_spec_md_size: int = Field(
        ge=100,
        description="living_spec.md 大小（最小 100B）"
    )
    requirement_count: int = Field(
        ge=1,
        description="需求数量（最小 1）"
    )

    class Config:
        extra = "allow"


def validate_spawn_params(params: dict) -> SpawnParamsContract:
    """
    验证 spawn_params dict 是否符合契约。

    Args:
        params: run_*_pro() 返回的 spawn_params dict

    Returns:
        SpawnParamsContract 实例

    Raises:
        ValidationError: 不符合契约
    """
    return SpawnParamsContract.model_validate(params)


def validate_cross_domain(blackboard_dir: str) -> CrossDomainContract:
    """
    验证跨域数据流是否符合契约。

    Args:
        blackboard_dir: 项目 blackboard 目录路径

    Returns:
        CrossDomainContract 实例

    Raises:
        ValidationError: 不符合契约
    """
    from pathlib import Path

    bb = Path(blackboard_dir)

    living_spec_md = bb / "data" / "living_spec.md"
    living_spec_exists = living_spec_md.exists()
    living_spec_size = living_spec_md.stat().st_size if living_spec_exists else 0

    # 从 living_spec.md 读取 requirement_index 数量（MD-first 契约）
    req_count = 0
    if living_spec_exists:
        try:
            from domains.spec_pro.spec_living_md import parse_living_spec_md

            spec = parse_living_spec_md(living_spec_md.read_text(encoding="utf-8"))
            req_count = len(spec.get("requirement_index", []))
        except Exception:
            req_count = 0

    return CrossDomainContract.model_validate({
        "living_spec_md_exists": living_spec_exists,
        "living_spec_md_size": living_spec_size,
        "requirement_count": req_count,
    })
