# Review: [Change 名稱]

## 3-1 程式碼清理

掃描範圍：26 個檔案（src 15 / views 3 / tests 8，不含 .ai），68ed557..df8447c

### 自動掃描

Checker 命令：`python .claude/skills/spec-driven-flow/scripts/checkers/runner.py --phase 3-1 --project-dir . --diff-base 68ed557 --json --output .ai/changes/simplify-non-stock-input/.cache/checker_3_1.json`
總違規：47 條（change_level_id_comments 6、function_too_large 3、file_too_long 2、duplicate_code 36 行級命中，合併後 7 處）
Baseline 命中：0 條
完整報告：`.ai/changes/simplify-non-stock-input/.cache/checker_3_1.json`

靜態工具：`ruff check .` 全過；vulture 未安裝，改以腳本檢查本次新增的所有 def 是否有 src/views 內的呼叫點，全部都有，無未使用的新增函式。src/views 的 diff 中無遺留 print / TODO / FIXME / Change 級編號註解。

### SAFE
- `tests/test_balance_input.py` L85/178/226/346/366 — `# === SC-092：... ===` 等 5 條區段註解引用 SC 編號（checker 已標，復核屬實）。建議改成只留業務描述（如 `# === 餘額推算 ===`），去掉 SC 編號。
- `tests/test_cost_basis.py` L698 — `# ==== 保險：...（SC-095~099） ====`（checker 已標，復核屬實）。同上，去掉括號內編號。
- `uses_premium`（`src/asset_lab/services/cost_basis_service.py`）— 評估：保留。它與既有 public 的 `uses_cost_basis` 對稱，有兩個內部呼叫點（`_ensure_uses_premium`、`_ensure_uses_cost_chain`），不是 dead code；`views/` 沒有呼叫（View 走 `resolve_input_mode`），所以可考慮降為 private。但降為 private 會與 `uses_cost_basis` 不對稱，且 tests 已有直接測試，建議保留 public，並在 design 的 public 介面清單補記（design 未列的這一點屬文件落差，不是程式問題）。

### CAREFUL
- `src/asset_lab/bootstrap.py` L47 / `tests/test_bootstrap.py` L53、`tests/test_input_view.py` L24 / `tests/test_monthly_input.py` L9 — checker 報 duplicate_code，復核為 import 區塊相似，偽陽性，不處理。
- `src/asset_lab/services/balance_input_service.py` L29/59/99 — checker 報 `derive` / `plan_save` / `plan_delete` 簽名區塊重複。復核為 keyword-only 參數簽名相似，偽陽性，不處理。
- `tests/test_cost_basis.py` L939~1010 — 兩個保險測試各自內聯相同的 records 準備（`_premium_record` 組合與 `plan_save_premium` 呼叫），checker 已標。可抽成 fixture/helper，但是測試內聯讓每個 SC 情境獨立可讀，抽出有可讀性代價；列為選擇性，需動測試檔，建議本輪不動，若要動僅限抽 records 準備。
- `views/input.py` L394 / L467 — `_render_save_delete(...)` 呼叫的 `plan_delete=lambda: cost_basis_service.plan_delete(...)` 在股票與保險編輯器重複（checker 已標）。兩處引數完全相同，屬 3 行呼叫樣板，保險與股票共用同一個累計成本鏈刪除；抽出收益極小，且兩個編輯器各自保持完整流程較易閱讀，不建議處理。
- `tests/test_input_view.py` 1054 行、`src/asset_lab/services/cost_basis_service.py` 502 行（checker file_too_long，LOW）— 前者是 AppTest 整合測試累積（本次 diff 為重寫該檔），後者只超 2 行。見 SUGGEST。

### RISKY
- `src/asset_lab/repositories/csv_import_writer.py::write_import` — 評估：可接受，建議保留現況，交 3-3 規則審查做最終判定。理由：它是無業務邏輯、僅在單一交易內依序呼叫三個 Repository 的 `*_with_context` 方法，符合 02-architecture §6「Compound method 合法」與 §9（Repository 方法在外部給定的交易 context 內執行、不自行 commit）；沒有反向呼叫 Service，函式命名有業務語意。與 design AD-10 文字的落差：design 寫「由 Page 持有交易 context」，實作改成由這個 module 函式持有 `with` 區塊，Page（`views/data_io.py`）只負責呼叫並 catch `PersistenceError`。這讓 Page 少接觸交易細節，是正向偏離。需使用者判斷的只有一點：是否接受 design 文字與實作不一致（建議做法：接受實作，補一句 design 註記；若堅持 design 原意，則要把 `with` 搬回 View，不建議，因為會讓 View 直接持有三個 Repository 與 transaction，更難測）。檔案放在 `repositories/` 但為模組級函式而非 Repository 類別，與「Repository 為類別」的慣例不同，也留給 3-3 判斷。

### SUGGEST
- `src/asset_lab/services/cost_basis_service.py::plan_save_premium`（54 行，checker 已標）— 超 50 行上限，但其中 docstring 佔 20 行，邏輯本體約 25 行，且與 `plan_save` 結構對稱。判定為偽陽性，不建議拆。
- `views/input.py::_render_premium_editor`（71 行）、`_render_balance_editor`（56 行）（checker 已標）— 各編輯器的流程為 seed、輸入框、parse/derive、預覽、存檔刪除，結構與既有 `_render_cost_basis_editor` 一致。可把 `plan_save` + `_render_save_delete` 收尾區塊抽成共用小函式，但每個編輯器參數不同，抽出後需傳入大量閉包，收益不明確。建議保持現況；若要處理，優先把 `_render_premium_editor` 的 widget 渲染與 seed 抽成 `_render_premium_inputs`。屬風格取捨，不是缺陷，留給使用者決定。
- `cost_basis_service.py` 502 行 — 只超標 2 行，不建議為此拆檔；之後若再新增分類才考慮把保險相關方法拆成獨立 mixin/Service（design 已選擇保險併入累計成本鏈，拆開會違背 AD-2/AD-4）。
- `tests/test_input_view.py` 1054 行 — 可依錄入方式（股票/保險/餘額/應繳/轉移移除）拆成多檔，但屬測試組織重構，超出本次清理範圍，建議另案。

### 建議第二段修正範圍
僅 SAFE 兩項（共 6 行註解，去掉 SC 編號）。其餘不動。
### 修正結果

使用者決定範圍：只修 6 行測試註解，風格題一律不動，design 落差接受實作（另請 designer 補記）。
- `tests/test_balance_input.py` 5 條區段註解去掉 SC 編號，保留業務描述。
- `tests/test_cost_basis.py` L698 去掉「（SC-095~099）」。
- 驗證：`ruff check .` 全過；`pytest tests` 685 passed。


## 3-2 安全性審查

<!-- security-reviewer subagent 產出（涉及認證/付款/個資時才執行） -->

## 3-3 規則符合度審查

<!-- rules-reviewer subagent 產出（工程準則全面符合度檢查）-->

## 3-4 行為對映審查

<!-- scenario-mapper subagent 產出（AI 比對 SC 描述 vs test 內容，分「不對齊」「對齊」兩類）-->
