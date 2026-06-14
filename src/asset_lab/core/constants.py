"""業務常數——所有環境皆相同的固定規格，非機密，進版控。

機密值（Turso 憑證、OAuth 憑證、允許登入 email）一律走 st.secrets，
不在此定義（見設計 AD-7）。
"""

# ==== 原生（標準庫） ====
# 無

# ==== 第三方套件 ====
# 無

# ==== 專案內部 ====
# 無


# 年月鍵的字串格式；全程以 'YYYY-MM' 表示月份節點。
YEAR_MONTH_FORMAT = "%Y-%m"

# 報酬率區間與圖表所採用的時區（年初判定、近一年起點以此計）。
TIMEZONE = "Asia/Taipei"

# 再平衡偏離門檻預設值，以「百分點」計（現況% − 目標% 的絕對值超過此值即建議再平衡）。
DEFAULT_REBALANCE_THRESHOLD = 5.0


class HOLDING_KIND:
    """持有項目性質。資產計入配置與報酬率；負債僅計入淨值的負向。"""

    ASSET = "asset"
    LIABILITY = "liability"
    ALL = (ASSET, LIABILITY)


class ASSET_CATEGORIES:
    """資產分類受控清單初始值。負債不歸類（category 為 None）。"""

    TW_STOCK = "台股/台股ETF"
    US_STOCK = "美股/美股ETF"
    CASH = "現金/定存"
    INSURANCE = "保險"
    ALL = (TW_STOCK, US_STOCK, CASH, INSURANCE)


class PERIOD_MODE:
    """報酬率計算的區間模式。"""

    INCEPTION = "inception"
    YTD = "ytd"
    LAST_12M = "last_12m"
    CUSTOM = "custom"
    ALL = (INCEPTION, YTD, LAST_12M, CUSTOM)


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
