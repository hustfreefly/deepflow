"""
过渡引导词单元测试

测试内容：
1. Pydantic 模型验证（TransitionPrompt, TransitionPromptVariables）
2. 渲染逻辑（三个模板：spec_to_solution, solution_to_ship, ship_completed）
3. 边界情况（缺失字段、无效值）
"""

import sys
from pathlib import Path

# 添加 .deepflow 到 sys.path
deepflow_root = Path(__file__).resolve().parent.parent
if str(deepflow_root) not in sys.path:
    sys.path.insert(0, str(deepflow_root))

import pytest
from pydantic import ValidationError

from domains.spec_pro.contracts.transition_prompt import (
    TransitionPrompt,
    TransitionPromptVariables,
    validate_transition_prompt,
)
from scripts.render_transition_prompt import render_transition_prompt


class TestTransitionPromptVariables:
    """测试 TransitionPromptVariables 模型"""
    
    def test_valid_spec_to_solution_variables(self):
        """测试 Spec Pro → Solution Pro 变量"""
        variables = TransitionPromptVariables(
            quality_score=82,
            quality_level="A",
            num_users=3,
            num_capabilities=8,
            num_constraints=5
        )
        assert variables.quality_score == 82
        assert variables.quality_level == "A"
        assert variables.num_users == 3
        assert variables.num_capabilities == 8
        assert variables.num_constraints == 5
    
    def test_valid_solution_to_ship_variables(self):
        """测试 Solution Pro → Ship Pro 变量"""
        variables = TransitionPromptVariables(
            harness_score=92,
            num_reqs=12,
            num_modules=5
        )
        assert variables.harness_score == 92
        assert variables.num_reqs == 12
        assert variables.num_modules == 5
    
    def test_valid_ship_completed_variables(self):
        """测试 Ship Pro 完成变量"""
        variables = TransitionPromptVariables(harness_score=88)
        assert variables.harness_score == 88
    
    def test_all_fields_optional(self):
        """测试所有字段可选"""
        variables = TransitionPromptVariables()
        assert variables.quality_score is None
        assert variables.quality_level is None
        assert variables.num_users is None
    
    def test_invalid_quality_level(self):
        """测试无效的 quality_level"""
        with pytest.raises(ValidationError):
            TransitionPromptVariables(quality_level="X")  # 必须是 S/A/B/C
    
    def test_negative_num_users(self):
        """测试负数的 num_users"""
        with pytest.raises(ValidationError):
            TransitionPromptVariables(num_users=-1)  # ge=0
    
    def test_extra_fields_allowed(self):
        """测试允许额外字段"""
        variables = TransitionPromptVariables(
            quality_score=82,
            extra_field="test"
        )
        assert variables.quality_score == 82


class TestTransitionPrompt:
    """测试 TransitionPrompt 模型"""
    
    def test_valid_spec_to_solution(self):
        """测试有效的 spec_to_solution"""
        prompt = TransitionPrompt(
            template="spec_to_solution",
            variables=TransitionPromptVariables(
                quality_score=82,
                quality_level="A",
                num_users=3,
                num_capabilities=8,
                num_constraints=5
            )
        )
        assert prompt.template == "spec_to_solution"
        assert prompt.variables.quality_score == 82
    
    def test_valid_solution_to_ship(self):
        """测试有效的 solution_to_ship"""
        prompt = TransitionPrompt(
            template="solution_to_ship",
            variables=TransitionPromptVariables(
                harness_score=92,
                num_reqs=12,
                num_modules=5
            )
        )
        assert prompt.template == "solution_to_ship"
        assert prompt.variables.harness_score == 92
    
    def test_valid_ship_completed(self):
        """测试有效的 ship_completed"""
        prompt = TransitionPrompt(
            template="ship_completed",
            variables=TransitionPromptVariables(harness_score=88)
        )
        assert prompt.template == "ship_completed"
        assert prompt.variables.harness_score == 88
    
    def test_invalid_template(self):
        """测试无效的 template"""
        with pytest.raises(ValidationError):
            TransitionPrompt(
                template="invalid_template",  # 必须是三个有效值之一
                variables=TransitionPromptVariables()
            )
    
    def test_validate_transition_prompt_function(self):
        """测试 validate_transition_prompt 函数"""
        data = {
            "template": "spec_to_solution",
            "variables": {
                "quality_score": 82,
                "quality_level": "A",
                "num_users": 3
            }
        }
        prompt = validate_transition_prompt(data)
        assert prompt.template == "spec_to_solution"
        assert prompt.variables.quality_score == 82
    
    def test_validate_transition_prompt_invalid(self):
        """测试 validate_transition_prompt 函数（无效数据）"""
        data = {
            "template": "invalid",
            "variables": {}
        }
        with pytest.raises(ValidationError):
            validate_transition_prompt(data)


class TestRenderTransitionPrompt:
    """测试渲染逻辑"""
    
    def test_spec_to_solution_high_quality(self):
        """测试 Spec Pro → Solution Pro（高质量 S/A 级）"""
        data = {
            "template": "spec_to_solution",
            "variables": {
                "quality_score": 82,
                "quality_level": "A",
                "num_users": 3,
                "num_capabilities": 8,
                "num_constraints": 5
            }
        }
        result = render_transition_prompt(data)
        
        assert "✅ 需求梳理完成！" in result
        assert "82 / 100（A级）" in result
        assert "3 个用户角色" in result
        assert "8 项核心能力" in result
        assert "5 项约束条件" in result
        assert "启动方案设计（Solution Pro）  ← 推荐" in result
    
    def test_spec_to_solution_medium_quality(self):
        """测试 Spec Pro → Solution Pro（中等质量 B 级）"""
        data = {
            "template": "spec_to_solution",
            "variables": {
                "quality_score": 65,
                "quality_level": "B",
                "num_users": 2,
                "num_capabilities": 5,
                "num_constraints": 3
            }
        }
        result = render_transition_prompt(data)
        
        assert "✅ 需求梳理完成" in result
        assert "65 / 100（B级）" in result
        assert "建议继续补充需求细节" in result
        assert "继续补充需求（推荐，可提升方案质量）" in result
    
    def test_spec_to_solution_low_quality(self):
        """测试 Spec Pro → Solution Pro（低质量 C 级）"""
        data = {
            "template": "spec_to_solution",
            "variables": {
                "quality_score": 45,
                "quality_level": "C",
                "num_users": 1,
                "num_capabilities": 2,
                "num_constraints": 1
            }
        }
        result = render_transition_prompt(data)
        
        assert "⚠️ 需求梳理完成，但质量评分较低" in result
        assert "45 / 100（C级）" in result
        assert "强烈建议继续补充需求细节" in result
        assert "继续补充需求  ← 强烈推荐" in result
    
    def test_solution_to_ship(self):
        """测试 Solution Pro → Ship Pro"""
        data = {
            "template": "solution_to_ship",
            "variables": {
                "harness_score": 92,
                "num_reqs": 12,
                "num_modules": 5
            }
        }
        result = render_transition_prompt(data)
        
        assert "✅ 方案设计完成！" in result
        assert "92 / 100" in result
        assert "12 个需求项" in result
        assert "5 个模块" in result
        assert "启动工程实现（Ship Pro）  ← 推荐" in result
    
    def test_ship_completed(self):
        """测试 Ship Pro 完成"""
        data = {
            "template": "ship_completed",
            "variables": {
                "harness_score": 88
            }
        }
        result = render_transition_prompt(data)
        
        assert "✅ 工程实现完成！" in result
        assert "88 / 100" in result
        assert "工作包已生成" in result
        assert "查看工作包详情  ← 推荐" in result
        assert "🎉 整个 DeepFlow 管线已完成！" in result
    
    def test_unknown_template(self):
        """测试未知模板"""
        data = {
            "template": "unknown",
            "variables": {}
        }
        result = render_transition_prompt(data)
        assert "[未知模板: unknown]" in result
    
    def test_missing_variables(self):
        """测试缺失变量（使用默认值）"""
        data = {
            "template": "spec_to_solution",
            "variables": {}
        }
        result = render_transition_prompt(data)
        # 应该使用默认值（0 或 "C"）
        assert "0 / 100（C级）" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
