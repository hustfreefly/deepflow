"""
Harness V2 验证器
=================

基于 DeepFlow 基础契约的验证模块
用于强制检查 Harness V2 合规性

P0-3 修复: Summarizer 响应检查机制
"""

from typing import List, Tuple, Dict, Any


def validate_summarizer_harness_response(
    summarizer_output: dict,
    final_feedback: List[str],
    final_improvements: List[str]
) -> Tuple[bool, List[str], dict]:
    """
    验证 Summarizer 是否完整响应 Harness Final 意见
    
    DeepFlow 基础契约合规:
    - 显式验证（非依赖 Agent 自觉遵守）
    - 返回详细错误信息
    - 提供修正建议
    
    Args:
        summarizer_output: Summarizer 输出字典
        final_feedback: Harness Final 的 feedback 列表
        final_improvements: Harness Final 的 improvements 列表
        
    Returns:
        (是否有效, 错误列表, 修正建议)
    """
    errors = []
    suggestions = {
        "missing_responses": [],
        "insufficient_reasoning": [],
        "format_issues": [],
        "additions_needed": []
    }
    
    # 1. 检查 harness_response 字段存在
    if "harness_response" not in summarizer_output:
        errors.append("缺少 harness_response 字段")
        suggestions["format_issues"].append("必须在输出 JSON 中包含 harness_response 字段")
        suggestions["additions_needed"].append({
            "field": "harness_response",
            "template": {
                "scores_received": {"overall": 0.0, "decision": "PASS"},
                "feedback_addressed": [],
                "improvements_addressed": [],
                "self_assessment": {"score": 0.0, "meets_standard": False, "note": ""}
            }
        })
        return False, errors, suggestions
    
    hr = summarizer_output["harness_response"]
    
    # 2. 检查必需子字段
    required_fields = ["scores_received", "feedback_addressed", 
                      "improvements_addressed", "self_assessment"]
    for field in required_fields:
        if field not in hr:
            errors.append(f"harness_response 缺少: {field}")
            suggestions["format_issues"].append(f"必须添加字段: {field}")
    
    # 3. 检查 feedback 是否全部响应
    if "feedback_addressed" in hr:
        if not isinstance(hr["feedback_addressed"], list):
            errors.append("feedback_addressed 必须是列表")
            suggestions["format_issues"].append("feedback_addressed 必须是数组格式")
        else:
            responded_items = {item.get("feedback", "") for item in hr["feedback_addressed"]}
            
            for fb in final_feedback:
                if fb not in responded_items:
                    errors.append(f"未响应 feedback: {fb[:50]}...")
                    suggestions["missing_responses"].append({
                        "type": "feedback",
                        "content": fb,
                        "template": {
                            "feedback": fb,
                            "adopted": True,  # 或 False
                            "action": "说明采纳后的具体行动或不采纳的详细理由（至少20字）"
                        }
                    })
            
            # 4. 检查每条响应质量
            for idx, item in enumerate(hr["feedback_addressed"]):
                if not isinstance(item, dict):
                    errors.append(f"feedback_addressed[{idx}] 必须是字典")
                    continue
                    
                if "adopted" not in item:
                    errors.append(f"feedback 响应缺少 adopted 字段: {item.get('feedback', '')[:30]}...")
                    suggestions["format_issues"].append(f"为 feedback '{item.get('feedback', '')[:20]}...' 添加 adopted: true/false")
                
                if "action" not in item or not item.get("action"):
                    errors.append(f"feedback 响应缺少 action: {item.get('feedback', '')[:30]}...")
                    suggestions["format_issues"].append(f"为 feedback '{item.get('feedback', '')[:20]}...' 添加 action 字段")
                elif not item.get("adopted") and len(item.get("action", "")) < 20:
                    # 不采纳的必须有充分理由（至少20字）
                    errors.append(f"不采纳的理由不充分（少于20字）: {item.get('feedback', '')[:30]}...")
                    suggestions["insufficient_reasoning"].append({
                        "item": item.get("feedback", ""),
                        "current_action": item.get("action", ""),
                        "required": "至少20字的详细理由，说明为什么不采纳以及替代方案"
                    })
    
    # 5. 检查 improvements 是否全部响应
    if "improvements_addressed" in hr:
        if not isinstance(hr["improvements_addressed"], list):
            errors.append("improvements_addressed 必须是列表")
            suggestions["format_issues"].append("improvements_addressed 必须是数组格式")
        else:
            responded_impls = {item.get("suggestion", "") for item in hr["improvements_addressed"]}
            
            for imp in final_improvements:
                if imp not in responded_impls:
                    errors.append(f"未响应 improvement: {imp[:50]}...")
                    suggestions["missing_responses"].append({
                        "type": "improvement",
                        "content": imp,
                        "template": {
                            "suggestion": imp,
                            "adopted": True,  # 或 False
                            "action": "说明采纳后的具体行动或不采纳的详细理由（至少20字）"
                        }
                    })
            
            # 检查每条 improvement 响应质量
            for idx, item in enumerate(hr["improvements_addressed"]):
                if not isinstance(item, dict):
                    errors.append(f"improvements_addressed[{idx}] 必须是字典")
                    continue
                    
                if "adopted" not in item:
                    errors.append(f"improvement 响应缺少 adopted 字段: {item.get('suggestion', '')[:30]}...")
                
                if "action" not in item or not item.get("action"):
                    errors.append(f"improvement 响应缺少 action: {item.get('suggestion', '')[:30]}...")
                elif not item.get("adopted") and len(item.get("action", "")) < 20:
                    errors.append(f"不采纳的理由不充分（少于20字）: {item.get('suggestion', '')[:30]}...")
                    suggestions["insufficient_reasoning"].append({
                        "item": item.get("suggestion", ""),
                        "current_action": item.get("action", ""),
                        "required": "至少20字的详细理由"
                    })
    
    # 6. 检查 self_assessment
    if "self_assessment" in hr:
        sa = hr["self_assessment"]
        if not isinstance(sa, dict):
            errors.append("self_assessment 必须是字典")
        else:
            if not sa.get("meets_standard") and not sa.get("note"):
                errors.append("self_assessment 未达标但未说明理由（缺少 note）")
                suggestions["format_issues"].append("如果 meets_standard=false，必须在 note 中说明理由")
    
    return len(errors) == 0, errors, suggestions


def enforce_harness_response(summarizer_task: str, 
                             final_feedback: List[str] = None,
                             final_improvements: List[str] = None) -> str:
    """
    在 Summarizer Prompt 中添加强制响应要求
    
    Args:
        summarizer_task: 基础 Summarizer Task
        final_feedback: 可选，列出具体的 feedback 以便更精确的提示
        final_improvements: 可选，列出具体的 improvements
        
    Returns:
        添加强制要求后的完整 Prompt
    """
    # 构建具体的反馈列表（如果提供）
    feedback_section = ""
    if final_feedback:
        feedback_list = "\n".join([f"  - {fb[:80]}..." for fb in final_feedback[:5]])  # 最多显示5条
        feedback_section = f"""

**你必须响应的 feedback（共{len(final_feedback)}条）:**
{feedback_list}
{"  ..." if len(final_feedback) > 5 else ""}
"""
    
    improvements_section = ""
    if final_improvements:
        impl_list = "\n".join([f"  - {imp[:80]}..." for imp in final_improvements[:5]])
        improvements_section = f"""

**你必须响应的 improvements（共{len(final_improvements)}条）:**
{impl_list}
{"  ..." if len(final_improvements) > 5 else ""}
"""
    
    enforcement = f"""

## ⚠️ 强制要求：Harness Final 意见响应

### 验证标准（代码级检查）

你的输出将通过以下代码逻辑验证：

```python
# 1. 检查字段存在
assert "harness_response" in output
assert "feedback_addressed" in output["harness_response"]
assert "improvements_addressed" in output["harness_response"]

# 2. 检查全部响应
for feedback in final_feedback:
    assert feedback in [item["feedback"] for item in output["harness_response"]["feedback_addressed"]]

# 3. 检查理由充分性
for item in output["harness_response"]["feedback_addressed"]:
    if not item["adopted"]:
        assert len(item["action"]) >= 20, "不采纳的理由必须至少20字"
```
{feedback_section}
{improvements_section}
### 自检清单（输出前必须完成）

- [ ] 我是否逐条响应了所有 feedback？（共{len(final_feedback) if final_feedback else "N"}条）
- [ ] 我是否逐条响应了所有 improvements？（共{len(final_improvements) if final_improvements else "N"}条）
- [ ] 每条响应是否都有 adopted: true/false？
- [ ] 不采纳的是否都有至少20字的理由？
- [ ] self_assessment 是否诚实准确？

### 常见错误（避免）

❌ 错误示例（理由不充分）：
```json
{{
  "feedback_addressed": [
    {{"feedback": "优化缓存策略", "adopted": false, "action": "不需要"}}  // 理由太少！
  ]
}}
```

✅ 正确示例（理由充分）：
```json
{{
  "feedback_addressed": [
    {{
      "feedback": "优化缓存策略", 
      "adopted": false, 
      "action": "当前缓存策略已满足<200ms响应要求，过度优化会增加系统复杂度，与必要性原则冲突。建议保持现有方案。"
    }}
  ]
}}
```

**未通过验证的输出将被拒绝并要求重新生成。**

"""
    return summarizer_task + "\n" + enforcement


def generate_harness_response_template(final_feedback: List[str],
                                       final_improvements: List[str]) -> dict:
    """
    生成 Harness Response 的模板，帮助 Summarizer 正确格式化输出
    
    Args:
        final_feedback: Harness Final 的 feedback 列表
        final_improvements: Harness Final 的 improvements 列表
        
    Returns:
        完整的 harness_response 模板
    """
    return {
        "harness_response": {
            "scores_received": {
                "overall": 0.85,
                "decision": "WARNING"
            },
            "feedback_addressed": [
                {
                    "feedback": fb,
                    "adopted": True,
                    "action": "已采纳并在第X节实施：具体实施内容..."
                } if i % 2 == 0 else {
                    "feedback": fb,
                    "adopted": False,
                    "action": "未采纳的理由：详细说明为什么不采纳以及替代方案（至少20字）"
                }
                for i, fb in enumerate(final_feedback)
            ],
            "improvements_addressed": [
                {
                    "suggestion": imp,
                    "adopted": True,
                    "action": "已采纳并在第Y节实施：具体实施内容..."
                } if i % 2 == 0 else {
                    "suggestion": imp,
                    "adopted": False,
                    "action": "未采纳的理由：详细说明为什么不采纳以及替代方案（至少20字）"
                }
                for i, imp in enumerate(final_improvements)
            ],
            "self_assessment": {
                "score": 0.87,
                "meets_standard": True,
                "note": "总结忠实反映了上游输出，已响应所有Harness意见"
            }
        }
    }


def calculate_compliance_score(content: str, feedback_list: List[str]) -> float:
    """
    计算Summarizer对Harness Final意见的遵从度分数
    
    基于以下指标：
    - 关键词覆盖度（反馈中的关键词是否出现在内容中）
    - 响应完整性（反馈数量 vs 响应数量）
    
    Args:
        content: Summarizer报告内容
        feedback_list: Harness Final反馈列表
    
    Returns:
        遵从度分数 (0.0 - 1.0)
    """
    if not feedback_list:
        return 1.0  # 没有反馈时，默认满分
    
    if not content:
        return 0.0
    
    content_lower = content.lower()
    
    # 计算关键词覆盖度
    covered_count = 0
    for feedback in feedback_list:
        # 提取关键词（简化处理：取前10个字符）
        keyword = feedback[:10].lower()
        if keyword in content_lower:
            covered_count += 1
    
    coverage = covered_count / len(feedback_list)
    
    # 基础分数 + 覆盖度加权
    base_score = 0.5
    score = base_score + (coverage * 0.5)
    
    return min(1.0, max(0.0, score))


if __name__ == "__main__":
    # 测试用例
    print("=" * 60)
    print("Harness Validator 测试")
    print("=" * 60)
    
    # 测试1: 有效输出
    valid_output = {
        "harness_response": {
            "scores_received": {"overall": 0.87, "decision": "WARNING"},
            "feedback_addressed": [
                {"feedback": "优化缓存", "adopted": True, "action": "已在3.2节实施Redis缓存"},
                {"feedback": "简化架构", "adopted": False, "action": "当前架构已满足需求，简化会降低扩展性，故保持现有设计。"}
            ],
            "improvements_addressed": [
                {"suggestion": "补充监控", "adopted": True, "action": "已在4.1节添加监控方案"}
            ],
            "self_assessment": {"score": 0.88, "meets_standard": True, "note": "响应完整"}
        }
    }
    
    is_valid, errors, suggestions = validate_summarizer_harness_response(
        valid_output,
        ["优化缓存", "简化架构"],
        ["补充监控"]
    )
    
    print(f"\n测试1 - 有效输出:")
    print(f"  结果: {'✅ 通过' if is_valid else '❌ 失败'}")
    if errors:
        print(f"  错误: {errors}")
    
    # 测试2: 无效输出（缺少字段）
    invalid_output = {
        "harness_response": {
            "feedback_addressed": [
                {"feedback": "优化缓存", "adopted": False, "action": "不需要"}  # 理由太短
            ]
        }
    }
    
    is_valid, errors, suggestions = validate_summarizer_harness_response(
        invalid_output,
        ["优化缓存", "简化架构"],
        ["补充监控"]
    )
    
    print(f"\n测试2 - 无效输出:")
    print(f"  结果: {'✅ 通过' if is_valid else '❌ 失败'}")
    print(f"  错误数: {len(errors)}")
    for e in errors[:3]:  # 显示前3个错误
        print(f"    - {e}")
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)
