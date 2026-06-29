# Solution Pro V2 重构方案：LLM 调用全走 OpenClaw

> **版本**: V3.0 | **日期**: 2026-06-29
> **作者**: 小满（主 Agent）
> **状态**: 评审后终版（Round 1 + Round 2 + Round 3 完成）

---

## 0. 任务澄清

### 做什么
将 Solution Pro V2 中所有"绕过 OpenClaw 直调 LLM API"的代码，统一重构为走 `spawn_fn`（→ `sessions_spawn`），实现**零额外 API Key**。

### 约束是什么
1. **平台约束**：OpenClaw 的 `exec` 环境是独立 Python 进程，无法 import openclaw SDK → 所有 LLM 调用必须通过 `spawn_fn`（由主 Agent 注入）
2. **V1 教训**：V1 的 `sessions_spawn` 模式是正确的，V2 不应该抛弃它
3. **不能破坏现有正确代码**：V2 核心编排（planning/research/review_qc orchestrator）已经正确使用 `spawn_fn`，不能改坏
4. **向后兼容**：测试时 `spawn_fn=None` 的 fallback 模式需保留
5. **深度约束**：OpenClaw 子 Agent 最多 2 层（depth-0 主 Agent → depth-1 Orchestrator → depth-2 Worker），不可逾越

### 成功标准
- ✅ 代码中没有任何 `api_key`、`openai`、`litellm` 直接调用
- ✅ 所有 LLM 评估通过 `spawn_fn` → `sessions_spawn` 完成
- ✅ E2E 测试能在 OpenClaw 环境中跑通（不再需要 spawn bridge 文件系统中转）
- ✅ `spawn_fn=None` 时仍能 fallback 到规则判定（测试模式）
- ✅ spawn_fn 使用正确的同步阻塞调用方式，返回字符串

---

## 1. 现状诊断

### 1.1 架构概览

```
V2 Solution Pro 的 LLM 调用路径：

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

### 1.2 spawn_fn 精确契约（Round 2 裁决）

```python
from typing import Protocol, Optional

class SpawnFn(Protocol):
    """spawn_fn 的精确接口契约。
    
    关键约束（Round 2 裁决）：
    1. 同步阻塞调用，返回字符串（子 Agent 的 visible reply）
    2. 不是 async，不是 dict，是 str
    3. 通过依赖注入传递（构造函数/方法参数），不通过 exec 环境变量
    """
    def __call__(
        self,
        task: str,                          # 必填：任务描述
        *,
        mode: str = "run",                  # 运行模式
        label: Optional[str] = None,        # 标签
        runTimeoutSeconds: Optional[int] = None,  # 超时（秒）
        # ... 其他 sessions_spawn 参数
    ) -> str:
        """同步阻塞，返回子 Agent 的 visible reply（字符串）。"""
        ...
```

**注入链路**：
```
depth-0: 主 Agent
  └─ sessions_spawn(task="...", mode="run") → 创建 depth-1 子 Agent
       └─ depth-1 子 Agent 内部：
            orchestrator = SomeOrchestrator(spawn_fn=injected_spawn_fn)
            # spawn_fn 通过构造函数注入，不是通过 exec 环境变量
```

### 1.3 问题模块清单

| # | 文件 | 问题 | 严重度 | 影响 |
|---|------|------|--------|------|
| P1 | `e2e_test_runner.py` | Spawn Bridge（文件中转） | P0 | E2E 测试无法在真实环境跑通 |
| P2 | `compliance_checker.py` | `llm_judge_fn` 回调可能被注入直调 API 的函数 | P1 | 合规检查可能绕过 OpenClaw |
| P3 | `harness_scorer.py` | 同上 | P1 | Harness 评分可能绕过 OpenClaw |
| P4 | `planner.py` | V1 legacy，已废弃但未清理 | P2 | 代码噪音 |
| P5 | `ai_native_auditor.py` | `llm_judge_fn` 同类问题 | P1 | 审计可能绕过 OpenClaw |

### 1.4 正确模块（不动）

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
- e2e_test_runner 提供明确的入口函数 `run_e2e(spawn_fn)`
- 主 Agent 读取任务模板后用 `sessions_spawn` 创建 depth-1 E2E Orchestrator
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

#### 2.2.1 修正后的 LLMJudgeAdapter（V3.0 最终版）

```python
import json
from typing import Optional, Callable, Any

class LLMJudgeAdapter:
    """将 spawn_fn 适配为 llm_judge_fn 接口。
    
    V3.0 关键修正（基于 Round 2 裁决）：
    1. spawn_fn 返回字符串（visible reply），不是 dict
    2. judge() 是同步方法，不是 async（spawn_fn 是同步阻塞）
    3. 不需要 _extract_output 的复杂逻辑，直接处理字符串
    4. 并发控制通过外部 batch_judge 的串行/分批实现，不用 asyncio.Semaphore
    """
    
    def __init__(self, spawn_fn: Callable, max_concurrent: int = 3):
        self.spawn_fn = spawn_fn
        self.max_concurrent = max_concurrent
    
    def judge(
        self,
        prompt: str,
        temperature: float = 0.2,
        max_retries: int = 2,
        output_schema: Optional[dict] = None,
    ) -> dict:
        """执行 LLM 评估（同步阻塞）。
        
        Args:
            prompt: 评估提示词（应包含完整的 Role + Context + Constraints + Output Format）
            temperature: 温度参数（通过 prompt 传递给子 Agent）
            max_retries: 失败重试次数
            output_schema: 期望的 JSON Schema（用于验证输出）
        
        Returns:
            dict: LLM 评估结果
        """
        last_error = None
        for attempt in range(max_retries + 1):
            try:
                # 构造完整的任务描述（包含输出格式要求）
                task = self._build_task(prompt, output_schema, temperature)
                
                # ✅ 正确的 spawn_fn 调用（同步阻塞，返回字符串）
                raw_output = self.spawn_fn(
                    task=task,                    # 第一个位置参数是 task
                    mode="run",
                    label="llm_judge",
                    runTimeoutSeconds=60,         # 正确参数名
                )
                
                # ✅ spawn_fn 返回的是字符串（visible reply）
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
            except Exception as e:
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
    
    def batch_judge(self, prompts: list[dict]) -> list[dict]:
        """批量评估多个维度，减少 spawn 次数。
        
        Args:
            prompts: [{"name": "维度名", "prompt": "评估指令", "schema": {...}}, ...]
        
        Returns:
            list[dict]: 每个维度的评估结果
        """
        results = []
        # 分批处理，每批最多 max_concurrent 个
        for i in range(0, len(prompts), self.max_concurrent):
            batch = prompts[i:i + self.max_concurrent]
            
            # 尝试合并为单次 spawn（如果维度 <= 3）
            if len(batch) <= 3:
                merged_task = self._merge_prompts(batch)
                merged_result = self.judge(merged_task, output_schema={
                    "type": "object",
                    "properties": {p["name"]: p["schema"] for p in batch},
                    "required": [p["name"] for p in batch],
                })
                results.extend([merged_result.get(p["name"], {}) for p in batch])
            else:
                # 串行 spawn（避免并发问题）
                for p in batch:
                    result = self.judge(p["prompt"], output_schema=p["schema"])
                    results.append(result)
        
        return results
    
    def _merge_prompts(self, prompts: list[dict]) -> str:
        """合并多个 prompt 为一个。"""
        parts = ["请同时完成以下多个评估任务："]
        for p in prompts:
            parts.append(f"\n### 评估任务：{p['name']}\n{p['prompt']}")
        return "\n".join(parts)


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

### 2.3 P4: 清理 V1 Legacy 代码

**方案**：
- `planner.py` 移动到 `v1_legacy/` 目录
- 文件顶部添加明确的废弃声明：
  ```python
  """
  ⚠️ DEPRECATED: V1 Legacy 代码，仅供 V1 session 续跑使用。
  新代码请使用 planning_orchestrator.py。
  预计移除时间：2026-Q3
  """
  ```

### 2.4 增强：spawn_fn 契约验证

```python
from pydantic import BaseModel, Field
from typing import Optional, Literal

class SpawnResult(BaseModel):
    """spawn_fn 返回值的标准契约（用于文档化，实际返回 str）。
    
    注意：spawn_fn 实际返回字符串（visible reply）。
    这个模型用于文档化和测试验证。
    """
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

### 2.5 新增：E2E 测试入口（Round 2 裁决）

```python
# e2e_test_runner.py（重写后）

def run_e2e(spawn_fn: Optional[Callable] = None) -> dict:
    """E2E 测试入口函数。
    
    Args:
        spawn_fn: 可选的 spawn_fn 实现。
                  - None: 使用 mock_spawn_fn（测试模式）
                  - 真实 spawn_fn: 生产模式
    
    Returns:
        dict: 测试结果摘要
    """
    if spawn_fn is None:
        from llm_recorder import create_mock_spawn_fn
        spawn_fn = create_mock_spawn_fn()
    
    # 创建 LLMJudgeAdapter
    adapter = LLMJudgeAdapter(spawn_fn)
    
    # 创建各模块（注入 spawn_fn）
    planner = PlanningOrchestrator(spawn_fn=spawn_fn)
    researcher = ResearchOrchestrator(spawn_fn=spawn_fn)
    reviewer = ReviewQCOrchestrator(spawn_fn=spawn_fn, llm_judge_fn=adapter.judge)
    
    # 执行完整流程
    # ... 具体流程取决于业务逻辑
    
    return {"status": "completed", "steps": [...]}
```

### 2.6 新增：mock_spawn_fn 接口统一（Round 2 裁决）

```python
# llm_recorder.py（修订后）

class MockSpawnFn:
    """mock_spawn_fn 实现，遵循 SpawnFn Protocol。
    
    关键约束（Round 2 裁决）：
    1. 签名与真实 spawn_fn 完全一致
    2. 返回字符串（与真实 spawn_fn 一致）
    3. 支持录制/回放模式
    """
    
    def __init__(self, recordings_dir: str = "tests/fixtures/recordings/"):
        self.recordings_dir = recordings_dir
        self.recordings = self._load_recordings()
    
    def __call__(
        self,
        task: str,
        *,
        mode: str = "run",
        label: Optional[str] = None,
        runTimeoutSeconds: Optional[int] = None,
    ) -> str:
        """同步阻塞，返回字符串（与真实 spawn_fn 一致）。"""
        # 基于 task hash 查找录制
        task_hash = hashlib.md5(task.encode()).hexdigest()
        if task_hash in self.recordings:
            return self.recordings[task_hash]
        
        # 未找到录制：返回默认 JSON
        return json.dumps({"status": "mock", "error": "no recording found"})
    
    def _load_recordings(self) -> dict:
        """加载录制数据。"""
        # ... 从 recordings_dir 加载
        pass


def create_mock_spawn_fn(recordings_dir: str = "tests/fixtures/recordings/") -> MockSpawnFn:
    """创建 mock_spawn_fn 实例。"""
    return MockSpawnFn(recordings_dir)
```

### 2.7 新增：CI/CD 测试策略（Round 2 裁决）

```yaml
# .github/workflows/test.yml（示例）

name: Test
on: [push, pull_request]

jobs:
  unit-test:
    name: Unit Tests (mock_spawn_fn)
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run unit tests
        run: |
          pytest tests/ -m "not integration"
        env:
          SOLUTION_PRO_TEST_MODE: mock
  
  integration-test:
    name: Integration Tests (requires OpenClaw)
    runs-on: self-hosted  # 需要 OpenClaw runtime
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v4
      - name: Run integration tests
        run: |
          pytest tests/ -m "integration"
```

**测试分层**：
- **Unit Test**（CI 每次跑）：使用 `mock_spawn_fn`，不需要 OpenClaw runtime
- **Integration Test**（仅 main 分支）：使用真实 `spawn_fn`，需要 OpenClaw runtime

### 2.8 新增：错误处理与可观测性

```python
# 全局配置
SPAWN_CONFIG = {
    "max_retries": 2,          # 最大重试次数
    "retry_delay": 1.0,        # 重试间隔（秒）
    "timeout_seconds": 60,     # 默认超时
    "max_concurrent": 3,       # 最大并发 spawn 数
}

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
| Phase 0 | 检查现有模块的测试覆盖，建立 baseline | 30min | 低 | 运行现有测试 |
| Phase 1 | 定义 `SpawnFn` Protocol + 创建 `LLMJudgeAdapter` 类 | 1h | 低 | 单元测试 |
| Phase 2 | 重构 `compliance_checker.py`、`harness_scorer.py`、`ai_native_auditor.py` | 1.5h | 中 | 单元测试 + 集成测试 |
| Phase 3 | 重写 `e2e_test_runner.py`（Spawn Bridge → 真 sessions_spawn） | 1.5h | 中 | E2E 测试 |
| Phase 4 | 移动 V1 legacy 代码 + 添加废弃声明 | 15min | 低 | 检查 V1 session 不受影响 |
| Phase 5 | 统一 `mock_spawn_fn` 接口 + 录制数据迁移 | 1h | 中 | CI 测试通过 |
| Phase 6 | E2E 验证（真实 OpenClaw 环境） | 1h | 高 | 完整 E2E 测试 |
| Phase 7 | 可观测性集成 + 文档更新 | 30min | 低 | 检查指标输出 |

**总预计**：7-8 小时

---

## 4. 与 V1 的对比

| 维度 | V1 | V2（现状） | V2（重构后） |
|------|-----|-----------|------------|
| LLM 调用方式 | sessions_spawn | 混合（spawn_fn + 直调 + Spawn Bridge） | 统一 spawn_fn → sessions_spawn |
| 额外 API Key | 不需要 | 可能需要 | 不需要 |
| 编排模式 | Orchestrator → Workers | MasterOrchestrator → Module Orchestrators → Workers | 同左（不改） |
| 测试模式 | mock spawn_fn | mock spawn_fn + Spawn Bridge | mock spawn_fn（统一接口） |
| 合规检查 | 规则判定 | llm_judge_fn（来源不确定） | LLMJudgeAdapter → spawn_fn |
| E2E 测试 | 可跑通 | 无法跑通（Spawn Bridge 问题） | 可跑通（真 sessions_spawn） |
| 错误处理 | 无 | 部分 | 统一重试 + 错误分类 |
| 可观测性 | 无 | 无 | SpawnMetrics 指标 |
| spawn_fn 契约 | 隐式 | 隐式 | 显式 Protocol + 文档化 |

---

## 5. 风险与缓解

| 风险 | 缓解 |
|------|------|
| `LLMJudgeAdapter` 引入额外 spawn 开销 | 批量评估（≤3 维度合并为单次 spawn）+ 串行分批 |
| 重写 e2e_test_runner 可能引入新 bug | 保留旧版本为 `e2e_test_runner_v1.py`，渐进替换 |
| `spawn_fn=None` fallback 被破坏 | 每个模块保留 fallback 规则判定，不强依赖 LLM |
| 子 Agent 深度超限 | 严格遵守 depth-0 → depth-1 → depth-2 限制，文档化 |
| spawn 参数名错误 | 使用 SpawnFn Protocol 约束，CI 中检查 |
| 录制数据失效 | 提供迁移脚本，基于 task_key 而非 prompt hash |
| CI 中缺少录制数据 | 测试失败（不是跳过），强制先录制再提交 |

---

## 6. 遗留问题（Round 3 裁决）

| # | 问题 | 裁决 | 理由 |
|---|------|------|------|
| 1 | 是否需要 Layer 2（LLM 语义验证）？ | 后续增强 | 合理但超出本次重构范围，可在 Phase 7 后单独做 |
| 2 | 是否需要 OpenClaw 原生工具（cron/blackboard）集成？ | 暂不集成 | 当前重构聚焦 LLM 路由，工具集成是独立 feature |
| 3 | 是否需要架构决策记录（ADR）对比 Crew AI/AutoGen？ | 文档补充 | 在方案附录中简要说明选择理由 |
| 4 | spawn_fn=None 在生产环境是否应该报错？ | 采纳 | 在 master_orchestrator 初始化时校验 |

---

## 7. 评审记录

### Round 1 评审结果

| 专家 | 评分 | P0 | P1 | P2 |
|------|------|----|----|-----|
| OpenClaw 平台专家 | 5/10 | 3 | 2 | 1 |
| AI Native 架构师 | 5/10 | 2 | 3 | 2 |
| 测试工程专家 | 5/10 | 2 | 4 | 2 |

**主要问题**：
1. spawn_fn 返回值假设错误（dict vs str）
2. judge() 是 async 但 spawn_fn 是同步
3. 并发控制缺失
4. exec 注入链路未说明
5. mock_spawn_fn 接口不一致
6. E2E 测试入口缺失
7. CI/CD 策略不完整

### Round 2 聚焦修复

| 争议 | 裁决 | V3 修订 |
|------|------|---------|
| spawn_fn 返回值 | 返回字符串 | ✅ 简化 _extract_output，直接处理 str |
| sync/async | judge() 必须同步 | ✅ 改为 def judge()，不用 asyncio |
| 注入链路 | 依赖注入，非 exec | ✅ 文档化构造函数注入方式 |
| mock 接口 | 需要 Protocol | ✅ 添加 SpawnFn Protocol |
| E2E 入口 | 需要显式函数 | ✅ 添加 run_e2e(spawn_fn) |
| CI 策略 | 双层测试 | ✅ unit + integration 分离 |

### Round 3 收敛裁决

- 所有 P0 问题已修复
- P1 问题已缓解
- 遗留问题已记录为后续增强
- 方案可执行

---

## 附录 A：架构决策记录（ADR）

### 为什么选择 spawn_fn 而非 Crew AI / AutoGen / LangGraph？

| 维度 | Crew AI | AutoGen | LangGraph | OpenClaw spawn_fn |
|------|---------|---------|-----------|----------------|
| LLM 调用 | 直调 API | 直调 API | 直调 API | 通过平台路由 |
| 额外 API Key | 需要 | 需要 | 需要 | **不需要** |
| 并发模型 | 同步 | 异步对话 | 状态图 | 异步 push-based |
| 上下文隔离 | 弱 | 中 | 强 | **强**（子 Agent 独立） |
| 平台集成 | 无 | 无 | 无 | **原生**（cron/blackboard/message） |

**选择理由**：
1. **零额外 API Key**：利用 OpenClaw 已有的 LLM 路由
2. **强上下文隔离**：每个子 Agent 独立 context，避免污染
3. **原生平台集成**：与 OpenClaw 的 cron/blackboard/message 无缝集成
4. **已验证模式**：V1 已证明 spawn_fn 模式可行

---

## 附录 B：spawn_fn 注入链路图

```
┌─────────────────────────────────────────────────────────────┐
│ depth-0: 主 Agent（OpenClaw 平台）                           │
│   - 拥有 sessions_spawn 工具                                 │
│   - 调用 sessions_spawn(task="...", mode="run")             │
│   - 调用 sessions_yield() 等待完成                          │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ depth-1: 子 Agent（如 E2E Orchestrator）                     │
│   - 接收注入的 spawn_fn（由主 Agent 在 task 描述中传递）      │
│   - 在 Python 代码中：                                       │
│     orchestrator = E2EOrchestrator(spawn_fn=injected_fn)    │
│   - spawn_fn 通过构造函数注入，不是通过 exec 环境变量         │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ depth-2: Worker（如 Planning Worker）                        │
│   - 由 depth-1 通过 spawn_fn 创建                           │
│   - 不可再 spawn（深度限制）                                 │
│   - 执行具体任务，返回 visible reply（字符串）               │
└─────────────────────────────────────────────────────────────┘
```

**关键点**：
- spawn_fn 是 Python callable，通过依赖注入传递
- exec 子进程不直接获取 spawn_fn，而是在子 Agent 内使用
- 如果子 Agent 需要运行 Python 脚本，脚本通过子 Agent 的 spawn_fn 间接调用
