"""
TierClassifier — ResearchPro 三层质量排序
契约: cage/research_pro_v1.0.yaml (L3: source_registry.quality_tier, RED-DC-006)

Tier 1 (官方/学术) 来源必须优先于 Tier 3 (社区/论坛) (RED-DC-006)。
"""

import json
import os
from typing import Optional


# RED-DC-006: Tier 1 weight 1.0, Tier 3 weight 0.4
TIER_WEIGHTS = {
    "tier_1": 1.0,   # 官方/学术
    "tier_2": 0.7,   # 权威媒体
    "tier_3": 0.4,   # 社区/论坛
    "unverified": 0.5,
}


class TierClassifier:
    """
    三层质量排序分类器。

    契约约束:
    - Tier 1 (官方/学术) 权重 1.0 (RED-DC-006)
    - Tier 3 (社区/论坛) 权重 0.4 (RED-DC-006)
    - 未知域名默认 tier_2, 标记 unverified
    """

    def __init__(self, config_path: str = "") -> None:
        """
        初始化 TierClassifier。

        Args:
            config_path: tier_domains.json 路径 (可选, 默认内置)
        """
        self._domains: dict[str, str] = {}
        self._load_config(config_path)

    def _load_config(self, config_path: str) -> None:
        """加载域名分类配置。"""
        if config_path and os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
            for tier_key in ["tier_1", "tier_2", "tier_3"]:
                for domain in cfg.get(tier_key, {}).get("domains", []):
                    self._domains[domain] = tier_key
        else:
            # 内置默认分类
            self._domains = {
                # Tier 1: 官方/学术
                "sec.gov": "tier_1", "cninfo.com.cn": "tier_1",
                "sse.com.cn": "tier_1", "szse.cn": "tier_1",
                "gov.cn": "tier_1", "arxiv.org": "tier_1",
                "nature.com": "tier_1", "pbc.gov.cn": "tier_1",
                "stats.gov.cn": "tier_1", "who.int": "tier_1",
                # Tier 2: 权威媒体
                "reuters.com": "tier_2", "bloomberg.com": "tier_2",
                "ft.com": "tier_2", "finance.sina.com.cn": "tier_2",
                "caixin.com": "tier_2", "36kr.com": "tier_2",
                "bbc.com": "tier_2", "cnbc.com": "tier_2",
                "wallstreetcn.com": "tier_2", "cls.cn": "tier_2",
                # Tier 3: 社区/论坛
                "xueqiu.com": "tier_3", "reddit.com": "tier_3",
                "weibo.com": "tier_3", "zhihu.com": "tier_3",
                "eastmoney.com": "tier_3", "seekingalpha.com": "tier_3",
            }

    def classify(self, domain: str) -> str:
        """
        分类域名。

        Args:
            domain: 域名字符串

        Returns:
            str: tier_1 | tier_2 | tier_3 | unverified
        """
        # 精确匹配
        if domain in self._domains:
            return self._domains[domain]

        # 子域名匹配 (只匹配真正的子域名, 防止 CWE-697 子串攻击)
        # 例: finance.eastmoney.com → eastmoney.com ✓
        #     evil-eastmoney.com → 不匹配 ✗ (不同域名)
        parts = domain.split(".")
        if len(parts) >= 3:
            # 只检查直接父域名 (去掉第一个子域名部分)
            parent = ".".join(parts[1:])
            if parent in self._domains:
                return self._domains[parent]

        return "unverified"

    def get_weight(self, tier: str) -> float:
        """
        获取 Tier 权重。

        Args:
            tier: tier 名称

        Returns:
            float: 1.0 | 0.7 | 0.4
        """
        # RED-DC-006: tier_1 weight 1.0, tier_3 weight 0.4
        return TIER_WEIGHTS.get(tier, 0.5)
