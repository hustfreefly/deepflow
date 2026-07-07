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
from domains.spec_pro.contracts.gate import gate_living_spec_density, gate_quality_report, gate_harness_decision
from domains.spec_pro.handoff import build_handoff_package, save_handoff_package
from core.trace import start_trace, span  # 全链路追踪：跨域 trace_id

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
        self._bb: Optional[BlackboardManager] = None
        self.current_round: int = 0
        self.state: DialogState = DialogState.START
        self._config = MODE_CONFIG[mode]
        # 域上下文缓存：parse 阶段推断后保存，供后续轮次评分/提问使用
        self._domain_type: Optional[str] = None
        self._domain_context: str = ""

        # 全链路追踪：在 Coordinator 初始化时启动 trace
        self.trace_id: Optional[str] = start_trace()
        span("coordinator_init", domain="spec_pro", scenario=scenario, mode=mode)

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

        # 全链路追踪：记录 session 初始化 span
        span("session_init", domain="spec_pro", scenario=self.scenario, session_id=self.session_id)

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

        # Build first round task
        self.current_round = 1
        self.state = DialogState.PARSING
        task = self._build_round_task(round_num=1, phase="init")

        # Watcher integration: provide all info needed for main Agent to create cron
        deepflow_root = str(Path(__file__).resolve().parent.parent.parent)
        watcher_config_rel = "domains/spec_pro/config/watcher_config.json"
        watcher_config_abs = os.path.join(deepflow_root, watcher_config_rel)

        return {
            "session_id": self.session_id,
            "base_path": str(self._bb.session_dir),
            "orchestrator_task": task,
            "v3_parse_worker_prompt": self._build_parse_worker_prompt(1),
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

        # Fix 2: 从上一轮 parse 输出中提取 inferred_domain（LLM 语义推断结果）
        self._extract_domain_from_parse(self.current_round - 1)

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

        # Build task
        task = self._build_round_task(
            round_num=self.current_round, phase="collecting"
        )
        v3_parse = self._build_parse_worker_prompt(self.current_round)

        self._write_execution_log("round_start", {
            "round": self.current_round,
            "response_length": len(user_response),
        })

        return {
            "orchestrator_task": task,
            "round_num": self.current_round,
            "v3_parse_worker_prompt": v3_parse,
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
            Worker task prompt string

        Raises:
            RuntimeError: session 未初始化
        """
        if not self.session_id or self._bb is None:
            raise RuntimeError("Session not initialized. Call init_session() first.")

        # Write confirmation
        self._bb.write("spec/user_confirmation.json", user_confirmation)

        self.state = DialogState.REVISING if user_confirmation.get("action") == "revise" else DialogState.CONFIRMING

        return self._build_confirmation_task(round_num=self.current_round + 1)

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

    def check_density_gate(self) -> dict:
        """
        程序化密度 Gate 检查。

        从 Blackboard 读取 living_spec.json，运行 gate_living_spec_density()。

        Returns:
            dict: {"passed": bool, "issues": list[str], "score": float, "warnings": list[str]}
        """
        if self._bb is None:
            return {"passed": False, "issues": ["Blackboard 未初始化"], "score": 0.0, "warnings": []}

        living_spec_data = self._bb.read_json("spec/living_spec.json")
        if living_spec_data is None:
            return {"passed": False, "issues": ["living_spec.json 不存在"], "score": 0.0, "warnings": []}

        try:
            spec_model = LivingSpec(**living_spec_data)
        except Exception as e:
            return {"passed": False, "issues": [f"LivingSpec 解析失败: {e}"], "score": 0.0, "warnings": []}

        density_result = gate_living_spec_density(spec_model)

        # Compute complexity score and inject into density gate result
        try:
            from domains.spec_pro.contracts.gate import compute_complexity_score
            complexity_result = compute_complexity_score(living_spec_data)
            density_result["complexity_score"] = complexity_result.get("complexity_score", 0)
            density_result["complexity_factors"] = complexity_result.get("complexity_factors", [])
            density_result["suggested_engine"] = complexity_result.get("suggested_engine", "direct")
            density_result["suggested_mode"] = complexity_result.get("suggested_mode", "simple")
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"compute_complexity_score failed: {e}")

        return density_result

    def run_harness_decision(self) -> Optional[dict]:
        """
        执行 Harness 三层门控决策（Layer 1 density + Layer 2 LLM scores → Layer 3 decision）。

        结果写入 spec/harness_report.json。

        Returns:
            harness decision dict，如果必要数据不存在则返回 None
        """
        if self._bb is None:
            return None

        # Layer 1: density gate
        density_result = self.check_density_gate()

        # Layer 2: quality report dimension scores
        quality_report_data = self._bb.read_json("spec/quality_report.json", default={})
        layer2_scores = quality_report_data.get("quality", quality_report_data)

        # Layer 3: merge decision
        decision = gate_harness_decision(density_result, layer2_scores)

        # 规范化 quality dimensions（数组 → dict）
        try:
            from domains.spec_pro.merge_spec import _normalize_quality_dimensions
            dims = layer2_scores.get("dimension_scores", {})
            normalized = _normalize_quality_dimensions(dims)
            if normalized != dims:
                layer2_scores["dimension_scores"] = normalized
                decision["layer2_scores"] = normalized
        except Exception:
            pass

        # 写入 harness report
        self._bb.write("spec/harness_report.json", decision)
        self._write_execution_log("harness_decision", decision)
        return decision

    def build_handoff_on_done(self) -> Optional[Path]:
        """
        在 density gate 通过后构建 handoff package。

        Returns:
            handoff package 文件路径，如果 gate 未通过则返回 None
        """
        if self._bb is None:
            return None

        density_result = self.check_density_gate()
        if not density_result.get("passed", False):
            return None

        living_spec_data = self._bb.read_json("spec/living_spec.json", default={})
        quality_report_data = self._bb.read_json("spec/quality_report.json", default={})

        # 契约笼子：验证 quality_report 格式
        _, qr_errors = gate_quality_report(quality_report_data)
        if qr_errors:
            raise ValueError(f"QualityReport 契约验证失败: {qr_errors}")

        # Harness 三层门控（如果尚未执行）
        harness_report = self._bb.read_json("spec/harness_report.json")
        if harness_report is None:
            harness_report = self.run_harness_decision()

        package = build_handoff_package(
            living_spec=living_spec_data,
            quality_report=quality_report_data,
            density_gate_result=density_result,
            semantic_anchors=living_spec_data.get("semantic_anchors", []),
        )
        # 全链路追踪：将 trace_id 注入 handoff package，供下游域继承
        package["trace_id"] = self.trace_id

        output_path = save_handoff_package(package, self._bb.session_dir)
        self._write_execution_log("handoff_package_created", {
            "path": str(output_path),
            "density_score": density_result.get("score", 0),
        })
        return output_path

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

    def _build_confirmation_task(self, round_num: int) -> str:
        """
        构建确认阶段主 Agent 执行指令。

        主 Agent 直接读写文件。
        包含 density gate 检查 + handoff package 生成。
        """
        threshold = self._compute_dynamic_threshold()
        session_dir = self._bb.session_dir if self._bb else ""

        # --- domain_context 注入（确认阶段也需要域感知） ---
        domain_context = self._get_domain_context()
        domain_prefix = f"{domain_context}\n\n" if domain_context else ""

        return f"""{domain_prefix}# Spec Pro v3 确认阶段 — 主 Agent 执行指南

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
   - 提取维度：根据项目性质选择合适的类别。常见类别包括：platform_api / architecture_principle / external_system / technical_constraint（软件域）; market_segment / patent_portfolio / regulatory_framework（投资域）; physical_constraint / material_spec（硬件域）; business_rule / compliance_requirement（商业域）。也可根据项目需要自定义类别。
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

5. **🔴 Density Gate 检查（契约笼子，不可跳过）**：
   执行以下命令检查 Living Spec 密度：
   ```
   python3 .deepflow/domains/spec_pro/check_density_cli.py "{session_dir}"
   ```
   - 如果输出 `PASSED`：继续步骤 6
   - 如果输出 `FAILED`：**不进入 done**，改为 action="questions"：
     - 将密度问题追加到 questions 列表
     - 写 round_result.json (action="questions")，包含密度问题
     - 结束本轮

6. **构建 Handoff Package + 写 round_result.json**：
   执行以下命令构建 handoff package（`--extract-anchors` 强制 Pydantic 验证 semantic anchors 格式）：
   ```
   python3 .deepflow/domains/spec_pro/build_handoff_cli.py "{session_dir}" --extract-anchors
   ```
   然后使用 write 工具写入 spec/round_result.json：
```json
{{
  "action": "done",
  "round": {round_num},
  "summary_text": "需求梳理完成。核心目标：[从 living_spec 提取]",
  "living_spec": [完整 living_spec 内容],
  "quality": {{
    "overall_score": [quality_report 的 overall_score],
    "level": [quality_report 的 level]
  }},
  "handoff_package_path": "spec/spec_handoff_package.json"
}}
```

### 如果 action = "revise"：

1. 合并修正内容到 living_spec.json：
```
python3 .deepflow/domains/spec_pro/merge_spec.py --revisions spec/user_confirmation.json spec/living_spec.json
```
2. 对更新后的 living_spec 进行 7 维度评分
3. 如果 overall_score >= {threshold}：
   - 执行 Density Gate 检查（同上步骤 5）
   - 如果 Density Gate PASSED → 构建 Handoff Package（同上步骤 6）→ 写 round_result.json (action="done")
   - 如果 Density Gate FAILED → 写 round_result.json (action="questions")，包含密度问题
4. 如果 overall_score < {threshold}：
   - 生成 2-4 个补充问题
   - 写 round_result.json (action="questions")
"""

    def _get_domain_context(self) -> str:
        """获取域上下文。优先从缓存读取，fallback 到 living_spec。

        域类型由 parse worker（LLM）在解析需求时推断，写入 living_spec.meta.domain_type。
        coordinator 不再做关键词匹配推断域类型（已删除 infer_domain_from_input）。

        Returns:
            域上下文文本（markdown 格式），如果无法确定则返回空字符串
        """
        # 优先使用缓存
        if hasattr(self, '_domain_context') and self._domain_context:
            return self._domain_context

        # fallback: 从 living_spec 读取
        domain_type = None
        if hasattr(self, '_bb') and self._bb is not None:
            try:
                living_spec_data = self._bb.read_json("spec/living_spec.json", default={})
                if isinstance(living_spec_data, dict):
                    domain_type = living_spec_data.get("meta", {}).get("domain_type")
            except Exception:
                pass

        if domain_type:
            try:
                from domains.spec_pro.domain_context import build_domain_context
                ctx = build_domain_context(domain_type)
                self._domain_context = ctx  # 缓存
                self._domain_type = domain_type
                return ctx
            except Exception:
                pass
        return ""

    def _extract_domain_from_parse(self, round_num: int) -> None:
        """从 parse worker 输出中提取 inferred_domain，保存到实例变量。

        parse worker（LLM）在解析需求时同时推断域类型。
        coordinator 读取推断结果，缓存到 _domain_type/_domain_context，
        供后续轮次的 _build_round_task 和 _build_confirmation_task 使用。

        Args:
            round_num: 已完成的轮次号（其 parse 输出将被读取）
        """
        if self._bb is None:
            return
        try:
            parse_data = self._bb.read_json(f"stages/round_{round_num:02d}_parse.json", default={})
            if not isinstance(parse_data, dict):
                return
            inferred = parse_data.get("inferred_domain", "")
            if inferred and inferred != "unknown":
                # 只在尚未确定域类型时更新，避免覆盖
                if not self._domain_type:
                    self._domain_type = inferred
                    from domains.spec_pro.domain_context import build_domain_context
                    self._domain_context = build_domain_context(inferred)
        except Exception:
            # 提取失败不阻断主流程
            pass

    def _build_round_task(self, round_num: int, phase: str) -> str:
        """
        生成主 Agent 直接执行的流程指令。

        主 Agent 直接评分+提问，不 spawn Worker。
        """
        threshold = self._compute_dynamic_threshold()
        base_threshold = self._config["threshold"]
        max_rounds = self._config["max_rounds"]
        
        threshold_note = ""
        if threshold != base_threshold:
            threshold_note = f"\n**注意**: 质量阈值已从 {base_threshold} 动态调整为 {threshold}\n"

        session_dir = self._bb.session_dir if self._bb else ""

        # --- domain_context 注入（域感知，由 LLM 在 parse 阶段推断） ---
        domain_context = self._get_domain_context()
        domain_prefix = f"{domain_context}\n\n" if domain_context else ""

        task = f"""{domain_prefix}# Spec Pro v3 扁平架构 — 主 Agent 执行指南

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

    def _build_parse_worker_prompt(self, round_num: int) -> str:
        """构建 ParseWorker 的 task prompt。

        第一轮不预注入 domain_context（此时还不知道域类型，LLM 自己会判断）。
        后续轮次从 living_spec.meta.domain_type 读取（由 _get_domain_context 提供）。
        """
        from core.prompt_registry import read_prompt
        parse_prompt = read_prompt("spec_pro/parse")
        session_dir = self._bb.session_dir if self._bb else ""

        # --- domain_context 注入（第一轮不注入，后续轮次从 living_spec 读取） ---
        domain_context = ""
        if round_num > 1:
            domain_context = self._get_domain_context()

        domain_prefix = f"{domain_context}\n\n" if domain_context else ""

        if round_num == 1:
            return f"""{domain_prefix}{parse_prompt}

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
            return f"""{domain_prefix}{parse_prompt}

## 当前任务上下文
- Session: {self.session_id}
- Blackboard: {session_dir}

## 文件路径
- 使用 read_json 读取: spec/living_spec.json
- 使用 read 读取: spec/user_response_round_{round_num}.md
- 使用 read_stage 读取: round_{prev:02d}_questions
- 使用 write_stage 写入: round_{round_num:02d}_response
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