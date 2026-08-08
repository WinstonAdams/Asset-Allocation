# 設計文件：house-dashboard（買房儀表板）

> 本文件為純技術設計（架構決策 + 介面契約），不含業務行為描述（無 GIVEN/WHEN/THEN）。
> **對應的 Scenarios 由後續階段（1-3 行為規格化）產出。**
> 綁定輸入：`proposal.md`（BR-1~BR-9）、`docs/DECISIONS.md`（D14/D15/D18）、`docs/ROADMAP.md` §5 隱私護欄。
> 1-2a 技術選型、1-2b 架構分析已跳過（沿用既有分層、無新技術選型），故無 tech-research.md / architecture-brief.md。

---

## 現況評估

既有 asset-lab 為 Streamlit + Turso(libsql) 常駐進程，分層為 `views/*.py`（View/Controller，尾端無條件呼叫 `render()`）→ `services/*`（純運算或注入 Repo 的業務）→ `repositories/*`（單表 I/O，連線由 bootstrap 注入）→ `models/*`（Pydantic 純資料）＋ `core/`（constants/utils/exceptions/access）。DI 由 `bootstrap.build_container` 以 keyword args 一次組裝為 `Container`，經 `@st.cache_resource` 快取，Page 從 `st.session_state["container"]` 取用。

本 Change 直接複用的既有慣例（沿用，不偏離）：

| 既有模式 | 位置 | 本 Change 如何沿用 |
|---------|------|------------------|
| 可配置參數：key→value 設定表 + effective 合併 + 存前驗證 | `protocol_threshold_repository` / `ProtocolService.effective_thresholds` / `validate_thresholds` | 買房參數比照（proposal 明列「沿用 protocol_thresholds 模式」） |
| 純運算 Service（建構子無依賴） | `ProtocolService`、`AllocationService` | 可負擔性引擎與買房評估比照 |
| 每個資料概念一張扁平表、單表 Repository | `holdings`/`monthly_records`/`target_allocations`/`protocol_thresholds` | 新增 `house_params`、`subjective_triggers` 兩表 |
| 建表 idempotent（CREATE IF NOT EXISTS，首啟即備妥） | `SchemaRepository.ensure_schema` | 擴充兩張新表 + holdings 加欄位遷移 |
| Page 為唯一 catch 點，委派 Service/Repo、不算業務值 | `overview.py`/`settings.py`/`input.py` | 買房獨立頁與設定頁擴充比照 |
| 「狀態→呈現」純模組可獨立單測 | `overview_presentation.py` | 買房頁的展示映射（見 AD-9） |
| 結果模型與主檔模型分離 | `models/results.py` vs `models/holding.py` 等 | 計算輸出入 `results.py`、持久化模型入新 `models/house.py` |

偏離既有的唯一處為 **holdings 表加欄位需要遷移**（既有 `ensure_schema` 只 CREATE IF NOT EXISTS，無 ALTER 路徑）——見 AD-6。

---

## 架構決策

### AD-1：沿用既有分層與 DI 容器，不新增架構層

- **背景**：本 Change 為純確定性數學（可負擔性、觸發檢核、bucket 進度），無新外部依賴、無 API、無模擬。ROADMAP §4 定調「1–2 個 Task 見效」。
- **選擇**：完全沿用 `views → services → repositories → models/core` 四層與 `bootstrap.Container` 的 keyword-args DI。新元件各歸其層：買房頁入 `views/house.py`，運算入新 Service，持久化入新 Repository 與 model，常數入 `core/constants.py`。所有新 Repository/Service 於 `build_container` 注入 `Container`。
- **理由**：既有分層已能容納本 Change 全部職責；引入新層（如 use-case 層、CQRS）對此規模是過早優化。與 `protocol_*` 系列的形狀一致，維護者無認知負擔。
- **否決方案**：(a) 把買房邏輯塞進既有 `AllocationService`／`overview.py`——否決，會讓既有元件承擔不相干職責，趨向 God Object 且污染既有配置/報酬口徑（違反 D14 純附加）。(b) 為買房建獨立子套件／獨立進程——否決，過度切割，共用同一 Turso 連線與 Container 才合理。
- **後果**：正面—零架構學習成本、與現有測試風格一致、304 既有測試不受牽動。負面—`Container` 欄位增加（新增 2 Repo + 2 Service），`build_container` 組裝清單變長（可接受，既有已 11 個依賴）。

### AD-2：可負擔性引擎獨立為純運算 Service（AffordabilityService）

- **背景**：proposal §核心業務能力 #1 明列「可負擔性引擎（純函式）」：本息均攤月付、由月付上限反推貸款上限、貸款上限＋自備款合成可負擔總價，且要求「自動化測試一律使用虛構參數值」驗證公式正確（BR-1）。
- **選擇**：獨立 `AffordabilityService`（建構子無依賴，比照 `ProtocolService`），只做金融數學，全部參數由呼叫端顯式傳入（無任何 baked-in 常數），回傳 `AffordabilityResult`。正反兩算各一 public 方法 + 共用的攤還私有方法。
- **理由**：引擎是本 Change 風險最高、最需獨立驗證的單元；抽離為零依賴純 Service 使其可用虛構值窮舉邊界（零利率、目標年已過、比率邊界），完全脫離 Streamlit 與 DB。與 proposal 能力 #1 的邊界一對一對應。
- **否決方案**：(a) 放 `core/utils.py`——否決，`core/utils` 規範限「無業務判斷的通用轉換」，本息均攤是金融業務數學，且 utils 不宜承載領域概念。(b) 與觸發/ bucket 併入單一 `HouseService`——否決，引擎與「消費引擎的評估」是不同抽象層，併入會讓單一類別橫跨數學與資料聚合兩種關注點。
- **後果**：正面—引擎可獨立單測、複用（Change 3/4 若需月付試算可直接調用）。負面—多一個 Service 類別與一次 DI 注入（成本極低）。

### AD-3：買房評估邏輯集中於 HouseService（純運算），由 Page 編排，不做 Service 間注入

- **背景**：觸發檢核（BR-5，混合主觀/客觀）、bucket 進度（BR-3/4/6）、bucket 組成警示（BR-8/D15）、總覽摘要都需組合「買房參數 + 資產資料 + 引擎輸出」。
- **選擇**：新增 `HouseService`（建構子無依賴，純運算）。所有方法接收「已由 Repo 取出的資料 + 已算好的 `AffordabilityResult`」為參數，回傳結果模型。**不把 AffordabilityService 注入 HouseService**；由 Page（Controller）依序調用：取參數/資產 → 算 bucket → 算 affordability → 餵入觸發檢核。
- **理由**：與既有 `overview.py` 的編排慣例一致（`overview.py` 已同時編排 `return_service`/`protocol_service`/`allocation_service`，彼此不互相注入）。無 Service 間耦合，兩個 Service 各自都能以虛構值獨立單測。符合架構合約「容錯/流程決策歸 Controller、運算歸 Service」。
- **否決方案**：(a) `HouseService` 注入 `AffordabilityService`——否決，徒增耦合且偏離既有「Page 編排多個純 Service」的一致做法。(b) 觸發/ bucket 也拆成各自 Service——否決，三者共享買房參數與資產快照、耦合度高、拆開反而分散口徑（如「用途=購屋」過濾若各 Service 各寫一份即口徑分裂），集中於 `HouseService` 讓「購屋 bucket 口徑」單一定義。
- **後果**：正面—口徑集中、低耦合、易測、與既有頁面編排同形。負面—`HouseService` 方法數較多（~8 個 public，仍低於 `ReturnService`），需靠命名與 docstring 維持內聚。

### AD-4：買房參數持久化沿用 protocol_thresholds 的 key→value 設定表模式

- **背景**：proposal 範圍明列「買房參數的 DB 存放與設定介面（沿用 protocol_thresholds 的可配置參數模式）」；BR-7 要求所有參數存 DB、存前驗證、非法值不落庫。
- **選擇**：新增單表 `house_params(param_key TEXT PRIMARY KEY, param_value REAL)`，`HouseParamRepository` 提供 `read_params()` / `upsert_param()`（比照 `ProtocolThresholdRepository` 的 read/upsert）。`HouseService.effective_params(stored)` 以已存值覆蓋中性預設、缺鍵補預設，回傳型別化的 `HouseParams`（比照 `effective_thresholds`→`ProtocolThresholds`）。`HouseService.validate_params(...)` 存前驗證（比照 `validate_thresholds`），失敗拋 `DataValidationError`、不落庫。所有參數以 REAL 儲存（年份亦以 REAL 存、讀出轉 int，於 `effective_params` 處理）。
- **理由**：proposal 直接指定沿用此模式；與 `protocol_thresholds`/`target_allocations` 兩張既有 key→value 設定表同形，upsert 語意、缺值補預設、存前驗證三件事都有現成範式。
- **否決方案**：(a) 單列多型別欄位表 `house_params(id, target_total_price REAL, target_year INTEGER, down_payment_ratio REAL, ...)`——雖較貼近 D17「明確欄位優於 generic KV」，但 D17 語境限「持有項目屬性」，且 proposal 明示沿用 key→value 模式；單列表新增參數需 ALTER schema，key→value 新增參數只需加常數。取捨後從 proposal 指令，選 key→value。年份以 REAL 存為此模式的已知小瑕疵（讀出轉 int），以 docstring 標註。(b) generic 全域 config KV 表混放所有領域參數——否決，違反「每概念一張表」慣例、跨 Change 命名衝突風險高。
- **後果**：正面—與既有兩張設定表一致、擴充參數零 schema 變更。負面—異質型別（金額/比率/年份）統一以 REAL 儲存，年份需在 `effective_params` 邊界轉型（單點、已註記）。

### AD-5：主觀觸發勾選狀態獨立表 subjective_triggers

- **背景**：BR-5 定錨、認知為「手動勾選存 DB」，語意是布林狀態，與數值型的買房政策參數性質不同。
- **選擇**：新增單表 `subjective_triggers(trigger_key TEXT PRIMARY KEY, checked INTEGER NOT NULL DEFAULT 0)`（0/1），`SubjectiveTriggerRepository` 提供 `read_triggers()` / `upsert_trigger()`。key 取自 `HOUSE_TRIGGER`（`anchor`/`cognition`）。
- **理由**：布林勾選與數值參數語意分離，各自一張扁平表符合既有慣例；避免把 0/1 布林塞進 `house_params` 的 REAL 值造成語意混淆。
- **否決方案**：折入 `house_params` 以 1.0/0.0 表布林——否決，混淆「政策數值參數」與「使用者主觀判斷勾選」兩種概念，且 UI 呈現（checkbox vs number_input）與驗證規則都不同。
- **後果**：正面—概念清晰、UI 對應直接。負面—多一張表與一個 Repository（成本低，與既有形狀一致）。

### AD-6：用途欄位以純附加 column 掛在 holdings，並引入 idempotent 加欄遷移

- **背景**：proposal 範圍「持有項目主檔新增『用途』標記（一般／購屋），新增與編輯介面同步支援；純附加欄位，不影響既有分類、報酬與配置計算」。BR-9 + D14：Change 1 維持純附加語意，不動既有配置 drift／自由數字口徑（那屬 Change 2）。既有 `ensure_schema` 只有 `CREATE TABLE IF NOT EXISTS`，對已部署且有資料的 DB **無加欄路徑**。
- **選擇**：
  1. `HoldingModel` 加 `purpose: str = HOLDING_PURPOSE.GENERAL`；`holdings` 表加 `purpose TEXT NOT NULL DEFAULT 'general'`。
  2. `SchemaRepository`：`_CREATE_HOLDINGS` 直接含 `purpose` 欄（全新庫）；**新增 idempotent 加欄步驟**——以 `PRAGMA table_info(holdings)` 探測欄位是否已存在，缺才 `ALTER TABLE holdings ADD COLUMN purpose TEXT NOT NULL DEFAULT 'general'`（既有庫，既有列由 DEFAULT 回填為 general）。
  3. 既有 `AllocationService`/`ReturnService`/`filter_asset_records`/淨值口徑**完全不讀 `purpose`**，維持 D14 純附加語意；`purpose` 僅由本 Change 的買房功能讀寫。
- **理由**：additive column + DEFAULT 回填是 SQLite/libsql 對既有資料最安全的演進；PRAGMA 探測 + 條件 ALTER 讓 `ensure_schema` 維持 idempotent（重複啟動安全）。D17「明確欄位、禁 generic KV 屬性表」正是此做法（與未來 `us_situs` 同模式）。
- **否決方案**：(a) 另建 `holding_purposes(holding_id, purpose)` 關聯表——否決，D17 明令可預見的少數屬性用明確欄位、禁為此建 KV 屬性表。(b) 直接改 `_CREATE_HOLDINGS` 但不做 ALTER——否決，對既有已建表的庫不生效（CREATE IF NOT EXISTS 對已存在的表是 no-op），既有 DB 永遠拿不到新欄位。(c) 破壞性重建表——否決，會動到既有 304 測試依賴與正式資料。
- **後果**：正面—既有資料與測試零破壞，用途對既有引擎透明。負面—`ensure_schema` 從「純 CREATE」升級為「CREATE + 條件 ALTER」，需一支探測既有欄位的小工具方法（並須有 SC 覆蓋「舊庫升級」與「新庫直建」兩路徑）。

### AD-7：隱私邊界下的參數預設值策略（個人化＝中性 0，政策方法論比率＝待確認）

- **背景**：ROADMAP §5／DECISIONS 隱私邊界／BR-7：程式碼、測試、文件不得含個人化數字；程式碼內建預設一律中性值（0 或虛構範例），真實值經設定頁落 DB。DECISIONS 定義個人化＝「金額、收入、人生時點、年齡、配置比重」。
- **選擇**：把買房參數分兩類，`HouseParams` / `HOUSE_PARAM_KEY` 與預設常數依此分組：
  - **個人化參數（程式碼預設一律中性 0）**：`target_total_price`（目標總價）、`target_year`（目標購屋年份）、`monthly_after_tax_income`（家庭稅後月收）、`income_threshold`（收入門檻）、`cash_floor`（現金地板）。皆為金額/收入/時點，預設 0；0 在 UI/引擎中對應「尚未設定」的中性姿態（bucket 目標 0 → 不呈現進度；收入門檻 0 → 標示未設定而非誤判達標）。真實值只經設定頁 → DB（Turso，不進版控）。
  - **政策方法論比率（非個人化）**：`down_payment_ratio`（自備比率）、`payment_cap_ratio`（月付上限比率）、`test_annual_rate`（驗算利率）、`loan_years`（貸款年限）。這類為財務規劃通則，proposal 已於版控明列預設（33%/35%/2.5%/30 年），性質同既有 `PROTOCOL_LEVEL_DEFAULTS`（10/20/30）與 `DEFAULT_REBALANCE_THRESHOLD`（5.0）等版控中的中性方法論常數。
- **理由**：核心引擎（AffordabilityService）完全不 bake 任何常數、全部參數顯式傳入，天然滿足「測試用虛構值、程式碼無個人化預設」（BR-1）。預設值只影響「設定頁初值」與「DB 空時 effective_params 回傳」；把會洩漏個人財務狀況的金額/收入/時點設 0，把不洩漏個資的通則比率保留為版控方法論常數，與既有協定門檻的處理一致。
- **否決方案**：把政策比率也設 0——雖最保守，但 `down_payment_ratio=0` 會使 `validate_params`（比率須 >0 <100）視為未設定，且與 proposal 版控中已寫明的預設矛盾；且比率 0 讓 `affordable_total_price` 分母 `(1 − 0)` 失去自備款語意。故不採全 0。
- **後果**：正面—隱私邊界明確、引擎與測試零個資、既有協定常數處理一致。負面／**須確認**：政策比率是否算「個人化」屬判斷邊界——本設計主張「否（proposal 已於版控明列即證非個資）」，採 33/35/2.5/30 為預設常數；若使用者認定這些具體比率仍屬私人策略選擇，則改為中性 0/留空並要求首次使用先於設定頁填入。**此為唯一待確認項，不影響架構，只影響 4 個預設常數的取值。**

### AD-8：CSV holdings 對外契約附加 purpose 欄位（含向後相容匯入）

- **背景**：`data_io_service` 的匯出/匯入以 `CSV_EXPORT.HOLDINGS_COLUMNS`（現 6 欄，無 purpose）為契約，且 `holding_repository.replace_all` 亦不含 purpose。若不處理，用途標記在「匯出→清庫→匯入」往返後會遺失（回退為 DEFAULT general），造成資料流失。
- **選擇**：holdings CSV 契約**附加**（append，維持既有欄序）`purpose` 欄。`export_holdings_csv` 輸出 purpose；`_build_holdings` 讀 purpose；`holding_repository.replace_all` 保留 purpose。向後相容：匯入舊版（無 purpose 欄）CSV 時，缺欄視為 `general`——故 `purpose` **不列入 `_require_headers` 的強制欄位集**（強制欄位維持既有 6 欄），僅在存在時讀取、不存在時補 general。
- **理由**：純附加欄位理應在備份/還原鏈路中被保存，否則違反「純附加」承諾；append 於欄序末端 + 匯入時可選，兼顧新匯出的完整性與舊備份的可還原性。
- **否決方案**：(a) CSV 不含 purpose——否決，往返即遺失用途，破壞資料完整性。(b) purpose 列入強制表頭——否決，會讓所有 Change 之前匯出的舊 CSV 匯入即失敗（不必要的破壞性）。
- **後果**：正面—用途在匯出入往返中保存、舊 CSV 仍可匯入。負面—`CSV_EXPORT.HOLDINGS_COLUMNS`、`export_holdings_csv`、`_build_holdings`、`replace_all` 四處需同步改（屬既有 CSV 契約的受控演進，須有 SC 覆蓋新舊 CSV 兩路徑）。

### AD-9：買房獨立頁 + 設定頁擴充 + 總覽摘要三處落點

- **背景**：proposal 範圍：買房獨立頁（可負擔性試算、五條觸發檢核、bucket 進度與組成警示）、用途標記於主檔新增/編輯、買房參數設定介面、總覽補一條買房進度摘要（與協定等級摘要同層）。
- **選擇**：
  - **新增 `views/house.py`**：買房獨立頁，於 `app.py` 的 `st.navigation` 註冊（置於「行為協定」後、「設定」前為宜）。頁為 View/Controller：委派 `HouseParamRepository`/`SubjectiveTriggerRepository`/`HoldingRepository`/`RecordRepository` + `AffordabilityService`/`HouseService`，單一 catch 點（`AssetLabError`→`st.error`），尾端 `render()`。
  - **擴充 `views/settings.py`**：`_render_holdings`/`_render_edit_holding` 兩表單加「用途」selectbox（一般/購屋，預設一般）；新增 `_render_house_params` 區塊（比照 `_render_protocol_thresholds`：讀 effective_params 帶初值、`validate_params` 存前驗證、`upsert_param` 落庫）。
  - **擴充 `views/overview.py`**：加一列買房摘要（bucket 進度% + 觸發 x/5），與現有協定等級摘要同層。摘要值由 `HouseService.overview_summary(...)` 回傳 `HouseSummary`，overview.py 讀買房參數/主觀勾選/主檔/最新月紀錄後編排取得。
  - **展示映射**：買房頁的燈號/文案映射（如觸發達成 emoji、警示文字）比照 `overview.py` 以頁內模組常數處理（如 `overview.py` 的 `_SIGNAL_EMOJI`）。若觸發/警示的「結果→呈現」轉換成長到需獨立單測，再抽 `house_presentation.py`（比照 `overview_presentation.py`）；初版不預先抽，避免過度設計。
- **理由**：三處落點與既有頁面職責邊界一致（頁只委派與呈現、業務值一律 Service 算）。overview 摘要值走 `HouseService` 純方法確保與買房頁同口徑。
- **否決方案**：把買房摘要邏輯寫進 `overview_presentation.py`——否決，該模組專責協定判定的呈現轉換，摻入買房會混淆職責；買房摘要應由 `HouseService` 產出結果模型後 overview 直接渲染。
- **後果**：正面—UI 落點清楚、口徑統一。負面—`overview.py` 編排增加（多讀 3 類資料並調 `HouseService`），屬 Controller 合理職責；`app.py` 導覽列 +1 頁。

### AD-10：家庭稅後月收參數歸屬與 Change 2 交接（D18）

- **背景**：D18 明定「家庭稅後月收」參數由 Change 1 引入（可負擔性試算與收入觸發都要用），Change 2 的 User Profile 接手為此參數 SSoT 時**必須沿用同一筆存放，禁止另建重複參數**，且收入門檻換算口徑（稅前年薪→稅後月收）為方法論、值屬私人參數。
- **選擇**：`monthly_after_tax_income` 與 `income_threshold` 皆存於本 Change 的 `house_params` 表（key→value），作為此二參數的當前 SSoT。於 design 與（後續）Change 2 proposal 標註：Change 2 User Profile 接手時沿用 `house_params` 同鍵，不新建參數表/鍵。
- **理由**：D18 直接約束；先在 house_params 落定單一存放，避免 Change 2 重建造成雙寫來源。
- **否決方案**：本 Change 先不存月收、僅頁面即時輸入不落庫——否決，收入觸發（BR-5②）需持久判定、且違反 D18「Change 1 引入此參數」。
- **後果**：正面—參數歸屬單一、Change 2 交接清楚。負面—需在交接輸出提醒主 AI：Change 2 proposal 要寫明沿用 house_params 鍵（跨 Change 契約，本 Change 只能標註不能代 Change 2 定案）。

---

## 技術選型

### TD-1：本息均攤自實作純數學，不新增財務函式庫

- **推薦**：以標準庫純數學實作本息均攤（等額本息）月付與其反推，**不引入** `numpy` / `numpy-financial` / `scipy`（信心度：High）
- **理由**：等額本息為封閉解公式（月付 = 本金 × r(1+r)^n / ((1+r)^n − 1)，r=月利率、n=總月數；r=0 退化為本金/n），單行可實作、零數值穩定性風險。proposal「無新外部依賴」、ROADMAP 決定 2「App 不連任何行情 API」、DECISIONS D10 保留 `numpy` 給 Change 3 模擬引擎。本 Change 為確定性數學，引入函式庫是過度依賴。既有 `pyxirr` 供 MWR 用，與本息均攤無關，不複用。

### TD-2：延續既有技術棧，無其他技術選型

- **推薦**：Streamlit + libsql(Turso) + Pydantic + pandas，全數沿用（信心度：High）
- **理由**：1-2a 已判定無新技術選型。DB 存取沿用 `cursor.execute` + upsert 慣例，UI 沿用 `st.number_input`/`st.selectbox`/`st.checkbox`/`st.metric`，模型沿用 Pydantic `BaseModel`。

---

## 介面契約

> 以下為型別簽名與語意契約（技術層）。比率一律以百分比（0–100）表示、與既有門檻/權重同單位；金額為 TWD（float）；年份為西元年（int）。**具體行為場景（邊界、缺口清單、警示觸發條件）由 1-3 Scenarios 定義。**

### 1. 常數（`core/constants.py` 新增）

```python
class HOLDING_PURPOSE:
    """持有項目用途。純附加標記，不影響既有分類/報酬/配置口徑（D14/BR-9）。"""
    GENERAL = "general"          # 一般（預設）
    HOUSE = "house"              # 購屋 bucket
    ALL = (GENERAL, HOUSE)

class HOUSE_PARAM_KEY:
    """買房政策/個人化參數鍵（house_params 表的 param_key 值域）。"""
    # 個人化（程式碼預設中性 0，見 AD-7）
    TARGET_TOTAL_PRICE = "target_total_price"           # 目標總價（TWD）
    TARGET_YEAR = "target_year"                         # 目標購屋年份（西元年，REAL 存、int 用）
    MONTHLY_AFTER_TAX_INCOME = "monthly_after_tax_income"  # 家庭稅後月收（TWD，D18）
    INCOME_THRESHOLD = "income_threshold"               # 收入門檻（TWD/月，D18）
    CASH_FLOOR = "cash_floor"                           # 現金地板（TWD，BR-4）
    # 政策方法論比率（預設值見 AD-7，須確認）
    DOWN_PAYMENT_RATIO = "down_payment_ratio"           # 自備比率（%）
    PAYMENT_CAP_RATIO = "payment_cap_ratio"             # 月付上限比率（%）
    TEST_ANNUAL_RATE = "test_annual_rate"               # 驗算利率（年化 %）
    LOAN_YEARS = "loan_years"                           # 貸款年限（年）

class HOUSE_PARAM_DEFAULTS:
    """effective_params 缺鍵時的中性補值。個人化一律 0；政策比率見 AD-7 待確認。"""
    # 個人化 → 0
    TARGET_TOTAL_PRICE = 0.0
    TARGET_YEAR = 0
    MONTHLY_AFTER_TAX_INCOME = 0.0
    INCOME_THRESHOLD = 0.0
    CASH_FLOOR = 0.0
    # 政策方法論（AD-7：proposal 版控已明列；若判定屬個資改中性 0）
    DOWN_PAYMENT_RATIO = 33.0
    PAYMENT_CAP_RATIO = 35.0
    TEST_ANNUAL_RATE = 2.5
    LOAN_YEARS = 30

class HOUSE_TRIGGER:
    """五條觸發條件鍵（BR-5）。anchor/cognition 為主觀（存 subjective_triggers）。"""
    ANCHOR = "anchor"            # 定錨（主觀）
    INCOME = "income"           # 收入門檻（客觀）
    DOWN_PAYMENT = "down_payment"  # 自備達標（客觀，含現金地板）
    PAYMENT = "payment"         # 月付占比（客觀）
    COGNITION = "cognition"     # 認知（主觀）
    ALL = (ANCHOR, INCOME, DOWN_PAYMENT, PAYMENT, COGNITION)
    SUBJECTIVE = (ANCHOR, COGNITION)

class HOUSE_PARAMS_TABLE:
    TABLE_NAME = "house_params"
    PARAM_KEY = "param_key"
    PARAM_VALUE = "param_value"

class SUBJECTIVE_TRIGGERS_TABLE:
    TABLE_NAME = "subjective_triggers"
    TRIGGER_KEY = "trigger_key"
    CHECKED = "checked"

# HOLDINGS_TABLE 新增欄位常數
class HOLDINGS_TABLE:
    ...
    PURPOSE = "purpose"

# CSV_EXPORT.HOLDINGS_COLUMNS 末端附加 "purpose"（AD-8）
```

### 2. 持久化模型（`models/house.py` 新增）

```python
class HouseParamModel(BaseModel):
    """單一買房參數持久化列（比照 ProtocolThresholdModel）。"""
    param_key: str
    param_value: float

class SubjectiveTriggerModel(BaseModel):
    """單一主觀觸發勾選狀態持久化列。"""
    trigger_key: str
    checked: bool

class HouseParams(BaseModel):
    """合併中性預設後的有效買房參數（比照 ProtocolThresholds）。
    ratio 欄位為 %（0–100）；金額 TWD；target_year 西元年。"""
    target_total_price: float
    target_year: int
    monthly_after_tax_income: float
    income_threshold: float
    cash_floor: float
    down_payment_ratio: float
    payment_cap_ratio: float
    test_annual_rate: float
    loan_years: int
```

### 3. 結果模型（`models/results.py` 新增）

```python
class AffordabilityResult(BaseModel):
    """可負擔性試算輸出。direction='reverse'（反推可負擔總價）或 'forward'（正算月付）。
    未適用於該方向的欄位為 None。"""
    direction: str
    monthly_payment: float | None = None          # 本息均攤月付（forward 主輸出）
    income_share_pct: float | None = None          # 月付 ÷ 月收（%）（forward）
    loan_amount: float | None = None               # forward：total_price×(1−自備比率)
    down_payment: float | None = None              # forward：total_price×自備比率
    affordable_total_price: float | None = None    # reverse 主輸出
    loan_ceiling: float | None = None              # reverse：由月付上限反推的貸款上限
    monthly_payment_cap: float | None = None       # reverse：月收×月付上限比率

class TriggerCondition(BaseModel):
    """單一觸發條件判定結果。kind='subjective'|'objective'。
    actual/required 供客觀數值條件呈現缺口（主觀條件為 None）。"""
    key: str
    kind: str
    met: bool
    actual: float | None = None
    required: float | None = None

class TriggerChecklist(BaseModel):
    """五條觸發彙總。all_met 全數成立才對應『可啟動購屋』（BR-5，呈現文案由頁/Scenario 定）。"""
    conditions: list[TriggerCondition]
    met_count: int
    all_met: bool

class BucketProgress(BaseModel):
    """自備款 bucket 進度（BR-3/4/6）。
    target_amount=目標總價×自備比率；progress_pct 於 target_amount=0 時為 None；
    reached_target_year=True（目標年已到/已過）時 required_annual_accumulation 為 None（不除以零）。"""
    bucket_value: float
    target_amount: float
    gap: float                                     # max(target_amount − bucket_value, 0)
    progress_pct: float | None
    years_to_target: int | None                    # target_year − current_year（未設年份為 None）
    reached_target_year: bool
    required_annual_accumulation: float | None

class BucketCompositionWarning(BaseModel):
    """bucket 組成序列風險提示（BR-8/D15）。只提示、不強制。"""
    has_non_cash: bool                             # bucket 含非活存/定存分類資產
    intensified: bool                              # years_to_target ≤ 5 時強化
    non_cash_value: float                          # 非活存/定存部分市值合計（供呈現）

class HouseSummary(BaseModel):
    """總覽頁買房摘要（bucket 進度% + 觸發 x/5）。"""
    bucket_progress_pct: float | None
    triggers_met_count: int
    triggers_total: int
```

### 4. Repository（`repositories/` 新增，連線由 bootstrap 注入）

```python
class HouseParamRepository:
    def __init__(self, *, conn: "Connection") -> None: ...
    def read_params(self) -> list[HouseParamModel]: ...          # 全部已存參數，可不完整
    def upsert_param(self, *, param: HouseParamModel) -> None: ...  # 同 key 覆蓋（ON CONFLICT）
    def read_all(self) -> list[HouseParamModel]: ...             # CSV 匯出用（如納入，見備註）

class SubjectiveTriggerRepository:
    def __init__(self, *, conn: "Connection") -> None: ...
    def read_triggers(self) -> list[SubjectiveTriggerModel]: ...
    def upsert_trigger(self, *, trigger: SubjectiveTriggerModel) -> None: ...
```

`HoldingRepository`（既有，擴充）：`_COLUMNS`/`_INSERT`/`_UPDATE`/`replace_all` 納入 `purpose`；`_row_to_model` 回填 `purpose`（舊列缺欄由 DB DEFAULT 保證為 'general'）。

`SchemaRepository.ensure_schema()`（既有，擴充）：新增
```python
_CREATE_HOUSE_PARAMS         # CREATE TABLE IF NOT EXISTS house_params(param_key TEXT PRIMARY KEY, param_value REAL NOT NULL)
_CREATE_SUBJECTIVE_TRIGGERS  # ... subjective_triggers(trigger_key TEXT PRIMARY KEY, checked INTEGER NOT NULL DEFAULT 0)
# holdings 加欄（idempotent）：PRAGMA table_info(holdings) 探測 purpose，缺才 ALTER TABLE ... ADD COLUMN purpose TEXT NOT NULL DEFAULT 'general'
```

### 5. Service（`services/` 新增，建構子無依賴）

```python
class AffordabilityService:
    """本息均攤引擎（純數學，全部參數顯式傳入，無 baked-in 常數）。"""
    def monthly_payment(self, *, principal: float, annual_rate_pct: float, years: int) -> float:
        """等額本息月付。annual_rate_pct=0 → principal/(years×12)。years×12 為總期數。"""
    def affordable_total_price(
        self, *, monthly_income: float, payment_cap_ratio_pct: float,
        test_annual_rate_pct: float, loan_years: int, down_payment_ratio_pct: float,
    ) -> AffordabilityResult:
        """反推：月付上限=月收×月付上限比率 → 反推貸款上限 → ÷(1−自備比率) 合成可負擔總價。"""
    def payment_for_price(
        self, *, total_price: float, down_payment_ratio_pct: float,
        test_annual_rate_pct: float, loan_years: int, monthly_income: float,
    ) -> AffordabilityResult:
        """正算：貸款=總價×(1−自備比率) → 本息均攤月付 → 月付÷月收=占比%。"""

class HouseService:
    """買房評估（純運算，無依賴）。方法接收 Repo 取出的資料 + 已算好的 AffordabilityResult。"""
    def effective_params(self, *, stored: list[HouseParamModel]) -> HouseParams:
        """以已存值覆蓋 HOUSE_PARAM_DEFAULTS、缺鍵補中性預設，target_year 於此轉 int。"""
    def validate_params(self, *, params: HouseParams) -> None:
        """存前驗證（BR-7）：比率 0<x<100、驗算利率≥0、貸款年限>0 整數、金額≥0、年份≥0。
        失敗拋 DataValidationError、不落庫。"""
    def bucket_value(
        self, *, month_records: list[MonthlyRecordModel], holdings: list[HoldingModel],
    ) -> float:
        """purpose=house 項目於最新月快照的市值合計；該項目不在快照中則以 initial_market_value 補（BR-3）。"""
    def cash_reserve_value(
        self, *, month_records: list[MonthlyRecordModel], holdings: list[HoldingModel],
    ) -> float:
        """未標記購屋(purpose=general)且分類∈{活存,定存}的最新月市值合計（BR-4 現金地板比較用）。"""
    def bucket_progress(
        self, *, bucket_value: float, params: HouseParams, current_year: int,
    ) -> BucketProgress:
        """target=目標總價×自備比率；gap、progress_pct、years_to_target、每年需累積速率
        （目標年已到/已過→速率 None，不除以零，BR-6）。"""
    def bucket_composition_warning(
        self, *, house_holdings: list[HoldingModel], month_records: list[MonthlyRecordModel],
        years_to_target: int | None,
    ) -> BucketCompositionWarning:
        """bucket 含非活存/定存分類資產→has_non_cash；years_to_target≤5→intensified（BR-8/D15）。"""
    def assess_triggers(
        self, *, params: HouseParams, bucket_value: float, cash_reserve_value: float,
        forward_result: AffordabilityResult, subjective: list[SubjectiveTriggerModel],
    ) -> TriggerChecklist:
        """五條混合檢核（BR-5）：
        - anchor/cognition：取自 subjective 勾選
        - income：monthly_after_tax_income ≥ income_threshold
        - down_payment：bucket ≥ 目標總價×自備比率 且 cash_reserve ≥ cash_floor（BR-4）
        - payment：目標總價的月付占比 ≤ 月付上限比率（forward_result.income_share_pct）
        全數 met 才 all_met=True。"""
    def overview_summary(
        self, *, bucket_progress: BucketProgress, checklist: TriggerChecklist,
    ) -> HouseSummary:
        """總覽摘要：bucket 進度% + 觸發 met_count/total。"""
```

### 6. DI 組裝（`bootstrap.py`）

`Container` 新增欄位：`house_param_repo`、`subjective_trigger_repo`、`affordability_service`、`house_service`。`build_container` 以 keyword args 注入（Repo 傳 `conn=conn`；兩個純 Service 無參數建構）。`ensure_schema` 已含新表與加欄。

### 7. View（`views/` 變更）

- **`views/house.py`（新增）**：買房獨立頁；`app.py` `st.navigation` 註冊。編排：讀 `effective_params` → 讀主檔/最新月紀錄算 `bucket_value`/`cash_reserve_value` → 算 `affordable_total_price` 與（目標總價的）`payment_for_price` → `bucket_progress`/`bucket_composition_warning`/`assess_triggers` → 渲染。含正/反算輸入、五條觸發清單（主觀 checkbox 即時 `upsert_trigger`）、bucket 進度與警示。單一 catch 點。
- **`views/settings.py`（擴充）**：holdings 新增/編輯表單加「用途」selectbox；新增 `_render_house_params`（讀 effective 帶初值、`validate_params` 後逐鍵 `upsert_param`）。
- **`views/overview.py`（擴充）**：新增買房摘要列（編排讀買房參數/主觀勾選/主檔/最新月紀錄 → `HouseService.overview_summary` → 渲染 bucket% 與 x/5）。

### 8. 已知限制與技術債

- **年份以 REAL 儲存**：`house_params` 統一 REAL，`target_year` 於 `effective_params` 邊界轉 int（AD-4 已知瑕疵，單點處理）。
- **overview 與 house 頁的資料編排部分重疊**：兩頁都需讀買房參數/主觀勾選/主檔/最新月紀錄以得觸發與 bucket；口徑經 `HouseService` 統一，但兩頁各自編排讀取（可接受的少量重複，未來若第三處需要再抽共用編排）。
- **家庭稅後月收 SSoT 交接**：Change 2 User Profile 接手時須沿用 `house_params` 同鍵，禁止另建（D18）——本 Change 只能標註，實際約束須寫進 Change 2 proposal。
- **CSV house_params/subjective_triggers 是否納入匯出入**：本設計預設 holdings 的 purpose 納入既有 CSV（AD-8）；`house_params`/`subjective_triggers` 兩表是否納入 CSV 備份契約，proposal 未明列——初版**不納入** CSV（設定頁可重填），避免擴大既有三表 CSV 契約；若後續要備份參數再議。列為待確認的次要項。

---

## 決策總覽

| ID | 類型 | 決策 | 信心度 |
|----|------|------|--------|
| AD-1 | 架構 | 沿用既有四層 + Container DI，不新增架構層 | High |
| AD-2 | 架構 | 可負擔性引擎獨立為零依賴純 Service（AffordabilityService） | High |
| AD-3 | 架構 | 買房評估集中於 HouseService（純運算），Page 編排、無 Service 間注入 | High |
| AD-4 | 架構 | 買房參數沿用 protocol_thresholds 的 key→value 設定表 + effective 合併 + 存前驗證 | High |
| AD-5 | 架構 | 主觀觸發勾選獨立表 subjective_triggers | High |
| AD-6 | 架構 | 用途以純附加 column + idempotent 加欄遷移（PRAGMA 探測 + 條件 ALTER），D14 純附加 | High |
| AD-7 | 架構 | 隱私邊界分類：個人化參數預設中性 0；政策比率預設值待確認 | Medium |
| AD-8 | 架構 | CSV holdings 契約附加 purpose 欄（向後相容匯入） | High |
| AD-9 | 架構 | 買房獨立頁 + 設定頁擴充 + 總覽摘要三處落點 | High |
| AD-10 | 架構 | 家庭稅後月收存 house_params，Change 2 沿用同鍵（D18） | High |
| TD-1 | 技術 | 本息均攤自實作純數學，不引入 numpy/財務函式庫 | High |
| TD-2 | 技術 | 延續 Streamlit+libsql+Pydantic+pandas，無新技術選型 | High |

> **待確認（不阻斷架構）**：AD-7 政策方法論比率（自備 33%／月付上限 35%／驗算利率 2.5%／貸款年限 30 年）是否視為個人化——本設計主張否（proposal 已於版控明列即證），採為預設常數；若使用者認定屬私人策略選擇，改為中性 0/留空並要求首次於設定頁填入。
