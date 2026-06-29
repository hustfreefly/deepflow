# Solution Pro V2 → V3 具体实施改动方案

> **版本**: V1.0 | **日期**: 2026-06-29
> **架构方案**: refactor_llm_routing_v3.md（已通过评审 8/10）
> **本文档**: 具体到每个文件的改动内容

---

## Phase 0: 建立 Baseline（30min）

### 0.1 运行现有测试
```bash
cd ~/.openclaw/workspace/.deepflow
python -m pytest domains/solution_pro/tests/ -v --tb=short 2>&1 | tee test_baseline.txt
```

### 0.2 记录当前测试状态
- 哪些 PASS / FAIL / SKIP
- 作为后续 Phase 的对比基准

---

## Phase 1: 定义 SpawnFn Protocol + LLMJudgeAdapter（1h）

### 1.1 新建 `spawn_fn_protocol.py`

**路径**: `domains/solution_pro/spawn_fn_protocol.py`
**内容**（~30 行）:

```python
"""SpawnFn Protocol 定义。

统一 mock_spawn_fn 和真实 sessions_spawn 的接口契约。
Round 2 裁决：spawn_fn 返回字符串（visible reply），不是 dict。
"""
from typing import Protocol, Optional, runtime_checkable


@runtime_checkable
class SpawnFn(Protocol):
    """spawn_fn 的精确接口契约。
    
    关键约束：
    1. 同步阻塞调用，返回字符串（子 Agent 的 visible reply）
    2. 不是 async，不是 dict，是 str
    3. 通过依赖注入传递（构造函数/方法参数），不通过 exec 环境变量
    """
    def __call__(
        self,
        task: str,
        *,
        mode: str = "run",
        label: Optional[str] = None,
        runTimeoutSeconds: Optional[int] = None,
    ) -> str:
        """同步阻塞，返回子 Agent 的 visible reply（字符串）。"""
        ...


class SpawnResult:
    """spawn_fn 返回值的文档化模型（实际返回 str）。
    
    用于文档化和测试验证，不是实际返回类型。
    """
    def __init__(self, status: str, output: Optional[str] = None, error: Optional[str] = None):
        self.status = status
        self.output = output
        self.error = error
    
    @property
    def success(self) -> bool:
        return self.status == "COMPLETE"
```

### 1.2 新建 `llm_judge_adapter.py`

**路径**: `domains/solution_pro/llm_judge_adapter.py`
**内容**（~120 行）:

```python
"""LLMJudgeAdapter：将 spawn_fn 适配为 llm_judge_fn 接口。

V3.0 关键修正（基于 PlanMode Pro Round 2 裁决）：
1. spawn_fn 返回字符串（visible reply），不是 dict
2. judge() 是同步方法，不是 async
3. 批量评估通过合并 prompt 减少 spawn 次数
4. 重试机制（max_retries=2）
"""
import json
import logging
from typing import Optional, Callable, Any, List

logger = logging.getLogger(__name__)


class JudgeOutputError(Exception):
    """LLM 评估输出格式错误。"""
    pass


class SpawnError(Exception):
    """spawn_fn 调用失败。"""
    pass


class LLMJudgeAdapter:
    """将 spawn_fn 适配为 llm_judge_fn 接口。
    
    用法：
        adapter = LLMJudgeAdapter(spawn_fn)
        result = adapter.judge("请评估以下输出的质量...")
        # 或作为回调注入：
        checker = ComplianceChecker(llm_judge_fn=adapter.judge)
    """
    
    def __init__(self, spawn_fn: Callable, max_retries: int = 2, batch_size: int = 3):
        self.spawn_fn = spawn_fn
        self.max_retries = max_retries
        self.batch_size = batch_size
    
    def judge(
        self,
        prompt: str,
        temperature: float = 0.2,
        output_schema: Optional[dict] = None,
    ) -> Optional[dict]:
        """执行 LLM 评估（同步阻塞）。
        
        Args:
            prompt: 评估提示词
            temperature: 温度参数（通过 prompt 文本传递）
            output_schema: 期望的 JSON Schema（用于验证输出）
        
        Returns:
            dict: LLM 评估结果；None 表示失败（触发 fallback）
        """
        task = self._build_task(prompt, output_schema, temperature)
        
        for attempt in range(self.max_retries + 1):
            try:
                # spawn_fn 同步阻塞调用，返回字符串
                raw_output = self.spawn_fn(
                    task=task,
                    mode="run",
                    label="llm_judge",
                )
                
                # raw_output 是字符串（visible reply）
                if not isinstance(raw_output, str):
                    raw_output = str(raw_output)
                
                parsed = self._parse_json(raw_output)
                
                # 可选 Schema 验证
                if output_schema:
                    self._validate_schema(parsed, output_schema)
                
                return parsed
                
            except (json.JSONDecodeError, KeyError, ValueError) as e:
                logger.warning(f"LLM judge attempt {attempt+1} failed: {e}")
                if attempt >= self.max_retries:
                    logger.error(f"LLM judge exhausted retries: {e}")
                    return None  # 触发 fallback
            except Exception as e:
                logger.warning(f"LLM judge spawn error attempt {attempt+1}: {e}")
                if attempt >= self.max_retries:
                    logger.error(f"LLM judge spawn exhausted: {e}")
                    return None  # 触发 fallback
        
        return None
    
    def batch_judge(self, prompts: List[dict]) -> List[Optional[dict]]:
        """批量评估，减少 spawn 次数。
        
        Args:
            prompts: [{"name": "维度名", "prompt": "评估指令", "schema": {...}}, ...]
        
        Returns:
            list[Optional[dict]]: 每个维度的评估结果
        """
        results = []
        for i in range(0, len(prompts), self.batch_size):
            batch = prompts[i:i + self.batch_size]
            
            if len(batch) <= self.batch_size:
                # 合并为单次 spawn
                merged_task = self._merge_prompts(batch)
                merged_result = self.judge(merged_task)
                
                if merged_result:
                    for p in batch:
                        results.append(merged_result.get(p["name"], None))
                else:
                    results.extend([None] * len(batch))
            else:
                for p in batch:
                    results.append(self.judge(p["prompt"], output_schema=p.get("schema")))
        
        return results
    
    def _build_task(self, prompt: str, output_schema: Optional[dict], temperature: float) -> str:
        """构造子 Agent 任务描述。"""
        parts = [
            "你是一个 LLM-as-Judge 评估器。请严格按照以下指令执行评估。",
            "",
            f"## 评估指令\n{prompt}",
            "",
            "## 输出要求",
            "你必须输出严格的 JSON，不要包含任何其他文本、代码块标记或解释。",
        ]
        if output_schema:
            parts.append(f"\n期望的 JSON 格式: {json.dumps(output_schema, ensure_ascii=False)}")
        if temperature != 0.2:
            parts.append(f"\nTemperature: {temperature}")
        return "\n".join(parts)
    
    def _parse_json(self, raw: str) -> dict:
        """从 LLM 输出中解析 JSON。"""
        cleaned = raw.strip()
        
        # 去除 markdown 代码块
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            cleaned = "\n".join(lines).strip()
        
        return json.loads(cleaned)
    
    def _validate_schema(self, data: dict, schema: dict) -> None:
        """简单的 Schema 验证（检查必需字段）。"""
        required = schema.get("required", [])
        for field in required:
            if field not in data:
                raise JudgeOutputError(f"缺少必需字段: {field}")
    
    def _merge_prompts(self, prompts: List[dict]) -> str:
        """合并多个评估 prompt 为一个。"""
        parts = ["请同时完成以下多个评估任务，输出一个包含所有结果的 JSON 对象："]
        for p in prompts:
            parts.append(f"\n### 评估维度: {p['name']}\n{p['prompt']}")
        return "\n".join(parts)
```

### 1.3 新建 `spawn_metrics.py`

**路径**: `domains/solution_pro/spawn_metrics.py`
**内容**（~60 行）:

```python
"""SpawnMetrics：spawn_fn 调用的可观测性指标。"""
import time
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class SpawnMetrics:
    """追踪 spawn_fn 调用的成功率、延迟、错误分布。"""
    
    def __init__(self):
        self.total_calls = 0
        self.success_count = 0
        self.failure_count = 0
        self.timeout_count = 0
        self.fallback_count = 0
        self.total_latency_ms = 0.0
        self._start_time: Optional[float] = None
    
    def start_call(self):
        """标记一次 spawn 调用开始。"""
        self._start_time = time.time()
    
    def record_success(self):
        """记录成功调用。"""
        self.total_calls += 1
        self.success_count += 1
        if self._start_time:
            self.total_latency_ms += (time.time() - self._start_time) * 1000
        self._start_time = None
    
    def record_failure(self, error_type: str = "unknown"):
        """记录失败调用。"""
        self.total_calls += 1
        self.failure_count += 1
        if self._start_time:
            self.total_latency_ms += (time.time() - self._start_time) * 1000
        self._start_time = None
        logger.warning(f"spawn_fn failure: {error_type}")
    
    def record_timeout(self):
        """记录超时调用。"""
        self.total_calls += 1
        self.timeout_count += 1
        self._start_time = None
    
    def record_fallback(self):
        """记录 fallback（LLM judge 返回 None，退化到规则判定）。"""
        self.fallback_count += 1
    
    @property
    def avg_latency_ms(self) -> float:
        if self.total_calls == 0:
            return 0.0
        return self.total_latency_ms / self.total_calls
    
    @property
    def success_rate(self) -> float:
        if self.total_calls == 0:
            return 0.0
        return self.success_count / self.total_calls
    
    def summary(self) -> dict:
        return {
            "total_calls": self.total_calls,
            "success": self.success_count,
            "failure": self.failure_count,
            "timeout": self.timeout_count,
            "fallback": self.fallback_count,
            "success_rate": round(self.success_rate, 3),
            "avg_latency_ms": round(self.avg_latency_ms, 1),
        }


# 全局单例
spawn_metrics = SpawnMetrics()
```

### 1.4 修改文件清单

| 文件 | 操作 | 行数 |
|------|------|------|
| `spawn_fn_protocol.py` | 新建 | ~45 行 |
| `llm_judge_adapter.py` | 新建 | ~140 行 |
| `spawn_metrics.py` | 新建 | ~70 行 |

---

## Phase 2: 重构 3 个 Judge 模块（1.5h）

### 2.1 修改 `compliance_checker.py`

**改动位置**：`__init__` 方法 + 注入方式
**当前代码**（第 94-101 行）:
```python
def __init__(self, llm_judge_fn: Optional[Callable] = None):
    self.llm_judge_fn = llm_judge_fn
```

**改为**:
```python
def __init__(self, llm_judge_fn: Optional[Callable] = None, spawn_fn: Optional[Callable] = None):
    # V3: 优先使用 spawn_fn → LLMJudgeAdapter
    if spawn_fn is not None and llm_judge_fn is None:
        from domains.solution_pro.llm_judge_adapter import LLMJudgeAdapter
        adapter = LLMJudgeAdapter(spawn_fn)
        self.llm_judge_fn = adapter.judge
    else:
        self.llm_judge_fn = llm_judge_fn
```

**改动量**：~8 行新增，原代码不动

**同理**，`quick_compliance_check` 函数签名也加 `spawn_fn` 参数：
```python
def quick_compliance_check(output: dict, llm_judge_fn=None, spawn_fn=None) -> dict:
    checker = ComplianceChecker(llm_judge_fn=llm_judge_fn, spawn_fn=spawn_fn)
    return checker.check(output)
```

### 2.2 修改 `harness_scorer.py`

**改动位置**：`__init__` 方法
**当前代码**（第 455-462 行）:
```python
def __init__(self, llm_judge_fn=None):
    self.llm_judge_fn = llm_judge_fn
```

**改为**:
```python
def __init__(self, llm_judge_fn=None, spawn_fn=None):
    if spawn_fn is not None and llm_judge_fn is None:
        from domains.solution_pro.llm_judge_adapter import LLMJudgeAdapter
        adapter = LLMJudgeAdapter(spawn_fn)
        self.llm_judge_fn = adapter.judge
    else:
        self.llm_judge_fn = llm_judge_fn
```

**改动量**：~6 行

### 2.3 修改 `ai_native_auditor.py`

**改动位置**：`__init__` 方法
**当前代码**（第 62-63 行）:
```python
def __init__(self, llm_judge_fn=None):
    self.llm_judge_fn = llm_judge_fn
```

**改为**（同上模式）:
```python
def __init__(self, llm_judge_fn=None, spawn_fn=None):
    if spawn_fn is not None and llm_judge_fn is None:
        from domains.solution_pro.llm_judge_adapter import LLMJudgeAdapter
        adapter = LLMJudgeAdapter(spawn_fn)
        self.llm_judge_fn = adapter.judge
    else:
        self.llm_judge_fn = llm_judge_fn
```

**改动量**：~6 行

### 2.4 Phase 2 改动总结

| 文件 | 改动行数 | 方式 |
|------|---------|------|
| `compliance_checker.py` | ~14 行 | `__init__` 加 spawn_fn 参数 |
| `harness_scorer.py` | ~6 行 | 同上 |
| `ai_native_auditor.py` | ~6 行 | 同上 |
| **合计** | **~26 行** | |

**向后兼容**：原有 `llm_judge_fn` 参数保留，新代码可以用 `spawn_fn` 代替。旧调用方不受影响。

---

## Phase 3: 重写 e2e_test_runner.py（1.5h）

### 3.1 备份旧版本
```bash
cp e2e_test_runner.py e2e_test_runner_v2_legacy.py
```

### 3.2 新版 `e2e_test_runner.py`

**完全重写**（~120 行），删除所有 Spawn Bridge 代码：

```python
#!/usr/bin/env python3
"""
Solution Pro V2 E2E Test Runner（V3 重构版）

改动：
- 删除 Spawn Bridge（文件中转）
- 改为显式入口 run_e2e(spawn_fn)
- 支持 mock 和真实 spawn_fn
"""
import os
import sys
import json
from pathlib import Path
from typing import Optional, Callable

DEEPFLOW = os.path.expanduser("~/.openclaw/workspace/.deepflow")
os.chdir(DEEPFLOW)
sys.path.insert(0, ".")

from domains.solution_pro.blackboard import BlackboardManager
from domains.solution_pro.master_orchestrator import MasterOrchestrator


# === 测试配置 ===
DEFAULT_TOPIC = "OpenClaw_AI_Native_Loop_Engineering_Framework"
DEFAULT_USER_INPUT = """构建 OpenClaw AI Native Loop Engineering Framework。
核心需求：全LLM控制的自主循环执行框架，支持8+小时无人干预运行。
"""


def run_e2e(
    spawn_fn: Optional[Callable] = None,
    topic: str = DEFAULT_TOPIC,
    user_input: str = DEFAULT_USER_INPUT,
    mode: str = "standard",
) -> dict:
    """E2E 测试入口。
    
    Args:
        spawn_fn: 
            - None: 使用 mock_spawn_fn（测试模式）
            - Callable: 使用真实 spawn_fn（生产模式）
        topic: 测试主题
        user_input: 用户输入
        mode: standard | full
    
    Returns:
        dict: 测试结果
    """
    # Step 1: 如果没有 spawn_fn，创建 mock
    if spawn_fn is None:
        spawn_fn = _create_mock_spawn_fn()
        print("[E2E] 使用 mock_spawn_fn（测试模式）")
    else:
        print("[E2E] 使用真实 spawn_fn（生产模式）")
    
    # Step 2: 初始化 Blackboard
    bm = BlackboardManager(topic, base_dir=Path(DEEPFLOW) / "domains/solution_pro/blackboard_sessions")
    bm.init_session()
    print(f"[E2E] Session ID: {bm.session_id}")
    
    # Step 3: 写入 frozen_spec
    frozen_spec = _load_or_create_frozen_spec(topic)
    bm.write("data/frozen_spec.json", frozen_spec)
    print(f"[E2E] Frozen spec: {len(frozen_spec.get('requirements', []))} requirements")
    
    # Step 4: 创建 MasterOrchestrator
    config = {
        "topic": topic,
        "solution_type": "architecture",
        "mode": mode,
    }
    
    master = MasterOrchestrator(
        blackboard=bm,
        spawn_fn=spawn_fn,
        config=config,
    )
    
    # Step 5: 执行 Pipeline
    print(f"[E2E] Starting V2 Pipeline: Planning → Research → ReviewQC")
    try:
        result = master.run(user_input=user_input, config=config)
        print(f"[E2E] Pipeline completed: {result.get('status', 'UNKNOWN')}")
        return {
            "status": "PASS",
            "pipeline_result": result,
            "session_id": bm.session_id,
        }
    except Exception as e:
        print(f"[E2E] Pipeline failed: {e}")
        return {
            "status": "FAIL",
            "error": str(e),
            "session_id": bm.session_id,
        }


def _create_mock_spawn_fn():
    """创建 mock spawn_fn。"""
    try:
        from domains.solution_pro.llm_recorder import LLMRecorder
        recorder = LLMRecorder()
        return recorder.create_mock_spawn_fn()
    except Exception:
        # 最简 mock：返回空 JSON
        def mock_spawn(task=None, **kwargs):
            return json.dumps({"status": "mock", "output": {}})
        return mock_spawn


def _load_or_create_frozen_spec(topic: str) -> dict:
    """加载或创建最小 frozen_spec。"""
    # 尝试从已有 session 加载
    spec_dir = Path(DEEPFLOW) / "blackboard"
    for session_dir in spec_dir.iterdir():
        spec_file = session_dir / "data" / "frozen_spec.json"
        if spec_file.exists():
            with open(spec_file) as f:
                return json.load(f)
    
    # 创建最小 frozen_spec
    return {
        "topic": topic,
        "solution_type": "architecture",
        "mode": "standard",
        "requirements": [
            {"req_id": "REQ-P0-001", "description": "全LLM控制", "priority": "P0"},
            {"req_id": "REQ-P0-002", "description": "8+小时运行", "priority": "P0"},
        ],
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Solution Pro V2 E2E Test")
    parser.add_argument("--topic", default=DEFAULT_TOPIC)
    parser.add_argument("--mode", default="standard", choices=["standard", "full"])
    parser.add_argument("--mock", action="store_true", help="使用 mock spawn_fn")
    args = parser.parse_args()
    
    spawn_fn = None if args.mock else None  # 生产模式需要主 Agent 注入
    result = run_e2e(spawn_fn=spawn_fn, topic=args.topic, mode=args.mode)
    print(json.dumps(result, indent=2, ensure_ascii=False))
```

### 3.3 Phase 3 改动总结

| 操作 | 文件 | 行数 |
|------|------|------|
| 备份 | `e2e_test_runner_v2_legacy.py` | 179 行 |
| 重写 | `e2e_test_runner.py` | ~120 行 |
| **净改动** | | **~120 行** |

**关键变化**：
- 删除 Spawn Bridge（`SPAWN_REQUEST_DIR`, `SPAWN_OUTPUT_DIR`, 文件中转逻辑）
- 新增 `run_e2e(spawn_fn)` 显式入口
- 支持 mock 和真实 spawn_fn 切换

---

## Phase 4: 移动 V1 Legacy 代码（15min）

```bash
mkdir -p domains/solution_pro/v1_legacy
mv domains/solution_pro/planner.py domains/solution_pro/v1_legacy/planner.py
# 在文件顶部添加废弃声明
```

---

## Phase 5: 统一 MockSpawnFn + prod 校验（1h）

### 5.1 修改 `llm_recorder.py`

**改动**：MockSpawnFn 签名对齐 SpawnFn Protocol

**当前代码**（约第 109-152 行）:
```python
def create_mock_spawn_fn(self, fallback_fn=None):
    def mock_spawn_fn(task=None, output_path=None, **kwargs) -> dict:
        # ... 返回 dict
```

**改为**:
```python
def create_mock_spawn_fn(self, fallback_fn=None):
    def mock_spawn_fn(task: str = "", *, mode: str = "run", label=None, runTimeoutSeconds=None, **kwargs) -> str:
        """MockSpawnFn：签名对齐 SpawnFn Protocol，返回字符串。"""
        task_hash = hashlib.md5(task.encode() if task else b"").hexdigest()[:8]
        recording = self._find_recording(task_hash)
        if recording:
            return json.dumps(recording, ensure_ascii=False)
        if fallback_fn:
            return str(fallback_fn(task=task, **kwargs))
        return json.dumps({"status": "mock", "task_hash": task_hash})
    return mock_spawn_fn
```

**改动量**：~20 行

### 5.2 修改 `master_orchestrator.py`

**改动**：`__init__` 中加 prod 校验

**在第 49-51 行后添加**:
```python
# V3: prod 环境强制要求 spawn_fn
if spawn_fn is None and os.environ.get("DEEPFLOW_ENV") == "prod":
    raise ValueError(
        "spawn_fn is required in production mode. "
        "Set DEEPFLOW_ENV=test for mock mode."
    )
```

**改动量**：~5 行

### 5.3 Phase 5 改动总结

| 文件 | 改动行数 | 说明 |
|------|---------|------|
| `llm_recorder.py` | ~20 行 | MockSpawnFn 返回 str，签名对齐 |
| `master_orchestrator.py` | ~5 行 | prod 校验 |
| **合计** | **~25 行** | |

---

## Phase 6: E2E 验证（1h）

### 6.1 运行测试对比 baseline
```bash
python -m pytest domains/solution_pro/tests/ -v --tb=short 2>&1 | tee test_after_refactor.txt
diff test_baseline.txt test_after_refactor.txt
```

### 6.2 运行 E2E 测试（mock 模式）
```bash
python domains/solution_pro/e2e_test_runner.py --mock
```

### 6.3 验证清单
- [ ] 所有原有测试仍 PASS（不引入回归）
- [ ] mock E2E 测试能跑通
- [ ] `compliance_checker` 注入 spawn_fn 后正常工作
- [ ] `harness_scorer` 注入 spawn_fn 后正常工作
- [ ] `ai_native_auditor` 注入 spawn_fn 后正常工作
- [ ] `master_orchestrator` prod 校验生效
- [ ] `mock_spawn_fn` 返回字符串（非 dict）

---

## Phase 7: 文档更新（30min）

### 7.1 更新 SKILL.md 中的接口说明
### 7.2 更新 DEVELOPMENT_RULES.md（如有）
### 7.3 记录 ADR（Architecture Decision Record）

---

## 总改动量汇总

| Phase | 文件数 | 新增行 | 修改行 | 删除行 |
|-------|--------|--------|--------|--------|
| Phase 1 | 3 新建 | ~255 行 | 0 | 0 |
| Phase 2 | 3 修改 | 0 | ~26 行 | 0 |
| Phase 3 | 1 重写 | ~120 行 | 0 | ~179 行（旧版） |
| Phase 4 | 1 移动 | 0 | 0 | 0 |
| Phase 5 | 2 修改 | 0 | ~25 行 | 0 |
| Phase 6 | 0 | 0 | 0 | 0 |
| Phase 7 | 文档 | ~50 行 | 0 | 0 |
| **合计** | **10 文件** | **~425 行** | **~51 行** | **~179 行** |

**净代码改动**：新增 ~425 行 + 修改 ~51 行 - 删除 ~179 行 = **净增 ~297 行**

---

## 风险检查点

| 风险 | 检查方式 | 回滚方案 |
|------|---------|---------|
| LLMJudgeAdapter 的 spawn_fn 调用方式与实际不匹配 | Phase 6 测试 | 保留原 llm_judge_fn 参数 |
| e2e_test_runner 重写后 MasterOrchestrator.run() 接口变化 | 检查 run() 签名 | 回退到 v2_legacy 版本 |
| mock_spawn_fn 返回 str 导致下游解析失败 | grep 检查所有 mock 使用处 | 添加兼容层 |
| prod 校验误拦测试环境 | 检查 DEEPFLOW_ENV 变量 | 去掉校验，改为 warning |
