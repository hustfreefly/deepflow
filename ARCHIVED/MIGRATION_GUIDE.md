# DeepFlow V1.0 → V2.0 迁移指南

## 新旧版本对比

| 特性 | V1.0 | V2.0 |
|------|------|------|
| **配置方式** | 硬编码 Python | YAML 契约驱动 |
| **阶段执行** | 顺序串行 | 支持多轮迭代 |
| **并行能力** | 无 | Researcher/Auditor 并行 |
| **数据传递** | 函数返回值 | Blackboard 持久化 |
| **收敛检测** | 无 | 自动收敛 + 分数计算 |
| **错误处理** | 简单 try-catch | 契约验证 + fallback |
| **扩展性** | 需修改代码 | 添加 YAML 即可 |
| **可观测性** | 日志 | Blackboard + 检查点 |

## 架构变化

### V1.0 架构
```
OrchestratorAgent
  ├── run() - 顺序执行所有阶段
  ├── execute_stage() - 硬编码阶段逻辑
  └── 直接返回结果
```

### V2.0 架构
```
CageOrchestrator
  ├── CageLoader - 从 YAML 加载契约
  ├── CageValidator - 验证输入输出
  ├── BlackboardManager - 数据持久化
  ├── Handlers - 各阶段处理器
  │   ├── data_collection_handler.py
  │   ├── research_handler.py (6个并行)
  │   ├── audit_handler.py (3个并行)
  │   └── ...
  └── 收敛检测 + 多轮迭代
```

## 迁移步骤

### Step 1: 更新导入
```python
# V1.0
from .deepflow.domains.investment.orchestrator import OrchestratorAgent

# V2.0
from .deepflow.domains.investment.cage_orchestrator import CageOrchestrator
```

### Step 2: 更新初始化
```python
# V1.0
orchestrator = OrchestratorAgent(domain="investment")

# V2.0
orchestrator = CageOrchestrator(domain="investment")
```

### Step 3: 运行方式不变
```python
# 两者调用方式相同
result = orchestrator.run({"code": "300604.SZ", "name": "长川科技"})
```

### Step 4: 处理新增字段
V2.0 的输出包含更多字段：
```python
{
    "status": "completed",
    "pipeline_state": "CONVERGED",  # 新增
    "session_id": "investment_300604_sz_xxx",  # 新增
    "final_score": 0.93,  # 新增
    "convergence_reason": "...",  # 新增
    "iterations": 3,  # 新增
    "stage_outputs": {...}
}
```

## 回滚方法

如果 V2.0 出现问题，可以快速回滚到 V1.0：

```python
import sys

# 临时使用 V1.0
sys.path.insert(0, '/path/to/.deepflow/ARCHIVED/v1.0_legacy')
from orchestrator_agent import OrchestratorAgent

orchestrator = OrchestratorAgent(domain="investment")
result = orchestrator.run({"code": "300604.SZ", "name": "长川科技"})
```

## 常见问题

### Q1: V2.0 比 V1.0 慢吗？
A: 初始迭代可能略慢（因为要写入 Blackboard），但多轮迭代的总体质量更高。Researcher/Auditor 的并行执行可以弥补性能损失。

### Q2: 如何禁用多轮迭代？
A: 在 `cage/convergence_rules.yaml` 中设置 `min_iterations: 1` 和 `max_iterations: 1`。

### Q3: Blackboard 数据在哪里？
A: 默认在 `~/.openclaw/workspace/.deepflow/blackboard/{session_id}/` 目录。

### Q4: 如何查看某次运行的详细日志？
A: 检查 Blackboard 目录下的 `stages/*/output.json` 文件，每个阶段的输出都持久化了。

## 性能对比

| 指标 | V1.0 | V2.0 |
|------|------|------|
| 单次执行时间 | ~30s | ~45s |
| 分析质量 | 中等 | 高（多轮迭代） |
| 可扩展性 | 低 | 高 |
| 调试难度 | 中 | 低（Blackboard 可追溯） |

---

*最后更新: 2026-04-20*
