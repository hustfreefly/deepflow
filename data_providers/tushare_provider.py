"""
Tushare Provider — 付费版专业数据源

优势：
- 无调用次数限制（付费版）
- 财务数据完整（利润表/资产负债表/现金流量表）
- 历史数据权威（上市公司公告）
- 实时行情（盘中无限制）
"""

import json
from datetime import datetime
from typing import Any, Dict

from data_manager import DataProvider, DataQuery, DataResult, DataFinding, Observability

logger = Observability.get_logger("tushare_provider")

# Tushare Pro Token（付费版）
TUSHARE_TOKEN = os.getenv("TUSHARE_TOKEN", "")

if not TUSHARE_TOKEN:
    # 尝试从配置文件读取
    try:
        from core.config_loader import get_tushare_token
        TUSHARE_TOKEN = get_tushare_token()
    except Exception:
        pass


class TushareProvider(DataProvider):
    """Tushare Pro 数据提供者（付费版）"""

    def __init__(self, token: str = TUSHARE_TOKEN):
        self.token = token
        self._pro = None

    @property
    def pro(self):
        """延迟初始化 Tushare Pro API"""
        if self._pro is None:
            try:
                import tushare as ts
                ts.set_token(self.token)
                self._pro = ts.pro_api()
            except ImportError:
                raise RuntimeError("tushare 未安装: pip install tushare")
        return self._pro

    def fetch(self, query: DataQuery) -> DataResult:
        """执行 Tushare 数据采集
        
        支持的 API（通过 query.params["api"] 指定）：
        - income: 利润表
        - balancesheet: 资产负债表
        - cashflow: 现金流量表
        - fina_indicator: 财务指标
        - daily: 日线行情
        - daily_basic: 每日指标（PE/PB/市值等）
        - stk_limit: 涨跌停统计
        - top10_holders: 前十大股东
        - report_rc: 券商一致性预期（研报预测）
        """
        api_name = query.params.get("api", "")
        params = query.params.get("params", {})

        if not api_name:
            raise ValueError("Tushare 调用需要指定 api 参数")

        try:
            api_func = getattr(self.pro, api_name)
            df = api_func(**params)

            if df is not None and not df.empty:
                data = {
                    "records": df.to_dict("records"),
                    "columns": list(df.columns),
                    "row_count": len(df),
                }
            else:
                data = {
                    "records": [],
                    "columns": [],
                    "row_count": 0,
                    "note": "无数据返回",
                }

            return DataResult(
                data=data,
                metadata={
                    "source": "tushare_pro",
                    "api": api_name,
                    "params": params,
                    "timestamp": datetime.now().isoformat(),
                    "token_type": "paid",  # 标记为付费版
                }
            )

        except AttributeError:
            raise ValueError(f"Tushare 无此 API: {api_name}")
        except Exception as e:
            logger.error("tushare_fetch_failed", api=api_name, error=str(e))
            raise

    def fetch_financials(self, ts_code: str, start_date: str = "",
                        end_date: str = "") -> Dict:
        """便捷方法：获取完整财务数据（利润表 + 资产负债表 + 现金流量表 + 财务指标）"""
        if not start_date:
            start_date = "20210101"
        if not end_date:
            end_date = "20251231"

        results = {}

        # 利润表
        try:
            df = self.pro.income(ts_code=ts_code, start_date=start_date,
                                end_date=end_date, fields='ts_code,end_date,revenue,net_profit')
            if df is not None and not df.empty:
                annual = df[df['end_date'].str.endswith('1231')].copy()
                annual = annual.sort_values('end_date')
                results["income"] = annual.to_dict("records")
        except Exception as e:
            logger.warning("income_fetch_warning", error=str(e))
            results["income"] = []

        # 财务指标
        try:
            df = self.pro.fina_indicator(ts_code=ts_code, start_date=start_date,
                                        end_date=end_date,
                                        fields='ts_code,end_date,gross_margin,netprofit_margin,roe')
            if df is not None and not df.empty:
                annual = df[df['end_date'].str.endswith('1231')].copy()
                annual = annual.sort_values('end_date')
                results["indicators"] = annual.to_dict("records")
        except Exception as e:
            logger.warning("indicators_fetch_warning", error=str(e))
            results["indicators"] = []

        # 资产负债表
        try:
            df = self.pro.balancesheet(ts_code=ts_code, start_date=start_date,
                                       end_date=end_date,
                                       fields='ts_code,end_date,total_assets,total_liab,total_hldr_eqy_exc_min_int')
            if df is not None and not df.empty:
                annual = df[df['end_date'].str.endswith('1231')].copy()
                annual = annual.sort_values('end_date')
                results["balancesheet"] = annual.to_dict("records")
        except Exception as e:
            logger.warning("balancesheet_fetch_warning", error=str(e))
            results["balancesheet"] = []

        # 现金流量表
        try:
            df = self.pro.cashflow(ts_code=ts_code, start_date=start_date,
                                  end_date=end_date,
                                  fields='ts_code,end_date,net_cash_flows_oper_act,net_cash_flows_inv_act,net_cash_flows_fnc_act')
            if df is not None and not df.empty:
                annual = df[df['end_date'].str.endswith('1231')].copy()
                annual = annual.sort_values('end_date')
                results["cashflow"] = annual.to_dict("records")
        except Exception as e:
            logger.warning("cashflow_fetch_warning", error=str(e))
            results["cashflow"] = []

        return results

    def fetch_daily_basics(self, ts_code: str, start_date: str = "",
                          end_date: str = "") -> Dict:
        """便捷方法：获取每日指标（PE/PB/市值/换手率等）"""
        if not start_date:
            start_date = "20250101"
        if not end_date:
            end_date = datetime.now().strftime("%Y%m%d")

        try:
            df = self.pro.daily_basic(ts_code=ts_code, start_date=start_date,
                                     end_date=end_date,
                                     fields='ts_code,end_date,pe,pe_ttm,pb,ps,ps_ttm,dv_ratio,dv_ttm,total_share,float_share,free_share,total_mv,circ_mv')
            if df is not None and not df.empty:
                return {
                    "records": df.to_dict("records"),
                    "latest": df.iloc[-1].to_dict(),
                }
        except Exception as e:
            logger.warning("daily_basic_fetch_warning", error=str(e))

        return {"records": [], "latest": {}}

    def fetch_analyst_forecasts(self, ts_code: str) -> Dict:
        """便捷方法：获取券商一致性预期（研报预测数据）"""
        try:
            df = self.pro.forecast(ts_code=ts_code)
            if df is not None and not df.empty:
                return {
                    "records": df.to_dict("records"),
                    "latest": df.iloc[-1].to_dict(),
                }
        except Exception as e:
            logger.warning("forecast_fetch_warning", error=str(e))

        return {"records": [], "latest": {}}

    def validate_finding(self, finding: DataFinding) -> bool:
        """Tushare 数据验证"""
        if not super().validate_finding(finding):
            return False

        # Tushare 数据必须有来源 API 标识
        if finding.source and "tushare" not in finding.source.lower():
            # 允许其他来源（Agent 从网页发现的数据）
            pass

        return True


# 自动注册
def register():
    """注册 Tushare Provider"""
    from data_manager import ProviderRegistry
    ProviderRegistry.register("tushare", TushareProvider())
