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


class HOLDING_PURPOSE:
    """持有項目用途。純附加標記，既有分類/報酬/配置計算完全不讀此欄（D14），
    只供買房功能（bucket 推導、現金保留計算）讀取。"""

    GENERAL = "general"
    HOUSE = "house"
    ALL = (GENERAL, HOUSE)


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
    PURPOSE = "purpose"


class MONTHLY_RECORDS_TABLE:
    """項目 × 月份時間序列資料表結構。(holding_id, year_month) 為唯一鍵。

    total_cost/realized_income 為成本鏈推算功能附加欄位，可為 NULL，語意依分類而定：
    total_cost 股票/ETF＝目前總成本、保險＝累計已繳保費；不為 NULL 即為新制成本鏈列，
    其 net_investment 為推算值；NULL 代表其他分類，或本功能上線前建立的舊制列。
    realized_income 股票/ETF＝「已實現損益＋現金股利」的合計、保險＝本月領回金額；
    cash_dividend 為其中的現金股利，NULL（非股票/ETF 列、舊制列、或本功能上線前的新制列）
    視為 0，其合計全數視為已實現損益。
    market_value 資產＝市值（活存/定存＝餘額、保險＝解約金、股票＝現值）；負債＝應繳金額。
    """

    TABLE_NAME = "monthly_records"
    HOLDING_ID = "holding_id"
    YEAR_MONTH = "year_month"
    MARKET_VALUE = "market_value"
    NET_INVESTMENT = "net_investment"
    TOTAL_COST = "total_cost"
    REALIZED_INCOME = "realized_income"
    CASH_DIVIDEND = "cash_dividend"


class COST_BASIS_INPUT:
    """依總成本＋已實現收益推算月淨投入的資產分類（股票/ETF）。"""

    CATEGORIES = frozenset({ASSET_CATEGORIES.TW_STOCK, ASSET_CATEGORIES.US_STOCK})


class PREMIUM_INPUT:
    """以「累計已繳保費＋本月領回」推算月淨投入的資產分類。由 bootstrap 注入 CostBasisService。"""

    CATEGORIES = frozenset({ASSET_CATEGORIES.INSURANCE})


class BALANCE_INPUT:
    """以「本月餘額 − 前期餘額」推算月淨投入的資產分類。由 bootstrap 注入 BalanceInputService。"""

    CATEGORIES = frozenset({ASSET_CATEGORIES.DEMAND_DEPOSIT, ASSET_CATEGORIES.TIME_DEPOSIT})


class INPUT_MODE:
    """月度錄入方式代碼：決定錄入欄位與當月淨投入的來源。

    BY_ASSET_CATEGORY 由三個 *_INPUT.CATEGORIES 組出（三個集合是唯一資料來源）；
    負債不查表，一律為 AMOUNT_DUE。本類別須定義在三個 *_INPUT 類別之後。
    """

    COST_BASIS = "cost_basis"  # 股票/ETF：總成本＋現值＋已實現損益＋現金股利
    PREMIUM = "premium"  # 保險：累計已繳保費＋解約金＋本月領回金額
    BALANCE = "balance"  # 活存/定存：只填餘額
    AMOUNT_DUE = "amount_due"  # 負債：只填應繳金額，淨投入固定 0
    BY_ASSET_CATEGORY = {
        **dict.fromkeys(COST_BASIS_INPUT.CATEGORIES, COST_BASIS),
        **dict.fromkeys(PREMIUM_INPUT.CATEGORIES, PREMIUM),
        **dict.fromkeys(BALANCE_INPUT.CATEGORIES, BALANCE),
    }


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


class HOUSE_PARAM_KEY:
    """買房政策與個人化參數鍵（house_params 表 param_key 值域）。

    個人化參數（金額/收入/時點）攸關使用者實際財務狀況；政策方法論比率
    （自備比率/月付上限比率/驗算利率/貸款年限）為財務規劃通則，非個人化資訊，
    可保留具體預設值（見 HOUSE_PARAM_DEFAULTS）。
    """

    TARGET_TOTAL_PRICE = "target_total_price"
    TARGET_YEAR = "target_year"
    MONTHLY_AFTER_TAX_INCOME = "monthly_after_tax_income"
    INCOME_THRESHOLD = "income_threshold"
    CASH_FLOOR = "cash_floor"
    DOWN_PAYMENT_RATIO = "down_payment_ratio"
    PAYMENT_CAP_RATIO = "payment_cap_ratio"
    TEST_ANNUAL_RATE = "test_annual_rate"
    LOAN_YEARS = "loan_years"


class HOUSE_PARAM_DEFAULTS:
    """effective_params 缺鍵時的中性補值。

    個人化參數（金額/收入/時點）一律為 0，代表「尚未設定」的中性姿態，不洩漏
    任何真實財務數字；政策方法論比率為財務規劃通則預設值，非個人化資訊。
    """

    TARGET_TOTAL_PRICE = 0.0
    TARGET_YEAR = 0
    MONTHLY_AFTER_TAX_INCOME = 0.0
    INCOME_THRESHOLD = 0.0
    CASH_FLOOR = 0.0
    DOWN_PAYMENT_RATIO = 33.0
    PAYMENT_CAP_RATIO = 35.0
    TEST_ANNUAL_RATE = 2.5
    LOAN_YEARS = 30


class HOUSE_TRIGGER:
    """買房觸發條件鍵。定錨與認知為使用者手動勾選的主觀條件；其餘三條為客觀自動判定。"""

    ANCHOR = "anchor"
    INCOME = "income"
    DOWN_PAYMENT = "down_payment"
    PAYMENT = "payment"
    COGNITION = "cognition"
    ALL = (ANCHOR, INCOME, DOWN_PAYMENT, PAYMENT, COGNITION)
    SUBJECTIVE = (ANCHOR, COGNITION)


class HOUSE_PARAMS_TABLE:
    """買房參數設定資料表結構。param_key 為主鍵，param_value 統一以 REAL 儲存。"""

    TABLE_NAME = "house_params"
    PARAM_KEY = "param_key"
    PARAM_VALUE = "param_value"


class SUBJECTIVE_TRIGGERS_TABLE:
    """主觀觸發勾選狀態資料表結構。trigger_key 為主鍵，checked 以 0/1 儲存。"""

    TABLE_NAME = "subjective_triggers"
    TRIGGER_KEY = "trigger_key"
    CHECKED = "checked"


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
    HOLDINGS_COLUMNS 末端附加 purpose（純附加，既有欄序不變）；HOLDINGS_REQUIRED_COLUMNS
    為匯入表頭驗證的強制欄位集，不含 purpose——舊版 CSV 缺此欄仍能通過表頭驗證並匯入，
    缺欄視為未填、補一般（向後相容）。RECORDS_COLUMNS 同理末端附加 total_cost、
    realized_income、cash_dividend；RECORDS_REQUIRED_COLUMNS 固定為前 4 欄，不含這三欄，
    舊版 CSV（4 欄或僅 6 欄）缺欄仍可匯入，缺欄視為未填（還原為 None）。
    total_cost、realized_income 的語意依分類而定：股票/ETF 為總成本與已實現收益合計，
    保險為累計已繳保費與本月領回金額（欄位本身不變，語意見 MONTHLY_RECORDS_TABLE）。
    """

    HOLDINGS_COLUMNS = (
        "holding_id",
        "name",
        "kind",
        "category",
        "initial_market_value",
        "initial_cost",
        "purpose",
    )
    HOLDINGS_REQUIRED_COLUMNS = HOLDINGS_COLUMNS[:-1]
    RECORDS_COLUMNS = (
        "holding_id",
        "year_month",
        "market_value",
        "net_investment",
        "total_cost",
        "realized_income",
        "cash_dividend",
    )
    RECORDS_REQUIRED_COLUMNS = RECORDS_COLUMNS[:4]
    TARGETS_COLUMNS = (
        "category",
        "target_weight",
    )


class APP_LOGGING:
    """App 的 log 設定。專案沒有 config.yml，運維參數集中於此。"""

    LOGGER_NAMESPACE = "asset_lab"  # 專案 logger 共同前綴；頁面 logger 皆掛在其下
    LEVEL = "INFO"
    FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


class RERUN_KIND:
    """重跑量測 log 的重跑類型。"""

    FULL = "full"
    FRAGMENT = "fragment"
