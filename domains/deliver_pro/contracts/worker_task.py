"""
WorkerTask / WorkerResult — Phase 2 Worker 的任务定义和结果。

对标 Solution Pro 的 AgentRequest / AgentResult。
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class WorkerTask(BaseModel):
    """
    单个 Worker 任务定义。

    Orchestrator 根据 ExecutionPlan 生成，传给 Worker Agent。
    """

    task_id: str = Field(description="Task ID")
    wp_id: str = Field(description="WP ID")
    title: str = Field(description="任务标题")
    scenario: str = Field(description="场景: code | report | mixed")
    prompt: str = Field(description="完整 prompt（静态约束 + 动态任务）")
    model: str = Field(default="qwen3.7-plus", description="推荐模型")
    timeout_seconds: int = Field(default=300, description="超时秒数")
    dependencies: list[str] = Field(
        default_factory=list,
        description="依赖的 task_id 列表",
    )
    forced_actions: list[str] = Field(
        default_factory=list,
        description="必须执行的动作",
    )
    expected_outputs: list[dict] = Field(
        default_factory=list,
        description="预期产出路径",
    )


class WorkerOutputMeta(BaseModel):
    """
    Worker 输出元数据（MANIFEST.json）。

    记录产出文件、接口定义、自检结果。
    """

    task_id: str
    wp_id: str
    scenario: str
    status: str = Field(description="COMPLETE | PARTIAL | FAILED")
    # DryRun D-P2-1: Worker prompt (P1-4 约束) 要求写入这两个字段，contract 需对齐
    covered_ac_ids: list[str] = Field(
        default_factory=list,
        description="本 Worker 覆盖的验收标准 ID 列表",
    )
    covered_req_ids: list[str] = Field(
        default_factory=list,
        description="本 Worker 覆盖的需求 ID 列表",
    )
    outputs: list[dict] = Field(
        default_factory=list,
        description="产出文件列表 [{path, type, checksum}]",
    )
    interfaces: dict = Field(
        default_factory=lambda: {"provides": [], "requires": []},
        description="接口定义（编程场景）",
    )
    quality_self_check: dict = Field(
        default_factory=lambda: {
            "acceptance_criteria_met": False,
            "tests_passed": False,
            "lint_passed": False,
            "web_search_count": 0,
            "data_sources_cited": 0,
            "issues_count": 0,
        },
        description="自检结果",
    )
    tool_calls: dict = Field(
        default_factory=lambda: {
            "exec": 0,
            "web_search": 0,
            "read": 0,
            "write": 0,
        },
        description="工具调用统计",
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
    )


class WorkerResult(BaseModel):
    """
    Worker 执行结果。

    Orchestrator 收集所有 WorkerResult 后传给 Integrate Agent。
    """

    task_id: str
    status: str = Field(description="COMPLETE | PARTIAL | FAILED")
    output_meta: Optional[WorkerOutputMeta] = None
    output_dir: str = Field(
        default="",
        description="Worker 输出目录路径",
    )
    error: Optional[str] = None
    attempts: int = Field(default=1, description="执行尝试次数")
    recovery_history: list[dict] = Field(
        default_factory=list,
        description="恢复历史 [{round, action, result}]",
    )
    duration_seconds: float = Field(default=0.0)

    @property
    def is_success(self) -> bool:
        return self.status in ("COMPLETE", "PARTIAL")

    @property
    def is_failed(self) -> bool:
        return self.status == "FAILED"
