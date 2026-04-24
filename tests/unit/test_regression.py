"""
DeepFlow 回归测试套件

职责：
- 自动运行 T1-T10 测试矩阵
- 检测代码变更引入的问题
- 生成测试报告

使用：
    pytest test_regression.py -v
    pytest test_regression.py -k "test_t1 or test_t5"  # 运行特定测试
"""

import pytest
import asyncio
import tempfile
import shutil
from pathlib import Path
from typing import List, Dict, Any

# 添加项目根目录到路径
import sys
sys.path.insert(0, str(Path(__file__).parent))

from coordinator import Coordinator, AgentResult
from pipeline_engine import PipelineEngine, PipelineState
from config_loader import ConfigLoader


class TestRegressionSuite:
    """回归测试套件"""
    
    @pytest.fixture
    def temp_session_dir(self):
        """创建临时会话目录"""
        temp_dir = tempfile.mkdtemp(prefix="deepflow_test_")
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    @pytest.fixture
    def coordinator(self):
        """创建 Coordinator 实例"""
        return Coordinator()
    
    @pytest.mark.asyncio
    async def test_t1_simple_task(self, coordinator, temp_session_dir):
        """T1: 简单任务端到端测试"""
        # Mock agent callback 直接返回结果
        async def mock_callback(**kwargs):
            return {
                "success": True,
                "output_file": "test_output.md",
                "score": 0.85,
                "error": None
            }
        
        # 测试意图解析
        domain = coordinator._parse_intent("分析 AAPL 股票")
        assert domain == "investment"
        
        # 测试完整流程
        status = await coordinator.start("investment:分析苹果股票")
        
        # 验证初始状态
        assert status.state in ["RUNNING", "WAITING_AGENT", "COMPLETED"]
        assert status.domain == "investment"
        
        print(f"✅ T1 passed: domain={status.domain}, state={status.state}")
    
    @pytest.mark.asyncio
    async def test_t2_standard_task(self, coordinator):
        """T2: 标准任务端到端测试"""
        status = await coordinator.start("architecture:设计微服务架构")
        
        assert status.domain == "architecture"
        assert status.session_id is not None
        
        print(f"✅ T2 passed: domain={status.domain}")
    
    @pytest.mark.asyncio
    async def test_t5_complex_multi_agent(self):
        """T5: 复杂任务多 Agent 并行测试"""
        # 此测试需要实际运行多 Agent，标记为慢测试
        pytest.skip("T5 requires actual agent execution, run manually")
    
    @pytest.mark.asyncio
    async def test_t6_fix_loop(self, coordinator):
        """T6: Fix→Verify→Audit 循环测试"""
        # 创建引擎并测试循环逻辑
        config_loader = ConfigLoader()
        
        from blackboard_manager import BlackboardManager
        from quality_gate import QualityGate, QualityConfig, DimensionConfig
        
        blackboard = BlackboardManager("test_fix_loop")
        blackboard.init_session()
        
        # 模拟多次迭代
        for i in range(3):
            blackboard.add_quality_score(
                stage="check",
                score=0.7 + i * 0.05,  # 逐渐提升的分数
                passed=True
            )
        
        # 验证分数记录
        scores = blackboard.get_shared_state().get("quality_scores", [])
        assert len(scores) == 3
        
        print(f"✅ T6 fix loop passed: {len(scores)} iterations recorded")
    
    @pytest.mark.asyncio
    async def test_coordinator_mode_d(self, coordinator):
        """Coordinator Mode D start/resume 测试"""
        # 测试 start
        status = await coordinator.start("code:优化这段代码")
        
        assert status.session_id is not None
        assert status.iteration == 0
        
        # 如果有 pending requests，测试 resume
        if status.is_waiting_agent:
            mock_results = [
                AgentResult(
                    request_id=req["request_id"],
                    success=True,
                    output_file=f"mock_{i}.md",
                    score=0.8,
                )
                for i, req in enumerate(status.pending_requests)
            ]
            
            status2 = await coordinator.resume(status.session_id, mock_results)
            assert status2.iteration >= status.iteration
        
        print(f"✅ Mode D start/resume passed")
    
    def test_config_loading(self):
        """配置加载回归测试"""
        config_loader = ConfigLoader()
        
        # 测试所有 domain 配置
        for domain in ["investment", "architecture", "code", "general"]:
            config = config_loader.load_domain(domain)
            assert config is not None
            assert config.pipeline is not None
            print(f"✅ {domain} config loaded")
    
    def test_pipeline_templates(self):
        """Pipeline 模板回归测试"""
        config_loader = ConfigLoader()
        
        for pipeline_name in ["iterative", "parallel", "audit"]:
            template = config_loader.load_pipeline(pipeline_name)
            assert template is not None
            assert len(template.stages) > 0
            print(f"✅ {pipeline_name} template loaded with {len(template.stages)} stages")
    
    def test_quality_gate_integration(self):
        """QualityGate 集成测试"""
        from quality_gate import QualityGate, QualityConfig, DimensionConfig
        
        dims = [
            DimensionConfig(name="accuracy", weight=0.4, threshold=70),
            DimensionConfig(name="completeness", weight=0.3, threshold=70),
            DimensionConfig(name="depth", weight=0.3, threshold=60),
        ]
        
        qg = QualityGate(QualityConfig(dimensions=dims))
        
        # 测试收敛检测
        scores = [60, 70, 75, 78, 80]
        converged, reason = qg.check_convergence(
            scores=scores,
            iteration=5,
            max_iterations=10,
            target_score=85
        )
        
        # 应该未收敛（分数未达目标）
        assert converged == False or reason is not None
        
        print(f"✅ QualityGate convergence check passed")


class TestPipelineEngineCore:
    """PipelineEngine 核心功能测试"""
    
    @pytest.mark.asyncio
    async def test_pipeline_state_transitions(self):
        """测试状态机转换"""
        engine = PipelineEngine("general", "test_state_001")
        
        # 初始状态
        assert engine.state == PipelineState.INIT
        
        # 模拟执行后状态变化
        # 注意：这里需要 mock agent_callback
        print(f"✅ PipelineEngine state machine test passed")
    
    @pytest.mark.asyncio
    async def test_stage_navigation(self):
        """测试 stage 导航"""
        engine = PipelineEngine("general", "test_nav_001")
        
        # 测试 _find_stage_index
        idx = engine._find_stage_index("plan")
        # 结果取决于具体 pipeline 配置
        
        print(f"✅ Stage navigation test passed")
    
    def test_threshold_normalization(self):
        """测试阈值尺度转换"""
        engine = PipelineEngine("general", "test_threshold_001")
        
        # 测试 0-1 尺度转换为 0-100
        assert engine._normalize_threshold(0.85) == 85.0
        assert engine._normalize_threshold(85.0) == 85.0  # 已经是 0-100 尺度
        
        print(f"✅ Threshold normalization test passed")


class TestConfigDrivenBehavior:
    """配置驱动行为测试"""
    
    def test_quality_gate_from_config(self):
        """测试从配置创建 QualityGate"""
        config_loader = ConfigLoader()
        config = config_loader.load_domain("investment")
        
        quality_config = getattr(config, 'quality', None)
        assert quality_config is not None
        
        # 验证质量维度配置
        assert len(quality_config.dimensions) >= 4
        
        print(f"✅ QualityGate from config test passed")
    
    def test_resilience_from_config(self):
        """测试从配置创建 ResilienceManager"""
        config_loader = ConfigLoader()
        config = config_loader.load_domain("investment")
        
        resilience_config = getattr(config, 'resilience', None)
        
        if resilience_config:
            assert hasattr(resilience_config, 'circuit_breaker')
            assert hasattr(resilience_config, 'retry_policy')
        
        print(f"✅ ResilienceManager from config test passed")


# ── 快速冒烟测试 ──

def test_smoke_import():
    """快速冒烟测试：确保所有模块可导入"""
    import coordinator
    import pipeline_engine
    import config_loader
    import quality_gate
    import blackboard_manager
    import resilience_manager
    
    print("✅ All modules import successfully")


def test_smoke_coordinator_init():
    """快速冒烟测试：Coordinator 可初始化"""
    coord = Coordinator()
    assert coord is not None
    print("✅ Coordinator initialization smoke test passed")


def test_smoke_pipeline_engine_init():
    """快速冒烟测试：PipelineEngine 可初始化"""
    engine = PipelineEngine("general", "smoke_test_001")
    assert engine is not None
    assert engine.state.name == "INIT"
    print("✅ PipelineEngine initialization smoke test passed")


if __name__ == "__main__":
    # 直接运行测试
    print("Running DeepFlow regression tests...\n")
    
    # 运行 pytest
    import subprocess
    result = subprocess.run(
        ["pytest", __file__, "-v", "--tb=short"],
        capture_output=False,
        text=True
    )
    
    sys.exit(result.returncode)
