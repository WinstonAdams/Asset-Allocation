"""月度紀錄模型。"""

# ==== 原生（標準庫） ====

# ==== 第三方套件 ====
from pydantic import BaseModel

# ==== 專案內部 ====
# 無


class MonthlyRecordModel(BaseModel):
    """(holding_id, year_month) 月度紀錄。

    資產的 market_value 為市值，負債為餘額（同欄依 kind 解讀）。
    賣出當月記市值 0、淨投入為負提領金額；之後月份省略該項目列（缺列＝已不持有）。
    net_investment 正為投入、負為提領；負債不使用此欄。

    total_cost 不為 None 即為新制股票/ETF 列，其 net_investment 為推算值；
    None 代表非股票/ETF 分類，或本功能上線前建立的舊制列。realized_income
    隨 total_cost 同時填寫，新制列一律有值（預設 0）。
    """

    holding_id: int
    year_month: str
    market_value: float | None = None
    net_investment: float = 0.0
    total_cost: float | None = None
    realized_income: float | None = None
