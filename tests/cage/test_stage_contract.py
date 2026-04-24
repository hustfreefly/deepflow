#!/usr/bin/env python3
"""
测试阶段契约验证器
"""

import sys
import os
import unittest

sys.path.insert(0, '/Users/allen/.openclaw/workspace/.deepflow/')
from core.cage_validator import CageValidator, ValidationResult


class TestStageContract(unittest.TestCase):
    """阶段契约测试"""
    
    def setUp(self):
        self.validator = CageValidator()
        self.contract_path = "/Users/allen/.openclaw/workspace/.deepflow/cage/stage_data_collection.yaml"
    
    def test_validate_valid_stage_contract(self):
        """测试有效的阶段契约"""
        result = self.validator.validate_stage_contract(self.contract_path)
        self.assertTrue(result.valid, f"Validation failed: {result.errors}")
    
    def test_missing_required_fields(self):
        """测试缺少必需字段"""
        import tempfile
        import yaml
        
        invalid_contract = {
            "stage": "data_collection",
            # 缺少 domain, cage_version, interface, behavior, data
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(invalid_contract, f)
            temp_path = f.name
        
        try:
            result = self.validator.validate_stage_contract(temp_path)
            self.assertFalse(result.valid)
            self.assertTrue(any("domain" in e for e in result.errors))
            self.assertTrue(any("cage_version" in e for e in result.errors))
        finally:
            os.unlink(temp_path)
    
    def test_invalid_timeout(self):
        """测试无效的 timeout"""
        import tempfile
        import yaml
        
        invalid_contract = {
            "stage": "test_stage",
            "domain": "investment",
            "cage_version": "2.0",
            "interface": {
                "input": {"context": {"required": ["code", "name"]}},
                "output": {"schema": {}, "assertions": []}
            },
            "behavior": {
                "timeout": -10,  # 负数，无效
                "retry": {"max_attempts": 2}
            },
            "data": {
                "output_path": "blackboard/{session_id}/data/",
                "validation": []
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(invalid_contract, f)
            temp_path = f.name
        
        try:
            result = self.validator.validate_stage_contract(temp_path)
            self.assertFalse(result.valid)
            self.assertTrue(any("timeout" in e.lower() for e in result.errors))
        finally:
            os.unlink(temp_path)
    
    def test_invalid_assertions_format(self):
        """测试无效的 assertions 格式"""
        import tempfile
        import yaml
        
        invalid_contract = {
            "stage": "test_stage",
            "domain": "investment",
            "cage_version": "2.0",
            "interface": {
                "input": {"context": {"required": ["code"]}},
                "output": {
                    "schema": {},
                    "assertions": "not_a_list"  # 应该是列表
                }
            },
            "behavior": {"timeout": 120},
            "data": {"output_path": "test/", "validation": []}
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(invalid_contract, f)
            temp_path = f.name
        
        try:
            result = self.validator.validate_stage_contract(temp_path)
            self.assertFalse(result.valid)
            self.assertTrue(any("assertions" in e.lower() for e in result.errors))
        finally:
            os.unlink(temp_path)
    
    def test_empty_stage_name(self):
        """测试空的 stage 名称"""
        import tempfile
        import yaml
        
        invalid_contract = {
            "stage": "",  # 空字符串
            "domain": "investment",
            "cage_version": "2.0",
            "interface": {"input": {}, "output": {}},
            "behavior": {"timeout": 120},
            "data": {"output_path": "test/", "validation": []}
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(invalid_contract, f)
            temp_path = f.name
        
        try:
            result = self.validator.validate_stage_contract(temp_path)
            self.assertFalse(result.valid)
            self.assertTrue(any("stage name" in e.lower() for e in result.errors))
        finally:
            os.unlink(temp_path)


if __name__ == "__main__":
    unittest.main()
