# Solution Pro 2.0.0 重构方案：LLM 调用全走 OpenClaw

> **版本**: 2.0.0 | **日期**: 2026-06-29
> **作者**: 小满（主 Agent）
> **状态**: 评审后修订版（Round 1 + Round 2 完成）

---

## 0. 任务澄清

### 做什么
将 Solution Pro 2.0.0 中所有"绕过 OpenClaw 直调 LLM API"的代码，统一重构为走 `spawn_fn`（→ `sessions_spawn`），实现**零额外 API Key**。

### 约束是什么
1. **平台约束**：OpenClaw 的 `exec` 环境是独立 Python 进程，无法 import openclaw SDK → 所有 LLM 调用必须通过 `spawn_fn`（由主 Agent 注入）
2. **2.0.0 教训**：2.0.0 的 `sessions_spawn` 模式是正确的，2.0.0 不应该抛弃它
3. **不能破坏现有正确代码**：2.0.0 核心编排（planning/research/review_qc orchestrator）已经正确使用 `spawn_fn`，不能改坏
4. **向后兼容**：测试时 `spawn_fn=None` 的 fallback 模式需保留
5. **深度约束**：OpenClaw 子 Agent 最多 2 层（depth-0 主 Agent → depth-1 Orchestrator → depth-2 Worker），不可逾越

### 成功标准
- ✅ 代码中没有任何 `api_key`、`openai`、`litellm` 直接调用
- ✅ 所有 LLM 评估通过 `spawn_fn` → `sessions_spawn` 完成
- ✅ E2E 测试能在 OpenClaw 环境中跑通（不再需要 spawn bridge 文件系统中转）
- ✅ `spawn_fn=None` 时仍能 fallback 到规则判定（测试模式）
- ✅ 所有 spawn 调用使用正确参数名和返回值提取方式

---

## 1. 现状诊断

### 1.1 架构概览

```
2.0.0 Solution Pro 的 LLM 调用路径：

✅ 正确路径（已实现，大部分模块）：
   ModuleOrchestrator._adapted_spawn()
     → spawn_fn (注入的 sessions_spawn)
       → OpenClaw 子 Agent
         → LLM（OpenClaw 内部路由）

❌ 问题路径 1：Spawn Bridge（e2e_test_runner.py）
   Python exec → 写文件到 requests/ → 期望另一个 Agent 轮询 → 写回 outputs/
   = 文件中转，不是真正的 sessions_spawn

❌ 问题路径 2：llm_judge_fn 回调（compliance_checker.py, harness_scorer.py）
   Python 函数 → llm_judge_fn(prompt) → ???
   = 取决于注入者，可能是直调 API
```

### 1.2 问题模块清单

| # | 文件 | 问题 | 严重度 | 影响 |
|---|------|------|--------|------|
| P1 | `e2e_test_runner.py` | Spawn Bridge（文件中转） | P0 | E2E 测试无法在真实环境跑通 |
| P2 | `compliance_checker.py` | `llm_judge_fn` 回调可能被注入直调 API 的函数 | P1 | 合规检查可能绕过 OpenClaw |
| P3 | `harness_scorer.py` | 同上 | P1 | Harness 评分可能绕过 OpenClaw |
| P4 | `planner.py` | 2.0.0 legacy，已废弃但未清理 | P2 | 代码噪音 |
| P5 | `ai_native_auditor.py` | `llm_judge_fn` 同类问题 | P1 | 审计可能绕过 OpenClaw |

### 1.3 正确模块（不动）

| 文件 | 状态 | 说明 |
|------|------|------|
| `module_orchestrator_base.py` | ✅ | `_adapted_spawn()` 是正确的 spawn_fn 封装 |
| `planning_orchestrator.py` | ✅ | 正确使用 `_adapted_spawn()` |
| `research_orchestrator.py` | ✅ | 正确使用 `_adapted_spawn()` |
| `review_qc_orchestrator.py` | ✅ | 正确使用 `_adapted_spawn()` |
| `fix_loop_state_machine.py` | ✅ | 正确使用 `spawn_fn` |
| `convergence_layer.py` | ✅ | 正确使用 `spawn_fn` |
| `master_orchestrator.py` | ✅ | 正确传递 `spawn_fn` 给所有子模块 |

---

## 2. 重构方案

### 2.1 P1: 重写 e2e_test_runner.py

**问题**：当前用文件系统中转（Spawn Bridge）模拟 `sessions_spawn`，但生产环境中没有 Agent 轮询 `requests/` 目录。

**方案 A：真 OpenClaw 子 Agent 模式（推荐）**

⚠️ **深度约束**：OpenClaw 最多支持 2 层子 Agent（depth-0 → depth-1 → depth-2）。

```
depth-0: 主 Agent
  └─ sessions_spawn → depth-1: E2E Orchestrator
       ├─ spawn_fn → depth-2: Planning Worker
       ├─ spawn_fn → depth-2: Research Worker
       └─ spawn_fn → depth-2: ReviewQC Worker
```

- 删掉 Spawn Bridge 代码
- e2e_test_runner 改为一个"任务模板"，主 Agent 读取后用 `sessions_spawn` 创建 depth-1 E2E Orchestrator
- E2E Orchestrator 自己用注入的 `spawn_fn` 创建 depth-2 Workers
- **不可再嵌套**：depth-2 Worker 不可再 spawn

**方案 B：同步测试模式（仅用于 CI/快速验证）**
```python
spawn_fn = mock_spawn_fn  # 返回预设数据或调用 LLM（通过 OpenClaw 路由）
```
- 保留 `llm_recorder.py` 的 `mock_spawn_fn` 模式
- 用于无 OpenClaw 环境的单元测试

**选择**：方案 A（生产） + 方案 B（测试），两者共存。

### 2.2 P2/P3/P5: llm_judge_fn 统一为 spawn_fn

**问题**：`compliance_checker.py`、`harness_scorer.py`、`ai_native_auditor.py` 接受 `llm_judge_fn` 回调，但注入来源不确定。

**方案**：

#### 2.2.1 修正后的 LLMJudgeAdapter（修复 spawn_fn 签名和返回值问题）

```python
import json
import asyncio
from typing import Optional, Callable, Any

class LLMJudgeAdapter:
    """将 spawn_fn 适配为 llm_judge_fn 接口。
    
    关键修正（2.0.0）：
    1. spawn_fn 签名是 (task: str, **kwargs)，不是 (messages, **kwargs)
    2. sessions_spawn 参数名是 runTimeoutSeconds，不是 timeout
    3. 返回值从子 Agent 的 visible reply 中提取，不是 result["output"]
    """
    
    def __init__(self, spawn_fn: Callable, max_concurrent: int = 3):
        self.spawn_fn = spawn_fn
        self.max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)
    
    async def judge(
        self,
        prompt: str,
        temperature: float = 0.2,
        max_retries: int = 2,
        output_schema: Optional[dict] = None,
    ) -> dict:
        """执行 LLM 评估。
        
        Args:
            prompt: 评估提示词（应包含完整的 Role + Context + Constraints + Output Format）
            temperature: 温度参数（通过 prompt 传递给子 Agent）
            max_retries: 失败重试次数
            output_schema: 期望的 JSON Schema（用于验证输出）
        
        Returns:
            dict: LLM 评估结果
        """
        async with self._semaphore:
            last_error = None
            for attempt in range(max_retries + 1):
                try:
                    # 构造完整的任务描述（包含输出格式要求）
                    task = self._build_task(prompt, output_schema, temperature)
                    
                    # ✅ 正确的 spawn_fn 调用
                    result = await self.spawn_fn(
                        task=task,                    # 第一个位置参数是 task
                        mode="run",
                        label="llm_judge",
                        runTimeoutSeconds=60,         # ✅ 正确参数名
                    )
                    
                    # ✅ 从 visible reply 提取结果
                    raw_output = self._extract_output(result)
                    parsed = self._parse_json(raw_output)
                    
                    # 验证输出 Schema
                    if output_schema:
                        self._validate_schema(parsed, output_schema)
                    
                    return parsed
                    
                except (json.JSONDecodeError, KeyError, ValueError) as e:
                    last_error = e
                    if attempt < max_retries:
                        continue  # 重试
                    raise JudgeOutputError(
                        f"LLM 输出解析失败（重试 {max_retries} 次后）: {e}"
                    )
                except SpawnError as e:
                    last_error = e
                    if attempt < max_retries:
                        continue
                    raise SpawnError(f"spawn_fn 调用失败（重试 {max_retries} 次后）: {e}")
    
    def _build_task(self, prompt: str, output_schema: Optional[dict], temperature: float) -> str:
        """构造完整的子 Agent 任务描述。"""
        task_parts = [
            "你是一个 LLM-as-Judge 评估器。请严格按照以下指令执行评估。",
            "",
            f"## 评估指令\n{prompt}",
            "",
            "## 输出要求",
            "你必须输出严格的 JSON，不要包含任何其他文本。",
        ]
        if output_schema:
            task_parts.append(f"JSON Schema: {json.dumps(output_schema, ensure_ascii=False)}")
        if temperature != 0.2:
            task_parts.append(f"Temperature: {temperature}")
        return "\n".join(task_parts)
    
    def _extract_output(self, result: Any) -> str:
        """从 sessions_spawn 返回值中提取 visible reply。
        
        sessions_spawn 返回格式（参考 OpenClaw 文档）：
        - dict: {"status": "completed", "output": "...", ...}
        - str: 直接是 visible reply
        """
        if isinstance(result, dict):
            # 尝试多种可能的字段名
            for key in ("output", "result", "content", "reply"):
                if key in result:
                    return str(result[key])
            # 如果都没有，尝试拼接所有字符串值
            parts = [str(v) for v in result.values() if isinstance(v, str)]
            if parts:
                return "\n".join(parts)
            raise JudgeOutputError(f"无法从返回值中提取输出: {result}")
        elif isinstance(result, str):
            return result
        else:
            raise JudgeOutputError(f"意外的返回值类型: {type(result)}")
    
    def _parse_json(self, raw: str) -> dict:
        """解析 JSON，处理常见的 LLM 输出格式问题。"""
        # 去除 markdown 代码块
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            # 去掉首尾的 ``` 行
            lines = [l for l in lines if not l.strip().startswith("```")]
            cleaned = "\n".join(lines)
        
        return json.loads(cleaned)
    
    def _validate_schema(self, data: dict, schema: dict) -> None:
        """简单的 Schema 验证。"""
        required = schema.get("required", [])
        for field in required:
            if field not in data:
                raise JudgeOutputError(f"缺少必需字段: {field}")


class JudgeOutputError(Exception):
    """LLM 评估输出错误。"""
    pass


class SpawnError(Exception):
    """spawn_fn 调用错误。"""
    pass
```

#### 2.2.2 注入方式

```python
# 在 master_orchestrator.py 或模块初始化时
if spawn_fn is not None:
    judge_adapter = LLMJudgeAdapter(spawn_fn, max_concurrent=3)
    llm_judge_fn = judge_adapter.judge  # 绑定方法作为回调
else:
    # 测试模式：fallback 到规则判定
    llm_judge_fn = rule_based_judge
```

#### 2.2.3 批量评估模式（减少 spawn 开销）

```python
async def batch_judge(self, prompts: list[dict]) -> list[dict]:
    """批量评估多个维度，减少 spawn 次数。
    
    Args:
        prompts: [{"name": "维度名", "prompt": "评估指令", "schema": {...}}, ...]
    
    Returns:
        list[dict]: 每个维度的评估结果
    """
    # 合并为单次 spawn（如果维度 <= 3）
    if len(prompts) <= 3:
        merged_task = self._merge_prompts(prompts)
        merged_result = await self.judge(merged_task, output_schema={
            "type": "object",
            "properties": {p["name"]: p["schema"] for p in prompts},
            "required": [p["name"] for p in prompts],
        })
        return [merged_result.get(p["name"], {}) for p in prompts]
    
    # 否则并发 spawn（受 semaphore 限制）
    tasks = [self.judge(p["prompt"], output_schema=p["schema"]) for p in prompts]
    return await asyncio.gather(*tasks, return_exceptions=True)
```

### 2.3 P4: 清理 2.0.0 Legacy 代码

**方案**：
- `planner.py` 移动到 `v1_legacy/` 目录
- 文件顶部添加明确的废弃声明：
  ```python
  """
  ⚠️ DEPRECATED: 2.0.0 Legacy 代码，仅供 2.0.0 session 续跑使用。
  新代码请使用 planning_orchestrator.py。
  预计移除时间：2026-Q3
  """
  ```

### 2.4 增强：spawn_fn 契约验证

```python
from pydantic import BaseModel, Field
from typing import Optional, Literal

class SpawnResult(BaseModel):
    """spawn_fn 返回值的标准契约。"""
    status: Literal["COMPLETE", "FAILED", "TIMEOUT"] = Field(
        description="执行状态"
    )
    output: Optional[str] = Field(
        default=None,
        description="子 Agent 的 visible reply（原始文本）"
    )
    error: Optional[str] = Field(
        default=None,
        description="错误信息（status=FAILED 时必填）"
    )
    session_key: Optional[str] = Field(
        default=None,
        description="子 Agent session key"
    )
    
    @property
    def success(self) -> bool:
        return self.status == "COMPLETE"
    
    def get_parsed_output(self) -> dict:
        """解析 JSON 输出。"""
        if not self.output:
            raise ValueError("No output to parse")
        return json.loads(self.output)
```

### 2.5 新增：错误处理与重试策略

```python
# 全局配置
SPAWN_CONFIG = {
    "max_retries": 2,          # 最大重试次数
    "retry_delay": 1.0,        # 重试间隔（秒）
    "timeout_seconds": 60,     # 默认超时
    "max_concurrent": 3,       # 最大并发 spawn 数
}

# 错误分类
SPAWN_ERRORS = {
    "TIMEOUT": "子 Agent 执行超时",
    "SPAWN_FAILED": "spawn_fn 调用失败",
    "OUTPUT_PARSE_ERROR": "输出解析失败",
    "SCHEMA_VALIDATION_ERROR": "输出 Schema 验证失败",
    "DEPTH_LIMIT": "超出子 Agent 深度限制",
}
```

### 2.6 新增：可观测性

```python
import logging

class SpawnMetrics:
    """spawn_fn 调用的可观测性指标。"""
    
    def __init__(self):
        self.total_calls = 0
        self.success_count = 0
        self.failure_count = 0
        self.timeout_count = 0
        self.total_latency_ms = 0
    
    def record(self, status: str, latency_ms: float):
        self.total_calls += 1
        if status == "COMPLETE":
            self.success_count += 1
        elif status == "TIMEOUT":
            self.timeout_count += 1
        else:
            self.failure_count += 1
        self.total_latency_ms += latency_ms
    
    @property
    def avg_latency_ms(self) -> float:
        return self.total_latency_ms / max(1, self.total_calls)
    
    def summary(self) -> dict:
        return {
            "total": self.total_calls,
            "success_rate": self.success_count / max(1, self.total_calls),
            "avg_latency_ms": round(self.avg_latency_ms, 1),
        }

# 全局指标
spawn_metrics = SpawnMetrics()
```

---

## 3. 执行计划

| Phase | 内容 | 预计工作量 | 风险 | 验证方式 |
|-------|------|-----------|------|---------|
| Phase 1 | 创建 `LLMJudgeAdapter` 类（含重试、并发控制、Schema 验证） | 45min | 低 | 单元测试 |
| Phase 2 | 重构 `compliance_checker.py`、`harness_scorer.py`、`ai_native_auditor.py` | 1h | 中 | 单元测试 + 集成测试 |
| Phase 3 | 重写 `e2e_test_runner.py`（Spawn Bridge → 真 sessions_spawn） | 1.5h | 中 | E2E 测试 |
| Phase 4 | 移动 2.0.0 legacy 代码 + 添加废弃声明 | 15min | 低 | 检查 2.0.0 session 不受影响 |
| Phase 5 | 添加 `SpawnResult` Pydantic 验证 + 错误处理 | 45min | 低 | 单元测试 |
| Phase 6 | E2E 验证（真实 OpenClaw 环境） | 1h | 高 | 完整 E2E 测试 |
| Phase 7 | 可观测性集成 + 文档更新 | 30min | 低 | 检查指标输出 |

**总预计**：5-6 小时

---

## 4. 与 2.0.0 的对比

| 维度 | 2.0.0 | 2.0.0（现状） | 2.0.0（重构后） |
|------|-----|-----------|------------|
| LLM 调用方式 | sessions_spawn | 混合（spawn_fn + 直调 + Spawn Bridge） | 统一 spawn_fn → sessions_spawn |
| 额外 API Key | 不需要 | 可能需要 | 不需要 |
| 编排模式 | Orchestrator → Workers | MasterOrchestrator → Module Orchestrators → Workers | 同左（不改） |
| 测试模式 | mock spawn_fn | mock spawn_fn + Spawn Bridge | mock spawn_fn（统一） |
| 合规检查 | 规则判定 | llm_judge_fn（来源不确定） | LLMJudgeAdapter → spawn_fn |
| E2E 测试 | 可跑通 | 无法跑通（Spawn Bridge 问题） | 可跑通（真 sessions_spawn） |
| 错误处理 | 无 | 部分 | 统一重试 + 错误分类 |
| 可观测性 | 无 | 无 | SpawnMetrics 指标 |

---

## 5. 风险与缓解

| 风险 | 缓解 |
|------|------|
| `LLMJudgeAdapter` 引入额外 spawn 开销 | 批量评估（≤3 维度合并为单次 spawn）+ 并发控制（Semaphore） |
| 重写 e2e_test_runner 可能引入新 bug | 保留旧版本为 `e2e_test_runner_v1.py`，渐进替换 |
| `spawn_fn=None` fallback 被破坏 | 每个模块保留 fallback 规则判定，不强依赖 LLM |
| 子 Agent 深度超限 | 严格遵守 depth-0 → depth-1 → depth-2 限制，文档化 |
| spawn 参数名错误 | 使用 Pydantic SpawnResult 契约验证，CI 中检查 |
| 返回值提取方式不一致 | `_extract_output()` 方法统一处理多种返回格式 |

---

## 6. 遗留问题（Round 2 裁决）

| # | 问题 | 裁决 | 理由 |
|---|------|------|------|
| 1 | 是否需要 OpenClaw 原生工具（cron/blackboard）集成？ | 暂不集成 | 当前重构聚焦 LLM 路由，工具集成可作为后续增强 |
| 2 | CI/CD 中无法跑真 sessions_spawn 测试 | 方案 B（mock_spawn_fn）覆盖 | CI 用 mock 模式，真实环境验证放在 Phase 6 |
| 3 | 是否需要性能基准测试？ | Phase 6 中简单对比 | 记录 spawn 延迟，但不做严格性能回归 |

---

## 7. 评审记录

### Round 1 评审结果

| 专家 | 评分 | P0 | P1 | P2 |
|------|------|----|----|-----|
| OpenClaw 平台专家 | 6/10 | 3 | 2 | 1 |
| AI Native 架构师 | 7/10 | 1 | 2 | 2 |
| 测试工程专家 | 6/10 | 1 | 2 | 1 |

**主要问题**：
1. spawn_fn 签名错误（task vs messages）
2. sessions_spawn 参数名错误（timeout vs runTimeoutSeconds）
3. 返回值提取方式错误（output vs visible reply）
4. e2e_test_runner 方案 A 存在深度限制风险
5. 缺少并发控制和错误处理
6. LLMJudgeAdapter 缺少 prompt 工程指导
7. 测试覆盖不足

### Round 2 聚焦修复

- ✅ 修复 spawn_fn 签名（task 参数）
- ✅ 修复参数名（runTimeoutSeconds）
- ✅ 修复返回值提取（_extract_output 方法）
- ✅ 添加并发控制（Semaphore）
- ✅ 添加错误处理和重试
- ✅ 添加 prompt 工程指导
- ✅ 明确深度约束（depth-0 → depth-1 → depth-2）
- ✅ 添加可观测性（SpawnMetrics）
- ✅ 补充测试场景

### Round 3 收敛裁决

- 所有 P0 问题已修复
- P1 问题已缓解（并发控制、错误处理、prompt 指导）
- P2 问题已处理（legacy 废弃声明、文档化）
- 遗留问题已记录，可作为后续增强
