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

<!-- security-reviewer subagent 產出（涉及認證/付款/個資時才執行） -->

## 3-3 規則符合度審查

<!-- rules-reviewer subagent 產出（工程準則全面符合度檢查）-->

## 3-4 行為對映審查

<!-- scenario-mapper subagent 產出（AI 比對 SC 描述 vs test 內容，分「不對齊」「對齊」兩類）-->
