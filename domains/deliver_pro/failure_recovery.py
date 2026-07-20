"""
Deliver Pro Worker 故障恢复 — AI Native 设计。

废除 F1-F8 故障分类 + 查表恢复。
LLM 端到端诊断：输入错误信息 + WP 上下文 + 已尝试策略 → 输出诊断 + 恢复方案。
唯一保留的代码：轮次计数器（attempts < max_attempts）。
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from .contracts.recovery_action import RecoveryAction, RecoveryStrategy, WorkerError


class WorkerFailureRecovery:
    """
    Worker 故障恢复管理器。

    AI Native 设计：
    - 不预定义故障类型（LLM 理解"超时""空输出""格式错"等概念）
    - 不查表（LLM 根据具体上下文动态生成恢复策略）
    - 唯一代码逻辑：轮次计数器
    """

    def __init__(self, max_attempts: int = 3):
        """
        初始化故障恢复管理器。

        Args:
            max_attempts: 最大恢复尝试次数（默认 3）
        """
        self.max_attempts = max_attempts

    # diagnose() 已移除 — 与 build_recovery_prompt() 重复
    # 使用 build_recovery_prompt() 直接生成诊断 prompt

    def build_recovery_prompt(self, error: WorkerError) -> str:
        """
        构建 LLM 诊断 prompt。

        Args:
            error: Worker 错误信息

        Returns:
            格式化的诊断 prompt
        """
        # 构建已尝试策略的历史记录
        history_text = ""
        if error.recovery_history:
            history_lines = []
            for i, attempt in enumerate(error.recovery_history, 1):
                round_num = attempt.get("round", i)
                action = attempt.get("action", "unknown")
                result = attempt.get("result", "unknown")
                history_lines.append(f"  轮次 {round_num}: 策略={action}, 结果={result}")
            history_text = "\n".join(history_lines)
        else:
            history_text = "  （首次失败，无历史记录）"

        # 构建上下文信息
        context_text = ""
        if error.context:
            context_lines = []
            for key, value in error.context.items():
                context_lines.append(f"  - {key}: {value}")
            context_text = "\n".join(context_lines)
        else:
            context_text = "  （无额外上下文）"

        prompt = f"""你是 Deliver Pro Worker 故障诊断专家。

## 任务
分析 Worker 执行失败的原因，并给出具体的恢复方案。

## 错误信息
- Task ID: {error.task_id}
- 错误类型: {error.error_type}
- 错误消息: {error.message}

## 错误上下文
{context_text}

## 已尝试的恢复策略
{history_text}

## 你的输出
请输出以下 JSON 格式的诊断结果：

```json
{{
  "task_id": "{error.task_id}",
  "diagnosis": "对失败原因的详细分析（50-100字）",
  "recovery_action": "retry | switch_model | split_wp | simplify | add_context | skip",
  "specific_changes": "具体的修改建议（如：换用 gpt-4o 模型 / 将任务拆分为 T-001a 和 T-001b / 补充 API 文档上下文）",
  "confidence": 0.0-1.0,
  "suggested_model": "如果 recovery_action=switch_model，推荐模型名称；否则 null"
}}
```

## 恢复策略说明
- `retry`: 原样重试（适用于临时性错误，如网络超时）
- `switch_model`: 换模型（适用于当前模型能力不足）
- `split_wp`: 拆分任务（适用于任务过于复杂）
- `simplify`: 简化任务（适用于任务超出能力范围）
- `add_context`: 补充上下文（适用于信息不足）
- `skip`: 跳过（标记为 FAILED，适用于无法恢复的错误）

## 注意事项
1. 不要重复已失败的策略
2. confidence 反映你对恢复方案的信心度
3. specific_changes 必须具体可执行
4. 如果 3 轮恢复均失败，建议 skip
"""
        return prompt

    def should_retry(self, attempts: int) -> bool:
        """
        判断是否应该重试。

        Args:
            attempts: 已尝试次数

        Returns:
            True 如果应该继续重试
        """
        return attempts < self.max_attempts

    def record_attempt(
        self,
        error: WorkerError,
        action: RecoveryAction,
        result: str,
    ) -> None:
        """
        记录恢复尝试。

        Args:
            error: Worker 错误（会被更新）
            action: 恢复动作
            result: 恢复结果（"success" / "failed" / "partial"）
        """
        attempt_record = {
            "round": len(error.recovery_history) + 1,
            "action": action.recovery_action.value,
            "specific_changes": action.specific_changes,
            "confidence": action.confidence,
            "result": result,
            "timestamp": datetime.now().isoformat(),
        }
        error.recovery_history.append(attempt_record)

    def get_next_strategy(self, error: WorkerError) -> Optional[RecoveryStrategy]:
        """
        根据历史记录推荐下一个策略。

        注意：这是辅助方法，实际决策由 LLM 做出。

        Args:
            error: Worker 错误

        Returns:
            推荐的策略（如果有的话）
        """
        if not error.recovery_history:
            return RecoveryStrategy.RETRY

        # 提取已尝试的策略
        tried_strategies = {
            attempt.get("action")
            for attempt in error.recovery_history
        }

        # 简单启发式：如果 retry 失败，尝试 add_context
        if "retry" in tried_strategies and "add_context" not in tried_strategies:
            return RecoveryStrategy.ADD_CONTEXT

        # 如果 add_context 也失败，尝试 simplify
        if "add_context" in tried_strategies and "simplify" not in tried_strategies:
            return RecoveryStrategy.SIMPLIFY

        # 如果 simplify 也失败，尝试 split_wp
        if "simplify" in tried_strategies and "split_wp" not in tried_strategies:
            return RecoveryStrategy.SPLIT_WP

        # 多种策略都失败，建议 skip
        return RecoveryStrategy.SKIP


__all__ = ["WorkerFailureRecovery"]
