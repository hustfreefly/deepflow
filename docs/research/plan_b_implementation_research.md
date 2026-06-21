# 方案 B 深度调研报告：在 OpenClaw 生态内构建类 Hermes 引擎

> **调研日期**: 2026-01-XX  
> **调研目标**: 评估在 OpenClaw 生态内构建类 Hermes 引擎的可行性、实现路径、挑战和业界最佳实践  
> **调研方法**: Web 搜索（8 次）+ 本地代码探索（4 次）+ 架构分析

---

## 目录

1. [OpenClaw 现有能力 vs Hermes 特性对照表](#1-openclaw-现有能力-vs-hermes-特性对照表)
2. [Codex/Claude Code 集成方案](#2-codexclaude-code-集成方案)
3. [编排引擎设计](#3-编排引擎设计)
4. [技能自动创建系统设计](#4-技能自动创建系统设计)
5. [策展记忆 / 蒸馏判断器设计](#5-策展记忆--蒸馏判断器设计)
6. [业界最佳实践调研](#6-业界最佳实践调研)
7. [挑战和难度评估](#7-挑战和难度评估)
8. [方案 A vs B 修正对比](#8-方案-a-vs-b-修正对比)
9. [推荐路径](#9-推荐路径)

---

## 1. OpenClaw 现有能力 vs Hermes 特性对照表

### 1.1 核心特性对照

| Hermes 特性 | OpenClaw 现有 | 差距评估 | 补齐方案 |
|------------|-------------|---------|---------|
| **飞书集成** | ✅ 完整支持（feishu-doc, feishu-drive, feishu-wiki 等 10+ skills） | 无差距 | — |
| **持久记忆（MEMORY.md）** | ✅ 有 MEMORY.md + memory_search + memory_get | 小差距 | 需增加结构化存储（SQLite）+ 自动整理机制 |
| **用户建模（USER.md）** | ✅ 有 USER.md（通过 memory 系统） | 小差距 | 需增强用户偏好自动提取 |
| **人格规则（SOUL.md）** | ✅ 有 AGENTS.md + SOUL.md（通过 workspace files） | 无差距 | — |
| **技能系统** | ✅ 完整 Skills 系统（84+ workspace skills） | 无差距 | — |
| **技能自动创建** | ⚠️ 有 skill_workshop 但需手动触发 | 大差距 | 需实现自动提取 + 自动注册 |
| **Reflection Pass** | ❌ 无系统性反思机制 | 大差距 | 需设计定期 LLM 整理流程 |
| **Codex 集成** | ⚠️ ACP 协议支持（acpx plugin） | 中差距 | 需完善 ACP→Codex 桥接 + SDK 直连 |
| **Claude Code 集成** | ⚠️ ACP 协议支持（acpx plugin） | 中差距 | 需完善 ACP→Claude Code 桥接 + SDK 直连 |
| **子 Agent** | ✅ sessions_spawn + subagents 系统 | 无差距 | — |
| **会话搜索** | ✅ LCM 系统（lcm_grep, lcm_expand, lcm_describe） | 无差距 | — |
| **Cron 调度** | ✅ 已有（通过 exec + cron） | 无差距 | — |
| **多模型支持** | ✅ 完整支持（多模型路由） | 无差距 | — |

### 1.2 关键差距分析

**大差距（需要新建系统）**：
1. **技能自动创建**：Hermes 能在任务成功后自动提取执行模式并生成 Skill，OpenClaw 的 skill_workshop 需要手动触发
2. **Reflection Pass**：Hermes 有系统性的自我反思循环，OpenClaw 缺少定期自动整理机制

**中差距（需要增强集成）**：
1. **Codex/Claude Code 集成**：OpenClaw 有 ACP 协议支持，但需要完善与 Codex CLI 和 Claude Code CLI 的具体桥接

**小差距（需要微调增强）**：
1. **持久记忆结构化**：MEMORY.md 是文本格式，需要增加 SQLite 结构化存储
2. **用户建模自动化**：需要增强用户偏好的自动提取和更新

---

## 2. Codex/Claude Code 集成方案

### 2.1 OpenClaw ACP 协议现状

**ACP（Agent Client Protocol）** 是 OpenClaw 用于连接 IDE 与 AI Agent 的桥接协议：

- **实现方式**：`@openclaw/acpx` 插件
- **配置**：`openclaw config set plugins.entries.acpx.enabled true`
- **功能**：将 ACP 协议翻译为 OpenClaw 内部的 WebSocket Gateway 协议
- **限制**：
  - 双向文件访问支持不完整
  - 终端集成有限
  - 会话连续性（重放历史消息）有偏差

### 2.2 Codex 集成方案

#### 方案 A：ACP 桥接（当前可用）

```bash
# 1. 启用 ACP 插件
openclaw plugins install @openclaw/acpx
openclaw config set plugins.entries.acpx.enabled true

# 2. 通过 ACP spawn Codex
/acp spawn codex

# 3. 在 OpenClaw 会话中与 Codex 交互
# OpenClaw → ACP → Codex CLI → 返回结果
```

**优点**：已有基础设施，配置即可用  
**缺点**：协议转换开销，功能受限

#### 方案 B：Codex SDK 直连（推荐）

OpenAI Codex SDK 提供 TypeScript 和 Python 库，可程序化控制 Codex CLI：

```python
# Python 示例：通过 Codex SDK 程序化调用
import subprocess
import json

class CodexExecutor:
    """在 OpenClaw sub-agent 中执行 Codex 任务"""
    
    def __init__(self, workspace: str, model: str = "o4-mini"):
        self.workspace = workspace
        self.model = model
    
    def execute_task(self, task_description: str, ac_items: list) -> dict:
        """
        执行单个 Work Package
        
        Args:
            task_description: 任务描述
            ac_items: 验收标准列表
        
        Returns:
            执行结果字典
        """
        # 构建 Codex prompt
        prompt = self._build_prompt(task_description, ac_items)
        
        # 调用 Codex CLI（通过 subprocess）
        cmd = [
            "codex", "run",
            "--model", self.model,
            "--workspace", self.workspace,
            "--prompt", prompt
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=3600  # 1 小时超时
        )
        
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "changed_files": self._parse_changed_files(result.stdout)
        }
    
    def _build_prompt(self, task_description: str, ac_items: list) -> str:
        """构建 Codex prompt"""
        ac_text = "\n".join(f"- {ac}" for ac in ac_items)
        return f"""
## 任务
{task_description}

## 验收标准
{ac_text}

## 要求
1. 实现所有验收标准
2. 编写测试覆盖关键路径
3. 确保代码符合项目规范
4. 输出变更文件列表
"""
```

#### 方案 C：Codex CLI 直接调用（最简单）

```python
# 在 OpenClaw exec 工具中直接调用 Codex CLI
import subprocess

def execute_codex_task(wp_spec: dict) -> dict:
    """通过 exec 工具调用 Codex CLI"""
    
    prompt = f"""
实现以下功能：
{wp_spec['description']}

验收标准：
{chr(10).join('- ' + ac for ac in wp_spec['ac_items'])}
"""
    
    # 写入临时文件
    with open("/tmp/codex_prompt.txt", "w") as f:
        f.write(prompt)
    
    # 调用 Codex CLI
    result = subprocess.run(
        ["codex", "run", "--prompt-file", "/tmp/codex_prompt.txt"],
        capture_output=True,
        text=True,
        cwd=wp_spec["workspace"]
    )
    
    return {
        "status": "completed" if result.returncode == 0 else "failed",
        "output": result.stdout,
        "errors": result.stderr
    }
```

### 2.3 Claude Code 集成方案

#### 方案 A：ACP 桥接（当前可用）

```bash
# 1. 通过 ACP spawn Claude Code
/acp spawn claude-code

# 2. Claude Code 可以作为 orchestrator，委托任务给 Codex
# Claude Code → Codex Plugin → Codex CLI
```

#### 方案 B：Claude Agent SDK 直连（推荐）

Claude Agent SDK（原 Claude Code SDK）提供 Python/TypeScript 库，可程序化构建和控制 AI Agent：

```python
# Python 示例：通过 Claude Agent SDK 程序化调用
import anyio
from claude_agent_sdk import ClaudeSDKClient, AssistantMessage, TextBlock

class ClaudeCodeExecutor:
    """在 OpenClaw sub-agent 中执行 Claude Code 任务"""
    
    async def execute_task(self, task_description: str, ac_items: list) -> dict:
        """
        执行单个 Work Package
        
        Args:
            task_description: 任务描述
            ac_items: 验收标准列表
        
        Returns:
            执行结果字典
        """
        client = ClaudeSDKClient()
        
        try:
            # 构建 prompt
            prompt = self._build_prompt(task_description, ac_items)
            
            # 执行任务并收集结果
            full_response = []
            async for message in client.query(prompt=prompt):
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            full_response.append(block.text)
            
            return {
                "success": True,
                "response": "\n".join(full_response),
                "changed_files": self._extract_changed_files(full_response)
            }
        
        finally:
            await client.aclose()
    
    def _build_prompt(self, task_description: str, ac_items: list) -> str:
        """构建 Claude Code prompt"""
        ac_text = "\n".join(f"- {ac}" for ac in ac_items)
        return f"""
## 任务
{task_description}

## 验收标准
{ac_text}

## 执行步骤
1. 分析需求，理解验收标准
2. 实现代码，确保覆盖所有 AC
3. 编写测试
4. 运行测试，确保通过
5. 输出变更文件列表和测试结果
"""
```

#### 方案 C：Claude Code CLI 直接调用（最简单）

```python
# 在 OpenClaw exec 工具中直接调用 Claude Code CLI
import subprocess

def execute_claude_code_task(wp_spec: dict) -> dict:
    """通过 exec 工具调用 Claude Code CLI"""
    
    prompt = f"""
实现以下功能：
{wp_spec['description']}

验收标准：
{chr(10).join('- ' + ac for ac in wp_spec['ac_items'])}

请按照以下步骤执行：
1. 分析需求
2. 实现代码
3. 编写测试
4. 运行测试
5. 输出变更文件列表
"""
    
    # 写入临时文件
    with open("/tmp/claude_prompt.txt", "w") as f:
        f.write(prompt)
    
    # 调用 Claude Code CLI
    result = subprocess.run(
        ["claude", "--prompt-file", "/tmp/claude_prompt.txt"],
        capture_output=True,
        text=True,
        cwd=wp_spec["workspace"]
    )
    
    return {
        "status": "completed" if result.returncode == 0 else "failed",
        "output": result.stdout,
        "errors": result.stderr
    }
```

### 2.4 长时间运行任务管理

**挑战**：Codex/Claude Code 任务可能运行数小时，需要有效管理。

**解决方案**：

```python
# 在 OpenClaw sub-agent 中管理长时间运行任务
import subprocess
import threading
import time
from typing import Dict, Optional

class TaskManager:
    """管理并行执行的 Codex/Claude Code 任务"""
    
    def __init__(self, max_parallel: int = 3):
        self.max_parallel = max_parallel
        self.running: Dict[str, subprocess.Popen] = {}
        self.results: Dict[str, dict] = {}
        self.lock = threading.Lock()
    
    def submit_task(self, task_id: str, cmd: list, workspace: str) -> None:
        """提交任务到执行队列"""
        with self.lock:
            # 等待空闲槽位
            while len(self.running) >= self.max_parallel:
                self._check_completed()
                time.sleep(1)
            
            # 启动任务
            process = subprocess.Popen(
                cmd,
                cwd=workspace,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            self.running[task_id] = process
    
    def _check_completed(self) -> None:
        """检查已完成的任务"""
        completed = []
        
        for task_id, process in self.running.items():
            if process.poll() is not None:
                # 任务已完成
                stdout, stderr = process.communicate()
                self.results[task_id] = {
                    "success": process.returncode == 0,
                    "stdout": stdout,
                    "stderr": stderr,
                    "returncode": process.returncode
                }
                completed.append(task_id)
        
        # 移除已完成任务
        for task_id in completed:
            del self.running[task_id]
    
    def wait_all(self, timeout: int = 7200) -> Dict[str, dict]:
        """等待所有任务完成"""
        start_time = time.time()
        
        while self.running:
            if time.time() - start_time > timeout:
                # 超时，终止所有任务
                for process in self.running.values():
                    process.terminate()
                break
            
            self._check_completed()
            time.sleep(1)
        
        return self.results
```

### 2.5 并行执行方案

```python
# 在 OpenClaw sub-agent 中并行执行多个 Codex/Claude 任务
from concurrent.futures import ThreadPoolExecutor, as_completed

def execute_work_packages_parallel(
    work_packages: list,
    executor_type: str = "codex",  # or "claude"
    max_workers: int = 3
) -> dict:
    """
    并行执行多个 Work Packages
    
    Args:
        work_packages: Work Package 列表
        executor_type: 执行器类型（codex 或 claude）
        max_workers: 最大并行数
    
    Returns:
        {wp_id: result} 字典
    """
    results = {}
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # 提交所有任务
        futures = {}
        for wp in work_packages:
            if executor_type == "codex":
                future = executor.submit(execute_codex_task, wp)
            else:
                future = executor.submit(execute_claude_code_task, wp)
            
            futures[future] = wp["wp_id"]
        
        # 收集结果
        for future in as_completed(futures):
            wp_id = futures[future]
            try:
                result = future.result()
                results[wp_id] = result
            except Exception as e:
                results[wp_id] = {
                    "success": False,
                    "error": str(e)
                }
    
    return results
```

### 2.6 集成方案对比

| 方案 | 实现复杂度 | 功能完整性 | 维护成本 | 推荐度 |
|-----|----------|----------|---------|-------|
| **ACP 桥接** | 低 | 中 | 低 | ⭐⭐⭐ |
| **SDK 直连** | 中 | 高 | 中 | ⭐⭐⭐⭐⭐ |
| **CLI 直接调用** | 低 | 中 | 低 | ⭐⭐⭐⭐ |

**推荐**：SDK 直连（方案 B），功能最完整，可控性最强。

---

## 3. 编排引擎设计

### 3.1 架构概览

```
┌─────────────────────────────────────────────────────────────┐
│                    Ship Package (JSON)                       │
│  - project_id, session_id                                    │
│  - work_packages[] (wp_id, phase, dependencies, ac_items)   │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│              Ship Package Importer                           │
│  - 验证 Ship Package schema                                  │
│  - 构建 task_map (wp_id → task metadata)                    │
│  - 构建 dependency_graph                                     │
│  - 拓扑排序 work_packages                                    │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│              Scheduler Import Contract                       │
│  - task_map, dependency_graph                                │
│  - gate_decisions, budget                                    │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│              Kanban Task Creator                             │
│  - 创建 Kanban 任务卡片                                       │
│  - 初始化状态机 (pending → ready → running → completed)      │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│              Codex/Claude Scheduler                          │
│  - 调度任务到 Codex/Claude Code                              │
│  - 管理并行执行 (max_workers=3)                              │
│  - 监控执行状态                                              │
│  - 收集执行结果                                              │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│              State Machine                                   │
│  - 管理任务状态转换                                           │
│  - 验证状态转换合法性                                         │
│  - 持久化状态到 JSON                                         │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│              Event Logger                                    │
│  - 记录所有事件 (task_created, codex_lane_started, etc.)     │
│  - 审计追踪                                                  │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 核心组件设计

#### 3.2.1 Ship Package Importer

**职责**：将 DeepFlow 产出的 Ship Package 转换为 Scheduler 可理解的 Import Contract。

**已有实现**：`core/scheduler/ship_importer/ship_importer.py`

**关键功能**：
- 验证 Ship Package schema（JSON Schema Draft7）
- 构建 task_map（wp_id → task metadata）
- 构建 dependency_graph（DAG）
- 拓扑排序 work_packages
- 生成 gate_decisions 和 budget

**代码片段**（来自实际代码库）：
```python
class ShipPackageImporter:
    """Convert a Ship Package into a schema-valid scheduler import contract."""
    
    def import_package(
        self,
        ship_package_path: str,
        scheduler_mode: str = "semi",
    ) -> dict:
        """Import a Ship Package and return Scheduler Import contract."""
        
        # 1. 验证 Ship Package
        with Path(ship_package_path).open("r", encoding="utf-8") as handle:
            ship_package = json.load(handle)
        
        errors = self.validate_ship_package(ship_package)
        if errors:
            raise ValueError("Invalid Ship Package: " + "; ".join(errors))
        
        # 2. 构建 task_map
        task_map = self.build_task_map(ship_package)
        
        # 3. 构建 dependency_graph
        dependency_graph = self._build_dependency_graph(ship_package)
        
        # 4. 生成 import contract
        result = {
            "contract_name": "deepflow.scheduler_import",
            "contract_version": SCHEMA_VERSION,
            "task_map": task_map,
            "dependency_graph": dependency_graph,
            "gate_decisions": self._build_gate_decisions(),
            "budget": self._build_budget(ship_package),
            # ... 其他字段
        }
        
        return result
```

#### 3.2.2 Kanban Task Creator

**职责**：从 Scheduler Import Contract 创建 Kanban 任务卡片，初始化状态机。

**已有实现**：`core/scheduler/task_creator/task_creator.py`

**关键功能**：
- 按拓扑顺序创建任务
- 初始化任务状态（pending）
- 验证任务 metadata schema
- 记录事件日志

**代码片段**（来自实际代码库）：
```python
class KanbanTaskCreator:
    """Create and track Kanban task metadata for a scheduler import."""
    
    def create_tasks(self, scheduler_import: dict) -> List[str]:
        """Create Kanban tasks from Scheduler Import, return task IDs."""
        
        task_ids: List[str] = []
        
        # 按拓扑顺序创建任务
        for wp_id in self._topological_order(scheduler_import):
            task = scheduler_import["task_map"][wp_id]
            task_id = task["task_id"]
            
            # 构建任务 metadata
            metadata = self._build_task_metadata(scheduler_import, task)
            
            # 验证 schema
            self._validate(metadata, self._task_validator, "kanban task metadata")
            
            # 添加到状态机
            self.state_machine.add_task(
                task_id=task_id,
                wp_id=task["wp_id"],
                phase=task["phase"],
                budget_limits=task.get("budget_limits"),
                max_retries=task.get("budget_limits", {}).get("max_retries", 3),
            )
            
            # 记录事件
            self.event_logger.log_event(
                "task_created",
                {"wp_id": task["wp_id"], "task_id": task_id}
            )
            
            task_ids.append(task_id)
        
        return task_ids
```

#### 3.2.3 Codex Scheduler

**职责**：调度并监控 Codex CLI 执行，收集执行结果。

**已有实现**：`core/scheduler/codex_scheduler/codex_scheduler.py`

**关键功能**：
- 调度任务到 Codex CLI
- 管理并行执行（subprocess.Popen）
- 监控执行状态和超时
- 收集执行结果（stdout, stderr, changed_files）
- 支持任务取消

**代码片段**（来自实际代码库）：
```python
class CodexScheduler:
    """Schedule and monitor Codex CLI executions for work packages."""
    
    def schedule_task(
        self,
        task_id: str,
        wp_spec: dict,
        timeout_seconds: int = 3600,
    ) -> dict:
        """Schedule a Codex execution for a task, return result."""
        
        # 1. 记录事件
        self.event_logger.log_event(
            "codex_lane_started",
            {"wp_id": wp_spec["wp_id"], "codex_session_id": f"codex_{task_id}"}
        )
        
        # 2. 更新状态
        self.state_machine.transition(task_id, "ready", "running", "codex execution started")
        
        # 3. 构建 Codex prompt
        prompt = self._build_prompt(
            wp_spec["title"],
            wp_spec["description"],
            wp_spec["ac_items"],
            wp_spec["risk_level"]
        )
        
        # 4. 执行 Codex CLI
        started_at = self._utc_now()
        start_time = time.time()
        
        try:
            process = self._execute_codex(prompt, timeout_seconds)
            self._running[task_id] = process
            
            # 5. 监控执行
            stdout, stderr = process.communicate(timeout=timeout_seconds)
            duration_seconds = int(time.time() - start_time)
            
            # 6. 收集结果
            if process.returncode != 0:
                status = "failed"
                errors = [self._build_error("execution_error", "EXE-002", 
                          f"Codex exited with code {process.returncode}", wp_spec["wp_id"])]
            else:
                status = "completed"
                errors = []
            
            result = {
                "contract_name": "deepflow.codex_lane_result",
                "contract_version": SCHEMA_VERSION,
                "wp_id": wp_spec["wp_id"],
                "task_id": task_id,
                "status": status,
                "started_at": started_at,
                "duration_seconds": duration_seconds,
                "tokens_used": self._estimate_tokens(stdout),
                "changed_files": self._parse_changed_files(stdout),
                "errors": errors
            }
            
            # 7. 更新状态
            self.state_machine.transition(task_id, "running", status, "codex execution completed")
            
            return result
        
        except subprocess.TimeoutExpired:
            process.kill()
            return self._build_timeout_result(task_id, wp_spec, timeout_seconds)
```

#### 3.2.4 State Machine

**职责**：管理任务状态转换，确保状态转换合法性。

**已有实现**：`core/scheduler/state_machine/state_machine.py`

**状态转换图**：
```
pending → ready → running → completed
                  ↓
               failed → ready (retry)
                  ↓
              cancelled
```

**代码片段**（来自实际代码库）：
```python
class StateMachine:
    """Manage task state transitions with validation."""
    
    ALLOWED_TRANSITIONS = {
        "pending": ["ready", "cancelled"],
        "ready": ["running", "cancelled"],
        "running": ["completed", "failed", "cancelled"],
        "failed": ["ready", "cancelled"],  # retry
        "completed": [],
        "cancelled": []
    }
    
    def transition(self, task_id: str, from_status: str, to_status: str, reason: str) -> dict:
        """Transition a task to a new state."""
        
        # 验证状态转换
        if not self._validate_transition(from_status, to_status):
            raise ValueError(f"Invalid transition: {from_status} → {to_status}")
        
        # 更新状态
        task = self._state["tasks"][task_id]
        task["status"] = to_status
        task["updated_at"] = self._utc_now()
        task["history"].append({
            "from": from_status,
            "to": to_status,
            "reason": reason,
            "timestamp": task["updated_at"]
        })
        
        # 验证整体状态
        self._validate_state()
        
        return copy.deepcopy(task)
```

### 3.3 编排引擎工作流

```python
# 完整的编排引擎工作流
class OrchestratorEngine:
    """DeepFlow 编排引擎：从 Ship Package 到代码实现"""
    
    def __init__(self, config: dict):
        self.config = config
        self.event_logger = EventLogger()
        self.state_machine = StateMachine()
        self.ship_importer = ShipPackageImporter(config)
        self.task_creator = KanbanTaskCreator(self.event_logger, self.state_machine)
        self.codex_scheduler = CodexScheduler(self.event_logger, self.state_machine)
    
    async def execute_ship_package(self, ship_package_path: str) -> dict:
        """
        执行完整的 Ship Package
        
        Args:
            ship_package_path: Ship Package JSON 文件路径
        
        Returns:
            执行结果字典
        """
        
        # Phase 1: Import Ship Package
        print("Phase 1: Importing Ship Package...")
        scheduler_import = self.ship_importer.import_package(
            ship_package_path,
            scheduler_mode="auto"
        )
        
        # Phase 2: Create Kanban Tasks
        print("Phase 2: Creating Kanban tasks...")
        task_ids = self.task_creator.create_tasks(scheduler_import)
        
        # Phase 3: Execute Work Packages
        print("Phase 3: Executing work packages...")
        results = await self._execute_work_packages(
            scheduler_import["task_map"],
            scheduler_import["dependency_graph"]
        )
        
        # Phase 4: Evaluate Results
        print("Phase 4: Evaluating results...")
        evaluation = self._evaluate_results(results, scheduler_import["task_map"])
        
        # Phase 5: Generate Report
        print("Phase 5: Generating report...")
        report = self._generate_report(evaluation, results)
        
        return report
    
    async def _execute_work_packages(
        self,
        task_map: dict,
        dependency_graph: dict
    ) -> dict:
        """执行 Work Packages（考虑依赖关系）"""
        
        results = {}
        completed = set()
        
        # 拓扑排序
        topo_order = self._topological_sort(dependency_graph)
        
        # 按阶段执行
        for wp_id in topo_order:
            # 等待依赖完成
            dependencies = dependency_graph.get(wp_id, [])
            while not all(dep in completed for dep in dependencies):
                await asyncio.sleep(1)
            
            # 执行任务
            task = task_map[wp_id]
            result = await self._execute_single_wp(task)
            results[wp_id] = result
            
            if result["success"]:
                completed.add(wp_id)
        
        return results
    
    async def _execute_single_wp(self, task: dict) -> dict:
        """执行单个 Work Package"""
        
        # 选择执行器（Codex 或 Claude Code）
        executor_type = self._select_executor(task)
        
        if executor_type == "codex":
            return self.codex_scheduler.schedule_task(
                task["task_id"],
                task,
                timeout_seconds=3600
            )
        else:
            # Claude Code 执行
            return await self._execute_claude_code(task)
    
    def _select_executor(self, task: dict) -> str:
        """选择执行器（基于任务特征）"""
        
        # 简单规则：根据 risk_level 和 phase 选择
        risk_level = task.get("risk_level", "low")
        phase = task.get("phase", "phase_1")
        
        if risk_level == "high" or phase in ["phase_3", "phase_4"]:
            return "claude"  # 高风险任务用 Claude（更强的推理能力）
        else:
            return "codex"  # 低风险任务用 Codex（更快的执行速度）
    
    def _evaluate_results(self, results: dict, task_map: dict) -> dict:
        """评估执行结果（AC 满足度）"""
        
        evaluation = {
            "total_tasks": len(results),
            "completed": sum(1 for r in results.values() if r["success"]),
            "failed": sum(1 for r in results.values() if not r["success"]),
            "ac_satisfaction": 0.0,
            "details": []
        }
        
        for wp_id, result in results.items():
            task = task_map[wp_id]
            ac_items = task.get("ac_items", [])
            
            # 简单的 AC 满足度评估（实际应该用 LLM 评估）
            if result["success"]:
                ac_satisfaction = 1.0
            else:
                ac_satisfaction = 0.0
            
            evaluation["details"].append({
                "wp_id": wp_id,
                "ac_items": ac_items,
                "ac_satisfaction": ac_satisfaction,
                "success": result["success"],
                "errors": result.get("errors", [])
            })
        
        # 计算总体 AC 满足度
        if evaluation["details"]:
            evaluation["ac_satisfaction"] = (
                sum(d["ac_satisfaction"] for d in evaluation["details"]) 
                / len(evaluation["details"])
            )
        
        return evaluation
```

### 3.4 自适应决策机制

```python
class AdaptiveDecisionMaker:
    """自适应决策：重试/换工具/反馈上游"""
    
    def __init__(self, orchestrator: OrchestratorEngine):
        self.orchestrator = orchestrator
    
    def decide_next_action(self, wp_id: str, result: dict) -> dict:
        """
        根据执行结果决定下一步行动
        
        Args:
            wp_id: Work Package ID
            result: 执行结果
        
        Returns:
            决策字典 {action: str, params: dict}
        """
        
        if result["success"]:
            return {"action": "continue", "params": {}}
        
        # 分析失败原因
        error_type = self._classify_error(result)
        
        if error_type == "timeout":
            # 超时：增加超时时间重试
            return {
                "action": "retry",
                "params": {"timeout_multiplier": 2.0}
            }
        
        elif error_type == "compilation_error":
            # 编译错误：切换到 Claude Code（更强的代码理解能力）
            return {
                "action": "switch_executor",
                "params": {"target_executor": "claude"}
            }
        
        elif error_type == "test_failure":
            # 测试失败：提供错误反馈重试
            return {
                "action": "retry_with_feedback",
                "params": {"error_context": result["stderr"]}
            }
        
        elif error_type == "ac_not_met":
            # AC 不满足：反馈上游（Solution Pro）重新规划
            return {
                "action": "feedback_upstream",
                "params": {
                    "target": "solution_pro",
                    "issue": "ac_not_met",
                    "wp_id": wp_id,
                    "ac_items": result.get("ac_items", [])
                }
            }
        
        else:
            # 未知错误：重试一次
            return {
                "action": "retry",
                "params": {"max_retries": 1}
            }
    
    def _classify_error(self, result: dict) -> str:
        """分类错误类型"""
        
        if "timeout" in result.get("error", "").lower():
            return "timeout"
        
        stderr = result.get("stderr", "")
        
        if "compilation error" in stderr.lower() or "syntax error" in stderr.lower():
            return "compilation_error"
        
        if "test failed" in stderr.lower() or "assertion error" in stderr.lower():
            return "test_failure"
        
        if "ac not met" in result.get("error", "").lower():
            return "ac_not_met"
        
        return "unknown"
```

### 3.5 状态持久化（断点续接）

```python
class StatePersistence:
    """状态持久化：支持断点续接"""
    
    def __init__(self, state_dir: str):
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
    
    def save_checkpoint(self, session_id: str, state: dict) -> None:
        """保存检查点"""
        checkpoint_path = self.state_dir / f"{session_id}_checkpoint.json"
        
        with open(checkpoint_path, "w", encoding="utf-8") as f:
            json.dump({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "state": state
            }, f, indent=2, ensure_ascii=False)
    
    def load_checkpoint(self, session_id: str) -> Optional[dict]:
        """加载检查点"""
        checkpoint_path = self.state_dir / f"{session_id}_checkpoint.json"
        
        if not checkpoint_path.exists():
            return None
        
        with open(checkpoint_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        return data["state"]
    
    def resume_from_checkpoint(self, session_id: str) -> dict:
        """从检查点恢复执行"""
        state = self.load_checkpoint(session_id)
        
        if not state:
            raise ValueError(f"No checkpoint found for session: {session_id}")
        
        # 恢复未完成的任务
        completed_tasks = state.get("completed_tasks", [])
        all_tasks = state.get("all_tasks", [])
        pending_tasks = [t for t in all_tasks if t not in completed_tasks]
        
        return {
            "state": state,
            "pending_tasks": pending_tasks
        }
```

---

## 4. 技能自动创建系统设计

### 4.1 Hermes 的技能自动创建机制

Hermes Agent 的核心特性之一是**技能自动创建**（Skill Auto-creation）：

**工作原理**：
1. **任务执行**：Agent 成功完成复杂或易错任务
2. **模式提取**：Agent 抽象并持久化解决方法
3. **技能文档生成**：生成可重用的 Skill 文档（SKILL.md）
4. **技能注册**：注册到技能系统，供未来使用
5. **技能优化**：通过反复使用，不断改进技能

**关键组件**：
- `skill_manage` 工具：创建、更新、删除技能
- 技能目录：`~/.hermes/skills/`
- 技能格式：每个技能是一个文件夹，包含 `SKILL.md`

### 4.2 OpenClaw 的技能系统现状

**已有能力**：
- ✅ 完整的 Skills 系统（84+ workspace skills）
- ✅ skill_workshop 工具（创建、更新、修订、应用技能）
- ✅ 技能格式标准化（SKILL.md + 支持文件）
- ✅ 技能版本管理（sha256 校验）

**差距**：
- ❌ 需要手动触发 skill_workshop
- ❌ 没有自动提取执行模式
- ❌ 没有自动注册机制

### 4.3 技能自动创建系统设计

#### 4.3.1 架构

```
┌─────────────────────────────────────────────────────────────┐
│                    Task Execution                            │
│  - Agent 执行任务（Codex/Claude Code）                        │
│  - 收集执行轨迹（prompt, actions, results）                  │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│              Success Detector                                │
│  - 判断任务是否成功完成                                       │
│  - 评估执行质量（AC 满足度、测试通过率）                      │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│              Pattern Extractor                               │
│  - 从成功执行中提取模式                                       │
│  - 识别关键步骤、决策点、工具使用                             │
│  - 使用 LLM 抽象和总结                                       │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│              Skill Generator                                 │
│  - 生成 SKILL.md 文档                                        │
│  - 定义触发条件、执行步骤、验证方法                           │
│  - 生成支持文件（示例、脚本）                                 │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│              Skill Validator                                 │
│  - 验证技能格式（schema 检查）                                │
│  - 验证技能可执行性（dry-run）                                │
│  - 验证技能不与现有技能冲突                                   │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│              Skill Registrar                                 │
│  - 注册到 OpenClaw skill_workshop                            │
│  - 设置技能版本（sha256）                                     │
│  - 记录技能来源（哪个任务生成的）                             │
└─────────────────────────────────────────────────────────────┘
```

#### 4.3.2 核心组件实现

```python
# 技能自动创建系统
import json
import hashlib
from pathlib import Path
from typing import Dict, List, Optional

class SkillAutoCreator:
    """自动从成功任务中提取并创建技能"""
    
    def __init__(self, skills_dir: str, workshop_client):
        """
        Args:
            skills_dir: 技能目录路径
            workshop_client: OpenClaw skill_workshop 客户端
        """
        self.skills_dir = Path(skills_dir)
        self.workshop_client = workshop_client
    
    def process_successful_task(
        self,
        task_id: str,
        task_spec: dict,
        execution_trace: dict,
        result: dict
    ) -> Optional[str]:
        """
        处理成功任务，尝试创建技能
        
        Args:
            task_id: 任务 ID
            task_spec: 任务规格
            execution_trace: 执行轨迹（prompt, actions, results）
            result: 执行结果
        
        Returns:
            创建的 skill_id，如果未创建则返回 None
        """
        
        # 1. 判断是否值得创建技能
        if not self._should_create_skill(task_spec, result):
            return None
        
        # 2. 提取执行模式
        pattern = self._extract_pattern(execution_trace)
        
        # 3. 生成技能文档
        skill_content = self._generate_skill_document(
            task_spec, pattern, execution_trace
        )
        
        # 4. 验证技能
        if not self._validate_skill(skill_content):
            return None
        
        # 5. 注册技能
        skill_id = self._register_skill(task_id, skill_content)
        
        return skill_id
    
    def _should_create_skill(self, task_spec: dict, result: dict) -> bool:
        """判断是否值得创建技能"""
        
        # 条件 1：任务成功完成
        if not result.get("success"):
            return False
        
        # 条件 2：任务复杂度足够高（不是简单任务）
        complexity = task_spec.get("complexity", "low")
        if complexity not in ["medium", "high"]:
            return False
        
        # 条件 3：AC 满足度高
        ac_satisfaction = result.get("ac_satisfaction", 0.0)
        if ac_satisfaction < 0.9:
            return False
        
        # 条件 4：任务类型可泛化（不是特定于某个项目）
        task_type = task_spec.get("type", "unknown")
        if task_type in ["project_specific", "one_off"]:
            return False
        
        return True
    
    def _extract_pattern(self, execution_trace: dict) -> dict:
        """从执行轨迹中提取模式"""
        
        # 使用 LLM 提取关键步骤和决策点
        prompt = f"""
分析以下执行轨迹，提取可重用的模式：

## 执行轨迹
{json.dumps(execution_trace, indent=2, ensure_ascii=False)}

## 请提取：
1. 关键步骤（按顺序）
2. 决策点（在哪里做了选择，为什么）
3. 工具使用（用了哪些工具，怎么用）
4. 常见问题和解决方案
5. 验证方法（如何确认成功）

输出 JSON 格式：
{{
  "key_steps": [...],
  "decision_points": [...],
  "tools_used": [...],
  "common_issues": [...],
  "validation_methods": [...]
}}
"""
        
        # 调用 LLM（通过 OpenClaw）
        response = self._call_llm(prompt)
        pattern = json.loads(response)
        
        return pattern
    
    def _generate_skill_document(
        self,
        task_spec: dict,
        pattern: dict,
        execution_trace: dict
    ) -> str:
        """生成 SKILL.md 文档"""
        
        skill_name = self._generate_skill_name(task_spec)
        
        content = f"""# {skill_name}

> **来源**: 从任务 {task_spec['task_id']} 自动提取  
> **创建时间**: {datetime.now(timezone.utc).isoformat()}  
> **版本**: 1.0.0

## 触发条件

当用户请求以下类型的任务时，使用此技能：
- {task_spec.get('description', 'N/A')}

## 执行步骤

"""
        
        for i, step in enumerate(pattern["key_steps"], 1):
            content += f"{i}. {step}\n"
        
        content += "\n## 决策点\n\n"
        
        for dp in pattern["decision_points"]:
            content += f"- **{dp['choice']}**: {dp['reasoning']}\n"
        
        content += "\n## 工具使用\n\n"
        
        for tool in pattern["tools_used"]:
            content += f"- `{tool['name']}`: {tool['purpose']}\n"
        
        content += "\n## 常见问题\n\n"
        
        for issue in pattern["common_issues"]:
            content += f"- **问题**: {issue['problem']}\n"
            content += f"  **解决**: {issue['solution']}\n"
        
        content += "\n## 验证方法\n\n"
        
        for method in pattern["validation_methods"]:
            content += f"- {method}\n"
        
        return content
    
    def _generate_skill_name(self, task_spec: dict) -> str:
        """生成技能名称"""
        
        # 从任务类型和描述生成
        task_type = task_spec.get("type", "general")
        description = task_spec.get("description", "")
        
        # 简单规则：取前 30 个字符
        name = f"{task_type}-{description[:30]}"
        name = name.lower().replace(" ", "-").replace("/", "-")
        
        return name
    
    def _validate_skill(self, skill_content: str) -> bool:
        """验证技能文档"""
        
        # 1. 检查基本格式
        if not skill_content.startswith("# "):
            return False
        
        # 2. 检查必要章节
        required_sections = ["触发条件", "执行步骤", "验证方法"]
        for section in required_sections:
            if section not in skill_content:
                return False
        
        # 3. 检查长度（不能太短）
        if len(skill_content) < 500:
            return False
        
        return True
    
    def _register_skill(self, task_id: str, skill_content: str) -> str:
        """注册技能到 OpenClaw"""
        
        # 调用 skill_workshop
        result = self.workshop_client.create(
            name=f"auto-{task_id}",
            description="Auto-created skill from successful task",
            proposal_content=skill_content
        )
        
        skill_id = result["proposal_id"]
        
        return skill_id
    
    def _call_llm(self, prompt: str) -> str:
        """调用 LLM（通过 OpenClaw）"""
        # 实际实现：通过 OpenClaw 的 LLM 调用接口
        # 这里简化为直接返回
        return "{}"
```

### 4.4 业界最佳实践

**Hermes Agent**：
- 使用 `skill_manage` 工具自动创建、更新、删除技能
- 技能存储在 `~/.hermes/skills/`
- 技能格式：文件夹 + `SKILL.md`

**Composio Agent Orchestrator**：
- 自我改进系统：观察 Agent 执行结果，记录性能指标
- 跟踪成功 prompt，从失败中学习
- 递归自我改进循环

**推荐做法**：
1. **验证门控**：在技能生命周期中添加验证门控，确保正确性、可复现性、一致性
2. **渐进式披露**：技能按需加载，最小化 token 使用
3. **版本管理**：技能应该有版本号，支持回滚

---

## 5. 策展记忆 / 蒸馏判断器设计

### 5.1 Hermes 的记忆架构

Hermes Agent 采用**多层记忆系统**：

**核心文件**：
- `SOUL.md`：Agent 的核心身份、人格、工作原则
- `MEMORY.md`：Agent 的个人笔记（环境事实、项目约定、学习的工作流）
- `USER.md`：用户画像（偏好、沟通风格、期望）

**特点**：
- **有界策展**：MEMORY.md 约 2,200 字符，USER.md 约 1,375 字符
- **主动管理**：Agent 主动策展记忆内容，添加、替换、删除条目
- **会话搜索**：所有消息存储在 SQLite 数据库（`~/.hermes/state.db`），支持 FTS5 全文搜索

**外部记忆提供商**：
- 支持 8 个外部记忆插件（Honcho, Mem0, Hindsight 等）
- 提供知识图谱、语义搜索、自动事实提取等高级功能

### 5.2 OpenClaw 的记忆系统现状

**已有能力**：
- ✅ MEMORY.md（通过 memory_get, memory_search）
- ✅ memory/*.md（多个记忆文件）
- ✅ LCM 系统（lcm_grep, lcm_expand, lcm_describe）
- ✅ 会话历史搜索

**差距**：
- ❌ 没有结构化存储（SQLite）
- ❌ 没有自动整理机制
- ❌ 没有蒸馏判断器

### 5.3 策展记忆系统设计

#### 5.3.1 架构

```
┌─────────────────────────────────────────────────────────────┐
│                    Memory Ingestion                          │
│  - 会话消息                                                  │
│  - 任务执行结果                                              │
│  - 用户反馈                                                  │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│              Distillation Judge                              │
│  - 判断信息是否值得保留                                       │
│  - 评估信息重要性（预测误差、新颖性、实用性）                 │
│  - 过滤冗余信息                                              │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│              Memory Curator                                  │
│  - 整理记忆内容（添加、更新、删除）                           │
│  - 维护 MEMORY.md 和 USER.md                                 │
│  - 定期 LLM 整理（Reflection Pass）                          │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│              Structured Storage (SQLite)                     │
│  - 结构化存储（会话、任务、用户偏好）                         │
│  - FTS5 全文搜索                                             │
│  - 知识图谱（可选）                                          │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│              Memory Retrieval                                │
│  - 语义搜索（memory_search）                                 │
│  - 精确检索（memory_get）                                    │
│  - 上下文注入（系统提示）                                     │
└─────────────────────────────────────────────────────────────┘
```

#### 5.3.2 蒸馏判断器实现

```python
# 蒸馏判断器：决定哪些信息值得保留
import sqlite3
import json
from typing import Dict, List, Optional

class DistillationJudge:
    """蒸馏判断器：评估信息重要性，决定是否保留"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self) -> None:
        """初始化 SQLite 数据库"""
        conn = sqlite3.connect(self.db_path)
        
        conn.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                timestamp TEXT,
                content TEXT,
                importance_score REAL,
                category TEXT,
                metadata TEXT
            )
        """)
        
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_preferences (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                preference_key TEXT UNIQUE,
                preference_value TEXT,
                confidence REAL,
                updated_at TEXT
            )
        """)
        
        # FTS5 全文搜索
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts 
            USING fts5(content, metadata)
        """)
        
        conn.commit()
        conn.close()
    
    def evaluate_importance(
        self,
        message: dict,
        context: dict
    ) -> float:
        """
        评估消息重要性（0.0 - 1.0）
        
        Args:
            message: 消息字典 {role, content, timestamp}
            context: 上下文信息 {session_id, task_type, user_id}
        
        Returns:
            重要性分数
        """
        
        # 使用 LLM 评估重要性
        prompt = f"""
评估以下消息的重要性（0.0 - 1.0）：

## 消息
角色: {message['role']}
内容: {message['content']}

## 上下文
会话 ID: {context.get('session_id', 'N/A')}
任务类型: {context.get('task_type', 'N/A')}

## 评估标准
1. **新颖性**：是否包含新信息？
2. **实用性**：对未来任务是否有帮助？
3. **用户偏好**：是否反映用户偏好或习惯？
4. **决策依据**：是否是重要决策的依据？
5. **错误教训**：是否包含错误和解决方案？

输出 JSON：
{{"importance_score": 0.8, "reasoning": "..."}}
"""
        
        response = self._call_llm(prompt)
        result = json.loads(response)
        
        return result["importance_score"]
    
    def should_retain(
        self,
        message: dict,
        context: dict,
        threshold: float = 0.6
    ) -> bool:
        """判断是否应该保留此消息"""
        
        importance = self.evaluate_importance(message, context)
        
        return importance >= threshold
    
    def store_memory(
        self,
        session_id: str,
        content: str,
        importance_score: float,
        category: str,
        metadata: dict
    ) -> int:
        """存储记忆到 SQLite"""
        
        conn = sqlite3.connect(self.db_path)
        
        cursor = conn.execute("""
            INSERT INTO memories 
            (session_id, timestamp, content, importance_score, category, metadata)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            session_id,
            datetime.now(timezone.utc).isoformat(),
            content,
            importance_score,
            category,
            json.dumps(metadata, ensure_ascii=False)
        ))
        
        memory_id = cursor.lastrowid
        
        # 更新 FTS 索引
        conn.execute("""
            INSERT INTO memories_fts (rowid, content, metadata)
            VALUES (?, ?, ?)
        """, (memory_id, content, json.dumps(metadata, ensure_ascii=False)))
        
        conn.commit()
        conn.close()
        
        return memory_id
    
    def search_memories(
        self,
        query: str,
        limit: int = 10,
        min_importance: float = 0.5
    ) -> List[dict]:
        """搜索记忆（FTS5 全文搜索）"""
        
        conn = sqlite3.connect(self.db_path)
        
        rows = conn.execute("""
            SELECT m.id, m.session_id, m.timestamp, m.content, 
                   m.importance_score, m.category, m.metadata
            FROM memories m
            JOIN memories_fts fts ON m.id = fts.rowid
            WHERE memories_fts MATCH ?
              AND m.importance_score >= ?
            ORDER BY m.importance_score DESC
            LIMIT ?
        """, (query, min_importance, limit)).fetchall()
        
        conn.close()
        
        return [
            {
                "id": row[0],
                "session_id": row[1],
                "timestamp": row[2],
                "content": row[3],
                "importance_score": row[4],
                "category": row[5],
                "metadata": json.loads(row[6])
            }
            for row in rows
        ]
    
    def _call_llm(self, prompt: str) -> str:
        """调用 LLM"""
        # 实际实现：通过 OpenClaw 的 LLM 调用接口
        return '{"importance_score": 0.5, "reasoning": "N/A"}'
```

#### 5.3.3 Reflection Pass 实现

```python
# Reflection Pass：定期 LLM 整理记忆
class ReflectionPass:
    """定期整理记忆，提取模式，更新 MEMORY.md 和 USER.md"""
    
    def __init__(
        self,
        judge: DistillationJudge,
        memory_file: str,
        user_file: str
    ):
        self.judge = judge
        self.memory_file = Path(memory_file)
        self.user_file = Path(user_file)
    
    def run_reflection(self, session_ids: List[str]) -> dict:
        """
        执行反思整理
        
        Args:
            session_ids: 要整理的会话 ID 列表
        
        Returns:
            整理结果字典
        """
        
        # 1. 收集近期记忆
        memories = self._collect_recent_memories(session_ids)
        
        # 2. 提取用户偏好
        user_preferences = self._extract_user_preferences(memories)
        
        # 3. 提取环境事实
        environment_facts = self._extract_environment_facts(memories)
        
        # 4. 提取工作流模式
        workflow_patterns = self._extract_workflow_patterns(memories)
        
        # 5. 更新 MEMORY.md
        self._update_memory_file(environment_facts, workflow_patterns)
        
        # 6. 更新 USER.md
        self._update_user_file(user_preferences)
        
        return {
            "memories_processed": len(memories),
            "user_preferences_updated": len(user_preferences),
            "environment_facts_updated": len(environment_facts),
            "workflow_patterns_updated": len(workflow_patterns)
        }
    
    def _collect_recent_memories(self, session_ids: List[str]) -> List[dict]:
        """收集近期记忆"""
        
        all_memories = []
        
        for session_id in session_ids:
            # 从 SQLite 查询
            memories = self.judge.search_memories(
                query=session_id,
                limit=100,
                min_importance=0.5
            )
            all_memories.extend(memories)
        
        return all_memories
    
    def _extract_user_preferences(self, memories: List[dict]) -> List[dict]:
        """提取用户偏好"""
        
        prompt = f"""
从以下记忆中提取用户偏好：

## 记忆
{json.dumps(memories, indent=2, ensure_ascii=False)}

## 请提取：
1. 用户偏好的工具/技术
2. 用户的沟通风格
3. 用户的工作习惯
4. 用户的期望和要求

输出 JSON 数组：
[
  {{"key": "preferred_language", "value": "Python", "confidence": 0.9}},
  ...
]
"""
        
        response = self._call_llm(prompt)
        preferences = json.loads(response)
        
        return preferences
    
    def _extract_environment_facts(self, memories: List[dict]) -> List[dict]:
        """提取环境事实"""
        
        prompt = f"""
从以下记忆中提取环境事实（项目约定、工具配置、工作流程等）：

## 记忆
{json.dumps(memories, indent=2, ensure_ascii=False)}

## 请提取：
1. 项目约定（代码风格、命名规范）
2. 工具配置（使用的工具、版本、配置）
3. 工作流程（部署流程、测试流程）
4. 技术栈（框架、库、API）

输出 JSON 数组：
[
  {{"fact": "使用 Python 3.11", "category": "tech_stack", "importance": 0.8}},
  ...
]
"""
        
        response = self._call_llm(prompt)
        facts = json.loads(response)
        
        return facts
    
    def _extract_workflow_patterns(self, memories: List[dict]) -> List[dict]:
        """提取工作流模式"""
        
        prompt = f"""
从以下记忆中提取工作流模式（成功的任务执行模式）：

## 记忆
{json.dumps(memories, indent=2, ensure_ascii=False)}

## 请提取：
1. 成功的任务执行步骤
2. 关键决策点
3. 常见问题和解决方案
4. 验证方法

输出 JSON 数组：
[
  {{
    "pattern_name": "API 集成模式",
    "steps": ["分析 API 文档", "编写集成代码", "编写测试", "运行测试"],
    "success_rate": 0.95
  }},
  ...
]
"""
        
        response = self._call_llm(prompt)
        patterns = json.loads(response)
        
        return patterns
    
    def _update_memory_file(
        self,
        environment_facts: List[dict],
        workflow_patterns: List[dict]
    ) -> None:
        """更新 MEMORY.md"""
        
        content = "# Memory\n\n"
        
        content += "## Environment Facts\n\n"
        for fact in environment_facts:
            content += f"- {fact['fact']} (category: {fact['category']})\n"
        
        content += "\n## Workflow Patterns\n\n"
        for pattern in workflow_patterns:
            content += f"### {pattern['pattern_name']}\n"
            content += f"Success rate: {pattern['success_rate']:.0%}\n\n"
            content += "Steps:\n"
            for i, step in enumerate(pattern["steps"], 1):
                content += f"{i}. {step}\n"
            content += "\n"
        
        # 限制长度（约 2,200 字符）
        if len(content) > 2200:
            content = content[:2200] + "\n\n... (truncated)"
        
        self.memory_file.write_text(content, encoding="utf-8")
    
    def _update_user_file(self, user_preferences: List[dict]) -> None:
        """更新 USER.md"""
        
        content = "# User Profile\n\n"
        
        for pref in user_preferences:
            content += f"- **{pref['key']}**: {pref['value']} "
            content += f"(confidence: {pref['confidence']:.0%})\n"
        
        # 限制长度（约 1,375 字符）
        if len(content) > 1375:
            content = content[:1375] + "\n\n... (truncated)"
        
        self.user_file.write_text(content, encoding="utf-8")
    
    def _call_llm(self, prompt: str) -> str:
        """调用 LLM"""
        # 实际实现：通过 OpenClaw 的 LLM 调用接口
        return "[]"
```

### 5.4 业界最佳实践

**NEMORI 框架**：
- 使用预测误差识别值得保留的信息
- 可预测信息被认为是冗余的
- 通过语义知识蒸馏将情景记忆转化为语义记忆

**Mem0**：
- 使用 LLM 从对话中提取"显著记忆"
- 决定是否添加或更新记忆
- Mem0g 版本使用有向标记图存储记忆

**推荐做法**：
1. **多层记忆模型**：短期工作记忆 + 长期情景/语义/程序性记忆
2. **蒸馏时过滤**：在信息摄入时评分、标记情感、提取事实
3. **定期整理**：使用 LLM 定期整理记忆，提取模式

---

## 6. 业界最佳实践调研

### 6.1 OpenAI Symphony

**核心架构**：
- **编排器**：长时间运行的自动化服务，持续监控 issue tracker
- **控制平面**：使用 Linear/GitHub 等项目管理工具作为控制平面
- **隔离工作区**：为每个 issue 创建隔离工作区
- **WORKFLOW.md**：Agent 提示和运行时设置版本化在代码库中

**关键设计**：
- 使用 Elixir 的 BEAM 虚拟机实现容错、并发 Agent 管理
- Agent 通过 ticket 写入（状态转换、评论、PR 链接）与控制平面交互
- 人类负责审查完成的任务、实现计划和 PR

**启示**：
- 使用现有项目管理工具作为控制平面是可行的
- 隔离工作区防止冲突
- 人类在环（HITL）是关键

### 6.2 Claude Squad

**核心架构**：
- **Git Worktrees**：每个 Agent 在独立的 Git worktree 中工作
- **tmux**：使用 tmux 管理多个 Agent 会话
- **人类在环节点**：Agent 独立工作，但在关键节点需要人类批准

**关键设计**：
- Agent 之间没有直接通信
- 每个 Agent 有自己的上下文窗口
- 编排层维护整体项目上下文

**启示**：
- Git worktrees 是隔离代码的有效方式
- Agent 之间不需要直接通信，通过控制平面协调即可

### 6.3 Composio Agent Orchestrator

**核心架构**：
- **模块化插件系统**：8 个可互换槽位（Runtime, Agent, Workspace, Tracker, SCM, Notifier, Terminal, Lifecycle）
- **双层任务管理**：Planner（高层分解）+ Executor（工具交互）
- **自主 PR 处理**：自动修复 CI 失败、响应审查评论

**关键设计**：
- 自我改进系统：观察 Agent 执行结果，记录性能指标
- 递归自我改进循环
- MCP（Model Context Protocol）集成层

**启示**：
- 模块化设计提高可扩展性
- 双层架构（Planner + Executor）比单层 ReAct 更稳健
- 自我改进是可能的

### 6.4 Factory AI

**核心架构**（制造业场景，但可借鉴）：
- **数据摄入层**：传感器、PLC/SCADA、MES/ERP
- **中央数据层**：数据湖、数字孪生、知识库
- **AI 模型层**：模型仓库、推理引擎、监控和重训练
- **编排引擎层**：事件处理、决策制定、目标管理
- **代码生成层**：上下文化、代码生成、约束检查、模拟测试
- **执行层**：执行器接口、软件系统集成
- **监控层**：系统监控、审计日志、安全模块

**启示**：
- 分层架构是复杂系统的标准做法
- 数字孪生（模拟测试）可以减少物理世界风险
- 约束检查和模拟测试是关键

### 6.5 开源编排框架

**CrewAI**：
- Python 框架，基于角色的架构
- 定义 Agent 的角色、目标、背景故事
- 支持 Agent 间协作

**AutoGen（Microsoft）**：
- 通过对话模式构建多 Agent 系统
- 支持自定义工具、记忆、人类在环

**LangGraph（LangChain）**：
- 基于图的架构，适合循环、条件、非线性流程
- 管理跨 Agent 的状态和流

**Claude Squad**：
- 开源 Agent 编排器
- 使用 Git worktrees 和 tmux 隔离
- 支持多种 coding agent

**Windmill**：
- 开源、可自托管的编排平台
- 代码优先，完全控制基础设施

**启示**：
- 没有银弹，每个框架都有自己的适用场景
- 基于角色的架构（CrewAI）适合协作任务
- 基于图的架构（LangGraph）适合复杂流程

### 6.6 最佳实践总结

**编排模式**：
1. **顺序执行**：任务按特定顺序执行
2. **并行执行**：独立任务同时执行
3. **层级执行**：Planner 分解任务，Executor 执行子任务
4. **事件驱动**：Agent 响应系统事件
5. **工具路由**：动态选择最合适的工具/模型

**关键原则**：
1. **窄而清晰的范围**：给 Agent 明确、狭窄的责任范围
2. **显式函数调用**：声明 Agent 可以调用的显式、类型化函数
3. **任务导向提示**：鼓励 Agent 在执行前规划步骤
4. **迭代开发**：从简单 Agent 开始，基于反馈迭代
5. **结果验证**：建立自动化测试管道验证 Agent 输出
6. **安全隔离**：在隔离容器中运行 Agent

**LLM 用于推理，代码用于执行**：
- LLM 严格用于推理、意图提取、规划
- 传统、确定性代码用于实际执行（计算、数据库写入）
- 使用严格的 JSON 验证模式

---

## 7. 挑战和难度评估

### 7.1 技术难度评估

| 组件 | 技术难度 | 主要挑战 | 风险等级 |
|-----|---------|---------|---------|
| **Ship Package Importer** | 低 | Schema 验证、拓扑排序 | 🟢 低 |
| **Kanban Task Creator** | 低 | 状态机初始化 | 🟢 低 |
| **Codex Scheduler** | 中 | 并行执行、超时管理、错误处理 | 🟡 中 |
| **Claude Code Scheduler** | 中 | SDK 集成、异步执行 | 🟡 中 |
| **State Machine** | 低 | 状态转换验证 | 🟢 低 |
| **Event Logger** | 低 | 事件记录、审计追踪 | 🟢 低 |
| **Adaptive Decision Maker** | 高 | 错误分类、决策逻辑 | 🔴 高 |
| **Skill Auto-Creator** | 高 | 模式提取、技能生成、验证 | 🔴 高 |
| **Distillation Judge** | 高 | 重要性评估、LLM 调用 | 🔴 高 |
| **Reflection Pass** | 中 | 记忆整理、USER.md 更新 | 🟡 中 |
| **State Persistence** | 中 | 检查点、断点续接 | 🟡 中 |

### 7.2 开发工作量评估

| 组件 | 工作量（人周） | 说明 |
|-----|-------------|------|
| **Ship Package Importer** | 1 | 已有实现，需要微调 |
| **Kanban Task Creator** | 1 | 已有实现，需要微调 |
| **Codex Scheduler** | 2 | 已有实现，需要增强并行执行 |
| **Claude Code Scheduler** | 2 | 新建，参考 Codex Scheduler |
| **State Machine** | 1 | 已有实现，需要增强 |
| **Event Logger** | 0.5 | 已有实现 |
| **Adaptive Decision Maker** | 3 | 新建，需要错误分类和决策逻辑 |
| **Skill Auto-Creator** | 4 | 新建，需要模式提取和技能生成 |
| **Distillation Judge** | 3 | 新建，需要重要性评估 |
| **Reflection Pass** | 2 | 新建，需要记忆整理逻辑 |
| **State Persistence** | 1.5 | 新建，需要检查点和断点续接 |
| **集成测试** | 3 | 端到端测试 |
| **文档** | 1 | 用户文档、API 文档 |
| **总计** | **25 人周** | 约 6 个月（1 人全职） |

### 7.3 主要风险

**技术风险**：
1. **Codex/Claude Code API 不稳定**：SDK 可能变化，需要持续维护
2. **LLM 调用成本**：Reflection Pass 和 Distillation Judge 需要频繁调用 LLM
3. **并行执行复杂性**：管理多个并行 Codex/Claude Code 任务的复杂性
4. **技能质量**：自动创建的技能可能质量不稳定

**产品风险**：
1. **用户接受度**：用户可能不信任自动创建的技能
2. **调试困难**：多 Agent 系统的调试比单 Agent 更困难
3. **性能瓶颈**：LLM 调用可能成为性能瓶颈

**维护风险**：
1. **持续维护成本**：需要持续维护 Codex/Claude Code 集成
2. **技能膨胀**：自动创建的技能可能积累过多，需要清理

### 7.4 与方案 A 的对比

| 维度 | 方案 A（Hermes + Codex） | 方案 B（OpenClaw 内构建） |
|-----|------------------------|------------------------|
| **开发工作量** | 2 人周（集成） | 25 人周（自建） |
| **维护成本** | 低（依赖 Hermes） | 高（自建自维） |
| **可控性** | 低（黑盒） | 高（白盒） |
| **可定制性** | 低（受 Hermes 限制） | 高（完全定制） |
| **天花板** | 中（Hermes 能力边界） | 高（无限制） |
| **风险** | 低（成熟方案） | 高（自建风险） |
| **与 OpenClaw 集成** | 中（需要桥接） | 高（原生集成） |
| **与 DeepFlow 集成** | 低（需要适配） | 高（原生集成） |

---

## 8. 方案 A vs B 修正对比

### 8.1 初始对比（来自方案调研）

| 维度 | 方案 A | 方案 B |
|-----|-------|-------|
| 核心思路 | 直接用 Hermes Agent + Codex | 在 OpenClaw 内构建类 Hermes 引擎 |
| 开发工作量 | 2 人周 | 25 人周 |
| 维护成本 | 低 | 高 |
| 可控性 | 低 | 高 |
| 天花板 | 中 | 高 |

### 8.2 修正对比（基于深度调研）

**方案 A 的优势**：
1. **快速上线**：2 人周即可集成
2. **成熟方案**：Hermes 已经实现持久记忆、技能自动创建、Reflection Pass
3. **低风险**：不需要自建复杂系统

**方案 A 的劣势**：
1. **黑盒**：Hermes 内部机制不透明
2. **集成成本**：需要桥接 Hermes ↔ OpenClaw ↔ DeepFlow
3. **定制受限**：受 Hermes 能力边界限制
4. **数据流复杂**：DeepFlow → Hermes → Codex → Hermes → DeepFlow

**方案 B 的优势**：
1. **原生集成**：与 OpenClaw 和 DeepFlow 原生集成
2. **完全可控**：白盒系统，可以深度定制
3. **数据流简单**：DeepFlow → OpenClaw Orchestrator → Codex/Claude
4. **无天花板**：可以根据需求无限扩展

**方案 B 的劣势**：
1. **开发周期长**：25 人周（约 6 个月）
2. **维护成本高**：需要持续维护 Codex/Claude Code 集成
3. **技术风险高**：自建系统可能遇到未预见的问题

### 8.3 修正后的推荐

**如果时间紧迫（< 2 个月）**：
- 选择**方案 A**，快速上线验证价值

**如果追求长期价值（> 6 个月）**：
- 选择**方案 B**，构建核心竞争力

**折中方案（推荐）**：
- **Phase 1（0-2 月）**：用方案 A 快速上线，验证需求
- **Phase 2（2-8 月）**：逐步用方案 B 替换方案 A 的核心组件
- **Phase 3（8+ 月）**：完全迁移到方案 B

---

## 9. 推荐路径

### 9.1 Phase 1：快速验证（0-2 月）

**目标**：用方案 A 快速上线，验证需求价值

**任务**：
1. 集成 Hermes Agent（2 人周）
2. 配置 Codex 集成（1 人周）
3. 测试 DeepFlow → Hermes → Codex 流程（1 人周）
4. 收集用户反馈（持续）

**交付物**：
- 可工作的端到端流程
- 用户反馈报告

### 9.2 Phase 2：逐步替换（2-8 月）

**目标**：逐步用方案 B 替换方案 A 的核心组件

**任务**：
1. 构建 Ship Package Importer（1 人周）
2. 构建 Codex Scheduler（2 人周）
3. 构建 Claude Code Scheduler（2 人周）
4. 构建 State Machine + Event Logger（1.5 人周）
5. 构建 Adaptive Decision Maker（3 人周）
6. 集成测试（2 人周）

**交付物**：
- 可工作的编排引擎（不含技能自动创建和记忆系统）
- 端到端测试报告

### 9.3 Phase 3：完整系统（8-12 月）

**目标**：构建完整的类 Hermes 引擎

**任务**：
1. 构建 Skill Auto-Creator（4 人周）
2. 构建 Distillation Judge（3 人周）
3. 构建 Reflection Pass（2 人周）
4. 构建 State Persistence（1.5 人周）
5. 集成测试（3 人周）
6. 文档（1 人周）

**交付物**：
- 完整的类 Hermes 引擎
- 用户文档和 API 文档
- 性能测试报告

### 9.4 关键里程碑

| 里程碑 | 时间 | 交付物 |
|-------|------|-------|
| **M1: 方案 A 上线** | 第 2 月 | Hermes + Codex 集成 |
| **M2: 编排引擎 MVP** | 第 5 月 | Ship Package → Codex 执行 |
| **M3: 完整编排引擎** | 第 8 月 | 含 Adaptive Decision Maker |
| **M4: 完整类 Hermes 引擎** | 第 12 月 | 含技能自动创建和记忆系统 |

### 9.5 资源需求

**人力**：
- 1 名全栈工程师（全职，12 个月）
- 或 2 名工程师（半职，12 个月）

**基础设施**：
- Codex API 费用：约 $500/月
- Claude API 费用：约 $500/月
- LLM 调用费用（Reflection Pass 等）：约 $200/月
- 总计：约 $1,200/月

**风险缓冲**：
- 建议增加 20% 时间缓冲（约 2.5 个月）
- 建议增加 30% 预算缓冲（约 $4,300）

---

## 附录

### A. 参考资料

1. **OpenAI Symphony**: https://openai.com/index/open-source-codex-orchestration-symphony/
2. **Claude Squad**: https://github.com/claude-squad/claude-squad
3. **Composio Agent Orchestrator**: https://composio.dev/blog/the-self-improving-ai-system-that-built-itself
4. **Hermes Agent**: https://hermes-agent.org/
5. **OpenClaw ACP**: https://docs.openclaw.ai/cli/acp
6. **Claude Agent SDK**: https://code.claude.com/docs/en/agent-sdk/overview
7. **Codex SDK**: https://developers.openai.com/codex/sdk

### B. 术语表

- **Ship Package**: DeepFlow 产出的交付物，包含 Work Packages 列表
- **Work Package (WP)**: 单个可执行的工作单元，包含 AC（验收标准）
- **ACP**: Agent Client Protocol，OpenClaw 用于连接 IDE 与 AI Agent 的协议
- **Reflection Pass**: 定期 LLM 整理记忆的机制
- **Distillation Judge**: 评估信息重要性，决定是否保留的组件
- **Skill Auto-Creator**: 自动从成功任务中提取并创建技能的系统

### C. 代码示例索引

- **Ship Package Importer**: `core/scheduler/ship_importer/ship_importer.py`
- **Kanban Task Creator**: `core/scheduler/task_creator/task_creator.py`
- **Codex Scheduler**: `core/scheduler/codex_scheduler/codex_scheduler.py`
- **State Machine**: `core/scheduler/state_machine/state_machine.py`
- **Event Logger**: `core/quality/observability.py`

---

**报告完成时间**: 2026-01-XX  
**报告作者**: AI Agent (OpenClaw Sub-agent)  
**报告版本**: 1.0.0
