"""
Investment Data Providers — 投资领域数据提供者

实现：
- AKShareProvider（财务数据、行业数据）
- SinaProvider（实时行情）
- WebFetchProvider（研报、新闻、网页数据）
"""

import json
import time
from datetime import datetime
from typing import Any, Dict

from core.data_manager import DataProvider, DataQuery, DataResult, DataFinding, Observability

logger = Observability.get_logger("investment_providers")


# ============================================================
# AKShare Provider — 财务数据
# ============================================================

class AKShareProvider(DataProvider):
    """AKShare 数据提供者（财务指标、行业数据）"""

    def fetch(self, query: DataQuery) -> DataResult:
        api = query.params.get("api", "")
        params = query.params.get("params", {})

        try:
            import akshare as ak

            if api == "stock_financial_analysis_indicator":
                data = self._fetch_financials(params.get("symbol", ""))
            elif api == "stock_individual_info_em":
                data = self._fetch_company_info(params.get("symbol", ""))
            elif api == "stock_zh_a_spot_em":
                data = self._fetch_market_overview()
            else:
                raise ValueError(f"未知 AKShare API: {api}")

            return DataResult(
                data=data,
                metadata={
                    "source": "akshare",
                    "api": api,
                    "timestamp": datetime.now().isoformat(),
                }
            )
        except ImportError:
            raise RuntimeError("akshare 未安装: pip install akshare")
        except Exception as e:
            logger.error("akshare_fetch_failed", api=api, error=str(e))
            raise

    def _fetch_financials(self, symbol: str) -> Dict:
        """获取财务指标"""
        try:
            import akshare as ak
            # 财务分析指标
            df = ak.stock_financial_analysis_indicator(symbol=symbol)
            if df is not None and not df.empty:
                return {
                    "annual_data": df.head(10).to_dict("records"),
                    "latest": df.iloc[0].to_dict() if not df.empty else {},
                }
        except Exception as e:
            logger.warning("financials_fetch_warning", error=str(e))

        return {"annual_data": [], "latest": {}}

    def _fetch_company_info(self, symbol: str) -> Dict:
        """获取公司基本信息"""
        try:
            import akshare as ak
            df = ak.stock_individual_info_em(symbol=symbol)
            if df is not None:
                return dict(zip(df["item"], df["value"]))
        except Exception as e:
            logger.warning("company_info_fetch_warning", error=str(e))

        return {}

    def _fetch_market_overview(self) -> Dict:
        """获取市场行情概览"""
        try:
            import akshare as ak
            df = ak.stock_zh_a_spot_em()
            if df is not None and not df.empty:
                return {
                    "total_stocks": len(df),
                    "top_gainers": df.nlargest(5, "涨跌幅")[["名称", "代码", "涨跌幅"]].to_dict("records"),
                }
        except Exception as e:
            logger.warning("market_overview_warning", error=str(e))

        return {}

    def validate_finding(self, finding: DataFinding) -> bool:
        """投资领域数据验证"""
        if not super().validate_finding(finding):
            return False

        # 数值合理性检查
        if finding.data_type == "financial_comparison":
            value = finding.value
            if isinstance(value, dict):
                for key, val in value.items():
                    if "毛利率" in key or "净利率" in key:
                        try:
                            pct = float(str(val).replace("%", ""))
                            if pct < 0 or pct > 100:
                                return False
                        except (ValueError, TypeError):
                            pass

        return True


# ============================================================
# Sina Provider — 实时行情
# ============================================================

class SinaProvider(DataProvider):
    """新浪财经实时行情提供者"""

    def fetch(self, query: DataQuery) -> DataResult:
        symbol = query.params.get("symbol", "")
        if not symbol:
            raise ValueError("缺少 symbol 参数")

        # 转换代码格式（300604.SZ → sz300604）
        parts = symbol.split(".")
        if len(parts) == 2:
            code_num = parts[0]
            exchange = parts[1].lower()
            sina_symbol = f"{exchange}{code_num}"
        else:
            sina_symbol = symbol

        url = f"https://hq.sinajs.cn/list={sina_symbol}"
        headers = {
            "Referer": "https://finance.sina.com.cn",
            "User-Agent": "Mozilla/5.0",
        }

        try:
            import urllib.request
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as resp:
                data_str = resp.read().decode("gbk")

            if sina_symbol in data_str:
                parts = data_str.split('"')[1].split(",")
                if len(parts) > 30:
                    quote = {
                        "name": parts[0],
                        "open": float(parts[1]),
                        "prev_close": float(parts[2]),
                        "current": float(parts[3]),
                        "high": float(parts[4]),
                        "low": float(parts[5]),
                        "volume": float(parts[8]),
                        "amount": float(parts[9]),
                        "timestamp": f"{parts[30]} {parts[31]}",
                    }
                    return DataResult(
                        data={"quote": quote},
                        metadata={
                            "source": "sina_finance",
                            "timestamp": datetime.now().isoformat(),
                        }
                    )
        except Exception as e:
            logger.warning("sina_quote_warning", symbol=symbol, error=str(e))

        return DataResult(
            data={"quote": {}},
            metadata={"source": "sina_finance", "error": "fetch_failed"}
        )


# ============================================================
# WebFetch Provider — 网页数据
# ============================================================

class WebFetchProvider(DataProvider):
    """网页数据采集提供者"""

    def fetch(self, query: DataQuery) -> DataResult:
        url = query.params.get("url", "")
        search_query = query.params.get("search_query", "")
        source_type = query.params.get("type", "general")

        if url:
            data = self._fetch_url(url, source_type)
        elif search_query:
            data = self._search_and_fetch(search_query)
        else:
            raise ValueError("WebFetch 需要 url 或 search_query")

        return DataResult(
            data=data,
            metadata={
                "source": "web_fetch",
                "url": url or search_query,
                "timestamp": datetime.now().isoformat(),
            }
        )

    def _fetch_url(self, url: str, source_type: str) -> Dict:
        """抓取单个 URL"""
        try:
            import urllib.request
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                content = resp.read().decode("utf-8", errors="replace")

            # 提取文本内容（简化版 HTML 清理）
            import re
            text = re.sub(r'<[^>]+>', ' ', content)
            text = re.sub(r'\s+', ' ', text).strip()

            return {
                "url": url,
                "type": source_type,
                "content_preview": text[:2000],
                "content_length": len(text),
            }
        except Exception as e:
            logger.warning("web_fetch_warning", url=url, error=str(e))
            return {"url": url, "error": str(e)}

    def _search_and_fetch(self, query: str) -> Dict:
        """搜索并抓取结果"""
        # 简化实现：返回搜索查询，实际搜索需要更复杂的爬虫
        return {
            "search_query": query,
            "note": "搜索功能需要额外实现",
        }

    def validate_finding(self, finding: DataFinding) -> bool:
        """网页数据验证：检查 URL 格式"""
        if not super().validate_finding(finding):
            return False

        if finding.source and finding.source.startswith("http"):
            return True

        return False


# ============================================================
# Provider 自动注册
# ============================================================

def register_providers():
    """注册所有投资领域 Provider"""
    from core.data_manager import ProviderRegistry

    ProviderRegistry.register("akshare", AKShareProvider())
    ProviderRegistry.register("sina_finance", SinaProvider())
    ProviderRegistry.register("web_fetch", WebFetchProvider())

    # Tushare Pro（付费版，无调用限制）
    try:
        from data_providers.tushare_provider import TushareProvider
        ProviderRegistry.register("tushare", TushareProvider())
    except ImportError:
        pass  # tushare 未安装时跳过
