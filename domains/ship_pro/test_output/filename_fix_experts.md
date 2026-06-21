# 多专家讨论：DeepFlow Ship Pro 管线输出文件命名一致性

> 讨论时间：2026-06-20
> 问题：LLM Worker 有时用连字符写文件名（`architect-output.json`），而非下划线（`architect_output.json`）
> 候选方向：A（注册表+归一化层）、B（约定式+后处理脚本）、C（Schema驱动）、D（注册表+Orchestrator代码层修复）

---

## 专家 1：分布式系统架构师

### 推荐方向：A（注册表 + 归一化层）

**理由**：

方向 A 最符合"单一事实源"（Single Source of Truth）原则。当前问题的根因是文件名定义散落在 6+ 处（`run_pipeline.py` 4处、`packager.md` 1处、`ship_orchestrator.md` 2处、各 Worker prompt），任何一处不一致都会导致故障。注册表将所有文件名收敛到一个字典，改动量从"改 8 处"降为"改 1 处"。

可扩展性方面，未来新增 Worker（如 `implementer`、`tester`）只需在 `SHIP_STAGE_REGISTRY` 中加一行，Orchestrator、Gate、Packager 自动适配。方向 B 的后处理脚本需要维护正则规则；方向 C 的 schema 需要 LLM 额外读取一个文件（增加 I/O 失败点）；方向 D 只做读取端修复，不解决写入端混乱。

**关键风险**：

1. 归一化 `rename()` 操作在极端情况下可能失败（文件被占用、权限问题），需要 try-except 保护
2. 注册表引入新模块（`blackboard.py`），需要确保 import 路径正确
3. 如果 LLM 写出完全偏离约定的文件名（如 `arch_out.json`），归一化层无法覆盖——但这属于极端 case，可通过 Gate 兜底

---

## 专家 2：LLM 行为专家

### 推荐方向：D（注册表 + Orchestrator 代码层修复）

**理由**：

从 LLM 行为约束角度，最优方案是**减少对 LLM 遵守命名规则的依赖**。方向 D 的核心思想是：不试图控制 LLM 写什么文件名，而是在 Orchestrator 读取端做 fallback 查找。这比方向 A 的"归一化 rename"更安全——rename 改变了文件系统状态，可能影响正在运行的 Worker 后续操作（如 Worker 想追加写入或读取自己的输出）。

方向 D 不修改 Worker prompt 的核心逻辑，不增加 Worker 的 I/O 负担（不像方向 C 需要读 schema），也不引入后处理脚本的执行时序问题（方向 B 的脚本何时运行？Worker 完成后立即？还是所有 stage 完成后？）。

对 LLM 行为的约束最少：Worker prompt 中可以完全删除"文件名必须用下划线"的警告（减少 prompt 噪音），让 LLM 专注于内容质量而非格式合规。

**关键风险**：

1. Fallback 查找需要定义清晰的搜索策略（精确匹配 → 连字符变体 → 模糊匹配），过度模糊会引入误匹配
2. 如果 Orchestrator 和 `run_pipeline.py` 都需要做 fallback，逻辑可能重复
3. 调试时文件名不一致的问题被"静默修复"，可能导致 LLM 持续产出错误命名而不被发现（需要日志记录）

---

## 专家 3：Python 工程专家

### 推荐方向：A（注册表 + 归一化层），但实现上融合 D 的 fallback 思路

**理由**：

从实现复杂度和兼容性角度，方向 A 的改动最可控：

1. **新增文件** `domains/ship_pro/blackboard.py`（~40 行），定义 `SHIP_STAGE_REGISTRY` 和 `resolve_output_path()`
2. **修改 `run_pipeline.py`**：4 处 `f"{agent_name}_output.json"` 改为调用 `resolve_output_path()`，改动量约 10 行
3. **修改 prompt 文件**：`packager.md` 和 `ship_orchestrator.md` 中的硬编码文件名改为引用注册表值（由 `prepare_pipeline` 注入）

与现有代码的兼容性：`resolve_output_path()` 是纯函数，不改变任何现有函数签名，只替换文件名构造逻辑。`_get_upstream_outputs`、`check_gate`、`validate_pipeline` 等函数只需将 `f"{dep}_output.json"` 替换为 `resolve_output_path(bb_dir, dep).name`。

方向 B 的后处理脚本引入额外的进程管理问题（何时调用？失败如何处理？）。方向 C 的 schema 驱动需要 LLM 额外读取文件，增加 I/O 失败点和延迟。方向 D 只做读取端修复，不解决"文件名在 prompt 中散落"的根本问题。

**关键风险**：

1. `resolve_output_path()` 中的 `rename()` 操作需要确保原子性（Python 的 `Path.rename()` 在 POSIX 上是原子的，但在 Windows 上不是——不过当前运行环境是 macOS，无此问题）
2. 注册表与 `AGENT_DEPENDENCIES` 字典存在信息重复（都包含 worker 名称），需要确保两者同步——可以通过从注册表生成依赖列表来消除重复
3. prompt 文件中的文件名注入需要在 `prepare_pipeline` 中增加 `.replace()` 调用，与之前的路径注入修复（`{base_path}`、`{prompts_dir}`）属于同一模式，不会增加复杂度

**实现建议**：融合方向 D 的 fallback 思路——`resolve_output_path()` 先查标准名，再查连字符变体并 rename，最后返回标准路径。这样既解决了"单一事实源"问题，又兼容了 LLM 的命名偏差。

---

## 综合推荐

### 最终方案：方向 A（注册表 + 归一化层）+ 方向 D 的 fallback 读取

**核心设计**：

```python
# domains/ship_pro/blackboard.py

SHIP_STAGE_REGISTRY = {
    "architect": "architect_output.json",
    "decomposer": "decomposer_output.json",
    "specifier": "specifier_output.json",
    "reviewer": "reviewer_output.json",
    "packager": "packager_output.json",
}

def resolve_output_path(blackboard_dir: Path, stage_name: str) -> Path:
    """
    查找 Worker 输出文件，自动处理命名变体。
    优先级：标准名 > 连字符变体 > 返回标准路径（让调用方处理不存在的情况）
    """
    canonical_name = SHIP_STAGE_REGISTRY[stage_name]
    canonical = blackboard_dir / canonical_name
    
    if canonical.exists():
        return canonical
    
    # 尝试连字符变体（architect-output.json）
    alt_name = canonical_name.replace('_', '-')
    alt = blackboard_dir / alt_name
    if alt.exists():
        try:
            alt.rename(canonical)  # 归一化
            return canonical
        except OSError:
            return alt  # rename 失败，返回变体路径
    
    return canonical  # 不存在，让调用方处理
```

**改动清单**：

| 文件 | 改动 | 行数 |
|------|------|------|
| `domains/ship_pro/blackboard.py` | 新建，定义注册表 + resolve 函数 | ~40 行 |
| `scripts/run_pipeline.py` L153 | `f"{dep}_output.json"` → `resolve_output_path(bb_dir, dep).name` | 1 行 |
| `scripts/run_pipeline.py` L373 | `f"{agent_name}_output.json"` → `resolve_output_path(bb_dir, agent_name).name` | 1 行 |
| `scripts/run_pipeline.py` L423 | 同上 | 1 行 |
| `scripts/run_pipeline.py` L558 | 同上 | 1 行 |
| `scripts/run_pipeline.py` L616 | `bb_dir / "architect_output.json"` → `resolve_output_path(bb_dir, "architect")` | 1 行 |
| `prompts/packager.md` L29-32 | 硬编码文件名 → `{architect_output_file}` 等占位符 | 4 行 |
| `prompts/ship_orchestrator.md` L39-43 | 文件名表 → 从注册表注入 | ~5 行 |
| `prompts/ship_orchestrator.md` L118-122 | 文件名规则 → 删除（由代码层保证） | -5 行 |

**总改动量**：~60 行新增/修改，0 行删除核心逻辑。

**关键设计决策**：

1. **归一化在读取端做**，不在写入端做——不试图控制 LLM 写什么，只在读取时自动修正
2. **rename 是 best-effort**，失败不阻塞——返回变体路径，让调用方继续
3. **prompt 中的文件名警告可以保留但降级**——从"必须严格遵守"改为"建议命名格式"，减少 prompt 噪音
4. **日志记录归一化事件**——每次 rename 成功都记录到 `.stage_progress.json` 的 `normalizations` 字段，便于诊断 LLM 命名偏差频率

**验证标准**：

- 连字符命名导致的 ENOENT 错误率降至 0（归一化层自动修正）
- 新增 Worker 只需在 `SHIP_STAGE_REGISTRY` 加一行 + 在 `AGENT_DEPENDENCIES` 加依赖关系
- `run_pipeline.py` 中不再有任何 `f"{xxx}_output.json"` 硬编码

---

*文档生成：多专家讨论 | 2026-06-20*
