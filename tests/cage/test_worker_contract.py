from core.config.path_config import PathConfig

#!/usr/bin/env python3
"""
测试 Worker 契约验证器
"""

import sys
import os
import unittest

sys.path.insert(0, str(PathConfig.resolve().base_dir))
from core.cage_validator import CageValidator, ValidationResult


class TestWorkerContract(unittest.TestCase):
    """Worker 契约测试"""
    
    def setUp(self):
        self.validator = CageValidator()
        self.contract_path = str(PathConfig.resolve().base_dir / "cage" / "worker_researcher.yaml")
    
    def test_validate_valid_worker_contract(self):
        """测试有效的 Worker 契约"""
        result = self.validator.validate_worker_contract(self.contract_path)
        self.assertTrue(result.valid, f"Validation failed: {result.errors}")
    
    def test_missing_required_fields(self):
        """测试缺少必需字段"""
        import tempfile
        import yaml
        
        invalid_contract = {
            "worker": "researcher",
            # 缺少 domain, cage_version, interface, behavior, checks, data
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(invalid_contract, f)
            temp_path = f.name
        
        try:
            result = self.validator.validate_worker_contract(temp_path)
            self.assertFalse(result.valid)
            self.assertTrue(any("domain" in e for e in result.errors))
            self.assertTrue(any("checks" in e for e in result.errors))
        finally:
            os.unlink(temp_path)
    
    def test_invalid_worker_count(self):
        """测试无效的 worker count"""
        import tempfile
        import yaml
        
        invalid_contract = {
            "worker": "test_worker",
            "domain": "investment",
            "cage_version": "2.0",
            "roles": ["role1"],
            "interface": {
                "input": {"prompt": "test.md", "context": {"required": []}},
                "output": {"format": "json", "schema": {}}
            },
            "behavior": {
                "count": -1,  # 负数，无效
                "timeout": 300
            },
            "checks": {"pre_spawn": [], "post_complete": []},
            "data": {"blackboard": {"write": {"path": "test/"}, "read": []}}
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(invalid_contract, f)
            temp_path = f.name
        
        try:
            result = self.validator.validate_worker_contract(temp_path)
            self.assertFalse(result.valid)
            self.assertTrue(any("count" in e.lower() for e in result.errors))
        finally:
            os.unlink(temp_path)
    
    def test_empty_roles_list(self):
        """测试空的 roles 列表"""
        import tempfile
        import yaml
        
        invalid_contract = {
            "worker": "test_worker",
            "domain": "investment",
            "cage_version": "2.0",
            "roles": [],  # 空列表
            "interface": {"input": {}, "output": {}},
            "behavior": {"count": 1, "timeout": 300},
            "checks": {"pre_spawn": [], "post_complete": []},
            "data": {"blackboard": {"write": {"path": "test/"}, "read": []}}
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(invalid_contract, f)
            temp_path = f.name
        
        try:
            result = self.validator.validate_worker_contract(temp_path)
            self.assertFalse(result.valid)
            self.assertTrue(any("roles" in e.lower() for e in result.errors))
        finally:
            os.unlink(temp_path)
    
    def test_missing_blackboard_path(self):
        """测试缺少 blackboard write path"""
        import tempfile
        import yaml
        
        invalid_contract = {
            "worker": "test_worker",
            "domain": "investment",
            "cage_version": "2.0",
            "roles": ["role1"],
            "interface": {"input": {}, "output": {}},
            "behavior": {"count": 1, "timeout": 300},
            "checks": {"pre_spawn": [], "post_complete": []},
            "data": {
                "blackboard": {
                    "write": {},  # 缺少 path
                    "read": []
                }
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(invalid_contract, f)
            temp_path = f.name
        
        try:
            result = self.validator.validate_worker_contract(temp_path)
            self.assertFalse(result.valid)
            self.assertTrue(any("path" in e.lower() for e in result.errors))
        finally:
            os.unlink(temp_path)
    
    def test_invalid_checks_format(self):
        """测试无效的 checks 格式"""
        import tempfile
        import yaml
        
        invalid_contract = {
            "worker": "test_worker",
            "domain": "investment",
            "cage_version": "2.0",
            "roles": ["role1"],
            "interface": {"input": {}, "output": {}},
            "behavior": {"count": 1, "timeout": 300},
            "checks": {
                "pre_spawn": "not_a_list",  # 应该是列表
                "post_complete": []
            },
            "data": {"blackboard": {"write": {"path": "test/"}, "read": []}}
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(invalid_contract, f)
            temp_path = f.name
        
        try:
            result = self.validator.validate_worker_contract(temp_path)
            self.assertFalse(result.valid)
            self.assertTrue(any("pre_spawn" in e.lower() for e in result.errors))
        finally:
            os.unlink(temp_path)


if __name__ == "__main__":
    unittest.main()
