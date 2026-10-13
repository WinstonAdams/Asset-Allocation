# Review: [Change 名稱]

## 3-1 程式碼清理

掃描範圍：16 個檔案（src 9、views 1、tests 6），24e13c0...HEAD；`ruff check .` 全綠，vulture 未安裝（跳過）

### 自動掃描

Checker 命令：`python .claude/skills/spec-driven-flow/scripts/checkers/runner.py --phase 3-1 --project-dir . --diff-base 24e13c0 --json ...`
總違規：7 條（皆 duplicate_code / MEDIUM）
Baseline 命中：0 條
完整報告：`.ai/changes/transfer-accumulate-fix/.cache/checker_3_1.json`

逐條復核：
- `cost_basis_service.py:84`（checker 已標）— 為 `derive` 與 `_derive_from_realized_income` 的 keyword-only 簽名行相似，非邏輯重複；判定偽陽性，不處理。
- `tests/test_bootstrap.py:531`（checker 已標）— 舊 schema 的 CREATE TABLE 字串，刻意重現舊庫結構供遷移測試；不處理。
- `tests/test_data_io.py:585/586`（checker 已標）— 匯出 CSV 的測試安排行，與既有測試相似，可讀性優先；不處理。
- `tests/test_input_view.py:612/627/658`（checker 已標）— 每個測試重複建 `_StubRecordRepo()` 等安排；見 SUGGEST。

### SAFE
- 無。未使用 import/變數/函式、debug print、TODO/FIXME、Change 級編號註解（AD-/BR-/SC-）於 src、views 皆未發現（checker 未報出，人工 grep 確認）。`views/input.py` 已移除不再使用的 `HoldingRepository` import，乾淨。

### CAREFUL
- 無。

### RISKY
- 無。

### SUGGEST
- `views/input.py` `_render_cost_basis_editor` — 預覽區已用 try 解析 `total_cost/realized_pnl/cash_dividend`，按下「儲存此列」時又對同三欄重新 `parse_amount` 一次（外加現值）。語意正確（按鈕分支需 raise DataValidationError 由上層 catch，與預覽的吞錯不同），但解析重複；可選擇抽成小 helper。屬可選，非必要，建議不動（避免改變解析失敗時的行為）。
- `views/input.py:137` 本月表格欄名「已實現收益」— 對應存的合計值（已實現損益＋股利），與錄入框已拆成兩格的用詞不同；屬文案/設計決策（design 保留 realized_income 為合計），非清理項，留給 3-3/3-4 判斷。
- `tests/test_input_view.py` 612/627/658 附近 — 重複的 `_StubRecordRepo()` 安排，可抽 fixture/helper；屬測試可讀性優化，效益低，建議不動。
- TDD 殘留：`derive`→`_derive_from_realized_income` 的拆分有「derive 與連動重算共用」的實際第二個呼叫者（`_recalculate_following`），非不必要中間層；結構判斷合理，不需清理。
- 函數大小：`_render_cost_basis_editor` 約 90 行、巢狀 try/else/try/else 達 4 層（未超過 >4）；可接受，如需拆可把預覽區抽成 `_render_derivation_preview`，屬可選。

結論：無需修改的必要清理項；第二段可視主 AI 指示僅做可選的 SUGGEST 項，或直接略過。

## 3-2 安全性審查

<!-- security-reviewer subagent 產出（涉及認證/付款/個資時才執行） -->

## 3-3 規則符合度審查

審查範圍：44 個檔案（src 9、views 1、tests 6、其餘為 .ai 文件），24e13c0...HEAD；`ruff check .` 全綠
核准判定：有條件通過（無 CRITICAL / HIGH 新增違規；僅 MEDIUM / LOW）

### 自動掃描

Checker 命令：`python .claude/skills/spec-driven-flow/scripts/checkers/runner.py --phase 3-3 --project-dir . --diff-base 24e13c0 --json ...`
總違規：189 條（CRITICAL: 0 / HIGH: 8 / MEDIUM: 3 / LOW: 178）
Baseline 命中：0 條（本專案無 baseline 檔，下列 HIGH 皆為既有專案慣例造成）
完整報告：`.ai/changes/transfer-accumulate-fix/.cache/checker_3_3.json`

逐條復核：
- `root_main_exists` / `src_project_layout_missing`（HIGH，checker 已標）— 本專案為 Streamlit 應用（`app.py` + `views/` + `bootstrap.Container`），沒有 controllers/main.py 結構，本 Change 未動結構；偽陽性（專案層級既有架構，非本次變更引入）。
- `repository_no_runtime_constants` / `no_runtime_constants_access`（HIGH，schema_repository.py:171/172，checker 已標）— 新增的 `CASH_DIVIDEND` 加欄遷移，沿用同檔既有 `TOTAL_COST`/`REALIZED_INCOME` 完全相同的 `MONTHLY_RECORDS_TABLE.<COL>` 寫法；該 table/column 為 schema 定義而非 runtime 業務參數，且為專案既有慣例。判定不新增違規；建議於檔內補 `# checker:noqa repository_no_runtime_constants`（`no_runtime_constants_access` 同理）。
- `no_module_level_constants_alias`（HIGH，record_repository.py:55，checker 已標）— 新增 `_CASH_DIVIDEND = MONTHLY_RECORDS_TABLE.CASH_DIVIDEND`，與其上 6 個既有別名同型，用於組 SQL 字串；既有慣例，建議補 `# checker:noqa no_module_level_constants_alias`。
- `no_runtime_constants_access`（HIGH，tests/test_bootstrap.py:548，checker 已標）— 測試內為重建舊 schema 供遷移測試用，非 production 程式；偽陽性。
- `model_naming_convention`（LOW，results.py:199/206，checker 已標）— `RecordEditorPrefill` / `CostBasisEditorPrefill` 非 `XxxModel/XxxResult/EnrichedXxx`。同檔既有 `ProtocolStatus`、`NetInvestmentDerivation` 亦未遵循此慣例，專案既有風格；可接受，見 LOW-1。
- `docstring_returns_section`（MEDIUM，tests 三處，checker 已標）— 皆為測試輔助／fixture，docstring 缺 Returns；見 MEDIUM-1。
- `docstring_required` / `ANN001` / `ANN201` / `ANN202` / `ANN003`（LOW 共 176 條，皆在 tests/，checker 已標）— 測試函式缺 docstring 與型別標註。專案既有測試全面如此（ruff 設定也未啟用 ANN），屬既有慣例；不對本次測試逐條要求，見 LOW-2。

### 規則審查發現
- [MEDIUM-1] `tests/test_input_view.py:54 record_repo`、`tests/test_bootstrap.py:542 _seed_prev_monthly_records_db`、`tests/test_data_io.py:571 _six_column_records_csv_bytes` — fixture/輔助函式有回傳值，docstring 缺 Returns 區塊。
  依據：01-coding-style §文件規範
  Checker 對應：`docstring_returns_section`（checker 已標，復核成立）。修正成本極低，建議第二段補上。
- [LOW-1] `src/asset_lab/models/results.py` `RecordEditorPrefill` / `CostBasisEditorPrefill` / `MonthRecordRow` — 命名不符 `XxxResult` 慣例；但與同檔既有類別一致、且語意清楚。建議不動（或補 noqa）。
  依據：03-data-config §Pydantic Models 命名慣例
  Checker 對應：`model_naming_convention`（部分，MonthRecordRow 未報）
- [LOW-2] 新增測試函式缺 docstring／型別標註。專案既有測試全面如此，非本次新增的特例；不建議在本 Change 清洗。
  依據：01-coding-style §型別提示、文件規範
  Checker 對應：`docstring_required`、`ANN*`（checker 已標）
- [LOW-3] `views/input.py` — widget key 字串（`"record_market_value"`、`"cost_basis_total_cost"` 等）在 `seed_amount_inputs(values=...)` 與 `amount_input(key=...)` 兩處重複寫死，易因改一處漏一處而失去播種效果。屬 UI 內部 key，非業務魔法字串，風險低；可選擇抽成模組常數。
  依據：01-coding-style §魔法字串
  Checker 對應：checker 未報出
- [LOW-4] `src/asset_lab/models/record.py` / `core/constants.py` docstring 以「本功能上線前」描述歷史背景。內容在說明 NULL 語意（WHY），非修改歷史註記，判定不違規，僅記錄。
  依據：01-coding-style §註解原則
  Checker 對應：checker 未報出

人工逐條檢視其餘項目結論（本次 diff 區塊皆符合）：
- 架構分層：新增 `accumulate_net_investments`（多步 I/O、單一交易、失敗 rollback 後原樣拋出、不 log error）屬 Repository compound method，歸屬正確；`build_record_prefill`、`summarize_month`、`build_cost_basis_prefill`、股利非負驗證皆為 Service 純方法、無 I/O；View 僅委派與呈現、唯一 catch 點維持在 `render()`。
- DI：Service 無 constants runtime 存取、無 `self` 存流程資料。
- Model：新增 Pydantic Model 為純資料，無業務邏輯。
- 錯誤處理：Service 以 `DataValidationError` 往上拋，未吞例外、未 log error；Repository 無 catch+log。
- Log：本次未新增 log 呼叫。
- 風格：雙引號、keyword args、Import 分組、docstring（繁中＋Args/Returns/Raises）在 src/views 皆符合；無 Change 編號（AD/BR/SC）註解、無修改歷史註解；`ruff check` 全綠。
- 敏感資料：無寫死密鑰或個資。

### 3-1 交接事項：本月紀錄表欄名「已實現收益」
結論：非規則違規，屬規格層面的文案一致性問題，不阻擋。
- 欄名顯示 `realized_income` 合計，是 design Q2（使用者接受選項 A）與 SC-089 THEN 明文決策（「合計一欄，不拆成兩欄」），實作與規格一致；`tests/test_input_view.py:709` 亦以此欄名斷言。
- 但錄入框已拆為「已實現損益」「現金股利」，同頁面「已實現收益」語意不易自明（使用者可能誤以為只有損益）。建議（需使用者決策，因會動 SC-089 與測試）：欄名改為「已實現收益（損益＋股利）」之類的明示用語，或維持現狀並接受。不屬規則違規，不在第二段強制修正範圍。

### 建議第二段修正範圍
- 必做：MEDIUM-1（三處 docstring 補 Returns）。
- 可選：於 `schema_repository.py`、`record_repository.py` 既有慣例處補 `# checker:noqa` 標記；LOW-3 抽 widget key 常數。
- 不處理：LOW-1/2（既有專案慣例）。

## 3-4 行為對映審查

<!-- scenario-mapper subagent 產出（AI 比對 SC 描述 vs test 內容，分「不對齊」「對齊」兩類）-->
