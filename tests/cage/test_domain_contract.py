from core.config.path_config import PathConfig

#!/usr/bin/env python3
"""
测试领域契约验证器
"""

import sys
import os
import unittest

sys.path.insert(0, str(PathConfig.resolve().base_dir))
from core.cage_validator import CageValidator, ValidationResult


class TestDomainContract(unittest.TestCase):
    """领域契约测试"""
    
    def setUp(self):
        self.validator = CageValidator()
        self.contract_path = str(PathConfig.resolve().base_dir / "cage" / "domain_investment.yaml")
    
    def test_validate_valid_domain_contract(self):
        """测试有效的领域契约"""
        result = self.validator.validate_domain_contract(self.contract_path)
        self.assertTrue(result.valid, f"Validation failed: {result.errors}")
    
    def test_missing_required_fields(self):
        """测试缺少必需字段"""
        # 创建一个临时无效契约文件
        import tempfile
        import yaml
        
        invalid_contract = {
            "cage_version": "2.0",
            "domain": "investment",
            # 缺少 interface, behavior, data
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(invalid_contract, f)
            temp_path = f.name
        
        try:
            result = self.validator.validate_domain_contract(temp_path)
            self.assertFalse(result.valid)
            self.assertTrue(any("interface" in e for e in result.errors))
            self.assertTrue(any("behavior" in e for e in result.errors))
            self.assertTrue(any("data" in e for e in result.errors))
        finally:
            os.unlink(temp_path)
    
    def test_invalid_convergence_config(self):
        """测试无效的收敛配置"""
        import tempfile
        import yaml
        
        invalid_contract = {
            "cage_version": "2.0",
            "domain": "test",
            "interface": {"input": {}, "output": {}},
            "behavior": {
                "stages": {"required_order": []},
                "convergence": {
                    "min_iterations": 5,
                    "max_iterations": 3,  # min > max，无效
                    "target_score": 1.5,  # > 1，无效
                }
            },
            "data": {"blackboard": {"required_files": []}}
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(invalid_contract, f)
            temp_path = f.name
        
        try:
            result = self.validator.validate_domain_contract(temp_path)
            self.assertFalse(result.valid)
            # 检查是否检测到 min > max
            self.assertTrue(any("min_iterations" in e and "max_iterations" in e for e in result.errors))
            # 检查是否检测到 target_score > 1
            self.assertTrue(any("target_score" in e for e in result.errors))
        finally:
            os.unlink(temp_path)
    
    def test_empty_required_order_warning(self):
        """测试空的 required_order 产生警告"""
        import tempfile
        import yaml
        
        contract = {
            "cage_version": "2.0",
            "domain": "test",
            "interface": {"input": {}, "output": {}},
            "behavior": {
                "stages": {"required_order": []},  # 空列表
                "convergence": {"min_iterations": 2, "max_iterations": 10}
            },
            "data": {"blackboard": {"required_files": []}}
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(contract, f)
            temp_path = f.name
        
        try:
            result = self.validator.validate_domain_contract(temp_path)
            self.assertTrue(result.valid)  # 仍然是有效的，只是有警告
            self.assertTrue(any("empty" in w.lower() for w in result.warnings))
        finally:
            os.unlink(temp_path)
    
    def test_file_not_found(self):
        """测试文件不存在"""
        result = self.validator.validate_domain_contract("/nonexistent/path.yaml")
        self.assertFalse(result.valid)
        self.assertTrue(any("Failed to load" in e for e in result.errors))


if __name__ == "__main__":
    unittest.main()
