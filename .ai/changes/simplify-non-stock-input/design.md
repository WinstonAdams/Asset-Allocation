# 設計文件：simplify-non-stock-input（非股票項目免填當月淨投入、負債改填應繳金額、新增各項目趨勢圖）

> 本文件只談技術：架構決策（ADR）和介面契約，不寫業務行為（沒有 GIVEN/WHEN/THEN）。
> **對應的 Scenarios 由後續 1-3 行為規格化（scenario-author）產出**；本文件用 BR 編號引用 `proposal.md` 的業務規則（BR-1~BR-8）。
> 參考來源：`proposal.md`。1-2a 技術選型、1-2b 架構分析都已跳過（progress 有記），所以沒有 tech-research.md 和 architecture-brief.md；既有架構慣例沿用 `.ai/archive/stock-total-cost-input/design.md`（以下簡稱「股票 Change」）、`.ai/archive/transfer-accumulate-fix/design.md`（以下簡稱「轉移 Change」）以及更早的 initial-build / house-dashboard design。
> 本 workspace **沒有 `utils_v2/`**（已再次確認目錄不存在，與前兩個 Change 相同）。02-architecture §7 與 04-cross-cutting 中 utils_v2、structlog、biz_job 的部分都不適用；logging 與錯誤處理照 initial-build AD-8（標準 `logging`、Page 層是唯一 catch 點）。

---

## 現況評估

既有 asset-lab 分四層：`views/*.py`（View/Controller，檔尾無條件呼叫 `render()`）→ `services/*`（純運算，或注入 Repo 只做讀取）→ `repositories/*`（單表 I/O，連線由 bootstrap 注入）→ `models/*`（Pydantic 純資料），外加 `core/`（constants/utils/exceptions/access）、UI 元件模組 `amount_widget.py` 與圖表元件 `charts.py`。DI 由 `bootstrap.build_container` 以 keyword args 組成 `Container`。

### 目前月度錄入的分流（本 Change 要改的地方）

| 項目性質／分類 | 現行錄入欄位 | 淨投入來源 | 寫入路徑 |
|---------------|------------|-----------|---------|
| 股票/ETF（`COST_BASIS_INPUT.CATEGORIES`） | 總成本、現值、已實現損益、現金股利 | `CostBasisService` 推算 | `plan_save`/`plan_delete` → `upsert_records`/`delete_record_and_upsert`（單一交易） |
| 活存、定存、保險 | 市值/餘額、當月淨投入 | **手填** | `upsert_record`/`delete_record`（單列） |
| 負債 | 市值/餘額、當月淨投入 | **手填**（下游不使用） | 同上 |
| 項目間轉移 | 來源、目標、金額 | `build_transfer_pair` → `transfer_records_to_write` | `accumulate_net_investments`（SQL 遞增） |

### 沿用的既有慣例

| 既有模式 | 位置 | 本 Change 怎麼沿用 |
|---------|------|------------------|
| 推算值在存檔時寫入既有 `net_investment` 欄，下游零改動 | 股票 Change AD-1 | 活存/定存/保險的推算值同樣落地在 `net_investment`；報酬率、淨值、配置、協定、CSV 匯出都不必改（proposal「本次不做」） |
| 純運算 Service（無 I/O、無 Streamlit），由 Page 編排，Service 之間不互相注入 | `CostBasisService`、`HouseService`（股票 Change AD-3） | 新增 `BalanceInputService`；保險併入 `CostBasisService`（AD-2、AD-4） |
| 連動重算：先在記憶體中套用異動，再往後重算，只回傳數值有變的列 | `CostBasisService._recalculate_following`（股票 Change AD-4） | 保險直接沿用；活存/定存另訂規則（AD-3，原因見該 ADR） |
| 多列寫入用 Repository compound method，單一交易，失敗時 rollback 後原樣往上拋 | `RecordRepository.upsert_records` / `delete_record_and_upsert`（股票 Change AD-5） | 活存/定存/保險的存檔與刪除全部改走這兩個方法，讓 BR-7「與存檔在同一交易寫入」直接成立 |
| 業務分類集合由 constants 定義，bootstrap 用建構子注入 Service | `COST_BASIS_INPUT.CATEGORIES` → `CostBasisService(cost_basis_categories=...)` | 新增 `PREMIUM_INPUT`、`BALANCE_INPUT` 與 `INPUT_MODE` 對照，一樣用注入（AD-1） |
| 錄入框帶入既有值，資料來源改變時才重新播種 | `amount_widget.seed_amount_inputs`（轉移 Change AD-2） | 三個新編輯器各用一組獨立的 widget key 和 seed key（AD-7） |
| 寫入成功後 `st.rerun()`，成功訊息走 flash | `views/input.py::_flash_and_rerun`（轉移 Change AD-3） | 新編輯器照用 |
| Plotly 金額折線：y 軸以萬元呈現，`customdata` 保留元做 hover，x 軸用 category | `charts.net_worth_line` | 新的各項目趨勢圖照同一套呈現契約（AD-8） |
| 配置頁的圖只算資產；市值留空不貢獻；缺月不補 | `AllocationService.snapshot` / `drift_series` / `net_worth_series` | 趨勢圖採同一口徑（AD-8） |

### 偏離既有做法的地方（各有 ADR）

- **「手填淨投入」的一般編輯器整個移除**（AD-7）：五個資產分類都改成自動推算，負債固定為 0，`views/input.py` 裡已經沒有任何一種項目需要手填淨投入。
- **`total_cost` / `realized_income` 兩欄的語意改成依分類而定**（AD-4）：股票/ETF 是「總成本／已實現收益合計」，保險是「累計已繳保費／本月領回金額」。這是刻意重用欄位，好讓 schema 和 CSV 契約都不用動。
- **活存/定存的連動重算會改寫舊制列**（AD-3）：股票 Change 的連動重算永遠不碰舊制列，這次 BR-7 明定活存/定存的下一筆即使是舊紀錄也要重算，所以活存/定存另訂一套規則。
- **刪除一個既有功能（項目間轉移）連同其 Service/Repository 方法**（AD-6）：不留 dead code。

---

## 架構決策

### AD-1：由單一對照決定「錄入方式」，在 `MonthlyInputService.resolve_input_mode` 集中解析

- **背景**：原本只有兩條分流（股票/ETF vs 其他），判斷是在 Page 呼叫 `cost_basis_service.uses_cost_basis`。這次變成四條：股票/ETF（總成本）、保險（累計保費）、活存/定存（餘額）、負債（應繳金額）。如果在 Page 寫一串 `if service_a.uses_x(...) elif service_b.uses_y(...)`，分類判斷就會散在 Page，而且「資產沒有對應錄入方式時怎麼辦」這種業務判斷也會落到 Page。
- **選擇**：
  1. `core/constants.py` 新增錄入方式代碼 `INPUT_MODE`（`COST_BASIS` / `PREMIUM` / `BALANCE` / `AMOUNT_DUE`）。新增 `PREMIUM_INPUT.CATEGORIES`、`BALANCE_INPUT.CATEGORIES`，和既有的 `COST_BASIS_INPUT.CATEGORIES` 並列，**這三個分類集合是唯一資料來源（SSoT）**。`INPUT_MODE.BY_ASSET_CATEGORY`（分類 → 錄入方式）由三個集合用 `dict.fromkeys` 組出來，不另外手寫一份。
  2. `MonthlyInputService` 新增 `resolve_input_mode(*, holding) -> str`：負債（`kind == liability_kind`）一律回 `AMOUNT_DUE`；資產用 `input_mode_by_category` 查表；資產分類查不到（例如 CSV 匯入時分類留空）就拋 `DataValidationError`，由 Page 轉成 `st.error`（Q4）。
  3. 對照表、`liability_kind`、`liability_input_mode` 都由 bootstrap 用建構子注入（04 §3.2），Service 不在方法內讀 constants。
  4. Page 只依回傳的錄入方式代碼分派到對應的編輯器（AD-7），不再呼叫 `uses_cost_basis`。
  5. 要有一個測試守住「`ASSET_CATEGORIES.ALL` 每個分類都恰好對應一種錄入方式、三個集合互不重疊」，日後新增分類卻漏設時會立刻失敗。
- **理由**：
  - 決定項目「怎麼錄入」是月度錄入的業務，`MonthlyInputService` 本來就負責月度錄入的純運算方法（帶入值、本月紀錄表），放在這裡最內聚。
  - 只有一個解析點，四種方式的互斥與完整性可以窮舉測試；`summarize_month` 判斷負債也能共用注入的 `liability_kind`。
- **否決方案**：
  - **Page 內 if/elif 串接各 Service 的 `uses_*`**：分類判斷散在 Page，「分類未對應」這個業務判斷也落進 View，違反 02 §2。否決。
  - **把解析器放進 `CostBasisService`**：該 Service 的職責是累計成本鏈推算，再加上「所有項目的錄入方式」會往 God Object 發展。否決。
  - **另開 `InputModeService`**：只有一個方法，`summarize_month` 也要判斷負債，拆開會讓同一份規則分成兩處注入。否決。
  - **分類對應不到時退回 BALANCE**：會讓分類設錯的項目被默默當成活存推算，錯誤看不見。否決（列 Q4 確認）。
- **後果**：
  - 正面：四條分流的規則集中在一處、可以測試；新增分類漏設對應時，測試會失敗。
  - 負面：`MonthlyInputService` 建構子多了三個參數，`tests/test_monthly_input.py` 的 `_service()` 和 `tests/test_input_view.py` 的 `_SpyMonthlyInputService` 要跟著補參數（機械式）。`CostBasisService.uses_cost_basis` 留作該 Service 內部守門和既有 SC-074 的測試對象，Page 不再呼叫它。

### AD-2：活存/定存以新的純運算 `BalanceInputService` 推算淨投入（BR-1），推算值落地在 `net_investment`

- **背景**：BR-1 規定活存/定存的淨投入＝本月餘額 − 前期餘額，使用者只填餘額；前期餘額取該項目上一筆紀錄的餘額，沒有紀錄就用主檔初始市值。這和股票的「總成本鏈」是不同的演算法：沒有過渡估算，前期值直接取 `market_value`，連動規則也不同（AD-3）。
- **選擇**：
  - 新增 `services/balance_input_service.py::BalanceInputService`（純運算，不碰 I/O、不 import streamlit），建構子注入 `balance_categories`（＝`BALANCE_INPUT.CATEGORIES`）。public 方法有三個：`derive`、`plan_save`、`plan_delete`。項目主檔和該項目的全部紀錄都由呼叫端當參數傳入（和 `CostBasisService` 一樣）。
  - **前期餘額**：在年月早於 M 的紀錄中，取**最近一筆 `market_value` 不為 None** 的值；都沒有就用 `holding.initial_market_value`（None 當 0）。`market_value` 為 None 的列（例如轉移 Change 累加寫入產生的「只有淨投入」列）跳過不看（Q1）。
  - 推算值寫進存檔列的 `net_investment`；`total_cost`、`realized_income`、`cash_dividend` 一律寫 None。
- **理由**：
  - 前期餘額跳過空白列，和 `ReturnService._value_series`「留空市值沿用上一個有值月份」的語意一致。這樣 TWR 的每段期初就是推算時用的前期餘額，活存/定存當月報酬會剛好是 0（proposal 已知、使用者接受）。
  - 和股票一樣落地在 `net_investment`，下游零改動，成功標準「報酬率等下游公式不變」由結構直接保證。
  - 獨立成一個 Service，演算法、守門和連動規則（AD-3）都封在一起，可以用固定紀錄序列窮舉邊界。
- **否決方案**：
  - **併入 `CostBasisService`**：前期值來源、過渡規則、連動規則都不一樣，硬塞會讓一個類別同時有兩套推算鏈和兩套連動規則。否決。
  - **併入 `MonthlyInputService`**：股票 Change AD-3 已否決過「把推算與重算規劃塞進注入了 Repo 的 MonthlyInputService」，理由相同（兩種抽象混在一起）。否決。
  - **前期餘額取「緊接的上一筆」，空白就當 0**：會把整個餘額當成淨投入，報酬大幅失真。否決。
- **後果**：
  - 正面：活存/定存只要填餘額；規則可以單獨測試。
  - 負面：`Container` 多一個欄位，`tests/test_bootstrap.py`、`tests/test_input_view.py` 的 Container 替身要補上。

### AD-3：活存/定存的連動重算只看「下一筆有餘額的列」，而且只有它的前期餘額真的改變時才重算（BR-7）

- **背景**：BR-7 規定修改或刪除某月活存/定存餘額時，緊接的下一筆要一起重算，**下一筆即使是本功能上線前的舊紀錄也要更新**；BR-6 則規定既有歷史紀錄保留原值。兩條規則要同時成立，就必須講清楚「什麼時候才算動到下一筆」。股票 Change AD-4 的做法是「往後重算所有新制列、只回傳有變的列」，那是建立在新制列的淨投入本來就是推算值（重算是冪等的）這個前提上。活存/定存的舊紀錄是**手填值**，一重算就會被改寫，所以不能套同一個判斷。
- **選擇**：`plan_save` / `plan_delete` 先在記憶體中套用這次異動（替換、插入或移除月份 M），然後：
  1. 找出年月晚於 M、**`market_value` 不為 None** 的第一筆紀錄 N（Q2）。
  2. 分別算 N 在異動**前**和異動**後**的前期餘額（AD-2 的規則）。
  3. **前期餘額沒變**（容許浮點誤差）時不碰 N。例如重存同一個餘額，就不會把 N 的舊手填值洗掉，BR-6 成立。
  4. **前期餘額有變**時，N 的淨投入＝N 的餘額 − 新的前期餘額；N 不分新舊一律更新（BR-7 字面）；和 N 的既存值相同時不回傳。
  5. N 之後的列都不碰：每筆的推算只依賴自己和前一筆有餘額的列，N 的餘額沒變，N 之後的前期值也就沒變。
  6. 回傳 `[存檔列, N（有變時）]` 或 `[N（有變時）]`。Page 交給 `upsert_records` / `delete_record_and_upsert`，在單一交易內寫入（BR-7「與存檔同一交易」）。
- **理由**：
  - 用「前期值有沒有變」來觸發重算，正好表達 BR-7 的理由欄「因前期值已改變」，也避免單純重存就改寫舊紀錄。
  - 中間插入（在兩筆既有紀錄之間新增月份）、刪除最早一筆（N 退回用初始市值）、刪除中間一筆，都由同一套「前後比較」涵蓋，不用分情況寫。
- **否決方案**：
  - **沿用股票 AD-4（往後重算全部、只回傳有變的列）**：會把 M 之後所有舊制手填值都改成餘額差，違反 BR-6。否決。
  - **不論前期值有沒有變，都重算緊接的下一筆**：重存同一餘額也會洗掉下一筆的舊手填值，超出 BR-7 的理由範圍。否決。
  - **只看字面上「緊接的下一筆」，即使它餘額空白**：空白列無從推算（餘額 − 前期 不成立），等於什麼都不做；而真正的前期值改變會傳到後面第一筆有餘額的列，結果會漏算。否決（列 Q2 確認）。
- **後果**：
  - 正面：BR-6 和 BR-7 同時成立；重算範圍最多一筆，測試容易窮舉。
  - 負面：舊紀錄 N 一旦因前期值改變而被重算，原本的手填淨投入就不可回復（這是 BR-7 明定的行為，列技術債知會）。

### AD-4：保險併入 `CostBasisService` 的累計成本鏈，重用 `total_cost` / `realized_income` 兩欄存累計保費與領回（BR-2、BR-6、BR-7），schema 與 CSV 契約不變

- **背景**：BR-2 規定保險填累計已繳保費、解約金、本月領回金額，淨投入＝（本月累計保費 − 前期累計保費）− 本月領回金額；前期累計保費比照股票的前期總成本規則（含 BR-6 的過渡估算）；領回不可為負。proposal 把「保險領回金額的儲存欄位與 CSV 契約」交給設計決定。這條公式和股票的「（本月總成本 − 前期總成本）− 已實現收益」**結構完全相同**。
- **選擇**：
  1. **儲存欄位重用**：累計已繳保費 → `total_cost`；解約金 → `market_value`；本月領回金額 → `realized_income`；`cash_dividend` 寫 None。**不加欄位、不動 schema、不動 CSV 欄位契約**（`RECORDS_COLUMNS` / `RECORDS_REQUIRED_COLUMNS` 維持原樣）。CSV 匯出入、replace_all 都已經支援這幾欄，自然可以往返。
  2. **「新制保險列」的判定**和股票相同：`total_cost IS NOT NULL`。保險舊紀錄的 `total_cost` 都是 NULL，所以過渡規則（前期＝初始成本＋之前所有淨投入）和連動重算（只重算新制列）都可以直接沿用 `_derive_from_realized_income` 與 `_recalculate_following`。
  3. `CostBasisService` 建構子新增注入 `premium_categories`（＝`PREMIUM_INPUT.CATEGORIES`），新增三個 public 方法：`derive_premium`、`plan_save_premium`、`build_premium_prefill`。`plan_delete` 的守門放寬成「股票/ETF 或保險」，兩條鏈共用。`uses_cost_basis`、`derive`、`plan_save`、`build_cost_basis_prefill` 的簽名和語意都不變（股票）。
  4. 驗證：`derive_premium` / `plan_save_premium` 在領回為負時拋 `DataValidationError`（BR-2）；分類不屬於保險時也拋 `DataValidationError`。
  5. **BR-7 對保險的實際效果**：沿用股票 Change AD-4，往後重算新制保險列、只回傳有變的列。保險舊紀錄沒有累計保費，無從用 BR-2 公式重算，所以**不會被更新**（這和 BR-7「下一筆即使是舊紀錄也更新」的字面不同，列 Q3 確認）。舊紀錄之後的第一筆新制列，因為過渡規則的加總涵蓋到被改的那一筆，仍會正確重算。
  6. `MONTHLY_RECORDS_TABLE`、`MonthlyRecordModel`、`CSV_EXPORT`、`NetInvestmentDerivation` 的 docstring 要寫明兩欄依分類而定的語意。
- **理由**：
  - 公式相同，重用既有推算鏈和連動重算，等於直接繼承股票 Change 已驗證過的邊界（首筆、過渡、刪除、中間插入）；新程式碼只有輸入的組裝和守門。
  - 零 schema、零 CSV 變更，新舊備份都能照常匯入；新匯出的保險資料不會遺失。
  - D17「明確欄位」原則講的是持有主檔屬性，不禁止月度欄位依分類有不同的業務名稱。「累計已繳保費」本質上就是保險的成本基礎，「領回」也就是從該項目拿回的現金，語意對得上。
- **否決方案**：
  - **新增 `cumulative_premium`、`withdrawal` 兩欄**：要做加欄遷移、改 CSV 契約，舊 CSV 相容邏輯再擴一次。推算鏈也得再寫一份，或把欄位名當參數傳來傳去，換來的只有欄名好讀一點。否決。
  - **用 `cash_dividend` 欄存領回、借用股票的 `derive(realized_pnl=0, cash_dividend=領回)`**：語意錯置（保險沒有股利），帶入值的還原邏輯也會被扭曲。否決。
  - **另開 `PremiumInputService`**：Service 之間不互相注入（house-dashboard AD-3），要共用推算鏈只能複製程式碼，或把它抽成模組級函式（違反 02 §5「必須以類別實作」）。否決。
- **後果**：
  - 正面：保險推算零新演算法；CSV 不變；BR-6 過渡規則對保險自然成立。
  - 負面：
    - `total_cost` / `realized_income` 的業務語意依分類而定，讀這兩欄的地方（目前只有 `views/input.py` 的本月紀錄表）要依分類呈現對應的名稱（AD-5）。
    - `CostBasisService` 的 public 方法從 6 個變成 8 個（移除 `transfer_records_to_write`、新增 3 個），但都屬於同一條累計成本鏈。
    - 項目從股票切換成保險（或反過來）時，已落地的列不會回溯（沿用股票 Change 的技術債）。

### AD-5：負債改走「應繳金額」錄入，淨投入固定為 0；本月紀錄表把負債金額獨立成一欄（BR-3、BR-4）

- **背景**：BR-3 規定負債只填應繳金額、淨投入固定 0；BR-4 規定負債的金額欄在畫面上一律稱「應繳金額」。proposal 把「負債在本月紀錄表的欄名呈現方式」交給設計決定。負債的金額照舊存在 `market_value` 欄（淨值計算 `net_worth_series` 讀這一欄），只是畫面上換名稱。
- **選擇**：
  - **存檔**：`MonthlyInputService.build_amount_due_record(*, holding, year_month, amount_due) -> MonthlyRecordModel`，回傳 `market_value=amount_due`、`net_investment=0.0`、成本欄全 None；`holding` 不是負債時拋 `DataValidationError`。Page 拿到後呼叫既有的 `upsert_record`；刪除呼叫既有的 `delete_record`。負債沒有推算鏈，不需要連動重算，也就不需要 compound 寫入。
  - **錄入框**：只有一個 `amount_input`，標籤為「應繳金額」；帶入值沿用 `build_record_prefill` 的 `market_value`。
  - **本月紀錄表**（`summarize_month` → `MonthRecordRow`）：新增 `is_liability: bool`（Service 用注入的 `liability_kind` 判斷）。Page 的表格把金額拆成兩欄：資產的值放在「市值 / 餘額」欄，負債的值放在「應繳金額」欄，另一欄留空。負債列的未填提醒改用「應繳金額」的字樣，資產列維持原本的提醒（具體字樣由 SC 定）。`total_cost` / `realized_income` 兩欄的表頭改成能同時涵蓋股票和保險的名稱（例如「總成本 / 累計保費」、「已實現收益 / 領回」，具體字樣由 SC 定，Q5）。
  - **CSV 欄名、DB 欄名都不改**（`market_value` 是技術契約，不是畫面）。
  - 淨值圖的「總負債」是彙總線，不是單一負債的金額欄，**維持原名**（Q8）。
- **理由**：
  - 「淨投入固定 0」雖然只是常數，仍是業務規則（BR-3），放在 Service 才能用 SC 測試守住，不寫死在 Page。
  - 表格拆欄，資產列和負債列的金額語意一眼可分，表頭也不必寫成「市值 / 餘額 / 應繳金額」這種三合一。
- **否決方案**：
  - **單一金額欄、表頭寫「市值 / 應繳金額」**：同一欄混兩種語意，和 BR-4「負債一律稱應繳金額」的精神不合。否決（列 Q5 確認）。
  - **另開 `amount_due` DB 欄**：淨值、帶入、CSV 全部要改，違反 proposal「下游不動」。否決。
  - **Page 直接 `MonthlyRecordModel(net_investment=0.0)`**：BR-3 沒有 Service 層的測試落點。否決。
- **後果**：
  - 正面：負債錄入只剩一格；BR-3 有測試落點；欄名呈現集中在 Page。
  - 負面：本月紀錄表多一欄。舊負債紀錄如果有非 0 的手填淨投入，重存之後會變成 0，沒重存的照舊（BR-6；下游本來就不讀負債的淨投入，沒有影響）。

### AD-6：完整移除「項目間轉移」功能與其 Service／Repository 方法（BR-5）

- **背景**：BR-5 規定移除項目間轉移，因為所有分類的淨投入都已自動推算，再寫一次轉移就會重複計算；股票/ETF 欄旁「存入有追蹤帳戶需另做轉移」的提示也一起移除。
- **選擇**：刪除以下程式碼，**不保留 dead code**：
  - `views/input.py::_render_transfer`，以及 `render()` 中對它的呼叫。
  - `views/input.py::_render_cost_basis_editor` 中的轉移提示 `st.caption`。
  - `MonthlyInputService.build_transfer_pair`，以及模組 docstring 中「轉移語意」那一段。
  - `CostBasisService.transfer_records_to_write`。
  - `RecordRepository.accumulate_net_investments` 與 `_ACCUMULATE` SQL，模組 docstring 中的 compound method 清單同步更新。
  - 對應測試一併刪除，SC 卡片用 `delta: REMOVED` 標記移除（見〈受影響的既有 SC 與測試〉）。
  - **既有資料不動**：過去轉移寫入的淨投入、轉移產生的「只有淨投入、市值空白」列都照原樣保留（BR-6）。活存/定存推算前期餘額時，這些空白列會被跳過（AD-2）。
- **理由**：功能已經沒有呼叫端，留著只會誤導後續維護者以為轉移仍然有效，而且 `accumulate_net_investments` 是唯一的「遞增寫入」原語，留著反而可能被誤用成重複計算。
- **否決方案**：
  - **只拿掉 UI、保留 Service/Repo 方法**：dead code，而且 SC-008/037/079/080/086 的測試還會繼續通過，讓人誤以為行為仍然存在。否決。
  - **保留轉移，改成只記帳不寫淨投入**：proposal 沒有這個需求。否決。
- **後果**：
  - 正面：程式碼和規格都少了一整塊；BR-5 的「一出一進相抵」由兩端各自的推算自然成立。
  - 負面：要刪的測試和 SC 卡片數量不少（見下方對照表），scenario-author 和 task-planner 要逐一處理。

### AD-7：月度錄入頁依錄入方式分派到四個編輯器，每個編輯器用獨立的 widget key；存檔一律「Service 規劃 → Repository 寫入」

- **背景**：AD-1 解析出四種錄入方式，每種的欄位、預覽、寫入路徑都不一樣。原本的「一般分類編輯器」（市值＋手填淨投入）在本 Change 之後已經沒有任何項目會用到。
- **選擇**：`views/input.py::_render_record_editor` 選定項目後呼叫 `input_service.resolve_input_mode(holding=...)`，依代碼分派：

  | 錄入方式 | 編輯器 | 欄位（`amount_input`） | 預覽 | 存檔 | 刪除 |
  |---------|--------|----------------------|------|------|------|
  | `COST_BASIS` | `_render_cost_basis_editor`（既有，只拿掉轉移提示） | 總成本、現值、已實現損益、現金股利 | `derive`（既有） | `plan_save` → `upsert_records` | `plan_delete` → `delete_record_and_upsert` |
  | `PREMIUM` | `_render_premium_editor`（新增） | 累計已繳保費、解約金、本月領回金額 | `derive_premium`：前期累計保費、推算淨投入、過渡估算提醒 | `plan_save_premium` → `upsert_records` | `plan_delete` → `delete_record_and_upsert` |
  | `BALANCE` | `_render_balance_editor`（新增） | 餘額 | `balance_input_service.derive`：前期餘額、推算淨投入（Q6） | `balance_input_service.plan_save` → `upsert_records` | `balance_input_service.plan_delete` → `delete_record_and_upsert` |
  | `AMOUNT_DUE` | `_render_amount_due_editor`（新增） | 應繳金額 | 無 | `build_amount_due_record` → `upsert_record` | `delete_record` |

  - **一般編輯器移除**：`_KEY_RECORD_NET_INVESTMENT` 等手填淨投入的 key 一併拿掉。
  - **每個編輯器用獨立的 widget key 與 seed key**（例如 `balance_*`、`premium_*`、`amount_due_*`），避免在不同錄入方式的項目之間切換時讀到前一種編輯器留下的 session state。帶入值：BALANCE 和 AMOUNT_DUE 用 `build_record_prefill(...).market_value`；PREMIUM 用 `build_premium_prefill`。
  - BALANCE 和 PREMIUM 都會讀 `record_repo.read_holding_records(holding_id=...)`，同一份清單同時給預覽和規劃使用；預覽的解析錯誤和推算拒絕，照股票編輯器既有的兩段式處理（`_render_derivation_preview` 模式）。
  - 頁首 `st.info` 的賣出／不再持有說明，要改寫成四種方式各自的填法（例如活存清空填餘額 0、保險解約時解約金填 0、領回填實收），具體文案由 SC 定。
- **理由**：Page 只做「解析 → 委派 → 呈現」，分類判斷和推算都在 Service，符合 02 §4。四個編輯器分開寫，彼此不會干擾，也延續股票 Change AD-10 的做法。
- **否決方案**：
  - **四種方式共用同一組 widget key**：在活存和保險之間切換時，靠 seed 來源比對雖然通常會重新播種，但兩邊欄位數不同，殘留的 key 會變成難查的狀態問題。否決。
  - **保留一般編輯器作為退路**：沒有任何項目會走到，等於 dead code。分類對應不到的資產，改在 `resolve_input_mode` 拋錯（AD-1）。否決。
- **後果**：
  - 正面：每種錄入方式的流程獨立、可測；BR-7 的同交易寫入沿用既有 compound method。
  - 負面：`views/input.py` 刪掉轉移區塊後還會再淨增約 100～150 行（列技術債，建議實作時把共用的預覽骨架抽成私有函式）；`tests/test_input_view.py` 的 Container 替身、Record 替身、分類切換測試都要更新。

### AD-8：資產配置頁新增「各項目市值趨勢」折線圖，`AllocationService` 算序列、`charts` 畫圖；缺月和空白市值一律畫成斷點（BR-8）

- **背景**：BR-8 要一張折線圖，每個資產項目一條線，橫軸月份、縱軸萬元，可以點圖例隱藏或顯示，負債不列入。proposal 把「缺月／市值空白的畫法」交給設計決定。
- **選擇**：
  - **資料層**：`AllocationService.holding_value_trend(*, range_df, holdings) -> HoldingValueTrend`（純運算）：
    - 先用既有的 `core.utils.filter_asset_records` 排除負債。
    - x 軸節點＝**資產紀錄的有資料月聯集**，依時間排序（和其他圖一致，缺月不補插）。
    - 每個「在區間內至少有一筆紀錄」的資產項目產生一條序列，用 `holding_id` 識別（項目名稱可能重複），名稱取主檔現名；序列的順序照傳入的 `holdings` 順序。
    - 序列值和 x 軸節點一一對齊：該月有紀錄且市值不為 None/NaN 就填市值（元）；**該月沒有紀錄或市值空白就填 None**（Q7）。
    - 購屋標記的資產也照畫（D14 只排除目標偏離和自由數字進度，不排除這張圖）。
  - **呈現層**：`charts.holding_value_lines(*, trend) -> go.Figure`（純函式）：每條序列一個 `go.Scatter(mode="lines+markers", connectgaps=False)`，y 以萬元呈現，`customdata` 保留元給 hover，hover 樣板和 `net_worth_line` 同一風格；`xaxis_type="category"`，並用 `categoryorder="array"` 加上 `categoryarray=trend.year_months` 固定月份順序；圖例標題「項目」。序列為空時回傳空的 `go.Figure()`。
  - **頁面**：`views/allocation.py` 新增 `_render_holding_trend`，沿用 `render()` 已讀好的同一份 `range_df`（不增加 I/O），建議放在「淨值趨勢」之後（同為萬元折線）。
  - 點圖例隱藏或顯示是 Plotly 的內建行為（`legend.itemclick` 預設就是 toggle），不需要額外程式碼。
- **理由**：
  - 空白市值畫成斷點，和配置頁其他圖「市值留空不貢獻」的口徑一致，也如實反映「該月沒填」，不會偽造數值；出清的項目會在市值 0 那個月之後自然中斷。
  - 每條序列都對齊完整的 x 軸並明示 `categoryarray`，避免 Plotly 的 category 軸照各 trace 首次出現的順序排月份（某項目較晚才開始持有時，月份順序會亂掉）。
  - 「資料層算、元件層畫、Page 委派」和既有四張圖同一個分工。
- **否決方案**：
  - **空白市值沿用前值**（報酬率口徑）：會畫出沒有填過的數字，和配置頁其他圖的口徑不一致。否決（Q7）。
  - **每個 trace 只帶自己有值的月份、讓 Plotly 自己連線**：缺月會被連成直線，看起來像有資料；category 軸的月份順序也可能錯亂。否決。
  - **用 `px.line` 長表**：處理 None 斷點和固定月份順序比較不直接，而且 `holding_id` 和名稱的對應要另外處理。否決。
- **後果**：
  - 正面：BR-8 全部用既有依賴就能做到；單元測試可以直接斷言 trace 數量、x 軸順序、None 位置和萬元換算。
  - 負面：項目多時圖例會很擠（目前規模可以接受）；項目改名後，整條線都會用新名稱。

### AD-9：不做任何資料遷移，也不回溯重算（BR-6）

- **背景**：BR-6 規定既有歷史紀錄的淨投入保留原值，只有新存檔或修改的月份套用新規則。
- **選擇**：本 Change **沒有 schema 變更、沒有資料遷移、沒有 CSV 契約變更**。新規則只在使用者存檔或刪除時，經由 AD-2/3/4/5 的規劃方法生效；CSV 匯入照原值還原，不重算（沿用股票 Change AD-9）。
- **理由**：AD-4 重用既有欄位之後就不需要加欄；推算一律在寫入時落地，讀取端完全不變。
- **否決方案**：**上線時把活存/定存歷史一次全部改成餘額差**：違反 BR-6，也會改動使用者已核對過的歷史報酬。否決。
- **後果**：
  - 正面：上線零風險，舊資料、舊備份都照常可用。
  - 負面：歷史月份的活存/定存報酬仍然反映舊的手填口徑，要等使用者修改某月時，才會因 AD-3 連帶改到下一筆。

---

## 技術選型

### TD-1：各項目趨勢圖用 Plotly `graph_objects.Scatter` 多 trace＋`connectgaps=False`＋category 軸固定順序

- **推薦**：`go.Scatter(mode="lines+markers", connectgaps=False)`，每個項目一個 trace，`layout.xaxis` 設 `type="category"`、`categoryorder="array"`、`categoryarray=<月份清單>`（信心度：High）
- **理由**：
  - 已在本機 venv（plotly 6.9.0）查證：y 值含 None 的 trace 可以正常建立，`connectgaps=False` 會讓線在 None 處斷開；`categoryorder="array"` 加 `categoryarray` 可以固定 category 軸的順序。
  - 圖例點擊切換顯示是 Plotly 預設行為（`legend.itemclick` 預設為 toggle，`st.plotly_chart` 保留互動）。
  - 呈現契約（萬元、`customdata`、hover 樣板）和既有的 `net_worth_line` 一致。

### TD-2：其餘技術棧全部沿用，不新增依賴

- **推薦**：Streamlit 1.59.1＋libsql(Turso)＋Pydantic＋pandas＋Plotly，全部沿用（信心度：High）
- **理由**：proposal 明定沒有新的外部依賴。交易控制沿用既有的 `upsert_records` / `delete_record_and_upsert`（股票 Change TD-3 已查證 libsql 支援 commit/rollback），浮點比較沿用 `math.isclose`（和 `_recalculate_following` 同樣的容差）。

---

## 介面契約

> 以下是型別簽名與語意契約（技術層）。金額單位是 TWD（float，UI 輸入取整數），年月是 `'YYYY-MM'`。
> **行為細節（邊界值、錯誤路徑、提示文案）由 1-3 Scenarios 用 BR 編號定義，這裡不重述。**

### 1. 常數（`core/constants.py`）

```python
class COST_BASIS_INPUT:            # 既有，不變
    CATEGORIES = frozenset({ASSET_CATEGORIES.TW_STOCK, ASSET_CATEGORIES.US_STOCK})


class PREMIUM_INPUT:
    """以「累計已繳保費＋本月領回」推算月淨投入的資產分類（BR-2）。由 bootstrap 注入 CostBasisService。"""

    CATEGORIES = frozenset({ASSET_CATEGORIES.INSURANCE})


class BALANCE_INPUT:
    """以「本月餘額 − 前期餘額」推算月淨投入的資產分類（BR-1）。由 bootstrap 注入 BalanceInputService。"""

    CATEGORIES = frozenset({ASSET_CATEGORIES.DEMAND_DEPOSIT, ASSET_CATEGORIES.TIME_DEPOSIT})


class INPUT_MODE:
    """月度錄入方式代碼：決定錄入欄位與當月淨投入的來源（AD-1）。

    BY_ASSET_CATEGORY 由三個 *_INPUT.CATEGORIES 組出（三個集合是唯一資料來源）；
    負債不查表，一律為 AMOUNT_DUE。
    """

    COST_BASIS = "cost_basis"   # 股票/ETF：總成本＋現值＋已實現損益＋現金股利
    PREMIUM = "premium"         # 保險：累計已繳保費＋解約金＋本月領回金額
    BALANCE = "balance"         # 活存/定存：只填餘額
    AMOUNT_DUE = "amount_due"   # 負債：只填應繳金額，淨投入固定 0
    BY_ASSET_CATEGORY = {
        **dict.fromkeys(COST_BASIS_INPUT.CATEGORIES, COST_BASIS),
        **dict.fromkeys(PREMIUM_INPUT.CATEGORIES, PREMIUM),
        **dict.fromkeys(BALANCE_INPUT.CATEGORIES, BALANCE),
    }
    # 注意：類別本體內不可用 comprehension 參照 COST_BASIS 等類別屬性（作用域限制），
    # dict.fromkeys 寫法可以；本類別須定義在三個 *_INPUT 類別之後。


class MONTHLY_RECORDS_TABLE:       # 欄位不變，只更新 docstring：
    # total_cost：股票/ETF＝目前總成本；保險＝累計已繳保費。不為 NULL 就是新制成本鏈列，其 net_investment 是推算值
    # realized_income：股票/ETF＝已實現損益＋現金股利；保險＝本月領回金額
    # market_value：資產＝市值（活存/定存＝餘額、保險＝解約金、股票＝現值）；負債＝應繳金額
    ...

# CSV_EXPORT：欄位與強制欄位集都不變；docstring 補上 total_cost/realized_income 依分類而定的語意（AD-4）
```

### 2. Models

```python
# models/record.py：MonthlyRecordModel 欄位不變，docstring 依上方語意更新（負債 market_value＝應繳金額；
#   total_cost/realized_income 在保險上的語意）

# models/results.py
class NetInvestmentDerivation(BaseModel):        # 既有，欄位不變；docstring 補上保險時 previous_total_cost＝前期累計保費
    previous_total_cost: float
    is_transition_estimate: bool
    net_investment: float


class BalanceDerivation(BaseModel):
    """活存/定存當月淨投入推算結果（BR-1，存檔前預覽用）。

    previous_balance 取年月早於推算月、最近一筆有餘額的紀錄；都沒有則為主檔初始市值（None 當 0）。
    """
    previous_balance: float
    net_investment: float


class PremiumEditorPrefill(BaseModel):
    """保險錄入框的帶入值。沒有紀錄時累計保費／解約金留空（None）、領回為 0。"""
    cumulative_premium: float | None
    surrender_value: float | None
    withdrawal: float


class MonthRecordRow(BaseModel):                 # 既有，新增一欄
    ...                                          # 既有欄位不變
    is_liability: bool                           # AD-5：Page 依此把金額放到「市值 / 餘額」或「應繳金額」欄


class HoldingValueSeries(BaseModel):
    """單一資產項目跨月市值序列（BR-8）。market_values 與 HoldingValueTrend.year_months 一一對齊；
    該月沒有紀錄或市值空白時為 None（圖上畫成斷點）。"""
    holding_id: int
    name: str
    market_values: list[float | None]


class HoldingValueTrend(BaseModel):
    """各資產項目市值趨勢（BR-8）。year_months 為資產紀錄有資料月的聯集，依時間排序。"""
    year_months: list[str]
    series: list[HoldingValueSeries]
```

### 3. Repositories

```python
# repositories/record_repository.py
#   刪除：accumulate_net_investments、_ACCUMULATE（AD-6）；模組 docstring 的 compound method 清單同步更新
#   其餘方法簽名與語意不變；活存/定存/保險的存檔與刪除沿用 upsert_records / delete_record_and_upsert，
#   負債沿用 upsert_record / delete_record

# repositories/schema_repository.py：不變（AD-9）
```

### 4. Services

```python
# services/monthly_input_service.py
class MonthlyInputService:
    def __init__(
        self, *, holding_repo: _HoldingReader, record_repo: _RecordReader,
        input_mode_by_category: Mapping[str, str],   # INPUT_MODE.BY_ASSET_CATEGORY
        liability_kind: str,                         # HOLDING_KIND.LIABILITY
        liability_input_mode: str,                   # INPUT_MODE.AMOUNT_DUE
    ) -> None: ...

    def resolve_input_mode(self, *, holding: HoldingModel) -> str: ...
        # 負債 → liability_input_mode；資產 → 查 input_mode_by_category；
        # 資產分類查不到（None 或不在表內）→ DataValidationError（AD-1，Q4）

    def build_amount_due_record(
        self, *, holding: HoldingModel, year_month: str, amount_due: float
    ) -> MonthlyRecordModel: ...
        # market_value=amount_due、net_investment=0.0、成本欄全 None；holding 非負債 → DataValidationError（AD-5，BR-3）

    def summarize_month(...) -> list[MonthRecordRow]: ...   # 簽名不變；每列多帶 is_liability（AD-5）
    def build_record_prefill(...) -> RecordEditorPrefill: ...   # 不變；BALANCE / AMOUNT_DUE 編輯器只取 market_value
    def prefill_from_previous(...) -> list[MonthlyRecordModel]: ...   # 不變
    # 刪除：build_transfer_pair（AD-6）


# services/balance_input_service.py（新增，純運算：無 I/O、無 Streamlit）
class BalanceInputService:
    """活存/定存以餘額變動推算月淨投入，以及修改/刪除時下一筆的連動重算（BR-1、BR-7）。"""

    def __init__(self, *, balance_categories: frozenset[str]) -> None: ...

    def derive(
        self, *, holding: HoldingModel, records: list[MonthlyRecordModel], year_month: str,
        balance: float,
    ) -> BalanceDerivation: ...
        # previous_balance：records 中 ym < year_month、market_value 不為 None 的最近一筆；
        #   沒有則 holding.initial_market_value（None 當 0）（AD-2，Q1）
        # net_investment ＝ balance − previous_balance

    def plan_save(
        self, *, holding: HoldingModel, records: list[MonthlyRecordModel], year_month: str,
        balance: float,
    ) -> list[MonthlyRecordModel]: ...
        # [存檔列（market_value=balance、net_investment=推算值、成本欄 None）,
        #  *下一筆有餘額列（只在其前期餘額改變、且重算值和既存值不同時）]（AD-3）

    def plan_delete(
        self, *, holding: HoldingModel, records: list[MonthlyRecordModel], year_month: str,
    ) -> list[MonthlyRecordModel]: ...
        # 移除 year_month 後，回傳 [下一筆有餘額列]（條件同上）或 []（AD-3）

    # 前置條件：records 只含該 holding 的紀錄（任意順序）；holding 分類不在 balance_categories → DataValidationError
    # 浮點比較容差與 CostBasisService._recalculate_following 一致（math.isclose, abs_tol=1e-6）


# services/cost_basis_service.py（既有，擴充保險；股票既有方法簽名不變）
class CostBasisService:
    def __init__(
        self, *, cost_basis_categories: frozenset[str], premium_categories: frozenset[str]
    ) -> None: ...

    # 不變：uses_cost_basis / derive / plan_save / build_cost_basis_prefill（股票/ETF）

    def derive_premium(
        self, *, holding: HoldingModel, records: list[MonthlyRecordModel], year_month: str,
        cumulative_premium: float, withdrawal: float,
    ) -> NetInvestmentDerivation: ...
        # 守門：分類屬保險、withdrawal >= 0，否則 DataValidationError（BR-2）
        # 委派 _derive_from_realized_income(total_cost=cumulative_premium, realized_income=withdrawal)
        #   → 前期累計保費規則（含 BR-6 過渡估算）與股票相同

    def plan_save_premium(
        self, *, holding: HoldingModel, records: list[MonthlyRecordModel], year_month: str,
        surrender_value: float, cumulative_premium: float, withdrawal: float,
    ) -> list[MonthlyRecordModel]: ...
        # 存檔列：market_value=surrender_value、total_cost=cumulative_premium、
        #   realized_income=withdrawal、cash_dividend=None、net_investment=推算值
        # 回傳 [存檔列, *年月之後推算值有變的新制列]（沿用 _recalculate_following，AD-4）

    def plan_delete(...) -> list[MonthlyRecordModel]: ...
        # 簽名不變；守門放寬為「股票/ETF 或保險」（兩條鏈共用）

    def build_premium_prefill(
        self, *, records: list[MonthlyRecordModel], year_month: str
    ) -> PremiumEditorPrefill: ...
        # 該月有紀錄：cumulative_premium=total_cost、surrender_value=market_value、withdrawal=realized_income or 0
        # 沒有紀錄：(None, None, 0.0)

    # 刪除：transfer_records_to_write（AD-6）


# services/allocation_service.py（既有，新增一個方法）
class AllocationService:
    def holding_value_trend(
        self, *, range_df: pd.DataFrame, holdings: list[HoldingModel]
    ) -> HoldingValueTrend: ...
        # 只含資產（filter_asset_records）；x 軸＝資產紀錄有資料月聯集；每個在區間內有紀錄的資產項目一條序列，
        # 依 holdings 順序；沒有紀錄或市值空白（None/NaN）→ None；沒有資產資料 → year_months=[]、series=[]（AD-8）
```

### 5. 圖表元件（`src/asset_lab/charts.py`，新增一個純函式）

```python
def holding_value_lines(*, trend: HoldingValueTrend) -> go.Figure: ...
    # 每條 series 一個 go.Scatter：x=trend.year_months、y=萬元（None 保持 None）、customdata=元、
    #   mode="lines+markers"、connectgaps=False、name=series.name、hover 樣板沿用 _NET_WORTH_HOVER_TEMPLATE 風格
    # layout：xaxis_title="時間"、xaxis_type="category"、xaxis_categoryorder="array"、
    #   xaxis_categoryarray=trend.year_months、yaxis_tickformat=",.1f"、legend_title_text="項目"
    # series 為空 → 空的 go.Figure()（TD-1）
```

### 6. Views／組裝

| 檔案 | 異動 |
|------|------|
| `views/input.py` | `_render_record_editor` 改成依 `resolve_input_mode` 分派（AD-7）；新增 `_render_premium_editor`、`_render_balance_editor`、`_render_amount_due_editor`；移除一般編輯器（手填淨投入）、`_render_transfer`、股票編輯器的轉移提示（AD-6）；本月紀錄表依 `is_liability` 拆成「市值 / 餘額」和「應繳金額」兩欄，成本欄表頭改成涵蓋保險的名稱（AD-5）；頁首賣出說明改寫（文案由 SC 定）；模組 docstring 同步更新 |
| `views/allocation.py` | 新增 `_render_holding_trend`，用同一份 `range_df`，建議放在淨值趨勢之後（AD-8）；模組 docstring 的圖表清單同步更新 |
| `bootstrap.py` | `Container` 新增 `balance_input_service: BalanceInputService`；`MonthlyInputService(..., input_mode_by_category=INPUT_MODE.BY_ASSET_CATEGORY, liability_kind=HOLDING_KIND.LIABILITY, liability_input_mode=INPUT_MODE.AMOUNT_DUE)`；`CostBasisService(cost_basis_categories=COST_BASIS_INPUT.CATEGORIES, premium_categories=PREMIUM_INPUT.CATEGORIES)`；`BalanceInputService(balance_categories=BALANCE_INPUT.CATEGORIES)` |
| `views/settings.py`、`views/data_io.py`、`app.py` | 不變 |

---

## 受影響的既有 SC 與測試（交接給 1-3 scenario-author／1-4 task-planner）

| 對象 | 影響 | 建議處理 |
|------|------|---------|
| **SC-008**（項目間轉移成對記錄淨投入） | 功能移除（BR-5） | `delta: REMOVED`；刪除 `tests/test_monthly_input.py::TestBuildTransferPair` |
| **SC-037**（轉移輸入防呆） | 功能移除 | `delta: REMOVED`；刪除 `TestTransferInputGuard` |
| **SC-079**、**SC-080**（轉移時濾掉股票/ETF 端） | 功能移除 | `delta: REMOVED`；刪除 `tests/test_cost_basis.py::TestTransferRecordsToWrite` |
| **SC-086**（轉移累加寫入） | 功能移除 | `delta: REMOVED`；刪除 `tests/test_monthly_input.py` 的 accumulate 測試群 |
| **SC-085**（批次寫入失敗不留部分結果） | `accumulate_net_investments` 的 rollback 測試失去對象；`upsert_records` / `delete_record_and_upsert` 的 rollback 測試仍然有效，而且現在也涵蓋活存/定存/保險 | 修訂卡片：拿掉轉移相關敘述，觸發情境擴大到活存/定存/保險；刪除 `test_sc085_accumulate_failure_rolls_back_all_writes` |
| **SC-009**（非股票項目賣出：記市值 0 與負淨投入；例子是保險解約） | 保險改填累計保費＋解約金＋領回，解約月份由推算得到負淨投入（落地結果相同），卡片中「使用者輸入淨投入 −530000」的敘述不再成立 | 修訂卡片，改用 BR-2 的輸入方式；`test_sc009_*` 只驗 Repository/Return 層，若仍然成立可保留，由 scenario-author 判斷 |
| **SC-087**（一般分類錄入框帶入既有值；例子是活存的市值＋淨投入） | 一般編輯器已移除；活存只剩餘額一格 | 修訂卡片，改成活存/定存的餘額帶入（及負債的應繳金額帶入）；`build_record_prefill` 的 Service 層測試仍然有效 |
| **SC-089**（本月已存紀錄表） | 負債列改顯示在「應繳金額」欄、提醒字樣改變；卡片中「執行一次涉及活存的項目間轉移」的步驟已經不存在 | 修訂卡片（BR-4、BR-5）；`summarize_month` 測試補上 `is_liability` 斷言 |
| SC-006（新增/編輯/刪除單列，例子是「填入市值、淨投入 0」） | Repository 層的 CRUD 行為不變；卡片的 UI 敘述（手填淨投入）可能過時 | scenario-author 判斷是否修訂措辭；Repository 測試不受影響 |
| SC-074（`uses_cost_basis` 只對股票/ETF 為真） | 語意不變（保險另有守門） | 不需修改；`test_cost_basis.py` 的 `service` fixture 要補 `premium_categories`（機械式） |
| SC-077、SC-078（股票連動重算） | 不變 | 無 |
| `tests/test_input_view.py` | 轉移相關測試（`test_transfer_button_passes_selected_year_month`、`TestTransferFiltersCostBasisEnd`、`TestTransferAccumulates`）、`test_non_stock_holding_shows_market_value_fields`（一般編輯器）都失效；替身缺 `resolve_input_mode`、`balance_input_service` | 刪除或改寫；補齊替身 |
| `tests/test_bootstrap.py` | Container 多一欄；`MonthlyInputService` 和 `CostBasisService` 的注入值增加 | 補上斷言 |
| `tests/test_monthly_input.py` 的 `_service()` | `MonthlyInputService` 建構子多三個必填參數 | 機械式補參數 |

scenario-author 另外應該掃過 capability 為 `monthly-input` / `cost-basis-input` 的所有卡片，確認有沒有其他以活存、定存、保險、負債為例、描述「手填淨投入」或「項目間轉移」的敘述。

---

## 已知技術債與限制

- **`total_cost` / `realized_income` 的語意依分類而定**（AD-4）：讀這兩欄的程式要先知道項目分類才能正確命名。目前只有本月紀錄表會讀，日後新增讀取端時要注意。
- **分類切換不會回溯重算**（沿用股票 Change）：項目在股票、保險、活存/定存之間改分類時，已落地的 `net_investment`、`total_cost` 都維持原值；之後在新分類下存檔，才會走新的錄入方式。活存/定存推算前期餘額時，會把改分類前的 `market_value` 當成前期餘額。
- **保險過渡估算的已知偏差**（AD-4、BR-6）：保險舊紀錄的手填淨投入如果包含過去的領回（負值），「初始成本＋之前所有淨投入」會低估真正的累計保費。第一個新制月份的預覽會用 `is_transition_estimate` 提醒使用者核對。
- **活存/定存的舊紀錄被連動重算後，原本的手填值不可回復**（AD-3）：這是 BR-7 明定的行為。
- **轉移時代留下的「市值空白、只有淨投入」列照原樣保留**（AD-6、BR-6）：它們對 TWR 的既有影響不變；活存/定存推算時會被跳過。使用者重存該月餘額時，那一列的淨投入才會被改成餘額差。
- **活存/定存「報酬為 0」只在新制推算的月份成立**：歷史月份仍然是舊的手填口徑（AD-9）。
- **`views/input.py` 會變長**（AD-7）：四個編輯器加上預覽，刪掉轉移之後預估仍淨增約 100～150 行，建議實作時把共用的預覽骨架抽成私有函式。
- **趨勢圖項目多時圖例擁擠**（AD-8），項目改名後整條線都用新名稱。

---

## 待確認事項

> 以下都不影響架構，只影響個別函式的邊界或呈現。每一項都已標出推薦的預設值，實作會照推薦值進行，除非使用者另有決定。

| # | 議題 | 選項 | 推薦 |
|---|------|------|------|
| Q1 | 活存/定存的前一筆紀錄餘額空白（例如過去轉移產生的「只有淨投入」列）時，前期餘額怎麼取 | A：往前跳過空白列，取最近一筆有餘額的值；都沒有就用初始市值。B：空白當 0。C：拒絕存檔，要求先補前一筆餘額 | **A**。和報酬率「留空沿用前值」的口徑一致，活存報酬才會是 0；B 會把整個餘額算成淨投入 |
| Q2 | BR-7 活存/定存的「緊接的下一筆」如果餘額空白 | A：改為重算其後第一筆有餘額的列（空白列無從推算）。B：照字面只看緊接的下一筆，空白就不重算 | **A**。B 會漏掉真正受前期值影響的那一筆 |
| Q3 | BR-7 寫「下一筆即使是舊紀錄也更新」，但**保險舊紀錄沒有累計保費**，無法用 BR-2 公式重算 | A：保險沿用股票的連動規則，舊紀錄不更新，其後第一筆新制列由過渡規則正確重算（AD-4）。B：把舊紀錄的淨投入改成某種估算值 | **A**。B 沒有可依據的累計保費，任何估算都是捏造。「舊紀錄也更新」這條實際上只適用於活存/定存 |
| Q4 | 資產項目的分類沒有對應的錄入方式（只會發生在 CSV 匯入時分類留空的資產） | A：月度錄入頁顯示錯誤，提示先到設定頁指定分類，不能存檔。B：退回當作活存/定存（餘額推算） | **A**。錯誤可見；B 會默默套錯規則 |
| Q5 | 本月紀錄表中負債金額的呈現（proposal 交由設計決定） | A：金額拆成「市值 / 餘額」（資產）和「應繳金額」（負債）兩欄，成本欄表頭改成「總成本 / 累計保費」、「已實現收益 / 領回」。B：單一金額欄，表頭寫「市值 / 應繳金額」 | **A**。符合 BR-4「負債一律稱應繳金額」，每欄只有一種語意 |
| Q6 | 活存/定存編輯器要不要在存檔前顯示「前期餘額、推算淨投入」預覽（proposal 沒有明講） | A：顯示（和股票、保險一致）。B：不顯示 | **A**。使用者可以在存檔前核對自動算出的數字，也幾乎不增加成本 |
| Q7 | 趨勢圖遇到缺月或市值空白（proposal 交由設計決定） | A：畫成斷點（不連線）。B：沿用前值。C：直接連線跨過 | **A**。和配置頁其他圖「空白不貢獻」的口徑一致，不畫出沒填過的數字 |
| Q8 | 「應繳金額」的改名範圍 | A：只改單一負債的金額欄（錄入框、本月紀錄表、提醒）；淨值圖的「總負債」彙總線和 CSV／DB 欄名不改。B：連「總負債」也改 | **A**。BR-4 講的是負債的金額欄，「總負債」是彙總概念 |

---

## 決策總覽

| ID | 類型 | 決策 | 信心度 |
|----|------|------|--------|
| AD-1 | 架構 | 錄入方式由 constants 的三個分類集合（SSoT）組成 `INPUT_MODE` 對照，在 `MonthlyInputService.resolve_input_mode` 集中解析；分類對應不到就拋錯 | High |
| AD-2 | 架構 | 活存/定存用新的純運算 `BalanceInputService` 推算淨投入＝餘額 − 前期餘額（跳過空白列），結果落地在 `net_investment` | High |
| AD-3 | 架構 | 活存/定存的連動只重算「下一筆有餘額的列」，而且只在它的前期餘額真的改變時，新舊列都適用；和存檔同一交易 | High |
| AD-4 | 架構 | 保險併入 `CostBasisService` 的累計成本鏈，重用 `total_cost` / `realized_income` 存累計保費與領回；schema 和 CSV 都不變 | High |
| AD-5 | 架構 | 負債走「應繳金額」錄入，`build_amount_due_record` 把淨投入固定為 0；本月紀錄表用 `is_liability` 把金額拆成兩欄 | High |
| AD-6 | 架構 | 完整移除項目間轉移（UI、`build_transfer_pair`、`transfer_records_to_write`、`accumulate_net_investments`），SC 標記 REMOVED | High |
| AD-7 | 架構 | 月度錄入頁依錄入方式分派到四個編輯器，各用獨立的 widget key；存檔一律「Service 規劃 → Repository 寫入」 | High |
| AD-8 | 架構 | `AllocationService.holding_value_trend` 加上 `charts.holding_value_lines`；x 軸是資產有資料月的聯集，缺月或空白畫成斷點，只畫資產 | High |
| AD-9 | 架構 | 不做資料遷移、不回溯重算、不動 schema 和 CSV（BR-6） | High |
| TD-1 | 技術 | Plotly `go.Scatter` 多 trace＋`connectgaps=False`＋category 軸固定順序；圖例切換用內建行為 | High |
| TD-2 | 技術 | 技術棧全部沿用，不加新依賴 | High |
