"""
Worker 结构化返回契约 (WorkerResult)

所有 Phase Worker 完成任务后，必须在输出末尾附带此 JSON。
loop_runner.py 和 FeedbackStream 依赖此契约解析 Worker 产出。

设计原则:
  - 最小侵入：Worker prompt 末尾追加输出要求，不改 Worker 内部逻辑
  - 容错解析：JSON 解析失败时 fallback 到文件存在性检查
  - 兼容现有：loop_runner.py 的 _file_exists 检查仍作为保底
"""

from __future__ import annotations

import json
import re
from typing import Literal, Optional

from pydantic import BaseModel, Field


class HelpRequest(BaseModel):
    """Worker 在执行过程中请求其他 Agent 帮助"""
    type: Literal["research", "review", "code", "design", "other"] = "other"
    description: str = ""
    priority: Literal["high", "medium", "low"] = "medium"
    context: str = ""


class WorkerResult(BaseModel):
    """
    每个 Worker 必须返回的结构化结果。

    Worker prompt 末尾会追加输出格式要求，
    Worker 在最后输出 ```json ... ``` 块。
    """

    # 基本状态
    status: Literal["success", "partial", "failed"] = "success"
    phase: int = 0
    phase_name: str = ""

    # 产出
    artifacts: dict[str, str] = Field(default_factory=dict)  # {"file_name": "file_path"}
    summary: str = ""  # 一句话摘要（给下一个 phase 的上下文输入）

    # 质量自评
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    issues: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    # 给 AI Judge 的元数据
    metrics: dict[str, float] = Field(default_factory=dict)

    # 动态协作请求（Layer 7 Emergent 用）
    help_needed: Optional[list[HelpRequest]] = None


# ── Prompt 后缀 ──────────────────────────────────────────────────

STRUCTURED_OUTPUT_SUFFIX = """

## 🔴 输出格式要求（必须严格遵守）

完成任务后，在**所有工作完成之后**，在最后输出以下 JSON 块（用 ```json 包裹）：

```json
{{
    "status": "success",
    "phase": {phase_number},
    "phase_name": "{phase_name}",
    "artifacts": {{"文件描述": "文件路径"}},
    "summary": "一句话总结你做了什么、产出了什么",
    "confidence": 0.85,
    "issues": [],
    "warnings": [],
    "metrics": {{}},
    "help_needed": null
}}
```

字段说明：
- **status**: success（全部完成）/ partial（部分完成）/ failed（失败）
- **artifacts**: 你创建的文件的描述和路径（相对于工作目录）
- **summary**: 50 字以内的摘要，供后续 phase 参考
- **confidence**: 你对产出质量的自评分（0=完全没把握，1=非常有把握）
- **issues**: 你遇到的问题（空数组表示没有问题）
- **warnings**: 需要注意但不阻塞的事项
- **help_needed**: null（除非你需要其他专家帮助）

⚠️ 这是你输出的**最后一部分**，不要在 JSON 块之后再写任何内容。
"""


def format_output_suffix(phase_number: int, phase_name: str) -> str:
    """为特定 phase 格式化输出后缀"""
    return STRUCTURED_OUTPUT_SUFFIX.format(
        phase_number=phase_number,
        phase_name=phase_name,
    )


# ── 解析工具 ──────────────────────────────────────────────────────

def parse_worker_result(text: str) -> Optional[WorkerResult]:
    """
    从 Worker 输出文本中解析 WorkerResult。

    策略：
    1. 查找最后一个 ```json ... ``` 块
    2. 尝试解析为 WorkerResult
    3. 解析失败返回 None（调用方 fallback 到文件检查）
    """
    # 查找所有 ```json ... ``` 块
    pattern = r'```json\s*\n(.*?)\n\s*```'
    matches = re.findall(pattern, text, re.DOTALL)

    if not matches:
        return None

    # 从最后一个块开始尝试解析
    for match in reversed(matches):
        try:
            data = json.loads(match.strip())
            result = WorkerResult(**data)
            return result
        except (json.JSONDecodeError, ValueError):
            continue

    return None


def parse_worker_result_safe(text: str, fallback_phase: int = 0, fallback_name: str = "") -> WorkerResult:
    """
    安全解析：失败时返回默认 WorkerResult 而非 None。

    用于 loop_runner.py 集成，保证不中断主流程。
    """
    result = parse_worker_result(text)
    if result is not None:
        return result

    # Fallback: 无法解析时返回保守默认值
    return WorkerResult(
        status="success",  # 假设成功，让文件检查做最终验证
        phase=fallback_phase,
        phase_name=fallback_name,
        summary="[WorkerResult 解析失败，需人工检查]",
        confidence=0.3,  # 低置信度，触发 PostWorker Hook
        warnings=["WorkerResult JSON 解析失败，输出格式可能不正确"],
    )
