"""
主 Agent 渲染逻辑：过渡引导词

读取 transition_prompt 数据，根据 template 渲染为用户可见的引导词文本。

设计原则：
1. 数据生成 vs 展示渲染分离
2. 用户友好：避免技术术语，使用用户能感知的价值描述
3. 简洁信息：维度评分默认折叠，只展示总分和等级
4. 使用 quality.level（S/A/B/C）而非硬编码阈值
"""

from typing import Dict


def render_transition_prompt(prompt_data: Dict) -> str:
    """渲染过渡引导词
    
    Args:
        prompt_data: 包含 template 和 variables 的字典
        
    Returns:
        渲染后的引导词文本
        
    Example:
        >>> data = {
        ...     "template": "spec_to_solution",
        ...     "variables": {
        ...         "quality_score": 82,
        ...         "quality_level": "A",
        ...         "num_users": 3,
        ...         "num_capabilities": 8,
        ...         "num_constraints": 5
        ...     }
        ... }
        >>> print(render_transition_prompt(data))
    """
    template = prompt_data.get("template", "")
    variables = prompt_data.get("variables", {})
    
    if template == "spec_to_solution":
        return _render_spec_to_solution(variables)
    elif template == "solution_to_ship":
        return _render_solution_to_ship(variables)
    elif template == "ship_completed":
        return _render_ship_completed(variables)
    else:
        return f"[未知模板: {template}]"


def _render_spec_to_solution(vars: Dict) -> str:
    """渲染 Spec Pro → Solution Pro 引导词"""
    quality_score = vars.get("quality_score", 0)
    quality_level = vars.get("quality_level", "C")
    num_users = vars.get("num_users", 0)
    num_capabilities = vars.get("num_capabilities", 0)
    num_constraints = vars.get("num_constraints", 0)
    
    # 根据质量等级选择不同模板
    if quality_level in ("S", "A"):
        # 高质量：积极鼓励
        return f"""━━━━━━━━━━━━━━━━━━━━
✅ 需求梳理完成！

📊 质量评分：{quality_score} / 100（{quality_level}级）

📄 需求文档已生成：
   • {num_users} 个用户角色
   • {num_capabilities} 项核心能力
   • {num_constraints} 项约束条件

━━━━━━━━━━━━━━━━━━━━
🎯 下一步：方案设计

基于这份需求文档，可以启动 Solution Pro 生成完整的技术方案：
  • 整体设计方案
  • 技术路线规划  
  • 实施路径图
  • 风险与对策

预计耗时：15-30 分钟

━━━━━━━━━━━━━━━━━━━━

请选择下一步：
  [1] 启动方案设计（Solution Pro）  ← 推荐
  [2] 查看需求文档详情
  [3] 继续补充需求细节

请输入数字选择。"""
    
    elif quality_level == "B":
        # 中等质量：建议继续补充
        return f"""━━━━━━━━━━━━━━━━━━━━
✅ 需求梳理完成

📊 质量评分：{quality_score} / 100（{quality_level}级）

💡 建议继续补充需求细节，提升评分后再进入方案设计，可获得更优的方案质量。

━━━━━━━━━━━━━━━━━━━━

请选择下一步：
  [1] 继续补充需求（推荐，可提升方案质量）
  [2] 启动方案设计（当前评分也可生成方案）
  [3] 查看需求文档详情

请输入数字选择。"""
    
    else:
        # 低质量（C级）：强烈建议继续补充
        return f"""━━━━━━━━━━━━━━━━━━━━
⚠️ 需求梳理完成，但质量评分较低

📊 质量评分：{quality_score} / 100（{quality_level}级）

强烈建议继续补充需求细节，提升评分后再进入方案设计。

━━━━━━━━━━━━━━━━━━━━

请选择下一步：
  [1] 继续补充需求  ← 强烈推荐
  [2] 查看当前需求文档
  [3] 仍然启动方案设计（建议先补充需求）

请输入数字选择。"""


def _render_solution_to_ship(vars: Dict) -> str:
    """渲染 Solution Pro → Ship Pro 引导词"""
    harness_score = vars.get("harness_score", 0)
    num_reqs = vars.get("num_reqs", 0)
    num_modules = vars.get("num_modules", 0)
    
    return f"""━━━━━━━━━━━━━━━━━━━━
✅ 方案设计完成！

📊 质量评分：{harness_score} / 100

📦 方案包含：
   • {num_reqs} 个需求项
   • {num_modules} 个模块
   • 整体设计方案 + 实施路径图

━━━━━━━━━━━━━━━━━━━━
🎯 下一步：工程实现

基于这份技术方案，可以启动 Ship Pro 生成可直接交付给开发的工作包：
  • 开发所需的文件结构
  • 测试验证标准
  • 部署上线配置

预计耗时：10-20 分钟

━━━━━━━━━━━━━━━━━━━━

请选择下一步：
  [1] 启动工程实现（Ship Pro）  ← 推荐
  [2] 查看方案详情
  [3] 调整方案某些部分

请输入数字选择。"""


def _render_ship_completed(vars: Dict) -> str:
    """渲染 Ship Pro 完成引导词"""
    harness_score = vars.get("harness_score", 0)
    
    return f"""━━━━━━━━━━━━━━━━━━━━
✅ 工程实现完成！

📦 工作包已生成，可直接交付给开发团队或 AI 编码助手。

📊 质量评分：{harness_score} / 100

━━━━━━━━━━━━━━━━━━━━
🎯 下一步

工作包已就绪，你可以：
  [1] 查看工作包详情  ← 推荐
  [2] 导出为 GitHub Issues（需要 gh CLI）
  [3] 生成项目脚手架代码
  [4] 下载工作包文件

━━━━━━━━━━━━━━━━━━━━

🎉 整个 DeepFlow 管线已完成！从需求 → 方案 → 工程实现，全流程闭环。"""


# 测试代码
if __name__ == "__main__":
    # 测试 Spec Pro → Solution Pro（高质量）
    test_data_1 = {
        "template": "spec_to_solution",
        "variables": {
            "quality_score": 82,
            "quality_level": "A",
            "num_users": 3,
            "num_capabilities": 8,
            "num_constraints": 5
        }
    }
    print("=== 测试 1: Spec Pro → Solution Pro (A级) ===")
    print(render_transition_prompt(test_data_1))
    print()
    
    # 测试 Solution Pro → Ship Pro
    test_data_2 = {
        "template": "solution_to_ship",
        "variables": {
            "harness_score": 92,
            "num_reqs": 12,
            "num_modules": 5
        }
    }
    print("=== 测试 2: Solution Pro → Ship Pro ===")
    print(render_transition_prompt(test_data_2))
    print()
    
    # 测试 Ship Pro 完成
    test_data_3 = {
        "template": "ship_completed",
        "variables": {
            "harness_score": 88
        }
    }
    print("=== 测试 3: Ship Pro 完成 ===")
    print(render_transition_prompt(test_data_3))
