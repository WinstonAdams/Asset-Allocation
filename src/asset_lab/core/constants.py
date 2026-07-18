"""業務常數——所有環境皆相同的固定規格，非機密，進版控。

機密值（Turso 憑證、OAuth 憑證、允許登入 email）一律走 st.secrets，
不在此定義（見設計 AD-7）。
"""

# ==== 原生（標準庫） ====
from dataclasses import dataclass

# ==== 第三方套件 ====
# 無

# ==== 專案內部 ====
# 無


# 年月鍵的字串格式；全程以 'YYYY-MM' 表示月份節點。
YEAR_MONTH_FORMAT = "%Y-%m"

# 「自最早記錄起」的區間下界 sentinel：早於任何真實年月，供 read_range 取全部歷史。
EARLIEST_YEAR_MONTH_SENTINEL = "0000-01"

# 報酬率區間與圖表所採用的時區（年初判定、近一年起點以此計）。
TIMEZONE = "Asia/Taipei"

# 再平衡偏離門檻預設值，以「百分點」計（現況% − 目標% 的絕對值超過此值即建議再平衡）。
DEFAULT_REBALANCE_THRESHOLD = 5.0

# 回撤基準的資料不足下限：累積 TWR 有效節點數低於此值即不判斷回撤深度，一律退回 L0。
PROTOCOL_MIN_DATA_MONTHS = 3

# docs/PROTOCOL.md 相對 repo 根的路徑；行為協定頁以此讀取全文唯讀渲染。
PROTOCOL_DOC_RELATIVE_PATH = "docs/PROTOCOL.md"


class HOLDING_KIND:
    """持有項目性質。資產計入配置與報酬率；負債僅計入淨值的負向。"""

    ASSET = "asset"
    LIABILITY = "liability"
    ALL = (ASSET, LIABILITY)


class ASSET_CATEGORIES:
    """資產分類受控清單初始值。負債不歸類（category 為 None）。"""

    TW_STOCK = "台股/台股ETF"
    US_STOCK = "美股/美股ETF"
    DEMAND_DEPOSIT = "活存"
    TIME_DEPOSIT = "定存"
    INSURANCE = "保險"
    ALL = (TW_STOCK, US_STOCK, DEMAND_DEPOSIT, TIME_DEPOSIT, INSURANCE)


class PERIOD_MODE:
    """報酬率計算的區間模式。"""

    INCEPTION = "inception"
    YTD = "ytd"
    LAST_12M = "last_12m"
    CUSTOM = "custom"
    ALL = (INCEPTION, YTD, LAST_12M, CUSTOM)


class PROTOCOL_LEVEL_CODE:
    """大跌行為協定等級代碼。L0 為平時姿態，L1–L3 依回撤深度遞增而愈趨保守。"""

    L0 = "L0"
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"
    ALL = (L0, L1, L2, L3)


class PROTOCOL_LEVEL_DEFAULTS:
    """回撤門檻預設值（正回撤幅度百分比）；使用者從未設定或缺某級時以此補齊。"""

    L1 = 10.0
    L2 = 20.0
    L3 = 30.0


class HOLDINGS_TABLE:
    """持有項目主檔資料表結構。"""

    TABLE_NAME = "holdings"
    HOLDING_ID = "holding_id"
    NAME = "name"
    KIND = "kind"
    CATEGORY = "category"
    INITIAL_MARKET_VALUE = "initial_market_value"
    INITIAL_COST = "initial_cost"
    CREATED_AT = "created_at"


class MONTHLY_RECORDS_TABLE:
    """項目 × 月份時間序列資料表結構。(holding_id, year_month) 為唯一鍵。"""

    TABLE_NAME = "monthly_records"
    HOLDING_ID = "holding_id"
    YEAR_MONTH = "year_month"
    MARKET_VALUE = "market_value"
    NET_INVESTMENT = "net_investment"


class TARGET_ALLOCATIONS_TABLE:
    """分類目標配置資料表結構。target_weight 以百分比（0–100）儲存。"""

    TABLE_NAME = "target_allocations"
    CATEGORY = "category"
    TARGET_WEIGHT = "target_weight"


class PROTOCOL_THRESHOLDS_TABLE:
    """回撤門檻設定資料表結構。level 為主鍵，drawdown_threshold 為正幅度百分比。"""

    TABLE_NAME = "protocol_thresholds"
    LEVEL = "level"
    DRAWDOWN_THRESHOLD = "drawdown_threshold"


@dataclass(frozen=True)
class ProtocolLevelSpec:
    """單一協定等級的展示規格（必做/禁止結構化編碼）。

    內容依 docs/PROTOCOL.md §1「情境分級與對應動作」表人工謄寫；兩處須人工同步，
    改動協定文本時須一併更新本表（已知維護點）。L0（平時）不在文件表格內，其必做/
    禁止依協定 §0 通則補上「照計畫、無特別禁止」的基準姿態，維持平時姿態的乾淨呈現，
    不帶任何大跌應對或行為防火牆提醒（那些只在真的偵測到回撤、進入 L1 以上時才有意義）。
    """

    code: str
    label: str
    band_text: str
    must_do: tuple[str, ...]
    must_not: tuple[str, ...]


# 行為防火牆通則（協定 §3）：只在真的判定進入 L1 以上（偵測到回撤）時才提醒，
# 平時（L0）不顯示，避免和「資料不足」的中性姿態混在一起、失去警示意義。
_BEHAVIOR_FIREWALL_REMINDER = "行為防火牆通則：只看本系統，不看券商 App"

# L0（平時）+ L1–L3 依 docs/PROTOCOL.md §1 表謄寫；供總覽頁查表呈現必做/禁止摘要。
PROTOCOL_LEVELS: tuple[ProtocolLevelSpec, ...] = (
    ProtocolLevelSpec(
        code=PROTOCOL_LEVEL_CODE.L0,
        label="平時",
        band_text="−10% 以內",
        must_do=("照計畫定期定額（依原訂投資計畫，不特別作為）",),
        must_not=("無特別禁止事項（平時姿態，維持既定計畫）",),
    ),
    ProtocolLevelSpec(
        code=PROTOCOL_LEVEL_CODE.L1,
        label="修正",
        band_text="−10% ~ −20%",
        must_do=("照常定期定額，什麼都不改",),
        must_not=(_BEHAVIOR_FIREWALL_REMINDER, "增加看盤頻率", "閱讀「崩盤將至」類內容"),
    ),
    ProtocolLevelSpec(
        code=PROTOCOL_LEVEL_CODE.L2,
        label="熊市",
        band_text="−20% ~ −30%",
        must_do=("照常定期定額", "若配置偏離目標超過 5 個百分點，執行再平衡"),
        must_not=(_BEHAVIOR_FIREWALL_REMINDER, "賣出任何部位", "修改目標配置", "與人爭論行情"),
    ),
    ProtocolLevelSpec(
        code=PROTOCOL_LEVEL_CODE.L3,
        label="深熊",
        band_text="−30% 以上",
        must_do=("照常定期定額", "啟動機動加碼（規則文字，見協定 §2）", "重讀本協定"),
        must_not=(
            _BEHAVIOR_FIREWALL_REMINDER,
            "賣出任何部位",
            "修改目標配置",
            "與人爭論行情",
            "72 小時內不做任何新決定",
        ),
    ),
)


class CSV_EXPORT:
    """CSV 匯出/匯入的對外欄位契約（含表頭標準 CSV，三類資料各一份）。

    欄位即各 model 的欄位、欄序固定；此為對外契約，發布後改欄位須維持相容。
    """

    HOLDINGS_COLUMNS = (
        "holding_id",
        "name",
        "kind",
        "category",
        "initial_market_value",
        "initial_cost",
    )
    RECORDS_COLUMNS = (
        "holding_id",
        "year_month",
        "market_value",
        "net_investment",
    )
    TARGETS_COLUMNS = (
        "category",
        "target_weight",
    )
