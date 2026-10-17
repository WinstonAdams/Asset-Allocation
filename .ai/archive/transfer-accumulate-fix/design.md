# 設計文件：transfer-accumulate-fix（項目間轉移改為累加寫入＋錄入框帶入既有值）

> 本文件只談技術：架構決策（ADR）和介面契約，不寫業務行為（沒有 GIVEN/WHEN/THEN）。
> **對應的 Scenarios 由後續 1-3 行為規格化（scenario-author）產出**；本文件用 BR 編號引用 `proposal.md` 的業務規則（BR-1~BR-7）。
> 參考來源：`proposal.md`。1-2a 技術選型、1-2b 架構分析都已跳過（progress 有記），所以沒有 tech-research.md 和 architecture-brief.md；既有架構慣例沿用 `.ai/archive/stock-total-cost-input/design.md`（以下簡稱「前一 Change」）及更早的 initial-build / house-dashboard design。
> 本 workspace **沒有 `utils_v2/`**（已再次確認目錄不存在，與前一 Change 相同），02-architecture §7 與 04-cross-cutting 的 utils_v2/structlog/biz_job 都不適用；logging 與錯誤處理照 initial-build AD-8（標準 `logging`、Page 層是唯一 catch 點）。

---

## 現況評估

既有 asset-lab 分四層：`views/*.py`（View/Controller，檔尾無條件呼叫 `render()`）→ `services/*`（純運算，或注入 Repo 只做讀取）→ `repositories/*`（單表 I/O，連線由 bootstrap 注入）→ `models/*`（Pydantic 純資料），外加 `core/`、UI 元件模組 `amount_widget.py`。DI 由 `bootstrap.build_container` 以 keyword args 組成 `Container`。

### 本 Change 要修的三個技術根因

| 根因 | 位置 | 現象 |
|------|------|------|
| 轉移寫入走整列覆寫 | `views/input.py::_render_transfer` → `RecordRepository.upsert_records` → `_UPSERT`（`DO UPDATE SET market_value = excluded.market_value, net_investment = excluded.net_investment, ...`） | 轉移紀錄的 `market_value` 是 None，把該月既有市值清成 NULL；淨投入被這次金額取代，不會累加 |
| 錄入框只在 key 第一次出現時播種 | `amount_widget.amount_input` 用 `session_state.setdefault(key, format_amount(value))`，`views/input.py` 呼叫時不帶 `value`（預設 0） | 選到已有紀錄的項目/月份仍顯示 0；切換項目/月份不會跟著換值；存檔時把 0 蓋回去 |
| 寫入與畫面在同一輪 rerun 內，寫入發生在畫面之後 | Streamlit 由上往下執行，按鈕的處理分支寫在各區塊內 | 轉移寫入後，同一輪上方的錄入框還是舊值；若下一輪才重讀，使用者在中間打的字會被蓋掉（見 AD-3） |

### 沿用的既有慣例

| 既有模式 | 位置 | 本 Change 怎麼沿用 |
|---------|------|------------------|
| 多列寫入用 Repository compound method，單一交易、失敗 rollback 後原樣上拋 | `RecordRepository.upsert_records` / `delete_record_and_upsert`（前一 Change AD-5） | 新增 `accumulate_net_investments` 走同樣交易模式（AD-1） |
| 加欄用 idempotent 遷移（PRAGMA 探測，缺欄才 ALTER），可為 NULL 的純附加欄 | `SchemaRepository._add_column_if_missing`（前一 Change AD-2） | `monthly_records` 附加 `cash_dividend`（AD-5） |
| CSV 對外契約尾端附加欄位、強制欄位集不變 | `CSV_EXPORT.RECORDS_COLUMNS` / `RECORDS_REQUIRED_COLUMNS`（前一 Change AD-9） | 尾端附加 `cash_dividend`（AD-7） |
| 純運算 Service，Page 編排，Service 之間不互相注入 | `CostBasisService`、`MonthlyInputService`（前一 Change AD-3） | 帶入值、本月紀錄表都做成純方法，放在各自負責的 Service（AD-2、AD-4） |
| Service 回傳 Pydantic 列，Page 以 `st.dataframe([{標籤: 值}])` 呈現 | `views/allocation.py::_render_drift` | 本月已存紀錄表照做（AD-4） |
| 推算值落地在既有欄，下游只讀既有欄 | `net_investment`、`realized_income`（前一 Change AD-1/AD-2） | `realized_income` 繼續存合計，推算公式的輸入不變（AD-5） |

### 偏離既有做法的地方（各有 ADR）

- **月度錄入頁的寫入動作在成功後呼叫 `st.rerun()`，成功訊息改走 session_state 暫存（flash）**（AD-3）：專案中其他頁面目前都是寫完後在同一輪直接 `st.success`。本頁因為「寫入結果要立刻反映在上方區塊」（BR-2、BR-4）而偏離，範圍只限 `views/input.py`。
- **`amount_widget` 新增「依資料來源重新播種」的輔助函式**（AD-2）：原本 `amount_input` 的初值只在 key 第一次建立時生效（Streamlit keyed widget 的預設語意）。新函式在資料來源改變時主動改寫 session_state，`amount_input` 本身簽名與行為不變。

---

## 架構決策

### AD-1：項目間轉移的非股票端改用 Repository 原子累加（SQL UPSERT 遞增），取代整列覆寫

- **背景**：BR-1 要求非股票端「在既有淨投入上累加 ±金額、既有市值不變」，同月多次轉移逐次累加；BR-3 要求當月沒有紀錄時新建一筆只有淨投入、市值留空的列。現行的 `_UPSERT` 是整列覆寫，造成市值被清空、淨投入不累加。
- **選擇**：
  - `RecordRepository` 新增 compound method `accumulate_net_investments(*, records)`，對每筆紀錄執行：
    ```sql
    INSERT INTO monthly_records (holding_id, year_month, net_investment) VALUES (?, ?, ?)
    ON CONFLICT(holding_id, year_month) DO UPDATE SET net_investment = net_investment + excluded.net_investment
    ```
    - 有既有列：只把 `net_investment` 加上增量，`market_value`、`total_cost`、`realized_income`、`cash_dividend` 一律不動（BR-1）。
    - 沒有既有列：新建一列，只有淨投入，其餘欄位都是 NULL（BR-3）。
    - 所有 statement 執行完才 `commit()` 一次；任一步失敗就 `rollback()` 後原樣上拋（沿用前一 Change AD-5 的交易模式，轉移兩端要嘛都生效、要嘛都不生效）。空清單不做任何事。
  - 傳入的 `MonthlyRecordModel` 只讀 `holding_id`、`year_month`、`net_investment` 三個欄位，`net_investment` 的意思是**增量**；其餘欄位忽略。這個語意寫在方法 docstring 和方法名稱裡。
  - Page 編排順序：`MonthlyInputService.build_transfer_pair`（防呆，簽名不變）→ `CostBasisService.transfer_records_to_write`（濾掉股票/ETF 端，簽名不變）→ `record_repo.accumulate_net_investments`。只有最後一步從 `upsert_records` 換成新方法。
  - 既有 `upsert_record` / `upsert_records` 的整列覆寫語意**不變**：單列錄入存檔、股票/ETF 推算存檔還是需要整列覆寫。
- **理由**：
  - 累加放在單一 SQL statement 裡，沒有「先讀、再算、再寫」的時間差，同月多次轉移、轉移和單列錄入的先後順序都不會互相蓋掉。
  - 「要累加還是覆寫」是業務決策，由 Page 選擇呼叫哪個 Repository 方法來表達；「哪些端要寫、金額正負」仍在 Service（`build_transfer_pair` / `transfer_records_to_write`）。Repository 只做原子遞增這個 I/O 原語，符合 02 §6「步驟間沒有業務邏輯介入」的 compound method 定義。
  - 已在本機 libsql（SQLite 3.45.1）實際驗證：既有列只遞增淨投入、市值保留；新列的市值為 NULL；同一列連續兩次遞增結果正確；rollback 會撤銷未 commit 的遞增。
- **否決方案**：
  - **Service 先讀當月紀錄、在記憶體合併後用 `upsert_records` 整列寫回**：多一次讀取；讀和寫之間不是原子的；寫回時還是整列覆寫，會把讀取之後才變動的欄位蓋掉。測試面也沒有好處，因為 Repository 層本來就用記憶體 DB 測（SC-006/SC-085 的既有做法）。否決。
  - **另建轉移明細表，讀取時加總**：proposal 明定本次不做轉移明細保存；所有讀 `net_investment` 的下游都得改。否決。
  - **改 `_UPSERT` 讓所有寫入都累加**：單列錄入存檔、股票/ETF 推算存檔需要覆寫語意，改了反而出錯。否決。
- **後果**：
  - 正面：proposal 成功標準的兩種順序（先錄入再轉移、先轉移再錄入）在 DB 層一定得到相同結果；轉移兩端在同一個交易內完成。
  - 負面：`RecordRepository` 多一條 SQL 和一個 public 方法；`tests/test_input_view.py` 的 Record 替身要補 `accumulate_net_investments`；累加沒有留下轉移明細，打錯只能用反向轉移或單列錄入更正（BR-5，proposal 已接受）。

### AD-2：錄入框帶入既有值：Service 純方法算出帶入值，`amount_widget` 依「資料來源」決定是否重新播種，widget key 維持固定

- **背景**：BR-2 要求選定項目與月份後，若該月已有紀錄就預先帶入既有值；切換項目或月份時跟著換；該月沒有紀錄時維持現行預設。限制有兩個：(1) Streamlit 的 keyed widget 只在 key 第一次建立時吃初值；(2) 使用者每次在欄位按 Enter 或離開焦點都會觸發 rerun，所以「每輪都用 DB 值覆寫」會把使用者還沒存檔的輸入洗掉。
- **選擇**：
  1. **帶入值由 Service 純方法產出**（可以不靠 Streamlit 單獨測）：
     - 一般分類：`MonthlyInputService.build_record_prefill(*, records, holding_id, year_month) -> RecordEditorPrefill`（市值、淨投入）。
     - 股票/ETF：`CostBasisService.build_cost_basis_prefill(*, records, year_month) -> CostBasisEditorPrefill`（總成本、現值、已實現損益、現金股利）。這裡要把存下來的合計拆回兩格（AD-5），拆分公式只出現在 `CostBasisService`。
     - 映射規則（技術預設，行為由 SC 定義）：沒有紀錄 → 各欄現行預設（全為 0）；有紀錄 → 照存的值帶入，存的是 NULL 的市值／總成本帶入空白（存檔前必須補填，避免把空白存成 0）；已實現損益／現金股利是 NULL 時帶 0（推算時 NULL 本來就當 0）。見 Q3。
  2. **重新播種的機制**放在 `amount_widget.seed_amount_inputs(*, seed_key, source, values)`：
     - `source` 是「資料來源」：`(holding_id, year_month, prefill)`，用 `==` 比較。
     - 以下任一成立時，把 `values` 中每個 widget key 的 session_state 改成 `format_amount(值)`，並把 `source` 記在 `session_state[seed_key]`：(a) `source` 和上次記下的不同（切換項目/月份，或 DB 值因存檔、轉移而改變）；(b) `values` 裡有任何 key 不在 session_state（例如在股票/一般兩種錄入框之間切換時，未渲染的 widget state 會被 Streamlit 清掉）。
     - 都不成立就不動，使用者還沒存檔的輸入會保留。
     - 一定要在同一輪的 `amount_input` 建立**之前**呼叫（Streamlit 不允許 widget 建立後再改它的 state）。
  3. widget key **維持固定**（`record_market_value`、`record_net_investment`、`cost_basis_total_cost`、`cost_basis_market_value`），只把 `cost_basis_realized_income` 拆成 `cost_basis_realized_pnl` 和 `cost_basis_cash_dividend`（BR-6）。前一 Change 的 CSS 前綴選擇器（AD-8）、SC-051 的同步 key 都不受影響。
- **理由**：
  - 「帶入什麼值」是業務映射，放在 Service 可以直接用固定的紀錄序列驗證；「什麼時候改寫 widget state」是 Streamlit 機制，集中在 UI 元件模組，Page 只負責接線。
  - 用資料來源當觸發條件，剛好區分出「該重新帶入」（選擇或 DB 改變）和「不該動」（使用者正在輸入）兩種情況。
  - 已用 AppTest 驗證：widget 建立前改寫 key 的 session_state 不會報錯；未渲染一輪的 widget state 會在下一輪消失，所以 (b) 這個條件是必要的。
- **否決方案**：
  - **widget key 帶入 holding_id 和年月**（每個項目×月份一組 key）：同一項目同一月份的 DB 值被轉移改掉時，key 不變，會繼續顯示舊值，使用者一存檔就把轉移結果蓋掉，正是本 Change 要修的問題。另外 key 會變成動態，既有 AppTest 用固定 key 定位 widget 的測試都要改寫。否決。
  - **每輪都用 DB 值覆寫**：使用者每次按 Enter 或離開欄位都會 rerun，還沒存檔的輸入會被洗掉，沒辦法用。否決。
  - **把帶入映射寫在 Page**：NULL 怎麼處理、合計怎麼拆回兩格都是業務規則，不該放在 View。否決。
- **後果**：
  - 正面：BR-2 的帶入、切換、沒有紀錄時的預設，都由同一個機制處理；先轉移再錄入時，錄入框一定顯示累加後的淨投入。
  - 負面：這個機制依賴 Streamlit 的 widget state 語意（建立前可以改寫、沒渲染的會被清掉），Streamlit 升級後需要回歸測試（列入技術債）。使用者還沒存檔就切換項目或月份時，輸入到一半的內容會被新的帶入值取代（這是 BR-2「跟著切換」的直接結果）。

### AD-3：月度錄入頁的寫入動作成功後 `st.rerun()`，成功訊息透過 session_state 暫存到下一輪顯示

- **背景**：BR-4 要求表格在存檔或轉移後立即反映；AD-2 要求錄入框依 DB 最新值重新播種。但 Streamlit 由上往下執行，寫入發生在按鈕分支內，同一輪中已經渲染過的區塊（表格、轉移上方的錄入框）都是寫入前的狀態。更麻煩的是：轉移之後如果沒有立刻重繪，使用者下一次在錄入框打字觸發 rerun 時，AD-2 會偵測到 DB 已變並重新播種，剛打的字就被蓋掉。
- **選擇**：
  - `views/input.py` 中每個成功的寫入分支（單列存檔／刪除、股票/ETF 存檔／刪除、建立轉移）最後都呼叫私有 helper `_flash_and_rerun(message)`：把成功訊息存進 `session_state[_FLASH_KEY]`，然後 `st.rerun()`。
  - `render()` 開頭先 pop 這個 key，有內容就 `st.success(...)` 顯示一次。
  - 兩端都是股票/ETF 的轉移（沒有寫入任何東西）維持現狀：直接 `st.info`，不 rerun。
  - 錯誤路徑不變：`DataValidationError` 等 `AssetLabError` 在 rerun 前就拋出，由 `render()` 既有的 `except AssetLabError` 轉成 `st.error`。`st.rerun()` 拋的是 `RerunException`（繼承 `BaseException`，已查證 Streamlit 1.59.1 原始碼），不會被 `except AssetLabError` 吃掉。
- **理由**：寫入後整頁用寫入後的 DB 狀態重繪，表格、錄入框、預覽三者一致；Page「唯一 catch 點」的錯誤處理模式不變。已用 AppTest 驗證：按鈕觸發 `st.rerun()` 後腳本會重跑，flash 訊息出現在重跑後的畫面，既有測試斷言 `at.success` 的寫法還是成立。
- **否決方案**：
  - **按鈕改用 `on_click` callback 寫入**（callback 在下一輪腳本之前執行）：callback 不在 `render()` 的 try 範圍內，例外會繞過 Page 唯一的 catch 點，需要另外把錯誤放進 session_state 傳遞；widget 值也得改從 session_state 讀。改動面比較大。否決。
  - **把表格放到頁面最下方、不 rerun**：表格雖然能讀到最新值，錄入框仍是舊值，會發生背景描述的「打字被蓋掉」，或更糟的「舊值被存回去」。否決。
- **後果**：
  - 正面：寫入結果立即反映在整頁；避免舊帶入值覆蓋新資料。
  - 負面：每次寫入多跑一輪腳本（多一輪 Turso 讀取，個人使用量下可以忽略）；成功訊息從「出現在按鈕旁邊」變成「出現在頁面上方」（位置由 SC/實作決定，見介面契約 §7）。

### AD-4：「本月已存紀錄」表格與市值未填提醒由 `MonthlyInputService.summarize_month` 純方法產出；Page 每輪只讀一次項目與當月紀錄

- **背景**：BR-4 要求顯示選定月份所有已存紀錄的唯讀表格，並提醒「當月有紀錄但市值空白」的項目（負債也適用）。這需要把月度紀錄和項目主檔對起來，再判斷哪些列要提醒，屬於資料組裝加業務判斷。
- **選擇**：
  - `MonthlyInputService.summarize_month(*, records, holdings) -> list[MonthRecordRow]`：純方法，不使用注入的 Repo。依 `records` 原本的順序（`read_month` 依 holding_id 排序）每筆紀錄產出一列：項目名稱、市值、淨投入、總成本、已實現收益（合計）、`market_value_missing`。
  - **提醒判斷以資料決定**：`market_value_missing = market_value is None`，不另外看分類。新制股票/ETF 列存檔時一定要填現值，所以實務上只有非股票列和舊制列會觸發；這和 BR-4「非股票/ETF 項目」的字面一致，還能順便抓到本 Change 之前被舊轉移清空市值的舊制股票列（proposal 已知缺陷提到，要靠這張表找出歷史空白月份）。見 Q1。
  - 表格的股票/ETF 欄位照 BR-4 字面顯示「已實現收益」合計，不拆成兩欄（見 Q2）。非股票列的總成本、已實現收益是 NULL，顯示為空白。
  - **Page 每輪只讀一次**：`render()` 在 try 區塊內讀 `holdings = holding_repo.list_holdings()` 和 `month_records = record_repo.read_month(year_month=target_ym)`，傳給表格、一般錄入框（帶入值來源）和轉移區塊。目前 `list_holdings()` 在錄入框和轉移區塊各讀一次，改成共用。股票/ETF 錄入框仍另外讀 `read_holding_records`（推算需要完整歷史）。
  - 建議的渲染順序是：月份選擇 → 本月已存紀錄表（含提醒）→ 單列錄入 → 項目間轉移。這只是版面建議，不影響正確性（AD-3 保證寫入後重繪）。
- **理由**：
  - 對照與判斷都是零 I/O 的純方法，可以直接用紀錄清單測試；`MonthlyInputService` 的職責本來就是「月度錄入」（帶入上月、成對轉移），加這兩個方法還在同一個範圍內（加上 AD-2 的 `build_record_prefill`，public 方法從 2 個變成 4 個）。
  - 用資料判斷提醒，就不需要分類集合，`MonthlyInputService` 不必注入 `CostBasisService` 或分類常數，維持「Service 之間不注入」的慣例，分類判斷也只有 `CostBasisService` 一個來源。
- **否決方案**：
  - **放進 `CostBasisService`**：表格包含負債和所有分類，不屬於總成本推算的職責。否決。
  - **新增一個專用的呈現 Service**：只有一個方法，而且要和 `MonthlyInputService` 共用同一份月份紀錄，拆出去只多一個 Container 欄位，沒有好處。否決。
  - **依 BR-4 字面用分類判斷提醒**：需要把分類集合也注入 `MonthlyInputService`（分類判斷變成兩個來源），或由 Page 先算出股票項目集合再傳進來（Controller 做資料轉換）；而且會漏掉舊制股票列的空白市值。否決（Q1 知會）。
- **後果**：
  - 正面：表格和提醒都可以單元測試；每輪 Turso 讀取次數不增反減。
  - 負面：`tests/test_input_view.py` 的 Record 替身要補 `read_month`；`_render_record_editor` / `_render_transfer` 的私有簽名改成接收已讀好的資料。

### AD-5：已實現收益拆成兩格：`realized_income` 繼續存合計（語意不變），新增 `cash_dividend` 欄；已實現損益在讀取時由 `CostBasisService` 用「合計 − 現金股利」還原

- **背景**：BR-6 把股票/ETF 錄入的「本月已實現收益」拆成「本月已實現損益」（可為負）和「本月現金股利」（不可為負），兩者都要能被 BR-2 各自帶回，所以必須分開保存；推算公式不變（兩者相加就是原本的已實現收益）。proposal 把「上線前已存的已實現收益舊值怎麼對應兩格」留給設計決定，也要求舊格式 CSV 仍可匯入。另一個限制來自環境：README 寫明本機開發和雲端部署**共用同一個 Turso 資料庫**（免費單庫），所以 2-Z 在本機啟動新版時，`ensure_schema` 會直接在正式資料庫上執行遷移，而雲端當時跑的還是舊版程式。
- **選擇**：
  1. **儲存**：`monthly_records` 附加 `cash_dividend REAL`（可為 NULL、不設 DEFAULT），沿用 `_add_column_if_missing`，新庫的 `_CREATE_MONTHLY_RECORDS` 直接包含這一欄。`realized_income` 的語意**完全不變**：還是「已實現損益＋現金股利」的合計，也就是推算公式用的那個值。
  2. **寫入**：`CostBasisService.plan_save` 接收 `realized_pnl`、`cash_dividend` 兩個值，存檔列寫 `realized_income = realized_pnl + cash_dividend`、`cash_dividend = cash_dividend`。新制列的 `cash_dividend` 一律寫實際值（預設 0），不寫 NULL。
  3. **讀回**：已實現損益 ＝ `(realized_income 或 0) − (cash_dividend 或 0)`，現金股利 ＝ `cash_dividend 或 0`。拆分和合併都只在 `CostBasisService` 內（`build_cost_basis_prefill` 拆、`derive`/`plan_save` 合）。
  4. **舊值對應**：本功能上線前存的 `realized_income`（`cash_dividend` 為 NULL）**全部視為已實現損益，現金股利視為 0**。合計不變，所以既有推算鏈、`_recalculate_following` 的結果都不會變。
  5. 金額都是 `parse_amount` 取整後的整數（float 存放），相加相減在 2^53 以內是精確的，不會出現拆回來差 0.0000001 的情況。
- **理由**：
  - **純附加遷移**：舊版程式的 SELECT/INSERT/UPSERT 都明確列出欄位名，多一個 `cash_dividend` 欄不影響它。2-Z 在共用資料庫上先行遷移時，雲端舊版照常運作；萬一要回滾到舊版，舊版讀到的 `realized_income` 仍是正確的合計，推算不會錯。
  - 合計和股利兩個值剛好就是兩個自由度，沒有冗餘，不會出現「三個欄位彼此不一致」的狀況；已實現損益可以無損還原，滿足 BR-2「兩格各自帶回」。
  - 推算公式的輸入（合計）、CSV 既有欄位、前一 Change 所有以 `realized_income` 為準的 SC 語意都不變，影響面最小。
  - 舊值只能對應到已實現損益：舊合計可能是負數，而現金股利不可為負，對應到股利會違反 BR-6。
- **否決方案**：
  - **把 `realized_income` 改名為 `realized_pnl`，再新增 `cash_dividend`**（欄位語意最「乾淨」）：`ALTER TABLE ... RENAME COLUMN` 不是附加式遷移。本機 2-Z 一啟動就會在共用的正式資料庫上改名，雲端舊版的 SELECT 立刻出現「no such column」；回滾到舊版也會遇到同樣問題。CSV 匯出欄名也得跟著改、舊檔要做別名對應。（已在本機 libsql 確認 RENAME 本身可以執行，否決理由是相容性，不是技術上做不到。）否決。
  - **新增 `realized_pnl`、`cash_dividend` 兩欄，同時保留 `realized_income`**（新增欄位後回填舊值，或三欄同時寫）：合計和兩個分項一起存，三欄可能互相矛盾，需要回填遷移與一致性維護；不回填的話，`realized_income` 會變成沒人讀的廢欄。否決。
  - **另建股利明細表**：每次讀取都要 JOIN、CSV 要多一份檔案，D17 也不允許為此另開屬性表。否決。
- **後果**：
  - 正面：零破壞的 schema 演進，相容舊版程式、舊 CSV、既有推算鏈。
  - 負面：已實現損益不是實體欄位，未來如果要直接用 SQL 統計損益，得寫成 `realized_income - COALESCE(cash_dividend, 0)`（列入技術債）。舊值無法還原真正的損益／股利比例，使用者重新存檔該月才會修正。2-Z 到正式部署這段期間，如果有人在雲端舊版編輯已填股利的股票/ETF 月份，舊版只會更新合計、不會更新股利，拆回來的損益就會錯（營運注意事項：這段期間不要用雲端舊版編輯股票/ETF 紀錄）。

### AD-6：「現金股利不可為負」的守門放在 `CostBasisService.derive`，`plan_save` 繼承；預覽區把「輸入還沒填完」和「推算被拒絕」分開顯示

- **背景**：BR-6 規定現金股利不可為負，已實現損益可以為負。這是業務規則，要決定守門放在哪一層。
- **選擇**：
  - `derive(..., realized_pnl, cash_dividend)` 一開始就檢查 `cash_dividend < 0`，違反時拋 `DataValidationError`（訊息帶欄位名稱）。`plan_save` 透過 `derive` 繼承這個檢查。
  - 內部把推算拆成私有方法 `_derive_from_realized_income(...)`（輸入合計）。`derive` 驗證後呼叫它；`_recalculate_following` 對已存在的列直接用存下來的合計呼叫它，不需要先拆再合（已存的列 `cash_dividend` 不是 NULL 就是 ≥ 0，不需要再驗）。
  - 預覽區（Page）：解析 `parse_amount` 失敗時維持現在的佔位提示；`derive` 拒絕時顯示拒絕原因。兩者都是 `DataValidationError`，用兩段 try 區分。具體文案由 SC 定義，見 Q4。
- **理由**：Service 是業務規則的唯一來源，存檔和預覽都經過同一個檢查；預覽能提早告訴使用者哪裡錯，而不是等到按存檔才知道。
- **否決方案**：
  - **在 Page 檢查**：業務規則寫進 View。否決。
  - **在 `parse_amount` 加非負參數**：通用解析函式不應該知道各欄位的業務規則（02 §8）。否決。
  - **只在 `plan_save` 檢查**：預覽會對不合法的輸入算出一個看起來正常的淨投入，造成誤導。否決。
- **後果**：
  - 正面：一個規則、一個位置。
  - 負面：`derive` / `plan_save` 的參數從 `realized_income` 改成 `realized_pnl` + `cash_dividend`，`tests/test_cost_basis.py` 呼叫這兩個方法的地方要機械式改寫（只改呼叫參數，直接建立 `MonthlyRecordModel(realized_income=...)` 的測試資料不用動）。

### AD-7：CSV records 契約尾端附加 `cash_dividend`；強制欄位集**明確**固定為原本 4 欄

- **背景**：BR-6 新增分開保存的欄位，CSV 匯出再匯入不能遺失；舊格式（4 欄、前一 Change 的 6 欄）都要能匯入。
- **選擇**：
  - `CSV_EXPORT.RECORDS_COLUMNS` 尾端附加 `"cash_dividend"`，成為 7 欄，既有欄序不變。
  - `RECORDS_REQUIRED_COLUMNS` 從 `RECORDS_COLUMNS[:-2]` 改成明確的 `RECORDS_COLUMNS[:4]`。**這一步必做**：照舊寫法，附加一欄後 `[:-2]` 會變成 5 欄（含 `total_cost`），4 欄的舊 CSV 就匯不進來了。
  - `export_records_csv` 不用改（`reindex` 跟著常數走，`read_all` 已含新欄）。`_build_records` 照 `total_cost` 的既有寫法：有 `cash_dividend` 欄就讀（空白轉 None），沒有就是 None。
  - 匯入不檢查 `cash_dividend ≤ realized_income` 之類的一致性，照原值還原（沿用前一 Change AD-9「匯入信任檔案」）。
- **理由**：和 holdings.purpose、total_cost/realized_income 同一套做法；三種歷代格式都能匯入，新匯出的檔案資料完整。
- **否決方案**：**把 `cash_dividend` 列為強制表頭**：前一 Change 之後匯出的 6 欄備份會匯入失敗。否決。
- **後果**：
  - 正面：向後相容。
  - 負面：SC-031 的匯出欄位斷言要擴充成 7 欄。`DataIoService._build_records` 延續該檔「方法內直接讀 CSV 欄名字串」的既有寫法（前一 Change 已知的既有慣例，3-3 審查已接受），本 Change 不順手重構。

---

## 技術選型

### TD-1：轉移累加用 SQLite UPSERT 的遞增運算式（`DO UPDATE SET col = col + excluded.col`）

- **推薦**：單一 statement 的原子遞增，包在既有的 commit/rollback 交易模式中（信心度：High）
- **理由**：專案已在使用 UPSERT（`_UPSERT`，SQLite ≥ 3.24）；已在本機 libsql 0.1.11（SQLite 3.45.1）實測遞增、新列市值 NULL、rollback 三種行為都符合 AD-1。Turso 伺服器端也是 libsql，語法相同。

### TD-2：寫入後重繪用 `st.rerun()`，帶入值用「widget 建立前改寫 session_state」

- **推薦**：`st.rerun()` + session_state 暫存成功訊息；`seed_amount_inputs` 在 `amount_input` 之前改寫 widget key（信心度：High）
- **理由**：Streamlit 1.59.1 已在本機用 AppTest 實測三件事：(1) 按鈕觸發 `st.rerun()` 後腳本重跑，暫存的成功訊息出現在重跑後的畫面；(2) widget 建立前改寫它的 session_state 不會拋 `StreamlitAPIException`；(3) 某一輪沒渲染的 widget，它的 state 會在下一輪消失（所以 AD-2 需要「key 不在就重新播種」這個條件）。`RerunException` 繼承 `BaseException`，不會被 Page 的 `except AssetLabError` 攔截。

### TD-3：其餘技術棧沿用

- **推薦**：Streamlit + libsql(Turso) + Pydantic v2 + pandas，全部沿用，不新增依賴（信心度：High）
- **理由**：proposal 明定沒有新外部依賴；`cash_dividend` 加欄沿用既有的 `_add_column_if_missing`；Pydantic 2.13 的模型可以直接用 `==` 比較，夠 AD-2 拿來比較資料來源。

---

## 介面契約

> 以下是型別簽名與語意契約（技術層）。金額單位為 TWD（float，UI 輸入取整數），年月格式為 `'YYYY-MM'`。
> **行為細節（邊界值、錯誤路徑、提示文案）由 1-3 Scenarios 用 BR 編號定義，這裡不重述。**

### 1. 常數（`core/constants.py`）

```python
class MONTHLY_RECORDS_TABLE:
    ...                                   # 既有欄位不變；REALIZED_INCOME 語意不變（已實現損益＋現金股利的合計）
    CASH_DIVIDEND = "cash_dividend"       # 股票/ETF 本月現金股利（≥0）；NULL＝非股票/ETF 列、舊制列，
                                          # 或本功能上線前的新制列（皆視為 0，其合計全數視為已實現損益）（AD-5）


class CSV_EXPORT:
    ...
    RECORDS_COLUMNS = (
        "holding_id", "year_month", "market_value", "net_investment",
        "total_cost", "realized_income", "cash_dividend",   # cash_dividend 尾端附加（AD-7）
    )
    RECORDS_REQUIRED_COLUMNS = RECORDS_COLUMNS[:4]   # 明確固定為原本 4 欄（不可再用 [:-N]）（AD-7）
```

docstring 同步更新：`MONTHLY_RECORDS_TABLE`、`CSV_EXPORT` 補上 `cash_dividend` 的語意說明。

### 2. Models

```python
# models/record.py
class MonthlyRecordModel(BaseModel):
    """（docstring 補：realized_income 為已實現損益＋現金股利的合計；cash_dividend 為其中的現金股利，
    None 視為 0；已實現損益不另存，＝realized_income − cash_dividend）"""
    holding_id: int
    year_month: str
    market_value: float | None = None
    net_investment: float = 0.0
    total_cost: float | None = None
    realized_income: float | None = None
    cash_dividend: float | None = None     # 新增（AD-5）


# models/results.py（新增三個純資料模型）
class RecordEditorPrefill(BaseModel):
    """一般分類單列錄入框的帶入值（BR-2）。沒有紀錄時為現行預設；市值 None 代表帶入空白。"""
    market_value: float | None
    net_investment: float


class CostBasisEditorPrefill(BaseModel):
    """股票/ETF 錄入框的帶入值（BR-2/BR-6）。total_cost／market_value 為 None 代表帶入空白。"""
    total_cost: float | None
    market_value: float | None
    realized_pnl: float
    cash_dividend: float


class MonthRecordRow(BaseModel):
    """「本月已存紀錄」唯讀表格的單列（BR-4）。

    total_cost/realized_income 只有新制股票/ETF 列有值；market_value_missing 為 True 時需提醒補填市值。
    """
    holding_id: int
    name: str
    market_value: float | None
    net_investment: float
    total_cost: float | None
    realized_income: float | None
    market_value_missing: bool
```

### 3. Repositories

```python
# repositories/record_repository.py
# 欄序常數、_row_to_model、_values、_INSERT、_UPSERT 擴充為 7 欄（加 cash_dividend）；
# _UPSERT 的 DO UPDATE SET 也加上 cash_dividend（整列覆寫語意不變）。
# read_range / read_all 的 DataFrame 變成 7 欄（空集合也保留完整欄位）。
class RecordRepository:
    def accumulate_net_investments(self, *, records: list[MonthlyRecordModel]) -> None: ...
        # 每筆 record 的 net_investment 視為增量，累加到同 (holding_id, year_month) 的既有列；
        # 既有列的其餘欄位（market_value/total_cost/realized_income/cash_dividend）不變；
        # 沒有既有列就新建（只有淨投入，其餘欄位 NULL）。record 的其他欄位一律忽略（AD-1）。
        # 單一交易：全部執行完才 commit；任一步失敗 → rollback 後原樣上拋；空清單不做任何事。


# repositories/schema_repository.py
class SchemaRepository:
    def ensure_schema(self) -> None: ...
        # _CREATE_MONTHLY_RECORDS 新庫直接包含 cash_dividend REAL；
        # 既有庫多一次 _add_column_if_missing(table=monthly_records, column=cash_dividend, alter_sql=...)
        # （純附加、不設 DEFAULT、既有列補 NULL）（AD-5）
```

### 4. Services

```python
# services/cost_basis_service.py（public 方法簽名異動以 ★ 標示）
class CostBasisService:
    def derive(                                                      # ★
        self, *, holding: HoldingModel, records: list[MonthlyRecordModel], year_month: str,
        total_cost: float, realized_pnl: float, cash_dividend: float,
    ) -> NetInvestmentDerivation: ...
        # cash_dividend < 0 → DataValidationError（AD-6）
        # 淨投入＝(total_cost − 前期總成本) − (realized_pnl + cash_dividend)；前期總成本規則不變

    def plan_save(                                                   # ★
        self, *, holding: HoldingModel, records: list[MonthlyRecordModel], year_month: str,
        market_value: float, total_cost: float, realized_pnl: float, cash_dividend: float,
    ) -> list[MonthlyRecordModel]: ...
        # 存檔列：realized_income = realized_pnl + cash_dividend、cash_dividend = cash_dividend（AD-5）
        # 回傳內容與連動重算規則不變（前一 Change AD-4）

    def build_cost_basis_prefill(                                    # 新增
        self, *, records: list[MonthlyRecordModel], year_month: str,
    ) -> CostBasisEditorPrefill: ...
        # records 只含該項目（同 derive 的前置條件）；找出 year_month 那一列：
        #   沒有 → total_cost=0, market_value=0, realized_pnl=0, cash_dividend=0（現行預設）
        #   有   → total_cost / market_value 照存的值（None 保持 None）；
        #          cash_dividend = 存的值 或 0；realized_pnl = (realized_income 或 0) − cash_dividend（AD-2/AD-5）

    def _derive_from_realized_income(                                # 新增私有：derive 與 _recalculate_following 共用
        self, *, holding: HoldingModel, records: list[MonthlyRecordModel], year_month: str,
        total_cost: float, realized_income: float,
    ) -> NetInvestmentDerivation: ...

    # uses_cost_basis / plan_delete / transfer_records_to_write：簽名與行為不變
    # （transfer_records_to_write 的 docstring 補一句：回傳的紀錄交給 accumulate_net_investments 累加寫入）


# services/monthly_input_service.py（新增兩個純方法，不使用注入的 Repo；既有方法不變）
class MonthlyInputService:
    def build_record_prefill(
        self, *, records: list[MonthlyRecordModel], holding_id: int, year_month: str,
    ) -> RecordEditorPrefill: ...
        # 找出 (holding_id, year_month) 相符的那一列：
        #   沒有 → market_value=0, net_investment=0（現行預設）
        #   有   → 照存的 market_value（None 保持 None）、net_investment（AD-2）

    def summarize_month(
        self, *, records: list[MonthlyRecordModel], holdings: list[HoldingModel],
    ) -> list[MonthRecordRow]: ...
        # 依 records 順序每筆一列；name 從 holdings 對應（前置條件：holdings 涵蓋 records 所有項目——
        # 項目不可刪除、CSV 匯入會拒絕孤兒紀錄，所以永遠成立）；
        # market_value_missing = market_value is None（AD-4，見 Q1）


# services/data_io_service.py：_build_records 有 cash_dividend 欄就讀（空白 → None），沒有就是 None（AD-7）
```

### 5. UI 元件（`src/asset_lab/amount_widget.py`）

```python
def seed_amount_inputs(
    *, seed_key: str, source: object, values: Mapping[str, float | None],
) -> None: ...
    # 以下任一成立時，把 values 每個 key 的 session_state 改成 format_amount(值)，並記 session_state[seed_key] = source：
    #   (a) session_state.get(seed_key) != source
    #   (b) values 中任一 key 不在 session_state（widget 上一輪沒渲染、state 已被 Streamlit 清掉）
    # 都不成立就不動（保留使用者還沒存檔的輸入）。
    # 前置條件：必須在同一輪對應的 amount_input 建立之前呼叫（AD-2）

# amount_input / inject_amount_input_style：簽名與行為不變
```

### 6. Views（`views/input.py`）

| 項目 | 異動 |
|------|------|
| `render()` | 開頭 pop `_FLASH_KEY` 顯示成功訊息；try 內讀一次 `holdings`、`month_records` 往下傳（AD-4）；新增 `_render_month_records`；頁首說明文案（賣出時已實現收益的填法）改成兩格版本，措辭由 SC 定義 |
| `_render_month_records`（新增） | `input_service.summarize_month(...)` → `st.dataframe([{標籤: format_amount(值)}...])`；有 `market_value_missing` 的列就顯示提醒（BR-4）；當月沒有紀錄時顯示空狀態文案 |
| `_render_record_editor`（一般分類） | 改收 `input_service`、`holdings`、`month_records`；`build_record_prefill` → `seed_amount_inputs(seed_key=_RECORD_SEED_KEY, source=(holding_id, target_ym, prefill), ...)` → 兩個 `amount_input`；存檔／刪除成功後 `_flash_and_rerun` |
| `_render_cost_basis_editor`（股票/ETF） | `build_cost_basis_prefill` → `seed_amount_inputs(seed_key=_COST_BASIS_SEED_KEY, ...)` → 四個 `amount_input`（總成本、現值、已實現損益 `cost_basis_realized_pnl`、現金股利 `cost_basis_cash_dividend`）；旁邊加 BR-7 提示；預覽區用兩段 try 區分解析失敗與 `derive` 拒絕（AD-6）；`plan_save` 傳 `realized_pnl`/`cash_dividend`；成功後 `_flash_and_rerun` |
| `_render_transfer` | 改收 `holdings`（不再自己讀）；`upsert_records` 換成 `accumulate_net_investments`（AD-1）；成功後 `_flash_and_rerun`；兩端都是股票時維持 `st.info`、不 rerun |
| `_flash_and_rerun`（新增私有） | 寫入 `session_state[_FLASH_KEY]` 後 `st.rerun()`（AD-3） |
| 模組常數 | `_FLASH_KEY`、`_RECORD_SEED_KEY`、`_COST_BASIS_SEED_KEY`（session_state key，View 私有，值為 UI 內部識別字串） |

`bootstrap.py`、`app.py`：不變（`Container` 欄位不變，沒有新 Service）。

---

## 受影響的既有 SC 與測試（交接給 1-3 scenario-author／1-4 task-planner）

| 對象 | 影響 | 建議處理 |
|------|------|---------|
| **SC-008**（成對記錄；活存→定存） | Service 層 `build_transfer_pair` 不變，既有測試照樣通過；但落地語意從「寫入」變成「累加」 | 修訂邊界：同月已有紀錄時改為累加；BR-1／BR-3 另開新卡（累加、保留市值、多次轉移、沒有紀錄時新建空市值列） |
| **SC-079 / SC-080**（股票端過濾） | 過濾行為不變；非股票端改為累加寫入 | SC-079 補「非股票端累加」的連結；測試不受影響（Service 層） |
| SC-037（轉移防呆） | 不變；BR-5 的反向轉移仍走這套防呆 | 不需修改；BR-5 可在新卡引用 |
| **SC-074～SC-078**（推算、過渡、清倉、連動重算） | 公式的輸入從一格變兩格；卡片敘述的「本月已實現收益」要改寫 | 改寫敘述（兩格相加＝原本的已實現收益，數值例子可以沿用）；`tests/test_cost_basis.py` 中 `derive(...)` / `plan_save(...)` 的 `realized_income=` 參數機械式改成 `realized_pnl=..., cash_dividend=0.0`，`MonthlyRecordModel(realized_income=...)` 的測試資料不用動 |
| SC-009（賣出當月） | 股票/ETF 清倉的填法敘述提到已實現收益 | 文字改成兩格版本 |
| SC-082 / SC-083（金額輸入框） | 新增「現金股利」金額欄，自動套用千分位與放大樣式 | 欄位清單補上；測試不受影響 |
| SC-031（`test_sc031_export_records_has_header_and_all_rows`） | 斷言匯出 6 欄 | 擴充為 7 欄（AD-7） |
| SC-084（舊格式 CSV） | 4 欄舊檔仍可匯入；另有前一 Change 的 6 欄格式 | 補一個邊界：6 欄（沒有 cash_dividend）匯入 → 現金股利視為未填；BR-6 的舊值對應另開新卡或併入 |
| SC-006（`test_read_range_empty_preserves_columns`；`test_bootstrap.py` 的加欄遷移三路徑測試） | DataFrame 從 6 欄變 7 欄；遷移多一欄 | 擴充欄位斷言；`test_bootstrap.py` 補一個「前一 Change 的 6 欄 schema → 升級後有 cash_dividend、既有值不變」的路徑（現有的 `_LEGACY_CREATE_MONTHLY_RECORDS` 是更早的 4 欄版本） |
| SC-085（批次寫入原子性） | `accumulate_net_investments` 也套用同一個交易保證 | 邊界補上轉移累加；對應補一個 rollback 測試 |
| SC-005（帶入上月仍持有項目） | 不受影響（按鈕沒有可見效果的問題另案處理） | 不需修改 |
| 非 SC 的 UI 機制測試（`tests/test_input_view.py`） | widget key `cost_basis_realized_income` 拆成兩個；Record 替身少了 `read_month`、`accumulate_net_investments`；轉移測試原本斷言 `batch_upserted`；存檔成功訊息改由 rerun 後的 flash 顯示（已驗證 `at.success` 斷言仍然成立） | 補齊替身、改斷言；新增帶入與重新播種的 View 層測試（切換項目/月份、轉移後重新帶入、輸入中不被覆寫） |

scenario-author 另外應該掃過 capability 為 `monthly-input` / `cost-basis-input` / `data-io` 的所有卡片，確認還有沒有其他把「已實現收益」當成單一輸入欄的敘述。

---

## 已知技術債與限制

- **轉移沒有明細**（AD-1，proposal 已接受）：累加後看不出這個淨投入是由幾筆轉移組成，打錯只能用反向轉移或單列錄入更正。
- **帶入機制依賴 Streamlit widget state 語意**（AD-2/TD-2）：建立前可以改寫、沒渲染的會被清掉。Streamlit 升級後要回歸 View 層的帶入測試。
- **寫入後多跑一輪腳本**（AD-3）：每次寫入多一輪 Turso 讀取；個人使用量下可以忽略。
- **已實現損益不是實體欄位**（AD-5）：SQL 層直接統計損益要寫 `realized_income - COALESCE(cash_dividend, 0)`。舊值全部歸到已實現損益，無法還原真正的損益／股利比例。
- **共用資料庫的部署空窗**（AD-5）：本機 2-Z 啟動就會在正式資料庫加欄（純附加，雲端舊版不受影響）。但從 2-Z 到正式部署這段期間，雲端舊版的轉移仍是舊的覆寫行為，而且舊版編輯股票/ETF 紀錄時只會更新合計、不會更新股利。建議這段期間不要用雲端版錄入，部署前先「匯出 CSV」備份。
- **分類切換的殘留欄位**（延伸前一 Change AD-1 的技術債）：項目從股票/ETF 改成其他分類後，轉移累加會保留該列既有的 `total_cost` / `realized_income` / `cash_dividend`，不會清掉。
- **既有歷史資料不自動修補**（proposal 範圍外）：已被舊轉移清空的市值，要靠 BR-4 表格的提醒找出來手動補錄；提醒只看選定的那個月，沒有跨月清單。
- **「帶入上月仍持有項目」按鈕沒有可見效果**（proposal 範圍外，另案）。

---

## 待確認事項

> 以下都不影響架構，只影響個別函式的判斷條件或畫面呈現。每一項都標了推薦值；除非使用者另有決定，實作會照推薦值進行。

| # | 議題 | 選項 | 推薦 |
|---|------|------|------|
| Q1 | 「市值尚未填」提醒的範圍 | A：只看資料，**任何**當月有紀錄但市值空白的列都提醒（含舊制股票/ETF 列）。B：照 BR-4 字面，只提醒非股票/ETF 分類 | **A**。新制股票/ETF 列存檔時一定要填現值，所以實務上和 B 一樣只抓到非股票列；另外還能抓到本 Change 之前被舊轉移清空市值的股票列（proposal 已知缺陷想找的正是這些）；`MonthlyInputService` 也不必知道分類規則 |
| Q2 | 本月已存紀錄表中股票/ETF 的收益欄 | A：照 BR-4 字面顯示「已實現收益」合計一欄。B：拆成「已實現損益」「現金股利」兩欄，和錄入框一致 | **A**。表格的目的是看已存的結果、找空白市值；要看兩格明細就點進錄入框（會帶回兩格）。B 會讓「合計拆回兩格」的公式出現在 `MonthlyInputService` 和 `CostBasisService` 兩處（或另抽共用函式） |
| Q3 | 已有紀錄、但個別欄位是空白時的帶入（知會） | 市值／總成本空白 → 帶入空白（存檔時必須補填，空白會被拒絕）；已實現損益／現金股利空白 → 帶 0 | 照列出的規則。避免把空白的總成本當成 0 存回去（0 代表清倉，推算淨投入會大幅失真）；收益兩格的空白在推算中本來就當 0 |
| Q4 | 現金股利填負數時，存檔前預覽怎麼呈現 | A：預覽區直接顯示拒絕原因（例如「現金股利不可為負」）。B：和「還沒填完」一樣顯示佔位提示，存檔時才報錯 | **A**。提早回饋，而且不會和「還沒填完」混在一起 |
| Q5 | 成功訊息的位置（知會） | 寫入後整頁重繪，成功訊息改顯示在頁面上方（月份選擇附近），不再出現在按鈕旁邊 | 知會即可；這是 AD-3 的直接後果 |

---

## 決策總覽

| ID | 類型 | 決策 | 信心度 |
|----|------|------|--------|
| AD-1 | 架構 | 轉移的非股票端改用 `RecordRepository.accumulate_net_investments`（SQL UPSERT 原子遞增，保留市值，沒有紀錄時新建空市值列），單一交易 | High |
| AD-2 | 架構 | 帶入值由 Service 純方法產出（一般分類／股票各一），`amount_widget.seed_amount_inputs` 依資料來源或 key 遺失決定是否重新播種，widget key 固定 | High |
| AD-3 | 架構 | 月度錄入頁寫入成功後 `st.rerun()`，成功訊息透過 session_state 暫存到下一輪；錯誤處理仍由 Page 唯一 catch 點負責 | High |
| AD-4 | 架構 | `MonthlyInputService.summarize_month` 產出本月紀錄表，提醒條件只看資料（市值為 None）；Page 每輪只讀一次項目與當月紀錄 | High |
| AD-5 | 架構 | `realized_income` 繼續存合計（語意不變）＋純附加 `cash_dividend` 欄；已實現損益＝合計−股利，由 `CostBasisService` 拆合；舊值全部歸為已實現損益；否決改名遷移（共用 Turso 資料庫，非附加遷移會讓雲端舊版壞掉） | High |
| AD-6 | 架構 | 現金股利非負的檢查放在 `CostBasisService.derive`（`plan_save` 繼承），預覽區區分「未填完」與「被拒絕」 | High |
| AD-7 | 架構 | CSV records 尾端附加 `cash_dividend`；`RECORDS_REQUIRED_COLUMNS` 明確固定為前 4 欄 | High |
| TD-1 | 技術 | SQLite UPSERT 遞增運算式（本機 libsql/SQLite 3.45.1 已實測） | High |
| TD-2 | 技術 | `st.rerun()` ＋ widget 建立前改寫 session_state（Streamlit 1.59.1 AppTest 已實測） | High |
| TD-3 | 技術 | 技術棧沿用，不新增依賴 | High |
