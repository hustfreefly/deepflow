# ADR-009: MD-First Architecture

## Status

**Accepted**

## Date

2026-07-12

## Context

DeepFlow 管线内部使用 JSON 作为结构化数据传递格式（性能优先、Schema 验证友好）。然而，最终交付物（cross-domain handoff、用户可见输出）需要人类可读的 Markdown 格式。

在 V3.0.0 之前，存在以下问题：

1. **信息丢失**：JSON → LLM 组装过程中，84% 的内容被丢失（Deliver Pro 实测）
2. **跨域信息不守恒**：下游域（Ship Pro、Deliver Pro）从 JSON 读取，但 JSON 字段映射不完整，导致关键上下文丢失
3. **降级机制滥用**：MD 不可用时静默 fallback 到 JSON，掩盖了上游渲染失败的根本原因
4. **交付物不可读**：最终输出是 JSON 而非人类可读格式，用户无法直接查看

核心矛盾：**管线内部需要 JSON（性能 + Schema），但交付物需要 MD（可读 + 信息守恒）**。

## Decision

### 核心原则

**MD 做 source of truth，JSON 做 ~1KB 衍生品。**

- MD 是跨域信息传递的唯一可信来源
- JSON 仅用于管线内部结构化数据传递（保持性能）
- 最终交付物必须是 MD 格式

### 输入端契约（P0）

**必须从 `living_spec.md` 读取，MD 不可用 → raise ValueError。**

```python
# ADR-009 P1: MD 唯一（不可信的约束不是约束）
md_path_str = raw_package.get("living_spec_md_path")
if not md_path_str:
    raise ValueError("ADR-009 契约违反: handoff package 缺少 living_spec_md_path")

md_path = Path(md_path_str)
if not md_path.exists():
    raise ValueError(f"ADR-009 契约违反: living_spec.md 文件缺失 ({md_path})")

from domains.spec_pro.spec_living_md import parse_living_spec_md
living_spec = parse_living_spec_md(md_content)
```

**禁止**：
- ❌ Fallback 到 JSON（`living_spec.json`）
- ❌ 静默降级（`try/except` 吞掉错误）
- ❌ 从 `frozen_spec.json` 读取（已废弃）

### 输出端契约（P0）

**必须生成 MD 格式交付物。**

Solution Pro 输出：
- `final_solution.md`（V2 schema：meta_info, overview, key_decisions, implementation_phases）
- `solution_document.md`（用户可见文档）
- `frozen_spec.md`（跨域 handoff，供 Ship Pro 读取）

Spec Pro 输出：
- `living_spec.md`（需求规格说明书）

Ship Pro 输出：
- `ship_plan.md`（执行计划）

Deliver Pro 输出：
- `delivery_report.md`（交付报告）

### 全域完成标准

每个域必须实现：

1. **`render_xxx_md(data: dict) → str`**：将内部 dict 渲染为 MD
2. **Sidecar write**：MD 写入 blackboard（与 JSON 并存，但 MD 优先）
3. **MD 优先读取**：下游域从 MD 读取，不从 JSON 读取

### Schema 规范

每个 MD 文件必须包含：

- **YAML Frontmatter**：domain, version, session
- **Required Sections**：由 Pydantic 契约定义（如 `REQUIRED_SECTIONS = ["meta_info", "overview", ...]`）
- **Round-trip 支持**：`render_xxx_md()` + `parse_xxx_md()` 必须可逆

### 失败处理

**MD 渲染失败 → 记录 ERROR 级别日志，不静默跳过。**

```python
try:
    from domains.solution_pro.frozen_living_md import render_frozen_spec_md
    frozen_spec_md = render_frozen_spec_md(frozen_spec)
    bm.write("data/frozen_spec.md", frozen_spec_md)
except Exception as e:
    logging.getLogger(__name__).error(
        f"ADR-009 契约违反: frozen_spec.md 渲染失败（Ship Pro 将失败）: {e}"
    )
    # 不 raise，但记录 ERROR（下游会因 MD 缺失而失败）
```

## Consequences

### 正面影响

1. **信息守恒**：跨域传递信息不丢失（MD 保留完整上下文，JSON 仅 ~1KB 索引）
2. **人类可读**：交付物可直接查看，无需 JSON 解析
3. **可追溯**：MD 文件可直接 diff、版本控制、审计
4. **契约强制**：MD 缺失 → raise ValueError，不静默降级（不可信的约束不是约束）

### 负面影响

1. **性能开销**：MD 渲染 + 解析比纯 JSON 慢（实测 <100ms，可接受）
2. **实现成本**：每个域需实现 `render_xxx_md()` + `parse_xxx_md()`（一次性成本）
3. **Schema 演进**：MD 格式变更需同步更新 render/parse 函数（需版本兼容检查）

### 风险缓解

- **性能**：MD 渲染仅在交付时执行，管线内部仍用 JSON（保持性能）
- **实现成本**：提供 `core/md_utils.py` 通用工具（YAML frontmatter、表格渲染）
- **Schema 演进**：Pydantic 契约 + 版本号（`schema_version: "2.0.0"`）+ round-trip 测试

### 迁移状态

| 域 | 版本 | MD 迁移状态 | 关键文件 |
|:---|:---:|:---:|:---|
| Spec Pro | V2.2.0 | ✅ 完成 | `spec_living_md.py` |
| Solution Pro | V3.1.0 | ✅ 完成 | `solution_living_md.py`, `frozen_living_md.py` |
| Ship Pro | V8.2 | ✅ 完成 | `ship_plan_md.py` |
| Deliver Pro | V1.0.0 | ✅ 完成 | `delivery_report_md.py` |
| Research Pro | V1.0 | ⏸️ 未迁移 | 无跨域交付物，暂不需要 |

### 测试覆盖

- ✅ 592+ tests passed（含 MD round-trip 测试）
- ✅ 契约笼子：Pydantic raise ValueError，不静默降级
- ✅ 信息守恒检查：`len(final) >= sum(len(worker.content))`

## References

- CHANGELOG.md V3.0.0 (2026-07-20)
- `domains/solution_pro/__init__.py`（`_try_load_handoff_package()`）
- `domains/solution_pro/solution_living_md.py`（`render_final_solution_md()`）
- `domains/solution_pro/frozen_living_md.py`（`render_frozen_spec_md()`）
- `domains/spec_pro/spec_living_md.py`（`parse_living_spec_md()`）
- `reviews/adr009_spec_pro_review.json`（P0-P2 问题清单）
