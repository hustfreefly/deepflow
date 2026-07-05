"""
Fix Loop 状态机

Version: 1.0.0
Author: DeepFlow Solution Pro
Date: 2026-06-28

描述:
- Fix Loop 状态机（替代 V1 的 Audit+Fix+Fixer 串行）
- 最多 2 轮修复
- Anti-oscillation 机制（防止循环失败）
- 状态持久化（fix_loop_state.json）

设计原则:
- 代码控制状态流转
- LLM 负责诊断和修复
- 不直接调用 OpenClaw（由主 Agent spawn）
"""

import json
import logging
from typing import Any, Callable, Optional
from enum import Enum
from datetime import datetime

logger = logging.getLogger(__name__)


class FixLoopStatus(str, Enum):
    """Fix Loop 状态枚举"""
    IDLE = "IDLE"  # 未开始
    EVALUATING = "EVALUATING"  # 评估 Harness Report
    DIAGNOSING = "DIAGNOSING"  # 诊断失败原因
    FIXING = "FIXING"  # 执行修复
    PASS = "PASS"  # 通过
    ABORT = "ABORT"  # 中止（达到最大轮次）


class FixLoopStateMachine:
    """
    Fix Loop 状态机
    
    状态流转：
    IDLE → EVALUATING → DIAGNOSING → FIXING → EVALUATING → ... → PASS/ABORT
    
    使用方法：
        fsm = FixLoopStateMachine(blackboard=bb, max_rounds=2)
        result = fsm.run_fix_loop(harness_report)
    """
    
    def __init__(
        self,
        blackboard: Any,
        spawn_fn: Optional[Callable] = None,
        max_rounds: int = 2,
    ):
        """
        初始化 Fix Loop 状态机
        
        Args:
            blackboard: BlackboardManager 实例
            spawn_fn: spawn 函数（用于 spawn LLM 做诊断和修复）
            max_rounds: 最大修复轮次（默认 2）
        """
        self.blackboard = blackboard
        self.spawn_fn = spawn_fn
        self.max_rounds = max_rounds
        
        # 加载或初始化状态
        self.state = self._load_or_init_state()
        
        logger.info(f"FixLoopStateMachine initialized (max_rounds={max_rounds})")
    
    def _load_or_init_state(self) -> dict:
        """加载或初始化状态"""
        try:
            state = self.blackboard.read("stages/fix_loop_state.json")
            logger.info("Loaded existing Fix Loop state")
            return state
        except Exception:
            # 初始化新状态
            state = {
                "schema_version": "1.0.0",
                "timestamp": datetime.now().isoformat(),
                "status": FixLoopStatus.IDLE.value,
                "current_round": 0,
                "max_rounds": self.max_rounds,
                "frozen_items": [],  # 已 PASS 的检查项（冻结，不再重新评估）
                "regression_detected": [],  # 检测到的回归
                "fix_history": [],  # 修复历史
            }
            self.blackboard.write("stages/fix_loop_state.json", state)
            logger.info("Initialized new Fix Loop state")
            return state
    
    def _save_state(self):
        """保存状态"""
        self.state["timestamp"] = datetime.now().isoformat()
        self.blackboard.write("stages/fix_loop_state.json", self.state)
    
    def run_fix_loop(self, harness_report: dict) -> dict:
        """
        运行 Fix Loop（主入口）
        
        Args:
            harness_report: Harness Agent 输出（包含 gate_a, gate_b, final_verdict）
        
        Returns:
            Fix Loop 结果（dict）
        """
        logger.info("Starting Fix Loop")
        
        # 状态流转：IDLE → EVALUATING
        self.state["status"] = FixLoopStatus.EVALUATING.value
        self._save_state()
        
        # 评估 Harness Report
        result = self._evaluate_harness_report(harness_report)
        
        if result["should_fix"]:
            # 需要修复
            self._run_fix_rounds(harness_report)
        else:
            # 不需要修复，直接 PASS
            self.state["status"] = FixLoopStatus.PASS.value
            self._save_state()
            logger.info("Fix Loop: PASS (no fix needed)")
        
        return {
            "status": self.state["status"],
            "rounds_completed": self.state["current_round"],
            "frozen_items": self.state["frozen_items"],
            "regression_detected": self.state["regression_detected"],
            "fix_history": self.state["fix_history"],
        }
    
    def _evaluate_harness_report(self, harness_report: dict) -> dict:
        """评估 Harness Report，决定是否需要修复"""
        final_verdict = harness_report.get("final_verdict", {}).get("final_verdict", "FAIL")
        
        if final_verdict == "PASS":
            return {"should_fix": False, "reason": "Already PASS"}
        
        # 检查是否达到最大轮次
        if self.state["current_round"] >= self.max_rounds:
            self.state["status"] = FixLoopStatus.ABORT.value
            self._save_state()
            return {"should_fix": False, "reason": f"Reached max rounds ({self.max_rounds})"}
        
        # 需要修复
        return {"should_fix": True, "reason": "FAIL and rounds available"}
    
    def _run_fix_rounds(self, harness_report: dict):
        """运行修复轮次"""
        while self.state["current_round"] < self.max_rounds:
            round_num = self.state["current_round"] + 1
            logger.info(f"Starting Fix Round {round_num}/{self.max_rounds}")
            
            # 状态：EVALUATING → DIAGNOSING
            self.state["status"] = FixLoopStatus.DIAGNOSING.value
            self.state["current_round"] = round_num
            self._save_state()
            
            # 1. 诊断失败原因（LLM）
            diagnosis = self._diagnose_failures(harness_report)
            
            # 2. Anti-oscillation 检查
            if self._check_oscillation(diagnosis):
                logger.warning("Anti-oscillation triggered, aborting Fix Loop")
                self.state["status"] = FixLoopStatus.ABORT.value
                self._save_state()
                break
            
            # 状态：DIAGNOSING → FIXING
            self.state["status"] = FixLoopStatus.FIXING.value
            self._save_state()
            
            # 3. 执行修复（LLM）
            fix_result = self._execute_fixes(diagnosis)
            
            # 4. 重新评估（spawn 新的 Harness Agent）
            new_harness_report = self._re_evaluate()
            
            # 5. 更新冻结项（已 PASS 的检查项）
            self._update_frozen_items(new_harness_report)
            
            # 6. 检测回归（之前 PASS 的项现在 FAIL）
            self._detect_regression(new_harness_report)
            
            # 7. 记录修复历史
            self.state["fix_history"].append({
                "round": round_num,
                "diagnosis": diagnosis,
                "fix_result": fix_result,
                "harness_report": new_harness_report,
            })
            self._save_state()
            
            # 8. 评估新的 Harness Report
            result = self._evaluate_harness_report(new_harness_report)
            
            if not result["should_fix"]:
                # PASS 或达到最大轮次
                if result["reason"] == "Already PASS":
                    self.state["status"] = FixLoopStatus.PASS.value
                    self._save_state()
                    logger.info(f"Fix Loop: PASS after {round_num} rounds")
                else:
                    logger.info(f"Fix Loop: ABORT after {round_num} rounds ({result['reason']})")
                break
            
            # 继续下一轮
            harness_report = new_harness_report
        
        # 如果循环结束仍未 PASS
        if self.state["status"] not in [FixLoopStatus.PASS.value, FixLoopStatus.ABORT.value]:
            self.state["status"] = FixLoopStatus.ABORT.value
            self._save_state()
            logger.info(f"Fix Loop: ABORT after {self.max_rounds} rounds")
    
    def _diagnose_failures(self, harness_report: dict) -> dict:
        """诊断失败原因（LLM）"""
        logger.info("Diagnosing failures (LLM)")
        
        # 提取失败项
        gate_b_failed = harness_report.get("gate_b_results", {}).get("failed_items", [])
        gate_a_score = harness_report.get("gate_a_scores", {}).get("score", 0)
        
        # 构建诊断 task
        task = f"""
你是一个失败诊断器。你的任务是分析 Harness Report 中的失败项，并给出修复建议。

## Harness Report
```json
{json.dumps(harness_report, indent=2, ensure_ascii=False)}
```

## 已冻结的检查项（不再重新评估）
{json.dumps(self.state["frozen_items"], indent=2)}

## 你的任务
1. 分析每个失败项的根因
2. 给出具体的修复建议（修改哪个文件、哪个字段）
3. 评估修复难度（easy/medium/hard）

## 输出格式
```json
{{
  "diagnoses": [
    {{
      "failed_item": "check_name",
      "root_cause": "根因分析",
      "fix_suggestion": "修复建议",
      "difficulty": "easy/medium/hard"
    }}
  ],
  "overall_assessment": "整体评估"
}}
```

## 输出路径
stages/fix_diagnosis_round_{self.state['current_round']}.json

请完成诊断并将输出写入指定路径。
"""
        
        # Spawn LLM（如果提供了 spawn_fn）
        if self.spawn_fn:
            result = self.spawn_fn(
                task=task,
                mode="run",
                label=f"fix_diagnosis_round_{self.state['current_round']}",
            )
            
            # 读取 LLM 输出
            diagnosis_path = f"stages/fix_diagnosis_round_{self.state['current_round']}.json"
            diagnosis = self.blackboard.read(diagnosis_path)
        else:
            # 本地诊断（简化实现，用于测试）
            diagnosis = self._diagnose_local(gate_b_failed, gate_a_score)
        
        return diagnosis
    
    def _diagnose_local(self, gate_b_failed: list, gate_a_score: float) -> dict:
        """本地诊断（简化实现，用于测试）"""
        logger.warning("Running local diagnosis (test mode)")
        
        diagnoses = []
        for item in gate_b_failed:
            diagnoses.append({
                "failed_item": item.get("name", "unknown"),
                "root_cause": f"Local diagnosis for {item.get('name', 'unknown')}",
                "fix_suggestion": f"Fix {item.get('name', 'unknown')}",
                "difficulty": "easy",
            })
        
        if gate_a_score < 0.85:
            diagnoses.append({
                "failed_item": "gate_a_score",
                "root_cause": f"Gate A score {gate_a_score:.2f} < 0.85",
                "fix_suggestion": "Improve completeness/necessity/alignment/global_impact",
                "difficulty": "medium",
            })
        
        return {
            "diagnoses": diagnoses,
            "overall_assessment": f"Local diagnosis: {len(diagnoses)} issues found",
        }
    
    def _check_oscillation(self, diagnosis: dict) -> bool:
        """
        Anti-oscillation 检查
        
        如果连续 2 轮诊断出相同的失败项，说明无法修复，触发 abort
        
        Returns:
            True = 触发 oscillation，应 abort
        """
        if self.state["current_round"] < 2:
            return False  # 第一轮无法检测
        
        # 提取当前轮的失败项
        current_failed = set()
        for d in diagnosis.get("diagnoses", []):
            current_failed.add(d.get("failed_item", ""))
        
        # 提取上一轮的失败项
        prev_fix = self.state["fix_history"][-1] if self.state["fix_history"] else {}
        prev_diagnosis = prev_fix.get("diagnosis", {})
        prev_failed = set()
        for d in prev_diagnosis.get("diagnoses", []):
            prev_failed.add(d.get("failed_item", ""))
        
        # 检查是否相同
        if current_failed and current_failed == prev_failed:
            logger.warning(f"Anti-oscillation: same failures in round {self.state['current_round']} and {self.state['current_round']-1}")
            return True
        
        return False
    
    def _execute_fixes(self, diagnosis: dict) -> dict:
        """执行修复（LLM）"""
        logger.info("Executing fixes (LLM)")
        
        # 构建修复 task
        task = f"""
你是一个修复器。你的任务是根据诊断结果修复失败的检查项。

## 诊断结果
```json
{json.dumps(diagnosis, indent=2, ensure_ascii=False)}
```

## 已冻结的检查项（不要修改）
{json.dumps(self.state["frozen_items"], indent=2)}

## 你的任务
1. 根据每个诊断项的 fix_suggestion 执行修复
2. 修改对应的 Blackboard 文件
3. 不要修改已冻结的检查项

## 输出格式
```json
{{
  "fixes": [
    {{
      "failed_item": "check_name",
      "file_modified": "stages/xxx.json",
      "changes": "修改描述"
    }}
  ],
  "overall_result": "修复结果总结"
}}
```

## 输出路径
stages/fix_result_round_{self.state['current_round']}.json

请完成修复并将输出写入指定路径。
"""
        
        # Spawn LLM（如果提供了 spawn_fn）
        if self.spawn_fn:
            result = self.spawn_fn(
                task=task,
                mode="run",
                label=f"fix_result_round_{self.state['current_round']}",
            )
            
            # 读取 LLM 输出
            fix_path = f"stages/fix_result_round_{self.state['current_round']}.json"
            fix_result = self.blackboard.read(fix_path)
        else:
            # 本地修复（简化实现，用于测试）
            fix_result = self._fix_local(diagnosis)
        
        return fix_result
    
    def _fix_local(self, diagnosis: dict) -> dict:
        """本地修复（简化实现，用于测试）"""
        logger.warning("Running local fix (test mode)")
        
        fixes = []
        for d in diagnosis.get("diagnoses", []):
            fixes.append({
                "failed_item": d.get("failed_item", "unknown"),
                "file_modified": "stages/test.json",
                "changes": f"Local fix for {d.get('failed_item', 'unknown')}",
            })
        
        return {
            "fixes": fixes,
            "overall_result": f"Local fix: {len(fixes)} items fixed",
        }
    
    def _re_evaluate(self) -> dict:
        """重新评估（spawn 新的 Harness Agent）"""
        logger.info("Re-evaluating (spawn new Harness Agent)")
        
        # 读取修复后的 consolidation 输出
        try:
            consolidation = self.blackboard.read("stages/consolidation.json")
        except Exception as e:
            logger.warning(f"Failed to read consolidation: {e}")
            consolidation = {}
        
        # 读取 Gate 配置
        try:
            expert_manifest = self.blackboard.read("stages/meta_planning.json")
            gate_a_config = expert_manifest.get("gate_a", {})
            gate_b_config = expert_manifest.get("gate_b", {})
        except Exception as e:
            logger.warning(f"Failed to load Gate config: {e}")
            gate_a_config = {}
            gate_b_config = {}
        
        # 构建 Harness Agent task
        task = f"""
你是一个 Harness Agent。你的任务是对修复后的方案进行重新评估。

## Consolidation 输出（修复后）
```json
{json.dumps(consolidation, indent=2, ensure_ascii=False)}
```

## Gate A 配置
```json
{json.dumps(gate_a_config, indent=2, ensure_ascii=False)}
```

## Gate B 配置
```json
{json.dumps(gate_b_config, indent=2, ensure_ascii=False)}
```

## 已冻结的检查项（不再重新评估）
{json.dumps(self.state["frozen_items"], indent=2)}

## 你的任务
1. 计算 Gate A 评分（四维度加权分）
2. 评估 Gate B 检查项（动态检查，跳过已冻结项）
3. 生成 final_verdict（Gate A PASS ∧ Gate B PASS）

## 输出路径
stages/harness_report_round_{self.state['current_round']}.json

请完成评估并将输出写入指定路径。
"""
        
        # Spawn Harness Agent（如果提供了 spawn_fn）
        if self.spawn_fn:
            result = self.spawn_fn(
                task=task,
                mode="run",
                label=f"harness_report_round_{self.state['current_round']}",
            )
            
            # 读取 Harness Agent 输出
            harness_path = f"stages/harness_report_round_{self.state['current_round']}.json"
            harness_report = self.blackboard.read(harness_path)
        else:
            # 本地评估（简化实现，用于测试）
            harness_report = self._evaluate_local(consolidation)
        
        return harness_report
    
    def _evaluate_local(self, consolidation: dict) -> dict:
        """本地评估（简化实现，用于测试）"""
        logger.warning("Running local evaluation (test mode)")
        
        return {
            "gate_a_scores": {
                "score": 0.9,
                "verdict": "PASS",
                "scores": {
                    "completeness": 0.9,
                    "necessity": 0.9,
                    "alignment": 0.9,
                    "global_impact": 0.9,
                },
            },
            "gate_b_results": {
                "pass_rate": 1.0,
                "verdict": "PASS",
                "failed_items": [],
            },
            "final_verdict": {
                "final_verdict": "PASS",
                "gate_a": "PASS",
                "gate_b": "PASS",
            },
        }
    
    def _update_frozen_items(self, harness_report: dict):
        """更新冻结项（已 PASS 的检查项）"""
        gate_b_passed = harness_report.get("gate_b_results", {}).get("passed_items", [])
        
        for item in gate_b_passed:
            if item not in self.state["frozen_items"]:
                self.state["frozen_items"].append(item)
                logger.info(f"Frozen item added: {item}")
        
        self._save_state()
    
    def _detect_regression(self, harness_report: dict):
        """检测回归（之前 PASS 的项现在 FAIL）"""
        gate_b_failed = harness_report.get("gate_b_results", {}).get("failed_items", [])
        
        for item in gate_b_failed:
            item_name = item.get("name", "")
            if item_name in self.state["frozen_items"]:
                # 回归检测
                regression = {
                    "item": item_name,
                    "round": self.state["current_round"],
                    "message": f"Regression detected: {item_name} was PASS but now FAIL",
                }
                self.state["regression_detected"].append(regression)
                logger.warning(f"Regression detected: {item_name}")
        
        self._save_state()


__all__ = [
    "FixLoopStatus",
    "FixLoopStateMachine",
]
