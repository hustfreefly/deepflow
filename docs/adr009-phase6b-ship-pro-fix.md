# ADR-009 Phase 6b: Ship Pro final_solution MD-first 修复

## 问题

`domains/ship_pro/__init__.py` 中的 `load_solution_pro_output()` 函数仍然是 JSON-first：
- Line 78: 读取 `final_solution.json`
- Line 82-87: JSON 不存在则报错
- Line 90: `json.loads()` 解析 JSON

这违反了 ADR-009 的 MD-first 原则。

## 修复方案

改为 MD-first，JSON 作为 fallback：

```python
def load_solution_pro_output(project_blackboard: Path) -> dict:
    """
    从统一 blackboard 读取 Solution Pro 输出。

    ADR-009 MD-first:
      final_solution.md 是真相源。
      final_solution.json 是 fallback（向后兼容）。

    Returns:
        final_solution 的内容 dict

    Raises:
        ValueError: MD 和 JSON 都不存在或 Schema 验证失败
    """
    import logging as _logging
    _logger = _logging.getLogger(__name__)

    final_md = project_blackboard / "stages" / "final_solution.md"
    final_json = project_blackboard / "stages" / "final_solution.json"

    data = None

    # 优先读 MD
    if final_md.exists():
        from domains.solution_pro.solution_living_md import parse_final_solution_md
        md_content = final_md.read_text(encoding="utf-8")
        data = parse_final_solution_md(md_content)
        _logger.info(f"Loaded final_solution from MD: {final_md}")

    # Fallback 到 JSON
    elif final_json.exists():
        import json as _json
        data = _json.loads(final_json.read_text(encoding="utf-8"))
        if isinstance(data, str):
            data = _json.loads(data)
        _logger.info(f"Loaded final_solution from JSON (fallback): {final_json}")

    else:
        raise ValueError(
            f"Solution Pro 契约违反: final_solution.md 和 final_solution.json 都不存在\n"
            f"  期望路径: {final_md}\n"
            f"  根因: Solution Pro 未产出最终方案。\n"
            f"  修复: 重新执行 Solution Pro。"
        )

    # Schema 验证: 必需字段存在且非空
    _REQUIRED_FIELDS = [
        "key_decisions", "implementation_phases", "covered_req_ids",
        "constraint_coverage", "semantic_anchors",
    ]
    missing = [f for f in _REQUIRED_FIELDS if not data.get(f)]
    if missing:
        raise ValueError(
            f"Solution Pro 契约违反: final_solution 缺少必需字段: {missing}\n"
            f"  文件存在但内容不完整。"
        )

    _logger.info(
        f"Solution Pro output loaded: {len(data.get('key_decisions', []))} decisions, "
        f"{len(data.get('covered_req_ids', []))} reqs, "
        f"{len(data.get('risk_summary', []))} risks"
    )

    return data
```

## 同时更新文档注释

Line 65-66 的注释需要更新：
```
final_solution.json 是唯一数据源（Agent 层保证产出）。
MD 是人类可读副本，不做数据传递。不降级、不 fallback。
```

改为：
```
final_solution.md 是真相源（ADR-009 MD-first）。
final_solution.json 是 fallback（向后兼容）。
```

## 验证标准

- [ ] `grep -rn "final_solution\.json" domains/ship_pro/__init__.py` 只剩 fallback 相关引用
- [ ] 测试通过
- [ ] Ship Pro 能正常从 MD 读取 final_solution
