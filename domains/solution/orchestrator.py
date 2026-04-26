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
import yaml
from pathlib import Path
from typing import Dict, Any, List

# P2-002: 动态计算项目根路径
DEEPFLOW_HOME = os.environ.get('DEEPFLOW_HOME')
if DEEPFLOW_HOME and os.path.exists(DEEPFLOW_HOME):
    _BASE_PATH = DEEPFLOW_HOME
else:
    _BASE_PATH = str(Path(__file__).resolve().parent.parent.parent)

sys.path.insert(0, _BASE_PATH)
sys.path.insert(0, os.path.join(_BASE_PATH, 'core'))

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
    
    # P0-FIX: 渐进交付检查点定义
    DELIVERY_CHECKPOINTS = {
        "planning": {"type": "quick_preview", "max_time": 30},
        "design": {"type": "partial_draft", "max_time": 120},
        "deliver": {"type": "final", "max_time": 600}
    }
    
    # P2-002: 使用动态路径
    BLACKBOARD_BASE = os.path.join(_BASE_PATH, "blackboard")
    PROMPTS_DIR = os.path.join(_BASE_PATH, "prompts", "solution")
    
    def __init__(self, user_context: Dict[str, Any]):
        """
        Args:
            user_context: 必须包含 topic, type
        """
        # P2-001: 完整输入校验
        self._validate_input(user_context)
        
        self.topic = user_context["topic"]
        self.solution_type = user_context.get("type", "architecture")
        self.constraints = user_context.get("constraints") or []
        self.stakeholders = user_context.get("stakeholders") or []
        
        super().__init__(domain="solution", user_context=user_context)
        
        # P1-001: 初始化时预加载 prompt 缓存
        self._prompt_cache = self._load_prompt_cache()
        
        # P0-FIX: 并发控制，限制最大并行Worker数 (OpenClaw限制)
        self.concurrency_limit = getattr(
            self.domain_config.concurrency, 
            'max_parallel_workers', 
            3  # 默认限制为3
        )
        self.semaphore = asyncio.Semaphore(self.concurrency_limit)
        
        # P0-FIX: 初始化 Blackboard 目录
        self.blackboard_dir = os.path.join(self.BLACKBOARD_BASE, self.session_id)
        os.makedirs(self.blackboard_dir, exist_ok=True)
        os.makedirs(os.path.join(self.blackboard_dir, "stages"), exist_ok=True)
        
        # P0-FIX: 质量维度配置
        self.quality_dimensions = self._load_quality_config()
        
        print(f"[Solution] Topic: {self.topic}")
        print(f"[Solution] Type: {self.solution_type}")
        print(f"[Solution] Concurrency limit: {self.concurrency_limit}")
        print(f"[Solution] Blackboard: {self.blackboard_dir}")
        print(f"[Solution] Prompt cache loaded: {len(self._prompt_cache)} templates")
    
    def _get_base_path(self) -> str:
        """
        P2-002: 获取 DeepFlow 项目根目录
        优先使用 DEEPFLOW_HOME 环境变量，其次使用 __file__ 相对路径推导
        """
        return _BASE_PATH
    
    def _load_quality_config(self) -> Dict[str, Any]:
        """加载质量维度配置"""
        config_path = os.path.join(_BASE_PATH, 'domains', 'solution.yaml')
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            return config.get('quality', {})
        except Exception as e:
            print(f"⚠️ Failed to load quality config: {e}")
            return {}
    
    def _validate_input(self, user_context: Dict[str, Any]) -> None:
        """
        P2-001: 完整输入校验
        验证 topic/type/constraints/stakeholders 格式和范围
        
        Raises:
            ValueError: topic 无效或 type 不在枚举中
            TypeError: constraints 或 stakeholders 非列表
        """
        # 检查 topic 存在性
        if "topic" not in user_context:
            raise ValueError("SolutionOrchestrator requires 'topic' in context")
        
        topic = user_context["topic"]
        
        # 检查 topic 长度
        if not isinstance(topic, str) or len(topic.strip()) == 0:
            raise ValueError("topic cannot be empty")
        
        if len(topic) < 5:
            raise ValueError("topic too short (minimum 5 characters)")
        
        if len(topic) > 200:
            raise ValueError("topic too long (maximum 200 characters)")
        
        # 检查 type 有效性
        solution_type = user_context.get("type", "architecture")
        valid_types = ["architecture", "business", "technical"]
        if solution_type not in valid_types:
            raise ValueError(f"invalid solution type '{solution_type}', must be one of {valid_types}")
        
        # 检查 constraints 类型（允许 None，会自动转为空列表）
        constraints = user_context.get("constraints")
        if constraints is not None and not isinstance(constraints, list):
            raise TypeError("constraints must be a list or None")
        
        # 检查 stakeholders 类型（允许 None，会自动转为空列表）
        stakeholders = user_context.get("stakeholders")
        if stakeholders is not None and not isinstance(stakeholders, list):
            raise TypeError("stakeholders must be a list or None")
    
    def _load_prompt_cache(self) -> Dict[str, str]:
        """
        P1-001: 预加载所有 prompt 模板到内存字典
        从 prompts/solution/ 目录读取所有 .md 文件
        
        Returns:
            Dict mapping role name to prompt content
        """
        cache = {}
        prompts_dir = self.PROMPTS_DIR
        
        if not os.path.exists(prompts_dir):
            print(f"⚠️ Prompts directory not found: {prompts_dir}")
            return cache
        
        for filename in os.listdir(prompts_dir):
            if filename.endswith('.md'):
                filepath = os.path.join(prompts_dir, filename)
                role_name = filename[:-3]  # 移除 .md 后缀
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        cache[role_name] = f.read()
                except Exception as e:
                    print(f"⚠️ Failed to load prompt {filename}: {e}")
                    cache[role_name] = ""
        
        return cache
    
    def _get_cached_prompt(self, role: str) -> str:
        """
        P1-001: 从缓存获取 prompt
        如果 role 不在缓存中，回退到文件读取
        
        Args:
            role: Worker 角色名（如 'planner', 'architect'）
        
        Returns:
            Prompt 内容字符串
        """
        if role in self._prompt_cache:
            return self._prompt_cache[role]
        
        # 回退到文件读取
        prompt_path = os.path.join(self.PROMPTS_DIR, f"{role}.md")
        try:
            if os.path.exists(prompt_path):
                with open(prompt_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                # 可选：更新缓存
                self._prompt_cache[role] = content
                return content
        except Exception as e:
            print(f"⚠️ Failed to load prompt {prompt_path}: {e}")
        
        return ""
    
    def _save_to_blackboard(self, stage_name: str, data: Any):
        """
        P0-FIX: 保存阶段产物到 Blackboard（文件持久化）
        """
        try:
            stage_dir = os.path.join(self.blackboard_dir, "stages")
            os.makedirs(stage_dir, exist_ok=True)
            
            file_path = os.path.join(stage_dir, f"{stage_name}.json")
            with open(file_path, 'w', encoding='utf-8') as f:
                if isinstance(data, (dict, list)):
                    json.dump(data, f, indent=2, ensure_ascii=False)
                else:
                    json.dump({"content": str(data)}, f, indent=2, ensure_ascii=False)
            
            # 同时保存 shared_state
            shared_state_path = os.path.join(self.blackboard_dir, "shared_state.json")
            shared_state = {
                "session_id": self.session_id,
                "domain": self.domain,
                "topic": self.topic,
                "solution_type": self.solution_type,
                "current_stage": stage_name,
                "stages_completed": list(self.context.stage_outputs.keys()),
                "scores": self.context.scores,
                "timestamp": __import__('datetime').datetime.now().isoformat()
            }
            with open(shared_state_path, 'w', encoding='utf-8') as f:
                json.dump(shared_state, f, indent=2, ensure_ascii=False)
            
            print(f"  💾 Saved to Blackboard: {stage_name}")
        except Exception as e:
            print(f"  ⚠️ Blackboard save failed: {e}")
    
    def _load_from_blackboard(self, stage_name: str) -> Any:
        """从 Blackboard 加载阶段产物"""
        try:
            file_path = os.path.join(self.blackboard_dir, "stages", f"{stage_name}.json")
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            print(f"  ⚠️ Blackboard load failed: {e}")
        return None
    
    def _apply_quality_gate(self, stage_output: Dict[str, Any], stage_name: str) -> Dict[str, Any]:
        """
        P0-FIX: 应用质量门禁
        检查阶段产出是否符合质量维度要求
        """
        if not self.quality_dimensions or 'dimensions' not in self.quality_dimensions:
            return {"passed": True, "score": 0.0, "issues": []}
        
        try:
            dimensions = self.quality_dimensions['dimensions']
            scores = {}
            issues = []
            
            # 从 stage_output 提取各维度分数（如果产出中有）
            if isinstance(stage_output, dict):
                for dim in dimensions:
                    dim_name = dim['name']
                    if dim_name in stage_output:
                        scores[dim_name] = float(stage_output[dim_name])
                    elif 'quality' in stage_output and dim_name in stage_output['quality']:
                        scores[dim_name] = float(stage_output['quality'][dim_name])
            
            # 计算加权总分
            total_weight = sum(d['weight'] for d in dimensions)
            weighted_score = 0.0
            
            for dim in dimensions:
                dim_name = dim['name']
                weight = dim['weight']
                threshold = dim.get('threshold', 0.0)
                
                if dim_name in scores:
                    dim_score = scores[dim_name]
                    weighted_score += dim_score * (weight / total_weight)
                    
                    if dim_score < threshold:
                        issues.append(f"{dim_name}: {dim_score:.2%} < threshold {threshold:.2%}")
            
            result = {
                "passed": len(issues) == 0,
                "score": weighted_score,
                "issues": issues
            }
            
            print(f"  📊 Quality Gate: score={weighted_score:.2%}, passed={result['passed']}")
            return result
            
        except Exception as e:
            print(f"  ⚠️ Quality gate error: {e}")
            return {"passed": True, "score": 0.0, "issues": []}
    
    def _deliver_checkpoint(self, stage_name: str, stage_output: Any):
        """
        P0-FIX: 渐进交付检查点
        在关键阶段完成后返回中间结果
        """
        if stage_name not in self.DELIVERY_CHECKPOINTS:
            return
        
        checkpoint = self.DELIVERY_CHECKPOINTS[stage_name]
        checkpoint_type = checkpoint["type"]
        
        print(f"\n📬 CHECKPOINT: {stage_name} ({checkpoint_type})")
        
        # 构建检查点摘要
        summary = self._build_checkpoint_summary(stage_name, stage_output, checkpoint_type)
        
        # 保存检查点产物
        checkpoint_path = os.path.join(self.blackboard_dir, f"checkpoint_{stage_name}.md")
        try:
            with open(checkpoint_path, 'w', encoding='utf-8') as f:
                f.write(summary)
            print(f"  💾 Checkpoint saved: {checkpoint_path}")
        except Exception as e:
            print(f"  ⚠️ Checkpoint save failed: {e}")
        
        # 尝试调用 sessions_yield 进行渐进交付（如果在 OpenClaw 环境中）
        try:
            from openclaw import sessions_yield
            # 构建交付消息
            if checkpoint_type == "quick_preview":
                message = f"🚀 **方案预览**\n\n{summary[:500]}..."
            elif checkpoint_type == "partial_draft":
                message = f"📄 **初稿完成**\n\n{summary[:1000]}..."
            else:
                message = f"📊 **最终方案**\n\n{summary}"
            
            # 注意：sessions_yield 只在 OpenClaw 环境中有效
            # 在非 Agent Run 环境中会抛出异常，被下面的 except 捕获
            sessions_yield(message=message)
            print(f"  📤 Progressive delivery sent")
        except ImportError:
            print(f"  ℹ️  sessions_yield not available (not in OpenClaw environment)")
        except Exception as e:
            print(f"  ⚠️ Progressive delivery failed: {e}")
    
    def _build_checkpoint_summary(self, stage_name: str, stage_output: Any, checkpoint_type: str) -> str:
        """构建检查点摘要"""
        summary = f"# Solution Design Checkpoint: {stage_name}\n\n"
        summary += f"**Session**: {self.session_id}\n"
        summary += f"**Type**: {self.solution_type}\n"
        summary += f"**Checkpoint**: {checkpoint_type}\n\n"
        
        if stage_name == "planning":
            if isinstance(stage_output, dict):
                analysis = stage_output.get("analysis", {})
                summary += f"## 方案类型: {analysis.get('solution_type', 'N/A')}\n"
                summary += f"## 置信度: {analysis.get('confidence', 'N/A')}\n"
                summary += f"## 核心问题: {analysis.get('core_problem', 'N/A')}\n"
                dimensions = stage_output.get("dimensions", {})
                summary += f"\n## 关键维度\n"
                for dim, info in dimensions.items():
                    summary += f"- {dim}: {'必需' if info.get('required') else '可选'}\n"
        
        elif stage_name == "design":
            if isinstance(stage_output, dict):
                design = stage_output.get("design", {})
                summary += f"## 设计类型: {design.get('type', 'N/A')}\n"
                sections = design.get("sections", {})
                summary += f"\n## 已完成章节 ({len(sections)})\n"
                for section_name in sections.keys():
                    summary += f"- {section_name}\n"
                
                risks = stage_output.get("risks", [])
                if risks:
                    summary += f"\n## 风险 ({len(risks)})\n"
                    for risk in risks[:3]:
                        summary += f"- {risk.get('description', 'N/A')} (严重程度: {risk.get('severity', 'N/A')})\n"
        
        elif stage_name == "deliver":
            if isinstance(stage_output, str):
                summary += stage_output[:2000]
            elif isinstance(stage_output, dict):
                summary += json.dumps(stage_output, indent=2, ensure_ascii=False)[:2000]
        
        return summary
    
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
                # Mock模式返回result字段，正常模式返回output字段
                output_data = result.get("output") or result.get("result")
                outputs.append({
                    "role": worker_role,
                    "output": output_data
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
        P1-001: 使用缓存的 prompt 模板，避免重复 I/O
        """
        # P1-001: 从缓存获取 prompt（自动处理 role 前缀）
        role_key = role.replace('solution_', '')
        role_prompt = self._get_cached_prompt(role_key)
        
        if not role_prompt:
            print(f"⚠️ No prompt found for role: {role_key}")
        
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
            # 注意：result 可能是直接的 results 列表，也可能是嵌套在 output 中
            results_list = None
            
            if "results" in result and isinstance(result["results"], list):
                results_list = result["results"]
            elif "output" in result and isinstance(result["output"], dict) and "results" in result["output"]:
                results_list = result["output"]["results"]
            
            if results_list and isinstance(results_list, list):
                scores = []
                for r in results_list:
                    if isinstance(r, dict):
                        # 检查 output 字段
                        output = r.get("output")
                        if isinstance(output, dict) and "audit_result" in output:
                            audit = output["audit_result"]
                            if isinstance(audit, dict) and "overall_score" in audit:
                                scores.append(float(audit.get("overall_score", 0)))
                        # 如果 output 是字符串，尝试解析 JSON
                        elif isinstance(output, str):
                            try:
                                import json
                                parsed = json.loads(output)
                                if isinstance(parsed, dict) and "audit_result" in parsed:
                                    audit = parsed["audit_result"]
                                    if isinstance(audit, dict) and "overall_score" in audit:
                                        scores.append(float(audit.get("overall_score", 0)))
                            except:
                                pass
                
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
                # 如果 output 是字符串，尝试解析 JSON
                elif isinstance(output, str):
                    try:
                        import json
                        parsed = json.loads(output)
                        if isinstance(parsed, dict):
                            if "overall_score" in parsed:
                                return float(parsed["overall_score"])
                            if "score" in parsed:
                                return float(parsed["score"])
                    except:
                        pass
            
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


    async def run(self) -> Dict[str, Any]:
        """
        P0-FIX: 覆盖 BaseOrchestrator.run()，添加 Blackboard、QualityGate、渐进交付
        """
        try:
            self.state = PipelineState.RUNNING
            print(f"\n{'='*60}")
            print(f"PIPELINE START: {self.domain_config.name}")
            print(f"Session: {self.session_id}")
            print(f"Stages: {len(self.domain_config.pipeline)}")
            print(f"{'='*60}")
            
            for stage_idx, stage in enumerate(self.domain_config.pipeline):
                self.context.current_stage = stage_idx
                
                print(f"\n{'='*60}")
                print(f"STAGE {stage_idx + 1}/{len(self.domain_config.pipeline)}: {stage.name}")
                print(f"Type: {stage.stage_type}")
                print(f"{'='*60}")
                
                # 执行阶段
                result = await self._execute_stage(stage)
                
                if not result.get("success"):
                    self.state = PipelineState.FAILED
                    # P0-FIX: 保存错误状态到 Blackboard
                    self._save_to_blackboard(stage.name, {"error": result.get("error")})
                    return self._build_result(error=result.get("error"))
                
                # P0-FIX: 保存阶段产物到 Blackboard
                self._save_to_blackboard(stage.name, result.get("output"))
                
                # P0-FIX: 应用质量门禁
                quality_result = self._apply_quality_gate(result.get("output"), stage.name)
                
                # P0-FIX: 渐进交付检查点
                self._deliver_checkpoint(stage.name, result.get("output"))
                
                # 保存阶段输出到内存上下文
                self.context.stage_outputs[stage.name] = result.get("output")
                
                # 如果是迭代阶段，处理收敛检测
                if stage.stage_type == "iterative":
                    score = self._extract_score(result.get("output"))
                    self.context.scores.append(score)
                    self.convergence.add_score(score)
                    
                    converged, reason = self.convergence.check()
                    print(f"  Score: {score:.2%}, Converged: {converged} ({reason})")
                    
                    if converged:
                        self.state = PipelineState.CONVERGED
                        return self._build_result(
                            iterations=self.context.current_iteration,
                            final_score=score,
                            convergence_reason=reason
                        )
            
            # 所有阶段完成但未收敛
            self.state = PipelineState.STALLED
            return self._build_result(
                iterations=self.context.current_iteration,
                final_score=self.context.scores[-1] if self.context.scores else 0,
                convergence_reason="pipeline_completed_without_convergence"
            )
            
        except CircuitBreakerOpen as e:
            self.state = PipelineState.CIRCUIT_BREAKER
            return self._build_result(error=str(e))
        except asyncio.TimeoutError:
            self.state = PipelineState.TIMEOUT
            return self._build_result(error="Pipeline timeout")
        except Exception as e:
            self.state = PipelineState.FAILED
            import traceback
            traceback.print_exc()
            return self._build_result(error=str(e))


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
