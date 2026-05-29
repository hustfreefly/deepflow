"""
Spec Pro Coordinator
====================

契约: cage/spec_pro_v2.0.yaml (L1, L2)
主Agent侧协调器,负责流程控制和状态管理.

职责:
- 初始化 session 和 Blackboard 目录
- 构建 Orchestrator Worker 的 task prompt
- 读写 Blackboard 文件(用户输入,Worker 输出)
- 跟踪对话轮次
- 检查 Safety Valve max_rounds

禁止:
- 包含 LLM 推理逻辑 (RED-SP2-001)
- 直接调用 sessions_spawn (RED-SP2-002)
"""

import json
import os
import time
from datetime import datetime
from typing import Any, Dict, Optional

from core.config.path_config import PathConfig
from domains.spec_pro.models import (
    DialogState,
    LivingSpec,
    MODE_CONFIG,
    RoundAction,
    Scenario,
)

# DeepFlow base directory
_BASE_DIR = PathConfig.resolve().base_dir


class SpecProCoordinator:
    """
    Spec Pro 主Agent侧协调器.

    管理 session 生命周期,Blackboard 文件,轮次追踪.
    不包含 LLM 推理,所有智能由 Worker Agents 完成.
    """

    def __init__(
        self,
        scenario: str = "genesis",
        mode: str = "standard",
        session_prefix: Optional[str] = None,
    ) -> None:
        """
        初始化 Coordinator.

        Args:
            scenario: 场景类型 (genesis/supplement/refine/pivot)
            mode: 对话深度 (quick/standard/deep)
            session_prefix: session ID 前缀(可选)
        """
        # Validate mode
        if mode not in MODE_CONFIG:
            raise ValueError(
                f"Invalid mode '{mode}'. Must be one of: {list(MODE_CONFIG.keys())}"
            )
        # Validate scenario
        try:
            Scenario(scenario)
        except ValueError:
            valid = [s.value for s in Scenario]
            raise ValueError(
                f"Invalid scenario '{scenario}'. Must be one of: {valid}"
            ) from None

        self.scenario = scenario
        self.mode = mode
        self.session_prefix = session_prefix or "spec"
        self.session_id: Optional[str] = None
        self.base_path: Optional[str] = None
        self.current_round: int = 0
        self.state: DialogState = DialogState.START
        self._config = MODE_CONFIG[mode]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def init_session(self, user_input: str) -> Dict[str, Any]:
        """
        初始化 session,创建 Blackboard 目录,写入用户输入,构建首轮 task.

        Args:
            user_input: 用户初始输入文本

        Returns:
            dict with keys: session_id, base_path, orchestrator_task

        Raises:
            ValueError: 输入过短(<5字符)或过长(>2000字符)
            OSError: 目录创建失败
        """
        if len(user_input) < 5:
            raise ValueError(
                f"Input too short ({len(user_input)} chars). Minimum 5 characters."
            )
        if len(user_input) > 2000:
            raise ValueError(
                f"Input too long ({len(user_input)} chars). Maximum 2000 characters."
            )

        # Generate session ID
        self.session_id = self._generate_session_id()
        self.base_path = os.path.join(str(_BASE_DIR), "blackboard", self.session_id)

        # Create directories
        spec_dir = os.path.join(self.base_path, "spec")
        stages_dir = os.path.join(self.base_path, "stages")
        os.makedirs(spec_dir, exist_ok=True)
        os.makedirs(stages_dir, exist_ok=True)

        # Write user input
        input_path = os.path.join(spec_dir, "input.md")
        with open(input_path, "w", encoding="utf-8") as f:
            f.write(user_input)

        # Initialize execution log
        self._write_execution_log("init", {
            "user_input_length": len(user_input),
            "scenario": self.scenario,
            "mode": self.mode,
        })

        # Initialize quality trajectory
        trajectory_path = os.path.join(spec_dir, "quality_trajectory.json")
        with open(trajectory_path, "w", encoding="utf-8") as f:
            json.dump([], f, ensure_ascii=False)

        # Initialize conversation log
        conv_path = os.path.join(spec_dir, "conversation_log.json")
        with open(conv_path, "w", encoding="utf-8") as f:
            json.dump([], f, ensure_ascii=False)

        # Build first round orchestrator task
        self.current_round = 1
        self.state = DialogState.PARSING
        task = self._build_orchestrator_task(
            round_num=1, phase="init"
        )

        return {
            "session_id": self.session_id,
            "base_path": self.base_path,
            "orchestrator_task": task,
        }

    def build_next_round_task(self, user_response: str) -> Dict[str, Any]:
        """
        构建下一轮 Orchestrator Worker task.

        将用户回答写入 Blackboard,检查 Safety Valve max_rounds.

        Args:
            user_response: 用户本轮回答

        Returns:
            dict with keys: orchestrator_task, round_num
            If max_rounds exceeded: {action: 'safety_stop', reason: 'max_rounds'}

        Raises:
            RuntimeError: session 未初始化
        """
        if not self.session_id or not self.base_path:
            raise RuntimeError("Session not initialized. Call init_session() first.")

        self.current_round += 1

        # Safety Valve: max_rounds check
        max_rounds = self._config["max_rounds"]
        if self.current_round > max_rounds:
            return {
                "action": "safety_stop",
                "reason": "max_rounds",
                "message": (
                    f"Reached maximum rounds ({max_rounds}) for mode '{self.mode}'. "
                    "Spec Pro is stopping."
                ),
            }

        # Write user response
        response_path = os.path.join(
            self.base_path, "spec", f"user_response_round_{self.current_round}.md"
        )
        with open(response_path, "w", encoding="utf-8") as f:
            f.write(user_response)

        # Build task
        task = self._build_orchestrator_task(
            round_num=self.current_round, phase="collecting"
        )

        self._write_execution_log("round_start", {
            "round": self.current_round,
            "response_length": len(user_response),
        })

        return {
            "orchestrator_task": task,
            "round_num": self.current_round,
        }

    def read_round_output(self) -> Dict[str, Any]:
        """
        读取本轮 Orchestrator Worker 的输出.

        从 spec/round_result.json 读取.

        Returns:
            dict with action and relevant fields.
            On error: {action: 'error', message: '...'}
        """
        if not self.base_path:
            return {"action": "error", "message": "Session not initialized"}

        result_path = os.path.join(self.base_path, "spec", "round_result.json")
        if not os.path.exists(result_path):
            return {"action": "error", "message": "round_result.json not found"}

        try:
            with open(result_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            return {"action": "error", "message": f"Failed to read round_result.json: {e}"}

        # Update internal state based on action
        action = data.get("action", "error")
        try:
            round_action = RoundAction(action)
        except ValueError:
            round_action = RoundAction.ERROR

        if round_action == RoundAction.DONE:
            self.state = DialogState.COMPLETED
        elif round_action == RoundAction.SAFETY_STOP:
            self.state = DialogState.KILLED
        elif round_action == RoundAction.ERROR:
            self.state = DialogState.FAILED
        elif round_action == RoundAction.SUMMARY:
            self.state = DialogState.CONFIRMING
        elif round_action == RoundAction.QUESTIONS:
            self.state = DialogState.ASKING

        return data

    def build_confirmation_task(self, user_confirmation: Dict[str, Any]) -> str:
        """
        构建确认阶段的 Orchestrator Worker task.

        Args:
            user_confirmation: {action: 'confirm'|'revise', revisions: [...]}

        Returns:
            Orchestrator Worker task prompt string

        Raises:
            RuntimeError: session 未初始化
        """
        if not self.session_id or not self.base_path:
            raise RuntimeError("Session not initialized. Call init_session() first.")

        # Write confirmation
        confirm_path = os.path.join(
            self.base_path, "spec", "user_confirmation.md"
        )
        with open(confirm_path, "w", encoding="utf-8") as f:
            json.dump(user_confirmation, f, ensure_ascii=False, indent=2)

        self.state = DialogState.REVISING if user_confirmation.get("action") == "revise" else DialogState.CONFIRMING

        return self._build_orchestrator_task(
            round_num=self.current_round + 1, phase="confirmation"
        )

    def get_status(self) -> Dict[str, Any]:
        """
        获取当前 session 状态.

        Returns:
            dict with: session_id, initialized, current_round, last_action, mode, scenario
        """
        last_action: Optional[str] = None
        if self.base_path:
            result_path = os.path.join(self.base_path, "spec", "round_result.json")
            if os.path.exists(result_path):
                try:
                    with open(result_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    last_action = data.get("action")
                except (json.JSONDecodeError, OSError):
                    pass

        return {
            "session_id": self.session_id,
            "initialized": self.session_id is not None,
            "current_round": self.current_round,
            "last_action": last_action,
            "mode": self.mode,
            "scenario": self.scenario,
            "state": self.state.value,
        }

    def is_done(self) -> bool:
        """
        检查 Spec Pro 是否已完成.

        Returns:
            True if action is 'done', 'error', or 'safety_stop'
        """
        if not self.base_path:
            return False
        result_path = os.path.join(self.base_path, "spec", "round_result.json")
        if not os.path.exists(result_path):
            return False
        try:
            with open(result_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("action") in ("done", "error", "safety_stop")
        except (json.JSONDecodeError, OSError):
            return False

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _generate_session_id(self) -> str:
        """Generate session ID: {prefix}_spec_{hash8}"""
        import hashlib

        ts = str(time.time()).encode()
        hash8 = hashlib.md5(ts).hexdigest()[:8]
        prefix = self.session_prefix[:20]  # cap prefix length
        sid = f"{prefix}_spec_{hash8}"
        return sid[:50]  # ensure <= 50 chars

    def _build_orchestrator_task(self, round_num: int, phase: str) -> str:
        """
        构建 Orchestrator Worker task prompt.

        从 domains/spec_pro/prompts/orchestrator.md 读取基础 Prompt,
        注入上下文变量(session_id, base_path, round, phase, etc.).
        """
        from core.prompt_registry import read_prompt

        orchestrator_prompt = read_prompt("spec_pro/orchestrator")

        threshold = self._config["threshold"]
        max_rounds = self._config["max_rounds"]

        task = f"""{orchestrator_prompt}

---
## 当前任务上下文

- Session: {self.session_id}
- Blackboard: {self.base_path}
- 场景: {self.scenario}
- 模式: {self.mode}
- 当前轮次: {round_num}
- 阶段: {phase}
- 质量阈值: {threshold}
- 最大轮数: {max_rounds}

## 本轮执行指令

"""
        if phase == "init":
            task += self._init_phase_instructions()
        elif phase == "collecting":
            task += self._collecting_phase_instructions(round_num)
        elif phase == "confirmation":
            task += self._confirmation_phase_instructions()
        else:
            task += f"# Unknown phase: {phase}\n"

        # Replace {Blackboard} placeholder with actual base_path
        task = task.replace("{Blackboard}", self.base_path)

        return task

    def _init_phase_instructions(self) -> str:
        """Round 1: Parse -> Assess -> Question"""
        return """# Phase: init (Round 1)

执行以下步骤,严格按顺序:

## Step 1: spawn ParseWorker
使用 sessions_spawn 创建 ParseWorker:
- runtime: "subagent"
- mode: "run"
- task: 读取 domains/spec_pro/prompts/parse.md 的内容作为 task,并注入以下上下文:
  - 读取文件: {Blackboard}/spec/input.md
  - 写入文件: {Blackboard}/stages/round_01_parse.json
  - 写入文件: {Blackboard}/spec/living_spec.json
- timeoutSeconds: 180
- cleanup: "delete"

等待 ParseWorker 完成.

## Step 1.5: Worker 存在性检查
执行以下命令检查 ParseWorker 输出:
```
test -f {Blackboard}/stages/round_01_parse.json && echo EXISTS || echo MISSING
```
如果输出 MISSING,执行:
```
python3 .deepflow/domains/spec_pro/worker_fallback.py parse {Blackboard}/stages/round_01_parse.json
```

## Step 2: spawn AssessWorker
- task: 读取 domains/spec_pro/prompts/assess.md 的内容,注入上下文:
  - 读取: {Blackboard}/spec/living_spec.json
  - 写入: {Blackboard}/spec/quality_report.json
- timeoutSeconds: 180

等待完成.

## Step 2.5: Worker 存在性检查
如果 spec/quality_report.json 不存在:
```
python3 .deepflow/domains/spec_pro/worker_fallback.py assess {Blackboard}/spec/quality_report.json
```

## Step 3: spawn QuestionWorker
- task: 读取 domains/spec_pro/prompts/guide.md 的内容,注入上下文:
  - 读取: {Blackboard}/spec/living_spec.json
  - 读取: {Blackboard}/spec/quality_report.json
  - 写入: {Blackboard}/stages/round_01_questions.json
- timeoutSeconds: 180

等待完成.

## Step 3.5: Worker 存在性检查
如果 stages/round_01_questions.json 不存在:
```
python3 .deepflow/domains/spec_pro/worker_fallback.py question {Blackboard}/stages/round_01_questions.json
```

## Step 4: 汇总
读取以下文件:
- {Blackboard}/stages/round_01_questions.json
- {Blackboard}/spec/quality_report.json

写入 {Blackboard}/spec/round_result.json:
```json
{
  "action": "questions",
  "round": 1,
  "questions": [从 questions.json 读取的 questions 数组],
  "quality": {"overall_score": [quality_report.json 的 overall_score], "level": [quality_report.json 的 level]},
  "inferred_items": [从 living_spec.json 的 inferred 层读取 status=pending 的项]
}
```

## Step 5: 更新 quality_trajectory.json
执行以下命令追加轨迹记录:
```
python3 .deepflow/domains/spec_pro/worker_fallback.py append_trajectory {Blackboard} 1 [quality_report.json 的 overall_score] [quality_report.json 的 level] [questions.json 中 questions 数组长度]
```

轨迹条目格式:
```json
{"round": 1, "overall_score": 数字, "level": "S/A/B/C", "dimension_scores": {"objective": 数字, "users": 数字, "capabilities": 数字, "quality_attributes": 数字, "constraints": 数字, "integration": 数字, "risks": 数字}, "delta": 0, "questions_asked": 数字, "inferences_validated": 0}
```

## Step 6: 更新 conversation_log.json
追加第一条对话日志,格式:
```json
{"round": 1, "timestamp": "ISO8601", "phase": "init", "questions": [questions.json 中的 questions 数组], "user_response": "[用户初始输入,截断500字]", "parsed_updates_summary": "ParseWorker 解析摘要", "quality_before": 0, "quality_after": [quality_report.json overall_score], "quality_delta": [overall_score], "inferences_created": [living_spec.json inferred 层数量], "inferences_confirmed": 0, "inferences_rejected": 0}
```
"""

    def _collecting_phase_instructions(self, round_num: int) -> str:
        """Round N: Response -> Assess -> (Question | Harness -> Structure)"""
        prev_round = round_num - 1
        nn = f"{round_num:02d}"
        pp = f"{prev_round:02d}"
        threshold = self._config["threshold"]

        return f"""# Phase: collecting (Round {round_num})

用户回答已写入: {{Blackboard}}/spec/user_response_round_{prev_round}.md
上轮问题在: {{Blackboard}}/stages/round_{pp}_questions.json

## Step 1: spawn ResponseWorker
- task: 读取 domains/spec_pro/prompts/parse_response.md,注入上下文:
  - 读取: {{Blackboard}}/spec/living_spec.json
  - 读取: {{Blackboard}}/spec/user_response_round_{prev_round}.md
  - 读取: {{Blackboard}}/stages/round_{pp}_questions.json
  - 写入: {{Blackboard}}/stages/round_{nn}_response.json
- timeoutSeconds: 180

## Step 1.5: Worker 存在性检查
如果 stages/round_{nn}_response.json 不存在:
```
python3 .deepflow/domains/spec_pro/worker_fallback.py response {{Blackboard}}/stages/round_{nn}_response.json
```

## Step 2: 合并 living_spec.json(代码化,不靠 LLM)
执行以下命令合并:
```
python3 .deepflow/domains/spec_pro/merge_spec.py {{Blackboard}}/stages/round_{nn}_response.json {{Blackboard}}/spec/living_spec.json
```
该脚本会按 writer_protocol 规则合并:
- confirmed 层: 追加新项,不删除已有项
- inferred 层: status=confirmed->移入confirmed层, status=rejected->标记rejected, 新推断->追加
- guardrails: 追加新项
- 矛盾处理: 保留两者并标注 contradiction

## Step 3: spawn AssessWorker
- task: 读取 domains/spec_pro/prompts/assess.md,注入上下文:
  - 读取: {{Blackboard}}/spec/living_spec.json
  - 写入: {{Blackboard}}/spec/quality_report.json
- timeoutSeconds: 180

## Step 3.5: Worker 存在性检查
如果 spec/quality_report.json 不存在:
```
python3 .deepflow/domains/spec_pro/worker_fallback.py assess {{Blackboard}}/spec/quality_report.json
```

## Step 4: Process Guard 检查
执行以下命令检查质量轨迹:
```
python3 .deepflow/domains/spec_pro/process_guard.py {{Blackboard}} {round_num}
```
该脚本读取 quality_trajectory.json,检查 progress_rate / inference_integrity / conversation_balance.
如果发现异常,输出调整指令文本;否则输出空.

## Step 5: 更新 quality_trajectory.json
执行以下命令追加轨迹记录:
```
python3 .deepflow/domains/spec_pro/worker_fallback.py append_trajectory {{Blackboard}} {round_num} [quality_report.json overall_score] [quality_report.json level] [上轮 questions 数量] [推断确认数]
```
轨迹条目格式:
```json
{{"round": {round_num}, "overall_score": 数字, "level": "S/A/B/C", "dimension_scores": {{"objective": 数字, "users": 数字, "capabilities": 数字, "quality_attributes": 数字, "constraints": 数字, "integration": 数字, "risks": 数字}}, "delta": [与上一轮分数差], "questions_asked": 数字, "inferences_validated": 数字}}
```

## Step 6: 检查停止条件
读取 quality_report.json 的 overall_score.

### 如果 overall_score >= {threshold}:
spawn HarnessWorker:
- task: 读取 domains/spec_pro/prompts/harness.md,注入上下文:
  - 读取: {{Blackboard}}/spec/living_spec.json
  - 读取: {{Blackboard}}/spec/quality_report.json
  - 读取: {{Blackboard}}/spec/conversation_log.json
  - 读取: {{Blackboard}}/spec/quality_trajectory.json
  - 写入: {{Blackboard}}/spec/harness_report.json
- timeoutSeconds: 240

等待 HarnessWorker 完成.

## Step 6.5: HarnessWorker 存在性检查
如果 spec/harness_report.json 不存在:
```
python3 .deepflow/domains/spec_pro/worker_fallback.py harness {{Blackboard}}/spec/harness_report.json
```

读取 harness_report.json 的 final_decision:
- PASS 或 WARN -> spawn StructureWorker:
  - task: 读取 domains/spec_pro/prompts/structure.md,注入上下文:
    - 读取: {{Blackboard}}/spec/living_spec.json
    - 读取: {{Blackboard}}/spec/quality_report.json
    - 写入: {{Blackboard}}/spec/round_result.json
    - action: "summary" (WARN时在round_result中添加 "harness_warning": true)
  - timeoutSeconds: 180
- SOFT_BLOCK 或 HARD_BLOCK -> spawn QuestionWorker:
  - task: 读取 domains/spec_pro/prompts/guide.md,注入上下文:
    - 读取: {{Blackboard}}/spec/living_spec.json
    - 读取: {{Blackboard}}/spec/quality_report.json
    - 写入: {{Blackboard}}/stages/round_{nn}_questions.json
  - timeoutSeconds: 180
  - 汇总到 round_result.json: action: "questions"

### 如果 overall_score < {threshold}:
spawn QuestionWorker:
- task: 读取 domains/spec_pro/prompts/guide.md,注入上下文:
  - 读取: {{Blackboard}}/spec/living_spec.json
  - 读取: {{Blackboard}}/spec/quality_report.json
  - 写入: {{Blackboard}}/stages/round_{nn}_questions.json
  - Process Guard 调整指令: [Step 4 的输出]
- timeoutSeconds: 180

汇总到 round_result.json:
```json
{{
  "action": "questions",
  "round": {round_num},
  "questions": [从 questions.json 读取],
  "quality": {{"overall_score": [quality_report overall_score], "level": [quality_report level]}},
  "inferred_items": [从 living_spec.json inferred 层读取 pending 项]
}}
```

## Step 7: 更新 conversation_log.json
追加本轮对话日志,格式:
```json
{{"round": {round_num}, "timestamp": "ISO8601", "phase": "collecting", "questions": [上轮 questions], "user_response": "[用户回答,截断500字]", "parsed_updates_summary": "[ResponseWorker 解析摘要,1-2句]", "quality_before": [上轮分数], "quality_after": [本轮分数], "quality_delta": [分数差], "inferences_created": [新增推断数], "inferences_confirmed": [确认数], "inferences_rejected": [拒绝数]}}
```
"""

    def _confirmation_phase_instructions(self) -> str:
        """Confirmation: confirm -> Structure / revise -> merge -> Assess -> Question"""
        return """# Phase: confirmation

用户确认/修正已写入: {Blackboard}/spec/user_confirmation.md

读取 user_confirmation.md 中的 action:

## 如果 action = "confirm":
spawn StructureWorker:
- task: 读取 domains/spec_pro/prompts/structure.md,注入上下文:
  - 读取: {Blackboard}/spec/living_spec.json
  - 读取: {Blackboard}/spec/quality_report.json
  - 读取: {Blackboard}/spec/harness_report.json(如果存在)
  - 写入: {Blackboard}/spec/round_result.json
  - action: "done"
  - 在 round_result 中包含: action="done", summary_text, quality, living_spec(完整内容), harness_report(如有), route_recommendation, solution_pro_hints, inferred_pending
- timeoutSeconds: 180

## 如果 action = "revise":
1. 合并修正内容到 living_spec.json:
   执行命令:
   ```
   python3 .deepflow/domains/spec_pro/merge_spec.py --revisions {Blackboard}/spec/user_confirmation.md {Blackboard}/spec/living_spec.json
   ```
   该脚本读取 user_confirmation.md 中的 revisions 数组,逐条更新到 living_spec.json 的 confirmed 层对应字段.

2. spawn AssessWorker(重新评估):
   - task: 读取 domains/spec_pro/prompts/assess.md,注入上下文:
     - 读取: {Blackboard}/spec/living_spec.json
     - 写入: {Blackboard}/spec/quality_report.json
   - timeoutSeconds: 180

3. AssessWorker 存在性检查:
   如果 spec/quality_report.json 不存在:
   ```
   python3 .deepflow/domains/spec_pro/worker_fallback.py assess {Blackboard}/spec/quality_report.json
   ```

4. 读取 quality_report.json 的 overall_score:
   - 达标(≥ threshold)-> spawn HarnessWorker -> 读 harness_report.json -> spawn StructureWorker(action="summary")
   - 未达标 -> spawn QuestionWorker(action="questions")

更新 conversation_log.json,追加一条 confirmation 阶段记录.
"""

    def _write_execution_log(self, event: str, data: Dict[str, Any]) -> None:
        """Append event to execution_log.json. Non-critical: failures are silent."""
        if not self.base_path:
            return
        log_path = os.path.join(self.base_path, "execution_log.json")
        log: Dict[str, Any] = {"events": []}
        if os.path.exists(log_path):
            try:
                with open(log_path, "r", encoding="utf-8") as f:
                    log = json.load(f)
            except (json.JSONDecodeError, OSError):
                pass
        log["events"].append({
            "timestamp": datetime.now().isoformat(),
            "event": event,
            "data": data,
        })
        try:
            with open(log_path, "w", encoding="utf-8") as f:
                json.dump(log, f, ensure_ascii=False, indent=2)
        except OSError:
            pass
