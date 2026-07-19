# Review: behavior-protocol

## 3-1 程式碼清理

掃描範圍：19 個檔案，c10716a..9f84425（t01–t05 全部新增/修改檔）

> 註：`git branch --show-current` 為 `main` 且與 `origin/main` 目前同點（tip 為
> `dc15a3d` 月度錄入下拉選單，屬另一個已合併的無關 Change），故未採用預設
> `--diff-base origin/main`（會得到空 diff）。改以本 Change 實際程式碼起訖點
> `c10716a`（1-1 提案確認前一個 commit）到 `9f84425`（t05 最後一次 fix）界定範圍，
> 對應 dispatch 指定的 t01–t05 檔案清單。額外發現 `tests/test_bootstrap.py` 亦在此
> 範圍內被本 Change 觸碰（+5 行，t02 為 Container 新欄位補 wiring 斷言），一併納入
> 掃描，不算範圍蔓延。

### 自動掃描

Checker 命令：`python .claude/skills/spec-driven-flow/scripts/checkers/runner.py --phase 3-1 --project-dir . --diff-base c10716a --json --output .ai/changes/behavior-protocol/.cache/checker_3_1.json`
退出碼：0
總違規：3 條（MEDIUM ×3，CRITICAL/HIGH/LOW 皆 0）
Baseline 命中：0 條（全數為本 Change 新增）
完整報告：`.ai/changes/behavior-protocol/.cache/checker_3_1.json`

Checker 掃描範圍含 `tests/test_bootstrap.py`、`tests/test_core_utils.py`、
`tests/test_input_view.py`、`views/input.py`、`src/asset_lab/core/utils.py`
（後四者屬 `dc15a3d` 無關 Change，checker 以 `--diff-base c10716a` 對到 HEAD 一併掃
入）；本報告只逐條復核落在 behavior-protocol 實際範圍（t01–t05 + test_bootstrap.py）
內的 3 條，其餘不屬本 Change 不予處理。

逐條復核：

1. `function_too_large` @ `src/asset_lab/services/protocol_service.py:82`（`assess`，51 行超過 50 行上限）——**判定：不建議拆分**。實際為 16 行 docstring（含 Args/Returns）+ 3 段 guard-clause early return + 1 段委派 `_current_drawdown`/`_level_for` 的線性流程，圈複雜度低、無深層巢狀；已將兩段非平凡運算（回撤計算、等級對應）抽成 `@staticmethod`。純以物理行數觸發，強拆會把三段 early-return 打散成更難讀的片段，屬過度切分風險。建議保留現狀，不加 `# checker:noqa`（物理行數規則非誤判，但此為可接受的例外，留原樣即可、未來若邏輯再增長才需真正拆分）。
2. `duplicate_code` @ `src/asset_lab/bootstrap.py:34` vs `tests/test_bootstrap.py:35`（import 區塊 6+ 行重複）——**判定：false positive，checker 已標**。經比對兩檔 import 區塊，重複純屬「模組本身的依賴 import」與「測試檔案為 isinstance 斷言需要而重複同一批 import」的結構性重疊——這在改動前就已存在於 `holding_repo`/`record_repo`/`schema_repo`/`target_repo`/`allocation_service` 等既有 import 上（可見 `git diff` 只新增了 `ProtocolThresholdRepository`、`ProtocolService` 兩行，延伸既有重疊模式，非本 Change 新創），不是可抽取的邏輯重複。不建議加 `# checker:noqa`（此為 checker 對「模組↔測試檔」這類配對的通用限制，非本檔案特有的刻意例外，逐一豁免不划算）。

### 人工掃描（逐檔語意）

- 未使用 import／變數／函式：`uv run ruff check .` 全數通過（All checks passed，含 F401/F841 等未使用檢查）；逐檔人工複核 constants.py、exceptions.py、models/protocol.py、models/results.py、protocol_service.py、兩個新 Repository、overview_presentation.py、bootstrap.py、三個 views 檔案的 import 與內部函式，未發現額外死碼。`vulture` 本專案未安裝依賴（`pyproject.toml` 無此套件），略過。
- Debug／TDD 殘留：全範圍 grep `TODO|FIXME|XXX|print\(|pdb\.|breakpoint\(` 無命中。
- Change 級編號註解（dead reference 風險）：見下方 SAFE 項。`docs/PROTOCOL.md` §SC-XXX 引用（`pytest.mark.scenario("SC-XXX")` 及 test docstring 內的 `SC-04X` 字樣）**不算此類**——這是本專案既有、跨 Change 持續存在的追蹤慣例（`tests/test_allocation.py` 等 initial-build 既有測試同樣大量使用，`.ai/scenarios/SC-*.md` 卡片本身也不隨 Change 歸檔而刪除），維持現狀。
- 重複程式碼（DRY）：`_container()` 在 `views/overview.py`、`views/protocol.py` 与既有 `views/input.py`／`data_io.py`／`allocation.py`／`returns.py`／`settings.py` 完全同構重複——此為 initial-build 既有的跨檔案慣例（每個 view 檔自成一體，故意不共用 helper），非本 Change 新增的重複，不予處理。`conn` fixture（`tests/test_protocol_thresholds.py`）與 `tests/test_holding_master.py`／`test_monthly_input.py` 同構，同理不予處理。
- 命名一致性：`PROTOCOL_LEVEL_CODE`／`PROTOCOL_LEVEL_DEFAULTS`／`PROTOCOL_THRESHOLDS_TABLE` 採 SCREAMING_SNAKE_CASE 類別名，比照既有 `HOLDING_KIND`／`PERIOD_MODE`／`ASSET_CATEGORIES`／`TARGET_ALLOCATIONS_TABLE` 慣例；`ProtocolLevelSpec` 為 `@dataclass(frozen=True)` 值物件，PascalCase 符合一般類別命名，是本檔案首次出現「非純常數命名空間」的資料類別，但用途（結構化必做/禁止規格）與命名皆自我解釋、docstring 已說明維護點，判定為合理新增，非不一致。
- 過大函數／深層巢狀：`views/overview.py` 的 `render()`／`_render()` 約 20–30 行、巢狀 ≤2 層；`views/settings.py` 的 `_render_protocol_thresholds()` 與既有 `_render_targets()` 同構、無異常巢狀。唯一 checker 標出的 `assess()` 已於自動掃描段落復核（判定不拆分）。

### SAFE

- `views/overview.py:12` — 模組 docstring 內「（AD-6：只消費既有 ReturnService/AllocationService 輸出）」為 Change 級 ADR 編號（`design.md` 的 AD-6）直接嵌入原始碼註解；歸檔後讀者手邊不會有 design.md 對照，`AD-6` 會變成無法解析的死引用。建議改寫為不帶編號、只留「為什麼」的說法，例如：「本頁只做委派、資料組裝與渲染，不算任何業務值（只消費既有 ReturnService/AllocationService 既有輸出，不改動報酬率/配置引擎邏輯）。」（checker 未報出——語意層發現，非 ruff/vulture 可偵測範圍）
  - 附註：`src/asset_lab/core/constants.py:4`「不在此定義（見設計 AD-7）」同樣是 AD 編號殘留，但該行不在本 Change 的 diff 範圍內（`git diff c10716a..9f84425` 該行無變更，屬 initial-build 既有殘留），依範圍蔓延防範原則不在本次處理，僅此附註供之後留意。
  - **狀態：已修正**。主 AI 確認採納後，已將該行改寫為「與渲染，不算任何業務值（只消費既有 ReturnService/AllocationService 既有輸出，不改動報酬率/配置引擎邏輯）。」；改寫後單行超過 100 字元觸發 `ruff` E501，已依既有段落換行風格拆成兩行收斂。`uv run ruff check .`／`uv run pytest tests/ -q`（282 全綠）皆確認通過，無回歸。

### CAREFUL

（無）

### RISKY

（無）

### SUGGEST

- `tests/test_protocol.py` 與 `tests/test_protocol_thresholds.py` 各自定義了實質相同的 `_series(cumulative_twrs: list[float]) -> list[CumulativeTwrPoint]` 私有 helper（僅 docstring 詳略不同，函式本體逐行相同）。因程式碼本體僅 4 行、低於 checker 的 6 行重複門檻，未被自動掃描標出（checker 未報出——語意層發現）。是否值得抽到共用 fixture／helper 屬判斷題：本專案既有慣例（`test_allocation.py` 的 `_asset`/`_record`/`_approx` 等）是每個測試檔自成一體、刻意不共用，此重複與該慣例一致；且僅兩處、每處僅 4 行，尚未達到「Rule of Three」的抽取門檻。建議維持現狀，僅在未來第三個測試檔需要相同 helper 時才考慮抽出共用模組。
  - **狀態：主 AI 確認維持現狀**，本輪不處理。

## 3-2 安全性審查

審查範圍：8 個檔案（dispatch 指定 t01–t05 新增/修改）——
`repositories/protocol_threshold_repository.py`、`repositories/protocol_doc_repository.py`、
`services/protocol_service.py`、`bootstrap.py`、`app.py`、`views/overview.py`、
`views/protocol.py`、`views/settings.py`；連帶查證支撐檔（`core/access.py`、
`core/exceptions.py`、`core/constants.py`、`models/protocol.py`、`schema_repository.py`、
`overview_presentation.py`、`.gitignore`、`.streamlit/secrets.toml.example`）。

核准判定：**通過**（附 3 項 LOW／資訊級非阻擋建議）
- 無真實 CRITICAL／HIGH／MEDIUM 漏洞；checker 報出的 3 條 CRITICAL 逐條復核皆為 false positive（見下）。
- `pip-audit`：No known vulnerabilities found（A06 無已知 CVE）。
- 觸發理由三點（新增持久化表＋設定頁寫入／落地頁改總覽／固定路徑讀檔）逐一查證，未發現繞過既有 fail-closed 守門或新增可利用攻擊面。

### 自動掃描

Checker 命令：`python .claude/skills/spec-driven-flow/scripts/checkers/runner.py --phase 3-2 --project-dir . --diff-base c10716a --json --output .ai/changes/behavior-protocol/.cache/checker_3_2.json`
退出碼：0
總違規：3 條（CRITICAL: 3 / HIGH: 0 / MEDIUM: 0 / LOW: 0）
Baseline 命中：0 條
完整報告：`.ai/changes/behavior-protocol/.cache/checker_3_2.json`

> diff-base 說明：沿用 3-1 的判定——`origin/main`（`dc15a3d`，「月度錄入下拉」無關 Change）
> 為 HEAD（`b6bd1d4`）的祖先且僅差 1 個 commit（3-1 清理 fix），若用預設 `--diff-base origin/main`
> 只會掃到該單一 commit、掃不到本 Change 主體，故改以本 Change 起點前一 commit `c10716a`
> 界定完整 t01–t05 範圍。checker 因此連帶掃入不屬本 Change 的 `dc15a3d` 檔案
> （`views/input.py`、`core/utils.py`、`tests/test_input_view.py`、`tests/test_core_utils.py`），
> 該批不在本次安全審查範圍、亦未產生任何違規，不予處理。

**3 條 CRITICAL 逐條復核（結論：全數 false positive）**

三條 `sql_injection_risk` 皆命中「SQL 以 f-string 動態插值拼接」的機械式啟發規則，
但插值 token 全部是**模組層字串常數**（來自 `PROTOCOL_THRESHOLDS_TABLE` 的
`TABLE_NAME="protocol_thresholds"` / `LEVEL="level"` / `DRAWDOWN_THRESHOLD="drawdown_threshold"`），
**無任何使用者輸入流入**；真正的資料值一律走 `?` placeholder 綁定。SQL 標準下
資料表/欄位「識別子」本就無法參數化（placeholder 僅適用於值），以常數插值識別子是
不可避免且安全的標準寫法，與既有 `target_allocations`/`holdings`/`monthly_records`
四表 DDL 及 `TargetRepository` 完全同構。

1. [CRITICAL→false positive] A03 — `protocol_threshold_repository.py:23` — `_SELECT_ALL`
   `f"SELECT {_LEVEL}, {_DRAWDOWN_THRESHOLD} FROM {_TABLE} ORDER BY {_LEVEL}"`。三個插值全為常數識別子，無值插入、無使用者輸入。**不構成注入。** Checker 對應：`sql_injection_risk`（checker 已標 CRITICAL）。
2. [CRITICAL→false positive] A03 — `protocol_threshold_repository.py:25` — `_UPSERT`
   `INSERT INTO {_TABLE} (...) VALUES (?, ?) ON CONFLICT(...)`。識別子為常數插值；實際寫入值 `threshold.level`、`threshold.drawdown_threshold` 於 `cursor.execute(_UPSERT, (...))` 以 `?` 綁定（第 56 行），已參數化。且 `level` 值來自 `settings.py` 硬編的 `PROTOCOL_LEVEL_CODE.L1/L2/L3` 常數迴圈、`drawdown_threshold` 來自 `st.number_input` 的 float，非自由字串。**不構成注入。** Checker 對應：`sql_injection_risk`（checker 已標 CRITICAL）。
3. [CRITICAL→false positive] A03 — `schema_repository.py:62` — `_CREATE_PROTOCOL_THRESHOLDS`
   `CREATE TABLE IF NOT EXISTS {TABLE_NAME} ({LEVEL} TEXT PRIMARY KEY, {DRAWDOWN_THRESHOLD} REAL NOT NULL)`。DDL 全由常數插值，無使用者輸入，DDL 亦無法用 placeholder 綁識別子。**不構成注入。** Checker 對應：`sql_injection_risk`（checker 已標 CRITICAL）。

### 發現

- [LOW] A03（縱深防禦，checker 未報出）— `repositories/protocol_doc_repository.py` — `read_protocol_markdown`
  問題：目前 `doc_path` 由 `bootstrap.py` 以 `Path(__file__).resolve().parents[2] / PROTOCOL_DOC_RELATIVE_PATH`（常數 `"docs/PROTOCOL.md"`）錨定注入，讀取方法**不吃任何參數**，故當前**無路徑遍歷風險**（觸發理由三之查證結論：安全）。惟 Repository 對「注入進來的 `doc_path` 是否落在預期目錄內」不做任何錨定校驗——若未來有人把檔名或子路徑改為可由使用者/外部設定控制（例如「選擇要顯示哪份文件」），現行實作會直接 `read_text` 任意路徑，缺乏容器邊界防護。
  修復（建議，非阻擋）：維持現狀即可（無現行風險）；若日後參數化來源，於 Repository 內加一道 `resolved.is_relative_to(base_dir)` 之類的錨定校驗，或以白名單限定可讀檔名，避免 `../` 逃逸。
  影響：目前無（路徑寫死）；僅為未來演進時的縱深防禦提醒。
  **狀態：主 AI 裁定不處理、維持現狀**（第二段）——目前無現行風險，僅為未來參數化時的縱深防禦提醒，屆時再評估。

- [LOW] A09（資訊揭露，checker 未報出）— `repositories/protocol_doc_repository.py:32` + `views/protocol.py:36`
  問題：`ProtocolDocError(f"無法讀取行為協定文件：{self._doc_path}")` 將**伺服器絕對路徑**帶入例外訊息，`views/protocol.py` 再以 `st.error(str(error))` 顯示給前端，洩漏部署目錄結構。
  修復（建議，非阻擋）：例外訊息對使用者可只給「無法讀取行為協定文件，請確認部署包含 docs/PROTOCOL.md」，絕對路徑僅留在 `logger.exception`（伺服器端）。
  影響：極低——僅在讀檔失敗時觸發，且畫面只對「已通過守門的允許清單本人」呈現（單一擁有者的個人理財部署），非匿名可見；不涉財務資料本身。
  **狀態：已修正（第二段）**。主 AI 確認採納後，`protocol_doc_repository.py` 的 `ProtocolDocError` 訊息改為使用者可見的「無法讀取行為協定文件，請確認部署包含 docs/PROTOCOL.md。」（不含伺服器絕對路徑）；完整路徑與底層 `OSError` 細節經 `from error` 保留在例外鏈，由 Page 層 `logger.exception` 記入 server log 供除錯——比照 `data_io_service.py:138` 讀檔/解析失敗的既有慣例（友善訊息 + `from error`）。`tests/test_protocol_doc.py` 僅斷言 `pytest.raises(ProtocolDocError)`、不驗訊息內容，未受影響。`uv run ruff check .` 綠、`uv run pytest tests/ -q` 282 全綠，無回歸。

- [資訊/建議] Checker 衛生 — 上述 3 條 CRITICAL false positive
  建議（判斷題，交主 AI 裁量）：由於 `sql_injection_risk` 屬 CRITICAL 且每次 3-2 掃描都會復現，長期會稀釋 CRITICAL 訊號、可能遮蔽未來真實注入，可考慮在該 3 行補 `# checker:noqa sql_injection_risk` 並附「識別子為常數、值走 `?` 綁定」說明，將其標記為「已評估的刻意安全寫法」。
  但需注意 3-1 審查對同類 checker 通用限制採「不逐一豁免」立場，且既有 `TargetRepository`/`schema_repository` 其餘三表同樣寫法未被豁免（僅因不在 diff 範圍未被掃出）——若補 noqa 宜以**repo 一致策略**評估，避免只豁免本 Change 這幾行造成標準不一。本輪為第一段（只寫報告），未實作任何 noqa。
  **狀態：主 AI 裁定不加 noqa**（第二段）——維持與既有 Repository 一致（既有同寫法皆未標註），不只豁免本 Change 這幾行以免標準不一。

### 各維度查證摘要（無新發現者一併記錄依據）

- **A01 存取控制／A07 認證失效（觸發理由二：落地頁改總覽）**：安全。`app.py::main()` 為線性順序——`_require_access()` 最先執行，未放行即 `st.stop()` 中止整支腳本；容器 `get_resilient_container()` 與 `st.navigation(...).run()` 皆在守門通過**之後**才執行，各 view 檔尾端的 `render()` 由 `navigation.run()` 觸發、亦在守門之後。nav 清單順序改變（`overview` 設 `default=True` 取代月度錄入）**不影響守門先於一切渲染/DB 存取**的不變量。頁面檔置於 `views/`（非 Streamlit 保留字 `pages/`，已確認無 `pages/` 目錄），避免 Streamlit 多頁自動路由繞過 `app.py` 守門——此為 initial-build 既定安全設計，本 Change 維持。`evaluate_access` 三段式 fail-closed（未登入擋／無 email 擋／不在白名單擋），email 兩側皆 `strip().lower()` 正規化一致。`allowed_emails()` 在 secrets 缺失時回空 set（`StreamlitSecretNotFoundError` → 空集），空集＝不放行任何人，漏設傾向擋下。
- **A05 安全設定／密鑰（觸發理由一：新增持久化表＋設定頁寫入）**：安全。Turso 憑證、`allowed_emails`、OAuth 設定全走 `st.secrets`，`bootstrap.py` 僅存 key 名稱常數、無寫死機密。`.gitignore` 已排除 `.streamlit/secrets.toml`、`.env`、`*.env`；`git ls-files` 僅追蹤 `.streamlit/secrets.toml.example`（內容經核對全為虛構佔位值：`owner@example.com`、`PASTE_YOUR_TURSO_AUTH_TOKEN_HERE` 等）；`git log --all -- '*.env' '*.pem' '*.key' 'secrets.toml'` 無任何歷史命中（密鑰從未進版控）。新增 `protocol_thresholds` 表僅存業務門檻數字（非機密、非個資），設定頁寫入前經 `validate_thresholds` 把關（`0 < l1 < l2 < l3`，NaN 因比較為 False 亦被擋、fail-closed），非法即拒不落 DB。
- **A03 注入／輸入驗證**：見上，3 條 CRITICAL 皆 false positive；值路徑全參數化。設定頁寫入的 `level` 為常數、`drawdown_threshold` 為 float，無自由字串入 SQL。
- **A02 加密／A08 完整性／A10 SSRF**：無新增加密作業（TLS 由 libsql `libsql://` 承擔，非本 Change）；無反序列化（無 pickle/yaml.load）；`views/protocol.py` 以 `st.markdown(text)` 渲染**版控且唯讀**的 `docs/PROTOCOL.md`，`unsafe_allow_html` 預設 False（HTML 逸出），內容非使用者供給，無 XSS；全 Change 無任何以使用者輸入構造的對外請求，無 SSRF 面。
- **A06 依賴元件**：`pip-audit` 無已知 CVE；`pip list --outdated` 僅 anyio/GitPython/narwhals/pydantic_core/streamlit 各差一個 minor/patch 版，非安全性修補，資訊級不阻擋。本 Change 未新增任何第三方依賴。
- **A09 日誌**：三個 view（overview/protocol/settings）皆 `logger.exception(<固定訊息>)` + `st.error(str(error))`——完整堆疊留伺服器日誌、對使用者只給友善訊息，未吞掉堆疊亦未把堆疊噴給前端；固定訊息不內插敏感資料。唯一資訊揭露為上述 ProtocolDocError 路徑（已列 LOW）。

### 建議 commit message

`docs(behavior-protocol): 3-2 安全審查報告（OWASP 全維度；SQL 注入 3 條 CRITICAL 復核為 false positive、pip-audit 無 CVE、守門不變量與密鑰治理查證通過，判定通過附 2 項 LOW 非阻擋建議）`

## 3-3 規則符合度審查

審查範圍：本 Change（t01–t05）新增/修改的原始碼與測試，共 19 檔：
`src/asset_lab/core/constants.py`、`core/exceptions.py`、`models/protocol.py`、`models/results.py`（`ProtocolStatus`）、`services/protocol_service.py`、`repositories/protocol_threshold_repository.py`、`repositories/protocol_doc_repository.py`、`repositories/schema_repository.py`（`protocol_thresholds` 建表）、`overview_presentation.py`、`bootstrap.py`（新增注入）、`views/overview.py`、`views/protocol.py`、`views/settings.py`（新增區段）、`app.py`（nav 新增）、`tests/test_protocol.py`、`test_protocol_thresholds.py`、`test_protocol_doc.py`、`test_overview.py`、`tests/test_bootstrap.py`（新增 wiring 斷言）。

**Diff-base 說明（偏離 dispatch 指定的 `origin/main`）**：本機 `origin/main` 已被前序階段（2-Z/3-1/3-2）持續直接推送，目前 = `dc15a3d`；`git diff origin/main HEAD` 只能看到最後 2 個未推送 commit（3-2 的 2 個 fix），無法涵蓋 t01–t05 全部異動。改以本 Change 真正起點的前一 commit `c10716a`（initial-build 收尾後、behavior-protocol 1-1 提案前）為 diff-base，`git diff c10716a HEAD` 即完整涵蓋 t01–t05。另需排除同期夾雜的**無關** commit `dc15a3d`（`feat(input): 月度錄入年月下拉`，非本 Change 範圍，diff 中已手動剔除其觸及的 `views/input.py`、`tests/test_input_view.py`、`tests/test_core_utils.py`、`src/asset_lab/core/utils.py`）。

核准判定：**通過**（無 CRITICAL / HIGH 真實違規；checker 報出的 103 HIGH + 19 MEDIUM + 2 LOW 經逐條復核，絕大多數為對照 initial-build 既有、已審定架構慣例的偽陽性；未發現本 Change 局部引入的新違規）

### 自動掃描

Checker 命令：`python .claude/skills/spec-driven-flow/scripts/checkers/runner.py --phase 3-3 --project-dir . --diff-base c10716a --json --output .ai/changes/behavior-protocol/.cache/checker_3_3.json`（`--diff-base` 由 `origin/main` 改為 `c10716a`，理由見上）
退出碼：0（正常完成）
總違規：124 條（CRITICAL: 0 / HIGH: 103 / MEDIUM: 19 / LOW: 2）
Baseline 命中：0 條
完整報告：`.ai/changes/behavior-protocol/.cache/checker_3_3.json`

按 `rule_id` 分組次數：`no_runtime_constants_access`×65、`docstring_returns_section`×15、`import_block_format`×13、`service_no_runtime_constants`×12、`constants_top_level_only`×4、`no_module_level_constants_alias`×3、`model_naming_convention`×2、`no_stdlib_get_logger`×2、`event_name_format`×2、`no_logger_exception`×2、`note_required`×2、`root_main_exists`×1、`src_project_layout_missing`×1。

### 逐條復核（按 rule_id 分組；每組列代表性樣本，判定套用同組全部命中）

- **`no_runtime_constants_access` + `service_no_runtime_constants`（合計 77 條，checker 已標，HIGH）**——「方法 body 內 runtime 存取 constants」，命中遍布 `protocol_service.py`（`PROTOCOL_LEVEL_CODE.*`／`PROTOCOL_LEVEL_DEFAULTS.*`）、`views/overview.py`／`views/settings.py`（`PROTOCOL_MIN_DATA_MONTHS`／`EARLIEST_YEAR_MONTH_SENTINEL`／`PROTOCOL_LEVEL_CODE.*`）、`views/input.py`（`TIMEZONE`，屬 dc15a3d 但一併列此判定供對照）與各測試檔。**判定：不違規（既有慣例延續，非本 Change 新增）**。以 `grep` 核對既有（已通過 initial-build 3-3 審查）的 `allocation_service.py`／`period_service.py`／`data_io_service.py`／`return_service.py` 四個 Service 檔，皆同樣在方法 body 內直接存取 `HOLDING_KIND.ASSET`／`PERIOD_MODE.INCEPTION` 等列舉常數，且該審查明確肯定「constants.py 以嵌套 class + 模組級具名常數組織」「Service 純運算無 I/O」而未對此存取模式提出違規。04-cross-cutting §3.2 表列的違規情境（`ENVIRONMENTS.DEV[...]`、Sheet `COL_NAME` schema 值）針對的是**環境差異值／Repository schema 欄位**——理由是不同實例可能需要不同注入值；`PROTOCOL_LEVEL_CODE`（列舉標籤）與 `PROTOCOL_LEVEL_DEFAULTS`（無 `--env` 差異的固定業務門檻預設）不屬此類，`ProtocolService` 亦無建構子參數、單例組裝、無「不同呼叫端需要不同值」的情境，且 `test_protocol_thresholds.py` 已直接對預設值行為斷言、可測性未受影響。checker 規則對「環境差異值」與「純業務列舉/預設常數」未加區分，屬規則對本專案場景的過度泛化，非本 Change 引入的新問題。
- **`import_block_format`（13 條，checker 已標，HIGH）**——「缺少 `# ==== AsiaYo 專案內部 ====`」。**判定：不違規（checker 誤判，未辨識專案已改用簡化用語）**。以 `grep` 核對 `allocation_service.py`／`target_repository.py`／`charts.py` 等既有檔案，全部一致使用 `# ==== 專案內部 ====`（無「AsiaYo」前綴）——這是本專案（個人 side project，非 AsiaYo 內部專案）在 initial-build 階段即已建立、且通過該次 3-3 審查的既定用語；01-coding-style.md 範例的「AsiaYo 專案內部」字面文字對非 AsiaYo 專案不適用。本次新增的 13 個檔案（`protocol.py`／`overview_presentation.py`／`protocol_doc_repository.py`／`protocol_threshold_repository.py`／`schema_repository.py`／`protocol_service.py`／`views/overview.py`／`views/protocol.py`／4 個測試檔）皆與既有檔案用語一致，未新增偏離。
- **`docstring_returns_section`（15 條，checker 已標，MEDIUM）**——私有 helper／測試 helper（`_neutral_message_for`、`_row_to_model`、`_current_drawdown`、`_level_for`、`_container`、`_format_decimal_as_percent`、`_format_percent_value`、`_series`、`_thresholds`、`_approx`、`_status`、`_run_app` 等）缺 `Returns:` 區塊。**判定：不違規（既有慣例延續）**。01-coding-style §3 docstring 規則明文只強制「**public** 函式、方法、類別」；上述全為底線開頭的私有/測試輔助函式。核對既有 `target_repository.py::_row_to_model`（單行 docstring、無 Args/Returns）與 `views/returns.py::_format_percent`（同樣單行、無 Returns），確認本專案對私有 helper 的既定慣例即為簡短單行 docstring，本次新增函式與此完全一致，非新增偏離。
- **`constants_top_level_only`（4 條，checker 已標，MEDIUM）**——`PROTOCOL_MIN_DATA_MONTHS`、`PROTOCOL_DOC_RELATIVE_PATH`、`_BEHAVIOR_FIREWALL_REMINDER`、`PROTOCOL_LEVELS` 為 constants.py 頂層散變數（非 class）。**部分判定不違規、部分為已知且合理的新結構**：
  - `PROTOCOL_MIN_DATA_MONTHS`／`PROTOCOL_DOC_RELATIVE_PATH`——與既有 `YEAR_MONTH_FORMAT`／`EARLIEST_YEAR_MONTH_SENTINEL`／`TIMEZONE`／`DEFAULT_REBALANCE_THRESHOLD`（皆為 constants.py 頂層純量常數）同構，initial-build 3-3 審查已明確描述並肯定「constants.py 以嵌套 class + **模組級具名常數**組織」。不違規，與既有慣例一致。
  - `_BEHAVIOR_FIREWALL_REMINDER`（私有字串常數，避免 3 處 `must_not` tuple 重複「行為防火牆通則」全文）與 `PROTOCOL_LEVELS`（`tuple[ProtocolLevelSpec, ...]`，frozen dataclass 記錄陣列）——**屬本 Change 新結構樣式，非既有純量常數模式的直接延伸**。判定可接受：`PROTOCOL_LEVELS` 本質是「4 列 × 5 欄」的規格表（code/label/band_text/must_do/must_not），以 `frozen dataclass` + `tuple` 表達比硬套嵌套 class 更貼合「多筆同形記錄」的資料形狀，且仍具型別安全與可查表特性（`_LEVEL_SPEC_BY_CODE = {spec.code: spec for spec in PROTOCOL_LEVELS}`），t04 任務卡（`tasks/t04-overview-landing.md`）已將此結構列為明確實作範圍、非事後隨意decision。`_BEHAVIOR_FIREWALL_REMINDER` 為單純 DRY 手法、僅檔內私用。均不影響任何硬性規則，checker 對「頂層皆 class」的字面比對未涵蓋 dataclass/tuple 這種等價形式，非本 Change 局部缺陷。
- **`no_module_level_constants_alias`（3 條，checker 已標，HIGH）**——`protocol_threshold_repository.py` 模組頂層 `_TABLE = PROTOCOL_THRESHOLDS_TABLE.TABLE_NAME` 等別名賦值。**判定：不違規（既有慣例延續，initial-build 3-3 已明文接受）**。核對既有 `target_repository.py`（`_TABLE = TARGET_ALLOCATIONS_TABLE.TABLE_NAME`、`_CATEGORY = ...`）完全同構，initial-build review.md §3-3 已對此模式做出明確結論：「Repository 的 `from constants import *_TABLE` 為模組級 schema 常數定義用於組 SQL 字串、非 runtime 環境差異值……本專案無 `--env` 多環境、表名為全域固定常數，且 SQL 模板須在模組級組裝，判定可接受、非違規」。本次新 Repository 與既有 Repository 手法一致，非新增偏離。
- **`model_naming_convention`（2 條，checker 已標，LOW）**——`ProtocolThresholds`、`ProtocolStatus` 未使用 `XxxModel`/`XxxResult` 後綴。**判定：不違規（既有慣例延續）**。核對既有 `models/results.py` 內 `CumulativeTwrPoint`、`AllocationSnapshot`、`NetWorthPoint`、`DriftRow` 四個既有 model 皆為「計算/呈現用值物件」，均未加 `Model`/`Result` 後綴（僅持久化列模型如 `HoldingModel`／`TargetAllocationModel`／`ProtocolThresholdModel` 才加 `Model`）；`ProtocolThresholds`（合併後有效門檻值物件）、`ProtocolStatus`（判定結果值物件）與上述四個既有非持久化 model 屬同一命名類別，一致不加後綴，非新增偏離。
- **`no_stdlib_get_logger` / `event_name_format` / `no_logger_exception` / `note_required`（合計 8 條，checker 已標，HIGH）**——`views/overview.py`／`views/protocol.py` 用 `logging.getLogger(__name__)` 與 `logger.exception("總覽頁渲染失敗")`（非 structlog kwargs 格式）。**判定：不違規（AD-8 既定偏離，initial-build 3-3 已確認）**。核對既有全部 7 個 view（`input.py`／`data_io.py`／`allocation.py`／`returns.py`／`settings.py` 等）皆同一寫法：`logging.getLogger(__name__)` + `logger.exception(<固定中文訊息>)`。design.md 開頭即載明「本 Change 不新增機密、不新增第三方依賴……沿用 initial-build 的偏離依據（標準 `logging` + Page 層唯一 catch），不另套 v2 工具」。checker 對 structlog kwargs 契約（`note=`／`event_name` 格式／`exc_info=True`）的檢查對本專案（無 utils_v2、無 structlog）不適用，屬既定且已審定的架構偏離，非新增違規。
- **`root_main_exists` / `src_project_layout_missing`（2 條，checker 已標，HIGH）**——缺 `main.py`、缺 `asset_lab/controllers`。**判定：不違規（initial-build AD-1／AD-2 既定偏離，已於前次 3-3 審查確認）**。本 Change 未變更專案入口模型或分層結構，沿用既有 `app.py` + `st.navigation` + `views/` 扮演 Controller 角色的架構，無需重新論證。

### 規則審查發現（checker 未報出，人工掃描）

未發現本 Change 局部引入、checker 遺漏的額外違規。以下為人工比對established風格後的**觀察性**記錄（非違規）：

- [LOW，供記錄] `src/asset_lab/overview_presentation.py` 定位為「Page 呈現轉換層」，未放在 `services/`——與既有 `src/asset_lab/charts.py`（docstring 明文「不做業務運算，只負責呈現契約」）同一定位，且 `overview_presentation.py` 自身 docstring 已明確聲明「定位比照 charts.py」。判定為既有架構模式的合理延伸：把「狀態 → 呈現資料」的純函式抽離出 View，使 `views/overview.py`（Controller 角色）維持薄委派、不含查表/轉換邏輯，反而比把邏輯留在 View 內更貼合 02-architecture §2「運算/轉換/篩選歸 Service」精神。無需動作。
- [LOW，供記錄] `src/asset_lab/repositories/protocol_doc_repository.py::read_protocol_markdown` 捕捉 `OSError` 並轉型為 `ProtocolDocError` 後 `raise ... from error`（不 log）。核對既有 `record_repository.py::insert_record` 同樣「catch → 依內容轉譯領域例外類型 → raise，不 log」，且 initial-build 3-3 已明確判定此手法為「轉譯例外類型後 raise 屬合法的加 context 轉拋，非吞例外」。本次新 Repository 手法一致，非違規；3-2 安全審查已另就此檔案的訊息內容（不洩漏伺服器路徑）做過核准。

### 各規則檔逐項符合度結論

- **01-coding-style**：雙引號、`snake_case`/`PascalCase`、kwargs（所有方法呼叫與建構子注入一律 keyword args，含 `ProtocolThresholdModel(level=..., drawdown_threshold=...)`、`protocol_service.assess(series=..., thresholds=..., min_data_months=...)` 等）皆遵守。型別提示全部函式簽名（含私有 helper、`ProtocolService` 全部方法、`overview_presentation` 全部函式）齊備，`float | None`／`list[...]`／`tuple[...]` 現代語法一致（呼應既有 UP045 既定偏離，`Optional[X]` 已全面改 `X | None`）。docstring：public 函式/方法/類別皆有、繁中、含 Args/Returns（`ProtocolService.assess`／`validate_thresholds`／`effective_thresholds` 尤詳盡，含 Raises 說明業務邊界）；私有 helper 沿用既有簡短單行慣例（見上）。註解說明 WHY（如 `protocol_service.py` 對「起始基準 1.0」「四捨五入精度」「達門檻即進入較深級」等業務決策的大量行內註解），未見「已修正」「依你指示」類禁忌註解。Import 三區塊用語與既有一致（`# ==== 專案內部 ====`），空區塊 `# 無` 緊接下一標頭無空行——與既有全庫（`target_repository.py` 等）同一 ruff I001 既定偏離，不重複處理。魔法字串：協定等級代碼、狀態旗標（`_STATUS_NO_DATA` 等）、必做/禁止文字皆具名常數，未見散落魔法字串。
- **02-architecture**：分層歸屬正確——`ProtocolService` 純運算、建構子無依賴、無 I/O、無 Streamlit 依賴，內部迴圈（`effective_thresholds` 的 dict comprehension）不涉容錯決策，符合 §5。`ProtocolThresholdRepository`／`ProtocolDocRepository` 只做 I/O 與 row↔model 轉換，業務校驗（門檻順序合法性）明確委由 Service（`validate_thresholds`），docstring 亦自陳「本層不判斷」，符合 §6 與既有 AD-9 精神（`target_repository.py` 同構）。`views/overview.py`／`views/protocol.py`／`views/settings.py` 新增區段皆為委派 + 渲染，未見資料篩選/轉換/欄位細部操作留在 View（`_format_*` 屬純顯示格式化，非業務轉換，且與既有 `returns.py::_format_percent` 同構）；`overview_presentation.resolve_presentation` 把「狀態→呈現」查表邏輯抽離 View，比 View 內聯更符合「Controller 不做資料轉換」原則。`bootstrap.py` 新增注入（`protocol_threshold_repo`／`protocol_doc_repo`／`protocol_service`）遵循既有 DI 組裝順序（Repo→Service→Container，keyword args）。main.py/controllers 結構偏離為既有 AD-1/AD-2（見自動掃描復核），本 Change 未擴大偏離面。
- **03-data-config**：constants.py 新增內容以「業務概念」分組（`PROTOCOL_LEVEL_CODE`／`PROTOCOL_LEVEL_DEFAULTS`／`PROTOCOL_THRESHOLDS_TABLE`），DB schema 常數延續既有扁平 class 模式（`TABLE_NAME`／`LEVEL`／`DRAWDOWN_THRESHOLD`，無 URL 混入、無 SCHEMA 中間層）。`ProtocolLevelSpec`（frozen dataclass）+ `PROTOCOL_LEVELS`（tuple）為新結構樣式，已於上方逐條復核中評估為合理延伸、非違規。Pydantic Model（`ProtocolThresholdModel`／`ProtocolThresholds`／`ProtocolStatus`）皆純資料結構，無業務邏輯、無 I/O、無 field_validator、無 Service/Repository 呼叫；命名慣例與既有非持久化 value object（`DriftRow` 等）一致（見上）。機密治理：本 Change 未新增任何機密欄位，3-2 安全審查已確認。
- **04-cross-cutting**：Logging 延續既有 stdlib `logging.getLogger(__name__)` + Page 層 `logger.exception`（AD-8 既定偏離，見上）。Error handling：`ProtocolService.validate_thresholds` 拋 `DataValidationError`（純運算業務規則違反，非「轉換例外類型」但屬 Service 合法直接拋出）；`ProtocolDocRepository` 轉譯 `OSError→ProtocolDocError`（既有 Repository 慣例延伸，見上）；`views/*.py` 為唯一 catch 點，`except AssetLabError`（`DataValidationError`／`ProtocolDocError` 皆其子類）統一攔截，不重複 log、不吞例外。DI：`ProtocolService` 建構子無依賴（純運算不需注入），`ProtocolThresholdRepository`／`ProtocolDocRepository` 依賴（`conn`／`doc_path`）皆由 `bootstrap.build_container` keyword 注入；Service/View 方法 body 內對 `PROTOCOL_LEVEL_CODE`／`PROTOCOL_MIN_DATA_MONTHS` 等業務列舉/常數的直接存取，經上方逐條復核判定為既有全庫慣例的延伸、非違規（詳見自動掃描復核第一項）。
- **05-reference**：作為理想化 RPA/utils_v2 場景的具現化參考，其 structlog／main.py／建構子注入列舉常數等寫法與本專案已確立的偏離（AD-1／AD-2／AD-8，及本次確認的「Service 直接存取列舉常數」既有慣例）已於 initial-build 與本次審查完整論證，不重複裁決。

### 既定偏離延續清單（本次未新增偏離，僅重申已審定項）

- **`X | None` 取代 `Optional[X]`**（ruff UP045）——initial-build 已確認採 ruff 為準，本次新增程式碼全數一致。
- **`# ==== 專案內部 ====` 取代 `# ==== AsiaYo 專案內部 ====`**——本專案非 AsiaYo 內部專案，既定簡化用語，本次新增檔案一致延續。
- **AD-1／AD-2／AD-8（Streamlit 入口、Page 即 Controller、stdlib logging）**——design.md 開頭已明文重申沿用，不擴大偏離面。
- **Repository 模組頂層 schema 常數別名**（`_TABLE = XXX_TABLE.TABLE_NAME`）——initial-build 3-3 已明文接受，本次新 Repository 延續同一手法。
- **Service／View 方法 body 內直接存取列舉/業務常數**（`HOLDING_KIND.ASSET` 類比 `PROTOCOL_LEVEL_CODE.L0`）——本次審查首度就此模式明確論證並確認為既有慣例（此前 initial-build 3-3 報告未逐字點名此模式，但既有 4 個 Service 檔已一致採此寫法且通過審查），供後續 Change 引用免重複論證。

### 建議 commit message

`docs(behavior-protocol): 3-3 規則符合度審查報告（工程準則全面比對；checker 124 條違規逐條復核，皆為對照 initial-build 既有架構慣例的偽陽性或既定偏離延續，無 CRITICAL/HIGH 真實違規，判定通過）`

<!-- rules-reviewer subagent 產出（工程準則全面符合度檢查）-->

## 3-4 行為對映審查

審查範圍：8 個 SC（SC-043~SC-050，含 t05 對 SC-050 的文字修訂）× 4 個 test 檔、
46 個 `@pytest.mark.scenario` 裝飾點（parametrize 展開後實際執行筆數更多：SC-044
深度邊界 ×8、SC-045 月數不足 ×2、SC-047 非法組合 ×5、SC-050 防火牆繼承 ×3）——
tests/test_protocol.py（SC-043×5／SC-044×2／SC-045×4）、tests/test_protocol_thresholds.py
（SC-046×6／SC-047×3）、tests/test_protocol_doc.py（SC-048×6）、tests/test_overview.py
（SC-050×8／SC-049×12）。

比對方式：逐張讀 SC 卡片 GIVEN/WHEN/THEN + 邊界/錯誤，對照對映 test 函式的實際輸入值
（series 建構、thresholds 值）與 assert 斷言內容；並回溯 `ProtocolService.assess`／
`validate_thresholds`、`overview_presentation.resolve_presentation`、`constants.PROTOCOL_LEVELS`
與 `docs/PROTOCOL.md` 原文，確認 test 斷言不是空判或弱斷言，而是真的鎖住 SC 描述的數值/文案。

核准判定：**通過**（不對齊清單為空；下方列一項非「不對齊」但值得記錄的既有慣例觀察）

### 不對齊

（無）

### 對齊

| SC | test 函式 | 判斷依據 |
|----|----------|---------|
| SC-043 | test_sc043_drawdown_from_growth_index_with_inception_baseline | series=[+5%,−8%,−22%]，斷言 drawdown≈0.78/1.05−1、current_cumulative_twr≈−22%、data_month_count=3、status=ok，逐項對齊 SC 例題 |
| SC-043 | test_sc043_only_losses_peak_still_anchored_at_inception | **直接鎖定「歷史高點納入起始基準 1.0」本身**：series=[−6%,−13%,−19%]（只跌不漲），斷言 drawdown≈−19%（=0.81/1.00−1）而非誤把首月 0.94 當高點的 −13.8%——回溯 `_current_drawdown()` 原始碼確認 `index_path=[1.0, *(1+twr)]`、`peak=max(index_path)` 確實把 1.0 併入取最大值運算，test 若拿掉基準 1.0 會斷言失敗，非空跑一般回撤 |
| SC-043 | test_sc043_new_high_has_zero_drawdown | series 全正且遞增，斷言 drawdown≈0 且 level_code=L0，對齊「投組正處歷史新高」邊界 |
| SC-043 | test_sc043_peak_in_middle_of_series | series=[+10%,+20%,+5%]，斷言 drawdown≈1.05/1.20−1（以中段高點量測），對齊「歷史高點在中段」邊界 |
| SC-043 | test_sc043_extreme_gain_then_crash_still_measures_from_true_peak | 極端值 9.0→4.0（暴漲後腰斬），斷言 drawdown=−50%，SC 卡片未列此邊界但屬同一行為的延伸覆蓋，不牴觸 |
| SC-044 | test_sc044_depth_maps_to_expected_level（parametrize×8：0.0/9.99/10.0/19.99/20.0/29.99/30.0/35.0） | **精確覆蓋 SC 邊界表全部 8 個值**，含 3 個「恰等於門檻」邊界（10.0→L1、20.0→L2、30.0→L3）與 3 個「差一絲未達」邊界（9.99/19.99/29.99）；series 以固定小跌鎖定高點於 1.0、末月精確跌到 `depth_percent/100`，回溯 `_level_for()` 用 `depth >= threshold` 的 `>=` 語意確認「達門檻進較深級」實作與測試斷言方向一致，非只測中間值 |
| SC-044 | test_sc044_same_input_yields_same_level_across_calls | 額外驗證純函式無隱藏狀態（同輸入重複呼叫結果一致），非 SC-044 核心邊界但斷言的 level_code=L2 仍與深度 20% 對應正確，不牴觸 |
| SC-045 | test_sc045_no_record_returns_no_data_status | series=[]，斷言 status="no_data"（與下一項 "insufficient_data" 為不同字串），level=L0、drawdown=None、current_cumulative_twr=None，對齊「有效月數=0／完全無紀錄」邊界 |
| SC-045 | test_sc045_below_minimum_months_returns_insufficient_data_despite_huge_drop（parametrize month_count=[1,2]） | series 單月/雙月暴跌 90%，斷言 status="insufficient_data"（與上一項 "no_data" 字串不同）、level=L0、drawdown=None，但 current_cumulative_twr 仍可讀取 −90%；對齊「有效月數=1或2／有資料但不足」邊界，且證明「不因少數月雜訊誤報大跌」 |
| SC-045 | test_sc045_at_minimum_months_assesses_by_drawdown_depth | 有效月數=3，斷言 status="ok"、正式依深度判定 L2，對齊「達下限」邊界 |
| SC-045 | test_sc045_min_data_months_is_caller_configurable_not_hardcoded | 額外驗證 min_data_months 為呼叫端注入參數非寫死，SC 未列但不牴觸 |
| SC-045（文案部分） | test_overview.py::test_sc049_no_record_shows_l0_with_no_record_message_and_no_drawdown／test_sc049_below_minimum_months_shows_l0_with_distinct_message／test_sc049_no_data_and_insufficient_data_messages_are_distinct（掛 SC-049，非 SC-045 marker） | **「無紀錄」與「資料不足」兩種文案確實分別被覆蓋，t05 前後皆完整、無遺漏**：`NO_DATA_MESSAGE = "尚無資料，請先至月度錄入輸入"`／`INSUFFICIENT_DATA_MESSAGE = "資料尚不足，暫不評估大跌等級"` 逐字比對 SC-045／SC-049 卡片原文完全相符，並有專門測試斷言兩文案不相等；SC-045 卡片本身「測試對映」只寫 tests/test_protocol.py（服務層 no_data/insufficient_data 兩狀態），文案呈現層留給 SC-049（呈現層職責），兩者合起來完整覆蓋、非遺漏，只是分散在兩個 SC 的 marker 下 |
| SC-046 | test_sc046_never_configured_uses_all_defaults／test_sc046_missing_level_falls_back_to_default／test_sc046_all_levels_stored_overrides_all_defaults | 分別覆蓋「全未設定」「缺一級」「三級皆設」，對齊 SC 邊界「缺值以預設補齊」 |
| SC-046 | test_sc046_saved_thresholds_persist_across_repository_reload | 存值後另建 Repository 實例重讀同一連線，模擬重啟重建 Repo，對齊「持久化」 |
| SC-046 | test_sc046_thresholds_persist_across_container_rebuild | 端到端以 `bootstrap.build_container` 重建整個容器（非只重建 Repository）驗證門檻仍在，對齊「重啟後生效」比 Repository 級測試更貼近真實部署路徑 |
| SC-046 | test_sc046_new_thresholds_change_level_assessment | 新門檻 L1=12/L2=25/L3=35，回撤 26% 斷言判為 L2，逐字對齊 SC 例題 |
| SC-047 | test_sc047_invalid_order_raises_validation_error（parametrize×5，含 L2=L3 額外邊界） | 覆蓋 SC 錯誤清單全部 4 種（順序顛倒/相等/零/負值）+1 個 SC 未列但同語意的 L2=L3 邊界，皆斷言拋 DataValidationError |
| SC-047 | test_sc047_valid_strictly_increasing_thresholds_pass | 合法值 12/25/35 通過，對齊「合法設定」邊界 |
| SC-047 | test_sc047_rejected_save_does_not_change_persisted_thresholds | **端到端持久化不受影響，非只測驗證函式本身**：先以 Repository 把合法值 10/20/30 落地寫入記憶體 DB，呼叫 `validate_thresholds(20,10,30)` 確認拋例外後，**重新讀 DB**（`repo.read_thresholds()`）斷言仍是 10/20/30 未被更動；模擬「view 驗證失敗不會呼叫 upsert」的呼叫慣例（比照 target_allocations 既有測法），非空泛只測 validate_thresholds 拋例外 |
| SC-048 | test_sc048_reads_full_markdown_text_from_real_file | 讀真實 docs/PROTOCOL.md，逐次重讀磁碟原文比對，非快取舊值，對齊「顯示文件當前最新內容」 |
| SC-048 | test_sc048_content_covers_all_protocol_sections | 逐一斷言 6 個標題字串存在於全文，逐字核對 docs/PROTOCOL.md 實際標題（本協定存在的理由/情境分級與對應動作/機動加碼規則/行為防火牆/事前授權的例外/檢核）完全相符，對齊 THEN 條列 |
| SC-048 | test_sc048_missing_file_raises_protocol_doc_error／test_sc048_directory_path_raises_protocol_doc_error_not_raw_os_error | 分別覆蓋檔案缺失與路徑為目錄（IsADirectoryError）兩種底層例外，皆須轉為統一的 ProtocolDocError，對齊錯誤 THEN「不顯示技術堆疊」的前置條件（Repository 層不外洩底層例外型別） |
| SC-048 | test_sc048_container_protocol_doc_repo_reads_real_file／test_sc048_module_level_path_resolves_to_repo_root_docs_file | 端到端經 bootstrap 容器組裝仍讀到真實檔案，對齊「文件存在於系統可存取位置」不依賴 CWD |
| SC-049 | test_sc049_l2_shows_level_band_and_metrics | status=L2/ok/drawdown=−25%，斷言 label=熊市、band=−20%~−30%、show_alert=True、drawdown_percent=−25.0，對齊 SC 例題（L2 燈號與回撤帶） |
| SC-049 | test_sc049_l0_with_sufficient_data_has_no_alert | 資料充足但 L0：斷言 show_alert=False，對齊「警示只在 L1–L3」隱含前提 |
| SC-049 | test_sc049_l3_must_do_is_rule_reference_text_not_computed_amount／test_sc049_presentation_struct_carries_no_computed_amount_field | 斷言 L3 必做文字不含金額語彙（$/元），且 `OverviewPresentation` dataclass 欄位集合鎖定為僅 4 個（無任何加碼金額/現金地板欄位），結構性防止日後誤加，精確對齊「僅顯示規則文字，不計算/顯示加碼金額」邊界 |
| SC-049 | test_sc049_l3_status_still_shows_alert_and_drawdown | L3 仍顯示警示與回撤數值（−35%），對齊「L3 只是必做內容不同，非整體隱藏」 |
| SC-049 | test_sc049_no_record_shows_l0_with_no_record_message_and_no_drawdown | status=no_data，斷言 level=L0、show_alert=False、drawdown_percent=None、neutral_message=NO_DATA_MESSAGE，對齊「完全無紀錄」邊界 |
| SC-049 | test_sc049_below_minimum_months_shows_l0_with_distinct_message | status=insufficient_data，即使 current_cumulative_twr=−90% 仍斷言不顯示回撤數值/警示、文案為 INSUFFICIENT_DATA_MESSAGE，對齊「有資料但不足」邊界 |
| SC-049 | test_sc049_no_data_and_insufficient_data_messages_are_distinct | 直接斷言兩文案字串不相等，鎖定「兩種情況需不同文案」不被日後改成同一句 |
| SC-049 | test_sc049_overview_view_file_exists／test_sc049_overview_registered_as_first_page_with_default_true／test_sc049_existing_pages_still_registered_after_reorder | 以 app.py 原始碼正則掃描，斷言 overview.py 為第一個 `st.Page` 且唯一 `default=True`、其餘既有頁面仍註冊，對齊「總覽為登入落地頁、取代月度錄入」且未破壞既有導覽 |
| SC-050 | test_sc050_four_levels_present_in_ascending_order | PROTOCOL_LEVELS 順序=L0→L1→L2→L3，對齊四級結構 |
| SC-050 | test_sc050_l0_must_do_and_label／test_sc050_l1_matches_protocol_table／test_sc050_l2_matches_protocol_table／test_sc050_l3_prohibitions_equal_l2_plus_cooldown | 逐級逐字比對 must_do/must_not/label/band_text，與 `docs/PROTOCOL.md` §1 表原文（回溯核對：L1「照常定期定額，什麼都不改」「增加看盤頻率;閱讀「崩盤將至」類內容」、L2/L3 同理）逐字相符，對齊「摘要須與協定表一致」 |
| SC-050 | test_sc050_l0_must_not_is_not_blank_and_states_no_special_prohibition | 斷言 L0 must_not 非空且含「無特別禁止」字樣，對齊「不得呈現為空白」邊界 |
| SC-050 | test_sc050_l0_stays_clean_without_firewall_or_crash_wording | **t05 修訂後的核心斷言**：斷言 L0 的 must_do/must_not 全部項目皆不含「券商 App」「行為防火牆」字樣；回溯 `constants.py` PROTOCOL_LEVELS 的 L0.must_not 目前僅為 `("無特別禁止事項（平時姿態，維持既定計畫）",)`，不含防火牆提醒，test 與修訂後常數/SC-050 文字三方一致，非仍測舊版（舊版把防火牆提醒掛在 L0.must_not） |
| SC-050 | test_sc050_l1_and_above_include_firewall_reminder（parametrize L1/L2/L3） | 斷言 L1/L2/L3 的 must_not 皆含「行為防火牆通則：只看本系統，不看券商 App」，對齊「自 L1 起顯示、L2/L3 皆沿用（L3 透過同 L2 繼承）」修訂後語意 |

### 觀察（非不對齊，列出供參考，不影響本次核准判定）

- SC-049 THEN 條列的「關鍵指標」含三項：最新累積 TWR、目前淨值、目前自高點回撤百分比。目前只有「回撤百分比」經 `overview_presentation.resolve_presentation` 純函式被 test 直接鎖定數值（`drawdown_percent`）；「最新累積 TWR」與「目前淨值」實際渲染邏輯在 `views/overview.py::_render()`（呼叫 `st.metric("最新累積 TWR", ...)`／`st.metric("目前淨值", ...)`），該檔案模組尾端無條件呼叫 `render()`，依本專案既有慣例（見 test_overview.py 檔案開頭註解，比照 test_page_config.py／test_navigation_guard.py 的作法）不直接 import 測試，因此這兩項指標「有沒有真的顯示、標籤文字/來源值是否正確」目前沒有任何測試鎖定（無論是純函式測試或 app.py 原始碼掃描）。經確認此為既有專案架構慣例（views/*.py 渲染細節普遍不被單元測試，只測抽出的純函式層），非本 Change 新引入的特有缺口（views/protocol.py、views/input.py 等既有頁面亦同），故不列為「不對齊」、不建議在本輪回頭補測試；若未來要補強，建議做法是仿照 test_sc049_overview_registered_as_first_page_with_default_true 的原始碼正則掃描手法，斷言 `views/overview.py` 原始碼含 `st.metric("最新累積 TWR"` 與 `st.metric("目前淨值"` 字樣。

### 建議 commit message

（本階段僅產出審查報告，無程式碼異動，不需 commit；若第二段有修正，屆時再補對應 commit message）

<!-- scenario-mapper subagent 產出（AI 比對 SC 描述 vs test 內容，分「不對齊」「對齊」兩類）-->
