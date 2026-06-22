"""
事实锚点校验器

校验优化后的简历是否保留了所有不可变信息：
- 公司名称
- 职位名称
- 入职/离职时间
- 学历信息
- 量化数据

版本: 1.0.0-Lite
"""

import re
from typing import Dict, List, Any


def extract_anchors(text: str) -> Dict[str, List[str]]:
    """
    从简历文本中提取事实锚点

    Returns:
        {
            'companies': [...],
            'titles': [...],
            'dates': [...],
            'education': [...],
            'metrics': [...]
        }
    """
    anchors = {
        'companies': [],
        'titles': [],
        'dates': [],
        'education': [],
        'metrics': []
    }

    # 公司名称（中文 + 英文）
    company_patterns = [
        r'([\u4e00-\u9fa5]+(?:公司|集团|科技|技术|有限|股份|研究院|实验室))',
        r'([A-Z][a-zA-Z\s]+(?:Inc\.?|Corp\.?|Ltd\.?|LLC|Technologies|Solutions))'
    ]
    for pattern in company_patterns:
        matches = re.findall(pattern, text)
        anchors['companies'].extend(matches)

    # 职位名称
    title_patterns = [
        r'(?:职位|岗位|Title):\s*([^\n]+)',
        r'([\u4e00-\u9fa5]+(?:工程师|经理|总监|主管|专员|顾问|架构师|研究员))',
        r'([A-Z][a-zA-Z\s]+(?:Engineer|Manager|Director|Specialist|Consultant|Architect))'
    ]
    for pattern in title_patterns:
        matches = re.findall(pattern, text)
        anchors['titles'].extend(matches)

    # 日期（入职/离职时间）
    date_patterns = [
        r'(\d{4}[./\-]\d{1,2}(?:[./\-]\d{1,2})?)',
        r'(\d{4}年\d{1,2}月)',
        r'((?:19|20)\d{2}[-/年]\d{1,2}(?:[-/月]\d{1,2}日?)?)'
    ]
    for pattern in date_patterns:
        matches = re.findall(pattern, text)
        anchors['dates'].extend(matches)

    # 学历信息
    education_patterns = [
        r'([\u4e00-\u9fa5]+(?:大学|学院|University|College|Institute))',
        r'([\u4e00-\u9fa5]+(?:本科|硕士|博士|学士|MBA|EMBA|PhD|Master|Bachelor))',
        r'((?:本科|硕士|博士|学士|MBA|EMBA|PhD|Master|Bachelor)[\u4e00-\u9fa5]*)'
    ]
    for pattern in education_patterns:
        matches = re.findall(pattern, text)
        anchors['education'].extend(matches)

    # 量化数据
    metric_patterns = [
        r'(\d+(?:\.\d+)?%)',
        r'(\d+(?:\.\d+)?(?:倍|万|亿|K|M|B))',
        r'(提升|降低|增长|减少|优化|节省)(?:了)?\s*(\d+(?:\.\d+)?%?)',
        r'(\d+)\s*(?:人|个|项|次|天|月|年)'
    ]
    for pattern in metric_patterns:
        matches = re.findall(pattern, text)
        if isinstance(matches[0], tuple) if matches else False:
            for match in matches:
                anchors['metrics'].extend([m for m in match if m])
        else:
            anchors['metrics'].extend(matches)

    # 去重
    for key in anchors:
        anchors[key] = list(set(anchors[key]))

    return anchors


def validate_anchors(original: str, optimized_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    校验优化后的简历是否保留了所有事实锚点

    Args:
        original: 原始简历文本
        optimized_data: 优化后的 JSON 数据（包含 optimized_sections）

    Returns:
        {
            'valid': bool,
            'missing': {
                'companies': [...],
                'titles': [...],
                'dates': [...],
                'education': [...],
                'metrics': [...]
            },
            'summary': str
        }
    """
    # 提取原始锚点
    original_anchors = extract_anchors(original)

    # 构建优化后的完整文本
    optimized_text = ''
    for section in optimized_data.get('optimized_sections', []):
        optimized_text += section.get('title', '') + '\n'
        optimized_text += section.get('content', '') + '\n'

    # 提取优化后的锚点
    optimized_anchors = extract_anchors(optimized_text)

    # 检查缺失的锚点
    missing = {}
    for key in original_anchors:
        missing[key] = []
        for anchor in original_anchors[key]:
            # 精确匹配或模糊匹配
            if anchor not in optimized_text:
                # 尝试模糊匹配（去除空格、标点）
                anchor_clean = re.sub(r'[\s\-./年月度日]', '', anchor)
                optimized_clean = re.sub(r'[\s\-./年月度日]', '', optimized_text)
                if anchor_clean not in optimized_clean:
                    missing[key].append(anchor)

    # 判断是否通过
    valid = all(len(v) == 0 for v in missing.values())

    # 生成摘要
    if valid:
        summary = '✅ 事实锚点校验通过：所有关键信息均已保留'
    else:
        issues = []
        if missing['companies']:
            issues.append(f"公司名: {', '.join(missing['companies'])}")
        if missing['titles']:
            issues.append(f"职位: {', '.join(missing['titles'])}")
        if missing['dates']:
            issues.append(f"时间: {', '.join(missing['dates'])}")
        if missing['education']:
            issues.append(f"学历: {', '.join(missing['education'])}")
        if missing['metrics']:
            issues.append(f"数据: {', '.join(missing['metrics'])}")
        summary = f"⚠️ 事实锚点校验失败：以下信息被修改或丢失\n- " + "\n- ".join(issues)

    return {
        'valid': valid,
        'missing': missing,
        'summary': summary,
        'original_anchors_count': {k: len(v) for k, v in original_anchors.items()},
        'optimized_anchors_count': {k: len(v) for k, v in optimized_anchors.items()}
    }
