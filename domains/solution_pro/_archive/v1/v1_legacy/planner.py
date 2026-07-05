"""
Planner Pro Agent，从配置动态读取 stages

Version: 2.1.0
Author: DeepFlow Solution Pro
Date: 2026-06-01
"""

"""
V1-LEGACY: This file is part of V1 pipeline (10-stage architecture).
V2 uses MasterOrchestrator + PlanningOrchestrator + ResearchOrchestrator + ReviewQCOrchestrator.
Do not import this file for new V2 workflows.
"""

#!/usr/bin/env python3
"""Planner Pro Agent - Prompt驱动极简版"""
import sys as _sys; _p=__import__('pathlib').Path(__file__).resolve(); _r=next((d for d in _p.parents if (d/'core'/'blackboard').is_dir()),None); _sys.path.insert(0,str(_r)) if _r and str(_r) not in _sys.path else None  # 契约笼子: 自动发现 .deepflow 根目录
import json
import re
from typing import Dict, Any

from domains.solution_pro.blackboard import PIPELINE_STAGES, STAGE_PATH_REGISTRY


class PlannerProAgent:
    """只负责解析和保存LLM输出"""
    
    def __init__(self, blackboard):
        self.blackboard = blackboard
    
    def _extract_json(self, text: str) -> str:
        """从LLM输出中提取纯JSON"""
        # 尝试提取```json代码块
        json_block_pattern = r'```(?:json)?\s*([\s\S]*?)\s*```'
        matches = re.findall(json_block_pattern, text)
        if matches:
            return matches[0].strip()
        
        # 尝试提取第一个{...}对象
        json_object_pattern = r'\{[\s\S]*\}'
        matches = re.findall(json_object_pattern, text)
        if matches:
            return matches[0].strip()
        
        # 直接返回（假设已经是纯JSON）
        return text.strip()
    
    def _validate_structure(self, plan: Dict) -> None:
        """验证plan结构完整性"""
        # 验证plan.plan.stages
        if "plan" not in plan:
            raise ValueError("Missing 'plan' field")
        if "stages" not in plan["plan"]:
            raise ValueError("Missing 'plan.stages' field")
        if not isinstance(plan["plan"]["stages"], list):
            raise ValueError("'plan.stages' must be a list")
        expected_stage_count = len(PIPELINE_STAGES)
        if len(plan["plan"]["stages"]) != expected_stage_count:
            import warnings
            warnings.warn(
                f"Expected {expected_stage_count} stages, got {len(plan['plan']['stages'])}. "
                "Please check config/solution.yaml for current pipeline definition.",
                RuntimeWarning
            )
        
        # 验证每个stage
        for i, stage in enumerate(plan["plan"]["stages"]):
            required = ["stage", "name", "parallel", "timeout", "agents"]
            for field in required:
                if field not in stage:
                    raise ValueError(f"Stage {i} missing field: {field}")
            if not isinstance(stage["agents"], list):
                raise ValueError(f"Stage {i} 'agents' must be a list")
            
            # 验证字段类型
            if not isinstance(stage["parallel"], bool):
                raise ValueError(f"Stage {i} 'parallel' must be boolean (true/false)")
            if not isinstance(stage["timeout"], (int, float)):
                raise ValueError(f"Stage {i} 'timeout' must be a number (seconds)")
            if not isinstance(stage["stage"], int):
                raise ValueError(f"Stage {i} 'stage' must be an integer (not stage_number)")
    
    def save_plan(self, llm_output: str) -> Dict[str, Any]:
        """解析LLM输出并保存到Blackboard"""
        try:
            # 提取JSON（处理Markdown代码块）
            json_str = self._extract_json(llm_output)
            plan = json.loads(json_str)
            
            # 基础字段验证
            for field in ["role", "session_id", "plan", "key_areas"]:
                if field not in plan:
                    raise ValueError(f"Missing: {field}")
            
            # 验证 key_areas 字段名（必须是 area，不是 name）
            for i, area in enumerate(plan.get("key_areas", [])):
                if "area" not in area:
                    raise ValueError(f"key_areas[{i}] missing 'area' field (use 'area', not 'name')")
                if "name" in area and "area" not in area:
                    raise ValueError(f"key_areas[{i}] uses 'name' instead of 'area' - this is incorrect")
            
            # 结构验证（新增）
            self._validate_structure(plan)
            
            # 验证Agent数量（动态读取配置，不再硬编码）
            total = sum(len(s.get("agents", [])) for s in plan["plan"]["stages"])
            if total < 5:
                import warnings
                warnings.warn(
                    f"Only {total} agents defined (expected >= 5). "
                    "Check config/solution.yaml pipeline.agents.",
                    RuntimeWarning
                )
            
            # 验证权重总和≈1.0
            w = sum(a.get("weight", 0) for a in plan["key_areas"])
            if abs(w - 1.0) > 0.01:
                raise ValueError(f"Weight sum={w}, expected 1.0")
            
            # 验证 estimated_duration 格式（必须是 "数字+min"，如 "58min"）
            est_duration = plan.get("plan", {}).get("estimated_duration", "")
            if not re.match(r'^\d+min$', est_duration):
                raise ValueError(
                    f"estimated_duration format error: '{est_duration}' "
                    f"(expected format: '数字+min', e.g., '58min', not '6个月' or '58分钟')"
                )
            
            self.blackboard.write(STAGE_PATH_REGISTRY["planning"], plan)
            return {"status": "success", "plan": plan, "total_agents": total}
        except (json.JSONDecodeError, ValueError) as e:
            return {"status": "failed", "error": str(e), "raw_output": llm_output[:500]}
        except Exception as e:
            return {"status": "failed", "error": str(e), "raw_output": llm_output[:500]}
