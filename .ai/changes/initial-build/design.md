# 設計文件：initial-build（資產配置管理工具）

> 本文件整合 `proposal.md`（需求基準）與 `tech-research.md`（技術選型）。
> `architecture-brief.md` 不存在（greenfield 新專案，無既有 codebase 可分析，progress 已標跳過）。
> 本專案為 greenfield，**無 `utils_v2/` 工具庫**（已確認該目錄不存在），故 02-architecture §7 的「優先使用 utils_v2」與 04-cross-cutting 的 `init()` / `biz_job()` / `structlog` 工具皆不適用；偏離理由見 AD-1、AD-8。
> 本文件僅含架構決策與介面契約，**不含業務行為（GIVEN/WHEN/THEN）**；對應的 Scenarios 將由後續 1-3 階段（scenario-author）產出，本文件以 BR 編號引用 proposal 的業務規則。

---

## 現況評估

- **既有模式**：無。本專案為全新空目錄（僅有 `.gitignore`、`SPEC`、`.ai/`），無既有程式碼可沿用。
- **可參照的工程準則**：`.claude/docs/rules/py/*` 的分層合約（Controller→Service→Repository→Model）。
- **沿用 vs. 偏離**：
  - **沿用**：Service/Repository/Model 三層職責切分、DI by keyword args、pydantic 純資料模型、constants 設定決策表、import 三區塊、docstring/型別提示規範、錯誤往上拋。
  - **偏離（已記 ADR）**：規則的入口契約（`main.py` + argparse + `biz_job` + Controller 批次容錯迴圈）是為 **CLI/RPA 排程腳本**設計；本專案是 **Streamlit 互動式 Web App**，入口模型、容錯邊界、logging 基礎設施皆不同。偏離點集中於 AD-1、AD-8，其餘層級規範照常遵守。
  - **無 utils_v2**：規則假設的 `from utils_v2 import init, biz_job, SheetTable, http_retry` 等一律不可用，以標準庫 / 第三方套件替代（見 AD-8）。

---

## 架構決策

### AD-1：以 Streamlit 多頁 App 取代 RPA `main.py` 入口模型
- **背景**：工程準則的入口合約假設「argparse 解析 → `init()` 載入 env/config → DI 組裝 → `with biz_job(): controller.execute()` 一次性跑完退出」。Streamlit App 的執行模型完全不同：由 `streamlit run app.py` 啟動常駐進程，每次使用者互動觸發整個 script 由上而下 **rerun**，無「跑完即退出」的批次語意，也沒有 CLI 參數。
- **選擇**：
  - 入口檔為 `app.py`（專案根目錄），職責＝「`st.login()` 守門 → 組裝依賴（cached）→ 路由到當前頁面」。多頁面**僅**用 Streamlit 原生 `st.navigation`（程式化路由）驅動，頁面檔集中放於 `views/`。
  - 每個頁面檔（如 `views/input.py`、`views/allocation.py`、`views/returns.py`、`views/settings.py`、`views/data_io.py`）扮演 **Controller/View 複合角色**：負責 UI 元件渲染、收集使用者輸入、呼叫 Service、把結果交給圖表元件。
  - **修正（t12）**：資料夾刻意不命名為 `pages/`——`pages/` 是 Streamlit 的保留資料夾名，與入口目錄同層存在時會觸發框架「檔案系統自動多頁」模式，使每個子頁被獨立註冊為可直接以 URL 存取的頁面，完全繞過 `app.py` 的 `st.login()` 守門（認證繞過）；同時側邊欄會以檔名（而非 `st.Page(title=...)` 設定的中文標題）顯示。改名為 `views/` 後，導覽只由 `app.py` 內的 `st.navigation` 程式化驅動，未登入時側邊欄不會出現任何子頁項目。
  - 依賴組裝集中在一個 `bootstrap` 模組（`src/asset_lab/bootstrap.py`），以 `@st.cache_resource` 快取 Repository/Service 實例（避免每次 rerun 重建連線）。
  - **修正（t16）**：`@st.cache_resource` 只保證「進程存活期間不重建」，不代表 Turso 遠端連線本身恆久有效——其 Hrana stream 閒置隔夜會被伺服器端關閉，快取住的連線與（綁定該連線的）容器不會自動感知，下次操作即拋「stream not found」類例外導致整頁崩潰（本機與 Community Cloud 長駐皆會發生）。新增 `bootstrap.get_resilient_container()`（`app.py` 改呼叫此函式取代直接呼叫 `get_container()`）：每次取用容器時以 `ensure_schema()`（idempotent 的 `CREATE TABLE IF NOT EXISTS`，順便當存活探測）驗證連線可用；偵測到訊息含 `stream not found` 的可重連失效樣態時，依序清「連線＋容器」兩層快取（`get_connection.clear()` + `get_container.clear()`）後重取一次並再驗證，成功即透明恢復、使用者無感；非此類例外（SQL 語法錯、約束違反等業務例外）原樣往上拋，且最多重試一次，不無限重連。
- **理由**：Streamlit 是 proposal 拍板的 UI 框架（SPEC §二已定案），其 rerun 模型與 `main.py` 批次模型不相容，硬套會產生死碼（argparse、biz_job 在常駐 Web App 無意義）。頁面即 Controller 是 Streamlit 社群慣例，符合「流程決策歸 Controller」的精神——頁面決定呼叫哪些 Service、如何呈現失敗。
- **否決方案**：
  - **硬套 `main.py` + argparse + biz_job**：在 Web App 中無對應語意（無批次、無退出碼、無 CLI 參數），會產生無法執行的死碼，否決。
  - **單一巨型 `app.py`（所有頁面與邏輯塞一支）**：演變成 Big Ball of Mud / God Object，違反分層，否決。
- **後果**：
  - 正面：符合 Streamlit 慣例、rerun 友善、依賴只建一次（cache_resource）。
  - 負面：偏離工程準則的標準入口骨架，需在 README / 本文件明確說明偏離理由；新接手者若預期 `main.py` 會找不到。緩解：入口檔命名 `app.py` 並於 README 標注啟動方式 `streamlit run app.py`。

### AD-2：分層結構——Page(View/Controller) → Service → Repository → Model
- **背景**：需求含大量業務運算（TWR 連乘、MWR/XIRR、配置佔比、目標偏離、淨值彙總），與 I/O（Turso 讀寫、CSV 匯出入），必須切分以免運算邏輯與 UI/IO 糾纏。
- **選擇**：
  ```
  app.py / views/*.py        ← View + 流程決策（呼叫哪些 Service、如何呈現）
        ↓
  services/*.py              ← 純業務運算（無 I/O；報酬率、配置、淨值、目標、CSV 整形）
        ↓
  repositories/*.py          ← 所有 I/O（libsql 對 Turso 的 SQL 讀寫）
        ↓
  models/*.py                ← pydantic 純資料結構
  core/                      ← constants.py（業務常數）、utils.py（純函式）、exceptions.py
  ```
  - **Service 不碰 I/O、不碰 Streamlit**（不 import streamlit、不 import libsql）；輸入輸出皆為 pydantic model / pandas DataFrame，可純函式式單元測試。
  - **Repository 不含業務判斷**：只負責 SQL 執行與 row↔model 轉換；TWR/XIRR 等不得進 Repository。
  - **Page 不直接寫 SQL、不算報酬率**：只渲染與委派。
- **理由**：報酬率口徑（BR-3/4/4e）是本專案最易錯、最需測試的核心，必須隔離為**不依賴 Streamlit、不依賴 DB** 的純 Service，才能用 pytest 餵固定現金流序列驗證。符合 02-architecture 維度 A（運算→Service、I/O→Repository）。
- **否決方案**：
  - **報酬率直接寫成 SQL 在 Repository 算**（SPEC 曾設想「報酬率就是一句 SQL」）：TWR 跨月連乘需排除當月淨投入、XIRR 需數值迭代求解、子維度現金流歸屬複雜，純 SQL 難維護且不可單元測試，否決。彙總性讀取（取某區間某維度的市值/淨投入序列）仍走 SQL；**報酬率的數值計算留在 Service**。
  - **Streamlit page 直接呼叫 libsql**：UI 與 I/O 強耦合，無法測試業務邏輯，否決。
- **後果**：正面＝核心算法可獨立測試、職責清晰；負面＝小專案下層數較多，但報酬率複雜度證成此切分（非過早優化）。

### AD-3：資料模型——項目主檔（穩定 ID）+ 月度時間序列 + 目標配置
- **背景**：BR-1b 要求項目以穩定 ID 識別（改名不斷裂歷史連乘）；BR-1 以 (年月, 項目ID) 為唯一鍵；BR-1e 項目分資產/負債；BR-5h 需各分類目標比重。
- **選擇**：三張表（Turso/SQLite schema，整數金額避免浮點誤差，金額以 TWD 元為單位用 `REAL` 或 `INTEGER`——見 AD-7 取捨）：

  **`holdings`（持有項目主檔）**
  | 欄 | 型別 | 說明 |
  |----|------|------|
  | `holding_id` | INTEGER PK AUTOINCREMENT | 穩定身分（BR-1b），改名不影響 |
  | `name` | TEXT NOT NULL | 顯示名稱（可改） |
  | `kind` | TEXT NOT NULL | `asset` / `liability`（BR-1e）|
  | `category` | TEXT NULL | 資產分類（受控清單 BR-7）；負債為 NULL（BR-1e） |
  | `initial_market_value` | REAL NULL | 初始市值（BR-1d）；負債為 NULL |
  | `initial_cost` | REAL NULL | 初始成本（BR-1d、BR-4e）；負債為 NULL |
  | `created_at` | TEXT | ISO 時間戳 |

  **`monthly_records`（項目 × 月份時間序列）**
  | 欄 | 型別 | 說明 |
  |----|------|------|
  | `holding_id` | INTEGER FK → holdings | |
  | `year_month` | TEXT (`YYYY-MM`) | 月份鍵 |
  | `market_value` | REAL NULL | 資產市值 / 負債餘額（同欄複用，依 kind 解讀；BR-1e/BR-5b）|
  | `net_investment` | REAL NOT NULL DEFAULT 0 | 當月淨投入，正＝投入負＝提領（BR-2）；負債不使用（恆 0 / 忽略）|
  | PRIMARY KEY (`holding_id`, `year_month`) | | 唯一鍵（BR-1）|

  **時間序列語意（已定案，見 AD-10）**：
  - **賣出當月**：記 `market_value=0`、`net_investment=−提領金額`（捕捉最後一期報酬與資金流出）。
  - **之後月份**：省略該項目列（**缺列＝已不持有**）。
  - **缺月**：序列以「有資料的月份」為節點，相鄰兩個有資料月之間視為一段期間（缺月跳過、不補插）；連乘、XIRR、圖表節點皆以有資料月為準。

  **`target_allocations`（分類目標配置，BR-5h）**
  | 欄 | 型別 | 說明 |
  |----|------|------|
  | `category` | TEXT PK | 資產分類 |
  | `target_weight` | REAL | 目標比重，以**百分比（%）**儲存（0–100）；各分類目標總和應為 100%（見 AD-10、BR-5h）|

  - 對應 pydantic models：`HoldingModel`、`MonthlyRecordModel`、`TargetAllocationModel`，皆純資料結構（03-data-config §3）。
  - 衍生計算結果（佔比、報酬率、淨值序列）用獨立 Result model（`ReturnResult`、`AllocationSnapshot`、`NetWorthPoint`、`DriftRow`），不混入主檔 model。
- **理由**：穩定 PK 滿足 BR-1b 連乘不斷裂；複合主鍵 (holding_id, year_month) 直接表達 BR-1 唯一性；分類記在 holdings 主檔 → BR-1b「改分類後歷史以當前分類回溯重算」自然成立（分類非時間版本化）。
- **否決方案**：
  - **以項目名稱當鍵**：改名即斷裂歷史，違反 BR-1b，否決。
  - **分類做成時間版本化（每月一筆分類）**：proposal BR-1b 明示「以當前分類回溯重算，非時間版本化」，過度工程，否決。
  - **資產與負債拆兩套表**：兩者月度結構幾乎相同（皆 (項目,月,金額)），拆表增加 JOIN 與匯出入複雜度；以 `kind` 欄區分更簡潔，否決拆表。
- **後果**：正面＝schema 貼合業務規則、唯一鍵由 DB 保證；負面＝`market_value` 一欄雙義（資產市值/負債餘額），需在 Service/Repository 明確以 `kind` 解讀（已於 §介面契約標注，並由 Scenario 覆蓋）。

### AD-4：報酬率計算口徑分工——Service 內三條獨立管線（BR-4e【強制】）
- **背景**：BR-4e 是 proposal 標【強制】的核心規則，也是最易錯處：TWR/MWR 須以**初始市值**起算（記錄後績效），賺賠金額與簡單總報酬率須以**初始成本**起算（含記錄前歷史）；**初始成本不得餵入 TWR/MWR**，否則記錄前價差被誤算成第一期報酬。
- **選擇**：在 `ReturnService` 內切三條互不汙染的計算管線，輸入來源在型別簽名上就分開：
  1. **TWR**（BR-3/4b）：以序列中「有資料的月份」為節點，相鄰兩個有資料月之間視為一段期間，逐段 `(期末市值 − 當月淨投入 − 期初市值) / 期初市值` 連乘（**缺月跳過，不補插**，見 AD-10）；首段期初市值＝初始市值；期初市值為 0 的建倉月不納入連乘（BR-3 邊界）。未滿 12 月不年化（BR-4b）。
  2. **MWR/XIRR**（BR-4/4c）：現金流序列＝首月初始市值視為流出（負）、各有資料月淨投入依正負號（投入流出為負/提領流入為正）、末月市值為流入（正）；交給 `pyxirr.xirr` 求解；不收斂時 fallback（見 AD-5）。未滿 12 月不年化。
  3. **P&L / 簡單總報酬率**（BR-4d）：累積成本＝初始成本 + Σ後續淨投入；賺賠＝市值 − 累積成本；簡單總報酬率＝賺賠 / 累積成本（累積成本為 0 不顯示）。
  - **API 層面強制隔離**：TWR/MWR 的函式簽名**只接受 `initial_market_value` 與月度市值/淨投入序列**，不接受 `initial_cost`；P&L 的函式**只接受 `initial_cost`**。型別簽名即護欄，從介面上杜絕 BR-4e 違規。
  - **三維度現金流歸屬（已定案）**（整體/分類/單一標的，BR-5）：以單一標的為計算原子，分類與整體由標的彙總；**每個維度的 TWR/MWR 以「該維度自身的淨投入序列 ＋ 該維度期末市值為終值」獨立計算**（標的層各自序列；分類/整體層為其成員標的同月淨投入與市值的彙總序列）；負債不納入（僅資產）。
- **理由**：把 BR-4e 的「不得混用」從「人工小心」升級為「型別系統保證」，是對抗本專案頭號風險的設計手段。三條管線各自純函式，可用固定數列 pytest 驗證（含 proposal 成功標準「某月額外投入本金不被算成報酬」）。
- **否決方案**：
  - **單一 `calculate_return()` 同時吃 initial_market_value 與 initial_cost**：易誤用、難防 BR-4e 違規，否決。
  - **用 `scipy.optimize` 自解 XIRR**：proposal 明確排除 scipy（肥大依賴），tech-research TD-2 已定 pyxirr，否決。
  - **缺月以前值/插值補滿再連乘**：補出的非真實節點會稀釋真實期間報酬，已定案改採「相鄰有資料月分段連乘」（AD-10），否決補插。
- **後果**：正面＝核心風險被介面強制隔離、高度可測、缺月與子維度歸屬規則已定案可直接寫 Scenario；負面＝三條管線各需序列前處理（區間切分、有資料月節點抽取、子維度彙總序列組裝），前處理邏輯量不小。

### AD-5：MWR/XIRR 不收斂的降級策略（BR-4 fallback）
- **背景**：BR-4 要求 XIRR 無法收斂時須有 fallback 呈現，不可讓單一指標失敗拖垮整頁。
- **選擇**：`ReturnService` 的 MWR 計算捕捉 `pyxirr` 的求解失敗（拋例外或回非有限值），回傳 `ReturnResult.mwr = None` 並附 `mwr_status = "not_converged"`；Page 層偵測 `None` 時顯示「MWR 無法計算」，TWR 與簡單報酬率照常呈現。
- **理由**：報酬率是並列三指標，單一失敗應局部降級而非整頁崩。此為 Service 對「可預期的計算邊界」的結果建模（回 Optional + 狀態旗標），非吞例外——pyxirr 的不收斂屬數值邊界而非系統錯誤。
- **否決方案**：讓例外往上拋到 Page 中斷整頁渲染 → 違反 BR-4「不拖垮整頁」，否決。
- **後果**：正面＝韌性、符合 BR-4；負面＝需在 Result model 明確標記狀態，Page 需處理 None 分支（由 Scenario 覆蓋）。

### AD-6：登入守門——`st.login()` Google OIDC + email 比對（BR-8）
- **背景**：BR-8 要求未登入須先登入、登入後比對 `st.user.email` 僅放行本人（單一，可擴充）；保護財務資料。
- **選擇**：在 `app.py` 最頂層（任何資料載入/頁面渲染之前）執行守門：未登入 → 顯示 `st.login()` 按鈕並 `st.stop()`；已登入但 `st.user.email` 不在受控允許清單 → 顯示拒絕訊息並 `st.stop()`，不渲染任何頁面、不觸發任何 Repository 讀取。允許 email 清單為受控設定（見 AD-7 存放決策）。
- **理由**：守門必須前置於資料存取，確保非本人「登入後也看不到任何財務資料」（proposal 成功標準）。`st.login()` 為 Streamlit ≥1.42 原生 OIDC（tech-research TD-4 確認可行）。
- **否決方案**：
  - **自建帳密資料表**：proposal 明示不做（§本次不做），否決。
  - **僅靠 `st.login()` 不比對 email**：任何 Google 帳號都能進，洩漏財務資料，否決。
- **後果**：正面＝財務資料受保護、零自建認證；負面＝依賴使用者自建 Google OAuth client 並正確設定 redirect_uri（本機+雲端兩網址）、同意畫面建議 Publish——屬運維前置（proposal §已知缺陷已列），非程式碼問題。

### AD-7：設定與機密存放——`st.secrets` 為唯一機密來源，業務常數進 constants.py
- **背景**：BR-9 要求 Turso 憑證與 OAuth 憑證本機走 `.streamlit/secrets.toml`（gitignore）、雲端走 Community Cloud Secrets UI，程式統一讀 `st.secrets`；BR-7 分類為受控清單；敏感資料護欄禁止寫死機密。
- **選擇**（套用 03-data-config 設定決策表，但以 Streamlit 機制替代 `.env`/argparse）：
  | 資料 | 存放 | 理由 |
  |------|------|------|
  | Turso URL / Auth Token、OAuth client_id/secret/cookie_secret/redirect_uri、**允許登入 email** | `st.secrets`（本機 `.streamlit/secrets.toml` gitignore；雲端 Secrets UI） | 機密 + 換部署環境會變（BR-8/BR-9）；email 屬個資（敏感資料護欄），不寫死 |
  | 資產分類受控清單初始值（台股/台股ETF、美股/美股ETF、現金/定存、保險）、`kind` 列舉值、再平衡偏離門檻預設、`YYYY-MM` 格式、DB 表名/欄名 schema | `core/constants.py`（嵌套 class） | 所有環境相同的業務規格（BR-7），非機密、進版控 |
  - `bootstrap.py` 從 `st.secrets` 讀機密、從 `constants` 讀業務常數，**以 keyword args 注入** Repository/Service（DI 原則 04-cross-cutting §3）；Service/Repository 內部不直接讀 `st.secrets` 或存取 constants 值（型別提示 import 例外）。
  - 金額型別取捨：以 `REAL`（TWD 元）儲存。否決「整數分」——本工具為月度手動輸入、無逐筆撮合，元級浮點對展示與報酬率足夠，整數分徒增轉換負擔（非過早優化）。報酬率計算在 Service 內以 float 進行。
- **理由**：`.streamlit/secrets.toml` 已在 `.gitignore`（已確認），符合 BR-9 與敏感資料護欄；分類清單為業務規格放 constants 符合決策表「什麼都不換」欄。
- **否決方案**：把允許 email / Turso token 寫進 constants.py 或程式碼 → 機密進版控，違反敏感資料護欄與 BR-9，否決。
- **後果**：正面＝機密零進版控、設定來源清晰；負面＝本機開發需手動建 `.streamlit/secrets.toml`（README 須提供範本，但範本只放佔位符不放真值）。

### AD-8：Logging 與錯誤處理——以標準 `logging` + Streamlit UI 反饋替代 utils_v2 / biz_job
- **背景**：04-cross-cutting 規範以 `structlog` + `utils_v2` 的 `init()`/`biz_job()` 為基礎設施；本專案無 utils_v2，且 Streamlit App 無 `biz_job` 的批次 job 語意。
- **選擇**：
  - 用標準庫 `logging`（`logger = logging.getLogger(__name__)` 模組頂層宣告，不經建構子注入——保留 04-cross-cutting §1.1 精神），於 `bootstrap` 統一設定 level。
  - **錯誤反饋雙軌**：Service/Repository 的錯誤**往上拋**（保留 02/04 的「錯誤往上拋、下層不吞」原則）；**Page 層為唯一 catch 點**（取代 RPA 的 Controller 角色），catch 後 `st.error(...)` 對使用者顯示友善訊息 + `logger.exception(...)` 記錄，不讓 traceback 直接噴到 UI。
  - 不採用 structlog 的 event-name/note/log_type 強制欄位格式——該格式綁定 utils_v2 pipeline，無 pipeline 時形同空轉；改以可讀的中文 log message + 必要 context。
- **理由**：在無 utils_v2、無 Loki pipeline、互動式 UI 的環境下，硬套 structlog 欄位契約只是形式主義；「下層拋、UI 層 catch 並反饋使用者」才是 Web App 的正確容錯邊界，且保留了規則的核心精神（錯誤往上拋、單一 catch 點、不重複 log）。
- **否決方案**：
  - **強行 import utils_v2 / structlog**：套件不存在，否決。
  - **Service/Repository 自行 catch 並 `st.error`**：下層耦合 Streamlit、違反分層與「下層不吞例外」，否決。
- **後果**：正面＝符合 Streamlit 容錯實況、保留分層精神；負面＝偏離 04-cross-cutting 的 structlog 欄位契約，需在本文件明示（已記此 ADR），3-3 規則符合度審查時以本 ADR 為偏離依據。

### AD-9：CSV 匯出/匯入——成對全量，匯入須驗證唯一鍵（BR-12）
- **背景**：BR-12 要求匯出全部原始紀錄（主檔含性質/初始市值/初始成本/分類 + 月度列）、匯入可還原到新的 Turso DB，且匯入須驗證格式與唯一鍵避免重複污染。
- **選擇**：`DataIoService`（純整形：model↔DataFrame↔CSV bytes，無 I/O）+ `HoldingRepository`/`RecordRepository` 提供批次寫入。匯出/匯入採**含表頭的標準 CSV**（已定案，第一列為欄位標題）供 `st.download_button` 下載 / `st.file_uploader` 上傳；匯入由 Page 收位元組 → Service 解析驗證（表頭齊全、(holding_id, year_month) 不重複、kind/分類合法）→ Repository 批次寫入空庫。匯入前置檢查目標庫是否為空（避免污染既有資料）。三類資料（holdings/records/targets）以多份標準 CSV 處理（各自含表頭），對外欄位即各 model 的欄位。
- **理由**：整形屬運算歸 Service；批次寫入屬 I/O 歸 Repository；驗證唯一鍵是業務判斷歸 Service。含表頭標準 CSV 對 SQL 母語使用者最直觀、Excel/pandas 通吃。符合分層與 BR-12。
- **否決方案**：
  - Page 直接讀 CSV 寫 DB → 跳過驗證與分層，易污染資料，否決。
  - 單檔多區段（一個 CSV 塞三表）→ 表頭不一致、解析需自訂分隔，破壞「標準 CSV」的通用性，否決。
- **後果**：正面＝資料保全可靠、職責清晰、標準 CSV 通用易讀；負面＝CSV 欄位（即 model 欄位）為對外契約，發布後改欄位須維持相容。

### AD-10：時間序列語意——不再持有的表示法、缺月處理、目標比重單位（已定案）
- **背景**：proposal §已知缺陷列出三個影響連乘/帶入/圖表的待決點（「不再持有」表示法、缺月處理、目標比重單位），須在進入 Scenario 前定案，否則 TWR 連乘節點、XIRR 現金流對齊、BR-1c 帶入邏輯、目標偏離單位都無法明確化。
- **選擇**（使用者已定案）：
  1. **賣出/不再持有的表示法**：賣出當月**記 `market_value=0`、`net_investment=−提領金額`**（捕捉最後一期報酬與資金流出，使該月仍進 TWR 末段與 XIRR 終值）；**之後月份省略該項目列**（缺列＝已不持有，不再帶入 BR-1c、不進後續任何維度）。
  2. **缺月處理**：序列以「有資料的月份」為節點，**相鄰兩個有資料月之間視為一段期間**計報酬（缺月跳過、不補插值）；TWR 逐段連乘、XIRR 現金流、所有圖表節點皆以有資料月為準。
  3. **目標比重單位**：**百分比（%），0–100**；各分類目標總和應為 100%；偏離（BR-5h）= 現況% − 目標%，門檻亦以百分點計（預設可設）。全程（DB `target_weight`、Model `target_weight`、UI 輸入、`DriftRow.target_weight/current_weight/drift`）統一以 % 表示，不混用 0–1。
- **理由**：
  - 「賣出當月 0 + 之後缺列」讓最後一期報酬與資金流出都被正確捕捉，又不需要「持有中歸零 vs 已賣出」的額外狀態欄；語意單一（缺列＝不持有）。
  - 「相鄰有資料月分段連乘」避免補插的非真實節點稀釋真實期間報酬，且讓缺月不致中斷整段序列。
  - % 為使用者最直覺的配置語言（「目標 60%」），且總和 100% 易於現場校驗。
- **否決方案**：
  - **賣出後仍續記市值 0 列**：無法區分「持有歸零」與「已出清」，且永久產生空列污染帶入清單，否決。
  - **缺月以前值/線性插值補滿**：見 AD-4 否決理由（稀釋真實報酬），否決。
  - **比重存 0–1**：與 UI/門檻單位易混淆，每處轉換徒增 off-by-100 風險，否決。
- **後果**：正面＝三個原未決點全數可直接落入 Scenario，連乘/帶入/偏離無歧義；負面＝「賣出當月 0、之後缺列」是約定俗成的隱性契約，須在錄入頁與 README 明確提示使用者（避免誤記成續記 0 列），由 Scenario 覆蓋此錄入行為。

---

## 技術選型

> 以下釘住 `tech-research.md` 的結論並標注設計階段定案；信心度沿用 tech-research 評估。

### TD-1：Turso 連線套件 — `libsql`（已定案）
- **推薦**：`libsql`（信心度：High）。原 proposal/SPEC 寫的 `libsql-client` 已棄用（websocket driver 隨 AWS 遷移失效）；**proposal §外部依賴 與 SPEC §二 的套件名已更正為 `libsql`（於 1-2a commit caae4df 落定），無待辦**。
- **理由**：官方現行唯一遠端連線 SDK，API 近似 sqlite3、無編譯依賴、Community Cloud 可 pip 安裝。資料量極小（年約 12×N 列）+ 使用者 SQL 為母語 → **不引入 ORM（否決 sqlalchemy-libsql，過度工程）**，Repository 直接寫原生 SQL。連線於 `bootstrap` 以 `@st.cache_resource` 建一次；**閒置逾時的自動重連見 AD-1「修正（t16）」**——libsql 的 Python binding 未提供公開的「連線層自動重開」API（compiled extension，無可查證的重連方法），故重連採「清快取＋重新呼叫 `libsql.connect()`」而非連線物件自我修復，是查證過套件實際行為後的務實選擇。

### TD-2：XIRR / MWR — `pyxirr`
- **推薦**：`pyxirr`（0.10.x，信心度：High）。
- **理由**：Rust 實作、有 manylinux+cp312 prebuilt wheel、Community Cloud 零摩擦、體積遠小於 scipy（proposal 明確排除 scipy）。不收斂 fallback 見 AD-5。

### TD-3：圖表 — Plotly（已定案）
- **推薦**：Plotly 一套到底（信心度：High，使用者已確認）。`px.pie`（圓餅 BR-5c）、`px.line`（淨值 BR-5b / 報酬走勢 BR-5g）、`px.area`（堆疊面積 BR-5d，`groupnorm="percent"`）。
- **理由**：Streamlit 原生無圓餅圖（硬約束），Plotly 一套語法覆蓋四類圖、互動開箱即用。Altair 已不採用；圖表渲染集中於 `charts.py` 元件層。

### TD-4：登入 — `st.login()`（Streamlit ≥ 1.42 原生 OIDC）
- **推薦**：`st.login()` + Google OIDC（信心度：High，已拍板確認）。版本下限 `streamlit>=1.42` 釘進 requirements。架構落地見 AD-6。

### TD-5：資料整形 — `pandas`（建議納入）
- **推薦**：`pandas`（信心度：High）。
- **理由**：TWR 跨月連乘、區間切分（YTD/近一年/自訂 BR-5e/5f）、三維度 groupby 彙總、CSV 匯出入，用 DataFrame 最直接；資料量極小無效能顧慮。tech-research 建議納入，本設計確認採用。

**requirements 草案**：`streamlit>=1.42`、`libsql`、`pyxirr`、`plotly`、`pandas`。

---

## 介面契約

> 以下為各層 public 介面骨架（簽名 + 職責）。所有注入一律 keyword args；Service 不 import streamlit/libsql；Repository 不含業務判斷。
> 行為細節（邊界值、錯誤路徑）由 1-3 Scenarios 以 BR 編號定義，此處不重述。

### Models（`src/asset_lab/models/`）— 純資料結構（pydantic）

```python
class HoldingModel(BaseModel):
    """持有項目主檔。kind 為 'asset'/'liability'；負債的 category/initial_* 為 None。"""
    holding_id: Optional[int]          # 新增時 None，DB 產生後回填
    name: str
    kind: str                          # 'asset' | 'liability'
    category: Optional[str]            # 負債為 None
    initial_market_value: Optional[float]
    initial_cost: Optional[float]

class MonthlyRecordModel(BaseModel):
    """(holding_id, year_month) 月度紀錄。資產 market_value=市值；負債 market_value=餘額。"""
    holding_id: int
    year_month: str                    # 'YYYY-MM'
    market_value: Optional[float]      # 賣出當月記 0；缺列＝已不持有（AD-10）
    net_investment: float = 0.0        # BR-2 正投入負提領；賣出當月記 −提領金額（AD-10）；負債不使用

class TargetAllocationModel(BaseModel):
    """分類目標配置（BR-5h）。"""
    category: str
    target_weight: float               # 百分比 0–100；各分類總和應為 100%（AD-10）

# --- Result models（計算輸出，與主檔分離）---
class ReturnResult(BaseModel):
    """單一維度的報酬率結果（BR-4/4d/4e/5）。"""
    dimension: str                     # 'overall' | 'category' | 'holding'
    dimension_key: Optional[str]       # 分類名或 holding_id（overall 為 None）
    twr: Optional[float]
    mwr: Optional[float]               # 不收斂時 None（AD-5）
    mwr_status: str                    # 'ok' | 'not_converged'
    simple_return: Optional[float]     # 累積成本為 0 時 None（BR-4d）
    pnl_amount: Optional[float]        # 賺賠金額（BR-4d）
    annualized: bool                   # 未滿 12 月為 False（BR-4b）

class AllocationSnapshot(BaseModel):
    """某月份單一資產項目/分類佔比（BR-5c，僅資產）。"""
    year_month: str
    dimension_key: str                 # 項目名或分類
    market_value: float
    weight: float                      # 佔比，百分比 0–100（與目標 % 同單位，AD-10）

class NetWorthPoint(BaseModel):
    """淨值趨勢單點（BR-5b）。"""
    year_month: str
    total_assets: float
    total_liabilities: float
    net_worth: float

class DriftRow(BaseModel):
    """目標偏離單列（BR-5h）。權重一律百分比 0–100（AD-10）。"""
    category: str
    current_weight: float              # %
    target_weight: float              # %
    drift: float                       # current - target，百分點
    needs_rebalance: bool              # |drift| > 門檻（百分點）
```

### Repositories（`src/asset_lab/repositories/`）— 只做 I/O（libsql + 原生 SQL）

```python
class HoldingRepository:
    """持有項目主檔 I/O。連線由 bootstrap 注入。"""
    def __init__(self, *, conn) -> None: ...
    def list_holdings(self) -> list[HoldingModel]: ...
    def get_holding(self, *, holding_id: int) -> Optional[HoldingModel]: ...
    def add_holding(self, *, holding: HoldingModel) -> int: ...        # 回傳新 holding_id
    def update_holding(self, *, holding: HoldingModel) -> None: ...     # 改名/改分類（BR-1b）
    def replace_all(self, *, holdings: list[HoldingModel]) -> None: ... # CSV 匯入用（批次）

class RecordRepository:
    """月度紀錄 I/O。(holding_id, year_month) 為唯一鍵（BR-1）。
    寫入分兩條語義不同的路徑（不可合併）：
      - insert_record：嚴格新增（SC-007），撞唯一鍵須拒絕
      - upsert_record：在地更新（SC-006 編輯），同鍵覆寫不產生重複列
    """
    def __init__(self, *, conn) -> None: ...
    def read_month(self, *, year_month: str) -> list[MonthlyRecordModel]: ...
    def read_range(self, *, start_ym: str, end_ym: str) -> pd.DataFrame: ...   # 報酬率/趨勢用
    def read_all(self) -> pd.DataFrame: ...                                    # CSV 匯出用
    def latest_year_month(self) -> Optional[str]: ...                          # 帶入上月用（BR-1c）
    def insert_record(self, *, record: MonthlyRecordModel) -> None: ...        # 嚴格新增（SC-007）；撞 (holding_id, year_month) 唯一鍵 → DataValidationError
    def upsert_record(self, *, record: MonthlyRecordModel) -> None: ...        # 在地更新（SC-006 編輯）；同鍵覆寫，不產生重複列
    def delete_record(self, *, holding_id: int, year_month: str) -> None: ...
    def replace_all(self, *, records: list[MonthlyRecordModel]) -> None: ...   # CSV 匯入批次

class TargetRepository:
    """分類目標配置 I/O（BR-5h）。"""
    def __init__(self, *, conn) -> None: ...
    def read_targets(self) -> list[TargetAllocationModel]: ...
    def upsert_target(self, *, target: TargetAllocationModel) -> None: ...
    def read_all(self) -> list[TargetAllocationModel]: ...                     # CSV 匯出用

class SchemaRepository:
    """建表（首次啟動建立三張表 if not exists）。"""
    def __init__(self, *, conn) -> None: ...
    def ensure_schema(self) -> None: ...
```

### Services（`src/asset_lab/services/`）— 純業務運算（無 I/O、無 Streamlit）

```python
class MonthlyInputService:
    """月度錄入業務邏輯（BR-1c 帶入上月、BR-11 成對轉移）。"""
    def __init__(self, *, holding_repo: HoldingRepository, record_repo: RecordRepository) -> None: ...
    def prefill_from_previous(self, *, target_ym: str) -> list[MonthlyRecordModel]: ...
        # 帶入上月「有資料且仍持有」項目清單，市值留空、淨投入預設 0（BR-1c）；
        # 上月缺列（已賣出，AD-10）的項目不帶入；首月從主檔挑（無上月）
    def build_transfer_pair(self, *, source_id: int, dest_id: int, amount: float,
                            year_month: str) -> tuple[MonthlyRecordModel, MonthlyRecordModel]: ...
        # 來源記 -amount、目標記 +amount（BR-11）；實際寫入由 Page 委派 Repository

class ReturnService:
    """報酬率三口徑計算（BR-3/4/4b/4c/4d/4e/5/5e/5f/5g）。BR-4e 由簽名強制隔離。
    所有序列以「有資料的月份」為節點，相鄰有資料月間分段計算（缺月跳過，AD-10）。"""
    def __init__(self) -> None: ...     # 純運算，無依賴
    # --- TWR：只吃市值/淨投入序列 + 初始市值，不吃 initial_cost（BR-4e 護欄）---
    #     monthly 僅含有資料月，相鄰兩月為一段連乘（AD-10）
    def compute_twr(self, *, monthly: pd.DataFrame, initial_market_value: float) -> Optional[float]: ...
    # --- MWR/XIRR：同樣不吃 initial_cost；不收斂回 (None, 'not_converged')（AD-5）---
    def compute_mwr(self, *, monthly: pd.DataFrame,
                    initial_market_value: float) -> tuple[Optional[float], str]: ...
    # --- P&L / 簡單總報酬率：只吃 initial_cost，不碰 TWR/MWR（BR-4d/4e 護欄）---
    def compute_pnl(self, *, monthly: pd.DataFrame,
                    initial_cost: float) -> tuple[Optional[float], Optional[float]]: ...  # (pnl, simple_return)
    def compute_returns(self, *, range_df: pd.DataFrame, holdings: list[HoldingModel],
                        dimension: str, start_ym: str, end_ym: str) -> list[ReturnResult]: ...
        # 彙總三維度（overall/category/holding，僅資產 BR-5）；每維度以「自身淨投入序列＋
        # 自身期末市值為終值」獨立組現金流計 XIRR（AD-4）；組合上述三管線；未滿12月不年化（BR-4b）

class AllocationService:
    """配置佔比、漂移、淨值（BR-5b/5c/5d/5h，僅資產不含負債）。權重一律 % 0–100（AD-10）。"""
    def __init__(self) -> None: ...
    def snapshot(self, *, month_records: list[MonthlyRecordModel],
                 holdings: list[HoldingModel], by: str) -> list[AllocationSnapshot]: ...  # by='holding'|'category'
    def drift_series(self, *, range_df: pd.DataFrame, holdings: list[HoldingModel]) -> pd.DataFrame: ...
        # 堆疊面積資料；以有資料月為節點（AD-10）
    def net_worth_series(self, *, range_df: pd.DataFrame,
                         holdings: list[HoldingModel]) -> list[NetWorthPoint]: ...  # 淨值=Σ資產-Σ負債
    def compute_drift(self, *, snapshot: list[AllocationSnapshot],
                      targets: list[TargetAllocationModel], threshold: float) -> list[DriftRow]: ...
        # BR-5h；threshold 以百分點計（如 5.0）；drift=現況% − 目標%（AD-10）

class PeriodService:
    """報酬率區間解析（BR-5e/5f，Asia/Taipei 時區）。純函式。"""
    def resolve_period(self, *, mode: str, latest_ym: str,
                       custom_start: Optional[str], custom_end: Optional[str]) -> tuple[str, str]: ...
        # mode='inception'|'ytd'|'last_12m'|'custom' → (start_ym, end_ym)

class DataIoService:
    """CSV 匯出/匯入整形與驗證（BR-12）。含表頭標準 CSV（AD-9/AD-10）。純整形，I/O 委派 Repository。"""
    def export_holdings_csv(self, *, holdings: list[HoldingModel]) -> bytes: ...    # 含表頭
    def export_records_csv(self, *, records: pd.DataFrame) -> bytes: ...            # 含表頭
    def export_targets_csv(self, *, targets: list[TargetAllocationModel]) -> bytes: ...  # 含表頭
    def parse_and_validate(self, *, holdings_csv: bytes, records_csv: bytes, targets_csv: bytes,
                           target_db_empty: bool
                           ) -> tuple[list[HoldingModel], list[MonthlyRecordModel], list[TargetAllocationModel]]: ...
        # 驗證表頭齊全、(holding_id, year_month) 唯一鍵不重複、kind/分類合法、目標%總和；失敗拋例外（Page catch → st.error）
        # target_db_empty：目標庫是否為空（SC-032「非空須拒絕」）。空庫與否是 I/O 事實，
        #   依 AD-2 Service 須純運算（無 I/O），故由 Page 層查 Repository 後注入此布林旗標；
        #   「非空即拒（→ DataValidationError）」的業務判斷留在 Service。
```

### core（`src/asset_lab/core/`）
- `constants.py`：`ASSET_CATEGORIES`（BR-7 受控清單初始值）、`HOLDING_KIND`（asset/liability）、`PERIOD_MODE`、`DEFAULT_REBALANCE_THRESHOLD`（百分點，預設如 5.0，AD-10）、`YEAR_MONTH_FORMAT`、DB 表名/欄名 schema、`TIMEZONE="Asia/Taipei"`（BR-5f）。皆業務常數，不含機密。
- `utils.py`：純函式——如 `year_month_add`（月份加減）、`parse_year_month`、`adjacent_periods`（從有資料月序列抽相鄰期間段供分段連乘，AD-10）。無 I/O、無業務流程判斷。
- `exceptions.py`：`DataValidationError`（CSV 匯入驗證失敗）、`SchemaError` 等業務例外。

### 入口與組裝（`app.py` + `src/asset_lab/bootstrap.py`）
- `app.py`：`st.login()` 守門（AD-6）→ `bootstrap.get_resilient_container()`（cached 依賴，含閒置逾時自動重連，見 AD-1「修正（t16）」）→ `st.navigation` 路由。
- `bootstrap.py`：
  ```python
  @st.cache_resource
  def get_connection():           # libsql.connect(database=st.secrets[...], auth_token=...)
  @st.cache_resource
  def get_container():            # 讀 st.secrets（機密）+ constants（業務常數），keyword-args 注入 Repo/Service
  def get_resilient_container() -> Container:  # 取容器＋驗證連線存活；失效則清快取重連重試一次（t16）
  def allowed_emails() -> set[str]:   # 從 st.secrets 讀允許清單（BR-8，個資不寫死）
  ```
- `views/*.py`：View+流程決策（Controller 角色）；唯一 catch 點（AD-8）；呼叫 Service、把結果交 `charts.py`（Plotly 元件）渲染。資料夾名刻意避開 Streamlit 保留字 `pages/`（見 AD-1 修正說明），僅由 `app.py` 的 `st.navigation` 程式化註冊路由。

---

## 已知技術債與限制

- **`market_value` 一欄雙義**（資產市值/負債餘額）：靠 `kind` 解讀。簡化了 schema 但增加讀取端心智負擔，已於介面標注、由 Scenario 覆蓋。
- **金額用 float（TWD 元）**：月度手動輸入場景下精度足夠；若未來引入逐筆撮合或極大金額才需重評整數分。
- **外幣資產內含匯率波動**（BR-6 刻意取捨）：美股等以使用者自換 TWD 輸入，報酬率含匯率影響——proposal 已聲明為刻意取捨，非缺陷。
- **logging 偏離 structlog 欄位契約**（AD-8）：無 utils_v2 pipeline 下的合理偏離；若日後此 monorepo 引入 utils_v2，logging 層可再對齊。
- **CSV 為對外契約**：含表頭標準 CSV，欄位即各 model 欄位（AD-9/AD-10）；一旦發布即須維持相容，未來改欄位須考慮回溯相容。
- **「賣出當月 0、之後缺列」為隱性錄入約定**（AD-10）：須在錄入頁與 README 明確提示，避免使用者誤記成續記 0 列；由 Scenario 覆蓋此錄入行為。
- **連線存活探測以 `ensure_schema()` 代表整條連線**（t16）：假設同一條連線的 Hrana stream 若已失效，其上任何操作都會以同一樣態失敗，故用它探測即可代表本次 rerun 對所有 Repository 呼叫皆有效，不逐一探測每個 Repository；若未來 libsql 出現「部分操作失效、部分正常」的樣態，此假設需重新檢視。
- **`app.py` 頂層以環境變數規避 pyarrow 原生記憶體配置器相容性問題**（t17）：pyarrow 25 內建的 mimalloc 配置器在 macOS arm64 有 thread-init segfault，使用者本機操作（編輯月度錄入、切頁）觸發 Streamlit 顯示 DataFrame 的 pandas→Arrow 轉換時，曾實測整個 Python 進程 `EXC_BAD_ACCESS` 崩潰——與本專案業務邏輯無關，是第三方原生套件的平台相容性 bug。`app.py` 在 `import streamlit` 之前搶先 `os.environ.setdefault("ARROW_DEFAULT_MEMORY_POOL", "system")` 停用 mimalloc、改用系統 malloc，已驗證可規避；因 pyarrow 只在自身被 import 的當下讀取此環境變數，這行必須早於（連帶 import pyarrow 的）Streamlit import，故此檔案 import 順序刻意偏離慣例。此為執行環境層級的防呆，非業務行為，未新增 Scenario；若未來 pyarrow 修正此問題或專案改採其他資料表元件，可評估移除此環境變數設定。

---

## 已定案決策（原未決事項，已整合，使用者 2026-06-14 拍板）

> 以下 7 項原列「未決事項」，使用者已逐項定案並整合進對應 schema/ADR/介面契約；本節保留決策摘要供追溯。**目前無待確認的未決點。**

| # | 原議題 | 定案 | 落點 |
|---|--------|------|------|
| 1 | 不再持有表示法 | 賣出當月記市值=0、淨投入=−提領金額；之後月份省略該項目列（缺列＝已不持有） | AD-10、AD-3 schema、MonthlyRecordModel、MonthlyInputService |
| 2 | 缺月處理 | 以有資料月為節點，相鄰兩有資料月為一段期間計報酬（缺月跳過不補插）；圖表同以有資料月為節點 | AD-10、AD-4、ReturnService、AllocationService、utils.adjacent_periods |
| 3 | 子維度 MWR 現金流歸屬 | 各維度以「自身淨投入序列＋自身期末市值為終值」獨立計 XIRR | AD-4、ReturnService.compute_returns |
| 4 | 目標比重單位 | 百分比 %（0–100），各分類總和應為 100% | AD-10、AD-3 schema、TargetAllocationModel、DriftRow、AllocationSnapshot、AllocationService、constants |
| 5 | CSV 格式 | 含表頭的標準 CSV（三類資料各一份標準 CSV） | AD-9、DataIoService |
| 6 | 圖表庫 | Plotly（確認，非待選） | TD-3、charts.py |
| 7 | Turso 套件名 | `libsql`（proposal 與 SPEC 已更正完成） | TD-1 |

---

## 決策總覽

| ID | 類型 | 決策 | 信心度 |
|----|------|------|--------|
| AD-1 | 架構 | Streamlit 多頁 App（`app.py` + `views/`，程式化 `st.navigation`，避開保留字 `pages/`）取代 RPA `main.py`/biz_job 入口模型 | High |
| AD-2 | 架構 | 分層 Page(View/Controller)→Service(純運算)→Repository(I/O)→Model | High |
| AD-3 | 架構 | 三表 schema：holdings（穩定 ID）+ monthly_records（複合鍵）+ target_allocations | High |
| AD-4 | 架構 | 報酬率三管線（TWR/MWR/PnL），BR-4e 以函式簽名強制隔離初始市值 vs 初始成本 | High |
| AD-5 | 架構 | MWR/XIRR 不收斂回 None+狀態旗標，Page 局部降級不拖垮整頁 | High |
| AD-6 | 架構 | `st.login()` Google OIDC + email 比對守門，前置於任何資料存取 | High |
| AD-7 | 架構 | 機密走 `st.secrets`（含允許 email），業務常數進 constants.py | High |
| AD-8 | 架構 | 標準 logging + Page 層唯一 catch + st.error 反饋，替代 utils_v2/biz_job/structlog | Medium |
| AD-9 | 架構 | CSV 含表頭標準格式（三類各一份）全量匯出入，匯入驗證唯一鍵與合法性後批次寫空庫 | High |
| AD-10 | 架構 | 時間序列語意：賣出當月記0+之後缺列、缺月分段連乘、目標比重用 %（0–100） | High |
| TD-1 | 技術 | Turso 連線用 `libsql`（proposal/SPEC 已更正），不引 ORM | High |
| TD-2 | 技術 | XIRR/MWR 用 `pyxirr`（排除 scipy） | High |
| TD-3 | 技術 | 圖表用 Plotly 一套到底（已確認，非待選） | High |
| TD-4 | 技術 | 登入用 `st.login()`（streamlit>=1.42 原生 OIDC） | High |
| TD-5 | 技術 | 資料整形納入 pandas | High |
