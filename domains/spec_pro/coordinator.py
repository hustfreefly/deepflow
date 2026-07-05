"""
Spec Pro Coordinator
====================

契约: cage/active/spec_pro_v2.0.yaml (L1, L2)
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

去路径化: 所有文件 I/O 通过 BlackboardManager API，不再直接拼接路径。
"""

import sys as _sys; _p=__import__('pathlib').Path(__file__).resolve(); _r=next((d for d in _p.parents if (d/'core'/'blackboard').is_dir()),None); _sys.path.insert(0,str(_r)) if _r and str(_r) not in _sys.path else None  # 契约笼子: 自动发现 .deepflow 根目录
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from core.config.path_config import PathConfig
from domains.spec_pro.blackboard import BlackboardManager
from domains.spec_pro.schemas import (
    EMPTY_CONVERSATION_LOG,
    EMPTY_QUALITY_TRAJECTORY,
)
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
        architecture_version: str = "v3_flat",
    ) -> None:
        """
        初始化 Coordinator.

        Args:
            scenario: 场景类型 (genesis/supplement/refine/pivot)
            mode: 对话深度 (quick/standard/deep)
            session_prefix: session ID 前缀(可选)
            architecture_version: 架构版本 ('v2_nested' 或 'v3_flat')
                - v2_nested: Orchestrator Worker 串行调度 (旧架构)
                - v3_flat: 主 Agent 直接评分+提问 (Phase 3 扁平架构)
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
        self.architecture_version = architecture_version
        self.session_id: Optional[str] = None
        self._bb: Optional[BlackboardManager] = None
        self.current_round: int = 0
        self.state: DialogState = DialogState.START
        self._config = MODE_CONFIG[mode]

    # ------------------------------------------------------------------
    # BlackboardManager 属性 # ------------------------------------------------------------------

    @property
    def bb(self) -> BlackboardManager:
        """获取 BlackboardManager 实例（懒初始化）。"""
        if self._bb is None:
            if self.session_id is None:
                raise RuntimeError("Session not initialized. Call init_session() first.")
            self._bb = BlackboardManager(self.session_id)
        return self._bb

    @property
    def base_path(self) -> Optional[str]:
        """
        ⚠️ DEPRECATED: 获取 session 目录路径。

        请使用 self.bb.write/read 代替直接路径拼接。
        保留此属性仅为向后兼容，将在 v7 中移除。
        """
        if self._bb is not None:
            return str(self._bb.session_dir)
        return None

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
            ValueError: 输入过短(<5字符)或过长(>5000字符)
            OSError: 目录创建失败
        """
        if len(user_input) < 5:
            raise ValueError(
                f"Input too short ({len(user_input)} chars). Minimum 5 characters."
            )
        if len(user_input) > 5000:
            raise ValueError(
                f"Input too long ({len(user_input)} chars). Maximum 5000 characters."
            )

        # Record pipeline start time for watcher timeout detection
        run_start_at = datetime.now(timezone.utc).isoformat()

        # Generate session ID
        self.session_id = self._generate_session_id()

        # Initialize BlackboardManager self._bb = BlackboardManager(self.session_id)
        self._bb.init_session()

        # Write user input
        self._bb.write("input.md", user_input)

        # Initialize execution log
        self._write_execution_log("init", {
            "user_input_length": len(user_input),
            "scenario": self.scenario,
            "mode": self.mode,
        })

        # Initialize quality trajectory (schemas.py 定义的格式)
        self._bb.write("spec/quality_trajectory.json", json.dumps(EMPTY_QUALITY_TRAJECTORY))

        # Initialize conversation log (schemas.py 定义的格式)
        self._bb.write("spec/conversation_log.json", json.dumps(EMPTY_CONVERSATION_LOG))

        # Build first round task (v3 flat or v2 nested)
        self.current_round = 1
        self.state = DialogState.PARSING
        if self.architecture_version == "v3_flat":
            task = self._build_v3_round_task(round_num=1, phase="init")
        else:
            task = self._build_orchestrator_task(
                round_num=1, phase="init"
            )

        # Watcher integration: provide all info needed for main Agent to create cron
        deepflow_root = str(Path(__file__).resolve().parent.parent.parent)
        watcher_config_rel = "domains/spec_pro/config/watcher_config.json"
        watcher_config_abs = os.path.join(deepflow_root, watcher_config_rel)

        return {
            "session_id": self.session_id,
            "base_path": str(self._bb.session_dir),
            "orchestrator_task": task,
            "v3_parse_worker_prompt": self._build_v3_parse_worker_prompt(1) if self.architecture_version == "v3_flat" else None,
            "v3_main_eval_prompt": self._build_v3_main_eval_prompt(1) if self.architecture_version == "v3_flat" else None,
            # --- Watcher fields (new, backward-compatible) ---
            "run_start_at": run_start_at,
            "watcher_config": watcher_config_rel,
            "watcher_config_abs": watcher_config_abs,
            "deepflow_root": deepflow_root,
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
        if not self.session_id or self._bb is None:
            raise RuntimeError("Session not initialized. Call init_session() first.")

        # F-safety: 阻止 safety_stop 后继续调用
        if self.state == DialogState.KILLED:
            return {
                "action": "safety_stop",
                "reason": "already_killed",
                "message": "Session already killed by safety valve. Cannot continue.",
            }

        self.current_round += 1

        # Safety Valve: max_rounds check
        max_rounds = self._config["max_rounds"]
        if self.current_round > max_rounds:
            # F6: 落状态 + 写 round_result
            self.state = DialogState.KILLED
            result_data = {
                "action": "safety_stop",
                "reason": "max_rounds",
                "message": (
                    f"Reached maximum rounds ({max_rounds}) for mode '{self.mode}'. "
                    "Spec Pro is stopping."
                ),
            }
            # 写 round_result.json 让 is_done() 能检测到
            self._bb.write("spec/round_result.json", result_data)
            return result_data

        # Write user response
        self._bb.write(f"spec/user_response_round_{self.current_round}.md", user_response)

        # Build task (v3 flat or v2 nested)
        if self.architecture_version == "v3_flat":
            task = self._build_v3_round_task(
                round_num=self.current_round, phase="collecting"
            )
            v3_parse = self._build_v3_parse_worker_prompt(self.current_round)
            v3_eval = self._build_v3_main_eval_prompt(self.current_round)
        else:
            task = self._build_orchestrator_task(
                round_num=self.current_round, phase="collecting"
            )
            v3_parse = None
            v3_eval = None

        self._write_execution_log("round_start", {
            "round": self.current_round,
            "response_length": len(user_response),
            "architecture_version": self.architecture_version,
        })

        return {
            "orchestrator_task": task,
            "round_num": self.current_round,
            "v3_parse_worker_prompt": v3_parse,
            "v3_main_eval_prompt": v3_eval,
        }

    def read_round_output(self) -> Dict[str, Any]:
        """
        读取本轮 Orchestrator Worker 的输出.

        从 spec/round_result.json 读取.

        Returns:
            dict with action and relevant fields.
            On error: {action: 'error', message: '...'}
        """
        if self._bb is None:
            return {"action": "error", "message": "Session not initialized"}

        data = self._bb.read_json("spec/round_result.json")
        if data is None:
            return {"action": "error", "message": "round_result.json not found"}

        # 契约笼子：Pydantic 门控
        from domains.spec_pro.contracts.gate import gate_round_result
        validated, errors = gate_round_result(data)
        if errors:
            return {"action": "error", "message": f"RoundResult 格式错误: {errors}"}

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
        elif round_action == RoundAction.PROPOSAL:
            self.state = DialogState.CONFIRMING  # F4: proposal 也等待用户确认
        elif round_action == RoundAction.QUESTIONS:
            self.state = DialogState.ASKING

        return data

    def build_confirmation_task(self, user_confirmation: Dict[str, Any]) -> str:
        """
        构建确认阶段的 task.

        Args:
            user_confirmation: {action: 'confirm'|'revise', revisions: [...]}

        Returns:
            Worker task prompt string (v3_flat 返回主Agent执行指令，v2返回Orchestrator task)

        Raises:
            RuntimeError: session 未初始化
        """
        if not self.session_id or self._bb is None:
            raise RuntimeError("Session not initialized. Call init_session() first.")

        # Write confirmation
        self._bb.write("spec/user_confirmation.json", user_confirmation)

        self.state = DialogState.REVISING if user_confirmation.get("action") == "revise" else DialogState.CONFIRMING

        # v3 flat: 主 Agent 直接执行，不 spawn Worker
        if self.architecture_version == "v3_flat":
            return self._build_v3_confirmation_task(round_num=self.current_round + 1)

        return self._build_orchestrator_task(
            round_num=self.current_round + 1, phase="confirmation"
        )

    def build_annotation_task(self) -> str:
        """
        构建 RequirementStructuringWorker task（阶段2：LLM标注增强）.

        在 Spec Pro 收尾阶段调用，对 living_spec.confirmed 中的需求进行语义标注。
        标注结果写入 living_spec.confirmed.requirement_annotations。

        Returns:
            RequirementStructuringWorker task prompt string

        Raises:
            RuntimeError: session 未初始化
        """
        if not self.session_id or self._bb is None:
            raise RuntimeError("Session not initialized. Call init_session() first.")

        session_dir = self._bb.session_dir

        return f"""你是 Requirement Structuring Worker。

你的任务是对 living_spec.confirmed 中的需求进行语义标注，为下游 Solution Pro 提供结构化元数据。

## 输入
使用 BlackboardManager 读取: spec/living_spec.json

## 执行步骤
1. 使用 read_stage 或 read_json 读取 living_spec.json 的 confirmed 层
2. 调用 annotate_requirements(confirmed) 进行 LLM 标注
3. 如果标注成功，将结果写入 living_spec.confirmed.requirement_annotations
4. 如果标注失败（JSON解析错误、Schema验证失败、覆盖率<80%），不写入 requirement_annotations，保持 living_spec 不变

## 输出
更新 spec/living_spec.json，在 confirmed 层新增 requirement_annotations 字段（如果标注成功）

## 标注格式
使用 JSON 格式输出，符合以下 Schema：
```json
{{
  "type": "array",
  "items": {{
    "type": "object",
    "required": ["original_text", "category", "priority"],
    "properties": {{
      "original_text": {{"type": "string"}},
      "category": {{
        "enum": ["core_objective", "capability", "prohibition", "quality_attribute", 
                 "constraint", "integration", "pain_point", "success_metric", 
                 "user", "scenario", "risk", "assumption"]
      }},
      "priority": {{"enum": ["P0", "P1", "P2"]}},
      "dependencies": {{"type": "array", "items": {{"type": "string"}}}},
      "potential_conflicts": {{"type": "array", "items": {{"type": "string"}}}},
      "context_note": {{"type": "string"}}
    }}
  }}
}}
```

## 失败处理
如果标注失败，不写入 requirement_annotations，下游 frozen_spec.py 会自动 fallback 到纯脚本方案。

## 超时
180秒
"""

    def apply_annotations(self, living_spec: Dict[str, Any], annotations: list) -> None:
        """
        将 LLM 标注结果写入 living_spec.confirmed.requirement_annotations.

        Args:
            living_spec: living_spec.json 内容
            annotations: LLM 标注结果列表

        Raises:
            RuntimeError: session 未初始化
        """
        if self._bb is None:
            raise RuntimeError("Session not initialized. Call init_session() first.")

        # 写入 requirement_annotations
        living_spec.setdefault("confirmed", {})["requirement_annotations"] = annotations

        # 保存回文件
        self._bb.write("spec/living_spec.json", living_spec)

        self._write_execution_log("annotation_applied", {
            "annotation_count": len(annotations)
        })

    def get_status(self) -> Dict[str, Any]:
        """
        获取当前 session 状态.

        Returns:
            dict with: session_id, initialized, current_round, last_action, mode, scenario
        """
        last_action: Optional[str] = None
        if self._bb is not None:
            data = self._bb.read_json("spec/round_result.json")
            if data is not None:
                last_action = data.get("action")

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
            True if action is 'done', 'error', 'safety_stop', 'proposal', or 'summary'
        """
        if self._bb is None:
            return False
        data = self._bb.read_json("spec/round_result.json")
        if data is None:
            return False
        return data.get("action") in ("done", "error", "safety_stop", "proposal", "summary")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _generate_session_id(self) -> str:
        """Generate session ID: {prefix}_spec_{uuid16}"""
        import uuid

        uid = uuid.uuid4().hex[:16]
        prefix = self.session_prefix[:20]  # cap prefix length
        sid = f"{prefix}_spec_{uid}"
        return sid[:50]  # ensure <= 50 chars

    def _compute_dynamic_threshold(self) -> int:
        """
        动态计算质量阈值 (D6: 阈值僵硬修复).

        基础阈值来自 MODE_CONFIG,根据轨迹停滞情况动态下调:
        - 连续 2 轮 delta < 3 分: 降 10 分
        - 连续 3 轮 delta < 3 分: 降 15 分
        - 最低不低于 50 分

        Returns:
            调整后的阈值(整数)
        """
        base = self._config["threshold"]
        if self._bb is None:
            return base

        raw_trajectory = self._bb.read_json("spec/quality_trajectory.json", default={})
        # quality_trajectory.json is a dict with {"scores": [], "trajectory": []}
        if isinstance(raw_trajectory, dict):
            trajectory = raw_trajectory.get("trajectory", [])
        elif isinstance(raw_trajectory, list):
            trajectory = raw_trajectory
        else:
            trajectory = []
        trajectory = trajectory or []

        if len(trajectory) < 2:
            return base

        # Count consecutive stagnation rounds (delta < 3)
        stagnation_count = 0
        for point in reversed(trajectory):
            if abs(point.get("delta", 0)) < 3:
                stagnation_count += 1
            else:
                break

        adjustment = 0
        if stagnation_count >= 3:
            adjustment = 15
        elif stagnation_count >= 2:
            adjustment = 10

        return max(base - adjustment, 50)

    def _build_v3_confirmation_task(self, round_num: int) -> str:
        """
        Phase 3 扁平架构：构建确认阶段主 Agent 执行指令。

        v3 下不 spawn StructureWorker，主 Agent 直接读写文件。
        """
        threshold = self._compute_dynamic_threshold()
        session_dir = self._bb.session_dir if self._bb else ""

        return f"""# Spec Pro v3 确认阶段 — 主 Agent 执行指南

你是 Spec Pro 主 Agent。用户在确认阶段做出了决定。

## 当前任务上下文

- Session: {self.session_id}
- Blackboard: {session_dir}
- 当前轮次: {round_num}
- 质量阈值: {threshold}

## 执行步骤

使用 BlackboardManager API 读取 spec/user_confirmation.json 中的 action：

### 如果 action = "confirm"：

1. 使用 read_json 读取 spec/living_spec.json
2. 使用 read_json 读取 spec/quality_report.json（如有）
3. 使用 read_json 读取 spec/harness_report.json（如有）
4. **提取 Semantic Anchors（契约笼子强制步骤）**：
   - 从 living_spec.confirmed 的 narrative/description/requirements 中，提取所有**不可抽象化的具体技术引用**
   - 提取维度：platform_api（具体 API/工具名）、architecture_principle（不可妥协的架构原则）、external_system（必须集成的外部系统）、technical_constraint（硬性技术约束）
   - 判断标准：如果被泛化/抽象化，会导致下游实施者不知道该用什么具体技术 → 这就是 anchor
   - 反例："设计优雅"、"代码质量高" 不是 anchor（太抽象）
   - 将提取结果写入 living_spec.semantic_anchors，格式：
   ```json
   [
     {{
       "name": "sessions_spawn",
       "category": "platform_api",
       "constraint": "子 Agent 生成必须使用 sessions_spawn",
       "confidence": 0.95,
       "applicable_to": ["all"]
     }}
   ]
   ```
   - 如果没有不可抽象化的引用，写入空数组 []
   - 使用 write 更新 spec/living_spec.json（加入 semantic_anchors 字段）
5. 使用 write 工具写入 spec/round_result.json：
```json
{{
  "action": "done",
  "round": {round_num},
  "summary_text": "需求梳理完成。核心目标：[从 living_spec 提取]",
  "living_spec": [完整 living_spec 内容],
  "quality": {{
    "overall_score": [quality_report 的 overall_score],
    "level": [quality_report 的 level]
  }}
}}
```

### 如果 action = "revise"：

1. 合并修正内容到 living_spec.json：
```
python3 .deepflow/domains/spec_pro/merge_spec.py --revisions spec/user_confirmation.json spec/living_spec.json
```
2. 对更新后的 living_spec 进行 7 维度评分
3. 如果 overall_score >= {threshold}：
   - 写 round_result.json (action="done")
4. 如果 overall_score < {threshold}：
   - 生成 2-4 个补充问题
   - 写 round_result.json (action="questions")
"""

    def _build_orchestrator_task(self, round_num: int, phase: str) -> str:
        """
        构建 Orchestrator Worker task prompt.

        从 domains/spec_pro/prompts/orchestrator.md 读取基础 Prompt,
        注入上下文变量(session_id, base_path, round, phase, etc.).
        
        D6 修复: 使用动态阈值而非固定值.
        """
        from core.prompt_registry import read_prompt

        orchestrator_prompt = read_prompt("spec_pro/orchestrator")

        # D6: 使用动态阈值
        threshold = self._compute_dynamic_threshold()
        base_threshold = self._config["threshold"]
        max_rounds = self._config["max_rounds"]
        
        # 如果动态阈值与基础阈值不同,添加说明
        threshold_note = ""
        if threshold != base_threshold:
            threshold_note = f"\n**注意**: 质量阈值已从 {base_threshold} 动态调整为 {threshold} (检测到停滞趋势)\n"

        session_dir = self._bb.session_dir if self._bb else ""

        task = f"""{orchestrator_prompt}

---
## 当前任务上下文

- Session: {self.session_id}
- Blackboard: {session_dir}
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

        # Replace {Blackboard} placeholder with actual session dir
        task = task.replace("{Blackboard}", session_dir)

        return task

    def _build_v3_round_task(self, round_num: int, phase: str) -> str:
        """
        Phase 3 扁平架构：生成主 Agent 直接执行的流程指令。
        
        与 v2 的 _build_orchestrator_task() 不同，此方法不包含
        多 Worker spawn 逻辑，只生成主 Agent 评分+提问的指导。
        """
        threshold = self._compute_dynamic_threshold()
        base_threshold = self._config["threshold"]
        max_rounds = self._config["max_rounds"]
        
        threshold_note = ""
        if threshold != base_threshold:
            threshold_note = f"\n**注意**: 质量阈值已从 {base_threshold} 动态调整为 {threshold}\n"

        session_dir = self._bb.session_dir if self._bb else ""

        task = f"""# Spec Pro v3 扁平架构 — 主 Agent 执行指南

你是 Spec Pro 主 Agent。本次使用 v3 扁平架构：你直接做评分和提问。

## 流程概述

1. ParseWorker（子 Agent）已完成 → 使用 read_stage 读取 round_{round_num:02d}_parse
2. 你（主 Agent）直接做 7 维度质量评估
3. 你（主 Agent）直接生成 3-5 个引导问题
4. 写 round_result.json
5. 展示给用户

## 关键规则

### 🔴 需求 vs 设计边界

**允许问（需求）**：
- 用户期望什么结果/行为/质量？
- 用户的场景是什么？

**禁止问（设计）**：
- ❌ 系统如何实现？（架构、算法、技术选型）
- ❌ 系统内部如何组织？（Agent 划分、数据流）
- ❌ 用技术术语问业务问题（服务器、域名、MVP、API 网关等）

### 🔴 意图判断式评分

- 用户说"参考业界最优实践" → 对应维度给 **70 分**（有效需求声明）
- 用户说"兼职尽量少投入" → constraints 给 **60 分**
- 用户说"合规不用管" → deliberately_omitted → **50 分**，不追问
- 用户说"你们来决定" → 委托设计 → 不扣分

---
## 当前任务上下文

- Session: {self.session_id}
- Blackboard: {session_dir}
- 场景: {self.scenario}
- 模式: {self.mode}
- 当前轮次: {round_num}
- 阶段: {phase}
- 质量阈值: {threshold}
- 最大轮数: {max_rounds}
{threshold_note}
"""
        if phase == "init":
            task += """\n## 你的任务

1. 使用 read_json 读取 living_spec.json（已由 ParseWorker 创建）
2. 对 living_spec 进行 7 维度评分（0-100）：
   - objective (20%): 目标清晰度、痛点、成功指标
   - users (15%): 用户角色、场景
   - capabilities (15%): always_do/should_do/never_do
   - quality_attributes (15%): 量化指标
   - constraints (15%): platform/tech_stack/data_source
   - integration (10%): 外部系统、接口
   - risks (10%): 风险、假设（deliberately_omitted 维度给 50 分）
3. 生成 3-5 个引导问题，聚焦最低分维度
   - 每个问题标注 boundary_check: demand 或 design
   - 禁止出现技术词汇
   - 禁止问"如何实现"
4. 写 round_result.json（格式见下文）

### round_result.json 格式

```json
{
  "action": "questions",
  "round": 1,
  "questions": [...],
  "quality": {
    "overall_score": 数字,
    "level": "S/A/B/C",
    "dimension_scores": {每个维度的分数和delta},
    "top_improvements": [],
    "top_missing": [缺失项]
  },
  "inferred_items": [living_spec.json inferred 层 pending 项]
}
```
"""
        elif phase == "collecting":
            prev = round_num - 1
            task += f"""\n## 你的任务

1. 使用 read_json 读取 living_spec.json（已由 merge_spec.py 合并更新）
2. 对 living_spec 进行 7 维度评分（0-100）
3. 生成 3-5 个引导问题，聚焦最低分维度
   - 已问过且已回答的问题不再重复
   - deliberately_omitted 维度不提问
   - 每个问题标注 boundary_check
4. 写 round_result.json

### round_result.json 格式

```json
{{
  "action": "questions",
  "round": {round_num},
  "questions": [...],
  "quality": {{
    "overall_score": 数字,
    "level": "S/A/B/C",
    "dimension_scores": {{
      "objective": {{"score": 分数, "delta": 与上轮差值, "change": "up/down/flat"}},
      "users": {{"score": 分数, "delta": 差值, "change": "..."}},
      "capabilities": {{"score": 分数, "delta": 差值, "change": "..."}},
      "quality_attributes": {{"score": 分数, "delta": 差值, "change": "..."}},
      "constraints": {{"score": 分数, "delta": 差值, "change": "..."}},
      "integration": {{"score": 分数, "delta": 差值, "change": "..."}},
      "risks": {{"score": 分数, "delta": 差值, "change": "..."}}
    }},
    "top_improvements": [提升最大的2-3维度],
    "top_missing": [缺失项]
  }},
  "inferred_items": [living_spec.json inferred 层 pending 项]
}}
```

**注意**: 如果 overall_score >= {threshold}，action 改为 "summary"。
"""
        elif phase == "confirmation":
            task += """\n## 你的任务

1. 使用 read_json 读取 user_confirmation.json
2. 如果 action="confirm"，写 round_result.json (action="done")
3. 如果 action="revise"，执行 merge_spec.py --revisions，然后重新评分
"""

        return task

    def _build_v3_parse_worker_prompt(self, round_num: int) -> str:
        """Phase 3: 构建 ParseWorker 的 task prompt。"""
        from core.prompt_registry import read_prompt
        parse_prompt = read_prompt("spec_pro/parse")
        session_dir = self._bb.session_dir if self._bb else ""
        if round_num == 1:
            return f"""{parse_prompt}

## 当前任务上下文
- Session: {self.session_id}
- Blackboard: {session_dir}

## 文件路径
- 使用 BlackboardManager 读取: input.md
- 使用 write_stage 写入: round_{round_num:02d}_parse
- 使用 write 写入: spec/living_spec.json
"""
        else:
            prev = round_num - 1
            return f"""{parse_prompt}

## 当前任务上下文
- Session: {self.session_id}
- Blackboard: {session_dir}

## 文件路径
- 使用 read_json 读取: spec/living_spec.json
- 使用 read 读取: spec/user_response_round_{round_num}.md
- 使用 read_stage 读取: round_{prev:02d}_questions
- 使用 write_stage 写入: round_{round_num:02d}_response
"""

    def _build_v3_main_eval_prompt(self, round_num: int) -> str:
        """Phase 3: 构建主 Agent 评分+提问的 prompt。

        ⚠️ DEPRECATED (2026-06-04): 此方法返回值从未被使用。
        评分+提问逻辑已在 _build_v3_round_task() 中内嵌实现。
        保留此方法仅为历史兼容，后续版本可安全删除。
        
        复用 assess.md 的评分哲学 + guide.md 的边界规则。
        """
        from core.prompt_registry import read_prompt
        assess_prompt = read_prompt("spec_pro/assess")
        guide_prompt = read_prompt("spec_pro/guide")
        
        prev = round_num - 1
        session_dir = self._bb.session_dir if self._bb else ""
        return f"""# 主 Agent 评分 + 提问（v3 扁平架构）

你是 Spec Pro 主 Agent。请对当前 Living Spec 进行质量评估并生成引导问题。

{assess_prompt}

---

{guide_prompt}

---

## 你的任务

1. 使用 read_json 读取 spec/living_spec.json
2. 按上述评分标准进行 7 维度评估
3. 按上述边界规则生成 3-5 个引导问题
4. 使用 write 写 spec/quality_report.json
5. 使用 write_stage 写 round_{round_num:02d}_questions
6. 使用 write 写 spec/round_result.json

## 上下文
- 上轮问题: 使用 read_stage 读取 round_{prev:02d}_questions
- 对话历史: 使用 read_json 读取 spec/conversation_log.json
- 质量轨迹: 使用 read_json 读取 spec/quality_trajectory.json
"""

    def _init_phase_instructions(self) -> str:
        """Round 1: Parse -> Assess -> Question"""
        return """# Phase: init (Round 1)

执行以下步骤,严格按顺序:

## Step 1: spawn ParseWorker
使用 sessions_spawn 创建 ParseWorker:
- runtime: "subagent"
- mode: "run"
- task: 读取 domains/spec_pro/prompts/parse.md 的内容作为 task,并注入以下上下文:
  - 使用 BlackboardManager 读取: input.md
  - 使用 write_stage 写入: round_01_parse
  - 使用 write 写入: spec/living_spec.json
- timeoutSeconds: 180
- cleanup: "delete"

等待 ParseWorker 完成.

## Step 1.5: Worker 存在性检查
使用 stage_exists 检查 round_01_parse 是否存在:
```
stage_exists("round_01_parse")
```
如果不存在,使用 write_stage 写入 fallback 数据:
```
write_stage("round_01_parse", {"status": "timeout", "parsed": {}, "inferred": [], "confidence": 0})
```

## Step 2: spawn AssessWorker
- task: 读取 domains/spec_pro/prompts/assess.md 的内容,注入上下文:
  - 使用 read_json 读取: spec/living_spec.json
  - 使用 write 写入: spec/quality_report.json
- timeoutSeconds: 180

等待完成.

## Step 2.5: Worker 存在性检查
如果 spec/quality_report.json 不存在,使用 write 写入 fallback 数据:
```
write("spec/quality_report.json", {"overall_score": 0, "level": "C", "dimensions": [], "top_missing": ["评估超时"], "recommendation": "请继续补充信息"})
```

## Step 3: spawn QuestionWorker
- task: 读取 domains/spec_pro/prompts/guide.md 的内容,注入上下文:
  - 使用 read_json 读取: spec/living_spec.json
  - 使用 read_json 读取: spec/quality_report.json
  - 使用 read_json 读取: spec/conversation_log.json (历史对话记录)
  - 使用 write_stage 写入: round_01_questions
  
  **已问去重规则** (必须遵守):
  1. 读取 conversation_log.json 中所有轮的 meta_directives
     - 如果用户明确说"不要再问 X",则该维度**禁止提问**
  2. 不要重复提问已经得到明确回答的维度
  3. 如果某维度被标记为 deliberately_omitted (用户主动放弃),跳过该维度

- timeoutSeconds: 180

等待完成.

## Step 3.5: Worker 存在性检查
使用 stage_exists 检查 round_01_questions 是否存在:
```
stage_exists("round_01_questions")
```
如果不存在,使用 write_stage 写入 fallback 数据:
```
write_stage("round_01_questions", {"questions": [{"type": "clarification", "text": "请再展开说说你的需求？", "dimension": "objective"}], "strategy_note": "fallback"})
```

## Step 4: 汇总 (D3: 包含 7 维分数)
读取以下文件:
- 使用 read_stage 读取: round_01_questions
- 使用 read_json 读取: spec/quality_report.json

使用 write 工具将以下内容写入 spec/round_result.json:
```json
{
  "action": "questions",
  "round": 1,
  "questions": [从 questions 读取的 questions 数组],
  "quality": {
    "overall_score": [quality_report.json 的 overall_score],
    "level": [quality_report.json 的 level],
    "dimension_scores": {
      "objective": {"score": [分数], "delta": 0, "change": "new"},
      "users": {"score": [分数], "delta": 0, "change": "new"},
      "capabilities": {"score": [分数], "delta": 0, "change": "new"},
      "quality_attributes": {"score": [分数], "delta": 0, "change": "new"},
      "constraints": {"score": [分数], "delta": 0, "change": "new"},
      "integration": {"score": [分数], "delta": 0, "change": "new"},
      "risks": {"score": [分数], "delta": 0, "change": "new"}
    },
    "top_improvements": [],
    "top_missing": [quality_report.json 的 top_missing]
  },
  "inferred_items": [从 living_spec.json 的 inferred 层读取 status=pending 的项]
}
```

## Step 5: 更新 quality_trajectory.json
执行以下命令追加轨迹记录:
```
python3 .deepflow/domains/spec_pro/worker_fallback.py append_trajectory <Blackboard> 1 [quality_report.json 的 overall_score] [quality_report.json 的 level] [questions 中 questions 数组长度]
```

轨迹条目格式:
```json
{"round": 1, "overall_score": 数字, "level": "S/A/B/C", "dimension_scores": {"objective": 数字, "users": 数字, "capabilities": 数字, "quality_attributes": 数字, "constraints": 数字, "integration": 数字, "risks": 数字}, "delta": 0, "questions_asked": 数字, "inferences_validated": 0}
```

## Step 6: 更新 conversation_log.json

使用 write 工具追加第一条对话日志到 spec/conversation_log.json (如果文件已存在,先读取现有内容并追加),格式:
```json
{
  "round": 1,
  "timestamp": "ISO8601",
  "phase": "init",
  "questions": [questions 中的 questions 数组],
  "user_response": "[用户初始输入,截断500字]",
  "parsed_updates_summary": "ParseWorker 解析摘要",
  "quality_before": 0,
  "quality_after": [quality_report.json overall_score],
  "quality_delta": [overall_score],
  "inferences_created": [living_spec.json inferred 层数量],
  "inferences_confirmed": 0,
  "inferences_rejected": 0,
  "meta_directives": [],
  "stop_asking_dimensions": []
}
```

**验证**: 确认 spec/round_result.json 已创建且为合法 JSON。
**验证**: 确认 spec/conversation_log.json 已更新。

**完成。**"""

    def _collecting_phase_instructions(self, round_num: int) -> str:
        """Round N: Response -> Merge -> ProcessGuard -> Assess -> (Question | Proposal | Harness -> Structure)
        
        v2.1 改进:
        - D1: QuestionWorker 注入历史对话 + 已问去重规则
        - D2: ResponseWorker 增加用户指令检测, AssessWorker 增加 deliberately_omitted 规则
        - D3: round_result 包含 7 维分数 + delta
        - D4: QuestionWorker 增加 Process Guard 优先级规则
        - D5: 增加停滞检测分支 -> proposal 模式
        - D7: ProcessGuard 提前到 AssessWorker 之前
        """
        prev_round = round_num - 1
        nn = f"{round_num:02d}"
        pp = f"{prev_round:02d}"
        threshold = self._compute_dynamic_threshold()

        return f"""# Phase: collecting (Round {round_num})

⚠️ **【格式锚点】ResponseWorker 输出格式（强制，不可修改）**
ResponseWorker 的 write_stage("round_{nn}_response") 必须严格按以下 JSON schema 输出：
```json
{{
  "input_guard": {{"valid": true, "contradictions": [], "off_topic": false, "skipped_dimensions": [], "needs_followup": []}},
  "parsed_updates": {{"objective": "...", "pain_points": [], "success_metrics": [], "users": [], "key_scenarios": [], "capabilities": {{"always_do": [], "should_do": [], "never_do": []}}, "quality_attributes": [], "constraints": {{}}, "integration": {{"existing_systems": [], "requirements": []}}, "risks_and_assumptions": {{"risks": [], "assumptions": [], "dependencies": []}}, "user_directives": []}},
  "inference_responses": [],
  "meta_signals": {{"user_said_enough": false, "user_wants_pivot": false, "new_topic_detected": false}},
  "new_inferences": []
}}
```
**禁止使用 "updates" 数组格式！必须使用 "parsed_updates" 对象格式！**

用户回答已写入: spec/user_response_round_{round_num}.md
上轮问题: 使用 read_stage 读取 round_{pp}_questions

## Step 1: spawn ResponseWorker
- task: 读取 domains/spec_pro/prompts/parse_response.md,注入上下文:
  - 使用 read_json 读取: spec/living_spec.json
  - 使用 read 读取: spec/user_response_round_{round_num}.md
  - 使用 read_stage 读取: round_{pp}_questions
  - 使用 write_stage 写入: round_{nn}_response
  
  **用户指令检测规则** (D2: 评分区分拒绝):
  如果用户明确说"不要再问 X"、"X 不需要考虑"、"X 不重要"等:
  - 在 parsed_updates 中新增 user_directives 数组
  - 每条指令包含: dimension, directive="deliberately_omitted", reason
  
  示例输出:
  ```json
  "parsed_updates": {{
    "user_directives": [
      {{"dimension": "users", "directive": "deliberately_omitted", "reason": "用户原话: '不要再问用户相关的问题'"}}
    ]
  }}
  ```
- timeoutSeconds: 180

⚠️ **【格式提醒】再次确认: round_{nn}_response 必须使用 "parsed_updates" 格式，不要用 "updates" 格式！**

## Step 1.5: Worker 存在性检查
使用 stage_exists 检查 round_{nn}_response:
```
stage_exists("round_{nn}_response")
```
如果不存在,使用 write_stage 写入 fallback 数据:
```
write_stage("round_{nn}_response", {{"input_guard": {{"valid": false}}, "parsed_updates": {{}}, "meta_signals": {{}}}})
```

## Step 2: 合并 living_spec.json(代码化,不靠 LLM)
使用 read_stage 读取 round_{nn}_response 的数据,使用 read_json 读取 spec/living_spec.json,然后执行合并命令:
```
python3 .deepflow/domains/spec_pro/merge_spec.py --v6 {{Blackboard}} round_{nn}_response
```
该命令会使用 API 读取 stage 数据,合并到 living_spec.json 并写回。
该脚本会按 writer_protocol 规则合并:
- confirmed 层: 追加新项,不删除已有项
- inferred 层: status=confirmed->移入confirmed层, status=rejected->标记rejected, 新推断->追加
- guardrails: 追加新项
- user_directives: 如果 parsed_updates 中存在 user_directives,合并到 living_spec.confirmed.user_directives
- 矛盾处理: 保留两者并标注 contradiction

## Step 3: Process Guard 检查 (D7: 提前到 AssessWorker 之前)
执行以下命令检查质量轨迹:
```
python3 .deepflow/domains/spec_pro/process_guard.py {{Blackboard}} {round_num}
```
该脚本读取 quality_trajectory.json,检查 progress_rate / inference_integrity / conversation_balance.
如果发现异常,输出调整指令文本;否则输出空.

**保存 Process Guard 输出**,后续注入到 QuestionWorker.

## Step 4: spawn AssessGuideWorker (合并评分+提问)
- task: 读取 domains/spec_pro/prompts/assess_guide.md,注入上下文:
  - 使用 read_json 读取: spec/living_spec.json
  - 使用 read_json 读取: spec/quality_trajectory.json (可选,用于判断轮次策略)
  - 使用 read_json 读取: spec/conversation_log.json (历史对话记录,用于问题去重)
  - 使用 read_stage 读取: round_{pp}_questions (上轮问题)
  - 使用 read_stage 读取: round_{pp}_response (上轮回答解析)
  - 使用 write 写入: spec/quality_report.json (Phase 1 输出)
  - 使用 write_stage 写入: round_{nn}_questions (Phase 2 输出)
  
  **Phase 1: 质量评估**
  - 对 living_spec 进行 7 维度加权评分
  - 特殊状态: deliberately_omitted (用户主动放弃的维度给 50 分,不扣分,不出现在 top_missing)
  
  **Phase 2: 问题生成**
  - 基于 Phase 1 的 quality_report,生成 2-5 个高质量引导问题
  - 已问去重规则 (必须遵守):
    1. 读取 conversation_log.json 中所有轮的 meta_directives
       - 如果用户明确说"不要再问 X",则该维度**禁止提问**
    2. 读取上轮 questions
       - 如果某个维度的某类问题已经问过且用户已回答,不再重复
    3. 如果某维度被标记为 deliberately_omitted,跳过该维度
  
  **Process Guard 优先级规则** (D4):
  如果 Step 3 的 Process Guard 输出了 adjustment_instruction:
  - 将调整指令**作为最高优先级**注入到问题生成逻辑
  - Process Guard 的 adjustments 优先级高于默认策略
  - 如果 Process Guard 说"某维度已被充分覆盖",则该维度不再提问
  
  Process Guard 调整指令: [Step 3 的输出]
- timeoutSeconds: 180

等待 AssessGuideWorker 完成.

## Step 4.5: Worker 存在性检查
如果 spec/quality_report.json 不存在,使用 write 和 write_stage 写入 fallback:
```
write("spec/quality_report.json", {{"overall_score": 0, "level": "C", "dimensions": [], "top_missing": ["AssessGuideWorker 超时"], "recommendation": "请继续补充"}})
write_stage("round_{nn}_questions", {{"questions": [{{"type": "clarification", "text": "请再展开说说你的需求？", "dimension": "objective"}}], "strategy_note": "fallback"}})
```

## Step 5: 更新 quality_trajectory.json
执行以下命令追加轨迹记录:
```
python3 .deepflow/domains/spec_pro/worker_fallback.py append_trajectory {{Blackboard}} {round_num} [quality_report.json overall_score] [quality_report.json level] [上轮 questions 数量] [推断确认数]
```
轨迹条目格式:
```json
{{"round": {round_num}, "overall_score": 数字, "level": "S/A/B/C", "dimension_scores": {{"objective": 数字, "users": 数字, "capabilities": 数字, "quality_attributes": 数字, "constraints": 数字, "integration": 数字, "risks": 数字}}, "delta": [与上一轮分数差], "questions_asked": 数字, "inferences_validated": 数字}}
```

## Step 6: 检查停止条件 (D5: 增加停滞检测)
使用 read_json 读取 quality_report.json 的 overall_score 和 quality_trajectory.json.

### 分支 A: 停滞检测 (D5: 方案确认模式)
如果满足以下**所有**条件:
1. round_num >= 3 (至少已进行 3 轮)
2. 最近 2 轮的 delta 绝对值都 < 3 (质量停滞)
3. overall_score >= 50 (至少有基础信息)

则**不再问问题**,直接输出 Spec 草稿让用户确认:
- spawn StructureWorker:
  - task: 读取 domains/spec_pro/prompts/structure.md,注入上下文:
    - 使用 read_json 读取: spec/living_spec.json
    - 使用 read_json 读取: spec/quality_report.json
    - 使用 write 写入: spec/round_result.json
    - action: "proposal" (注意:不是 "summary")
  - timeoutSeconds: 180
- round_result.json 格式:
```json
{{
  "action": "proposal",
  "round": {round_num},
  "proposal_text": "[StructureWorker 生成的 Spec 草稿摘要]",
  "stagnation_reason": "连续 2 轮质量提升 < 3 分,建议用户确认当前 Spec 是否满足需求",
  "quality": {{
    "overall_score": [overall_score],
    "level": [level],
    "dimension_scores": {{
      "objective": {{"score": [分数], "delta": [与上轮差值], "change": "up/down/flat"}},
      "users": {{"score": [分数], "delta": [差值], "change": "up/down/flat"}},
      "capabilities": {{"score": [分数], "delta": [差值], "change": "up/down/flat"}},
      "quality_attributes": {{"score": [分数], "delta": [差值], "change": "up/down/flat"}},
      "constraints": {{"score": [分数], "delta": [差值], "change": "up/down/flat"}},
      "integration": {{"score": [分数], "delta": [差值], "change": "up/down/flat"}},
      "risks": {{"score": [分数], "delta": [差值], "change": "up/down/flat"}}
    }},
    "top_improvements": [本轮提升最大的 2-3 个维度],
    "top_missing": [quality_report.json 的 top_missing]
  }},
  "inferred_items": [pending 状态的推断]
}}
```

### 分支 B: 质量达标 (overall_score >= {threshold})
spawn HarnessWorker:
- task: 读取 domains/spec_pro/prompts/harness.md,注入上下文:
  - 使用 read_json 读取: spec/living_spec.json
  - 使用 read_json 读取: spec/quality_report.json
  - 使用 read_json 读取: spec/conversation_log.json
  - 使用 read_json 读取: spec/quality_trajectory.json
  - 使用 write 写入: spec/harness_report.json
- timeoutSeconds: 240

等待 HarnessWorker 完成.

## Step 6.5: HarnessWorker 存在性检查
如果 spec/harness_report.json 不存在,使用 write 写入 fallback:
```
write("spec/harness_report.json", {{"final_decision": "WARN", "final_reasoning": "Harness Worker 超时,跳过门禁"}})
```

使用 read_json 读取 harness_report.json 的 final_decision:
- PASS 或 WARN -> spawn StructureWorker:
  - task: 读取 domains/spec_pro/prompts/structure.md,注入上下文:
    - 使用 read_json 读取: spec/living_spec.json
    - 使用 read_json 读取: spec/quality_report.json
    - 使用 write 写入: spec/round_result.json
    - action: "summary" (WARN时在round_result中添加 "harness_warning": true)
  - timeoutSeconds: 180
- SOFT_BLOCK 或 HARD_BLOCK -> 进入分支 C (questions 已由 AssessGuideWorker 产出)

### 分支 C: 质量未达标且未停滞 (overall_score < {threshold} 且不满足停滞条件)
**Questions 已由 Step 4 的 AssessGuideWorker 产出,使用 read_stage 读取 round_{nn}_questions 即可。**

使用 write 工具将以下内容写入 spec/round_result.json (D3: 包含 7 维分数):
```json
{{
  "action": "questions",
  "round": {round_num},
  "questions": [从 questions 读取],
  "quality": {{
    "overall_score": [quality_report overall_score],
    "level": [quality_report level],
    "dimension_scores": {{
      "objective": {{"score": [分数], "delta": [与上轮差值], "change": "up/down/flat"}},
      "users": {{"score": [分数], "delta": [差值], "change": "up/down/flat"}},
      "capabilities": {{"score": [分数], "delta": [差值], "change": "up/down/flat"}},
      "quality_attributes": {{"score": [分数], "delta": [差值], "change": "up/down/flat"}},
      "constraints": {{"score": [分数], "delta": [差值], "change": "up/down/flat"}},
      "integration": {{"score": [分数], "delta": [差值], "change": "up/down/flat"}},
      "risks": {{"score": [分数], "delta": [差值], "change": "up/down/flat"}}
    }},
    "top_improvements": [本轮提升最大的 2-3 个维度,包含 dimension/delta/reason],
    "top_missing": [quality_report.json 的 top_missing]
  }},
  "inferred_items": [从 living_spec.json inferred 层读取 pending 项]
}}
```

## Step 7: 更新 conversation_log.json (D1: 增加元信号记录)

使用 write 工具追加本轮对话日志到 spec/conversation_log.json (如果文件已存在,先读取现有内容并追加),格式:
```json
{{
  "round": {round_num},
  "timestamp": "ISO8601",
  "phase": "collecting",
  "questions": [上轮 questions],
  "user_response": "[用户回答,截断500字]",
  "parsed_updates_summary": "[ResponseWorker 解析摘要,1-2句]",
  "quality_before": [上轮分数],
  "quality_after": [本轮分数],
  "quality_delta": [分数差],
  "inferences_created": [新增推断数],
  "inferences_confirmed": [确认数],
  "inferences_rejected": [拒绝数],
  "meta_directives": [本轮新发现的用户指令,如 deliberately_omitted],
  "stop_asking_dimensions": [用户明确要求停止提问的维度]
}}
```
"""

    def _confirmation_phase_instructions(self) -> str:
        """Confirmation: confirm -> Structure / revise -> merge -> AssessGuide -> (Question | Harness -> Structure)"""
        threshold = self._compute_dynamic_threshold()
        nn = f"{self.current_round:02d}"
        return f"""# Phase: confirmation

用户确认/修正已写入: spec/user_confirmation.json

使用 read_json 读取 user_confirmation.json 中的 action:

## 如果 action = "confirm":
spawn StructureWorker:
- task: 读取 domains/spec_pro/prompts/structure.md,注入上下文:
  - 使用 read_json 读取: spec/living_spec.json
  - 使用 read_json 读取: spec/quality_report.json
  - 使用 read_json 读取: spec/harness_report.json(如果存在)
  - 使用 write 写入: spec/round_result.json
  - action: "done"
  - 在 round_result 中包含: action="done", summary_text, quality, living_spec(完整内容), harness_report(如有), route_recommendation, solution_pro_hints, inferred_pending
- timeoutSeconds: 180

## 如果 action = "revise":
1. 合并修正内容到 living_spec.json:
   执行命令:
   ```
   python3 .deepflow/domains/spec_pro/merge_spec.py --revisions {{Blackboard}}/spec/user_confirmation.json {{Blackboard}}/spec/living_spec.json
   ```
   该脚本读取 user_confirmation.json 中的 revisions 数组,逐条更新到 living_spec.json 的 confirmed 层对应字段.

2. spawn AssessGuideWorker (合并评分+提问):
   - task: 读取 domains/spec_pro/prompts/assess_guide.md,注入上下文:
     - 使用 read_json 读取: spec/living_spec.json
     - 使用 read_json 读取: spec/conversation_log.json (历史对话)
     - 使用 read_json 读取: spec/quality_trajectory.json
     - 使用 write 写入: spec/quality_report.json (Phase 1)
     - 使用 write_stage 写入: round_{nn}_questions (Phase 2)
   - timeoutSeconds: 180

3. AssessGuideWorker 存在性检查:
   如果 spec/quality_report.json 不存在,使用 write 和 write_stage 写入 fallback:
   ```
   write("spec/quality_report.json", {{"overall_score": 0, "level": "C", "dimensions": [], "top_missing": ["AssessGuideWorker 超时"], "recommendation": "请继续补充"}})
   write_stage("round_{nn}_questions", {{"questions": [{{"type": "clarification", "text": "请再展开说说你的需求？", "dimension": "objective"}}], "strategy_note": "fallback"}})
   ```

4. 使用 read_json 读取 quality_report.json 的 overall_score:
   - 达标(≥ {threshold})-> spawn HarnessWorker -> 读取 harness_report.json -> spawn StructureWorker(action="summary")
   - 未达标 -> 使用 write 工具写入 round_result.json (使用 read_stage 读取 round_{nn}_questions)

更新 conversation_log.json,追加一条 confirmation 阶段记录.
"""

    def _write_execution_log(self, event: str, data: Dict[str, Any]) -> None:
        """Append event to execution_log.json. Non-critical: failures are silent."""
        if self._bb is None:
            return
        log = self._bb.read_json("execution_log.json", default={"events": []})
        if log is None:
            log = {"events": []}
        log["events"].append({
            "timestamp": datetime.now().isoformat(),
            "event": event,
            "data": data,
        })
        self._bb.write("execution_log.json", log)