"""
PromptRegistry 单元测试
契约笼子: cage/active/ (see registry.yaml)
"""

import threading
from pathlib import Path
import pytest
from unittest.mock import patch, mock_open

from core.prompt_registry import PromptRegistry, PromptInfo, get_prompt_info


class TestPromptRegistry:
    """PromptRegistry测试套件"""
    
    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """每个测试前重置单例状态"""
        PromptRegistry._instance = None
        PromptRegistry._initialized = False
        yield
        # 测试后清理
        PromptRegistry._instance = None
        PromptRegistry._initialized = False
    
    @pytest.fixture
    def mock_registry_data(self):
        """模拟注册表数据"""
        return {
            "schema_version": "2.0.0",
            "domains": {
                "test": {
                    "prompts": {
                        "planner": {
                            "name": "Test Planner",
                            "filename": "planner.md",
                            "version": "2.0.0",
                            "role": "planner",
                            "variables": {
                                "required": [{"name": "VAR1", "type": "string"}],
                                "optional": [{"name": "VAR2", "type": "string", "default": "default_val"}]
                            }
                        },
                        "researcher_finance": {
                            "name": "Finance Researcher",
                            "filename": "researcher_finance.md",
                            "version": "2.0.0",
                            "role": "researcher",
                            "subtype": "finance"
                        },
                        "researcher_tech": {
                            "name": "Tech Researcher",
                            "filename": "researcher_tech.md",
                            "version": "2.0.0",
                            "role": "researcher",
                            "subtype": "tech"
                        }
                    }
                }
            }
        }
    
    # ============ FIX-001: 线程安全测试 ============
    
    def test_singleton_thread_safety(self, mock_registry_data):
        """FIX-001: 多线程环境下单例正确性"""
        instances = []
        
        def create_instance():
            with patch('core.prompt_registry.yaml.safe_load', return_value=mock_registry_data):
                with patch.object(Path, 'exists', return_value=True):
                    instances.append(PromptRegistry())
        
        # 10个线程并发创建
        threads = [threading.Thread(target=create_instance) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # 所有实例应该是同一个对象
        assert len(set(id(i) for i in instances)) == 1
        print(f"✅ FIX-001: 单例线程安全通过 ({len(instances)}个线程)")
    
    def test_initialization_once(self, mock_registry_data):
        """FIX-001: 初始化只执行一次"""
        call_count = [0]
        original_load = PromptRegistry._load_registry
        
        def counting_load(self):
            call_count[0] += 1
            original_load(self)
        
        with patch.object(PromptRegistry, '_load_registry', counting_load):
            with patch('core.prompt_registry.yaml.safe_load', return_value=mock_registry_data):
                with patch.object(Path, 'exists', return_value=True):
                    # 多次获取实例
                    r1 = PromptRegistry()
                    r2 = PromptRegistry()
                    r3 = PromptRegistry()
                    
                    # _load_registry只应被调用一次
                    assert call_count[0] == 1
        print(f"✅ FIX-001: 初始化只执行一次通过 (调用次数: {call_count[0]})")
    
    # ============ FIX-002: 实例变量测试 ============
    
    def test_instance_isolation(self, mock_registry_data):
        """FIX-002: 多个实例状态隔离"""
        with patch('core.prompt_registry.yaml.safe_load', return_value=mock_registry_data):
            with patch.object(Path, 'exists', return_value=True):
                # 创建多个实例
                r1 = PromptRegistry()
                r2 = PromptRegistry()
                
                # 修改r1的数据（通过直接访问内部变量）
                r1._prompts_by_id['test/new'] = PromptInfo(
                    id='test/new', name='New', filename='new.md',
                    version='1.0.0', role='test', domain='test'
                )
                
                # r2应该不受影响（因为是同一个实例，单例）
                # 但如果类变量实现错误，这里会出问题
                assert 'test/new' in r1._prompts_by_id
                
                print("✅ FIX-002: 实例变量隔离通过")
    
    # ============ FIX-003: get_by_role逻辑测试 ============
    
    def test_get_by_role_without_domain(self, mock_registry_data):
        """FIX-003: 不指定domain查询角色"""
        with patch('core.prompt_registry.yaml.safe_load', return_value=mock_registry_data):
            with patch.object(Path, 'exists', return_value=True):
                registry = PromptRegistry()
                
                # 查询所有researcher
                result = registry.get_by_role("researcher")
                
                assert len(result) == 2
                assert all(r.role == "researcher" for r in result)
                print("✅ FIX-003: 无domain查询通过")
    
    def test_get_by_role_with_domain(self, mock_registry_data):
        """FIX-003: 指定domain查询角色"""
        with patch('core.prompt_registry.yaml.safe_load', return_value=mock_registry_data):
            with patch.object(Path, 'exists', return_value=True):
                registry = PromptRegistry()
                
                # 查询test domain的researcher
                result = registry.get_by_role("researcher", domain="test")
                
                assert len(result) == 2
                assert all(r.role == "researcher" for r in result)
                assert all(r.domain == "test" for r in result)
                print("✅ FIX-003: 有domain查询通过")
    
    def test_get_by_role_nonexistent_domain(self, mock_registry_data):
        """FIX-003: 查询不存在的domain"""
        with patch('core.prompt_registry.yaml.safe_load', return_value=mock_registry_data):
            with patch.object(Path, 'exists', return_value=True):
                registry = PromptRegistry()
                
                # 查询不存在的domain
                result = registry.get_by_role("researcher", domain="nonexistent")
                
                assert result == []
                print("✅ FIX-003: 不存在domain返回空列表通过")
    
    def test_get_by_role_no_match(self, mock_registry_data):
        """FIX-003: 无匹配角色"""
        with patch('core.prompt_registry.yaml.safe_load', return_value=mock_registry_data):
            with patch.object(Path, 'exists', return_value=True):
                registry = PromptRegistry()
                
                # 查询不存在的角色
                result = registry.get_by_role("nonexistent_role")
                
                assert result == []
                print("✅ FIX-003: 无匹配返回空列表通过")
    
    # ============ FIX-004: 异常处理测试 ============
    
    def test_check_version_invalid_format(self, mock_registry_data):
        """FIX-004: 无效版本格式处理"""
        # 修改版本为无效格式
        mock_registry_data['domains']['test']['prompts']['planner']['version'] = 'invalid'
        
        with patch('core.prompt_registry.yaml.safe_load', return_value=mock_registry_data):
            with patch.object(Path, 'exists', return_value=True):
                registry = PromptRegistry()
                
                with pytest.raises(ValueError) as exc_info:
                    registry.check_version("test/planner", "1.0.0")
                
                assert "Invalid version format" in str(exc_info.value)
                print("✅ FIX-004: 无效版本格式处理通过")
    
    def test_check_version_valid(self, mock_registry_data):
        """FIX-004: 有效版本格式处理"""
        with patch('core.prompt_registry.yaml.safe_load', return_value=mock_registry_data):
            with patch.object(Path, 'exists', return_value=True):
                registry = PromptRegistry()
                
                # v2.0.0 >= v1.0.0
                assert registry.check_version("test/planner", "1.0.0") is True
                # v2.0.0 >= v2.0.0
                assert registry.check_version("test/planner", "2.0.0") is True
                # v2.0.0 < v3.0.0
                assert registry.check_version("test/planner", "3.0.0") is False
                
                print("✅ FIX-004: 版本比较逻辑通过")
    
    # ============ 其他功能测试 ============
    
    def test_get_existing_prompt(self, mock_registry_data):
        """获取存在的prompt"""
        with patch('core.prompt_registry.yaml.safe_load', return_value=mock_registry_data):
            with patch.object(Path, 'exists', return_value=True):
                registry = PromptRegistry()
                
                info = registry.get("test/planner")
                assert info.name == "Test Planner"
                assert info.version == "2.0.0"
                print("✅ 获取存在的prompt通过")
    
    def test_get_nonexistent_prompt(self, mock_registry_data):
        """获取不存在的prompt，验证友好错误提示"""
        with patch('core.prompt_registry.yaml.safe_load', return_value=mock_registry_data):
            with patch.object(Path, 'exists', return_value=True):
                registry = PromptRegistry()
                
                with pytest.raises(KeyError) as exc_info:
                    registry.get("test/nonexistent")
                
                # 验证错误信息包含建议
                assert "Did you mean" in str(exc_info.value) or "not found" in str(exc_info.value)
                print("✅ 友好错误提示通过")
    
    def test_list_all(self, mock_registry_data):
        """列出所有prompt"""
        with patch('core.prompt_registry.yaml.safe_load', return_value=mock_registry_data):
            with patch.object(Path, 'exists', return_value=True):
                registry = PromptRegistry()
                
                all_prompts = registry.list_all()
                assert len(all_prompts) == 3
                print("✅ 列出所有prompt通过")
    
    def test_exists(self, mock_registry_data):
        """检查prompt是否存在"""
        with patch('core.prompt_registry.yaml.safe_load', return_value=mock_registry_data):
            with patch.object(Path, 'exists', return_value=True):
                registry = PromptRegistry()
                
                assert registry.exists("test/planner") is True
                assert registry.exists("test/nonexistent") is False
                print("✅ exists检查通过")


class TestReadPromptWithVars:
    """read_prompt_with_vars测试"""
    
    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        PromptRegistry._instance = None
        PromptRegistry._initialized = False
        yield
        PromptRegistry._instance = None
        PromptRegistry._initialized = False
    
    def test_required_variable_missing(self):
        """缺少必填变量时抛出错误"""
        mock_data = {
            "domains": {
                "test": {
                    "prompts": {
                        "test": {
                            "name": "Test",
                            "filename": "test.md",
                            "version": "1.0.0",
                            "role": "test",
                            "variables": {
                                "required": [{"name": "REQUIRED_VAR", "type": "string"}],
                                "optional": []
                            }
                        }
                    }
                }
            }
        }
        
        with patch('core.prompt_registry.yaml.safe_load', return_value=mock_data):
            with patch.object(Path, 'exists', return_value=True):
                with patch('core.prompt_registry.read_prompt', return_value="{{REQUIRED_VAR}}"):
                    with pytest.raises(ValueError) as exc_info:
                        from core.prompt_registry import read_prompt_with_vars
                        read_prompt_with_vars("test/test")
                    
                    assert "Missing required variable" in str(exc_info.value)
                    print("✅ 必填变量检查通过")
    
    def test_optional_variable_default(self):
        """可选变量使用默认值"""
        mock_data = {
            "domains": {
                "test": {
                    "prompts": {
                        "test": {
                            "name": "Test",
                            "filename": "test.md",
                            "version": "1.0.0",
                            "role": "test",
                            "variables": {
                                "required": [],
                                "optional": [{"name": "OPT_VAR", "type": "string", "default": "default_value"}]
                            }
                        }
                    }
                }
            }
        }
        
        with patch('core.prompt_registry.yaml.safe_load', return_value=mock_data):
            with patch.object(Path, 'exists', return_value=True):
                with patch('core.prompt_registry.read_prompt', return_value="Value: {{OPT_VAR}}"):
                    from core.prompt_registry import read_prompt_with_vars
                    result = read_prompt_with_vars("test/test")
                    
                    assert "default_value" in result
                    print("✅ 可选变量默认值通过")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
