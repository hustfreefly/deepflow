"""
事实锚点校验器测试

测试简历优化后的事实信息保留情况
"""

import sys
import json
sys.path.insert(0, '/Users/allen/.openclaw/workspace/.deepflow/projects/resumefit/src')

from anchor_validator import extract_anchors, validate_anchors


def test_extract_anchors():
    """测试锚点提取功能"""
    print("=== 测试：锚点提取 ===")

    sample_resume = """
# 张三

## 工作经历

### 高级封装工程师 - 华为技术有限公司
2020.06 - 至今
- 负责 2.5D/3D 先进封装工艺开发
- 优化 CoWoS 封装良率，提升 15%
- 管理 5 人技术团队

### 封装工程师 - 中芯国际集成电路制造有限公司
2016.07 - 2020.05
- 参与 FCBGA 封装项目
- 降低封装成本 20%

## 教育背景

清华大学 材料科学与工程 硕士
2014.09 - 2016.06

北京理工大学 材料成型及控制工程 本科
2010.09 - 2014.06

## 技能

封装技术：CoWoS、FCBGA、2.5D/3D、TSV、RDL
工具：Cadence、ANSYS、Mentor Graphics
"""

    anchors = extract_anchors(sample_resume)

    print(f"公司: {anchors['companies']}")
    print(f"职位: {anchors['titles']}")
    print(f"日期: {anchors['dates']}")
    print(f"学历: {anchors['education']}")
    print(f"数据: {anchors['metrics']}")

    # 验证关键锚点被提取
    assert '华为技术有限公司' in anchors['companies'] or '华为技术' in anchors['companies'], "未提取到华为"
    assert '中芯国际' in str(anchors['companies']), "未提取到中芯国际"
    assert len(anchors['dates']) >= 4, f"日期提取不足，只找到 {len(anchors['dates'])} 个"
    assert '清华大学' in anchors['education'], "未提取到清华大学"
    assert '硕士' in anchors['education'] or '本科' in anchors['education'], "未提取到学位"
    assert len(anchors['metrics']) >= 2, "未提取到量化数据"

    print("✅ 锚点提取测试通过\n")


def test_validate_anchors_pass():
    """测试锚点校验通过场景"""
    print("=== 测试：锚点校验通过 ===")

    original = """
高级封装工程师 - 华为技术有限公司
2020.06 - 至今
优化 CoWoS 封装良率，提升 15%

清华大学 材料科学与工程 硕士
"""

    optimized_data = {
        "optimized_sections": [
            {
                "title": "工作经历",
                "content": "高级封装工程师 - 华为技术有限公司\n2020.06 - 至今\n- 主导 CoWoS 先进封装工艺优化\n- 成功提升封装良率 15%",
                "section_type": "experience"
            },
            {
                "title": "教育背景",
                "content": "清华大学 材料科学与工程 硕士",
                "section_type": "education"
            }
        ]
    }

    result = validate_anchors(original, optimized_data)

    print(f"结果: {result['summary']}")
    assert result['valid'] == True, "应该校验通过"
    print("✅ 锚点校验通过测试通过\n")


def test_validate_anchors_fail():
    """测试锚点校验失败场景"""
    print("=== 测试：锚点校验失败 ===")

    original = """
高级封装工程师 - 华为技术有限公司
2020.06 - 至今
优化 CoWoS 封装良率，提升 15%

清华大学 材料科学与工程 硕士
"""

    # 故意丢失公司名和时间
    optimized_data = {
        "optimized_sections": [
            {
                "title": "工作经历",
                "content": "高级封装工程师 - 某科技公司\n- 主导先进封装工艺优化\n- 成功提升封装良率",
                "section_type": "experience"
            },
            {
                "title": "教育背景",
                "content": "某大学 材料科学与工程",
                "section_type": "education"
            }
        ]
    }

    result = validate_anchors(original, optimized_data)

    print(f"结果: {result['summary']}")
    print(f"缺失: {result['missing']}")
    assert result['valid'] == False, "应该校验失败"
    assert len(result['missing']['companies']) > 0, "应该检测到公司名丢失"
    print("✅ 锚点校验失败测试通过\n")


def test_validate_anchors_metrics():
    """测试量化数据校验"""
    print("=== 测试：量化数据校验 ===")

    original = """
- 提升良率 15%
- 降低成本 20%
- 管理 5 人团队
"""

    # 丢失量化数据
    optimized_data = {
        "optimized_sections": [
            {
                "title": "工作经历",
                "content": "- 显著提升良率\n- 有效降低成本\n- 管理技术团队",
                "section_type": "experience"
            }
        ]
    }

    result = validate_anchors(original, optimized_data)

    print(f"结果: {result['summary']}")
    print(f"缺失数据: {result['missing']['metrics']}")
    # 量化数据丢失应该被检测
    assert result['valid'] == False or len(result['missing']['metrics']) > 0, "应该检测到量化数据丢失"
    print("✅ 量化数据校验测试通过\n")


if __name__ == '__main__':
    test_extract_anchors()
    test_validate_anchors_pass()
    test_validate_anchors_fail()
    test_validate_anchors_metrics()

    print("=" * 50)
    print("✅ 所有事实锚点校验测试通过！")
    print("=" * 50)
