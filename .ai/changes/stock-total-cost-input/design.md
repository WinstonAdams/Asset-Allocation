# 設計文件：stock-total-cost-input（股票/ETF 改填總成本＋金額輸入框放大與千分位）

> 本文件只談技術：架構決策（ADR）和介面契約，不寫業務行為（沒有 GIVEN/WHEN/THEN）。
> **對應的 Scenarios 由後續 1-3 行為規格化（scenario-author）產出**；本文件用 BR 編號引用 `proposal.md` 的業務規則。
> 參考來源：`proposal.md`（BR-1~BR-10）。1-2a 技術選型、1-2b 架構分析都已跳過（progress 有記），所以沒有 tech-research.md 和 architecture-brief.md；既有架構慣例直接沿用 `.ai/archive/initial-build/design.md` 與 `.ai/archive/house-dashboard/design.md`。
> 本 workspace **沒有 `utils_v2/`**（已確認目錄不存在），02-architecture §7 與 04-cross-cutting 的 utils_v2/structlog/biz_job 都不適用；logging 與錯誤處理照 initial-build AD-8（標準 `logging`、Page 層是唯一 catch 點）。

---

## 現況評估

既有 asset-lab 分四層：`views/*.py`（View/Controller，檔尾無條件呼叫 `render()`）→ `services/*`（純運算，或注入 Repo 只做讀取）→ `repositories/*`（單表 I/O，連線由 bootstrap 注入）→ `models/*`（Pydantic 純資料），外加 `core/`（constants/utils/exceptions/access）。DI 由 `bootstrap.build_container` 用 keyword args 組成 `Container`，Page 從 `st.session_state["container"]` 取用。

本 Change 直接沿用的既有慣例：

| 既有模式 | 位置 | 本 Change 怎麼沿用 |
|---------|------|------------------|
| 加欄用 idempotent 遷移（PRAGMA 探測，缺欄才 ALTER） | `SchemaRepository._ensure_holdings_purpose_column`（house-dashboard AD-6） | `monthly_records` 加 `total_cost`、`realized_income` 兩欄；探測邏輯抽成通用私有 helper 兩處共用（AD-2） |
| CSV 對外契約附加欄位＋向後相容匯入 | `CSV_EXPORT.HOLDINGS_COLUMNS` / `HOLDINGS_REQUIRED_COLUMNS`（house-dashboard AD-8） | records 契約附加兩欄，強制欄位集維持原本 4 欄（AD-9） |
| 純運算 Service（無 I/O、無 Streamlit），由 Page 編排，Service 之間不互相注入 | `HouseService` / `AffordabilityService`（house-dashboard AD-3） | 新增 `CostBasisService`（AD-3） |
| 多列寫入：多次 execute 後單一 commit | `RecordRepository.replace_all` | 新增 compound 寫入方法（AD-5），另補失敗時 rollback |
| 表單 `on_change` 回呼同步 session_state | `views/settings.py::_sync_cost_to_market_value`（SC-051） | 金額框的千分位正規化也走 `on_change`，並能串接既有同步回呼（AD-7） |
| 下游只讀 `net_investment` 欄（TWR/MWR/P&L/配置/淨值/協定） | `ReturnService` 等，一律用具名欄位存取 DataFrame | 推算值直接寫進 `net_investment`，下游不用改（AD-1） |

偏離既有做法的地方（各有 ADR）：
- **金額輸入元件從 `st.number_input` 改成 `st.text_input`**（AD-7）：`number_input` 的 `format` 只接受純數字輸出（Streamlit 1.59 docstring：*"The output must be purely numeric"*），顯示不了千分位。這是 UI 機制層的替換，會帶動既有 UI 機制測試做機械式改寫（見〈受影響的既有 SC 與測試〉）。
- **新增一個會 import streamlit 的 UI 元件模組 `src/asset_lab/amount_widget.py`**：前例是 `bootstrap.py`（同樣位於 `src/asset_lab/`、同樣 import streamlit）。Service/Repository 仍然不 import streamlit。
- **新增 Service 的業務參數一律用建構子注入**（`cost_basis_categories`）：專案裡有些既有 Service 會在方法內直接讀 constants 值（例如 `DataIoService`），但新程式碼照 04-cross-cutting §3.2 走注入，既有程式碼不動。

---

## 架構決策

### AD-1：推算出的淨投入在存檔時寫入既有 `net_investment` 欄（落地），不在讀取時動態推算

- **背景**：BR-8 要求推算值和手填淨投入語意相同、下游口徑不變；proposal 的「本次不做」列出所有下游計算與既有歷史紀錄都不動。要決定的是：推算值是存下來，還是每次讀取時再算。
- **選擇**：股票/ETF 存檔時由 `CostBasisService` 算出當月淨投入，連同 `total_cost`、`realized_income` 一起寫進 `monthly_records`，淨投入寫在既有的 `net_investment` 欄。`ReturnService`、`AllocationService`、淨值、協定判定、CSV 匯出**一行都不改**，照舊讀 `net_investment`。
- **理由**：
  - BR-8 靠結構就成立：下游讀到的是同一欄、同一語意，不用逐一證明各下游沒被影響。
  - 既有歷史紀錄（舊制手填值）原封不動，符合「既存的淨投入數字不動」。
  - 代價只有一個：前一筆紀錄改動時，受影響的後續列要跟著重算（BR-4），交給 AD-4 處理。
- **否決方案**：
  - **讀取時動態推算**：每個讀 `monthly_records` 的地方（`read_range`/`read_all`/`read_month` 與其下游）都得套推算，而且區間查詢需要區間外的前一筆紀錄。推算放 Repository 等於把業務邏輯塞進 I/O 層（違反 02 §6）；放各下游 Service 則要改所有下游，違反「本次不做」。否決。
  - **另開 `derived_net_investment` 欄，下游改讀它**：下游要全改，而且新舊兩欄語意重疊。否決。
- **後果**：
  - 正面：下游零改動；報酬率一致性（成功標準第 2 條）由「同欄同語意」直接保證。
  - 負面：`net_investment` 在股票/ETF 新制列上變成「衍生值」，必須靠 AD-4 維持一致。如果項目分類在「股票/ETF」和「其他」之間切換，已落地的值不會回溯重算（列入技術債）。

### AD-2：`monthly_records` 附加 `total_cost`、`realized_income` 兩欄（可為 NULL），沿用 idempotent 加欄遷移

- **背景**：BR-1、BR-2 需要每月總成本與已實現收益；proposal 的外部契約要求沿用既有 idempotent ALTER 遷移，舊資料為空值。
- **選擇**：
  1. 新增兩欄 `total_cost REAL`、`realized_income REAL`，**都可為 NULL、不設 DEFAULT**。`_CREATE_MONTHLY_RECORDS` 直接包含這兩欄（新庫）；既有庫在 `ensure_schema` 裡探測缺欄才 `ALTER TABLE monthly_records ADD COLUMN ...`。
  2. 把既有的 `_ensure_holdings_purpose_column` 抽成通用私有 helper `_add_column_if_missing(cursor, *, table, column, alter_sql)`，holdings.purpose 和這兩欄共用，避免同樣邏輯複製三份。
  3. **判斷一列是不是新制**：`total_cost IS NOT NULL` 就是新制股票/ETF 列，它的 `net_investment` 是推算值；`total_cost` 為 NULL 的列可能是非股票/ETF，也可能是本功能上線前的股票/ETF 舊制列。這就是 BR-2 過渡規則判斷「上一筆是不是本功能上線前建立」的技術依據。
  4. 新制列的 `realized_income` 一律寫實際值（預設 0，不寫 NULL）；推算時把 NULL 當 0 處理。
- **理由**：可為 NULL 的附加欄是 SQLite/libsql 對既有資料最安全的演進方式，NULL 本身就表示「未填／舊制」，不需要另開旗標欄。D17 的 schema 演進原則是明確欄位、不用 generic KV。
- **否決方案**：
  - **加 DEFAULT 0**：舊制列會被回填成 total_cost=0，和「清倉月的總成本 0」（BR-3）無法區分，過渡判斷會錯。否決。
  - **另加 `input_mode` 旗標欄**：資訊和 `total_cost IS NULL` 重複，兩者可能不一致。否決。
  - **另建 `stock_cost_records` 關聯表**：每次讀取都得 JOIN，CSV 也要多一份檔案，D17 也不允許為此另開屬性表。否決。
- **後果**：
  - 正面：舊庫升級、新庫直建兩條路最後結構一致；舊資料不遺失、不變動。
  - 負面：`RecordRepository` 的欄序常數、`_row_to_model`、`_values`、INSERT/UPSERT SQL 和 DataFrame 欄位都要一起擴充（DataFrame 會多兩欄，下游用具名欄位存取，不受影響），會碰到斷言「確切欄位清單」的既有測試（見〈受影響的既有 SC 與測試〉）。

### AD-3：推算與連動重算邏輯集中在新的純運算 `CostBasisService`，由 Page 編排

- **背景**：這個 Change 要新增四件業務能力：判斷項目是否走總成本推算（BR-1/BR-7）、推算當月淨投入（BR-1/BR-2，含過渡規則）、修改或刪除後的連動重算（BR-4）、轉移時濾掉股票/ETF 端（BR-6）。
- **選擇**：新增 `services/cost_basis_service.py::CostBasisService`：
  - **純運算**：不碰 I/O、不 import streamlit。項目主檔和該項目的全部月度紀錄都由呼叫端當參數傳入。
  - **建構子注入** `cost_basis_categories: frozenset[str]`，由 bootstrap 從 `COST_BASIS_INPUT.CATEGORIES` 注入（照 04 §3.2，Service 不在方法內讀 constants 值）。
  - Page 負責依序呼叫：`record_repo.read_holding_records` → `cost_basis_service.derive/plan_save/plan_delete` → `record_repo.upsert_records` / `delete_record_and_upsert`。
  - `MonthlyInputService` 維持原本的職責（帶入上月、成對轉移防呆），**不注入** `CostBasisService`。
- **理由**：推算和重算是這個 Change 風險最高的部分，做成零 I/O 的純函式後，可以直接用固定的紀錄序列窮舉邊界（首筆、過渡、清倉、中間插入、刪除），完全不用 DB 或 Streamlit。這和 house-dashboard AD-3「Page 編排多個純 Service、Service 之間不注入」的慣例一致。
- **否決方案**：
  - **塞進 `MonthlyInputService`**：該 Service 已注入 Repo 做讀取，而且文件寫明「不在內部觸發任何寫入」。硬加推算和重算規劃會混進兩種抽象（讀 I/O 的帶入 vs 純推算），往 God Object 發展。否決。
  - **推算放 `RecordRepository.upsert` 內自動完成**：業務邏輯進 I/O 層，違反 02 §6。否決。
  - **放 `core/utils.py`**：推算含業務判斷（分類、過渡規則），不符 02 §8「禁止業務流程判斷」。否決。
- **後果**：
  - 正面：核心規則可以獨立單元測試；職責單一（約 5 個 public 方法）。
  - 負面：Container 多一個欄位；`views/input.py` 的編排步驟變多（讀紀錄 → 規劃 → 寫入），但都只是「呼叫 Service/Repo 加上錯誤處理」，符合 Controller 職責。

### AD-4：連動重算的範圍是「該項目在異動月份之後的所有新制列」，依時間順序往後重算，只回傳數值有變的列

- **背景**：BR-4 要求改動或刪除某月後，下一筆有紀錄月份自動重算，並註明「只影響緊接的下一筆（每月推算只依賴自身與前一筆）」。但 BR-2 的過渡規則（上一筆是舊制時，用「初始成本＋該月以前所有淨投入」當前期總成本）會讓推算值依賴**跨越多筆**的淨投入總和。例子：刪除一筆較早的舊制列，或把某筆舊制列重存成新制，緊接的下一筆如果是舊制列（不推算），真正受影響的是更後面第一筆新制列。只重算緊接的下一筆，在這種情況會漏掉。
- **選擇**：`plan_save`／`plan_delete` 先在記憶體中套用這次異動（替換／插入／移除月份 M），然後對該項目**年月晚於 M 的每一筆新制列**（`total_cost` 不為 NULL）依時間順序重新推算淨投入。後面的列會用到前面列已更新的淨投入，所以過渡規則的總和會取到最新值。**只回傳推算值和既存值不同的列**，比較時容許浮點誤差。M 之前的列只當輸入，永遠不改；舊制列（`total_cost` 為 NULL）永遠不重算。
- **理由**：
  - 全部是新制列時，M 之後只有緊接的下一筆會變，所以回傳結果剛好是「存檔列＋下一筆」，和 BR-4 字面**完全一致**，SC 可以直接斷言。
  - 有過渡列時仍然正確，不會漏算。
  - 重算是冪等的：沒受影響的列算出來還是原值，不會回傳也不會被寫入。資料量很小（每個項目每年約 12 列），全段重算的成本可忽略。
- **否決方案**：
  - **只重算緊接的下一筆**（BR-4 字面）：在過渡規則下會漏算，理由如背景所述。否決。
  - **每次都重算該項目全部新制列（包括 M 之前）**：可能順手「修正」M 之前與 M 無關的列（例如 CSV 匯入時帶進來的不一致值），寫入範圍超出這次異動，違反最小影響原則。否決。
- **後果**：
  - 正面：兩種情況都正確；回傳清單就是這次要寫入的差異，方便測試與稽核。
  - 負面：比字面規則多一層「往後掃描」。這是設計對 BR-4 的解讀，已列入〈待確認事項〉Q5 供知會，不需要另做決策。

### AD-5：多列寫入改用 Repository compound method，在單一交易內完成（失敗時 rollback）

- **背景**：股票/ETF 存檔要寫「存檔列＋受影響的後續列」，刪除要「刪一列＋更新受影響的後續列」，轉移要寫 0～2 列。只寫了一半會讓推算鏈不一致。
- **選擇**：`RecordRepository` 新增兩個 compound method，所有 statement 執行完才 `commit()` 一次；任何一步拋例外就先 `self._conn.rollback()` 再**原樣往上拋**（不 log，錯誤處理仍由 Page 負責）：
  - `upsert_records(*, records)`：批次 upsert。
  - `delete_record_and_upsert(*, holding_id, year_month, records)`：刪除一列後批次 upsert。
  - 已確認本機 libsql 的 Connection 有 `rollback`、`in_transaction` 屬性。多個 statement 共用一次 commit 的做法，既有 `replace_all` 已經在用。
- **理由**：多步 I/O 中間沒有業務邏輯介入，符合 02 §6 compound method 的定義；方法名稱帶業務語意。rollback 後再拋，是和 main.py 範例 `browser.cleanup()` 同類的資源清理，不算吞例外，也不在 Repository 記 error log（符合 04 §2.1）。
- **否決方案**：
  - **Page 逐筆呼叫 `upsert_record`**：每筆各自 commit，中途失敗就會留下半套的推算鏈。否決。
  - **不做 rollback**：失敗後未 commit 的 statement 會留在連線上，下一個操作 commit 時會把殘缺結果一起寫進去。否決。
- **後果**：
  - 正面：推算鏈寫入要嘛全部成功、要嘛全部失敗。轉移改走 `upsert_records` 後也變成原子寫入。
  - 負面：`views/input.py` 的轉移路徑從兩次 `upsert_record` 改成一次 `upsert_records`，`tests/test_input_view.py` 的 Record 替身要跟著補方法。

### AD-6：項目間轉移沿用 `build_transfer_pair` 的防呆，再由 `CostBasisService` 濾掉股票/ETF 端（BR-6）

- **背景**：BR-6 規定股票/ETF 那一端不寫淨投入（交給總成本推算），只記另一端；兩端都是股票/ETF 時兩端都不寫。既有的 `build_transfer_pair` 會固定產出兩筆，SC-008/SC-037 在 Service 層有測試。
- **選擇**：
  - `MonthlyInputService.build_transfer_pair` **簽名和行為都不變**，SC-037 的防呆（金額須為正、來源不可等於目標）照舊在這裡攔下。
  - 新增 `CostBasisService.transfer_records_to_write(*, pair, holdings) -> list[MonthlyRecordModel]`：從成對紀錄中去掉「走總成本推算」那一端，回傳 0～2 筆。
  - Page 編排：`build_transfer_pair` → `transfer_records_to_write` → 非空就 `upsert_records`；空清單（兩端都是股票/ETF）時不寫任何紀錄，用非錯誤的提示告知使用者（UX 見 Q4）。
- **理由**：不改既有方法，SC-008/SC-037 的 Service 層測試就不會壞；BR-6 的過濾需要「分類判斷」，本來就屬於 `CostBasisService` 的能力。兩步分開，各自的職責都清楚。
- **否決方案**：
  - **把 `build_transfer_pair` 的回傳改成 list 並加 holdings 參數**：既有 SC-008/SC-037 測試對 tuple 的解包會全部壞掉，而且 `MonthlyInputService` 要多吃分類規則。否決。
  - **兩端都是股票/ETF 時拋錯誤**：BR-6 已明定這是合法情況（兩端都不寫），不是無效輸入。否決（UX 仍列 Q4 確認）。
- **後果**：
  - 正面：既有 Service 契約不破壞；BR-6 集中在一處。
  - 負面：SC-008 卡片的敘述（例子是「現金 → 台積電」，兩端都記淨投入）和新的整體行為不一致，需要 scenario-author 修訂或另開新卡取代（見〈受影響的既有 SC 與測試〉）。

### AD-7：千分位金額輸入改用 `st.text_input`，搭配純函式解析/格式化與 `on_change` 正規化

- **背景**：BR-9 要求金額以整數千分位顯示，輸入時有沒有逗號都接受，負數用 `-`，無法解析就拒絕存檔。Streamlit 原生 `st.number_input` 的 `format` 只能輸出純數字（1.59 已查證），做不到千分位。
- **選擇**：
  1. **純函式**（`core/utils.py`，無 I/O、無業務判斷，可以單獨測試）：
     - `format_amount(value)`：四捨五入（遠離零）成整數，加千分位逗號；負數前面加 `-`；`-0` 顯示成 `0`；`None` 顯示成空字串。
     - `parse_amount(text, *, field_label)`：先做 NFKC 正規化（全形數字和全形逗號轉半形，照顧中文輸入法），去掉前後空白，再用嚴格格式比對：有逗號時必須是標準三位一組，否則就是純數字；可以有 `-` 前綴和小數部分。通過後四捨五入（遠離零）成整數，以 float 回傳（對齊 Model 的 float 欄）。空字串、`None` 或格式不合就拋 `DataValidationError`，訊息裡帶欄位名稱。
  2. **UI 元件**（`src/asset_lab/amount_widget.py::amount_input`）：包裝 `st.text_input`，初值用 `format_amount(value)`。自帶一個 `on_change` 正規化回呼：解析成功就把 `session_state[key]` 改寫成千分位格式；解析失敗就保留原字串（存檔時才報錯）。之後再呼叫呼叫端傳入的回呼，讓 SC-051 的 `_sync_cost_to_market_value` 可以串在後面。元件**回傳原始字串**，數值解析由 Page 呼叫 `parse_amount` 負責。
  3. **Page 存檔時**用 `parse_amount` 轉成數值，失敗拋 `DataValidationError`，由既有的 page 層 `except AssetLabError` 轉成 `st.error`，不寫入 DB（BR-9）。**存檔前預覽**（BR-5）在 Page 內用 `try/except DataValidationError` 局部處理，失敗時只顯示「輸入完成後顯示推算值」之類的佔位提示，不當成錯誤。
  4. **套用範圍**照 BR-10 的金額欄清單；百分比、年份、年限、利率欄維持 `number_input` 不動。
- **理由**：不加外部依賴（proposal 限制）；解析/格式化是純函式，嚴格分組可以攔下「1,00,000」這種多打或少打 0 的輸入，正好是這個 Change 想防的錯。`on_change` 正規化讓欄位離開焦點（blur）或按 Enter 後立刻變成千分位，所見即所存。
- **否決方案**：
  - **維持 `number_input`，下方加一行千分位 caption**：輸入框本身還是沒有千分位，不符 BR-9「數值以整數千分位顯示」。否決。
  - **第三方或自製 component**：要新增依賴或前端建置，proposal 明定不加新依賴。否決。
  - **解析時只把逗號去掉、不檢查分組**：「1,00,000」會被默默當成 100000，失去防止打錯 0 的意義。否決（嚴格程度列 Q1 確認）。
- **後果**：
  - 正面：零依賴、可以測試、跨頁一致。
  - 負面：
    - 少了 `number_input` 的 +/- 步進鈕和 `min_value` 限制。買房金額的非負檢核改由既有的 `HouseService.validate_params` 負責（已查證它會檢查金額非負）；初始市值和初始成本原本就沒有 `min_value`。
    - 小數會被取整（Q1）。
    - 既有 UI 機制測試（`at.number_input(key=...)`、`format == "%.0f"`）要改成 `at.text_input`。

### AD-8：金額輸入框放大，用有 key 的外層 container 加一段全站 CSS

- **背景**：BR-10 要把金額框的字級和高度放大，但只限金額欄；同一頁還有非金額的 `text_input`（例如設定頁的「名稱」），不能一起被放大。
- **選擇**：
  - `amount_input` 外層包一個 `st.container(key=f"{_CONTAINER_KEY_PREFIX}{key}")`。Streamlit 會把有 key 的元素加上 `st-key-<key>` CSS class，這是官方 docstring 寫明的行為（已查證 1.59 的 `st.container` 支援 `key`）。
  - `amount_widget.inject_amount_input_style()` 用 `st.html("<style>…</style>")` 注入 CSS，選擇器是 `[class*="st-key-<前綴>"] input`。只有 style 的 `st.html` 會被放進 event container、不佔版面（已查證）。字級約 1.25rem、高度約 3rem，實際數值以模組私有常數定義。
  - 在 `app.py::main()` 的守門通過後、`navigation.run()` 之前**呼叫一次**，所有頁面都生效。
- **理由**：用 key 前綴來選中目標，精準對到金額欄、不影響其他 text_input；widget 本身的 key 不動（例如 `new_market_value`），SC-051 的同步 key 和既有測試的 key 都不用改名；樣式定義只有一處。
- **否決方案**：
  - **對全站 `text_input` 套 CSS**：「名稱」欄也會被放大，不符 BR-10。否決。
  - **強制金額 widget 的 key 都加前綴**：要改動既有 key，SC-051 同步對照表和測試都得跟著改名。否決。
  - **每頁各自注入**：樣式定義分散、容易漏掉。否決。
- **後果**：
  - 正面：放大範圍精準，只改一處即可全站調整。
  - 負面：`st-key-*` class 是公開行為，但 class 底下的 `<input>` DOM 結構不是公開 API，Streamlit 升級後選擇器可能要調整（列入技術債）；用 AppTest 單獨跑 `views/*.py` 時沒有經過 app.py，不會有樣式，所以視覺效果只能在 2-Z 啟動驗證時確認。

### AD-9：CSV records 對外契約附加 `total_cost`、`realized_income`，舊格式仍可匯入

- **背景**：proposal 要求 CSV 匯出再匯入後，總成本和已實現收益不遺失、後續推算仍正確；舊格式（沒有新欄位）的 CSV 也必須能還原，新欄位視為未填。
- **選擇**：
  - `CSV_EXPORT.RECORDS_COLUMNS` 在**尾端附加** `total_cost`、`realized_income`，既有欄序不變。
  - 新增 `CSV_EXPORT.RECORDS_REQUIRED_COLUMNS`＝原本 4 欄，比照 `HOLDINGS_REQUIRED_COLUMNS` 的寫法。
  - `export_records_csv` 用 reindex 輸出 6 欄（`read_all` 已含新欄）。
  - `parse_and_validate` 驗證表頭時改用 `RECORDS_REQUIRED_COLUMNS`；`_build_records` 在欄位存在時讀新欄（空白用既有的 `_optional_float` 轉成 None），欄位不存在就是 None。
  - `replace_all` 經由擴充後的 `_values` 自動寫入新欄。
  - **匯入時不重算、也不檢查淨投入和總成本鏈是否一致**：匯出的 `net_investment` 本來就是已落地的值（AD-1），照原值還原即可。
- **理由**：和 house-dashboard AD-8 的 holdings.purpose 同一套路。新匯出的檔案資料完整，舊備份照樣能還原；舊檔還原後股票/ETF 列 `total_cost` 為 NULL，第一個新制月份會自然走 BR-2 的過渡規則。
- **否決方案**：
  - **新欄列為強制表頭**：這個 Change 之前匯出的舊 CSV 一匯入就失敗，破壞沒有必要。否決。
  - **匯入後重算整條鏈**：會改動使用者備份裡的淨投入，違反「還原」的語意。否決。
- **後果**：
  - 正面：新舊格式都能匯入，新欄位也不會在往返中遺失。
  - 負面：SC-031 的匯出欄位斷言要跟著擴充；匯入端信任 CSV 內的淨投入（列入技術債）。

### AD-10：月度錄入頁依項目分類切換輸入欄位，並在存檔前顯示推算預覽（BR-5/BR-7）

- **背景**：股票/ETF 要輸入「目前總成本＋現值＋本月已實現收益（預設 0）」，其他分類維持「市值/餘額＋當月淨投入」；存檔前要顯示推算出的淨投入供核對。
- **選擇**：`views/input.py::_render_record_editor` 選定項目後，先呼叫 `cost_basis_service.uses_cost_basis(holding=...)`（分類判斷不寫在 Page）決定要顯示哪一組欄位：
  - **股票/ETF**（抽成 `_render_cost_basis_editor`）：三個 `amount_input`（總成本、現值、已實現收益，已實現收益初值 0）。每次 rerun 讀取該項目的全部紀錄，呼叫 `derive(...)`，顯示「前期總成本」和「推算本月淨投入」；如果 `is_transition_estimate` 為 True，另外標示前期總成本是用過渡規則估算的，讓使用者注意 proposal 已知的過渡偏差風險。儲存時 `plan_save` → `upsert_records`；刪除時 `plan_delete` → `delete_record_and_upsert`。**不論該月是新制還是舊制列**，股票/ETF 項目的存檔和刪除一律走這條路（刪掉舊制列也可能影響後續推算，見 AD-4）。
  - **其他分類**：兩個 `amount_input`（市值/餘額、當月淨投入），寫入維持既有的 `upsert_record` / `delete_record`。
  - 轉移金額也改用 `amount_input`（AD-6）。
  - 頁面提示文案（清倉怎麼填、兩端都是股票/ETF 的轉移提示等）的具體措辭由 SC 定義，本設計不寫死。
- **理由**：Page 只負責委派與呈現，分類判斷和推算都在 Service，符合 AD-2（initial-build）的分層。Streamlit 每次互動就 rerun，預覽可以即時更新，不用額外狀態管理。
- **否決方案**：
  - **股票/ETF 同時顯示淨投入欄讓使用者手動覆寫**：proposal 已知缺陷明定本次不提供手動覆寫推算值。否決。
  - **把預覽邏輯放在 Page**：前期總成本判斷含過渡規則，屬於業務判斷。否決。
- **後果**：
  - 正面：股票/ETF 只要照抄券商數字（成功標準第 1 條）；兩種分類的輸入流程在程式碼上分開，不會互相干擾。
  - 負面：`views/input.py` 行數增加（抽成子函式控制）；單列錄入**仍然不預載該月既有紀錄的值**（既有行為，不在本次範圍）。

---

## 技術選型

### TD-1：千分位輸入用 Streamlit 原生 `st.text_input`＋自製純函式，不引入第三方元件

- **推薦**：`st.text_input` + `core/utils.format_amount` / `parse_amount` + `on_change` 正規化（信心度：High）
- **理由**：
  - 已查證 Streamlit 1.59.1 的 `st.number_input(format=...)` 只接受純數字輸出，無法顯示千分位。
  - `st.text_input` 支援 `key`、`on_change`、`kwargs`，足以做到「離開焦點就正規化」。
  - proposal 明定不加外部依賴，所以否決 `streamlit-extras` 之類的套件和自製前端 component。

### TD-2：放大樣式用 `st.html` 注入 style，並以 `st-key-*` class 選中目標

- **推薦**：`st.container(key=...)` 加上 `st.html("<style>…</style>")`（信心度：Medium）
- **理由**：
  - 以 key 產生 `st-key-<key>` class，以及 style-only `st.html` 不佔版面，兩者都寫在 1.59 docstring 裡，已查證。
  - 信心度給 Medium，是因為 class 底下 `<input>` 的 DOM 結構不是公開 API，最後的視覺效果要在 2-Z 啟動驗證時確認。

### TD-3：其餘技術棧沿用

- **推薦**：Streamlit + libsql(Turso) + Pydantic + pandas，全部沿用（信心度：High）
- **理由**：交易控制（commit/rollback）用 libsql Connection 原生方法，已在本機 venv 查證有 `rollback`、`in_transaction`；NFKC 正規化用標準庫 `unicodedata`；四捨五入用標準庫 `decimal`（`ROUND_HALF_UP` 在 decimal 模組中就是遠離零取整）。

---

## 介面契約

> 以下是型別簽名與語意契約（技術層）。金額單位是 TWD（float，UI 輸入取整數），年月是 `'YYYY-MM'`。
> **行為細節（邊界值、錯誤路徑、提示文案）由 1-3 Scenarios 用 BR 編號定義，這裡不重述。**

### 1. 常數（`core/constants.py`）

```python
class MONTHLY_RECORDS_TABLE:
    ...                                   # 既有欄位不變
    TOTAL_COST = "total_cost"             # 股票/ETF 當月目前總成本；NULL＝非股票/ETF 或本功能上線前的舊制列
    REALIZED_INCOME = "realized_income"   # 股票/ETF 本月已實現收益（已實現損益＋現金股利，可為負）；NULL 同上


class COST_BASIS_INPUT:
    """以「總成本＋已實現收益」推算當月淨投入的資產分類（BR-1/BR-7）。由 bootstrap 注入 CostBasisService。"""

    CATEGORIES = frozenset({ASSET_CATEGORIES.TW_STOCK, ASSET_CATEGORIES.US_STOCK})


class CSV_EXPORT:
    ...
    RECORDS_COLUMNS = (
        "holding_id", "year_month", "market_value", "net_investment",
        "total_cost", "realized_income",   # 尾端附加（AD-9）
    )
    RECORDS_REQUIRED_COLUMNS = RECORDS_COLUMNS[:-2]   # 匯入強制欄位集＝原本 4 欄（向後相容）
```

### 2. Models

```python
# models/record.py
class MonthlyRecordModel(BaseModel):
    """（docstring 補上新欄語意：total_cost 不為 None 就是新制股票/ETF 列，其 net_investment 為推算值）"""
    holding_id: int
    year_month: str
    market_value: float | None = None
    net_investment: float = 0.0
    total_cost: float | None = None        # AD-2
    realized_income: float | None = None   # AD-2；新制列一律有值（預設 0）


# models/results.py
class NetInvestmentDerivation(BaseModel):
    """股票/ETF 當月淨投入推算結果（BR-1/BR-2，BR-5 存檔前預覽用）。

    is_transition_estimate 為 True 表示上一筆是舊制列，前期總成本是用
    「初始成本＋該月以前所有淨投入」估算的（BR-2 過渡規則）。
    """
    previous_total_cost: float
    is_transition_estimate: bool
    net_investment: float
```

### 3. 純函式（`core/utils.py`）

```python
def format_amount(value: float | None) -> str: ...
    # None → ""；否則四捨五入（遠離零）成整數，加千分位逗號；負數前加 "-"；-0 → "0"（AD-7）

def parse_amount(text: str | None, *, field_label: str) -> float: ...
    # NFKC 正規化 → strip → 嚴格比對：^-?(\d{1,3}(,\d{3})+|\d+)(\.\d+)?$
    # 四捨五入（遠離零）成整數，以 float 回傳
    # 空字串、None、格式不合 → DataValidationError（訊息帶 field_label）（AD-7，嚴格程度見 Q1/Q2）
```

### 4. Repositories

```python
# repositories/record_repository.py（既有方法簽名不變；欄序、row↔model、INSERT/UPSERT 擴充到 6 欄）
class RecordRepository:
    def read_holding_records(self, *, holding_id: int) -> list[MonthlyRecordModel]: ...
        # 該項目的全部月度紀錄，依 year_month 由舊到新排序（供 CostBasisService 推算）
    def upsert_records(self, *, records: list[MonthlyRecordModel]) -> None: ...
        # 批次 upsert，單一交易；任一步失敗 → rollback 後原樣往上拋（AD-5）；空清單不做任何事
    def delete_record_and_upsert(
        self, *, holding_id: int, year_month: str, records: list[MonthlyRecordModel]
    ) -> None: ...
        # 刪除單列後批次 upsert 受影響列，單一交易；失敗 → rollback 後原樣往上拋（AD-5）
    # 既有 read_range / read_all 的 DataFrame 欄位擴充為 6 欄（空集合也保留完整欄位）
    # 既有 _UPSERT 的 DO UPDATE SET 擴充為 market_value、net_investment、total_cost、realized_income 四欄


# repositories/schema_repository.py
class SchemaRepository:
    def ensure_schema(self) -> None: ...
        # 既有六表 CREATE IF NOT EXISTS（monthly_records 新庫直接含兩個新欄）
        # ＋ holdings.purpose、monthly_records.total_cost、monthly_records.realized_income 三個加欄遷移
    @staticmethod
    def _add_column_if_missing(cursor, *, table: str, column: str, alter_sql: str) -> None: ...
        # PRAGMA table_info 探測，缺欄才執行 alter_sql；取代既有 _ensure_holdings_purpose_column（AD-2）
```

### 5. Services

```python
# services/cost_basis_service.py（新增，純運算：無 I/O、無 Streamlit）
class CostBasisService:
    """股票/ETF 總成本推算淨投入、連動重算規劃、轉移端過濾（BR-1/2/4/6/7）。"""

    def __init__(self, *, cost_basis_categories: frozenset[str]) -> None: ...

    def uses_cost_basis(self, *, holding: HoldingModel) -> bool: ...
        # 項目的當前分類在 cost_basis_categories 內就是 True（負債 category 為 None → False）

    def derive(
        self, *, holding: HoldingModel, records: list[MonthlyRecordModel], year_month: str,
        total_cost: float, realized_income: float,
    ) -> NetInvestmentDerivation: ...
        # 前期總成本（BR-2），只看 records 中 ym < year_month 的列：
        #   沒有前一筆 → holding.initial_cost（None 當 0）
        #   前一筆 total_cost 不為 None → 前一筆的 total_cost
        #   前一筆是舊制（total_cost 為 None）→ initial_cost + Σ(ym < year_month 各列的 net_investment)，is_transition_estimate=True
        # 淨投入（BR-1）＝(total_cost − 前期總成本) − realized_income

    def plan_save(
        self, *, holding: HoldingModel, records: list[MonthlyRecordModel], year_month: str,
        market_value: float, total_cost: float, realized_income: float,
    ) -> list[MonthlyRecordModel]: ...
        # 回傳 [存檔列（net_investment＝推算值）, *ym 晚於 year_month 且推算值有變的新制列]，依 ym 排序（AD-4）

    def plan_delete(
        self, *, holding: HoldingModel, records: list[MonthlyRecordModel], year_month: str,
    ) -> list[MonthlyRecordModel]: ...
        # 在記憶體中移除 year_month 列後，回傳 ym 晚於 year_month 且推算值有變的新制列（AD-4）

    def transfer_records_to_write(
        self, *, pair: tuple[MonthlyRecordModel, MonthlyRecordModel], holdings: list[HoldingModel],
    ) -> list[MonthlyRecordModel]: ...
        # 去掉走總成本推算那一端，回傳 0～2 筆（BR-6，AD-6）

    # 前置條件：records 只含該 holding 的紀錄；plan_save / plan_delete / derive 限用於
    # uses_cost_basis 為 True 的項目，違反時拋 DataValidationError


# services/monthly_input_service.py：不變（build_transfer_pair 的簽名與防呆維持原樣，AD-6）

# services/data_io_service.py：export_records_csv 輸出 6 欄；表頭驗證改用 RECORDS_REQUIRED_COLUMNS；
#   _build_records 選讀兩個新欄（缺欄或空白 → None）（AD-9）
```

### 6. UI 元件（`src/asset_lab/amount_widget.py`，新增，會 import streamlit）

```python
def amount_input(
    label: str, *, key: str, value: float | None = 0.0,
    on_change: Callable[..., None] | None = None, kwargs: dict | None = None,
) -> str: ...
    # 外層包 st.container(key=_CONTAINER_KEY_PREFIX + key)，內部 st.text_input(key=key)
    # 初值 format_amount(value)，只在該 key 第一次建立時生效（和 Streamlit keyed widget 語意一致；
    #   建議用 session_state.setdefault 播種，避免「value 參數與 Session State API 同時設定」的警告）
    # 自帶的 on_change：先正規化 session_state[key]（能解析 → 改成千分位格式），再呼叫呼叫端的 on_change(**kwargs)
    # 回傳原始字串；數值解析由呼叫端用 parse_amount 進行

def inject_amount_input_style() -> None: ...
    # st.html 注入 style-only CSS：選擇器 [class*="st-key-<前綴>"] input，字級約 1.25rem、高度約 3rem（AD-8）
```

### 7. Views／入口／組裝

| 檔案 | 異動 |
|------|------|
| `views/input.py` | `_render_record_editor` 依 `uses_cost_basis` 分成兩支（AD-10）；新增 `_render_cost_basis_editor`；金額欄全改 `amount_input` + `parse_amount`；轉移改走 `transfer_records_to_write` + `upsert_records`（AD-6/AD-5） |
| `views/settings.py` | 初始市值、初始成本（新增與編輯表單）和四個買房金額參數（目標總價、家庭稅後月收、收入門檻、現金地板）改用 `amount_input` + `parse_amount`；`_sync_cost_to_market_value` 經由 `amount_input(on_change=..., kwargs=...)` 串接，widget key 不改名；比率、年份、年限、利率、目標比重、協定門檻不動 |
| `app.py` | `main()` 在 `_require_access()` 之後呼叫一次 `inject_amount_input_style()`（AD-8） |
| `bootstrap.py` | `Container` 新增 `cost_basis_service: CostBasisService`；`build_container` 以 `CostBasisService(cost_basis_categories=COST_BASIS_INPUT.CATEGORIES)` 組裝 |

---

## 受影響的既有 SC 與測試（交接給 1-3 scenario-author／1-4 task-planner）

| 對象 | 影響 | 建議處理 |
|------|------|---------|
| **SC-008**（項目間轉移成對記錄；例子是現金 → 台積電） | BR-6 之後，台積電（股票）那一端不再寫入，整體行為和卡片敘述不一致。Service 層 `build_transfer_pair` 沒改，既有 SC-008 測試仍會通過 | scenario-author 修訂 SC-008（或另開新卡取代），講清楚「Service 產出成對紀錄」和「寫入時股票/ETF 端被濾掉」這兩層 |
| **SC-009**（賣出當月記市值 0 與負淨投入；例子是台積電） | 股票/ETF 清倉改成填總成本 0、現值 0、已實現收益照實填（BR-3）；落地結果（市值 0、淨投入為負）一樣，但卡片中「使用者輸入淨投入」的敘述對股票/ETF 不再成立 | 修訂或另開新卡，限定原敘述只適用於非股票/ETF 分類 |
| SC-031（`test_sc031_export_records_has_header_and_all_rows`） | 斷言匯出欄位剛好 4 欄 | 擴充為 6 欄（AD-9） |
| SC-006（`test_read_range_empty_preserves_columns`） | 斷言 `read_range` 空集合剛好 4 欄 | 擴充為 6 欄（AD-2） |
| SC-051（`tests/test_settings_view.py` 的活存/定存成本同步） | 行為不變；widget 從 `number_input` 改成 `text_input`，值變成千分位字串 | 機械式改寫測試（`at.text_input(key=...)`，斷言字串值） |
| SC-037 | 轉移金額改從文字解析；≤0 仍由 `build_transfer_pair` 拒絕 | Service 層測試不受影響；View 層測試做機械式改寫 |
| 非 SC 的 UI 機制測試 | `TestInitialValueCostNoDecimal`（斷言 `format == "%.0f"`，被 BR-9 取代）、`test_input_view.py`（`at.number_input(key="amt")`、Container 替身少了 `cost_basis_service`、Record 替身少了 `upsert_records`、Holding 替身少了 `category`） | 改寫成千分位顯示的斷言，並補齊替身 |
| holdings.purpose 遷移測試 | `_ensure_holdings_purpose_column` 抽成通用 helper | 既有測試應維持通過（行為不變） |
| `test_bootstrap.py` | Container 多一個欄位 | 如有斷言完整欄位集合就補上 |

scenario-author 另外應該掃過 capability 為 `monthly-input` / `data-io` 的所有卡片，確認有沒有其他以股票/ETF 為例、描述手填淨投入的敘述。

---

## 已知技術債與限制

- **推算值落地之後，分類切換不會回溯重算**（AD-1）：項目在「股票/ETF」和「其他分類」之間切換時，已寫入的 `net_investment` 維持原值；之後在新分類下存檔才走新的輸入方式。
- **CSV 匯入信任檔案裡的淨投入**（AD-9）：不檢查淨投入和總成本鏈是否一致；如果使用者手動編輯過 CSV 造成不一致，要等該月之後再有異動時，才會由 AD-4 的往後重算修正其後的列。
- **過渡規則的已知偏差**（proposal 已列）：上線前若曾賣出，第一個新制月份的前期總成本會和券商數字相差過去的已實現損益；緩解方式是 `is_transition_estimate` 標示加上存檔前預覽。使用者已確認上線前沒有賣出紀錄。
- **既有轉移 upsert 的覆寫行為（本 Change 之前就存在，本 Change 沒有新增或擴大，建議另案處理）**：`_UPSERT` 會用 excluded 值覆寫同月同項目的 `market_value` 和 `net_investment`。轉移寫入的非股票/ETF 端市值為 None，會把該月已存的市值清空；同月對同一項目做多次轉移時，淨投入會被後一次覆寫，不會累加。本 Change 讓股票/ETF 端不再被轉移寫入，股票端從此不受影響。
- **CSS 依賴 `st-key-*` class 底下的 DOM 結構**（AD-8/TD-2）：Streamlit 升級後，`<input>` 的選擇器可能要調整。
- **`text_input` 沒有步進鈕，也沒有數字鍵盤提示**：手機上輸入金額時，會跳出一般鍵盤而不是數字鍵盤。
- **單列錄入不預載該月既有紀錄的值**：這是既有行為，不在本次範圍；BR-4 的「修改」是指重新存檔同一月。

---

## 待確認事項

> 以下都不影響架構，只影響個別函式的邊界。每一項都已標出推薦的預設值，實作會照推薦值進行，除非使用者另有決定。

| # | 議題 | 選項 | 推薦 |
|---|------|------|------|
| Q1 | 金額輸入的小數與千分位分組規則 | A：接受小數，四捨五入（遠離零）成整數；逗號必須是標準三位一組，否則拒絕。B：拒絕任何小數。C：保留小數存檔、只在顯示時取整（需要另存一份原始值的 session state） | **A**。所見即所存，照抄券商數字時如果帶小數也能直接貼上；嚴格分組可以攔下「1,00,000」這類打錯 0 的輸入 |
| Q2 | 金額欄清空（空字串）時怎麼處理 | A：所有金額欄一律當成無法解析，拒絕存檔（已實現收益欄初值就是 `0`，清空一定是使用者刻意的）。B：已實現收益空白當 0，其他欄拒絕 | **A**。規則單一、不用分欄處理 |
| Q3 | 總成本、現值要不要加非負檢核 | A：不加（proposal 沒要求，BR-9 允許負數）。B：在 `plan_save` 前拒絕負值 | **A**。不額外增加 proposal 沒有的規則；若要加，落點是 `CostBasisService.plan_save` |
| Q4 | 兩端都是股票/ETF 的轉移（BR-6 規定兩端都不寫）的畫面回饋 | A：不寫任何紀錄，用 `st.info` 告知（不算錯誤）。B：當成無效輸入，用 `st.error` 顯示 | **A**。BR-6 把這種情況定義為合法 |
| Q5 | BR-4「只影響緊接的下一筆」的解讀（只需知會） | 本設計採 AD-4 的往後重算，只回傳數值有變的列：全部是新制列時結果和字面規則一致；有過渡列時也不會漏算 | 知會即可；scenario-author 可以把「全部新制列時只回傳存檔列＋下一筆」寫成 SC 斷言 |

---

## 決策總覽

| ID | 類型 | 決策 | 信心度 |
|----|------|------|--------|
| AD-1 | 架構 | 推算淨投入在存檔時寫入既有 `net_investment` 欄，下游零改動（BR-8 靠結構成立） | High |
| AD-2 | 架構 | `monthly_records` 附加可為 NULL 的 `total_cost`/`realized_income`，用 idempotent 加欄遷移（抽出通用 helper）；`total_cost IS NOT NULL` 就是新制列 | High |
| AD-3 | 架構 | 新增純運算 `CostBasisService`（分類集合用建構子注入），由 Page 編排，Service 之間不注入 | High |
| AD-4 | 架構 | 連動重算＝異動月份之後的新制列依時間順序重算，只回傳有變的列（BR-4 的超集，過渡規則下仍正確） | High |
| AD-5 | 架構 | Repository compound method 在單一交易內寫入多列，失敗時 rollback 後原樣往上拋 | High |
| AD-6 | 架構 | 轉移沿用 `build_transfer_pair` 防呆，再由 `transfer_records_to_write` 濾掉股票/ETF 端（BR-6） | High |
| AD-7 | 架構 | 金額欄改用 `text_input`＋純函式 `parse_amount`/`format_amount`＋`on_change` 正規化 | High |
| AD-8 | 架構 | 有 key 的 container 加上全站單點 `st.html` CSS 放大金額欄（BR-10） | Medium |
| AD-9 | 架構 | CSV records 附加兩欄，強制表頭維持 4 欄（舊格式可匯入），匯入不重算 | High |
| AD-10 | 架構 | 月度錄入依分類切換欄位，存檔前用 `derive` 預覽（含過渡估算標示）（BR-5/BR-7） | High |
| TD-1 | 技術 | 千分位用原生 `st.text_input`＋自製純函式，不加新依賴 | High |
| TD-2 | 技術 | `st-key-*` class 選擇器＋style-only `st.html` 注入樣式 | Medium |
| TD-3 | 技術 | 技術棧沿用；交易控制用 libsql 原生 commit/rollback，正規化與取整用標準庫 | High |
