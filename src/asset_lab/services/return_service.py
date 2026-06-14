"""報酬率計算服務。

本服務為純運算，不碰 I/O、不依賴 Streamlit。報酬率分三條互不汙染的口徑：
時間加權報酬率（TWR）以「初始市值」起算記錄後績效；賺賠金額與簡單總報酬率
以「初始成本」起算、含記錄前歷史。兩者的初始基準必須隔離——記錄前的價差只屬於
賺賠口徑，不可被算成 TWR 的第一期報酬，故各管線的函式簽名只接受自身基準參數，
從介面上杜絕混用。

月度序列以「有資料的月份」為節點，相鄰兩個有資料月之間視為一段期間；整月缺漏
直接跳過、不補插值，避免非真實節點稀釋真實期間報酬。
"""

# ==== 原生（標準庫） ====
# 無

# ==== 第三方套件 ====
import pandas as pd

# ==== 專案內部 ====
from asset_lab.core.constants import MONTHLY_RECORDS_TABLE


class ReturnService:
    """報酬率三口徑計算。建構子無依賴（純運算）。"""

    def __init__(self) -> None:
        """初始化報酬率服務。本服務無外部依賴，僅做數值運算。"""

    def compute_twr(self, *, monthly: pd.DataFrame, initial_market_value: float) -> float | None:
        """計算區間時間加權報酬率（TWR），逐段連乘且排除當月淨投入。

        以「初始市值」為首段期初，依時間排序後相鄰兩個有資料月為一段期間，
        每段報酬 =（期末市值 − 當月淨投入 − 期初市值）÷ 期初市值，逐段連乘後減一。
        當月淨投入視為月底發生，不賺取當月報酬，故須自期末市值扣除。
        期初市值為 0 的建倉月會造成除以 0，該段不納入連乘，自下一個期初大於 0 的
        期間起算。留空（None）的市值沿用上一個有值月份（見 _value_series）。
        若無任何有效連乘段（序列為空、僅建倉月、所有期初皆為 0），回傳 None。

        Args:
            monthly: 月度序列 DataFrame，含 year_month、market_value、net_investment 欄；
                僅含有資料月，market_value 可為 None 表當月留空。
            initial_market_value: 首段期初市值，即記錄起點的市值基準。

        Returns:
            區間 TWR（百分比小數，如 0.331 表 33.1%）；無有效連乘段時為 None。
        """
        values, net_investments = self._value_series(monthly)

        opening = initial_market_value
        cumulative = 1.0
        has_segment = False
        for end_value, net_investment in zip(values, net_investments, strict=True):
            if end_value is None:
                # 留空且無前值可沿用：無法形成有效期末，跳過此段並維持期初基準
                continue
            if opening != 0:
                cumulative *= (end_value - net_investment) / opening
                has_segment = True
            # 期初為 0 的建倉段不納入連乘，但其期末市值成為下一段的期初
            opening = end_value

        if not has_segment:
            return None
        return cumulative - 1.0

    def compute_pnl(
        self, *, monthly: pd.DataFrame, initial_cost: float
    ) -> tuple[float | None, float | None]:
        """計算賺賠金額與簡單總報酬率，以累積成本起算。

        累積成本 = 初始成本 + 後續各月淨投入合計；賺賠金額 = 當前市值 − 累積成本；
        簡單總報酬率 = 賺賠 ÷ 累積成本。初始成本含記錄前的歷史價差，與 TWR 起算的
        初始市值刻意分離。當前市值取最後一個有值月份（留空月沿用前值）。
        累積成本為 0 時簡單總報酬率無意義，回傳 None（賺賠金額仍可呈現）。

        Args:
            monthly: 月度序列 DataFrame，含 year_month、market_value、net_investment 欄；
                僅含有資料月，market_value 可為 None 表當月留空。
            initial_cost: 累積成本的起算基準，含記錄前已投入的歷史成本。

        Returns:
            (賺賠金額, 簡單總報酬率) 二元組；無有值月份時賺賠為 None，
            累積成本為 0 時簡單總報酬率為 None。
        """
        values, net_investments = self._value_series(monthly)

        cumulative_cost = initial_cost + sum(net_investments)
        current_value = next((value for value in reversed(values) if value is not None), None)
        if current_value is None:
            return None, None

        pnl = current_value - cumulative_cost
        simple_return = None if cumulative_cost == 0 else pnl / cumulative_cost
        return pnl, simple_return

    @staticmethod
    def _value_series(monthly: pd.DataFrame) -> tuple[list[float | None], list[float]]:
        """將月度序列依時間排序，並對留空市值沿用上一個有值月份。

        以有資料的月份為節點依 year_month 排序；某月仍在清單但市值留空（None）
        代表仍持有、當月未更新，沿用上一個有值月份的市值，且不視為當月有變動。
        首個有值月份之前若有留空（無前值可沿用）則維持 None。

        Args:
            monthly: 月度序列 DataFrame，含 year_month、market_value、net_investment 欄。

        Returns:
            (沿用後的市值清單, 淨投入清單)，兩者皆依時間排序、長度一致。
        """
        if monthly.empty:
            return [], []

        ordered = monthly.sort_values(MONTHLY_RECORDS_TABLE.YEAR_MONTH)
        values: list[float | None] = []
        net_investments: list[float] = []
        last_valued: float | None = None
        for _, row in ordered.iterrows():
            raw_value = row[MONTHLY_RECORDS_TABLE.MARKET_VALUE]
            if raw_value is None or pd.isna(raw_value):
                values.append(last_valued)
            else:
                last_valued = float(raw_value)
                values.append(last_valued)
            net_investments.append(float(row[MONTHLY_RECORDS_TABLE.NET_INVESTMENT]))
        return values, net_investments
