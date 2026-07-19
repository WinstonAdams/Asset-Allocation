# 設計文件：behavior-protocol（大跌行為協定內建化）

> 本文件整合 `proposal.md`（需求基準），並延伸既有子專案 `initial-build/design.md`（10 條 ADR、分層 Page→Service→Repository→Model、Turso/libsql、`st.navigation` 多頁）。
> **1-2a 技術選型／1-2b 架構分析已於 progress 標「跳過」**（無新技術棧、非 greenfield 由本設計直接讀既有 codebase 整合），故無 `tech-research.md` / `architecture-brief.md`。
> **關於 utils_v2**：本 workspace 子專案 `資產管理/` 不存在 `utils_v2/`（已 `find` 確認），此為 initial-build AD-1／AD-8 已記載的既定偏離；本 Change 不新增機密、不新增第三方依賴，故 `utils_v2/google/sheets`、`utils_v2/setup` 的 API 無適用面，沿用 initial-build 的偏離依據（標準 `logging` + Page 層唯一 catch），不另套 v2 工具。
> 本文件僅含**架構決策與介面契約**，**不含業務行為（GIVEN/WHEN/THEN）**；對應的 Scenarios 將由後續 1-3 階段（scenario-author）以 proposal 的 BR 編號展開產出。

---

## 現況評估

- **既有模式（沿用，不另起爐灶）**：
  - **分層**：Page（`views/*.py`，View+Controller 複合、唯一 catch 點）→ Service（純運算，不 import streamlit/libsql）→ Repository（libsql 原生 SQL I/O）→ Model（pydantic 純資料）；`core/`（constants/utils/exceptions）。本 Change 全部新元件依此歸位。
  - **依賴注入**：`bootstrap.build_container` 以 keyword args 一次組裝所有 Repo/Service 成 `Container`；`app.py` 放行後 `get_resilient_container()` 存入 `st.session_state["container"]`，各頁 `_container()` 取用。新元件一律進 `Container`，頁面不自行 new。
  - **多頁路由**：`app.py` 以程式化 `st.navigation([st.Page(...), ...])` 註冊，頁面檔集中於**專案根目錄 `views/`**（刻意避開 Streamlit 保留字 `pages/`，見 initial-build AD-1；避免認證繞過）。每個 view 檔尾端直接呼叫 `render()`。
  - **可配置設定持久化樣式**：既有「目標配置」= `target_allocations` 表（`category` PK、`target_weight` REAL）+ `TargetRepository`（`read_targets` / `upsert_target`，`ON CONFLICT DO UPDATE`）+ 設定頁 `_render_targets` 編輯。**本 Change 的門檻設定完全比照此樣式**。
  - **報酬率／淨值引擎**：`ReturnService.cumulative_twr_series()` 已產出「逐有資料月的整體累積 TWR 序列」（`list[CumulativeTwrPoint]`，僅資產、排除淨投入）；`AllocationService.net_worth_series()` 產出逐月淨值。本 Change **只消費其輸出**，不改其邏輯（proposal §本次不做、§外部依賴）。
  - **常數／機密決策**：業務常數進 `core/constants.py`（嵌套 class、dot-notation）；機密走 `st.secrets`。本 Change 無新機密，僅新增業務常數。
- **偏離**：無新增偏離。沿用 initial-build 既有兩項偏離（無 `main.py`/argparse 的 Streamlit 入口模型 AD-1；標準 `logging` 取代 structlog/biz_job AD-8），本 Change 之新頁面／服務落在同一偏離框架內，不擴大偏離面。
- **架構警訊自檢**：新增 1 個純運算 Service（`ProtocolService`）、2 個薄 Repository（門檻、協定文件）、2 個 view、若干常數/model —— 皆為**與既有同構的小元件**，不塞進既有檔案、不做通用 KV 設定表（避免過度工程），不讓 `overview.py` 變 God Object（判定歸 Service、I/O 歸 Repository、文字歸 constants）。

---

## 架構決策

### AD-1：回撤基準採「累積 TWR 指數回撤」，否決「排除淨投入後的淨值序列回撤」
- **背景**：proposal §已知缺陷要求二選一定案，作為「大盤回撤」的自身資料 proxy（BR-1）。系統無任何行情 API，只能用使用者投組資料推算，須挑一個「最能代表市場績效跌幅、且最不受個人資金進出污染」的序列。
- **選擇**：以**整體資產的累積 TWR（時間加權報酬率）指數**作為回撤基準序列，直接**消費既有 `ReturnService.cumulative_twr_series()`** 的輸出（`list[CumulativeTwrPoint]`，逐有資料月、僅資產、已排除淨投入）。
  - **指數路徑**：對序列每個節點取 `index_i = 1 + cumulative_twr_i`（`cumulative_twr` 為百分比小數，指數即成長倍數）；並在路徑最前端**納入建倉基準點 `index = 1.0`（起始月 0% 累積報酬）**，構成完整指數路徑 `[1.0, index_1, index_2, …]`。
  - **歷史高點（high-water mark）**：`peak = max(指數路徑)`（BR-4「取所有已記錄月份中基準序列的最大值」，含起始基準 1.0）。
  - **目前回撤**：`drawdown = current / peak − 1`（`current = 指數路徑最後一點`），結果為 ≤ 0 的小數（如 −0.22 表 −22%）。
- **理由**：
  1. **TWR 天生排除資本流動**——每段報酬已扣除當月淨投入（`compute_twr` 逐段 `(期末 − 當月淨投入 − 期初)/期初`），故此指數只反映市場績效漲跌，「當月多投入本金」不會抬高指數、「提領」不會壓低指數。這正是「大盤回撤 proxy」要的語意。
  2. **PROTOCOL.md 自身背書**：§3 行為防火牆第 1 條明言「看累積 TWR 走勢…排除資本流動的報酬率引擎,就是為這一天寫的」——把回撤基準綁到累積 TWR，與協定文本一致。
  3. **零核心改動、可測試**：`cumulative_twr_series()` 已存在且由既有 SC 覆蓋；本 Change 只在其輸出上做指數化與 max/current 比較（純運算），完全符合 proposal「只消費 ReturnService 輸出、不改報酬率引擎核心」。
  4. **納入起始基準 1.0** 確保「只跌不漲」的投組仍以建倉點為高點量測回撤，避免以「第一個已下跌月」當高點而**低報**跌幅。
- **否決方案**：
  - **排除淨投入後的淨值序列回撤**：`net_worth_series()` 的淨值 = 總資產 − 總負債，**同時混入市場績效、資金進出、負債變動**。要「排除淨投入」等同要重建一條剔除現金流的指數——本質就是再造一次 TWR，重工且易與既有引擎口徑分歧。且淨值受「還房貸／提領現金」等非市場因素牽動，可能把一次大額提領誤判成 L3 深熊，違反「不誤報大跌」（BR-6）。否決。
  - **用單月市值變動或含負債的淨值直接算回撤**：同上污染問題，且負債不屬「大盤」範疇，否決。
- **後果**：
  - 正面：proxy 口徑乾淨、與協定文本一致、零核心改動、可獨立單元測試；回撤基準與報酬率頁的累積 TWR 走勢圖同源，使用者兩處看到的數字自洽。
  - 負面：TWR 為月度粒度（BR-4），回撤隨每月錄入更新、非即時——proxy 的先天限制，proposal 已聲明接受。累積 TWR 序列僅在有有效連乘段的月份產生節點（首個建倉月可能不成節點），資料不足處理見 AD-3。

### AD-2：等級判定歸新 `ProtocolService`（純運算）；邊界「達門檻即進入該級」；門檻以正回撤幅度儲存
- **背景**：需把 AD-1 的回撤映射到 L0–L3，並定案「回撤剛好等於門檻」的歸屬（BR-2）。判定為純運算、須可獨立測試（proposal 核心能力 1）。
- **選擇**：
  - 新增 `ProtocolService`（`services/protocol_service.py`，**純運算、無 I/O、無 streamlit**，建構子無依賴），負責回撤→等級的全部判定。
  - **等級與門檻語意**：門檻以**正回撤幅度百分比**表示（L1=10、L2=20、L3=30，對應 −10%／−20%／−30%），與既有 `target_weight` 的百分比慣例同軸，避免負號/0–1 混用。令 `d = −drawdown × 100`（目前回撤深度，正值百分比）。
  - **邊界慣例（定案）**：`d ≥ L3 → L3`；`elif d ≥ L2 → L2`；`elif d ≥ L1 → L1`；`else → L0`。即**回撤恰好等於門檻時歸較深一級**（達到即進入），直接落實 proposal BR-2「達門檻深度即進入該級」的「達」字語意。
- **理由**：
  - 判定純函式化，餵固定指數序列即可 pytest 驗四級與邊界（含「剛好 −20%」→ L2）。
  - 「達門檻即進入」對一份「預先承諾、對抗恐慌」的協定而言是保守且明確的一側——邊界處寧可進入較深一級提醒使用者，符合協定目的，且與 proposal 用字一致。
  - 門檻用正幅度 % 與 `TargetAllocationModel.target_weight`、`DEFAULT_REBALANCE_THRESHOLD`（百分點）同一種「正百分比」心智，UI 輸入 0–100、比較直觀。
- **否決方案**：
  - **邊界歸較淺一級（`d > 門檻` 才進入）**：與既有 `needs_rebalance = abs(drift) > threshold` 的「嚴格大於」一致，但與 proposal BR-2「達…即進入」字面衝突；協定情境下較淺側較不保守。否決，但於介面契約明記慣例，交由 Scenario 固定測試。
  - **門檻存負值（−10/−20/−30）或 0–1 小數**：與既有 % 慣例不一致、每處轉換增 off-by-sign/off-by-100 風險。否決。
  - **把判定塞進 view 或 ReturnService**：view 會變 God Object、ReturnService 會被灌入非報酬率職責。否決。
- **後果**：正面＝判定隔離可測、單位自洽、邊界無歧義；負面＝門檻在 DB／UI 以正幅度儲存，與 proposal 文字的負值表述須在 model/常數 docstring 標注等價關係（0 < L1 < L2 < L3 ⇔ 0 > −L1 > −L2 > −L3）。

### AD-3：資料不足以狀態旗標表達，顯示「資料不足」並退回 L0 姿態，絕不誤報大跌
- **背景**：歷史過短時，單月大跌會讓「起始即高點」的回撤看似深不見底，造成誤報（BR-6、成功標準「資料不足時顯示 L0 或資料不足而非崩壞」）。須定案「多少月數視為不足、如何顯示」。
- **選擇**：
  - 定 `PROTOCOL_MIN_DATA_MONTHS = 3`（常數），指**累積 TWR 序列的有效節點數**（`len(series)`，即有有效連乘段的有資料月數）。
  - `ProtocolService.assess()` 依資料量回三種 `status`：
    - `no_data`：序列為空（尚無任何有效連乘段／無紀錄）。
    - `insufficient_data`：`0 < len(series) < PROTOCOL_MIN_DATA_MONTHS`。
    - `ok`：`len(series) ≥ PROTOCOL_MIN_DATA_MONTHS`，才據回撤判 L1–L3。
  - `no_data` 與 `insufficient_data` 一律 `level_code = 'L0'`（退回平時姿態，不觸發任何大跌等級），`drawdown = None`；總覽頁以中性「資料不足」提示 + L0（平時）必做/禁止呈現，**不顯示紅色警示**。
- **理由**：
  - 回撤在 AD-1 已納入起始基準 1.0，數學上 1 個節點就能算出回撤——正是單月假警報來源；`MIN=3` 要求至少 3 個有效觀測才信任回撤，過濾「起始月＋單月暴跌」的雜訊。
  - 取 3 是保守下限：低於此無從區分「真實峰到谷回撤」與「初期少數月雜訊」；月度粒度下 3 個月已能形成基本高點—目前對照，又不至於壓抑真實的早期修正。此為**單一可調常數**，日後若使用者覺得過鬆/過緊可單點調整（列為可調參數，見文末「可調參數與待確認」）。
  - 「退回 L0 姿態」滿足「顯示 L0」且同時給「資料不足」明示，二者兼得，且平時姿態（照計畫定期定額）本就是資料不足時最安全的行為預設。
- **否決方案**：
  - **資料不足時照算並顯示 L1–L3**：直接違反 BR-6「不誤報大跌」。否決。
  - **資料不足時整頁報錯/空白**：違反「非崩壞」要求、使用者體驗差。否決。
  - **把門檻設得很高（如 12 月）**：會壓抑真實的早期修正訊號（第 5 個月的 −15% 也被吞掉），過度保守。否決，取 3 為折衷。
- **後果**：正面＝假警報被系統性擋下、行為安全；負面＝`MIN` 是工程判斷值而非需求硬性數字，須經 Scenario 固定並在使用者驗收時確認可接受。

### AD-4：門檻持久化＝新增 `protocol_thresholds` 表 + 新 Repository（比照目標配置模式），驗證歸 Service
- **背景**：門檻須可於設定頁調整、存 DB、重啟後生效；且須拒絕不合法順序（BR-3）。proposal §已知缺陷要求定案「新增設定表 vs 沿用既有機制」。
- **選擇**：
  - **新增專用表** `protocol_thresholds(level TEXT PRIMARY KEY, drawdown_threshold REAL NOT NULL)`，3 列（`'L1'/'L2'/'L3'`），`drawdown_threshold` 為正幅度百分比（AD-2）。**結構與 `target_allocations` 同構**（單鍵、單值、可配置）。
  - **新增 `ProtocolThresholdRepository`**（`repositories/protocol_threshold_repository.py`），**完全比照 `TargetRepository`**：`read_thresholds()`（SELECT 全部、依 level 排序）、`upsert_threshold(*, threshold)`（`INSERT … ON CONFLICT(level) DO UPDATE`）。純 I/O、不含業務判斷。
  - **建表**：在既有 `SchemaRepository.ensure_schema()` 追加 `CREATE TABLE IF NOT EXISTS protocol_thresholds …`（idempotent，與既有三表同一交易入口，兼作 AD-1(t16) 連線存活探測，無需另建入口）。
  - **預設值來源**：`constants.PROTOCOL_LEVEL_DEFAULTS`（L1=10.0、L2=20.0、L3=30.0）。表為空（使用者尚未設定）時，`ProtocolService.effective_thresholds()` 以預設補齊——app 首次啟動即可用，使用者存過一次後「重啟後生效」成立。
  - **合法性驗證歸 Service**（非 Repository）：`ProtocolService.validate_thresholds(l1, l2, l3)` 檢查 `0 < l1 < l2 < l3`（皆正、回撤深度嚴格遞增；等價 proposal 的 0 > −l1 > −l2 > −l3），違反拋 `DataValidationError`；設定頁在寫入前呼叫，失敗即 `st.error` 拒絕、不落 DB。此比照 initial-build AD-9「唯一鍵/合法性驗證屬業務判斷歸 Service，Repository 只執行 SQL」。
- **理由**：
  - 沿用已驗證的 `target_allocations` 樣式，**接線路徑（表→Repo→Container→設定頁）與既有一模一樣**，最小新增、最低風險、最易被 rules-reviewer 通過。
  - 專用表（3 個具名列）比「通用 KV `app_settings` 表」精確且零過度工程——initial-build 未建通用設定表，本 Change 不為 3 個數字引入通用機制（避免過早一般化）。
  - 驗證放 Service 保持 Repository 純 I/O、判定可單元測試（餵非法順序驗拒絕）。
- **否決方案**：
  - **通用 `app_settings(key,value)` KV 表**：為 3 個門檻引入泛用抽象，過度工程、型別鬆散（value 需字串轉型）。否決。
  - **門檻寫 constants 硬編、不進 DB**：違反「可於設定頁調整並持久化」（BR-3、目標）。constants 只作**預設**，可調值進 DB。
  - **把門檻塞進 `target_allocations` 或既有表**：語意不同（門檻非分類配置），混表污染。否決。
  - **驗證寫在 Repository**：違反分層（Repository 不含業務判斷）。否決。
- **後果**：正面＝與既有設定機制同構、可持久化、驗證可測；負面＝多一張表與一個 Repo（但皆薄且同構）。門檻**不納入既有 CSV 匯出入**（proposal §本次做未列，避免擴大 CSV 對外契約）——列為已知限制。

### AD-5：新增「總覽」落地頁與「行為協定」唯讀頁；協定文件經 `ProtocolDocRepository` 讀取；必做/禁止以 constants 結構化編碼
- **背景**：需新增登入後落地的總覽頁與唯讀渲染 `docs/PROTOCOL.md` 的協定頁，並把各級「必做/禁止」摘要在 app 內結構化（BR-5/BR-7、目標）。
- **選擇**：
  - **總覽落地頁** `views/overview.py`：在 `app.py` 的 `st.navigation` 清單中作為**第一個 `st.Page` 並設 `default=True`**，成為登入後預設落地頁（取代目前落地的「月度錄入」）。職責＝取 container → 讀全歷史區間 → 取累積 TWR 序列（`return_service.cumulative_twr_series`）→ 取有效門檻（`protocol_service.effective_thresholds(stored=protocol_threshold_repo.read_thresholds())`）→ `protocol_service.assess(...)` 得 `ProtocolStatus` → 依 `level_code` 自 `constants.PROTOCOL_LEVELS` 取該級規格 → 渲染燈號/等級/回撤帶 + 必做/禁止清單 + 關鍵指標（累積 TWR、淨值、目前回撤%）。為唯一 catch 點（`try/except AssetLabError → st.error`，AD-8）。
  - **行為協定唯讀頁** `views/protocol.py`：`container.protocol_doc_repo.read_protocol_markdown()` 取全文 → `st.markdown(text)` 唯讀渲染。為唯一 catch 點（檔案缺失 → 友善 `st.error`，不噴 traceback）。
  - **協定文件讀取歸 Repository**：新增 `ProtocolDocRepository`（`repositories/protocol_doc_repository.py`），建構子注入 `doc_path: Path`，`read_protocol_markdown() -> str` 讀檔回字串；檔案不存在時拋 `AssetLabError` 子類（見介面契約，交 Page catch）。**檔案讀寫屬 I/O 歸 Repository**（02-architecture §6），使 view 不直接碰檔案、且「檔案缺失」路徑可注入暫存檔測試。路徑於 `bootstrap` 以 `Path(__file__).resolve().parents[2] / constants.PROTOCOL_DOC_RELATIVE_PATH` 解析（`bootstrap.py` 在 `src/asset_lab/`，`parents[2]` 即 repo 根；Streamlit Cloud 一併部署 repo，相對結構成立），注入後由 Repository 惰性讀取。
  - **必做/禁止結構化編碼**：於 `constants.py` 定義**不可變參照內容** `PROTOCOL_LEVELS`（`ProtocolLevelSpec` frozen dataclass 之 tuple，L0–L3，各含 `code`/`label`/`band_text`/`must_do`/`must_not`），內容依 PROTOCOL.md §1 表謄寫（L0＝平時：照計畫定期定額、無特別禁止，可含 §3 行為防火牆通則，BR-7）。屬「所有環境相同的業務規格、非機密」，依 03-data-config 決策表歸 constants。
- **理由**：
  - `st.navigation` 首個 `st.Page`（並顯式 `default=True`）即落地頁，是既有多頁機制的原生用法，無新框架。
  - 唯讀渲染以 `st.markdown` 一行完成，無新依賴（見 TD-1）。
  - 必做/禁止是靜態業務文字，放 constants（結構化、可被 view 直接查表、可被測試斷言），滿足 BR-5「app 內以結構資料編碼」；PROTOCOL.md 仍為完整唯讀全文，兩處**人工對齊**為 BR-5 已知維護點，明列於技術債。
  - 文件讀取走 Repository 維持分層與可測性（檔案缺失分支可測）。
- **否決方案**：
  - **view 直接 `open()` 讀 `docs/PROTOCOL.md`**：I/O 落在 view、耦合 CWD、缺失分支難測。否決，改走 Repository。
  - **用固定相對路徑 `"docs/PROTOCOL.md"` 依賴 CWD**：本機以 `streamlit run app.py` 時 CWD＝repo 根尚可，但脆弱；改以 `__file__` 錨定 repo 根更穩。否決固定相對路徑。
  - **必做/禁止硬寫在 view 的 markdown 字串**：無結構、無法查表/測試、違反 BR-5「結構資料編碼」。否決。
  - **從 PROTOCOL.md 解析出必做/禁止表**：需寫 markdown 表格 parser，脆弱且過度工程；proposal BR-5 已接受「兩處人工對齊」。否決解析，採 constants 謄寫。
- **後果**：正面＝落地頁/唯讀頁皆用既有原生機制、必做/禁止可查表可測、文件讀取可測；負面＝`PROTOCOL_LEVELS` 與 `docs/PROTOCOL.md` §1 須人工同步（BR-5 已知維護點）；落地頁由「月度錄入」改為「總覽」，既有使用者登入後首見畫面改變（屬預期需求）。

### AD-6：關鍵指標與呈現只消費既有 `ReturnService` / `AllocationService`，不改報酬率/配置引擎
- **背景**：總覽需顯示累積 TWR、淨值、回撤%（proposal 目標、BR-3）；proposal §本次不做明訂「不改動既有報酬率引擎核心，只消費其輸出」。
- **選擇**：
  - 累積 TWR：取 `cumulative_twr_series()` 最後一點的 `cumulative_twr`（經 `ProtocolStatus.current_cumulative_twr` 帶出）。
  - 淨值：取 `AllocationService.net_worth_series()` 最後一點的 `net_worth`。
  - 目前回撤%：`ProtocolStatus.drawdown`（AD-1）。
  - 三者皆由總覽頁在既有 Service 之上組裝呈現，**不新增/不修改** `ReturnService`、`AllocationService`、`PeriodService` 的任何方法或口徑。全歷史區間以既有樣式取得：`record_repo.read_range(start_ym=EARLIEST_YEAR_MONTH_SENTINEL, end_ym=latest_ym)`（與 returns 頁一致）。
- **理由**：嚴守 proposal 邊界（不動核心引擎），復用已測邏輯，降低回歸風險（成功標準「既有行為不回歸」）。
- **否決方案**：為總覽另寫一套淨值/報酬彙總 → 與既有引擎口徑分歧、重工、增回歸風險。否決。
- **後果**：正面＝零核心改動、口徑與既有頁一致；負面＝總覽對既有 Service 輸出形狀有耦合（其變更會波及總覽），屬合理耦合。

---

## 技術選型

> 本 Change 無新技術棧（1-2a 已跳過）。沿用 initial-build 的 `streamlit>=1.42`、`libsql`、`pyxirr`、`plotly`、`pandas`，**不新增第三方依賴**。

### TD-1：協定唯讀渲染 — `st.markdown`（標準庫 `pathlib` 讀檔）
- **推薦**：`st.markdown(text)` 直接渲染 `docs/PROTOCOL.md` 全文；檔案以標準庫 `pathlib.Path.read_text(encoding="utf-8")` 讀取（信心度：High）。
- **理由**：Streamlit 原生支援 markdown 渲染，零新依賴；`docs/PROTOCOL.md` 為 repo 內檔案、隨 repo 部署，本機與 Community Cloud 皆以 `__file__` 錨定的 repo 相對路徑存取（AD-5）。UTF-8 明確指定以避免跨平台預設編碼差異（含中文）。

---

## 介面契約

> 各層 public 介面骨架（簽名 + 職責）。所有注入一律 keyword args；Service 不 import streamlit/libsql；Repository 不含業務判斷。行為細節（邊界值、錯誤路徑）由 1-3 Scenarios 以 BR 編號定義，此處不重述。**既有元件僅列「新增/變更點」。**

### Models

新增 `src/asset_lab/models/protocol.py`（純資料 / 參照內容）：

```python
from pydantic import BaseModel

class ProtocolThresholdModel(BaseModel):
    """單一等級的回撤門檻設定（持久化列，AD-4）。"""
    level: str                 # 'L1' | 'L2' | 'L3'
    drawdown_threshold: float  # 正回撤幅度百分比，如 10.0 表 −10%（AD-2）

class ProtocolThresholds(BaseModel):
    """合併預設後的有效門檻（供 assess 使用，AD-2/AD-4）。皆為正幅度 %。"""
    l1: float
    l2: float
    l3: float
```

新增於 `src/asset_lab/models/results.py`（計算輸出，與既有 Result models 並列）：

```python
class ProtocolStatus(BaseModel):
    """協定等級判定結果（回撤 → 等級，AD-1/AD-2/AD-3）。"""
    level_code: str                        # 'L0' | 'L1' | 'L2' | 'L3'
    status: str                            # 'ok' | 'insufficient_data' | 'no_data'
    drawdown: float | None                 # 目前自歷史高點回撤（≤0 小數，如 -0.22）；資料不足時 None
    current_cumulative_twr: float | None   # 最新有資料月的整體累積 TWR（小數）；無節點時 None
    data_month_count: int                  # 納入判定的累積 TWR 有效節點數（AD-3）
```

`ProtocolLevelSpec`（不可變參照內容）定義於 `constants.py`（見下）——以 frozen dataclass 而非 pydantic，因其為**常數定義**非流經各層的驗證資料。

### constants.py（新增業務常數，非機密、進版控）

```python
from dataclasses import dataclass

# 回撤基準的資料不足下限：累積 TWR 有效節點數低於此值即不判 L1–L3（AD-3，可調）。
PROTOCOL_MIN_DATA_MONTHS = 3
# docs/PROTOCOL.md 相對 repo 根的路徑（AD-5，唯讀渲染來源）。
PROTOCOL_DOC_RELATIVE_PATH = "docs/PROTOCOL.md"

class PROTOCOL_LEVEL_CODE:
    """協定等級代碼。"""
    L0 = "L0"; L1 = "L1"; L2 = "L2"; L3 = "L3"
    ALL = (L0, L1, L2, L3)

class PROTOCOL_LEVEL_DEFAULTS:
    """回撤門檻預設值（正幅度 %，AD-4）；表為空時由 Service 以此補齊。"""
    L1 = 10.0; L2 = 20.0; L3 = 30.0

class PROTOCOL_THRESHOLDS_TABLE:
    """回撤門檻設定表結構（AD-4）。level 為主鍵。"""
    TABLE_NAME = "protocol_thresholds"
    LEVEL = "level"
    DRAWDOWN_THRESHOLD = "drawdown_threshold"

@dataclass(frozen=True)
class ProtocolLevelSpec:
    """單一等級的展示規格（必做/禁止結構化編碼，BR-5/BR-7）。
    內容依 docs/PROTOCOL.md §1 表人工謄寫；兩處須人工對齊（已知維護點）。"""
    code: str                    # 'L0'..'L3'
    label: str                   # '平時'/'修正'/'熊市'/'深熊'
    band_text: str               # 回撤帶描述，如 '−10% ~ −20%'
    must_do: tuple[str, ...]
    must_not: tuple[str, ...]

# L0（平時）+ L1–L3 依 PROTOCOL.md §1；內容謄寫，供總覽頁查表。
PROTOCOL_LEVELS: tuple[ProtocolLevelSpec, ...] = ( ... )
```

### Repositories（只做 I/O）

新增 `src/asset_lab/repositories/protocol_threshold_repository.py`（比照 `TargetRepository`）：

```python
class ProtocolThresholdRepository:
    """回撤門檻 I/O。level 為主鍵。連線由 bootstrap 注入。"""
    def __init__(self, *, conn) -> None: ...
    def read_thresholds(self) -> list[ProtocolThresholdModel]: ...          # SELECT 全部，依 level 排序
    def upsert_threshold(self, *, threshold: ProtocolThresholdModel) -> None: ...  # INSERT … ON CONFLICT(level) DO UPDATE
```

新增 `src/asset_lab/repositories/protocol_doc_repository.py`：

```python
from pathlib import Path

class ProtocolDocRepository:
    """協定文件（docs/PROTOCOL.md）唯讀 I/O。路徑由 bootstrap 注入。"""
    def __init__(self, *, doc_path: Path) -> None: ...
    def read_protocol_markdown(self) -> str: ...   # 以 UTF-8 讀全文；檔案不存在時拋 AssetLabError 子類（交 Page catch → st.error）
```

變更 `SchemaRepository.ensure_schema()`：追加建立 `protocol_thresholds` 表（`CREATE TABLE IF NOT EXISTS`，idempotent）。**既有三表 DDL 不變。**

### Services（純運算，無 I/O、無 streamlit）

新增 `src/asset_lab/services/protocol_service.py`：

```python
class ProtocolService:
    """協定等級判定與門檻運算（AD-1/AD-2/AD-3/AD-4）。純運算，建構子無依賴。"""
    def __init__(self) -> None: ...

    def effective_thresholds(
        self, *, stored: list[ProtocolThresholdModel]
    ) -> ProtocolThresholds: ...
        # 以 stored 覆蓋 constants.PROTOCOL_LEVEL_DEFAULTS；缺哪級用預設補（AD-4）

    def validate_thresholds(self, *, l1: float, l2: float, l3: float) -> None: ...
        # 檢查 0 < l1 < l2 < l3（皆正、深度嚴格遞增）；違反拋 DataValidationError（AD-4；BR-3）

    def assess(
        self, *, series: list[CumulativeTwrPoint], thresholds: ProtocolThresholds,
        min_data_months: int,
    ) -> ProtocolStatus: ...
        # 消費累積 TWR 序列（AD-1，只讀不改 ReturnService）：
        #   指數路徑 = [1.0] + [1 + p.cumulative_twr for p in series]
        #   peak = max(指數路徑)；current = 指數路徑[-1]；drawdown = current/peak − 1
        #   資料量 len(series)：0 → no_data；< min → insufficient_data；皆退 L0、drawdown=None（AD-3）
        #   否則 d = −drawdown×100；d≥l3→L3 / d≥l2→L2 / d≥l1→L1 / else L0（AD-2 邊界：達即進入）
```

**既有 Service（`ReturnService` / `AllocationService` / `PeriodService` / …）：無介面變更**，總覽頁僅消費其既有輸出（AD-6）。

### 入口與組裝

`src/asset_lab/bootstrap.py`（變更 `build_container` + 新增協定文件路徑常量）：

```python
# 於模組層解析協定文件路徑（bootstrap 在 src/asset_lab/，parents[2] 即 repo 根，AD-5）
_PROTOCOL_DOC_PATH = Path(__file__).resolve().parents[2] / PROTOCOL_DOC_RELATIVE_PATH

@dataclass(frozen=True)
class Container:
    # …既有欄位不動…
    protocol_threshold_repo: ProtocolThresholdRepository   # 新增
    protocol_doc_repo: ProtocolDocRepository               # 新增
    protocol_service: ProtocolService                      # 新增

def build_container(*, conn) -> Container:
    # …既有組裝不動…以 keyword args 新增：
    #   ProtocolThresholdRepository(conn=conn)
    #   ProtocolDocRepository(doc_path=_PROTOCOL_DOC_PATH)
    #   ProtocolService()   # 純運算，無依賴
```

`app.py`（變更 `st.navigation` 清單；**守門/組裝/pyarrow 規避等既有邏輯不動**）：

```python
navigation = st.navigation([
    st.Page("views/overview.py", title="總覽",   icon=":material/dashboard:", default=True),  # 新增，登入落地頁
    st.Page("views/input.py",      title="月度錄入", icon=":material/edit_note:"),
    st.Page("views/allocation.py", title="資產配置", icon=":material/donut_large:"),
    st.Page("views/returns.py",    title="報酬率",   icon=":material/trending_up:"),
    st.Page("views/protocol.py",   title="行為協定", icon=":material/menu_book:"),           # 新增，唯讀渲染
    st.Page("views/settings.py",   title="設定",     icon=":material/settings:"),
    st.Page("views/data_io.py",    title="匯出入",   icon=":material/import_export:"),
])
```

### Views（View + 流程決策；唯一 catch 點）

- **新增 `views/overview.py`**：登入落地頁（AD-5/AD-6）。取 container → `record_repo.latest_year_month()`：若為 `None`（尚無紀錄）直接以 `no_data` 姿態渲染（不呼叫 `read_range`，避免以 null 訖月查詢）；否則 `read_range(EARLIEST_YEAR_MONTH_SENTINEL, latest_ym)` 取全歷史 + holdings → `cumulative_twr_series` → `effective_thresholds`(讀門檻) → `assess` → 依 `level_code` 查 `PROTOCOL_LEVELS` → 渲染燈號/等級/回撤帶 + 必做/禁止 + 指標（累積 TWR / 淨值 / 回撤%）；`status` 為 `no_data`/`insufficient_data` 時顯示中性「資料不足」提示 + L0 姿態。`try/except AssetLabError → logger.exception + st.error`。尾端 `render()`。
- **新增 `views/protocol.py`**：唯讀渲染協定全文。`container.protocol_doc_repo.read_protocol_markdown()` → `st.markdown(...)`；`try/except AssetLabError → st.error`（檔案缺失友善提示）。尾端 `render()`。
- **變更 `views/settings.py`**：新增 `_render_protocol_thresholds(*, protocol_threshold_repo, protocol_service)` 區段——以 `effective_thresholds` 帶出目前 L1/L2/L3 為 `st.number_input`（0–100 正幅度）預設，儲存時先 `validate_thresholds`（失敗 → `st.error` 拒絕、不落 DB；BR-3），通過則對三級各 `upsert_threshold`。比照既有 `_render_targets` 樣式，納入既有 `try/except AssetLabError`。

### exceptions.py（新增，供文件缺失走 Page catch）

```python
class ProtocolDocError(AssetLabError):
    """協定文件讀取失敗（如 docs/PROTOCOL.md 缺失）時拋出，交 Page 層反饋。"""
```

---

## 已知技術債與限制

- **必做/禁止兩處人工對齊**（BR-5）：`constants.PROTOCOL_LEVELS` 與 `docs/PROTOCOL.md` §1 表須人工同步；改協定文本時須一併更新常數。已於 `ProtocolLevelSpec` docstring 標注，為 proposal 明列的已知維護點。
- **回撤為月度粒度 proxy**（BR-4）：等級隨每月錄入更新、非即時；且以自身投組 TWR 代理「大盤回撤」，非真實市場指數——proposal 刻意取捨（無行情 API）。
- **`PROTOCOL_MIN_DATA_MONTHS = 3` 為工程判斷值**（AD-3）：非需求硬性數字，屬「不誤報大跌」的保守下限，單一常數可調；建議使用者驗收時確認。
- **門檻不納入 CSV 匯出入**（AD-4）：proposal §本次做未涵蓋，為避免擴大 CSV 對外契約而不納入；門檻遺失時 Service 以預設補齊，不致崩壞。若日後要求門檻可隨資料庫遷移，再評估納入 CSV。
- **總覽對既有 Service 輸出形狀耦合**（AD-6）：`cumulative_twr_series` / `net_worth_series` 的輸出結構若變更會波及總覽——屬合理的消費端耦合，非缺陷。
- **協定文件路徑以 `__file__` 錨定 repo 根**（AD-5）：假設 `src/` layout 與 `docs/` 相對結構隨 repo 一併部署（Community Cloud 成立）；若未來改打包方式（如把 `docs/` 排除於部署），此路徑假設需重檢。

---

## 待確認 / 可調參數

> 皆有設計預設可直接進 Scenario；標示者建議使用者驗收時確認。

| 項目 | 設計定案（預設） | 性質 |
|------|------------------|------|
| 回撤基準 | 累積 TWR 指數回撤（AD-1） | **已定案**（含理由） |
| 邊界歸屬 | 達門檻即進入較深級（`d ≥ 門檻`，AD-2） | **已定案** |
| 資料不足門檻 | 累積 TWR 有效節點 < 3 → 顯示「資料不足」+ L0（AD-3） | 已定案，`3` 為可調常數，**建議確認** |
| 門檻儲存 | 新增 `protocol_thresholds` 表 + 專用 Repo（AD-4） | **已定案** |
| 落地頁 | 「總覽」設 `default=True` 取代「月度錄入」（AD-5） | 已定案，若使用者仍想以錄入頁落地可調 nav |

---

## 決策總覽

| ID | 類型 | 決策 | 信心度 |
|----|------|------|--------|
| AD-1 | 架構 | 回撤基準採「累積 TWR 指數回撤」（消費既有 `cumulative_twr_series`，含起始基準 1.0 為高點路徑起點），否決淨值序列回撤 | High |
| AD-2 | 架構 | 等級判定歸新純運算 `ProtocolService`；邊界「達門檻即進入較深級」；門檻以正幅度 % 儲存 | High |
| AD-3 | 架構 | 資料不足（有效節點 < `PROTOCOL_MIN_DATA_MONTHS=3`）以狀態旗標表達、顯示「資料不足」並退回 L0，不誤報大跌 | Medium |
| AD-4 | 架構 | 門檻持久化＝新增 `protocol_thresholds` 表 + 新 Repo（比照 `target_allocations`）；合法性驗證歸 Service | High |
| AD-5 | 架構 | 新增總覽落地頁（`default=True`）與行為協定唯讀頁；文件經 `ProtocolDocRepository` 讀取；必做/禁止以 constants `PROTOCOL_LEVELS` 結構化編碼 | High |
| AD-6 | 架構 | 關鍵指標與呈現只消費既有 `ReturnService`/`AllocationService`，不改報酬率/配置引擎 | High |
| TD-1 | 技術 | 協定唯讀渲染用 `st.markdown` + `pathlib` 讀檔，無新依賴 | High |
