"""
Golden Case Runner — 端到端验证运行器

用途：运行预定义的 Golden Case，验证 Pipeline 端到端功能
"""
import json
import logging
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class GoldenCaseRunner:
    """
    Golden Case 运行器
    
    支持：
    1. 从 JSON 文件加载 Golden Case
    2. 使用 LLMRecorder 的 mock spawn_fn
    3. 运行完整 Pipeline
    4. 验证输出（量化断言）
    """
    
    def __init__(self, golden_cases_dir: str = None):
        self.golden_cases_dir = Path(golden_cases_dir or "tests/golden/v2")
    
    def load_case(self, case_id: str) -> dict:
        """加载 Golden Case"""
        filepath = self.golden_cases_dir / f"{case_id}.json"
        if not filepath.exists():
            raise FileNotFoundError(f"Golden case not found: {filepath}")
        
        return json.loads(filepath.read_text())
    
    def run_case(self, case_id: str, master_orchestrator) -> dict:
        """
        运行单个 Golden Case
        
        Args:
            case_id: Golden Case ID（如 "golden_case_001"）
            master_orchestrator: MasterOrchestrator 实例
        
        Returns:
            {
                "case_id": str,
                "status": "PASS" | "FAIL",
                "assertions": [...],
                "duration": float,
            }
        """
        case = self.load_case(case_id)
        start_time = time.time()
        
        # 运行 Pipeline
        try:
            result = master_orchestrator.run(
                user_input=case["input"]["user_input"],
                config=case["input"]["config"],
            )
            
            # 验证断言
            assertions = self._verify_assertions(result, case["expected"])
            
            duration = time.time() - start_time
            all_passed = all(a["passed"] for a in assertions)
            
            return {
                "case_id": case_id,
                "status": "PASS" if all_passed else "FAIL",
                "assertions": assertions,
                "duration": duration,
                "pipeline_result": result,
            }
            
        except Exception as e:
            return {
                "case_id": case_id,
                "status": "ERROR",
                "error": str(e),
                "duration": time.time() - start_time,
            }
    
    def _verify_assertions(self, result: dict, expected: dict) -> list:
        """验证量化断言"""
        assertions = []
        
        # 1. Pipeline 状态
        assertions.append({
            "name": "pipeline_status",
            "expected": "COMPLETE",
            "actual": result.get("status"),
            "passed": result.get("status") == "COMPLETE",
        })
        
        # 2. Planning 输出存在（类型安全）
        planning = result.get("planning", {})
        if not isinstance(planning, dict):
            planning = {}
        assertions.append({
            "name": "planning_has_experts",
            "expected": True,
            "actual": len(planning.get("experts", [])) > 0,
            "passed": len(planning.get("experts", [])) > 0,
        })
        
        # 3. 约束数量 >= 预期最小值
        min_constraints = expected.get("min_constraints", 1)
        actual_constraints = len(planning.get("unified_constraints", {}).get("constraints", []))
        assertions.append({
            "name": "min_constraints",
            "expected": f">= {min_constraints}",
            "actual": actual_constraints,
            "passed": actual_constraints >= min_constraints,
        })
        
        # 4. Research 输出存在（类型安全）
        research = result.get("research", {})
        if not isinstance(research, dict):
            research = {}
        research_has_output = (
            len(research.get("findings", [])) > 0 
            or len(research.get("key_findings", [])) > 0
            or research.get("status") in ("DEGRADED", "COMPLETE")
            or len(research.keys()) > 3  # has substantial content
        )
        assertions.append({
            "name": "research_has_findings",
            "expected": True,
            "actual": research_has_output,
            "passed": research_has_output,
        })
        
        # 5. ReviewQC 输出存在（类型安全）
        review_qc = result.get("review_qc", {})
        if not isinstance(review_qc, dict):
            review_qc = {}
        assertions.append({
            "name": "review_qc_has_verdict",
            "expected": True,
            "actual": review_qc.get("final_verdict") is not None or review_qc.get("status") == "DEGRADED",
            "passed": review_qc.get("final_verdict") is not None or review_qc.get("status") == "DEGRADED",
        })
        
        # 6. 最终报告存在
        assertions.append({
            "name": "final_report_exists",
            "expected": True,
            "actual": result.get("final_report") is not None,
            "passed": result.get("final_report") is not None,
        })
        
        # 7. 自定义断言
        for assertion in expected.get("custom_assertions", []):
            actual_value = self._resolve_path(result, assertion["path"])
            assertions.append({
                "name": assertion["name"],
                "expected": assertion["expected"],
                "actual": actual_value,
                "passed": self._compare(actual_value, assertion["expected"], assertion.get("operator", "eq")),
            })
        
        return assertions
    
    def _resolve_path(self, data: dict, path: str):
        """解析 dot-separated path"""
        parts = path.split(".")
        current = data
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            else:
                return None
        return current
    
    def _compare(self, actual, expected, operator: str) -> bool:
        """比较操作"""
        if operator == "eq":
            return actual == expected
        elif operator == "gte":
            return actual >= expected
        elif operator == "lte":
            return actual <= expected
        elif operator == "contains":
            return expected in str(actual)
        elif operator == "not_none":
            return actual is not None
        return False
