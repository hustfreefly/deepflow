#!/usr/bin/env python3
"""
DeepFlow V2.0 - 笼子契约验证器
验证领域契约、阶段契约、Worker 契约和收敛规则是否符合规范
"""

import os
import sys
import json
import yaml
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple

sys.path.insert(0, '/Users/allen/.openclaw/workspace/.deepflow/')


# ============================================================================
# 验证结果定义
# ============================================================================

@dataclass
class ValidationResult:
    """验证结果"""
    valid: bool = True
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    
    def add_error(self, msg: str):
        self.errors.append(msg)
        self.valid = False
    
    def add_warning(self, msg: str):
        self.warnings.append(msg)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "valid": self.valid,
            "errors": self.errors,
            "warnings": self.warnings
        }
    
    def __str__(self) -> str:
        if self.valid:
            status = "✅ VALID"
        else:
            status = f"❌ INVALID ({len(self.errors)} errors)"
        
        lines = [status]
        if self.errors:
            lines.append("Errors:")
            for e in self.errors:
                lines.append(f"  - {e}")
        if self.warnings:
            lines.append("Warnings:")
            for w in self.warnings:
                lines.append(f"  ⚠️ {w}")
        
        return "\n".join(lines)


# ============================================================================
# JSON Schema 验证器（简化版）
# ============================================================================

class SimpleSchemaValidator:
    """简化的 JSON Schema 验证器（不依赖外部库）"""
    
    @staticmethod
    def validate(data: Any, schema: Dict[str, Any], path: str = "$") -> List[str]:
        """
        验证数据是否符合 schema
        
        Returns:
            错误列表
        """
        errors = []
        
        # 检查类型
        if "type" in schema:
            type_errors = SimpleSchemaValidator._check_type(data, schema["type"], path)
            errors.extend(type_errors)
            if type_errors:
                return errors  # 类型不对，不再检查其他
        
        # 检查 required
        if schema.get("type") == "object" and "required" in schema:
            if isinstance(data, dict):
                for req_field in schema["required"]:
                    if req_field not in data:
                        errors.append(f"{path}: missing required field '{req_field}'")
        
        # 检查 properties
        if schema.get("type") == "object" and "properties" in schema:
            if isinstance(data, dict):
                for prop_name, prop_schema in schema["properties"].items():
                    if prop_name in data:
                        prop_errors = SimpleSchemaValidator.validate(
                            data[prop_name], prop_schema, f"{path}.{prop_name}"
                        )
                        errors.extend(prop_errors)
        
        # 检查 enum
        if "enum" in schema:
            if data not in schema["enum"]:
                errors.append(f"{path}: value '{data}' not in enum {schema['enum']}")
        
        # 检查 minimum/maximum
        if isinstance(data, (int, float)):
            if "minimum" in schema and data < schema["minimum"]:
                errors.append(f"{path}: value {data} < minimum {schema['minimum']}")
            if "maximum" in schema and data > schema["maximum"]:
                errors.append(f"{path}: value {data} > maximum {schema['maximum']}")
        
        # 检查 minLength/maxLength
        if isinstance(data, str):
            if "minLength" in schema and len(data) < schema["minLength"]:
                errors.append(f"{path}: length {len(data)} < minLength {schema['minLength']}")
            if "maxLength" in schema and len(data) > schema["maxLength"]:
                errors.append(f"{path}: length {len(data)} > maxLength {schema['maxLength']}")
        
        # 检查 pattern
        if isinstance(data, str) and "pattern" in schema:
            import re
            if not re.match(schema["pattern"], data):
                errors.append(f"{path}: value '{data}' doesn't match pattern '{schema['pattern']}'")
        
        return errors
    
    @staticmethod
    def _check_type(data: Any, expected_type: str, path: str) -> List[str]:
        """检查数据类型"""
        type_map = {
            "string": str,
            "integer": int,
            "number": (int, float),
            "boolean": bool,
            "array": list,
            "object": dict,
        }
        
        expected_python_type = type_map.get(expected_type)
        if expected_python_type and not isinstance(data, expected_python_type):
            # 特殊处理：integer 也接受 float（如果是整数）
            if expected_type == "integer" and isinstance(data, float) and data.is_integer():
                return []
            return [f"{path}: expected type '{expected_type}', got '{type(data).__name__}'"]
        
        return []


# ============================================================================
# 笼子契约验证器
# ============================================================================

class CageValidator:
    """
    笼子契约验证器
    
    验证以下契约文件：
    - 领域契约 (domain_*.yaml)
    - 阶段契约 (stage_*.yaml)
    - Worker 契约 (worker_*.yaml)
    - 收敛规则 (convergence_rules.yaml)
    """
    
    def __init__(self, cage_dir: str = None):
        self.cage_dir = Path(cage_dir or "/Users/allen/.openclaw/workspace/.deepflow/cage")
        self.schema_validator = SimpleSchemaValidator()
    
    def validate_domain_contract(self, path: str) -> ValidationResult:
        """
        验证领域契约
        
        Args:
            path: 契约文件路径
            
        Returns:
            ValidationResult
        """
        result = ValidationResult()
        
        try:
            with open(path, 'r', encoding='utf-8') as f:
                contract = yaml.safe_load(f)
        except Exception as e:
            result.add_error(f"Failed to load file: {e}")
            return result
        
        # 检查必需字段
        required_top_level = ["cage_version", "domain", "interface", "behavior", "data"]
        for field in required_top_level:
            if field not in contract:
                result.add_error(f"Missing required top-level field: '{field}'")
        
        if not result.valid:
            return result
        
        # 验证 interface.input.schema
        if "interface" in contract and "input" in contract["interface"]:
            input_schema = contract["interface"]["input"].get("schema", {})
            if input_schema:
                # 这里可以添加更详细的 schema 验证
                pass
        
        # 验证 behavior.stages
        if "behavior" in contract and "stages" in contract["behavior"]:
            stages = contract["behavior"]["stages"]
            if "required_order" in stages:
                if not isinstance(stages["required_order"], list):
                    result.add_error("behavior.stages.required_order must be a list")
                elif len(stages["required_order"]) == 0:
                    result.add_warning("behavior.stages.required_order is empty")
        
        # 验证 convergence 规则
        if "behavior" in contract and "convergence" in contract["behavior"]:
            conv = contract["behavior"]["convergence"]
            if "min_iterations" in conv and "max_iterations" in conv:
                if conv["min_iterations"] > conv["max_iterations"]:
                    result.add_error(
                        f"min_iterations ({conv['min_iterations']}) > max_iterations ({conv['max_iterations']})"
                    )
            if "target_score" in conv:
                if not (0 <= conv["target_score"] <= 1):
                    result.add_error(f"target_score must be between 0 and 1, got {conv['target_score']}")
        
        # 验证 data.blackboard.required_files
        if "data" in contract and "blackboard" in contract["data"]:
            bb = contract["data"]["blackboard"]
            if "required_files" in bb:
                if not isinstance(bb["required_files"], list):
                    result.add_error("data.blackboard.required_files must be a list")
        
        return result
    
    def validate_stage_contract(self, path: str) -> ValidationResult:
        """
        验证阶段契约
        
        Args:
            path: 契约文件路径
            
        Returns:
            ValidationResult
        """
        result = ValidationResult()
        
        try:
            with open(path, 'r', encoding='utf-8') as f:
                contract = yaml.safe_load(f)
        except Exception as e:
            result.add_error(f"Failed to load file: {e}")
            return result
        
        # 检查必需字段
        required_top_level = ["stage", "domain", "cage_version", "interface", "behavior", "data"]
        for field in required_top_level:
            if field not in contract:
                result.add_error(f"Missing required top-level field: '{field}'")
        
        if not result.valid:
            return result
        
        # 验证 stage 名称格式
        stage_name = contract.get("stage", "")
        if not stage_name or not isinstance(stage_name, str):
            result.add_error("stage name must be a non-empty string")
        
        # 验证 interface.output.assertions
        if "interface" in contract and "output" in contract["interface"]:
            output = contract["interface"]["output"]
            if "assertions" in output:
                if not isinstance(output["assertions"], list):
                    result.add_error("interface.output.assertions must be a list")
                else:
                    for i, assertion in enumerate(output["assertions"]):
                        if not isinstance(assertion, str):
                            result.add_error(f"assertion[{i}] must be a string")
        
        # 验证 behavior.timeout
        if "behavior" in contract and "timeout" in contract["behavior"]:
            timeout = contract["behavior"]["timeout"]
            if not isinstance(timeout, (int, float)) or timeout <= 0:
                result.add_error(f"behavior.timeout must be a positive number, got {timeout}")
        
        # 验证 data.validation
        if "data" in contract and "validation" in contract["data"]:
            validations = contract["data"]["validation"]
            if not isinstance(validations, list):
                result.add_error("data.validation must be a list")
        
        return result
    
    def validate_worker_contract(self, path: str) -> ValidationResult:
        """
        验证 Worker 契约
        
        Args:
            path: 契约文件路径
            
        Returns:
            ValidationResult
        """
        result = ValidationResult()
        
        try:
            with open(path, 'r', encoding='utf-8') as f:
                contract = yaml.safe_load(f)
        except Exception as e:
            result.add_error(f"Failed to load file: {e}")
            return result
        
        # 检查必需字段
        required_top_level = ["worker", "domain", "cage_version", "interface", "behavior", "checks", "data"]
        for field in required_top_level:
            if field not in contract:
                result.add_error(f"Missing required top-level field: '{field}'")
        
        if not result.valid:
            return result
        
        # 验证 worker 名称
        worker_name = contract.get("worker", "")
        if not worker_name or not isinstance(worker_name, str):
            result.add_error("worker name must be a non-empty string")
        
        # 验证 roles
        if "roles" in contract:
            roles = contract["roles"]
            if not isinstance(roles, list) or len(roles) == 0:
                result.add_error("roles must be a non-empty list")
        
        # 验证 behavior.count
        if "behavior" in contract and "count" in contract["behavior"]:
            count = contract["behavior"]["count"]
            if not isinstance(count, int) or count <= 0:
                result.add_error(f"behavior.count must be a positive integer, got {count}")
        
        # 验证 behavior.timeout
        if "behavior" in contract and "timeout" in contract["behavior"]:
            timeout = contract["behavior"]["timeout"]
            if not isinstance(timeout, (int, float)) or timeout <= 0:
                result.add_error(f"behavior.timeout must be a positive number, got {timeout}")
        
        # 验证 checks.pre_spawn
        if "checks" in contract:
            checks = contract["checks"]
            if "pre_spawn" in checks:
                if not isinstance(checks["pre_spawn"], list):
                    result.add_error("checks.pre_spawn must be a list")
            if "post_complete" in checks:
                if not isinstance(checks["post_complete"], list):
                    result.add_error("checks.post_complete must be a list")
        
        # 验证 data.blackboard.write/read
        if "data" in contract and "blackboard" in contract["data"]:
            bb = contract["data"]["blackboard"]
            if "write" in bb:
                if "path" not in bb["write"]:
                    result.add_error("data.blackboard.write must have 'path'")
            if "read" in bb:
                if not isinstance(bb["read"], list):
                    result.add_error("data.blackboard.read must be a list")
        
        return result
    
    def validate_convergence_rules(self, path: str) -> ValidationResult:
        """
        验证收敛规则契约
        
        Args:
            path: 契约文件路径
            
        Returns:
            ValidationResult
        """
        result = ValidationResult()
        
        try:
            with open(path, 'r', encoding='utf-8') as f:
                contract = yaml.safe_load(f)
        except Exception as e:
            result.add_error(f"Failed to load file: {e}")
            return result
        
        # 检查必需字段
        required_top_level = ["domain", "cage_version", "rules"]
        for field in required_top_level:
            if field not in contract:
                result.add_error(f"Missing required top-level field: '{field}'")
        
        if not result.valid:
            return result
        
        # 验证 rules
        rules = contract.get("rules", {})
        
        # 检查 min_iterations
        if "min_iterations" in rules:
            rule = rules["min_iterations"]
            if "value" not in rule:
                result.add_error("rules.min_iterations must have 'value'")
            elif not isinstance(rule["value"], int) or rule["value"] <= 0:
                result.add_error(f"rules.min_iterations.value must be a positive integer, got {rule['value']}")
        
        # 检查 max_iterations
        if "max_iterations" in rules:
            rule = rules["max_iterations"]
            if "value" not in rule:
                result.add_error("rules.max_iterations must have 'value'")
            elif not isinstance(rule["value"], int) or rule["value"] <= 0:
                result.add_error(f"rules.max_iterations.value must be a positive integer, got {rule['value']}")
        
        # 检查 min < max
        if "min_iterations" in rules and "max_iterations" in rules:
            min_val = rules["min_iterations"].get("value", 0)
            max_val = rules["max_iterations"].get("value", 0)
            if min_val > max_val:
                result.add_error(
                    f"min_iterations ({min_val}) > max_iterations ({max_val})"
                )
        
        # 检查 target_score
        if "target_score" in rules:
            rule = rules["target_score"]
            if "value" not in rule:
                result.add_error("rules.target_score must have 'value'")
            elif not (0 <= rule["value"] <= 1):
                result.add_error(f"rules.target_score.value must be between 0 and 1, got {rule['value']}")
        
        # 检查 high_score
        if "high_score" in rules:
            rule = rules["high_score"]
            if "threshold" not in rule:
                result.add_error("rules.high_score must have 'threshold'")
            elif not (0 <= rule["threshold"] <= 1):
                result.add_error(f"rules.high_score.threshold must be between 0 and 1, got {rule['threshold']}")
        
        # 验证 output.schema
        if "output" in contract and "schema" in contract["output"]:
            schema = contract["output"]["schema"]
            if "required" in schema:
                if not isinstance(schema["required"], list):
                    result.add_error("output.schema.required must be a list")
        
        return result
    
    def validate_all(self) -> Dict[str, ValidationResult]:
        """
        验证所有契约文件
        
        Returns:
            {文件名: ValidationResult}
        """
        results = {}
        
        # 查找所有契约文件
        cage_files = list(self.cage_dir.glob("*.yaml"))
        
        for cage_file in cage_files:
            filename = cage_file.name
            
            if filename.startswith("domain_"):
                results[filename] = self.validate_domain_contract(str(cage_file))
            elif filename.startswith("stage_"):
                results[filename] = self.validate_stage_contract(str(cage_file))
            elif filename.startswith("worker_"):
                results[filename] = self.validate_worker_contract(str(cage_file))
            elif filename == "convergence_rules.yaml":
                results[filename] = self.validate_convergence_rules(str(cage_file))
        
        return results


# ============================================================================
# 工具函数
# ============================================================================

def print_validation_report(results: Dict[str, ValidationResult]):
    """打印验证报告"""
    print("\n" + "="*60)
    print("CAGE CONTRACT VALIDATION REPORT")
    print("="*60 + "\n")
    
    all_valid = True
    for filename, result in sorted(results.items()):
        print(f"📄 {filename}")
        print(result)
        print()
        if not result.valid:
            all_valid = False
    
    print("="*60)
    if all_valid:
        print("✅ ALL CONTRACTS VALID")
    else:
        print("❌ SOME CONTRACTS HAVE ERRORS")
    print("="*60 + "\n")


# ============================================================================
# 入口函数
# ============================================================================

if __name__ == "__main__":
    validator = CageValidator()
    results = validator.validate_all()
    print_validation_report(results)
    
    # 退出码：有错误则返回 1
    has_errors = any(not r.valid for r in results.values())
    sys.exit(1 if has_errors else 0)
