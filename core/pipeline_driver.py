"""
Deterministic Pipeline Driver — 替代 LLM 状态机

设计原则：
  1. 状态机在 Python 代码中，不在 LLM prompt 中
  2. Agent 只做执行器：调 driver → 执行 action → 报告结果 → 循环
  3. 不解释 completion event，不做决策，不判断状态
  4. 可测试、可调试、可恢复

使用方式：
  cd .deepflow && PYTHONPATH=. python3 -c "
  from core.pipeline_driver import PipelineDriver
  d = PipelineDriver('session_id')
  action = d.next_step()
  print(action)  # Agent 根据 action['type'] 执行对应 tool call
  "
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class PipelineAction:
    """Pipeline Driver 返回的单步动作"""
    type: str  # WRITE_PROMPT | ACQUIRE_RUN | SPAWN_MODULE | WAIT_FOR_MODULE | VALIDATE | RETRY | PIPELINE_COMPLETED | PIPELINE_FAILED
    module: Optional[str] = None
    params: dict = field(default_factory=dict)
    message: str = ""
    
    def to_json(self) -> str:
        return json.dumps({
            'type': self.type,
            'module': self.module,
            'params': self.params,
            'message': self.message,
        }, ensure_ascii=False, indent=2)


class PipelineDriver:
    """
    确定性管线驱动器
    
    替代 Orchestrator Agent 的状态机职责。
    每次调用 next_step() 返回一个明确的动作，Agent 只需执行。
    
    状态转移完全由 Python 代码决定，不依赖 LLM 解释。
    """
    
    MODULES = ['planning', 'research', 'summary']
    
    MODULE_CONFIG = {
        'planning': {
            'files': ['stages/planning_convergence.json'],
            'sizes': {'stages/planning_convergence.json': 10000},
            'timeout': 1800,
            'prompt_template': 'domains/solution_pro/prompts/planning_module.md',
        },
        'research': {
            'files': ['stages/research_digest.json'],
            'sizes': {'stages/research_digest.json': 20000},
            'timeout': 3600,
            'prompt_template': 'domains/solution_pro/prompts/research_module.md',
        },
        'summary': {
            'files': ['stages/solution_document.md', 'stages/final_solution.md'],
            'sizes': {'stages/solution_document.md': 50000, 'stages/final_solution.md': 5000},
            'timeout': 3600,
            'prompt_template': 'domains/solution_pro/prompts/summary_module.md',
        },
    }
    
    def __init__(self, session_id: str, deepflow_root: Optional[str] = None):
        from core.blackboard.blackboard_manager import BlackboardManager
        from core.process_manager import SingleSourceStateManager, ModuleLifecycleManager
        
        self.session_id = session_id
        self.bm = BlackboardManager(session_id)
        self.state_mgr = SingleSourceStateManager(str(self.bm.session_dir))
        self.lifecycle = ModuleLifecycleManager(str(self.bm.session_dir))
        self.deepflow_root = deepflow_root or str(self.bm.session_dir.parent.parent)
        
        # 重试计数（从 blackboard 读取）
        self._retry_counts = {}
        for m in self.MODULES:
            self._retry_counts[m] = self.bm.read_stage(f'retry_count_{m}', default=0)
    
    def next_step(self) -> PipelineAction:
        """
        核心方法：返回下一步动作。
        
        状态机逻辑完全在这里，确定性执行，不依赖 LLM。
        
        状态转移：
          pending → WRITE_PROMPT → prompt_written → ACQUIRE_RUN → run_acquired → SPAWN_MODULE → spawned → WAIT_FOR_MODULE → completed → VALIDATE → (next module)
        """
        # 找到第一个未完成的模块
        current_module = self._find_current_module()
        
        if current_module is None:
            # 所有模块完成 → 写入 .completed
            return self._finish_pipeline()
        
        # 检查模块状态
        module_status = self._get_module_status(current_module)
        
        if module_status == 'pending':
            return self._action_write_prompt(current_module)
        
        elif module_status == 'prompt_written':
            return self._action_acquire_run(current_module)
        
        elif module_status == 'run_acquired':
            return self._action_spawn_module(current_module)
        
        elif module_status == 'spawned':
            return self._action_wait_for_module(current_module)
        
        elif module_status == 'completed':
            # 验证输出
            return self._action_validate(current_module)
        
        elif module_status == 'validated':
            # 标记完成，推进到下一个模块
            self._mark_module_done(current_module)
            return self.next_step()  # 递归：处理下一个模块
        
        elif module_status == 'needs_retry':
            return self._action_retry(current_module)
        
        elif module_status == 'failed':
            return self._action_fail(current_module)
        
        else:
            return PipelineAction(
                type='PIPELINE_FAILED',
                module=current_module,
                message=f'Unknown module status: {module_status}',
            )
    
    def report_action_result(self, action_type: str, module: str, success: bool, details: dict = None):
        """
        Agent 执行完动作后，报告结果。
        Driver 更新内部状态。
        """
        details = details or {}
        
        if action_type == 'WRITE_PROMPT' and success:
            self._set_module_status(module, 'prompt_written')
        
        elif action_type == 'ACQUIRE_RUN' and success:
            run_id = details.get('run_id', '')
            already_running = details.get('already_running', False)
            if already_running:
                # 已经在运行，跳到等待
                self._set_module_status(module, 'spawned')
            else:
                self._set_module_status(module, 'run_acquired')
        
        elif action_type == 'SPAWN_MODULE' and success:
            self._set_module_status(module, 'spawned')
        
        elif action_type == 'WAIT_FOR_MODULE':
            if success:
                self._set_module_status(module, 'completed')
            else:
                # 检查重试次数
                retry_count = self._retry_counts.get(module, 0)
                if retry_count < 2:
                    self._set_module_status(module, 'needs_retry')
                else:
                    self._set_module_status(module, 'failed')
        
        elif action_type == 'VALIDATE' and success:
            self._set_module_status(module, 'validated')
        
        elif action_type == 'RETRY':
            self._retry_counts[module] = self._retry_counts.get(module, 0) + 1
            self.bm.write(f'retry_count_{module}', self._retry_counts[module], subdir='stages')
            self._set_module_status(module, 'pending')  # 重新走 WRITE_PROMPT 流程
    
    # ── 内部方法 ──────────────────────────────────────────────────────────
    
    def _find_current_module(self) -> Optional[str]:
        """找到第一个未完成（非 validated/done）的模块"""
        for m in self.MODULES:
            status = self._get_module_status(m)
            if status not in ('validated', 'done'):
                return m
        return None
    
    def _get_module_status(self, module: str) -> str:
        """
        获取模块状态。
        
        状态检测优先级（从高到低）：
          1. Agent 写入的显式状态（pipeline_driver 控制）
          2. 已验证标记（.validated 文件）
          3. 向后兼容推断（下一个模块已启动 = 当前模块已验证）
          4. Run 状态（.runs/{module}.run.json）
          5. Prompt 文件存在性
          6. 默认 pending
        """
        # 1. 检查 Agent 写入的状态（PipelineDriver 控制）
        #    注意：PipelineDriver 自己会设置 'completed'，不要忽略
        #    使用 read_stage_raw 兼容无后缀文件（write 写入的）和有后缀文件（write_stage 写入的）
        agent_status = self.bm.read_stage_raw(f'{module}_agent_status')
        if agent_status:
            return agent_status.strip()
        
        # 2. 检查已验证标记
        validated_marker = self.bm.session_dir / 'stages' / f'.{module}_validated'
        if validated_marker.exists():
            return 'validated'
        
        # 3. 向后兼容：如果下一个模块已启动/完成，说明当前模块已验证
        module_idx = self.MODULES.index(module) if module in self.MODULES else -1
        if module_idx >= 0 and module_idx < len(self.MODULES) - 1:
            next_module = self.MODULES[module_idx + 1]
            next_run = self._get_run_info(next_module)
            if next_run and next_run.get('status') in ('running', 'completed'):
                # 下一个模块已启动，说明当前模块已被旧 Orchestrator 验证
                return 'validated'
        
        # 4. 检查 run 状态
        run_info = self._get_run_info(module)
        if run_info:
            status = run_info.get('status', '')
            if status == 'running':
                return 'spawned'
            elif status == 'completed':
                # 输出存在，但未被 driver 验证 → 需要验证
                return 'completed'
        
        # 5. 检查 prompt 是否已写入
        prompt_path = self.bm.session_dir / 'stages' / f'{module}_module_prompt.md'
        if prompt_path.exists():
            return 'prompt_written'
        
        # 6. 默认 pending
        return 'pending'
    
    def _set_module_status(self, module: str, status: str):
        """设置模块状态（Agent 可读取）"""
        # 使用 write_stage 而不是 write — write_stage 自动加 .md 后缀，read_stage 能找到
        self.bm.write_stage(f'{module}_agent_status', status)
    
    def _get_run_info(self, module: str) -> Optional[dict]:
        """读取 .runs/{module}.run.json"""
        run_path = self.bm.session_dir / '.runs' / f'{module}.run.json'
        if run_path.exists():
            return json.loads(run_path.read_text(encoding='utf-8'))
        return None
    
    # ── Action 构造 ───────────────────────────────────────────────────────
    
    def _action_write_prompt(self, module: str) -> PipelineAction:
        config = self.MODULE_CONFIG[module]
        return PipelineAction(
            type='WRITE_PROMPT',
            module=module,
            params={
                'template': config['prompt_template'],
                'output_path': f'stages/{module}_module_prompt.md',
            },
            message=f'Write {module} module prompt using render_prompt()',
        )
    
    def _action_acquire_run(self, module: str) -> PipelineAction:
        return PipelineAction(
            type='ACQUIRE_RUN',
            module=module,
            params={},
            message=f'Acquire run for {module} module',
        )
    
    def _action_spawn_module(self, module: str) -> PipelineAction:
        run_info = self._get_run_info(module)
        run_id = run_info.get('run_id', '') if run_info else ''
        
        prompt_path = self.bm.resolve_path(f'stages/{module}_module_prompt.md')
        failed_path = self.bm.resolve_path('stages/.failed')
        
        return PipelineAction(
            type='SPAWN_MODULE',
            module=module,
            params={
                'label': f'{module}_module_v4',
                'task': self._build_spawn_task(module, run_id, prompt_path, failed_path),
                'cwd': self.deepflow_root,
                'lightContext': True,
            },
            message=f'Spawn {module} module agent',
        )
    
    def _action_wait_for_module(self, module: str) -> PipelineAction:
        config = self.MODULE_CONFIG[module]
        return PipelineAction(
            type='WAIT_FOR_MODULE',
            module=module,
            params={
                'expected_files': config['files'],
                'timeout': config['timeout'],
                'min_file_sizes': config['sizes'],
            },
            message=f'Wait for {module} module completion',
        )
    
    def _action_validate(self, module: str) -> PipelineAction:
        config = self.MODULE_CONFIG[module]
        return PipelineAction(
            type='VALIDATE',
            module=module,
            params={
                'expected_files': config['files'],
                'min_sizes': config['sizes'],
            },
            message=f'Validate {module} output',
        )
    
    def _action_retry(self, module: str) -> PipelineAction:
        retry_count = self._retry_counts.get(module, 0)
        wait_time = 30 if retry_count == 0 else 60
        return PipelineAction(
            type='RETRY',
            module=module,
            params={
                'retry_count': retry_count + 1,
                'wait_seconds': wait_time,
            },
            message=f'Retry {module} (attempt {retry_count + 1}, wait {wait_time}s)',
        )
    
    def _action_fail(self, module: str) -> PipelineAction:
        return PipelineAction(
            type='PIPELINE_FAILED',
            module=module,
            params={
                'reason': 'MISSING_AFTER_2_RETRIES',
                'retry_count': self._retry_counts.get(module, 0),
            },
            message=f'Pipeline failed: {module} module missing after 2 retries',
        )
    
    def _finish_pipeline(self) -> PipelineAction:
        return PipelineAction(
            type='PIPELINE_COMPLETED',
            message='All modules completed. Write .completed marker.',
        )
    
    def _build_spawn_task(self, module: str, run_id: str, prompt_path: str, failed_path: str) -> str:
        """构建 spawn task（最小引用模式）"""
        return (
            f"cd {self.deepflow_root} && PYTHONPATH=.\n"
            f"你执行的所有 Python 命令必须以 `cd {self.deepflow_root} && PYTHONPATH=.` 开头。\n\n"
            f"session_id: `{self.session_id}`\n"
            f"RUN_ID: `{run_id}`\n"
            f"blackboard: `{str(self.bm.session_dir)}`\n\n"
            f"读取文件 `{prompt_path}` 并严格按照其中的指令执行。\n"
            f"如果文件不存在 → 写入 `{failed_path}` 并立即结束。"
        )


# ── CLI 入口（供 Agent exec 调用）──────────────────────────────────────────

def main():
    """CLI 入口：python3 -m core.pipeline_driver <session_id> [report <result_json>]"""
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python3 -m core.pipeline_driver <session_id> [report <result_json>]")
        sys.exit(1)
    
    session_id = sys.argv[1]
    
    # 找到 .deepflow root
    deepflow_root = str(Path(__file__).resolve().parent.parent)
    
    driver = PipelineDriver(session_id, deepflow_root=deepflow_root)
    
    if len(sys.argv) >= 4 and sys.argv[2] == 'report':
        # 报告动作结果
        result_json = sys.argv[3]
        result = json.loads(result_json)
        driver.report_action_result(
            action_type=result['action_type'],
            module=result['module'],
            success=result['success'],
            details=result.get('details', {}),
        )
        print(json.dumps({'status': 'updated'}, ensure_ascii=False))
    else:
        # 获取下一步动作
        action = driver.next_step()
        print(action.to_json())


if __name__ == '__main__':
    main()
