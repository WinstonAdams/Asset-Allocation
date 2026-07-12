"""大跌行為協定的等級判定服務。

本服務為純運算，不碰 I/O、不依賴 Streamlit。回撤基準取整體資產的累積 TWR 成長
指數：把每個有資料月的累積 TWR 換算成成長倍數，並在路徑最前端補上建倉基準點
（指數 1.0），讓「只跌不漲」的投組仍以建倉點為歷史高點量測回撤，不致低報跌幅。
資料量不足時一律退回 L0 平時姿態、不計回撤深度，避免早期少數月雜訊被誤判成大跌。
"""

# ==== 原生（標準庫） ====
# 無

# ==== 第三方套件 ====
# 無

# ==== 專案內部 ====
from asset_lab.core.constants import PROTOCOL_LEVEL_CODE
from asset_lab.models.protocol import ProtocolThresholds
from asset_lab.models.results import CumulativeTwrPoint, ProtocolStatus

# 建倉基準點：起始月尚無報酬，成長指數以 1.0 起算，構成歷史高點路徑的起點。
_INCEPTION_INDEX = 1.0

# 回撤深度四捨五入位數：累積 TWR 連乘會帶入極小浮點誤差，若「恰等於門檻」的深度
# 因誤差變成剛好差一絲未達標，會讓「達門檻即進入較深級」的邊界約定失效；此精度
# 遠高於任何有意義的業務差異，僅用來吸收浮點運算噪音。
_DRAWDOWN_ROUND_DIGITS = 6

# 資料充足度旗標。
_STATUS_NO_DATA = "no_data"
_STATUS_INSUFFICIENT_DATA = "insufficient_data"
_STATUS_OK = "ok"


class ProtocolService:
    """回撤基準計算與協定等級判定。建構子無依賴（純運算）。"""

    def __init__(self) -> None:
        """初始化協定服務。本服務無外部依賴，僅做數值運算。"""

    def assess(
        self,
        *,
        series: list[CumulativeTwrPoint],
        thresholds: ProtocolThresholds,
        min_data_months: int,
    ) -> ProtocolStatus:
        """依累積 TWR 序列判定目前的協定等級。

        以整體累積 TWR 建立成長指數路徑（起始基準 1.0 加上各節點的 1+累積TWR），
        歷史高點取路徑最大值、目前回撤＝最新一點相對歷史高點的跌幅。有效節點數
        （series 長度）低於 min_data_months 時，回撤深度尚不可信，一律退回 L0
        且不計回撤深度，避免早期少數月的雜訊觸發誤判；節點數為 0（尚無任何紀錄）
        與「有資料但不足」以不同 status 區分，供上層呈現對應的中性文案。

        Args:
            series: 逐有資料月的整體累積 TWR 序列，依月份遞增排序、僅計資產。
            thresholds: 三級回撤門檻（正回撤幅度百分比，應嚴格遞增）。
            min_data_months: 判定回撤深度所需的最低有效節點數。

        Returns:
            ProtocolStatus，含判定等級、資料充足度旗標與回撤/累積 TWR 數值。
        """
        data_month_count = len(series)
        current_cumulative_twr = series[-1].cumulative_twr if series else None

        if data_month_count == 0:
            return ProtocolStatus(
                level_code=PROTOCOL_LEVEL_CODE.L0,
                status=_STATUS_NO_DATA,
                drawdown=None,
                current_cumulative_twr=None,
                data_month_count=0,
            )
        if data_month_count < min_data_months:
            return ProtocolStatus(
                level_code=PROTOCOL_LEVEL_CODE.L0,
                status=_STATUS_INSUFFICIENT_DATA,
                drawdown=None,
                current_cumulative_twr=current_cumulative_twr,
                data_month_count=data_month_count,
            )

        drawdown = self._current_drawdown(series)
        return ProtocolStatus(
            level_code=self._level_for(drawdown=drawdown, thresholds=thresholds),
            status=_STATUS_OK,
            drawdown=drawdown,
            current_cumulative_twr=current_cumulative_twr,
            data_month_count=data_month_count,
        )

    @staticmethod
    def _current_drawdown(series: list[CumulativeTwrPoint]) -> float:
        """由累積 TWR 序列算出目前自歷史高點的回撤（≤0 小數）。

        成長指數路徑 = [建倉基準 1.0] + [各節點 1+累積TWR]；歷史高點取路徑最大值
        （含建倉基準，避免「只跌不漲」的投組把第一個已下跌月誤當高點、低報跌幅）；
        目前回撤＝路徑最新一點相對歷史高點的跌幅。
        """
        index_path = [_INCEPTION_INDEX, *(1 + point.cumulative_twr for point in series)]
        peak = max(index_path)
        current = index_path[-1]
        return round(current / peak - 1, _DRAWDOWN_ROUND_DIGITS)

    @staticmethod
    def _level_for(*, drawdown: float, thresholds: ProtocolThresholds) -> str:
        """依回撤深度（正百分比）對應四級，深度恰等於門檻時歸入較深一級。"""
        depth = -drawdown * 100
        if depth >= thresholds.l3:
            return PROTOCOL_LEVEL_CODE.L3
        if depth >= thresholds.l2:
            return PROTOCOL_LEVEL_CODE.L2
        if depth >= thresholds.l1:
            return PROTOCOL_LEVEL_CODE.L1
        return PROTOCOL_LEVEL_CODE.L0
