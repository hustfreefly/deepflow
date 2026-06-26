#!/usr/bin/env python3
"""
DeepFlow Watcher 契约层

Pydantic 模型作为唯一真相源，强制约束：
1. watcher_config.json 的结构和合法性
2. delivery 配置的合法性
3. wrapper prompt 的模板（禁止 LLM 自行判断）

所有 watcher 配置必须通过此契约验证。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Stage File 配置
# ---------------------------------------------------------------------------

class StageFile(BaseModel):
    """单个 stage 文件的配置"""
    name: str = Field(description="显示名称")
    seq: int = Field(ge=1, description="阶段序号")
    icon: str = Field(default="📄", description="图标")
    merge_group: Optional[str] = Field(default=None, description="并行阶段合并组")


class ScanDir(BaseModel):
    """扫描目录配置"""
    path: str = Field(description="相对于 base_path 的路径")
    pattern: str = Field(default="*.json", description="glob 模式")
    stage_files: Dict[str, StageFile] = Field(description="文件名 → 配置映射")


# ---------------------------------------------------------------------------
# Detection 配置
# ---------------------------------------------------------------------------

class DetectionConfig(BaseModel):
    """完成检测和阶段扫描配置"""
    completed_file: str = Field(default=".completed", description="完成标记文件名")
    completed_timestamp_field: str = Field(default="completed_at", description="时间戳字段名")
    scan_dirs: List[ScanDir] = Field(min_length=1, description="扫描目录列表")
    total_stages: int = Field(ge=1, description="总阶段数")
    final_artifact: str = Field(description="最终交付物文件名")


# ---------------------------------------------------------------------------
# Limits 配置
# ---------------------------------------------------------------------------

class LimitsConfig(BaseModel):
    """运行限制配置"""
    max_runs: int = Field(ge=1, le=100, default=20, description="最大巡检次数")
    timeout_minutes: int = Field(ge=5, le=120, default=60, description="超时时间（分钟）")
    circuit_breaker_threshold: int = Field(ge=1, le=10, default=3, description="熔断阈值")


# ---------------------------------------------------------------------------
# Templates 配置
# ---------------------------------------------------------------------------

class TemplatesConfig(BaseModel):
    """消息模板配置"""
    progress: str = Field(default="📊 {display_name}进度 ({completed}/{total})\n{stage_lines}\n已耗时: {elapsed_time}")
    completed: str = Field(default="✅ {display_name}完成！\n📊 {completed}/{total} 阶段 | 耗时 {elapsed_time}")
    failed: str = Field(default="⚠️ {display_name}失败\n已完成: {completed}/{total}\n原因: {error}")
    timeout: str = Field(default="⚠️ {display_name}超时（已运行 {timeout_minutes} 分钟）")
    circuit_break: str = Field(default="⚠️ 连续 {failures} 次无输出，可能已停止")


# ---------------------------------------------------------------------------
# Auto-Chain 配置
# ---------------------------------------------------------------------------

class AutoChainConfig(BaseModel):
    """下游管线自动触发配置"""
    enabled: bool = Field(default=False, description="是否启用自动链")
    next_pipeline: Optional[str] = Field(default=None, description="下游管线 ID")
    trigger_on: Literal["completed"] = Field(default="completed", description="触发条件")
    trigger_file: str = Field(default=".auto_chain_trigger", description="触发文件名")


# ---------------------------------------------------------------------------
# WatcherConfig — 主契约
# ---------------------------------------------------------------------------

class WatcherConfig(BaseModel):
    """
    DeepFlow Pipeline Watcher 配置契约

    所有 watcher_config.json 必须通过此模型验证。
    违反任何约束会抛出 ValidationError。
    """
    schema_version: Literal["deepflow/pipeline_watcher_config/v2"] = Field(
        alias="$schema",
        default="deepflow/pipeline_watcher_config/v2"
    )
    pipeline_id: str = Field(description="管线唯一 ID")
    display_name: str = Field(description="管线显示名称")
    limits: LimitsConfig = Field(default_factory=LimitsConfig)
    detection: DetectionConfig
    templates: TemplatesConfig = Field(default_factory=TemplatesConfig)
    stage_symbols: Dict[str, str] = Field(
        default={"done": "✅", "running": "⏳", "pending": "⬜"},
        description="阶段状态图标"
    )
    auto_chain: AutoChainConfig = Field(default_factory=AutoChainConfig)

    model_config = {"populate_by_name": True}

    @field_validator("pipeline_id")
    @classmethod
    def validate_pipeline_id(cls, v: str) -> str:
        allowed = {"solution_pro", "ship_pro", "spec_pro", "research_pro"}
        if v not in allowed:
            raise ValueError(f"pipeline_id must be one of {allowed}, got '{v}'")
        return v

    def to_json(self, path: Path) -> None:
        """导出为 JSON 文件"""
        data = self.model_dump(by_alias=True, exclude_none=True)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False))

    @classmethod
    def from_json(cls, path: Path) -> "WatcherConfig":
        """从 JSON 文件加载并验证"""
        data = json.loads(path.read_text())
        return cls(**data)


# ---------------------------------------------------------------------------
# DeliveryConfig — delivery 配置契约
# ---------------------------------------------------------------------------

class DeliveryConfig(BaseModel):
    """
    Cron delivery 配置契约

    强制约束合法的 delivery 配置组合，防止 cross-app 等问题。
    """
    mode: Literal["announce", "none"] = Field(default="announce")
    channel: Optional[Literal["feishu", "webchat", "telegram", "discord", "slack"]] = Field(
        default=None,
        description="目标 channel，None 表示使用当前会话 channel"
    )
    to: Optional[str] = Field(
        default=None,
        description="目标 ID（open_id / chat_id），None 表示使用当前会话目标"
    )

    @field_validator("to")
    @classmethod
    def validate_to(cls, v: Optional[str]) -> Optional[str]:
        if v and v.startswith("user:"):
            # OpenClaw 不接受 "user:" 前缀，直接用 open_id
            raise ValueError("to must be a bare open_id (e.g. 'ou_xxx'), not 'user:ou_xxx'")
        return v

    def to_cron_dict(self) -> dict:
        """转为 cron(action='add') 的 delivery 参数"""
        result = {"mode": self.mode}
        if self.channel:
            result["channel"] = self.channel
        if self.to:
            result["to"] = self.to
        return result


# ---------------------------------------------------------------------------
# Wrapper Prompt 模板 — 禁止 LLM 自行判断
# ---------------------------------------------------------------------------

WRAPPER_PROMPT_TEMPLATE = """你是 DeepFlow 管线巡检执行器。严格按以下步骤执行：

1. 运行: exec("python3 {deepflow_root}/scripts/pipeline_watcher.py --config {config_path} --base-path {base_path} --run-start-at {run_start_at} {cron_job_id_arg} --state-dir {base_path}")
2. 解析 stdout 的 JSON（必须是合法 JSON）
3. 根据 action 字段：
   - "noop" → 回复 NO_REPLY
   - 其他 → 直接输出 message 字段的文本（delivery 自动推送）
4. 如果 should_remove_cron = true：
   - 如果 cron_job_id 已知 → cron(action="remove", jobId="{cron_job_id}")
   - 如果为空 → cron(action="list") 找到匹配的 job name → cron(action="remove", jobId=<found_id>)
   输出消息后执行删除。

禁止：自行判断进度、编造消息、调用 message tool、跳过任何步骤。
"""


def render_wrapper_prompt(
    config_path: str,
    base_path: str,
    run_start_at: str,
    cron_job_id: str = "",
    deepflow_root: str = "",
) -> str:
    """渲染 wrapper prompt，替换所有变量
    
    cron_job_id 为空时启用 auto-discover 模式（解决鸡生蛋问题）
    """
    cron_arg = f"--cron-job-id {cron_job_id}" if cron_job_id else ""
    return WRAPPER_PROMPT_TEMPLATE.format(
        deepflow_root=deepflow_root,
        config_path=config_path,
        base_path=base_path,
        run_start_at=run_start_at,
        cron_job_id=cron_job_id,
        cron_job_id_arg=cron_arg,
    )


# ---------------------------------------------------------------------------
# 验证函数
# ---------------------------------------------------------------------------

def validate_watcher_config(config_path: Path) -> tuple[bool, list[str]]:
    """
    验证 watcher_config.json 是否符合契约

    Returns:
        (is_valid, errors)
    """
    try:
        WatcherConfig.from_json(config_path)
        return True, []
    except Exception as e:
        return False, [str(e)]


def validate_delivery_config(delivery: dict) -> tuple[bool, list[str]]:
    """
    验证 delivery 配置是否符合契约

    Returns:
        (is_valid, errors)
    """
    try:
        DeliveryConfig(**delivery)
        return True, []
    except Exception as e:
        return False, [str(e)]


# ---------------------------------------------------------------------------
# AI Native Watcher Prompt V3 — LLM 做判断，Python 只做文件扫描
# ---------------------------------------------------------------------------

WATCHER_V3_TEMPLATE = """你是 DeepFlow 管线巡检员。

1. 运行: exec("python3 {deepflow_root}/scripts/watcher_scan.py {base_path} {config_path} --run-start-at {run_start_at}")
2. 解析 stdout JSON。
3. 根据数据决定动作：
   - completed.exists=true 且 status="completed" → 用完成模板输出消息，然后 cron remove
   - completed.exists=true 且 status="failed" → 用失败模板输出消息，然后 cron remove
   - has_new=true → 用进度模板输出消息
   - run_count > {max_runs} → 输出超时消息，然后 cron remove
   - 其他 → NO_REPLY
4. cron remove: cron(action="remove", jobId="{cron_job_id}")
   如果 jobId 为空: cron(action="list") 找 name 含 "watcher" 的 job → remove

## 输出模板（必须使用，不可自行编写）

进度: 🟠 [{display_name}] {{current_phase}}
{{progress_bar}} {{completed}}/{{total}} 阶段
⏱️ {{elapsed}}min

完成: ✅ {display_name} 完成！{{completed}}/{{total}} 阶段 | {{elapsed}}min

失败: ⚠️ {display_name} 失败（{{completed}}/{{total}}）

超时: ⚠️ {display_name} 超时（{{max_runs}} 次巡检）

## 进度条
completed/total → "█"×completed + "░"×(total-completed)

## 规则
- 只输出模板文本，不输出 JSON
- NO_REPLY 时不输出任何文本
- 先发模板消息，再 cron remove"""


def render_v3_prompt(
    config_path: str,
    base_path: str,
    run_start_at: str,
    cron_job_id: str = "",
    deepflow_root: str = "",
    display_name: str = "Pipeline",
    max_runs: int = 15,
) -> str:
    """Render AI Native Watcher V3 prompt.
    
    LLM does judgment + formatting, Python only scans files.
    ~600 tokens per run (vs ~2000 for V2).
    """
    return WATCHER_V3_TEMPLATE.format(
        deepflow_root=deepflow_root,
        base_path=base_path,
        config_path=config_path,
        run_start_at=run_start_at,
        cron_job_id=cron_job_id,
        display_name=display_name,
        max_runs=max_runs,
    )


def build_v3_cron_payload(
    config_path: str,
    base_path: str,
    run_start_at: str,
    cron_job_id: str = "",
    deepflow_root: str = "",
    display_name: str = "Pipeline",
    max_runs: int = 15,
    pipeline_id: str = "unknown",
) -> dict:
    """Build complete cron job payload for AI Native Watcher V3."""
    prompt = render_v3_prompt(
        config_path=config_path,
        base_path=base_path,
        run_start_at=run_start_at,
        cron_job_id=cron_job_id,
        deepflow_root=deepflow_root,
        display_name=display_name,
        max_runs=max_runs,
    )
    return {
        "name": f"deepflow_watcher_{pipeline_id}_{run_start_at[:16].replace(':', '')}",
        "schedule": {"kind": "every", "everyMs": 180000},
        # 🔴 isolated 避免 SessionTakeoverError（current/session: 会和活跃会话冲突）
        "sessionTarget": "isolated",
        "payload": {
            "kind": "agentTurn",
            "message": prompt,
            "timeoutSeconds": 60,
            "lightContext": True,
        },
        # delivery 需要显式 channel + to，isolated 会话无法自动推断
        "delivery": {"mode": "announce"},
        "enabled": True,
    }


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python watcher_config.py <config.json>")
        sys.exit(1)

    path = Path(sys.argv[1])
    is_valid, errors = validate_watcher_config(path)
    if is_valid:
        print(f"✅ {path} is valid")
    else:
        print(f"❌ {path} is invalid:")
        for err in errors:
            print(f"   {err}")
        sys.exit(1)
