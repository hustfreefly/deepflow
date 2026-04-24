#!/usr/bin/env python3
"""
DeepFlow V2.0 - 投资领域 Orchestrator 实现
继承 BaseOrchestrator，实现投资特定的阶段逻辑
"""

import os
import sys
import json
import re
from pathlib import Path
from typing import Dict, Any, List

sys.path.insert(0, '/Users/allen/.openclaw/workspace/.deepflow/')
sys.path.insert(0, '/Users/allen/.openclaw/workspace/.deepflow/core/')

from orchestrator_base import (
    BaseOrchestrator, DomainConfig, StageConfig, ExecutionContext,
    PipelineState, CircuitBreakerOpen, ContractViolation
)


class InvestmentOrchestrator(BaseOrchestrator):
    """
    投资领域 Pipeline Orchestrator
    
    上下文要求：
    - code: 股票代码（如 "300604.SZ"）
    - name: 公司名称（如 "长川科技"）
    - price: 当前股价（可选）
    """
    
    def __init__(self, user_context: Dict[str, Any]):
        """
        Args:
            user_context: 必须包含 code, name
        """
        # 验证必需字段
        if "code" not in user_context or "name" not in user_context:
            raise ValueError("InvestmentOrchestrator requires 'code' and 'name' in context")
        
        # 先设置 stock_code 和 stock_name，因为 _generate_session_id() 需要它们
        self.stock_code = user_context["code"]
        self.stock_name = user_context["name"]
        self.stock_price = user_context.get("price")
        
        super().__init__(domain="investment", user_context=user_context)
        
        print(f"[Investment] Stock: {self.stock_name} ({self.stock_code})")
    
    def _generate_session_id(self) -> str:
        """投资领域特定的 session_id 生成"""
        code_clean = self.stock_code.replace('.SH', '').replace('.SZ', '')
        return f"{self.stock_name}_{code_clean}_{self.domain}_{__import__('uuid').uuid4().hex[:8]}"
    
    async def _execute_stage(self, stage: StageConfig) -> Dict[str, Any]:
        """
        执行投资领域特定的阶段
        """
        stage_type = stage.stage_type
        stage_name = stage.name
        
        if stage_type == "data_manager":
            return await self._execute_data_collection(stage)
        elif stage_type == "parallel_workers":
            return await self._execute_parallel_workers(stage)
        elif stage_type == "single_worker":
            return await self._execute_single_worker(stage)
        elif stage_type == "iterative":
            return await self._execute_iterative(stage)
        elif stage_type == "custom" and stage.custom_handler:
            handler = getattr(self, stage.custom_handler, None)
            if handler:
                return await handler(stage)
            else:
                return {"success": False, "error": f"Unknown custom handler: {stage.custom_handler}"}
        else:
            return {"success": False, "error": f"Unknown stage type: {stage_type}"}
    
    async def _execute_data_collection(self, stage: StageConfig) -> Dict[str, Any]:
        """
        执行数据采集阶段（STEP 1）
        """
        from data_manager import DataEvolutionLoop, ConfigDrivenCollector
        from data_providers.investment import register_providers
        from blackboard_manager import BlackboardManager
        
        try:
            print(f"  [Data] Initializing data collection...")
            
            # 注册数据源
            register_providers()
            
            # 初始化组件
            config_path = stage.config or "/Users/allen/.openclaw/workspace/.deepflow/data_sources/investment.yaml"
            collector = ConfigDrivenCollector(config_path)
            blackboard = BlackboardManager(self.session_id)
            data_loop = DataEvolutionLoop(collector, blackboard)
            
            # 执行采集
            context = {
                "code": self.stock_code,
                "name": self.stock_name,
                "price": self.stock_price
            }
            bootstrap_data = data_loop.bootstrap_phase(context)
            
            print(f"  ✅ Data collection complete: {len(bootstrap_data)} datasets")
            
            # 验证数据
            verification = self._verify_data_collection()
            
            return {
                "success": True,
                "output": {
                    "datasets": list(bootstrap_data.keys()),
                    "count": len(bootstrap_data),
                    "verification": verification
                }
            }
            
        except Exception as e:
            print(f"  ⚠️ Data collection warning: {e}")
            # 数据采集中断不致命
            return {
                "success": True,
                "output": {"error": str(e), "partial": True}
            }
    
    def _verify_data_collection(self) -> Dict[str, bool]:
        """验证数据文件是否存在"""
        base_path = Path(f"/Users/allen/.openclaw/workspace/.deepflow/blackboard/{self.session_id}/data")
        checks = {
            "index": (base_path / "INDEX.json").exists(),
            "financials": (base_path / "01_financials/key_metrics.json").exists(),
            "market": (base_path / "02_market_quote/key_metrics.json").exists(),
        }
        return checks
    
    async def _execute_parallel_workers(self, stage: StageConfig) -> Dict[str, Any]:
        """
        执行并行 Worker 阶段（如 6 个 researcher）
        """
        import asyncio
        from openclaw import sessions_spawn
        
        workers = stage.workers or []
        if not workers:
            return {"success": False, "error": "No workers configured for parallel stage"}
        
        print(f"  [Parallel] Spawning {len(workers)} workers...")
        
        async def run_worker(worker_config) -> Dict:
            async with self.semaphore:
                role = worker_config.role
                label = f"{role}_{self.context.current_iteration}"
                
                # 构建 task
                prompt = self.build_prompt(f"worker_{role}", {
                    "worker_role": role,
                    "stock_code": self.stock_code,
                    "stock_name": self.stock_name,
                })
                
                try:
                    result = sessions_spawn(
                        runtime="subagent",
                        mode="run",
                        label=label,
                        task=prompt,
                        timeout_seconds=worker_config.timeout or 300,
                        model=worker_config.model or self.domain_config.model_chain.primary,
                        scopes=["host.exec", "fs.read"],
                    )
                    return {"role": role, "success": True, "result": result}
                except Exception as e:
                    return {"role": role, "success": False, "error": str(e)}
        
        # 并行执行
        results = await asyncio.gather(
            *[run_worker(w) for w in workers],
            return_exceptions=True
        )
        
        # 处理结果
        successful = [r for r in results if isinstance(r, dict) and r.get("success")]
        failed = [r for r in results if isinstance(r, dict) and not r.get("success")]
        
        print(f"  ✅ {len(successful)} succeeded, {len(failed)} failed")
        
        return {
            "success": len(successful) > 0,  # 至少一个成功就算成功
            "output": {
                "results": results,
                "successful_count": len(successful),
                "failed_count": len(failed)
            }
        }
    
    async def _execute_single_worker(self, stage: StageConfig) -> Dict[str, Any]:
        """
        执行单 Worker 阶段
        """
        from openclaw import sessions_spawn
        
        workers = stage.workers
        if not workers:
            return {"success": False, "error": "No worker configured for single stage"}
        
        worker = workers[0]
        role = worker.role
        
        print(f"  [Single] Spawning {role}...")
        
        # 构建 task
        prompt = self.build_prompt(f"worker_{role}", {
            "worker_role": role,
            "stock_code": self.stock_code,
            "stock_name": self.stock_name,
            "stage_outputs": self.context.stage_outputs,
        })
        
        try:
            result = sessions_spawn(
                runtime="subagent",
                mode="run",
                label=f"{role}_{self.context.current_iteration}",
                task=prompt,
                timeout_seconds=worker.timeout or 300,
                model=worker.model or self.domain_config.model_chain.primary,
                scopes=["host.exec", "fs.read"],
            )
            
            return {
                "success": True,
                "output": {"role": role, "result": result}
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _execute_iterative(self, stage: StageConfig) -> Dict[str, Any]:
        """
        执行迭代阶段（带收敛检测）
        """
        self.context.current_iteration += 1
        iteration = self.context.current_iteration
        
        print(f"  [Iterative] Round {iteration}...")
        
        # 执行 Worker（类似 parallel 但带评分）
        result = await self._execute_parallel_workers(stage)
        
        if not result["success"]:
            return result
        
        # 提取分数
        score = self._extract_score(result["output"])
        result["output"]["score"] = score
        
        return result
    
    def _extract_score(self, result: Any) -> float:
        """
        从投资领域结果中提取分数
        """
        try:
            # 尝试从 result 中解析
            if isinstance(result, dict):
                # 直接有 score 字段
                if "score" in result:
                    return float(result["score"])
                
                # 从 results 列表中提取
                if "results" in result and isinstance(result["results"], list):
                    scores = []
                    for r in result["results"]:
                        if isinstance(r, dict) and "result" in r:
                            # 尝试从 result 字符串中解析
                            score = self._parse_score_from_text(str(r["result"]))
                            if score > 0:
                                scores.append(score)
                    if scores:
                        return sum(scores) / len(scores)
            
            # 尝试从文本中解析
            if isinstance(result, str):
                return self._parse_score_from_text(result)
            
            return 0.0
            
        except Exception as e:
            print(f"  ⚠️ Failed to extract score: {e}")
            return 0.0
    
    def _parse_score_from_text(self, text: str) -> float:
        """从文本中解析分数"""
        # 尝试多种格式
        patterns = [
            r'score[:\s]+(0\.\d+)',
            r'分数[:\s]+(0\.\d+)',
            r'final_score[:\s]+(0\.\d+)',
            r'评分[:\s]+(\d+)%',
            r'(\d+)%',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                score_str = match.group(1)
                if '.' in score_str:
                    return float(score_str)
                else:
                    return float(score_str) / 100.0
        
        return 0.0
    
    def _build_result(self, **kwargs) -> Dict[str, Any]:
        """
        构建投资领域最终结果
        """
        base_result = {
            "status": "completed" if self.state == PipelineState.CONVERGED else "failed",
            "pipeline_state": self.state.name,
            "session_id": self.session_id,
            "domain": self.domain,
            "stock_code": self.stock_code,
            "stock_name": self.stock_name,
            "iterations": self.context.current_iteration,
            "scores": self.context.scores,
        }
        
        base_result.update(kwargs)
        
        # 添加投资特定的字段
        if "final_score" not in base_result and self.context.scores:
            base_result["final_score"] = self.context.scores[-1]
        
        return base_result


# ============================================================================
# 投资领域入口
# ============================================================================

def run_investment_analysis(code: str, name: str, price: float = None) -> Dict[str, Any]:
    """
    投资领域快速入口
    
    Args:
        code: 股票代码（如 "300604.SZ"）
        name: 公司名称（如 "长川科技"）
        price: 当前股价（可选）
        
    Returns:
        分析结果
    """
    import asyncio
    
    context = {
        "code": code,
        "name": name,
        "price": price
    }
    
    orchestrator = InvestmentOrchestrator(context)
    return asyncio.run(orchestrator.run())


if __name__ == "__main__":
    # 测试
    print("✅ InvestmentOrchestrator loaded successfully")
    
    # 示例运行
    if os.environ.get("TEST_MODE"):
        result = run_investment_analysis("300604.SZ", "长川科技")
        print(json.dumps(result, indent=2, ensure_ascii=False))
