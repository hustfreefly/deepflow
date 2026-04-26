#!/usr/bin/env python3
"""
DeepFlow V2.0 - 解决方案设计领域 Orchestrator 实现
继承 BaseOrchestrator，实现方案设计特定的阶段逻辑
"""

import os
import sys
import json
import re
import asyncio
from pathlib import Path
from typing import Dict, Any, List

sys.path.insert(0, '/Users/allen/.openclaw/workspace/.deepflow/')
sys.path.insert(0, '/Users/allen/.openclaw/workspace/.deepflow/core/')

from orchestrator_base import (
    BaseOrchestrator, DomainConfig, StageConfig, ExecutionContext,
    PipelineState, CircuitBreakerOpen, ContractViolation, WorkerConfig
)


class SolutionOrchestrator(BaseOrchestrator):
    """
    解决方案设计领域 Pipeline Orchestrator
    
    上下文要求：
    - topic: 设计主题（如 "设计一个高并发电商订单系统"）
    - type: 方案类型（architecture | business | technical）
    - constraints: 约束条件列表（可选）
    - stakeholders: 利益相关者（可选）
    """
    
    def __init__(self, user_context: Dict[str, Any]):
        """
        Args:
            user_context: 必须包含 topic, type
        """
        # 验证必需字段
        if "topic" not in user_context:
            raise ValueError("SolutionOrchestrator requires 'topic' in context")
        
        self.topic = user_context["topic"]
        self.solution_type = user_context.get("type", "architecture")
        self.constraints = user_context.get("constraints", [])
        self.stakeholders = user_context.get("stakeholders", [])
        
        super().__init__(domain="solution", user_context=user_context)
        
        # P0-FIX: 并发控制，限制最大并行Worker数 (OpenClaw限制)
        self.concurrency_limit = getattr(
            self.domain_config.concurrency, 
            'max_parallel_workers', 
            3  # 默认限制为3
        )
        self.semaphore = asyncio.Semaphore(self.concurrency_limit)
        
        print(f"[Solution] Topic: {self.topic}")
        print(f"[Solution] Type: {self.solution_type}")
        print(f"[Solution] Concurrency limit: {self.concurrency_limit}")
    
    def _generate_session_id(self) -> str:
        """解决方案领域特定的 session_id 生成"""
        topic_slug = re.sub(r'[^\w]', '_', self.topic)[:30]
        return f"{topic_slug}_{self.solution_type}_{__import__('uuid').uuid4().hex[:8]}"
    
    async def _execute_stage(self, stage: StageConfig) -> Dict[str, Any]:
        """
        执行解决方案领域特定的阶段
        """
        stage_type = stage.stage_type
        stage_name = stage.name
        
        if stage_type == "parallel_workers":
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
    
    async def _execute_single_worker(self, stage: StageConfig) -> Dict[str, Any]:
        """
        执行单 Worker 阶段
        """
        worker = stage.workers[0] if stage.workers else None
        if not worker:
            return {"success": False, "error": "No worker configured"}
        
        print(f"  [Single] Role: {worker.role}, Timeout: {worker.timeout}s")
        
        # 构建 prompt
        prompt = self._build_worker_prompt(worker.role, stage.name)
        
        try:
            # 调用模型
            result = await self.models.call(prompt, timeout=worker.timeout)
            
            if result["success"]:
                print(f"  ✅ {worker.role} completed")
                return {
                    "success": True,
                    "output": result["result"],
                    "model_used": result["model_used"]
                }
            else:
                return {"success": False, "error": result.get("error", "Unknown error")}
                
        except Exception as e:
            print(f"  ❌ {worker.role} failed: {e}")
            return {"success": False, "error": str(e)}
    
    async def _execute_parallel_workers(self, stage: StageConfig) -> Dict[str, Any]:
        """
        执行并行 Worker 阶段
        """
        print(f"  [Parallel] Workers: {len(stage.workers)}")
        
        tasks = []
        for worker in stage.workers:
            task = self._run_worker(worker, stage.name)
            tasks.append(task)
        
        # 并发执行
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        outputs = []
        errors = []
        
        for i, result in enumerate(results):
            worker_role = stage.workers[i].role
            if isinstance(result, Exception):
                errors.append(f"{worker_role}: {str(result)}")
            elif result.get("success"):
                outputs.append({
                    "role": worker_role,
                    "output": result["output"]
                })
                print(f"  ✅ {worker_role} completed")
            else:
                errors.append(f"{worker_role}: {result.get('error')}")
                print(f"  ⚠️ {worker_role} failed: {result.get('error')}")
        
        # 只要有一个成功就算阶段成功
        if outputs:
            return {
                "success": True,
                "output": {
                    "results": outputs,
                    "errors": errors if errors else None
                }
            }
        else:
            return {
                "success": False,
                "error": f"All workers failed: {', '.join(errors)}"
            }
    
    async def _run_worker(self, worker: WorkerConfig, stage_name: str) -> Dict[str, Any]:
        """
        运行单个 Worker（带并发控制）
        """
        async with self.semaphore:
            prompt = self._build_worker_prompt(worker.role, stage_name)
            
            try:
                result = await self.models.call(prompt, timeout=worker.timeout)
                return result
            except Exception as e:
                return {"success": False, "error": str(e)}
    
    def _build_worker_prompt(self, role: str, stage_name: str) -> str:
        """
        构建 Worker Prompt
        """
        # 加载角色特定的 prompt 模板
        prompt_path = f"/Users/allen/.openclaw/workspace/.deepflow/prompts/solution/{role.replace('solution_', '')}.md"
        
        role_prompt = ""
        try:
            if os.path.exists(prompt_path):
                with open(prompt_path, 'r', encoding='utf-8') as f:
                    role_prompt = f.read()
        except Exception as e:
            print(f"⚠️ Failed to load prompt {prompt_path}: {e}")
        
        # 构建上下文
        context = {
            "topic": self.topic,
            "solution_type": self.solution_type,
            "constraints": self.constraints,
            "stakeholders": self.stakeholders,
            "stage": stage_name,
            "session_id": self.session_id
        }
        
        # 如果有之前阶段的输出，加入上下文
        if self.context.stage_outputs:
            context["previous_outputs"] = {
                k: v[:500] + "..." if isinstance(v, str) and len(v) > 500 else v
                for k, v in self.context.stage_outputs.items()
            }
        
        # 组装完整 prompt
        full_prompt = f"""# DeepFlow Solution Designer - {role}

## 任务上下文
```json
{json.dumps(context, indent=2, ensure_ascii=False)}
```

## 角色定义
{role_prompt}

## 当前阶段
你正在执行 pipeline 的 **{stage_name}** 阶段。

## 输出要求
- 使用中文输出
- 结构化表达，使用 Markdown 格式
- 关键决策必须有明确理由
"""
        
        return full_prompt
    
    def _extract_score(self, result: Any) -> float:
        """
        从审计结果中提取分数（带容错处理）
        
        P0-FIX: 增加异常处理，避免KeyError导致Pipeline崩溃
        """
        try:
            if not isinstance(result, dict):
                print(f"⚠️ _extract_score: result is not dict, type={type(result)}")
                return 0.5  # 默认中等分数
            
            # 从 audit 结果中提取
            if "audit_result" in result:
                audit = result["audit_result"]
                if isinstance(audit, dict) and "overall_score" in audit:
                    score = float(audit["overall_score"])
                    print(f"  Score extracted: {score:.2%}")
                    return score
            
            # 从并行 worker 结果中提取（取平均分）
            if "results" in result and isinstance(result["results"], list):
                scores = []
                for r in result["results"]:
                    if isinstance(r, dict) and "output" in r:
                        output = r["output"]
                        if isinstance(output, dict) and "audit_result" in output:
                            audit = output["audit_result"]
                            if isinstance(audit, dict) and "overall_score" in audit:
                                scores.append(float(audit.get("overall_score", 0)))
                
                if scores:
                    avg_score = sum(scores) / len(scores)
                    print(f"  Avg score from {len(scores)} auditors: {avg_score:.2%}")
                    return avg_score
            
            # 尝试直接解析 result.output 中的分数
            if "output" in result:
                output = result["output"]
                if isinstance(output, dict):
                    if "overall_score" in output:
                        return float(output["overall_score"])
                    if "score" in output:
                        return float(output["score"])
            
            print(f"⚠️ _extract_score: no score found in result, returning default 0.5")
            return 0.5  # 默认中等分数
            
        except (KeyError, TypeError, ValueError) as e:
            print(f"⚠️ _extract_score error: {e}, returning default 0.5")
            return 0.5
        except Exception as e:
            print(f"⚠️ _extract_score unexpected error: {e}, returning default 0.5")
            return 0.5
    
    def _build_result(self, **kwargs) -> Dict[str, Any]:
        """
        构建最终结果
        """
        result = {
            "session_id": self.session_id,
            "domain": self.domain,
            "topic": self.topic,
            "solution_type": self.solution_type,
            "state": self.state.name,
            "stages_completed": list(self.context.stage_outputs.keys()),
            "stage_outputs": self.context.stage_outputs,
        }
        
        # 添加可选字段
        if "iterations" in kwargs:
            result["iterations"] = kwargs["iterations"]
        if "final_score" in kwargs:
            result["final_score"] = kwargs["final_score"]
        if "convergence_reason" in kwargs:
            result["convergence_reason"] = kwargs["convergence_reason"]
        if "error" in kwargs:
            result["error"] = kwargs["error"]
        
        return result
    
    async def _execute_iterative(self, stage: StageConfig) -> Dict[str, Any]:
        """
        执行迭代阶段（审计-修复循环）
        """
        print(f"  [Iterative] Max rounds: {self.domain_config.convergence.max_iterations}")
        
        for iteration in range(self.domain_config.convergence.max_iterations):
            self.context.current_iteration = iteration
            print(f"\n  --- Iteration {iteration + 1}/{self.domain_config.convergence.max_iterations} ---")
            
            # 执行审计
            audit_result = await self._execute_parallel_workers(stage)
            if not audit_result["success"]:
                return audit_result
            
            # 提取分数
            score = self._extract_score(audit_result["output"])
            self.context.scores.append(score)
            self.convergence.add_score(score)
            
            # 检查收敛
            converged, reason = self.convergence.check()
            print(f"  Score: {score:.2%}, Converged: {converged}")
            
            if converged:
                return {
                    "success": True,
                    "output": audit_result["output"],
                    "score": score,
                    "iterations": iteration + 1
                }
            
            # 执行修复（如果未收敛）
            fix_prompt = self._build_worker_prompt("fixer", "fix")
            try:
                fix_result = await self.models.call(fix_prompt, timeout=240)
                if fix_result["success"]:
                    print(f"  ✅ Fix applied")
                    # 保存修复结果到 Blackboard
                    self.context.stage_outputs[f"fix_round_{iteration}"] = fix_result["result"]
            except Exception as e:
                print(f"  ⚠️ Fix failed: {e}")
        
        # 达到最大迭代次数
        return {
            "success": True,
            "output": audit_result["output"],
            "score": score,
            "iterations": self.domain_config.convergence.max_iterations,
            "note": "Max iterations reached"
        }


def run_solution_design(topic: str, solution_type: str = "architecture", 
                       constraints: List[str] = None, 
                       stakeholders: List[str] = None) -> Dict[str, Any]:
    """
    运行解决方案设计 Pipeline
    
    Args:
        topic: 设计主题
        solution_type: 方案类型 (architecture | business | technical)
        constraints: 约束条件列表
        stakeholders: 利益相关者列表
        
    Returns:
        执行结果
    """
    context = {
        "topic": topic,
        "type": solution_type,
        "constraints": constraints or [],
        "stakeholders": stakeholders or []
    }
    
    orchestrator = SolutionOrchestrator(context)
    return asyncio.run(orchestrator.run())


if __name__ == "__main__":
    # 测试
    print("✅ SolutionOrchestrator loaded successfully")
    
    # 快速测试
    test_context = {
        "topic": "设计一个高并发电商订单系统",
        "type": "architecture",
        "constraints": ["日均百万订单", "99.99%可用性"],
        "stakeholders": ["技术团队", "产品团队"]
    }
    
    orchestrator = SolutionOrchestrator(test_context)
    print(f"Session ID: {orchestrator.session_id}")
