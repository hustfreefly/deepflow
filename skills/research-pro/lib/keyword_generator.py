"""
KeywordGenerator — ResearchPro 6维关键词扩展引擎
契约: cage/research_pro_v1.0.yaml (L1: keyword_generator)

6维扩展:
1. 主题词直译
2. 同义词扩展
3. 专业术语扩展
4. 中英文切换
5. 时间维度
6. 来源定向 (site: 操作符)
"""

from typing import Optional


class KeywordGenerator:
    """
    关键词自动生成器 — 6维扩展。
    
    从分析计划自动提取关键词组，每组生成 3-5 个变体。
    """

    # 常见中文-英文映射 (内置基础词典)
    _SYNONYMS = {
        "财报": ["年报", "financial report", "earnings", "financial results"],
        "毛利率": ["gross margin", "GPM", "毛利率趋势"],
        "净利润": ["net profit", "净利润率", "net income"],
        "营收": ["revenue", "营业收入", "sales"],
        "市场份额": ["market share", "市占率", "市场占有率"],
        "竞争格局": ["competitive landscape", "行业竞争", "竞争分析"],
        "估值": ["valuation", "PE", "PB", "估值分析"],
        "风险": ["risk", "风险因素", "潜在风险"],
        "增长": ["growth", "增速", "增长率", "同比增长"],
        "投资": ["investment", "投资分析", "投资建议"],
    }

    def __init__(self, plan: dict) -> None:
        """
        初始化 KeywordGenerator。

        Args:
            plan: analysis_plan.json 内容 (dict)
        """
        self.plan = plan
        self.dimensions = plan.get("research_dimensions", [])
        self.subtopics = plan.get("subtopics", [])

    def generate(self, max_groups: int = 15) -> list[dict]:
        """
        生成关键词组。

        Args:
            max_groups: 最大组数 (快速模式 ≤5, 标准模式 ≤15)

        Returns:
            list[dict]: 关键词组列表, 每组含 base + variants + priority
        """
        groups = []

        # 从 dimensions 和 subtopics 提取基础关键词
        bases = list(self.subtopics) + list(self.dimensions)

        for i, base in enumerate(bases):
            if len(groups) >= max_groups:
                break

            variants = self.expand(base)
            groups.append({
                "base": base,
                "variants": variants[:5],  # 最多 5 个变体
                "priority": min(i + 1, 5),  # 1-5, 1 最高
            })

        # 如果不够, 补充时间维度和来源定向
        if len(groups) < max_groups:
            for base in bases[:3]:
                if len(groups) >= max_groups:
                    break
                # 时间维度
                groups.append({
                    "base": f"{base} 2025",
                    "variants": [f"{base} 2025", f"{base} latest", f"{base} 最新"],
                    "priority": 3,
                })

        return groups[:max_groups]

    def expand(self, base_keyword: str) -> list[str]:
        """
        6维扩展单个关键词。

        Args:
            base_keyword: 基础关键词

        Returns:
            list[str]: 3-5 个变体
        """
        variants = [base_keyword]

        # 维度 1: 同义词扩展
        for key, syns in self._SYNONYMS.items():
            if key in base_keyword:
                variants.extend(syns[:2])
                break

        # 维度 2: 中英文切换
        if any('\u4e00' <= c <= '\u9fff' for c in base_keyword):
            # 中文关键词 → 加英文版
            for key, syns in self._SYNONYMS.items():
                if key in base_keyword:
                    en_variants = [s for s in syns if all(ord(c) < 128 for c in s)]
                    variants.extend(en_variants[:1])

        # 维度 3: 时间维度
        variants.append(f"{base_keyword} 2025")

        # 维度 4: 来源定向
        if any(c in base_keyword for c in ["财报", "financial", "年报"]):
            variants.append(f"{base_keyword} site:sec.gov")

        # 维度 5: 补充通用扩展确保 ≥3 变体
        if len(set(variants)) < 3:
            variants.append(f"{base_keyword} 分析")
            variants.append(f"{base_keyword} latest")

        # 去重, 保留 3-5 个
        seen = set()
        unique = []
        for v in variants:
            if v not in seen:
                seen.add(v)
                unique.append(v)
        return unique[:5]
