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

審查範圍：18 個 SC（SC-008/009/031/074/075/076/078/079/082/083/084/085/086/087/088/089/090/091）× 約 120 個 (SC, test) 對映
核准判定：有條件通過（無數值／語義直接矛盾；有 2 項覆蓋缺口、4 項弱對映，皆可在第二段改 test 修正；無 SC 本身寫錯需使用者確認）

### 不對齊

- SC-075 ↔ （無對應 view 層 test）
  SC 描述：「AND 存檔前畫面另外標示前期總成本 250000 是用過渡規則估算的，提醒使用者注意可能與券商實際總成本有落差」
  test 內容：`test_cost_basis.py::test_sc075_...` 只斷言 `previous_total_cost=250000`、`is_transition_estimate is True`、`net_investment=30000`；`views/input.py:355-357` 有實際顯示警語，但 `test_input_view.py` 無任何 test 驗證該警語出現
  判斷：覆蓋缺口（畫面標示 AND 子句未被驗證）。建議在 test_input_view.py 新增 SC-075 test：兩筆舊制列＋初始成本 200000、輸入總成本 280000，斷言畫面出現「前期總成本：250,000」與「過渡期估算」警語

- SC-089 ↔ tests/test_input_view.py::TestTransferAccumulates::test_editor_and_table_reflect_latest_values_after_transfer
  SC 描述：「WHEN ...執行一次涉及『活存』的項目間轉移 THEN 表格立即反映最新的已存紀錄內容」
  test 內容：函式名稱含 table，但只斷言 `record_net_investment`／`record_market_value` 輸入框的值（-100,000／350,000），沒有讀 `at.dataframe`；且僅掛 SC-086/087，未掛 SC-089
  判斷：轉移後本月表格即時更新未被驗證。建議補斷言（`at.dataframe[0]` 活存列淨投入 = -100,000）並加掛 SC-089 marker

- SC-089 ↔ tests/test_input_view.py::TestMonthRecordsTable::test_table_reflects_saved_record_immediately
  SC 描述：「存檔補上『房貸』當月餘額 → 表格立即反映」（原本餘額留空顯示提醒，補後提醒應消失）
  test 內容：從空月份存第一筆（0 列 → 1 列），未驗證「原本有提醒的列被補值後提醒消失」
  判斷：弱對映（只證明新增列可見，沒證明既有未填列被更新）。建議改為先預置市值 None 的列、存檔補值後斷言該列市值已顯示且提醒為空

- SC-088 ↔ tests/test_input_view.py::TestCostBasisPrefillAndDividendFields::test_save_with_blank_cost_and_value_when_no_record_is_rejected
  SC 描述：「在總成本『或』現值留空的狀態下直接存檔 → 拒絕並提示必填」
  test 內容：總成本與現值同時留空（預設狀態），只斷言總成本 value == ""，無法區分單一欄位留空是否也被拒絕
  判斷：弱對映（「或」語意只驗到「兩者皆空」）。建議補 parametrize：僅留空總成本、僅留空現值各一組（另一欄填值）皆被拒絕

- SC-086 ↔ tests/test_input_view.py::TestSelectedMonthPassedDownstream::test_transfer_button_passes_selected_year_month
  SC 描述：SC-086 為「轉移累加且保留市值」
  test 內容：驗證的是下拉年月 2025-07 正確傳給 build_transfer_pair，僅附帶 `len(accumulated) == 2`；與累加／保留市值無直接關係
  判斷：marker 掛得牽強（年月傳遞屬 UI 機制，無 SC）；建議移除 SC-086 marker（SC-086 已由 `test_transfer_uses_accumulate_not_overwrite_upsert` 與 repo 層 TestAccumulateNetInvestments 完整覆蓋）。此為 marker 精確度問題，不影響行為覆蓋

- SC-090 ↔ tests/test_input_view.py::TestCostBasisPrefillAndDividendFields::test_transfer_hint_shown_next_to_realized_fields
  SC 描述：SC-090 只寫兩欄相加、推算淨投入、分開落地，未提及「項目間轉移／重複計入」提示文字
  test 內容：斷言 caption 含「項目間轉移」「重複計入」
  判斷：test 驗證的是 proposal BR-7（提示）而非 SC-090 任何 GIVEN/WHEN/THEN。屬 SC 缺漏而非 test 錯：建議在 SC-090 補一條 AND（畫面在已實現欄位旁提示：賣股款若已用項目間轉移記入請勿重複計入），或改掛無 SC 的說明。**SC 變更需使用者確認，不擅自改**

### 對齊但數值與 SC 範例不同（僅供參考，不需修正）

- SC-074 ↔ test_input_view.py::test_preview_shows_previous_total_cost_and_derived_investment：SC 範例為總成本 350000 → 淨投入 50000；此 view test 用總成本 0 → 前期 300000、淨投入 -300000。同一公式的委派線路測試，數學一致；SC 範例數值已由 `test_save_button_delegates_to_plan_save_then_batch_upsert`（350000/400000 → 50000）與 service 層 test 覆蓋。
- SC-090 ↔ test_input_view.py::test_two_fields_sum_into_preview_and_saved_record：view test 以初始成本 300000 無前期紀錄 → -402000；SC 範例為前期總成本 200000 → -302000。service 層 `test_sc090_*` 數值與 SC 完全一致（-302000、合計 102000、股利 2000 分開），view test 為同公式委派驗證。
- SC-084（6 欄 CSV）：`test_sc084_six_column_csv_imports_with_cash_dividend_none` 未斷言 `net_investment` 依原值還原（SC 寫「市值、淨投入、總成本、已實現收益依原值還原」）；其餘斷言（市值 510000、總成本 300000、已實現收益 8000 全保留、股利 None）對齊。建議順手補一行 `records[0].net_investment == 0.0`。
- SC-082：SC 的「嘗試存檔 → 拒絕並提示帶欄位名稱、不落庫」被分拆為 `test_core_utils.py::TestParseAmount`（1,00,000／abc／空字串／空白／None／欄位名稱／0 合法）＋ `test_amount_widget.py`（widget 層原樣保留文字，供存檔時拒絕）；兩層合起來對齊 SC，view 層無端到端「輸入 1,00,000 按存檔被擋」的 test，但已有 SC-087/088 的空白拒絕端到端覆蓋，視為可接受。
- SC-083：只以玩具頁面驗證樣式選擇器前綴命中 `amount_input` 容器、字級／高度 > 1rem、非金額 `text_input` 不被包入；SC 列舉的金額欄位（含新增「現金股利」）是否皆走 `amount_input` 由 `views/input.py:281-284、386` 的實作保證，無 view 層斷言。可接受。

### 對齊

| SC | test 函式（代表） | 判斷依據 |
|----|------------------|---------|
| SC-008 | test_monthly_input.py::TestBuildTransferPair（4 個 test） | 來源 -50000／目標 +50000、同月、金額相等方向相反、市值留空 |
| SC-009 | TestPrefillSoldExclusion、TestSaleMonthClearoutPersisted、test_sc005_sold_item_not_carried | 賣出月市值 0／淨投入 -530000 落地並進入 read_range；次月不帶入已出清項目 |
| SC-031 | test_data_io.py::TestExportImportRoundTrip（6 個 test） | 匯出表頭含 total_cost／realized_income／cash_dividend 七欄；round-trip 還原與匯出前一致（含 1200 股利） |
| SC-074 | test_cost_basis.py::TestDeriveHappyPath／TestUsesCostBasis／TestPlanSaveDeletePlanValidation／TestRealizedPnlAndCashDividendSplit；test_input_view.py 預覽／儲存／欄位切換 | 初始成本 300000 作前期、後續取前一筆 350000、淨投入 50000；負損益加回；兩欄相加；儲存落地現值 400000／淨投入 50000 |
| SC-075 | test_cost_basis.py::TestDeriveTransitionEstimate | 前期 250000＝200000+30000+20000、is_transition_estimate、淨投入 30000（畫面標示見上方缺口） |
| SC-076 | TestDeriveLiquidation | 前期 350000、賣出實收 400000（損益 50000、股利 0）→ 淨投入 -400000 |
| SC-078 | TestPlanDeleteAcrossTransitionRecords、test_sc078_recalculation_uses_stored_realized_income_total | 刪 2026-01 只重算 2026-03（集合僅含 2026-03、值 25000）；已存合計直接用於重算 |
| SC-079 | TestTransferRecordsToWrite 三個 test；view test_transfer_involving_stock_end_writes_only_non_stock_leg | 股票端不寫、非股票端 -80000／+50000 保留；View 只累加非股票端 |
| SC-082 | test_core_utils.py::TestParseAmount；test_amount_widget.py 無法解析輸入測試 | 1,00,000／abc／空字串皆拒絕、訊息帶欄位名（見參考說明） |
| SC-083 | test_amount_widget.py::TestInjectAmountInputStyleTargetsAmountFieldsOnly | 放大樣式命中金額欄、非金額欄不受影響 |
| SC-084 | test_data_io.py::TestLegacyRecords...（6 個 test） | 4 欄／6 欄舊 CSV 匯入成功、新欄位 None、舊已實現收益 8000 全保留不拆股利 |
| SC-085 | TestBatchWriteRollbackOnFailure、test_sc085_accumulate_failure_rolls_back_all_writes | 注入第 N 次 execute 失敗，整批回滾；原錯誤 RuntimeError 原樣拋出；刪除＋upsert 失敗還原被刪列 |
| SC-086 | TestAccumulateNetInvestments（repo 層 7 個）、view test_transfer_uses_accumulate_not_overwrite_upsert | 市值 350000 不變、-100000 → -150000 累加、先轉移後補市值結果相同、不覆蓋 |
| SC-087 | TestBuildRecordPrefill、TestSeedAmountInputs、TestRecordEditorPrefill | 既有值帶入 350,000／-150,000、不改直接存檔不變、無紀錄市值留空淨投入 0、留空存檔被拒、切換跟著換、未切換不洗掉輸入 |
| SC-088 | TestBuildCostBasisPrefill、view TestCostBasisPrefillAndDividendFields | 四欄分開帶回 10,000／1,500（不顯示合計）、無紀錄總成本／現值留空、損益／股利預設 0 |
| SC-089 | TestSummarizeMonth（3 個）、view 表格 test | 逐列名稱／市值／淨投入／總成本／合計已實現收益、市值空白（含負債）才提醒、市值 0 不提醒、空狀態 |
| SC-090 | test_cost_basis.py::test_sc090_*（數值與 SC 完全一致）、view 兩欄相加 test | 100000+2000 → 淨投入 -302000、plan_save 落地 realized_income 102000／cash_dividend 2000 分開 |
| SC-091 | test_cost_basis.py::test_sc091_*、view test_negative_dividend_rejected_in_preview_and_on_save／test_zero_dividend_and_negative_pnl_are_valid | 股利 -1000 於 derive／plan_save 拋 DataValidationError（訊息含「現金股利」）；預覽顯示拒絕原因且無佔位提示；存檔不落庫；0 股利＋負損益合法 |

### 其他觀察

- `python .claude/skills/spec-driven-flow/scripts/scenario_lint.py --project-dir 資產管理` 結果 FAIL，列出的皆為既有無 marker 技術債孤兒測試（如 test_core_utils.py 的年月工具函式），依派工說明不屬本 Change；本審查範圍內 18 張 SC 皆有 marker 對映。
- 本次比對 SC 修訂卡（SC-008/009/031/074/075/076/078/079/082/083/084/085）時，未發現 test 仍殘留舊語意（例如仍把已實現收益當單一輸入欄位）的情形。

### 需使用者確認

- SC-090：是否要把 BR-7「賣股款若已用項目間轉移記入請勿重複計入」提示補進 SC-090 作為 AND 子句（目前 test 有驗、SC 無寫）。其餘不對齊項皆為 test 側修正，無 SC 寫錯的情形。
