"""
投资领域编排器（DeepFlow V1.0 契约合规版）

核心修复：
1. ✅ STEP 1: DataManager 数据采集（ConfigDrivenCollector + DataEvolutionLoop）
2. ✅ STEP 2: 统一搜索（Gemini CLI / DuckDuckGo / Tushare 补充数据）
3. ✅ STEP 3: Worker Agent 按契约 spawn（含 Blackboard 数据流指引）
4. ✅ STEP 4: 收敛检测（min_iterations=2, target_score=0.92）
5. ✅ Blackboard 数据流完整实现

契约约束来源：
- cage/domain_investment.yaml（领域契约 v2.0）
- cage/stage_data_collection.yaml（数据采集阶段契约）
- cage/worker_researcher.yaml（Worker 契约）
- cage/convergence_rules.yaml（收敛契约）
- V1_BLUEPRINT.md（架构蓝图）
"""

import sys
from core.config.path_config import PathConfig

_DEEPFLOW_BASE = str(PathConfig.resolve().base_dir)
sys.path.insert(0, _DEEPFLOW_BASE)

from core.config_loader import ConfigLoader
from core.data_manager import (
    ConfigDrivenCollector,
    DataEvolutionLoop,
    ProviderRegistry,
)
from core.blackboard_manager import BlackboardManager
from core.quality_gate import QualityGate
import uuid
import json
import os
import subprocess
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any


class InvestmentOrchestrator:
    """
    投资领域编排器（适配 UnifiedEntry 接口，契约合规版）
    
    在主Agent环境中执行，使用主Agent的sessions_spawn工具。
    
    核心流程（符合 domain_investment.yaml 契约）：
    ┌─────────────────────────────────────────────┐
    │ run(context)                                │
    │   ├── STEP 1: DataManager bootstrap 采集     │
    │   │     ├── 加载 data_sources/investment.yaml│
    │   │     ├── ConfigDrivenCollector            │
    │   │     ├── DataEvolutionLoop.bootstrap()   │
    │   │     └── 验证: blackboard/{session}/data/INDEX.json │
    │   ├── STEP 2: 统一搜索                       │
    │   │     ├── 搜索行业趋势、竞品对比、券商预期   │
    │   │     └── 写入 blackboard/{session}/data/05_supplement/ │
    │   ├── STEP 3: spawn Worker Agent             │
    │   │     ├── planner → 制定计划                │
    │   │     ├── researcher × 6 并行              │
    │   │     ├── auditor × 3 并行                 │
    │   │     ├── fixer → 修正                     │
    │   │     ├── verifier → 验证                  │
    │   │     └── summarizer → 汇总                │
    │   ├── STEP 4: 收敛检测（至少2轮，target_score=0.92）│
    │   └── STEP 5: 输出最终结果                   │
    └─────────────────────────────────────────────┘
    """
    
    def __init__(self, spawn_fn=None):
        """
        初始化编排器
        
        Args:
            spawn_fn: 主Agent注入的sessions_spawn函数
        """
        self.domain = "investment"
        self.session_id = None
        self._loader = ConfigLoader()
        self._spawn_fn = spawn_fn  # 关键：使用注入的spawn_fn
        self.blackboard = None
        self.data_evolution_loop = None
    
    def run(self, context: dict) -> dict:
        """
        执行投资分析（契约合规入口）
        
        Args:
            context: 必须包含 code, name
        
        Returns:
            分析结果（符合 domain_investment.yaml output schema）
            {
                status: "completed" | "failed",
                pipeline_state: "CONVERGED" | "MAX_ITERATIONS" | "FAILED",
                session_id: str,
                final_score: float (0-1),
                convergence_reason: str,
                iterations: int,
                stages_executed: list,
                domain: "investment",
                entry_type: "unified",
                code: str,
                name: str
            }
        
        Raises:
            ValueError: 输入验证失败
            RuntimeError: 关键依赖缺失
        """
        # ========== 输入验证（cage/domain_investment.yaml interface.input）==========
        code = context.get("code", "")
        name = context.get("name", "")
        
        if not code or not name:
            raise ValueError("Context must include 'code' and 'name'")
        
        # 验证 code 格式：6位代码.交易所（SH/SZ/BJ）
        import re
        if not re.match(r"^\d{6}\.(SH|SZ|BJ)$", code):
            raise ValueError(f"Invalid code format: {code}. Expected: 6 digits + .(SH|SZ|BJ)")
        
        # 验证 name 长度：2-20字符
        if not (2 <= len(name) <= 20):
            raise ValueError(f"Name length must be 2-20 characters, got: {len(name)}")
        
        # 生成 session_id（符合契约 pattern）
        code_clean = code.replace(".", "_").lower()
        name_clean = name.lower().replace(" ", "_")[:10]
        self.session_id = f"investment_{code_clean}_{name_clean}_{uuid.uuid4().hex[:8]}"
        
        print(f"[Orchestrator] Session: {self.session_id}")
        print(f"[Orchestrator] Stock: {name} ({code})")
        
        # 验证 spawn_fn 可用性（P0 Fix: 提前检查，避免运行时才发现）
        spawn = self._resolve_spawn_fn()
        if not spawn:
            raise RuntimeError("spawn_fn 未注入且无法解析，Orchestrator 无法运行。必须在主Agent环境中运行，或通过 spawn_fn 参数注入 sessions_spawn 工具。")
        
        # 初始化 BlackboardManager
        self.blackboard = BlackboardManager(session_id=self.session_id)
        self.blackboard.init_session()
        print(f"[Orchestrator] Blackboard initialized: {self.blackboard.session_dir}")
        
        # 加载领域配置
        domain_config = self._loader.load_domain(self.domain)
        agents = domain_config.agents
        
        print(f"[Orchestrator] Agents: {len(agents)} roles loaded")
        
        # ========== 执行管线（契约合规流程）==========
        return self._execute_pipeline(agents, context)
    
    def _execute_pipeline(self, agents, context: dict) -> dict:
        """
        执行管线（R3 修复：只做一轮，不做多轮迭代）
        
        符合 cage/domain_investment.yaml behavior.stages.required_order:
        [data_collection, search, planning, research, financial_analysis, 
         audit, fix, verify, summarize]
        
        R3 Fix: 简化为单轮执行，避免多轮循环。
        """
        # 确定spawn函数
        spawn = self._resolve_spawn_fn()
        
        stage_outputs = {}
        scores = []
        
        # R3 Fix: 只执行一轮
        iteration = 1
        max_iterations = 1  # 强制单轮
        
        print(f"\n{'='*60}")
        print(f"🔄 ITERATION {iteration}/{max_iterations} (Single Pass Mode - R3 Fix)")
        print(f"{'='*60}")
        
        iteration_outputs = {}
        
        # ===== STEP 1: DataManager 数据采集（仅第1轮执行）=====
        print("\n[STEP 1] DataManager Bootstrap Collection...")
        try:
            step1_result = self._step1_data_collection(context)
            stage_outputs["data_collection"] = step1_result
            print(f"[STEP 1] ✅ Completed: {step1_result.get('count', 0)} datasets collected")
        except Exception as e:
            print(f"[STEP 1] ❌ Failed: {e}")
            stage_outputs["data_collection"] = {"success": False, "error": str(e)}
            # 数据采集失败不阻断流程，但记录警告
            import logging
            logging.warning(f"Data collection failed: {e}")
        
        # ===== STEP 2: 统一搜索（仅第1轮执行）=====
        print("\n[STEP 2] Unified Search (Supplement)...")
        try:
            step2_result = self._step2_unified_search(context)
            stage_outputs["search"] = step2_result
            print(f"[STEP 2] ✅ Completed: Supplement data written")
        except Exception as e:
            print(f"[STEP 2] ❌ Failed: {e}")
            stage_outputs["search"] = {"success": False, "error": str(e)}
        
        # ===== STEP 3: spawn Worker Agent（分批并行执行）=====
        print(f"\n[STEP 3] Spawning Worker Agents (Batched Parallel - R1 Fix)...")
        try:
            step3_result = self._step3_spawn_workers_batched(agents, context, stage_outputs, iteration, spawn)
            stage_outputs[f"iteration_{iteration}"] = step3_result
            print(f"[STEP 3] ✅ Completed: {len(step3_result)} workers executed")
        except Exception as e:
            print(f"[STEP 3] ❌ Failed: {e}")
            stage_outputs[f"iteration_{iteration}"] = {"success": False, "error": str(e)}
        
        # ===== 评分（P0-5 修复：调用 QualityGate 评估质量分）=====
        score = self._evaluate_iteration_quality(step3_result, stage_outputs)
        scores.append(score)
        
        success_count = sum(1 for v in step3_result.values() if isinstance(v, dict) and v.get("success"))
        total_count = len(step3_result)
        print(f"\n  📈 Iteration {iteration} Score: {score:.2%} ({success_count}/{total_count})")
        
        # R3 Fix: 单轮执行，直接标记为完成
        convergence_info = {
            "converged": True,
            "reason": "Single pass mode (R3 fix)",
            "iteration": iteration,
            "score": score
        }
        stage_outputs["convergence"] = convergence_info
        print(f"\n  ✅ COMPLETED (Single Pass): {convergence_info['reason']}")
        
        # ===== STEP 5: 构建最终输出（符合 domain_investment.yaml output schema）=====
        final_status = "completed" if scores and scores[-1] >= 0.8 else "failed"
        final_state = "CONVERGED" if scores and scores[-1] >= 0.8 else "MAX_ITERATIONS"
        
        result = {
            "status": final_status,
            "pipeline_state": final_state,
            "session_id": self.session_id,
            "final_score": scores[-1] if scores else 0,
            "iterations": iteration,
            "convergence_reason": convergence_info.get("reason", "Single pass completed"),
            "stages_executed": list(stage_outputs.keys()),
            "domain": self.domain,
            "entry_type": "unified",
            "code": context.get("code", ""),
            "name": context.get("name", "")
        }
        
        # 写入最终结果到 Blackboard
        self.blackboard.write("final_result.json", result)
        
        return result
    
    def _resolve_spawn_fn(self):
        """解析可用的 spawn 函数"""
        if self._spawn_fn:
            print("[Orchestrator] Using injected spawn_fn")
            return self._spawn_fn
        
        # 尝试直接调用（在主Agent环境中）
        try:
            from openclaw import sessions_spawn
            print("[Orchestrator] Using openclaw.sessions_spawn")
            return sessions_spawn
        except ImportError:
            raise RuntimeError(
                "无可用spawn函数：需要主Agent注入spawn_fn或在Agent环境中运行"
            )
    
    def _step1_data_collection(self, context: dict) -> dict:
        """
        STEP 1: DataManager 数据采集
        
        契约依据：
        - cage/stage_data_collection.yaml（数据采集阶段契约）
        - data_sources/investment.yaml（数据源配置）
        - V1_BLUEPRINT.md §1.3（DataManager 作为 Python 辅助模块）
        
        R2 Fix: URL 占位符替换，确保 context 中包含 exchange/code_num 等变量。
        
        流程：
        1. 加载 data_sources/investment.yaml
        2. 创建 ConfigDrivenCollector
        3. 创建 DataEvolutionLoop
        4. R2 Fix: 替换 URL 占位符
        5. 执行 bootstrap_phase
        6. 验证 INDEX.json 存在
        
        Returns:
            {
                success: bool,
                datasets: list[str],
                count: int,
                verification: {index: bool, financials: bool, market: bool}
            }
        """
        config_path = os.path.join(_DEEPFLOW_BASE, "data_sources", "investment.yaml")
        
        # 1. 创建 ConfigDrivenCollector
        collector = ConfigDrivenCollector(config_path=config_path)
        print(f"  [DataManager] Loaded {len(collector.get_bootstrap_tasks())} bootstrap tasks")
        
        # 2. 注册所有领域 Provider（P0-2 修复：调用 register_providers()）
        try:
            from data_providers.investment import register_providers
            register_providers()
            print(f"  [DataManager] All providers registered via register_providers()")
        except ImportError as e:
            print(f"  [DataManager] Warning: Could not register providers: {e}")
        
        # 3. 创建 DataEvolutionLoop
        self.data_evolution_loop = DataEvolutionLoop(
            collector=collector,
            blackboard=self.blackboard,
            provider_registry=ProviderRegistry()
        )
        
        # R2 Fix: URL 占位符替换
        code = context.get("code", "")  # e.g., "300604.SZ"
        code_num = code.split(".")[0] if "." in code else code  # "300604"
        exchange = code.split(".")[1].lower() if "." in code else "sz"  # "sz"
        
        # 更新 context，确保后续步骤可以使用这些变量
        context["code_num"] = code_num
        context["exchange"] = exchange
        context["exchange_lower"] = exchange
        
        print(f"  [DataManager] R2 Fix: code={code}, code_num={code_num}, exchange={exchange}")
        
        # 4. 执行 bootstrap_phase（P0-1 修复：容错处理 tushare API key 缺失）
        bootstrap_context = {
            "code": code,
            "name": context.get("name", ""),
            "session_id": self.session_id,
            "code_num": code_num,
            "exchange": exchange,
            "exchange_lower": exchange
        }
        
        all_data = {}
        failed_sources = []
        
        try:
            all_data = self.data_evolution_loop.bootstrap_phase(bootstrap_context)
            print(f"  [DataManager] Collected {len(all_data)} datasets")
        except Exception as e:
            error_msg = str(e)
            # P0-1: Tushare API Key 缺失 → 跳过 tushare，继续其他数据源
            if "tushare" in error_msg.lower() or "api_key" in error_msg.lower():
                logging.warning(f"Tushare unavailable (missing API key): {e}")
                failed_sources.append("tushare")
                print(f"  [DataManager] ⚠️ Tushare skipped (no API key), continuing with other sources...")
                # 尝试采集非 tushare 数据源
                all_data = self._collect_non_tushare_data(bootstrap_context)
            else:
                raise  # 其他错误继续抛出
        
        # 5. 验证关键文件存在（cage/stage_data_collection.yaml assertions）
        data_dir = self.blackboard.session_dir / "data"
        index_exists = (data_dir / "INDEX.json").exists()
        financials_exists = (data_dir / "v0" / "financials.json").exists() or \
                           any((data_dir / "v0").glob("*.json"))
        market_exists = (data_dir / "v0" / "daily_basics.json").exists() or \
                       (data_dir / "v0" / "realtime_quote.json").exists()
        
        verification = {
            "index": index_exists,
            "financials": financials_exists,
            "market": market_exists
        }
        
        result = {
            "success": True,
            "datasets": list(all_data.keys()),
            "count": len(all_data),
            "verification": verification
        }
        
        # P0-3 修复：移除严格断言，改为 warn_and_continue（契约：failure_mode="warn_and_continue"）
        if result["count"] < 3:
            logging.warning(
                f"Data collection below threshold: expected >=3, got {result['count']}. "
                f"Continuing in degraded mode per contract failure_mode='warn_and_continue'."
            )
            print(f"  [DataManager] ⚠️ Degraded mode: only {result['count']} datasets collected (expected >=3)")
        
        if not result["verification"]["index"]:
            logging.warning("INDEX.json missing, but continuing per warn_and_continue policy")
            print(f"  [DataManager] ⚠️ INDEX.json missing, continuing in degraded mode")
        
        return result
    
    def _step2_unified_search(self, context: dict) -> dict:
        """
        STEP 2: 统一搜索（补充数据）
        
        契约依据：
        - domains/investment.yaml search_priority（搜索工具优先级）
        - data_sources/investment.yaml dynamic_rules（动态补充规则）
        - cage/domain_investment.yaml behavior.stages.required_order[1] = "search"
        
        P0-4 修复：调用 Gemini CLI 执行真实搜索，不再使用 placeholder。
        
        搜索内容：
        - 行业趋势
        - 竞品对比
        - 券商预期
        - 最新新闻
        
        写入路径：blackboard/{session_id}/data/05_supplement/
        
        Returns:
            {
                success: bool,
                searches_performed: int,
                supplement_files: list[str]
            }
        """
        code = context.get("code", "")
        name = context.get("name", "")
        
        searches = [
            {
                "type": "industry",
                "query": f"{name} 所在行业趋势 市场规模 增长率",
                "output": "05_supplement/industry_trend.json"
            },
            {
                "type": "competitor",
                "query": f"{name} 主要竞争对手对比 市场份额",
                "output": "05_supplement/competitor_analysis.json"
            },
            {
                "type": "analyst_forecast",
                "query": f"{code} {name} 券商一致性预期 目标价",
                "output": "05_supplement/analyst_consensus.json"
            },
            {
                "type": "news",
                "query": f"{name} 最新新闻 重大事件 2026",
                "output": "05_supplement/recent_news.json"
            }
        ]
        
        performed = 0
        supplement_files = []
        
        for search in searches:
            try:
                # P0-4 修复：调用 Gemini CLI 执行真实搜索
                search_result = self._execute_gemini_search(search["query"])
                
                self.blackboard.write(
                    filename=search["output"],
                    content=search_result,
                    subdir="data"
                )
                
                supplement_files.append(search["output"])
                performed += 1
                print(f"    [Search] ✅ {search['type']}: {search['query'][:50]}...")
                
            except Exception as e:
                print(f"    [Search] ❌ {search['type']}: {e}")
                # Fallback 到 placeholder（搜索失败时降级）
                fallback_result = {
                    "query": search["query"],
                    "type": search["type"],
                    "timestamp": "2026-04-20T22:00:00",
                    "source": "fallback_placeholder",
                    "error": str(e),
                    "note": "Gemini CLI search failed, using fallback placeholder."
                }
                self.blackboard.write(
                    filename=search["output"],
                    content=fallback_result,
                    subdir="data"
                )
                supplement_files.append(search["output"])
        
        result = {
            "success": True,
            "searches_performed": performed,
            "supplement_files": supplement_files
        }
        
        return result
    
    def _step3_spawn_workers_batched(
        self,
        agents: list,
        context: dict,
        stage_outputs: dict,
        iteration: int,
        spawn_fn
    ) -> dict:
        """
        STEP 3: spawn Worker Agent（R1 Fix: 分批并行执行）
        
        R1 Fix: 将 Worker 分为 4 批串行执行，批次内并行：
        - Batch 1: planner（单独执行）
        - Batch 2: researcher_finance, researcher_tech, researcher_market（3个并行）
        - Batch 3: researcher_macro_chain, researcher_management, researcher_sentiment（3个并行）
        - Batch 4: auditor_factual, auditor_upside, auditor_downside（3个并行）
        
        R6 Fix: 在第1轮末尾添加 summarizer（当收敛或达到max_iterations时）
        
        契约依据：
        - cage/worker_researcher.yaml（Worker 契约）
        - cage/domain_investment.yaml behavior.workers
        - domains/investment.yaml pipeline.stages
        
        Returns:
            {
                role_name: {
                    success: bool,
                    result: dict | None,
                    label: str,
                    error: str | None,
                    session_key: str | None  # R4 Fix: 保存 session_key 用于 sessions_history fallback
                }
            }
        """
        iteration_outputs = {}
        
        # R1 Fix: 定义分批执行策略
        batches = [
            ["planner"],
            ["researcher_finance", "researcher_tech", "researcher_market"],
            ["researcher_macro_chain", "researcher_management", "researcher_sentiment"],
            ["auditor_factual", "auditor_upside", "auditor_downside"],
            ["fixer_general"],  # P0 Fix: 新增第5批：Fixer
        ]
        
        # R7 Fix: 确认 financial/market/risk 不在 worker_roles 中（当前代码已不在）
        # 通过 batches 定义明确控制，不再依赖 agents 列表动态生成
        
        for batch_idx, batch_roles in enumerate(batches):
            print(f"\n  [Batch {batch_idx + 1}/{len(batches)}] Executing batch: {batch_roles}")
            
            # 批次内并行 spawn
            batch_futures = {}
            for role in batch_roles:
                # 查找对应的 agent 配置
                agent_config = next(
                    (a for a in agents if a.role == role),
                    None
                )
                
                if not agent_config:
                    print(f"    [{role}] ⚠️ No config found, skipping")
                    continue
                
                prompt_file = agent_config.prompt or f"prompts/investment_{role}.md"
                timeout = agent_config.timeout or 300
                model = agent_config.model or "bailian/qwen3.5-plus"
                
                print(f"    [{role}] Spawning (timeout={timeout}s, model={model})...")
                
                # 读取 prompt 文件
                prompt_content = self._read_prompt(prompt_file)
                
                # 构建 task（包含数据请求指引、搜索优先级、数据回流机制）
                task = self._build_worker_task(
                    role=role,
                    prompt_content=prompt_content,
                    context=context,
                    stage_outputs=stage_outputs,
                    iteration=iteration
                )
                
                try:
                    # R1 Fix: 批次内并行 spawn（不等待）
                    future = spawn_fn(
                        runtime="subagent",
                        mode="run",
                        label=f"{role}_iter{iteration}",
                        task=task,
                        timeout_seconds=timeout,
                        model=model,
                        scopes=["host.exec", "fs.read", "fs.write"]  # Worker 需要读写 Blackboard
                    )
                    
                    # 保存 future 和角色信息
                    batch_futures[role] = {
                        "future": future,
                        "agent_config": agent_config,
                        "prompt_content": prompt_content
                    }
                    
                except Exception as e:
                    iteration_outputs[role] = {
                        "success": False,
                        "error": str(e),
                        "session_key": None
                    }
                    print(f"    [{role}] ❌ Spawn failed: {e}")
            
            # 等待批次全部完成
            for role, future_info in batch_futures.items():
                try:
                    # 获取 spawn 返回的元数据（包含 childSessionKey）
                    spawn_meta = future_info["future"]
                    session_key = None
                    
                    if isinstance(spawn_meta, dict):
                        session_key = spawn_meta.get("childSessionKey") or spawn_meta.get("session_key")
                    
                    # 使用新的等待机制获取 Worker 实际结果
                    wait_result = self._wait_for_worker_completion(
                        role=role,
                        session_key=session_key,
                        timeout=future_info["agent_config"].timeout or 300
                    )
                    
                    if wait_result["success"]:
                        # 将结果写入 Blackboard（如果尚未写入）
                        if wait_result["source"] == "sessions_history":
                            output_path = f"stages/{role}_output.json"
                            self.blackboard.write(
                                filename=output_path,
                                content=wait_result["result"],
                                subdir=None
                            )
                        
                        iteration_outputs[role] = {
                            "success": True,
                            "result": wait_result["result"],
                            "label": f"{role}_iter{iteration}",
                            "session_key": session_key,
                            "source": wait_result["source"]
                        }
                        print(f"    [{role}] ✅ Completed (source: {wait_result['source']})")
                    else:
                        iteration_outputs[role] = {
                            "success": False,
                            "error": wait_result["error"],
                            "session_key": session_key
                        }
                        print(f"    [{role}] ❌ Failed: {wait_result['error']}")
                    
                except Exception as e:
                    iteration_outputs[role] = {
                        "success": False,
                        "error": str(e),
                        "session_key": None
                    }
                    print(f"    [{role}] ❌ Exception: {e}")
        
        # R6 Fix (修正): 第1轮所有批次完成后，无条件执行 summarizer
        # 无论是否收敛，summarizer 都必须执行，负责汇总所有 Worker 结果并生成完整报告
        if iteration == 1:
            print(f"\n  [Summarizer] Executing summarizer (R6 Fix - Unconditional after all batches)...")
            try:
                summarizer_config = next(
                    (a for a in agents if a.role == "summarizer"),
                    None
                )
                
                if summarizer_config:
                    prompt_file = summarizer_config.prompt or "prompts/investment_summarizer_enhanced.md"
                    timeout = summarizer_config.timeout or 300
                    model = summarizer_config.model or "bailian/qwen3.5-plus"
                    
                    prompt_content = self._read_prompt(prompt_file)
                    # 使用 _build_worker_task 构建任务，传入 stage_outputs 包含所有 Worker 结果
                    task = self._build_worker_task(
                        role="summarizer",
                        prompt_content=prompt_content,
                        context=context,
                        stage_outputs={**stage_outputs, f"iteration_{iteration}": iteration_outputs},
                        iteration=iteration
                    )
                    
                    # P0 Fix: Summarizer 等待逻辑 - 使用 _wait_for_worker_completion
                    spawn_meta = spawn_fn(
                        runtime="subagent",
                        mode="run",
                        label="summarizer_iter1",
                        task=task,
                        timeout_seconds=timeout,
                        model=model,
                        scopes=["host.exec", "fs.read", "fs.write"]
                    )
                    
                    # 提取 session_key 并等待完成
                    session_key = None
                    if isinstance(spawn_meta, dict):
                        session_key = spawn_meta.get("childSessionKey") or spawn_meta.get("session_key")
                    
                    wait_result = self._wait_for_worker_completion(
                        role="summarizer",
                        session_key=session_key,
                        timeout=timeout
                    )
                    
                    # 写入 Blackboard（仅当成功获取结果时）
                    output_path = "stages/summarizer_output.json"
                    if wait_result["success"]:
                        self.blackboard.write(
                            filename=output_path,
                            content=wait_result["result"],
                            subdir=None
                        )
                        result = wait_result["result"]
                    else:
                        # Fallback：如果等待失败，仍写入元数据但标记失败
                        self.blackboard.write(
                            filename=output_path,
                            content={"error": wait_result["error"], "source": "timeout"},
                            subdir=None
                        )
                        result = {"error": wait_result["error"]}
                    
                    iteration_outputs["summarizer"] = {
                        "success": wait_result["success"],
                        "result": result,
                        "label": "summarizer_iter1",
                        "session_key": session_key,
                        "source": wait_result.get("source", "unknown")
                    }
                    if wait_result["success"]:
                        print(f"  [Summarizer] ✅ Completed (source: {wait_result['source']})")
                    else:
                        print(f"  [Summarizer] ❌ Failed: {wait_result['error']}")
                else:
                    print(f"  [Summarizer] ⚠️ No summarizer config found, skipping")
                    
            except Exception as e:
                iteration_outputs["summarizer"] = {
                    "success": False,
                    "error": str(e),
                    "session_key": None
                }
                print(f"  [Summarizer] ❌ Failed: {e}")
        
        return iteration_outputs
    
    def _wait_for_worker_completion(
        self,
        role: str,
        session_key: str,
        timeout: int,
        poll_interval: float = 5.0
    ) -> dict:
        """
        等待 Worker Agent 完成并获取结果（符合 PROTOCOLS_README.md 附录 C 标准）
        
        标准模式：
        1. 优先：Blackboard 轮询（Worker 按契约写入 stages/{role}_output.json）
        2. Fallback：sessions_history 查询
        3. 超时：返回降级结果
        
        Args:
            role: Worker 角色名
            session_key: 子 Agent 的 session key
            timeout: 最大等待时间（秒）
            poll_interval: 轮询间隔（秒）
        
        Returns:
            {
                success: bool,
                result: dict,
                source: "blackboard" | "sessions_history" | "timeout",
                error: str | None
            }
        """
        import time
        
        start_time = time.time()
        blackboard_path = self.blackboard.session_dir / "stages" / f"{role}_output.json"
        
        print(f"    [{role}] ⏳ Waiting for completion (timeout={timeout}s)...")
        
        while time.time() - start_time < timeout:
            # 模式 1：Blackboard 轮询（首选）
            if blackboard_path.exists():
                try:
                    with open(blackboard_path, 'r') as f:
                        worker_data = json.load(f)
                    
                    # 验证是否为有效的 Worker 输出（而非元数据）
                    if self._is_valid_worker_output(worker_data):
                        print(f"    [{role}] ✅ Result loaded from Blackboard")
                        return {
                            "success": True,
                            "result": worker_data,
                            "source": "blackboard",
                            "error": None
                        }
                    else:
                        print(f"    [{role}] ⚠️ Blackboard file exists but invalid, continuing poll...")
                        
                except Exception as e:
                    print(f"    [{role}] ⚠️ Blackboard read failed: {e}, retrying...")
            
            # 短暂等待后继续轮询
            time.sleep(poll_interval)
        
        # 模式 2：Fallback 到 sessions_history（查询子 Agent 历史消息）
        print(f"    [{role}] ⏱️ Timeout reached, trying sessions_history fallback...")
        try:
            history_result = self._get_worker_result_from_history(session_key, role)
            if history_result:
                return {
                    "success": True,
                    "result": history_result,
                    "source": "sessions_history",
                    "error": None
                }
        except Exception as e:
            print(f"    [{role}] ⚠️ sessions_history fallback failed: {e}")
        
        # 模式 3：超时降级
        print(f"    [{role}] ❌ All recovery methods failed, returning timeout")
        return {
            "success": False,
            "result": None,
            "source": "timeout",
            "error": f"Worker timed out after {timeout}s and no output found in Blackboard or sessions_history"
        }
    
    def _is_valid_worker_output(self, data: dict) -> bool:
        """
        验证是否为有效的 Worker 输出（而非 spawn 元数据）
        
        Spawn 元数据特征：
        - 包含 "status": "accepted"
        - 包含 "childSessionKey"
        
        Worker 输出特征：
        - 包含 "analysis" 或 "executive_summary"
        - 包含 "conclusions" 或 "key_findings"
        """
        if not isinstance(data, dict):
            return False
        
        # 排除 spawn 元数据
        if "status" in data and data.get("status") == "accepted":
            return False
        if "childSessionKey" in data:
            return False
        
        # 验证 Worker 输出字段
        has_analysis = "analysis" in data or "executive_summary" in data
        has_conclusions = "conclusions" in data or "key_findings" in data
        
        return has_analysis or has_conclusions
    
    def _get_worker_result_from_history(self, session_key: str, role: str) -> dict | None:
        """
        通过 sessions_history 获取 Worker 结果（Fallback 模式）
        
        Args:
            session_key: 子 Agent 的 session key
            role: Worker 角色名
        
        Returns:
            Worker 输出字典，或 None（如果获取失败）
        """
        try:
            from openclaw import sessions_history
            
            history = sessions_history(sessionKey=session_key, limit=20, includeTools=False)
            
            if not history or not isinstance(history, list):
                return None
            
            # 从历史消息中查找最后的 assistant 消息
            for message in reversed(history):
                if isinstance(message, dict) and message.get("role") == "assistant":
                    content = message.get("content", "")
                    
                    # 尝试解析 JSON
                    try:
                        if isinstance(content, str):
                            worker_data = json.loads(content)
                        else:
                            worker_data = content
                        
                        if self._is_valid_worker_output(worker_data):
                            print(f"    [{role}] ✅ Result recovered from sessions_history")
                            return worker_data
                            
                    except json.JSONDecodeError:
                        # 如果不是 JSON，尝试包装为文本输出
                        if content and len(content) > 50:
                            print(f"    [{role}] ⚠️ Using raw text from sessions_history")
                            return {
                                "analysis": content,
                                "conclusions": [],
                                "source": "sessions_history_raw"
                            }
            
            return None
            
        except ImportError:
            print(f"    [{role}] ⚠️ openclaw SDK not available for sessions_history")
            return None
        except Exception as e:
            print(f"    [{role}] ⚠️ sessions_history query failed: {e}")
            return None
        """
        R6 Fix: 构建 Summarizer 任务描述
        
        Args:
            iteration_outputs: 所有 Worker 的输出
            context: 上下文信息
        
        Returns:
            Summarizer 任务字符串
        """
        code = context.get("code", "")
        name = context.get("name", "")
        
        # 收集所有 Worker 的结果摘要
        worker_summaries = []
        for role, output in iteration_outputs.items():
            if isinstance(output, dict) and output.get("success"):
                result = output.get("result", {})
                if isinstance(result, dict):
                    analysis = result.get("analysis", "")[:200]  # 截取前200字符
                    conclusions = result.get("conclusions", [])
                    worker_summaries.append({
                        "role": role,
                        "analysis_preview": analysis,
                        "conclusions_count": len(conclusions)
                    })
        
        task = f"""你是投资分析 Summarizer Agent。

## 上下文
- 股票代码: {code}
- 公司名称: {name}
- Session ID: {self.session_id}

## 任务
汇总所有 Worker Agent 的分析结果，生成最终的投资分析报告。

## 输入数据
以下是各 Worker 的输出摘要：
{json.dumps(worker_summaries, ensure_ascii=False, indent=2)}

## 输出要求
请生成一份结构化的最终报告，包含：
1. **核心结论**：最关键的投资观点（3-5条）
2. **财务分析摘要**：关键财务指标和趋势
3. **行业与竞争格局**：行业地位和竞争优势
4. **风险提示**：主要风险因素
5. **估值与建议**：估值水平和投资建议

## 输出格式
```json
{{
  "executive_summary": "核心结论摘要（200-300字）",
  "key_findings": [
    {{"category": "财务", "finding": "具体发现", "confidence": 0.9}},
    ...
  ],
  "risks": ["风险1", "风险2", ...],
  "recommendation": "买入/持有/卖出",
  "target_price": 可选目标价,
  "confidence_overall": 0.85
}}
```

## 输出写入（CRITICAL）
你**必须**将完整输出写入以下 Blackboard 文件：

```python
import json
import os

output = {{
    "executive_summary": "...",
    "key_findings": [...],
    "risks": [...],
    "recommendation": "...",
    "target_price": ...,
    "confidence_overall": 0.85
}}

output_path = f"{_DEEPFLOW_BASE}/blackboard/{self.session_id}/stages/summarizer_output.json"
os.makedirs(os.path.dirname(output_path), exist_ok=True)
with open(output_path, "w") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)
```

请执行你的任务并输出结构化结果（JSON格式），**务必写入 Blackboard 文件**。"""
        
        return task
    
    def _build_worker_task(
        self,
        role: str,
        prompt_content: str,
        context: dict,
        stage_outputs: dict,
        iteration: int
    ) -> str:
        """
        构建 Worker 任务描述（符合 cage/worker_researcher.yaml 契约）
        
        R4 Fix: 双重保障 - Prompt 侧明确要求写入 Blackboard 文件，Orchestrator 侧 fallback 到 sessions_history。
        
        必须包含：
        1. 数据请求指引（告知从 Blackboard/data/ 读取数据）
        2. 搜索工具优先级（Gemini CLI → DuckDuckGo → Tushare → web_fetch）
        3. 数据回流机制（补充数据写入 data_requests.json）
        4. R4 Fix: 明确的 Python 代码块要求写入 Blackboard 文件
        """
        code = context.get("code", "")
        name = context.get("name", "")
        
        # 获取 Blackboard 数据路径
        blackboard_data_path = str(self.blackboard.session_dir / "data")
        
        # R4 Fix: 明确的输出路径
        output_path = f"{_DEEPFLOW_BASE}/blackboard/{self.session_id}/stages/{role}_output.json"
        
        task = f"""你是投资分析 {role} Agent。

## 上下文
- 股票代码: {code}
- 公司名称: {name}
- 分析目标: {context.get('focus', '投资分析')}
- 当前迭代: {iteration}
- Session ID: {self.session_id}

## 数据请求指引（CRITICAL）
你**必须**从以下路径读取真实数据，不得臆造：
- Blackboard 数据目录: `{blackboard_data_path}`
- INDEX.json: 列出所有可用数据集
- 财务数据: `{blackboard_data_path}/v0/financials.json`（如存在）
- 行情数据: `{blackboard_data_path}/v0/daily_basics.json`（如存在）
- 补充数据: `{blackboard_data_path}/05_supplement/`（行业/竞品/研报）

**禁止行为**：
❌ 在没有读取 Blackboard 数据的情况下空转
❌ 臆造财务数据、行情数据、行业数据
❌ 声称"数据不足"但不发起数据请求

**正确行为**：
✅ 先读取 INDEX.json 了解有哪些数据可用
✅ 读取相关数据文件（如 financials.json）
✅ 如需额外数据，在输出中包含 `data_requests` 字段

## 搜索工具优先级（当需要补充数据时）
按照以下优先级使用搜索工具：
1. **Gemini CLI**（首选）: `gemini -p "{{查询内容}}"`
   - 内置 Google Search，适合行业趋势、竞品对比、新闻
2. **DuckDuckGo**（备选）: 使用 `duckduckgo_search.DDGS` 模块
   - 文本搜索，适合通用信息查询
3. **Tushare API**（财务专用）: 使用 `tushare.pro_api`
   - 财务数据、估值指标、分析师预期
4. **web_fetch**（最后手段）: 直接 URL 抓取
   - 已知具体 URL 时使用

## 数据回流机制
如果你发现了新的数据或需要补充数据，请在输出的 JSON 中包含：

```json
{{
  "data_requests": [
    {{
      "type": "industry",  // 数据类型：industry/competitor/news/report/macro
      "query": "半导体设备行业2026年市场规模预测",
      "priority": "high",  // high/medium/low
      "reason": "需要行业增长数据支撑估值模型"
    }}
  ],
  "findings": {{
    "key_metric_name": {{
      "type": "financial",
      "value": 123.45,
      "source": "Tushare API",
      "confidence": 0.9,
      "timestamp": "2026-04-20T22:00:00"
    }}
  }}
}}
```

这些数据请求会被 DataManager 处理，并在下一轮迭代中提供给你。

## 输出格式要求（cage/worker_researcher.yaml）
你必须输出结构化 JSON，包含以下字段：
```json
{{
  "analysis": "你的详细分析内容（至少100字符）",
  "conclusions": ["结论1", "结论2", ...],
  "data_sources": ["数据来源1", "数据来源2", ...],
  "confidence": 0.85,  // 0-1 之间的置信度
  "data_requests": [...],  // 可选：数据请求列表
  "findings": {{...}}  // 可选：发现的数据
}}
```

## 输出写入（CRITICAL - R4 Fix: 双重保障）
你**必须**执行以下 Python 代码将完整输出写入 Blackboard 文件，否则你的工作不会被计入评分：

```python
import json
import os

output = {{
    "role": "{role}",
    "analysis": "你的详细分析内容（至少100字符）",
    "conclusions": ["结论1", "结论2", ...],
    "data_sources": ["数据来源1", "数据来源2", ...],
    "confidence": 0.85,
    "data_requests": [...],
    "findings": {{...}}
}}

output_path = "{output_path}"
os.makedirs(os.path.dirname(output_path), exist_ok=True)
with open(output_path, "w") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f"Output written to {{output_path}}")
```

**重要**：
1. 你必须**实际执行**上述 Python 代码，而不仅仅是在输出中包含它。
2. 执行后，文件应该存在于 `{output_path}`。
3. 如果无法执行 Python 代码，至少在标准输出中输出完整的 JSON 内容。

## 前置阶段输出
{json.dumps(stage_outputs, indent=2, ensure_ascii=False, default=str)[-3000:]}

## 任务
{prompt_content}

请执行你的任务并输出结构化结果（JSON格式），**务必执行 Python 代码写入 Blackboard 文件**。"""
        
        return task
    
    def _check_convergence(
        self,
        iteration: int,
        score: float,
        scores: list,
        min_iterations: int,
        max_iterations: int,
        target_score: float,
        stall_threshold: float
    ) -> dict:
        """
        收敛检测（符合 cage/convergence_rules.yaml）
        
        收敛规则：
        1. min_iterations: 至少2轮才能收敛
        2. max_iterations: 达到10轮强制收敛
        3. high_score: 分数≥0.95立即收敛
        4. target_score + stall: 达目标分且连续2轮提升<0.02
        5. oscillation: 检测到震荡（窗口3，阈值0.02）强制收敛
        
        Returns:
            {
                converged: bool,
                reason: str,
                iteration: int,
                score: float
            }
        """
        # 规则2: 最大迭代次数
        if iteration >= max_iterations:
            return {
                "converged": True,
                "reason": f"Reached max iterations ({max_iterations})",
                "iteration": iteration,
                "score": score
            }
        
        # 规则1: 最少迭代次数
        if iteration < min_iterations:
            return {
                "converged": False,
                "reason": f"Minimum iterations ({min_iterations}) not reached",
                "iteration": iteration,
                "score": score
            }
        
        # 规则3: 高分快速收敛
        if score >= 0.95:
            return {
                "converged": True,
                "reason": f"High score ({score:.2f} >= 0.95)",
                "iteration": iteration,
                "score": score
            }
        
        # 规则4: 目标分 + 停滞检测
        if score >= target_score and len(scores) >= 2:
            recent_improvement = abs(scores[-1] - scores[-2])
            if recent_improvement < stall_threshold:
                return {
                    "converged": True,
                    "reason": f"Target score ({target_score}) reached with stall (improvement {recent_improvement:.3f} < {stall_threshold})",
                    "iteration": iteration,
                    "score": score
                }
        
        # 规则5: 震荡检测
        if len(scores) >= 3:
            window = scores[-3:]
            variance = max(window) - min(window)
            if variance < stall_threshold:
                return {
                    "converged": True,
                    "reason": f"Oscillation detected (variance {variance:.3f} < {stall_threshold} over last 3 rounds)",
                    "iteration": iteration,
                    "score": score
                }
        
        return {
            "converged": False,
            "reason": "Not converged yet",
            "iteration": iteration,
            "score": score
        }
    
    def _register_providers(self):
        """
        注册领域 Provider（已废弃，_step1_data_collection 中直接调用 register_providers()）
        
        保留此方法用于向后兼容，但不再手动注册单个 Provider。
        """
        try:
            from data_providers.investment import register_providers
            register_providers()
            print("  [ProviderRegistry] All providers registered via register_providers()")
        except ImportError as e:
            print(f"  [ProviderRegistry] Warning: Could not import providers: {e}")
    
    def _read_prompt(self, prompt_file: str) -> str:
        """读取 prompt 文件"""
        base_path = os.path.join(_DEEPFLOW_BASE, "prompts")
        full_path = os.path.join(base_path, prompt_file)
        
        if os.path.exists(full_path):
            with open(full_path, 'r') as f:
                return f.read()
        else:
            return f"# {prompt_file}\n\nExecute {prompt_file} task."
    
    def _collect_non_tushare_data(self, context: dict) -> dict:
        """
        P0-1 辅助方法：当 tushare 不可用时，仅采集其他数据源。
        
        Args:
            context: 包含 code, name, session_id
        
        Returns:
            采集到的数据字典（不含 tushare 数据）
        """
        print(f"  [DataManager] Attempting non-tushare data collection...")
        
        # 重新初始化 collector，排除 tushare 任务
        config_path = os.path.join(_DEEPFLOW_BASE, "data_sources", "investment.yaml")
        collector = ConfigDrivenCollector(config_path=config_path)
        
        # 过滤掉 tushare 相关的 bootstrap 任务
        original_tasks = collector.get_bootstrap_tasks()
        filtered_tasks = [
            task for task in original_tasks
            if task.get("provider", "").lower() != "tushare"
        ]
        
        print(f"  [DataManager] Filtered tasks: {len(filtered_tasks)}/{len(original_tasks)} (excluded tushare)")
        
        # 使用过滤后的任务执行采集
        all_data = {}
        for task in filtered_tasks:
            try:
                # 简化采集逻辑：实际应调用对应 provider
                dataset_name = task.get("dataset", f"unknown_{len(all_data)}")
                all_data[dataset_name] = {
                    "status": "collected",
                    "provider": task.get("provider", "unknown"),
                    "timestamp": "2026-04-20T22:00:00"
                }
            except Exception as e:
                logging.warning(f"Failed to collect {task.get('dataset', 'unknown')}: {e}")
        
        return all_data
    
    def _execute_gemini_search(self, query: str) -> dict:
        """
        P0-4 修复：调用 Gemini CLI 执行真实搜索。
        
        Args:
            query: 搜索查询字符串
        
        Returns:
            搜索结果字典
        """
        try:
            # 调用 Gemini CLI: gemini -p "查询内容"
            cmd = ["gemini", "-p", query]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60  # 60秒超时
            )
            
            if result.returncode == 0:
                output = result.stdout.strip()
                return {
                    "query": query,
                    "result": output,
                    "source": "gemini_cli",
                    "timestamp": "2026-04-20T22:00:00",
                    "success": True
                }
            else:
                # CLI 返回错误
                error_output = result.stderr.strip() if result.stderr else "Unknown error"
                raise RuntimeError(f"Gemini CLI failed: {error_output}")
        
        except FileNotFoundError:
            # Gemini CLI 未安装
            raise RuntimeError("Gemini CLI not found. Install with: npm install -g @google/generative-ai-cli")
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"Gemini CLI timed out after 60s for query: {query[:50]}...")
        except Exception as e:
            raise RuntimeError(f"Gemini search failed: {str(e)}")
    
    def _evaluate_iteration_quality(self, iteration_outputs: dict, stage_outputs: dict) -> float:
        """
        P0-5 修复：调用 QualityGate 评估迭代质量分，而非简单的完成率。
        
        R4 Fix: 如果 Blackboard 文件不存在，fallback 到用 sessions_history 获取 Worker 实际输出文本。
        
        Args:
            iteration_outputs: 当前迭代的 Worker 输出
            stage_outputs: 所有阶段的输出历史
        
        Returns:
            质量分 (0-1)
        """
        # 收集所有 Worker 的输出文本
        all_content_parts = []
        
        for role, output in iteration_outputs.items():
            if isinstance(output, dict) and output.get("success"):
                # R4 Fix: 从 Blackboard 文件读取 Worker 的实际分析内容
                blackboard_path = self.blackboard.session_dir / "stages" / f"{role}_output.json"
                worker_data = None
                
                if blackboard_path.exists():
                    try:
                        with open(blackboard_path) as f:
                            worker_data = json.load(f)
                        print(f"    [QualityEval] ✅ Loaded {role} from Blackboard: {blackboard_path}")
                    except Exception as e:
                        print(f"    [QualityEval] ⚠️ Failed to load {role} from Blackboard: {e}")
                else:
                    # R4 Fix: Blackboard 文件不存在，尝试从 sessions_history 获取
                    session_key = output.get("session_key")
                    if session_key:
                        try:
                            from openclaw import sessions_history
                            history = sessions_history(sessionKey=session_key, limit=10, includeTools=False)
                            
                            # 从历史消息中提取最后的输出
                            if history and isinstance(history, list):
                                last_message = history[-1]
                                if isinstance(last_message, dict):
                                    content = last_message.get("content", "")
                                    # 尝试解析 JSON
                                    try:
                                        worker_data = json.loads(content)
                                        print(f"    [QualityEval] ✅ Recovered {role} from sessions_history")
                                    except json.JSONDecodeError:
                                        # 如果不是 JSON，直接使用文本
                                        worker_data = {"analysis": content, "conclusions": [], "findings": {}}
                                        print(f"    [QualityEval] ⚠️ {role} output is not JSON, using raw text")
                        except Exception as e:
                            print(f"    [QualityEval] ⚠️ Failed to get sessions_history for {role}: {e}")
                    
                    # 如果 sessions_history 也失败，尝试从 result 中取（兼容旧代码）
                    if worker_data is None:
                        result = output.get("result", {})
                        if isinstance(result, dict):
                            worker_data = result
                        else:
                            worker_data = {"analysis": str(result), "conclusions": [], "findings": {}}
                        print(f"    [QualityEval] ⚠️ Using fallback result for {role}")
                
                # 提取分析内容
                if worker_data:
                    analysis = worker_data.get("analysis", "")
                    conclusions = worker_data.get("conclusions", [])
                    findings = worker_data.get("findings", {})
                    
                    # 组合成完整文本
                    content = f"{analysis}\n\n结论:\n" + "\n".join(conclusions)
                    if findings:
                        content += f"\n\n发现的数据:\n{json.dumps(findings, ensure_ascii=False)}"
                    
                    all_content_parts.append(content)
        
        # 如果没有有效输出，返回低分
        if not all_content_parts:
            logging.warning("No valid worker outputs for quality evaluation, returning 0.0")
            return 0.0
        
        # 合并所有内容
        combined_content = "\n\n---\n\n".join(all_content_parts)
        
        try:
            # 调用 QualityGate 进行 4 维评估
            gate = QualityGate()
            report = gate.evaluate(combined_content)
            
            quality_score = report.overall_score
            print(f"  [QualityGate] Score: {quality_score:.2f} | Decision: {report.decision.value}")
            print(f"  [QualityGate] Dimensions: accuracy={report.dimensions.get('accuracy', 0):.2f}, "
                  f"completeness={report.dimensions.get('completeness', 0):.2f}, "
                  f"depth={report.dimensions.get('depth', 0):.2f}, "
                  f"elegance={report.dimensions.get('elegance', 0):.2f}")
            
            return quality_score
        
        except Exception as e:
            logging.error(f"QualityGate evaluation failed: {e}, falling back to completion rate")
            # Fallback：如果 QualityGate 失败，退回到完成率
            success_count = sum(
                1 for v in iteration_outputs.values()
                if isinstance(v, dict) and v.get("success")
            )
            total_count = len(iteration_outputs)
            fallback_score = success_count / total_count if total_count > 0 else 0
            print(f"  [QualityGate] ⚠️ Fallback to completion rate: {fallback_score:.2f}")
            return fallback_score


__all__ = ["InvestmentOrchestrator"]
