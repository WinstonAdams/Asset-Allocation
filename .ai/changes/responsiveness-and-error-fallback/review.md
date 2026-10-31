# Review: [Change 名稱]

## 3-1 程式碼清理

掃描範圍：78 個檔案（含 tests/文件），ac02bbb..HEAD（分支 feature/responsiveness-and-error-fallback）；原始碼 app.py、src/asset_lab 新增與修改模組、views/*.py 逐檔復核

### 自動掃描

Checker 命令：`python .claude/skills/spec-driven-flow/scripts/checkers/runner.py --phase 3-1 --project-dir . --diff-base ac02bbb --json`
總違規：8 條（HIGH 2、MEDIUM 6）
Baseline 命中：0 條
完整報告：`.ai/changes/responsiveness-and-error-fallback/.cache/checker_3_1.json`
靜態工具：`ruff check .` 全過；vulture 未安裝，跳過。

### SAFE
- `tests/test_bootstrap.py:1112` — 註解「logging 設定與頁面 logger 命名（SC-132）」含 Change 級編號，歸檔後成 dead reference（checker 已標，復核屬實）。改為不含編號的描述（如「logging 設定與頁面 logger 命名」）。
- `tests/test_connection_layers.py:216` — 註解「見 SC-114」同上（checker 已標，復核屬實）。改為只保留「讀取會繞過快取」的 WHY。
- `src/asset_lab/rerun_runtime.py` — `rerun_scope` 與 `verified_container` 之間多一個空行（共 3 個空行），縮為 2 個（checker 未報出；ruff check 不管，ruff format 會抓）。
- 原始碼（src、views、app.py）diff 範圍內無 print、無 TODO/FIXME、無編號註解（grep 已確認；檔頭 docstring 的 AD/BR 引用亦無）。

### CAREFUL
- `src/asset_lab/repositories/house_param_repository.py::upsert_param`、`protocol_threshold_repository.py::upsert_threshold` — settings 頁改走整批 `upsert_params`/`upsert_thresholds` 後，單筆版在正式程式碼已無呼叫者，只剩 tests 引用（vulture 未裝，以 grep 確認；checker 未報出）。是否移除取決於是否保留為公開 API；移除需同步改 tests/test_house_params.py、test_house.py、test_protocol_thresholds.py 中共 12 處呼叫，範圍超出「本次 diff 變更區塊」，建議不動，若要動請使用者決定。
- `src/asset_lab/repositories/query_metrics.py::total_roundtrips` — 只被 tests 使用，docstring 已明示為測試用，屬刻意設計，保留。
- `src/asset_lab/error_boundary.py` — `error_boundary` 與 `guarded_callback` 內「領域例外 / 未預期例外 / 細節開關」分類邏輯重複約 6 行，僅輸出方式不同（st.error vs session_state）。可抽共用分類，但會增加間接層，且兩處各 2 個分支，維持現狀可讀性反而較好；列為可選，不建議做。

### RISKY
- 無。

### SUGGEST
- `src/asset_lab/bootstrap.py::build_container`（68 行，checker 已標 MEDIUM）— 行數主因是 Container 欄位逐一具名接線與長 docstring，無分支；切分只會拆散「全專案唯一組裝點」的可讀性。判定為合理，不拆；若要豁免，建議於 def 行補 `# checker:noqa function_too_large`。
- `views/input.py::_render_record_editor`（65 行，checker 已標 MEDIUM）— 前半為取依賴與主檔選擇，後半為四種錄入方式分派。可把「取容器與資料」抽成小函式，但 fragment 內本就需自取資料，抽出收益小；建議不拆（可補 noqa 說明）。
- `tests/test_connection_layers.py::test_sc114_query_in_flight_when_commit_happens_is_not_written_back`（52 行，checker 已標）— 競態情境測試，單一情境不宜拆，超 2 行；建議補 noqa 或維持。
- `tests/flaky_connection.py:32`、`tests/test_data_io.py:848-849` duplicate_code（checker 已標）— 前者為參數簽名/賦值樣板，後者為三組 (key, content) 小表；皆為測試樣板，偽陽性，不整合。
- 預先存在的 `ruff format` 差異（35 檔不合格式，含 views/input.py、allocation.py、returns.py 的非本次變更行）— 與本 Change 無關，專案未強制 format，依範圍守則不動。
- 已知且使用者已同意，不列問題：app.py 總覽註冊行 noqa E501；頁面 logger 用 `asset_lab.views.<頁>`。

### 第二段建議修正範圍
僅 SAFE 三項（兩處測試註解去編號、rerun_runtime 空行）；其餘 CAREFUL/SUGGEST 不動。

## 3-2 安全性審查

審查範圍：22 個檔案（app.py、.streamlit/config.toml、src/asset_lab 12 檔、views 8 檔），ac02bbb...HEAD；另以 checker 與 grep 掃過 tests 20 檔的密鑰／個資（無發現）
核准判定：有條件通過（1 項 MEDIUM 依賴 CVE、1 項 LOW；無 CRITICAL／HIGH 發現）。第二段已修掉 MEDIUM；LOW 改由上線目視檢查追蹤

### 自動掃描

Checker 命令：`python3 .claude/skills/spec-driven-flow/scripts/checkers/runner.py --phase 3-2 --project-dir 資產管理 --diff-base ac02bbb --json --output 資產管理/.ai/changes/responsiveness-and-error-fallback/.cache/checker_3_2.json`（diff 基準照主 AI 指定用 ac02bbb，不用 origin/main）
總違規：0 條（CRITICAL: 0 / HIGH: 0 / MEDIUM: 0 / LOW: 0），掃描 40 檔（.streamlit/config.toml 不在 checker 範圍，人工已看）
Baseline 命中：0 條
完整報告：`.ai/changes/responsiveness-and-error-fallback/.cache/checker_3_2.json`

### 依賴掃描（A06）

- `pip-audit`（.venv）：1 個套件 3 筆 CVE，見下方 MEDIUM 發現；其餘套件無已知漏洞。
- 本次 diff 沒有改 pyproject.toml、uv.lock，沒有新增第三方依賴（符合 design TD-4）。
- `uv pip list --outdated`：authlib 1.7.2→1.9.1、starlette 1.3.1→1.10.0、cryptography 50.0.0→50.0.2 等有新版，pip-audit 都沒有報 CVE，屬例行升級，不列發現。

### 環境與密鑰檢查（A05）

- 為了不把可能的密鑰值帶進輸出，`git log --all` 改用 `--name-status` 列出 `*.env`／`*.json`／`*.pem`／`*.key`／`secrets.toml` 的歷史紀錄：只有 `.devcontainer/devcontainer.json`（內容沒有 token／secret／password 字樣）；`.env`、`.streamlit/secrets.toml` 從未進版控，.gitignore 已排除。
- 本次新增的 `.streamlit/config.toml` 只有 `[client] showErrorDetails = "none"`，沒有機密。
- diff 新增行掃描 token／URL／email 樣式：0 筆。測試只用 `owner@example.test`、`stranger@example.test`、`:memory:` 和 tmp_path 的 libsql，不連正式庫。
- 新增環境變數 `ASSET_LAB_SHOW_ERROR_DETAILS` 是部署環境差異的開關，不是機密。由入口 `os.environ` 讀取，變數名放在 constants，符合 03-data-config 決策表。本次沒有新增 secrets，所以不涉及金鑰輪換。

### 發現

- [MEDIUM] A06 — `uv.lock`（不是本次引入，main 上也有）— 開發用的間接依賴 filelock 3.29.7 有 3 筆已知 CVE
  問題：pip-audit 報出 CVE-2026-112940（GHSA-v4x8-3wr5-3wq8，GHSA 評為 HIGH）、CVE-2026-112913（GHSA-9vhv-jxww-xfm5，LOW）、CVE-2026-112907（GHSA-567q-5qvw-pf92，LOW）。受影響版本是 >=3.20.4 到 <=4.2.0，修補版 4.2.1，公告日 2026-10-23。依賴路徑是 asset-lab[dev] → pip-audit[filecache] → cachecontrol[filecache] → filelock，只在 dev 這個 optional extra。漏洞位置是 SQLite 版 `ReadWriteLock`／`AsyncReadWriteLock`（POSIX 的符號連結問題）與 Windows 的 soft lock；本專案程式不 import filelock，pip-audit 的快取用的是一般 `FileLock`。
  修復：`uv lock --upgrade-package filelock` → `uv sync --extra dev` → 重跑 `pip-audit` 確認 0 筆、`pytest` 全過。已用 `--dry-run` 試過，可直接解析到 4.2.4，沒有衝突；dry-run 前後 uv.lock 一致，沒有寫入。只改 uv.lock 的 dev 依賴，不影響 App 程式碼。
  影響：正式安裝不帶 dev extra，App 也不呼叫 filelock，公開網址沒有暴露面。風險只在開發機：要有另一個本機帳號能在鎖檔目錄建立符號連結才利用得到，本機是單人 macOS，實際上幾乎無法利用。原始評級 HIGH，依實際情境降為 MEDIUM。若照字面「有 HIGH CVE 就阻擋」處理，升級後也就解除了，成本很低，建議第二段直接修。
  Checker 對應：checker 未報出（依賴掃描不在 checker 範圍）

- [LOW] A05 — `app.py` 模組層（import 與 `st.set_page_config`）— 主防線 L1 的 `st.set_option("client.showErrorDetails", ...)` 要到 `main()` 才執行
  問題：如果 main() 之前就出錯（最可能是部署後某個依賴或專案模組 import 失敗），每次執行都會在同一處失敗，永遠跑不到 set_option，只剩 L0 `.streamlit/config.toml` 擋。design AD-8 自己寫了「Community Cloud 仍使用舊版 False（等同 stacktrace），只改 config.toml 不保證雲端生效」。所以如果雲端用命令列參數或環境變數蓋掉 L0，未登入的訪客會看到 stacktrace 模式的畫面（通用訊息加程式堆疊）。只要有一次執行跑到 set_option，就會以程序全域設定生效，這個缺口只在「import 層壞掉」時存在。
  修復（擇一，由使用者決定）：(a) 把 set_option 提前到 `import streamlit as st` 之後、專案模組 import 之前。`resolve_error_detail_mode` 要搬到不依賴 libsql 的輕量模組（constants 本身是純模組）。(b) 不改程式，寫進 design「已知技術債與限制」，並在上線目視清單加一項「確認雲端 config.toml 的 showErrorDetails 是否生效」。建議採 (b)：殘餘風險低，(a) 會動到入口的 import 結構。
  影響：只會在部署壞掉時發生，露出的是公開 repo 的程式碼與檔案路徑，不含 secrets 或財務資料。改動前雲端任何錯誤都會露出堆疊，這次已經大幅縮小範圍。
  Checker 對應：checker 未報出

- [INFO] A01 — `rerun_runtime.rerun_fragment`、`views/house.py::_persist_subjective_trigger`（guarded_callback）、側欄「重新讀取資料」的 on_click — 這三個入口都不經過 `_require_access`
  說明：Streamlit 的 widget callback 會在腳本主體之前執行，fragment 單獨重跑也不經過 app.py，所以都不會再跑一次登入守門。已對照 Streamlit 1.66.1 原始碼查證，不構成繞過：callback 和 fragment 都登記在各 session 自己的狀態裡（fragment 從該 session 的 FragmentStorage 查找，查不到就拋 FragmentStorageKeyError），只有守門放行後渲染過這些元件的 session 才觸發得到。st.user 在 session 期間固定，只有 st.login／st.logout 會改變，而這兩者都會開新 session。未登入或非本人的 session 不會渲染這些元件；test_app_guard 的 SC-033／034／108／116 已涵蓋「未登入看不到重新讀取鈕、也不觸發連線檢查」。守門外層包了 error_boundary，任何例外都會跳過後面的組裝與路由，是 fail-closed；`st.stop` 屬於 BaseException，不會被攔下（已查證 StopException 繼承 BaseException）。
  建議：不需修正。之後城市總覽新增 fragment 或 callback 時要沿用同一個前提：只能在守門之後渲染。想加一層縱深防禦的話，可以在 rerun_fragment 內加一行純判定（evaluate_access 加 allowed_emails），屬可選。

- [INFO] A05 — 錯誤細節開關
  說明：只接受 1、true、yes、on 這幾個值，其他一律 none，是失敗安全的設計。`error_details_enabled()` 以設定值等於 "full" 判斷，遇到舊版布林值也當作關閉。全專案沒有用 `st.exception`。各頁與 error_boundary 顯示的 AssetLabError 訊息都是寫給使用者看的固定文字，PersistenceError 不夾帶原始錯誤，已逐一檢查 raise 的位置。Streamlit 會把 Secrets 的頂層鍵匯成環境變數，雲端 Secrets 如果誤設這個鍵，就會打開完整錯誤顯示。design §11 已排入 4-1 README，4-1 必須確實寫進去。

- [INFO] A09 — 新增的 log
  說明：重跑量測那一行只有 kind、page、耗時、往返次數、快取命中、重連、中斷這幾欄；另外兩種是 `event=read_cache_cleared`、`event=reconnected`。都不含 email 或財務數值。未登入的訪客每次重跑也會記一行（page=-、interrupted=true），沒有個資，只是 log 量會隨匿名流量增加，可以接受。`configure_logging` 只設定 asset_lab 命名空間、不動 root，authlib、httpx 等第三方套件的 log 等級沒有被拉高，不會把 OAuth 或連線細節帶進 log。`logger.exception` 把領域錯誤訊息（可能含項目名稱）和堆疊寫進 log，這跟改動前各頁的行為相同，而且雲端 log 只有 app 管理者看得到。

- [INFO] A03／A04／A08 — 讀取快取與整批寫入（`read_cache.py`、`connection_layers.py`、兩個 upsert_* 方法）
  說明：快取是程序級、跨 session 共用，但只在守門之後才會讀取。資料放在記憶體、不序列化（沒有用 st.cache_data 的 pickle），沒有反序列化的攻擊面。快取鍵是「常數 SQL 加上參數 tuple」；新增的 `SELECT 1` 與沿用的 `_UPSERT` 都是常數 SQL 加佔位符，f-string 只代入表名、欄名常數，沒有注入面。commit 成功才清快取、寫入進行中不寫回、用世代擋住競態，設計嚴謹。破壞性的 CSV 匯入，在空庫守門的按鈕上先清快取（AD-4）。月度錄入沿用快取，可能跨程序用舊資料覆蓋，這是使用者已接受的風險（design 技術債 #4），不列為發現。快取沒有容量上限，但只有已授權的本人填得進去，TTL 5 分鐘整批清除，不構成 DoS 面。設定頁改成整批交易寫入，提升了資料完整性。

- [INFO] A07 — 側欄的登出按鈕改到連線確認之前，資料庫故障時仍能登出，屬改善。

### 逐維度結論

| 維度 | 結論 |
|------|------|
| A01 存取控制 | 守門順序不變、fail-closed；callback／fragment 不經守門已查證可接受（INFO） |
| A02 加密 | 連線與 TLS 沒有變動；快取只在記憶體 |
| A03 注入 | 新增的 SQL 都是常數加參數化；無路徑、命令或 HTML 注入面 |
| A04 不安全設計 | 快取一致性設計完整；已接受風險有記錄 |
| A05 設定錯誤 | 錯誤兜底分層合理；LOW 1 項（L1 之前的缺口） |
| A06 有漏洞的元件 | MEDIUM 1 項（filelock，dev 用、不是本次引入） |
| A07 認證 | 登入流程沒有變動；登出的可用性提升 |
| A08 完整性 | 設定頁整批交易；沒有反序列化 |
| A09 log | log 沒有個資或密鑰；錯誤細節只進 log |
| A10 SSRF | 不適用（沒有新增對外請求） |

### 其他觀察（非安全性問題，供 3-3／3-4 參考）

- `rerun_runtime._state.verified` 是 thread-local。如果 callback（例如買房勾選）已經呼叫 `verified_container()`，而在進入 app.py 最外層 scope 之前就被新的重跑請求中斷（ScriptRunner 在 callback 之後會檢查控制請求，同一個執行緒接著跑下一輪），暫存要等下一輪最外層 scope 結束才會清掉，所以下一輪會少探測一次。這只影響可靠性，而且極少發生，不是安全問題。

### 第二段建議修正範圍

- 必修：MEDIUM（升級 filelock，只改 uv.lock，修完重跑 pip-audit 與 pytest）。
- LOW：建議採 (b)，在 design 的已知限制補一列並加入上線目視項目，不改程式；要採 (a) 請使用者決定。
- INFO 項目不需修正；README 的錯誤細節開關警語留給 4-1。

### 第二段修正結果

使用者決定的範圍：MEDIUM 這次修；LOW 採 (b)，不改程式；INFO 不改。

- MEDIUM（A06 filelock）：已修。跑 `uv lock --upgrade-package filelock`，uv.lock 只有 filelock 從 3.29.7 換成 4.2.4（版本、sdist、wheel 三行），其他套件沒變。之後 `uv sync --extra dev` 同步本機環境。
  - 驗證：`pip-audit` 回報 No known vulnerabilities found；`ruff check .` 全過；`pytest tests/` 868 passed。
- LOW（A05 set_option 時機）：沒改程式。design.md「已知技術債與限制」補了第 16 列，上線目視檢查見下方。
- INFO：沒改。

### 上線目視檢查（3-2 LOW 追蹤）

- [ ] **確認雲端在載入階段出錯時不會露出堆疊（L0 `config.toml` 在雲端有效）**
  - 做法：不要動正式 App，也不要合併進 main（main 會自動部署）。
    1. 開一條臨時分支，在 `app.py` 的 import 區塊之後、`main()` 之前，暫時加一行 `raise RuntimeError("load-time probe")`。這一行在讀 secrets 和連資料庫之前就會拋出，所以不用設定 Secrets，也碰不到正式庫。
    2. 用 Community Cloud 從這條分支另外部署一個臨時 App。
    3. 以未登入狀態打開臨時 App 的網址。
  - 預期：畫面只有 Streamlit 的通用錯誤訊息，沒有 Traceback 和檔案路徑；完整錯誤只出現在該 App 的 Manage app → Logs。
  - 收尾：檢查完刪除臨時 App 和臨時分支。
  - 如果畫面出現堆疊，表示雲端蓋掉了 L0。這時要回頭評估方案 (a)：把 `set_option` 提前到專案模組 import 之前，`resolve_error_detail_mode` 搬到不依賴 libsql 的輕量模組。

## 3-3 規則符合度審查

審查範圍：非測試檔 22 個加測試檔 19 個，ac02bbb..HEAD（feature/responsiveness-and-error-fallback）
核准判定：有條件通過（無 CRITICAL、無 HIGH；MEDIUM 2 條、LOW 5 條，第二段建議修 MEDIUM 與 LOW-1、LOW-2）

### 自動掃描

Checker 命令：`python .claude/skills/spec-driven-flow/scripts/checkers/runner.py --phase 3-3 --project-dir . --diff-base ac02bbb --json`
總違規：641 條（CRITICAL: 0 / HIGH: 144 / MEDIUM: 53 / LOW: 444），其中測試檔約 70%；Baseline 命中：0 條
完整報告：`.ai/changes/responsiveness-and-error-fallback/.cache/checker_3_3.json`

逐類復核結論（checker 的 HIGH 全部經人工復核，實質違規 0 條）：

| rule_id | 數量 | 復核結論 |
|---------|-----:|----------|
| `no_stdlib_get_logger`／`event_name_format`／`note_required`／`no_logger_exception` | 16／7／7／4 | 偽陽性（對 RPA 專案模型）。本專案沿用標準 `logging`＋`%s` 與 `logger.exception`，design 的 TD-3、initial-build AD-8 已記錄偏離，base 的 8 個頁面早已如此。見下方「已記錄偏離」 |
| `no_runtime_constants_access`／`service_no_runtime_constants` | 79／12 | 偽陽性為主。Service 內的 `HOUSE_PARAM_KEY`、`PROTOCOL_LEVEL_CODE` 是列舉鍵，base 的 house_service 已同樣取用，本次只是把原本寫在 view 的組列邏輯搬進 Service（方向正確）；`bootstrap`、`app.py` 是組裝根，合法。剩餘兩處降為 LOW，見 LOW-3 |
| `repository_must_have_init` | 3 | 偽陽性：`DbCursor`／`DbConnection` 是 Protocol、`QueryMetricsSnapshot` 是 dataclass，只是放在 repositories 目錄 |
| `root_main_exists`／`src_project_layout_missing` | 2 | 偽陽性：入口是 `app.py`，無 controllers 層，initial-build AD-1 已記錄 |
| `import_block_format` | 14 | 區塊標籤「專案內部」與 base 一致，屬偽陽性；但同批新檔案另有「區塊間缺空行」的真問題（checker 未報出），見 MEDIUM-1 |
| `no_local_import` | 25 | 全在 tests（Streamlit AppTest 函式式腳本必須在函式內 import），src 為 0，不列 |
| `docstring_required`／`docstring_returns_section`／`ANN*` | 181／28／143+… | src 部分見 MEDIUM-2、LOW-1；tests 部分為舊有風格（既有測試同樣無 docstring 與型別），不列 |

### 已記錄偏離（使用者已同意，不列待修）

- 頁面 logger 用 `asset_lab.views.<頁>` 而非 `__name__`（AD-7）
- `app.py` 總覽頁註冊行 `# noqa: E501`（SC-049 測試以 regex 掃單行）
- log level 與格式放 `constants.APP_LOGGING`，專案無 config.yml
- 標準 `logging`、`%s` 與 `logger.exception`、無 structlog／utils_v2、無 main.py／controllers 層（TD-3、initial-build AD-1／AD-8）

### 規則審查發現

- [MEDIUM-1] `connection_layers.py`、`read_cache.py`、`query_metrics.py`、`health_repository.py` — import 三區塊之間沒有空行（`# 無` 後直接接下一個區塊註解）。
  依據：01-coding-style §2 Import 標準（「區塊間留空行」）；其餘新檔（error_boundary、rerun_runtime）與 base 檔案格式正確。
  Checker 對應：checker 未報出（只報了標籤，誤以為是標籤問題）。
- [MEDIUM-2] `house_service.build_param_models`、`protocol_service.build_threshold_models`、`ReadCache` 各公開方法、`QueryMetrics.take`／`total_roundtrips`、`CountingConnection.cursor`、`CachingConnection.cursor` 等 — 有回傳值但 docstring 缺 Returns；兩個 Service 新方法另缺 Args。
  依據：01-coding-style §3 文件規範（public 方法含 Args/Returns）。屬新增程式碼的 docstring 完整度。
  Checker 對應：`docstring_returns_section`（checker 已標，src 22 條，復核成立）。
- [LOW-1] `error_boundary.guarded_callback` 與 `rerun_runtime.rerun_fragment` 的內層 `wrapper(*args, **kwargs)` 無型別提示（參數與回傳）；另新類別的 `__init__`（ReadCache、QueryMetrics、CountingConnection 等）與 Protocol 方法無 docstring。
  依據：01-coding-style §1 型別提示必填、§3 `__init__` 需 docstring。建議 wrapper 標 `*args: object, **kwargs: object`；`__init__` 補一行說明即可。
  Checker 對應：`ANN002`／`ANN003`／`ANN202`（src 部分）、`docstring_required`（src 14 條），checker 已標。
- [LOW-2] `bootstrap.clear_read_cache`、`bootstrap._on_reconnect` 的 log 寫成 `"event=read_cache_cleared"`、`"event=reconnected 連線失效已重連"`：鍵值前綴與中文混在同一則訊息，且與其餘模組（`context=%s`、全中文）風格不一致。標準 logging 下不違反準則，但建議統一成「中文訊息＋必要時 key=value」，例如 `"讀取快取已清除"`、`"連線失效已重連"`。
  依據：04-cross-cutting §1.2 精神（event 命名一致、訊息清楚）；標準 logging 沒有 event/note 契約，故僅 LOW。
  Checker 對應：`event_name_format`、`note_required`（checker 已標，但依 structlog 契約，判定為不適用）。
- [LOW-3] `error_boundary.error_details_enabled` 在函式內比對 `ERROR_DETAILS.SHOW`、`rerun_runtime.rerun_fragment` 內取 `RERUN_KIND.FRAGMENT`：runtime glue 模組自行讀 constants。這兩者是列舉值（非可調參數），而 bootstrap 與 base 的 view 層皆同樣做法，不建議為此改動；記錄即可。
  依據：04-cross-cutting §3.2；專案既有慣例。
  Checker 對應：`no_runtime_constants_access`（checker 已標，判定可接受）。
- [LOW-4] `ReadCache`、`QueryMetrics` 放在 `repositories/` 但不做 I/O，嚴格說不是 Repository（接近「連線層基礎設施」）。design 已把它們歸入連線層、且與計數／快取包裝同目錄便於閱讀，不建議搬動；記錄供日後有第二個基礎設施模組時再評估。
  依據：02-architecture §6 Repository 合約；design AD-6。
  Checker 對應：checker 未報出。

### 無違規確認（重點條目）

- Repository 層：新增 `ConnectionHealthRepository`、`upsert_params`／`upsert_thresholds` 皆有建構子注入、無 catch 後 log error、錯誤直接上拋；`CachingConnection.rollback` 用 try/finally 不吞例外。
- Service 層：新增兩個方法只做驗證與組列，無 I/O、無 `self` 存流程資料，例外原樣上拋。
- DI：所有新類別建構子皆 keyword-only 注入（`inner=`、`cache=`、`metrics=`、`ttl_seconds=`）；`ReadCache` 的 TTL 由 bootstrap 讀 `READ_CACHE.TTL_SECONDS` 後注入，符合 §3.1。
- 錯誤處理：`error_boundary` 是最終 catch 點；`FragmentHandledException` 與 st.stop／st.rerun 控制例外不被攔截；未預期錯誤只顯示通用訊息、細節進 log。
- 機密與 log 安全：log 行不含 email、不含連線字串；環境變數開關只讀不印；`.streamlit/config.toml` 無機密。
- 註解：新增註解皆說明 WHY（例如 noqa 行的 regex 原因、callback 在腳本主體之前執行的理由），無修改歷史式註解。
- `ruff check .` 全數通過。

### 第二段修正結果

- MEDIUM-1：已修 `read_cache.py`、`query_metrics.py`、`health_repository.py` 的區塊空行。`connection_layers.py` 無法同時滿足：加空行後 ruff 的 isort 規則（I001）判違規，與準則衝突時以 `ruff check .` 為準，故維持原樣（`# 無` 後直接接下一區塊註解）。
- MEDIUM-2：已補 Returns／Args（ReadCache、QueryMetrics、CountingConnection／Cursor、CachingConnection／Cursor、兩個 Service 新方法）。
- LOW-1：兩個 wrapper 補 `*args: object, **kwargs: object -> object`；新類別 `__init__` 與 Protocol 方法補 docstring。
- LOW-2：使用者決定不改，`bootstrap` 的 `event=...` log 保留鍵=值格式，理由是和每次重跑的量測行一致、量測時好搜尋。
- LOW-3、LOW-4：只記錄。
- 驗證：`pytest tests/` 868 passed，`ruff check .` 通過。

### thread-local 驗證暫存觀察（3-2「其他觀察」評估）

結論：不違反任何工程準則，維持設計取捨，不改程式。理由：暫存只在「callback 呼叫過 `verified_container()` 且該次執行在進入最外層 scope 前被新請求中斷」時殘留，後果是下一輪少探測一次，由 `error_boundary` 接住並顯示通用訊息，使用者重新操作即恢復；而唯一的修法（在進入 scope 時清暫存）會破壞「callback 與腳本主體共用同一次探測」的設計目的（SC-111）。建議維持 3-2 記錄的「已知限制」。若要降低機率，只能在 `verified_container` 暫存值上加時間戳，屬過度設計，不建議。


## 3-4 行為對映審查

審查範圍：25 個 SC（SC-108～132）× 171 組 (SC, test) 對映（AST 解析 `@pytest.mark.scenario`，涵蓋 test_app_guard、test_bootstrap、test_probe_roundtrips、test_rerun_runtime、test_connection_layers、test_read_cache、test_read_cache_equivalence、test_input_view、test_error_boundary、test_error_details_switch、test_house、test_data_io、test_settings_view、test_protocol_thresholds、test_house_params、test_query_metrics）；25 個 SC 全部至少有一個 test 對映
核准判定：有條件通過（無數值／情境語義錯置；有 6 項斷言強度不足，皆可只改 test 修正；無 SC 本身寫錯）

審查前提（使用者已決定，不列缺口）：SC-120 的「只有編輯器重跑」以結構斷言＋fragment 本體直接執行＋log 間接驗證；SC-110 重連失敗維持通用訊息；scenario_lint 38 個既有孤兒 test 另案。

### 不對齊（斷言強度不足，test 沒有驗證到 SC 寫的結果）

1. SC-120 ↔ tests/test_input_view.py::test_sc120_editor_runs_and_preview_follows_amount_change
   SC 描述：餘額 100,000 改 150,000 後，淨投入預覽「立即依 150,000 更新」
   test 內容：從空白欄位直接填 150000，只斷言畫面出現「推算本月淨投入」字樣與探測次數 3
   判斷：沒有斷言預覽數字隨金額改變（金額從 100,000 變 150,000 時預覽值的差異）；預覽即使沒更新也會綠。建議：先填 100000 取預覽文字，再改 150000，斷言預覽文字含依 150,000 算出的淨投入且與前值不同。

2. SC-121 ↔ tests/test_input_view.py::test_sc121_delete_success_reruns_whole_page_with_flash
   SC 描述：刪除成功後「該列從表格消失」
   test 內容：只斷言 success=「已刪除」與 repo 收到一次刪除呼叫
   判斷：未斷言表格列消失。建議：刪除後 `len(at.dataframe)` 或表格內容不再含該列。

3. SC-121 ↔ tests/test_input_view.py::test_sc121_save_success_reruns_whole_page_with_flash_and_new_table
   SC 描述：存檔後整頁重跑，表格「顯示新值」
   test 內容：斷言 success=「已儲存」、`len(at.dataframe) == 1`、第一行 interrupted=true 且共 ≥2 行
   判斷：表格只驗列數、沒驗新值（400,000）；「整頁」重跑也只靠兩行 log 間接推得（可接受），但新值缺口應補：斷言表格該列市值為 400,000 格式化值。

4. SC-111 ↔ tests/test_house.py::test_sc111_checkbox_writes_via_verified_container_probed_once
   SC 描述：「該輪重跑（勾選處理加上頁面重跑）用於確認連線的往返最多 1 次」；頁面重跑時不再重複確認
   test 內容：直接跑 views/house.py，只驗 callback 內 `verified_container` 探測 1 次、寫入走新容器
   判斷：頁面重跑端（app.py 的 scope 內再呼叫 `verified_container`）不在這個 test 裡，「callback＋頁面合計 1 次」沒有端到端斷言；拼湊證據是 test_rerun_runtime 的 per-execution 暫存測試（單 scope 內）與本 test，缺 callback 在 scope 外先探測、進入 scope 後不再探測的組合測。建議在 test_rerun_runtime 補一個：scope 外呼叫一次、進 scope 再呼叫，`probe` 只被呼叫 1 次。

5. SC-127 ↔ tests/test_error_boundary.py::test_sc127_unexpected_callback_error_shows_generic_message_below_title、tests/test_house.py::test_sc127_unexpected_write_failure_shows_message_and_page_still_renders
   SC 描述：「標題下方」以紅字顯示訊息
   test 內容：兩者都只驗錯誤訊息出現、頁面其餘元素存在（test 註解寫「訊息在標題之後」但沒有任何順序斷言）
   判斷：位置未驗。建議：用 `at.main` 的元素順序（title/subheader 的索引 < error 的索引）斷言。

6. SC-129 ↔ tests/test_settings_view.py::TestBatchSaveFailure::test_sc129_*（threshold／house_param／commit_and_rollback）
   SC 描述：畫面不顯示資料庫原生錯誤或程式堆疊；細節寫入 log；快取不清除時畫面仍顯示原值
   test 內容：驗證庫內原值不變、錯誤文字等於友善訊息；沒有 caplog 斷言「細節進 log」，也沒斷言頁面不含原生錯誤文字（只靠「error 清單恰為友善訊息」間接成立）；快取不清除另由 Repository 層 test_sc129_failed_batch_write_does_not_clear_read_cache 驗證
   判斷：「細節寫入 log」缺斷言，屬部分對齊。建議：在其中一個 view 層 test 加 caplog，斷言 ERROR 紀錄含 exc_info。

### 有疑慮但可接受（建議記錄，不要求修正）

- SC-128 成功案例只驗 stub repo 收到整批與成功訊息，未驗「畫面反映新值」；因驗證／批次路徑已涵蓋，且 stub 不會回讀，列為可接受。
- SC-110 的「重連後仍失敗→畫面只顯示通用訊息」分成兩段驗證：bootstrap 層證明 get_container 恰 2 次不重試第三次，畫面層由 SC-123 app 測試（`get_resilient_container` 拋 RuntimeError）證明通用訊息；沒有「stale→stale」連續到畫面的單一端到端 test，視為組合覆蓋。
- SC-112 的「切頁／切換報酬率下拉」以連線層與快取層單元測試表達（相同查詢第二次 0 往返、不同參數視為不同查詢），未用 AppTest 走頁面；語義對齊。
- SC-131「兩行往返與耗時相加為一次存檔成本」是計算性質，未單獨斷言，由「中斷行＋後續行」兩個 test 間接成立。
- SC-119 計算比對涵蓋淨值、TWR、協定判斷、持有／紀錄；「資產配置」僅經 `net_worth_series`，未對配置占比逐項比對；列可接受。

### 對齊

| SC | test 函式（代表） | 判斷依據 |
|----|------------------|---------|
| SC-108 | test_probe_roundtrips::test_sc108_second_full_rerun…、test_bootstrap::test_sc108_second_resilient_container_call…、test_app_guard::test_sc108_*、test_rerun_runtime::test_sc108_* | 第二輪實測往返恰為 1（SELECT 1）、第一輪 >1、第二次不再 CREATE TABLE；未登入／陌生人不探測 |
| SC-109 | test_bootstrap::test_sc109_stale_probe_reconnects_without_rebuilding_schema_and_logs_warning、test_sc109_reconnect_keeps_read_cache、test_with_reconnect_recovers_from_stale_stream_error | 失效→清連線→新連線只有 SELECT 1、無 CREATE TABLE；WARNING 恰 1 行含「連線失效已重連」；reconnected 旗標；快取保留；重試恰 1 次 |
| SC-110 | test_with_reconnect_gives_up_after_second_consecutive_failure、…non_stale…（×2）、test_rerun_runtime::test_sc110_probe_failure_propagates_and_is_not_cached | get_container 恰 2 次不第三次；非 stale 錯誤不重連；失敗不暫存（畫面訊息見前述組合覆蓋） |
| SC-111 | test_house::test_sc111_checkbox_writes_via_verified_container_probed_once | 勾選寫入走驗證後新容器、舊 repo 無寫入、勾選狀態正確（頁面端合計次數見不對齊 4） |
| SC-112 | test_connection_layers::test_sc112_*、test_read_cache::test_sc112_* | 第二次相同 SELECT 0 往返且結果相同；不同參數視為不同查詢；快取命中計入 metrics |
| SC-113 | test_connection_layers::test_sc113_*（commit 後 100→120、刪除後列消失、整批僅最終 commit 後清）、test_read_cache::test_sc113_* | 120 值與 DELETE 情境與 SC 一致；整批邊界對齊 |
| SC-114 | test_connection_layers::test_sc114_*、test_read_cache::test_sc114_* | commit 失敗／rollback 後快取保留；寫入進行中讀取繞過快取且不存入；在途查詢世代已變不寫回 |
| SC-115 | test_read_cache::test_sc115_*、test_rerun_runtime::test_sc115_entry_at_299_keeps_cache_and_at_300_clears_whole_batch 等 | 299 秒保留、300 秒整批清除；入口只判定一次；同一次執行不逐筆判定；探測失敗不判定 |
| SC-116 | test_app_guard::test_sc116_*、test_bootstrap::test_sc116_* | 資料庫故障時重新讀取與登出仍在側欄；點擊觸發 clear_read_cache；清除後下次讀取來自資料庫；log 恰 1 行；未登入不顯示 |
| SC-117 | test_data_io::test_sc117_import_is_rejected_when_other_connection_has_written、…really_empty | 另一連線寫入後快取記「空」仍被拒絕且資料不被覆蓋；真空庫照常匯入 |
| SC-118 | test_read_cache_equivalence::test_sc118_*（兩個） | 冷快取總覽頁同一 (sql, 參數) 不重複往返、對照組確實重複；BETWEEN 與全部紀錄各自往返；commit 後重新讀取 |
| SC-119 | test_read_cache_equivalence::test_sc119_*、test_connection_layers::test_sc119_*、test_read_cache::test_sc119_* | 冷／熱快取與無快取 snapshot 逐項相等；呼叫端改資料不汙染快取 |
| SC-120 | test_input_view::TestEditorIsFragment（結構斷言×2）、test_rerun_runtime::test_sc120_fragment_*、test_sc131_fragment_run_logs_exactly_one_fragment_line | 依使用者既定間接驗證方式：裝飾器、參數僅 target_ym、fragment 入口先探測、log kind=fragment（預覽數值斷言見不對齊 1） |
| SC-121 | test_input_view::test_sc121_*（存檔 interrupted=true 後再一行）、test_rerun_runtime::test_sc131_st_rerun_inside_fragment_is_not_swallowed_and_marks_interrupted | 中斷行＋後續行順序對齊；rerun 不被吞（表格新值／刪除列見不對齊 2、3） |
| SC-122 | test_input_view::test_sc122_write_failure_inside_fragment_keeps_friendly_message、test_rerun_runtime::test_sc122_* | 友善訊息原文、無 secret 洩漏、細節進 log、repo 無寫入；fragment 內領域／未預期錯誤各自正確 |
| SC-123 | test_error_boundary::test_sc123_*、test_app_guard::TestSc123AppBoundary、test_error_details_switch::test_sc123_config_toml… | 通用訊息不含原始文字、細節進 log、st.stop／BaseException／FragmentHandledException 不被攔；config.toml 預設 none |
| SC-124 | test_error_details_switch::test_sc124_*（九組參數、套用到 Streamlit option、原生設定不能洩漏） | 1／TRUE／" Yes "／on 開、0／false／空／enabled／未設定關，與 SC 逐值一致 |
| SC-125 | test_error_boundary::test_sc125_*、test_app_guard::test_sc125_* | 開啟時原樣拋出（app.exception 1）、不改寫、仍寫 log |
| SC-126 | test_error_boundary::test_sc126_domain_error_keeps_its_own_message（HIDE／SHOW 兩模式） | 領域錯誤顯示原訊息、log 含 exc_info、開關開啟時亦同 |
| SC-127 | test_error_boundary::test_sc127_*、test_house::test_sc127_*（位置斷言見不對齊 5） | 未預期→通用訊息、領域→原訊息、只顯示一次後清除、頁面仍渲染、細節進 log、開關開啟時原樣拋出 |
| SC-128 | test_settings_view::test_sc128_*、test_protocol_thresholds／test_house_params::test_sc128_* | 3 筆／9 筆同一批次、驗證失敗不進寫入、空清單不產生寫入 |
| SC-129 | test_settings_view::TestBatchSaveFailure／KeepsCache、test_protocol_thresholds／test_house_params::test_sc129_* | 第 2 筆失敗三筆維持 10／20／30；第 N 筆（fail_at=4）9 筆維持原值；commit＋rollback 皆失敗仍同一友善訊息；失敗不清快取（log 斷言見不對齊 6） |
| SC-130 | test_rerun_runtime::test_sc130_*、test_query_metrics::test_sc130_* | 恰一行、欄位格式 regex 與數值、巢狀不另記、中斷標示、登入守門停止記一行 interrupted、log 不含 email、畫面無量測字樣、scope 前往返併入 |
| SC-131 | test_rerun_runtime::test_sc131_*、test_input_view::test_sc131_editor_run_is_logged_as_fragment | fragment 一行、kind=fragment、page=月度錄入編輯器；中斷行＋後續行 |
| SC-132 | test_bootstrap::test_sc132_* | logger 名為 asset_lab.views.<檔名>（掃 8 個 views）、stderr handler、INFO 不丟、重複 configure 不重複輸出 |

### 建議第二段修正範圍

只改 test，不改 SC、不改源碼：
1. SC-120：預覽 test 加金額變化前後的預覽值斷言
2. SC-121：刪除 test 加表格列消失；存檔 test 加新值斷言
3. SC-111：test_rerun_runtime 補「scope 外先探測、scope 內不再探測」組合測（及視需要在 house test 補註記）
4. SC-127：兩個 test 補標題在 error 之前的順序斷言
5. SC-129：view 層 test 補 caplog 細節進 log 斷言

### 備註

- review.md 先前整份 3-1／3-2／3-3 重複出現兩次，已去重：後一份是前一份的子集（僅缺 3-3 的「第二段修正結果」），保留前一份，無需併入其他差異。

### 第二段修正結果

6 項不對齊已全部補斷言（只改 test，未改源碼與 SC 卡片）：SC-120 預覽隨 100,000→150,000 變動且差 50,000；SC-121 刪除後表格無列且顯示「本月尚無已存紀錄」、存檔後表格市值為 400,000；SC-111 新增 callback 在 scope 外探測、進 scope 不再探測的組合測；SC-127 兩處以主區元素順序斷言 title < error（買房頁再加 < subheader）；SC-129 兩個 view 層 test 加 caplog，斷言 settings logger 恰一筆 ERROR、含 exc_info 與底層細節。驗證：`pytest tests/` 869 passed，`ruff check .` 通過。核准判定更新為通過。
