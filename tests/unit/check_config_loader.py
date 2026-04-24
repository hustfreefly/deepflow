#!/usr/bin/env python3
"""
check_config_loader.py - 验证 PipelineStage input/output 字段
"""
import sys
from dataclasses import fields

def test_pipeline_stage_fields():
    """验证 PipelineStage 有 input/output 字段"""
    # 动态导入（避免缓存）
    import importlib
    import config_loader
    importlib.reload(config_loader)
    
    from config_loader import PipelineStage
    
    field_names = {f.name for f in fields(PipelineStage)}
    
    # 检查 input 字段
    assert "input" in field_names, "PipelineStage 缺少 input 字段"
    print("✅ input 字段存在")
    
    # 检查 output 字段  
    assert "output" in field_names, "PipelineStage 缺少 output 字段"
    print("✅ output 字段存在")
    
    # 测试默认值
    stage = PipelineStage(id="test", name="Test", type="agent", agent="test_agent")
    assert stage.input == [], f"input 默认值应为 [], 实际 {stage.input}"
    assert stage.output is None, f"output 默认值应为 None, 实际 {stage.output}"
    print("✅ 默认值正确")
    
    # 测试赋值
    stage2 = PipelineStage(
        id="test2", 
        name="Test2", 
        type="agent", 
        agent="test_agent",
        input=["plan.md", "context.md"],
        output="result.md"
    )
    assert stage2.input == ["plan.md", "context.md"]
    assert stage2.output == "result.md"
    print("✅ 赋值正确")
    
    return True

def test_yaml_loading():
    """验证 YAML 加载解析 input/output"""
    import tempfile
    import os
    import importlib
    import config_loader
    importlib.reload(config_loader)
    
    yaml_content = """name: test
stages:
  - id: plan
    name: 规划
    type: agent
    agent: planner
    input: []
    output: plan.md
    next: execute
  - id: execute
    name: 执行
    type: agent
    agent: researcher
    input: [plan.md]
    output: execution.md
"""
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write(yaml_content)
        temp_path = f.name
    
    try:
        loader = config_loader.ConfigLoader()
        template = loader._load_pipeline_from_yaml(temp_path, "test")
        
        # 找到 plan stage
        plan_stage = next((s for s in template.stages if s.id == "plan"), None)
        assert plan_stage is not None, "plan stage 未找到"
        assert plan_stage.output == "plan.md", f"plan output 错误: {plan_stage.output}"
        print("✅ plan stage output 解析正确")
        
        # 找到 execute stage
        exec_stage = next((s for s in template.stages if s.id == "execute"), None)
        assert exec_stage is not None, "execute stage 未找到"
        assert exec_stage.input == ["plan.md"], f"execute input 错误: {exec_stage.input}"
        assert exec_stage.output == "execution.md", f"execute output 错误: {exec_stage.output}"
        print("✅ execute stage input/output 解析正确")
        
    finally:
        os.unlink(temp_path)
    
    return True

if __name__ == "__main__":
    print("=" * 50)
    print("ConfigLoader 契约验证")
    print("=" * 50)
    
    try:
        test_pipeline_stage_fields()
        test_yaml_loading()
        print("=" * 50)
        print("✅ 全部通过")
        sys.exit(0)
    except AssertionError as e:
        print(f"❌ 失败: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ 异常: {e}")
        sys.exit(1)
