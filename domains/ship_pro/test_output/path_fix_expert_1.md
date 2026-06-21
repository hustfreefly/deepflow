# DeepFlow 管线路径传递问题评估报告

## 推荐方案：方案 B（绝对路径注入法）

**理由**：方案 B 直接修复根因（Orchestrator 缺少路径信息导致猜测），实现最简单、prompt 体积零膨胀，且不改变现有架构。方案 A 虽更彻底但引入 50KB prompt 膨胀，方案 C 存在"上游路径在 prepare 时不确定"的架构硬伤，不可行。

---

## 三方案一句话总结

| 方案 | 优点 | 缺点 |
|------|------|------|
| A 预加载嵌入 | 彻底消除文件读取，可靠性最高 | Orchestrator prompt 膨胀 ~50KB，注意力稀释风险 |
| B 绝对路径注入 | 改动最小、prompt 无膨胀、修复根因 | Orchestrator 仍需一次 read 调用（但路径正确） |
| C 预生成 Task | 完全解耦 Orchestrator 与文件系统 | 上游路径在 prepare 时不可知，架构不兼容 |

---

## 方案 B 实施要点

### 改动文件

1. **`run_pipeline.py`** — `prepare_pipeline` 函数中注入 `prompts_dir`
2. **`prompts/orchestrator.md`** — Worker prompt 读取指令改用 `{prompts_dir}` 占位符

### 关键代码片段

**run_pipeline.py**:
```python
from pathlib import Path

def prepare_pipeline(...):
    # 现有 base_path 逻辑不变
    base_path = str(bb_dir.resolve())
    
    # 新增：注入 prompts 绝对路径
    prompts_dir = str((Path(__file__).parent / "prompts").resolve())
    
    orchestrator_prompt = orchestrator_prompt.replace("{base_path}", base_path)
    orchestrator_prompt = orchestrator_prompt.replace("{prompts_dir}", prompts_dir)
```

**prompts/orchestrator.md** (Worker spawn 指令段):
```markdown
## Worker Prompt 读取

每个 Worker 的 prompt 文件位于 `{prompts_dir}/{worker_name}.md`。
构建 Worker task 时，先用 read 工具读取该文件内容，再嵌入 task prompt。
路径已由管线预注入，禁止猜测或拼接相对路径。
```

### 验证标准

- ENOENT 错误率从 73% 降至 < 5%
- Orchestrator 日志中 read 调用路径全部为绝对路径
- 新增 Worker 时无需改动 `run_pipeline.py`（路径自动解析）
