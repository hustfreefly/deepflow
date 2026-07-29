"""
Input Element Conservation Gate — Spec Pro 出口语义守恒验证

用户铁律（最高优先级）：
- 需求对齐是硬性要求，不存在降级或静默方案
- 不一致就直接 raise，禁止静默或降级
- fail-closed：LLM 调用失败 → raise，禁止异常时静默放行

架构（两层 LLM，禁止正则做语义判断）：
  Layer 1: LLM 从原始输入提取语义要素清单 [{element, criticality: MUST|SHOULD}]
  Layer 2: LLM-as-Judge 逐要素判定 living_spec 覆盖状态 COVERED/PARTIAL/MISSING

处置：
  - MUST 要素 MISSING → raise ValueError（HARD_BLOCK handoff）
  - SHOULD 要素 MISSING → 写入 declared_gaps（显式记录，不阻断）
  - LLM 调用失败 → raise（fail-closed，禁止静默放行）

使用方式：
    from domains.spec_pro.contracts.gate_input_conservation import gate_input_conservation
    result = gate_input_conservation(user_input, living_spec_data, llm_call)
    # result: {"passed": True, "declared_gaps": [], "elements": [...], "conservation_rate": 1.0}
"""

from typing import Callable, Dict, Any, List
import json
import logging
import re

logger = logging.getLogger(__name__)


# ============================================================================
# Layer 1: 语义要素提取 Prompt
# ============================================================================

EXTRACT_ELEMENTS_PROMPT = """你是需求要素提取专家。从用户原始输入中提取所有语义要素。

## 用户原始输入
{user_input}

## 提取规则
1. 每个独立的技术术语、约束、目标、时间框架、组织原则、交付物类型都算一个要素
2. 标题/非编号文本中的要素也必须提取（不得因为"不是编号列表"而忽略）
3. 标注 criticality：
   - MUST：用户显式提及的硬约束（明确提到的技术平台、时间线、组织原则等）
   - SHOULD：隐含期望或上下文推断的要素
4. category 开放枚举：technology / organization_principle / timeline_constraint / domain / deliverable_type / quality_attribute / scope / 其他

## 输出格式
输出 JSON：
```json
{{"input_elements": [{{"id": "E1", "element": "要素描述", "category": "technology", "criticality": "MUST"}}]}}
```

只输出 JSON，不要输出其他内容。"""


# ============================================================================
# Layer 2: LLM-as-Judge 守恒判定 Prompt
# ============================================================================

JUDGE_CONSERVATION_PROMPT = """你是信息守恒验证专家。逐要素判断 living_spec 是否覆盖了原始输入的每个语义要素。

## 原始输入要素清单（{element_count} 个）
{elements_json}

## Living Spec 摘要
- topic: {topic}
- objective: {objective}
- core_summary（前 2000 字）: {core_summary}
- semantic_anchors: {anchors}
- requirement_index 数量: {req_count}
- narrative（前 1000 字）: {narrative}

## 判定标准
- COVERED: 要素在 living_spec 中有明确语义对应（不要求字面匹配，但语义必须等价）
- PARTIAL: 要素被部分覆盖但有信息损失（例如只覆盖了子项）
- MISSING: 要素在 living_spec 中完全缺失

## 输出格式
输出 JSON：
```json
{{"conservation_results": [{{"id": "E1", "element": "要素描述", "status": "COVERED/PARTIAL/MISSING", "evidence": "判定依据"}}], "conservation_rate": 0.0}}
```

conservation_rate = COVERED 要素数 / 总要素数（PARTIAL 算 0.5，MISSING 算 0）。

只输出 JSON，不要输出其他内容。"""


# ============================================================================
# JSON 解析工具（复用 extract_semantic_anchors 的模式）
# ============================================================================

def _parse_llm_json(raw: str) -> Any:
    """从 LLM 输出中提取 JSON（处理 markdown 代码块）"""
    # 尝试直接解析
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # 尝试提取 ```json ... ``` 块
    match = re.search(r'```(?:json)?\s*\n?(.*?)\n?\s*```', raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # 尝试找第一个 { 和最后一个 }（或 [ 和 ]）
    for start_char, end_char in [('{', '}'), ('[', ']')]:
        start = raw.find(start_char)
        end = raw.rfind(end_char)
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(raw[start:end + 1])
            except json.JSONDecodeError:
                pass

    return None


# ============================================================================
# Layer 1: 要素提取
# ============================================================================

def extract_input_elements(
    user_input: str,
    llm_call: Callable[[str], str],
) -> List[Dict[str, str]]:
    """
    用 LLM 从原始输入提取语义要素清单。

    Args:
        user_input: 用户原始输入文本
        llm_call: LLM 调用函数 (prompt: str) -> str

    Returns:
        [{"id": "E1", "element": "...", "category": "...", "criticality": "MUST|SHOULD"}]

    Raises:
        ValueError: LLM 调用失败或返回格式不合法（fail-closed）
    """
    if not user_input or len(user_input.strip()) < 5:
        raise ValueError(
            f"gate_input_conservation: user_input 过短（{len(user_input or '')} chars），无法提取要素"
        )

    prompt = EXTRACT_ELEMENTS_PROMPT.format(user_input=user_input[:5000])

    # fail-closed: LLM 调用失败直接 raise
    try:
        raw_output = llm_call(prompt)
    except Exception as e:
        raise ValueError(
            f"gate_input_conservation: Layer 1 要素提取 LLM 调用失败（fail-closed）: {e}"
        ) from e

    if not raw_output or not raw_output.strip():
        raise ValueError(
            "gate_input_conservation: Layer 1 要素提取 LLM 返回空输出（fail-closed）"
        )

    data = _parse_llm_json(raw_output)
    if data is None:
        raise ValueError(
            f"gate_input_conservation: Layer 1 要素提取 JSON 解析失败（fail-closed）。\n"
            f"原始输出前 500 字: {raw_output[:500]}"
        )

    # 兼容 list 或 dict 包装
    if isinstance(data, dict):
        elements = data.get("input_elements", [])
    elif isinstance(data, list):
        elements = data
    else:
        raise ValueError(
            f"gate_input_conservation: Layer 1 输出格式错误: expected dict/list, got {type(data).__name__}"
        )

    if not elements:
        raise ValueError(
            "gate_input_conservation: Layer 1 提取到 0 个要素（fail-closed）。\n"
            "LLM 未从原始输入中提取任何语义要素，这不应该发生。"
        )

    # 验证每个要素的结构
    validated = []
    for i, elem in enumerate(elements):
        if not isinstance(elem, dict):
            raise ValueError(
                f"gate_input_conservation: 要素 [{i}] 不是 dict: {type(elem).__name__}"
            )
        if not elem.get("element"):
            raise ValueError(
                f"gate_input_conservation: 要素 [{i}] 缺少 'element' 字段"
            )
        validated.append({
            "id": elem.get("id", f"E{i+1}"),
            "element": str(elem["element"]),
            "category": str(elem.get("category", "其他")),
            "criticality": str(elem.get("criticality", "MUST")).upper(),
        })

    logger.info(f"gate_input_conservation: Layer 1 提取了 {len(validated)} 个语义要素")
    return validated


# ============================================================================
# Layer 2: LLM-as-Judge 守恒判定
# ============================================================================

def judge_element_conservation(
    elements: List[Dict[str, str]],
    living_spec: Dict[str, Any],
    llm_call: Callable[[str], str],
) -> Dict[str, Any]:
    """
    LLM-as-Judge 逐要素判定 living_spec 覆盖状态。

    Args:
        elements: Layer 1 提取的语义要素清单
        living_spec: living_spec 数据
        llm_call: LLM 调用函数

    Returns:
        {"conservation_results": [...], "conservation_rate": float}

    Raises:
        ValueError: LLM 调用失败或返回格式不合法（fail-closed）
    """
    # 构建 living_spec 摘要
    confirmed = living_spec.get("confirmed", {})
    req_index = living_spec.get("requirement_index", [])
    anchors = living_spec.get("semantic_anchors", [])

    topic = str(confirmed.get("topic", living_spec.get("topic", "")))
    objective = str(confirmed.get("objective", ""))
    core_summary = str(living_spec.get("core_summary", ""))[:2000]
    narrative = str(living_spec.get("narrative", living_spec.get("core_summary", "")))[:1000]
    anchors_str = json.dumps(
        [a.get("name", str(a)) if isinstance(a, dict) else str(a) for a in anchors],
        ensure_ascii=False,
    )

    elements_json = json.dumps(elements, ensure_ascii=False, indent=2)

    prompt = JUDGE_CONSERVATION_PROMPT.format(
        element_count=len(elements),
        elements_json=elements_json,
        topic=topic,
        objective=objective,
        core_summary=core_summary,
        anchors=anchors_str,
        req_count=len(req_index) if isinstance(req_index, list) else 0,
        narrative=narrative,
    )

    # fail-closed: LLM 调用失败直接 raise
    try:
        raw_output = llm_call(prompt)
    except Exception as e:
        raise ValueError(
            f"gate_input_conservation: Layer 2 Judge LLM 调用失败（fail-closed）: {e}"
        ) from e

    if not raw_output or not raw_output.strip():
        raise ValueError(
            "gate_input_conservation: Layer 2 Judge LLM 返回空输出（fail-closed）"
        )

    data = _parse_llm_json(raw_output)
    if data is None:
        raise ValueError(
            f"gate_input_conservation: Layer 2 Judge JSON 解析失败（fail-closed）。\n"
            f"原始输出前 500 字: {raw_output[:500]}"
        )

    results = data.get("conservation_results", [])
    if not isinstance(results, list):
        raise ValueError(
            f"gate_input_conservation: Layer 2 输出 conservation_results 不是 list: {type(results).__name__}"
        )

    conservation_rate = float(data.get("conservation_rate", 0.0))

    return {
        "conservation_results": results,
        "conservation_rate": conservation_rate,
    }


# ============================================================================
# 主入口：gate_input_conservation
# ============================================================================

def gate_input_conservation(
    user_input: str,
    living_spec: Dict[str, Any],
    llm_call: Callable[[str], str],
) -> Dict[str, Any]:
    """
    输入要素守恒 Gate — Spec Pro handoff 前调用。

    两层 LLM 架构：
      1. LLM 提取原始输入语义要素
      2. LLM-as-Judge 判定 living_spec 覆盖状态

    处置（用户铁律）：
      - MUST 要素 MISSING → raise ValueError（HARD_BLOCK handoff）
      - SHOULD 要素 MISSING → declared_gaps（显式记录，不阻断）
      - LLM 调用失败 → raise（fail-closed）

    Args:
        user_input: 用户原始输入文本
        living_spec: living_spec 数据 dict
        llm_call: LLM 调用函数 (prompt: str) -> str

    Returns:
        {
            "passed": True,
            "conservation_rate": float,
            "elements": [...],
            "declared_gaps": [...],  # SHOULD 要素未覆盖
            "details": [...]  # 完整判定结果
        }

    Raises:
        ValueError: MUST 要素 MISSING 或 LLM 调用失败
    """
    # Layer 1: 提取语义要素
    elements = extract_input_elements(user_input, llm_call)

    # Layer 2: LLM-as-Judge 守恒判定
    judge_result = judge_element_conservation(elements, living_spec, llm_call)

    # 处置决策
    results = judge_result["conservation_results"]
    conservation_rate = judge_result["conservation_rate"]

    # 构建要素 id → element 映射
    element_map = {e["id"]: e for e in elements}

    # 分类：MUST MISSING / SHOULD MISSING / 其他
    must_missing = []
    should_missing = []
    declared_gaps = []

    for r in results:
        elem_id = r.get("id", "")
        status = r.get("status", "MISSING").upper()
        elem_info = element_map.get(elem_id, {})
        criticality = elem_info.get("criticality", "MUST")
        element_desc = r.get("element", elem_info.get("element", "?"))

        if status == "MISSING":
            if criticality == "MUST":
                must_missing.append({
                    "id": elem_id,
                    "element": element_desc,
                    "evidence": r.get("evidence", ""),
                })
            else:
                # SHOULD or NICE
                should_missing.append({
                    "id": elem_id,
                    "element": element_desc,
                    "criticality": criticality,
                    "evidence": r.get("evidence", ""),
                })
                declared_gaps.append({
                    "id": elem_id,
                    "element": element_desc,
                    "criticality": criticality,
                })
        elif status == "PARTIAL":
            # PARTIAL 不算 MISSING，但记录
            pass

    # 用户铁律：MUST 要素 MISSING → raise ValueError
    if must_missing:
        missing_names = [m["element"] for m in must_missing]
        raise ValueError(
            f"输入要素守恒 Gate 阻断（HARD_BLOCK）: "
            f"{len(must_missing)} 个 MUST 要素在 living_spec 中缺失: {missing_names}\n"
            f"conservation_rate={conservation_rate:.2f}\n"
            f"详情: {json.dumps(must_missing, ensure_ascii=False, indent=2)}\n\n"
            f"修复: 重新运行 Spec Pro parse 阶段，确保原始输入的所有关键要素被保留。"
        )

    logger.info(
        f"gate_input_conservation: PASS — conservation_rate={conservation_rate:.2f}, "
        f"declared_gaps={len(declared_gaps)}"
    )

    return {
        "passed": True,
        "conservation_rate": conservation_rate,
        "elements": elements,
        "declared_gaps": declared_gaps,
        "details": results,
    }
