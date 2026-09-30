# Review: stock-total-cost-input

## 3-1 程式碼清理

掃描範圍：21 個程式碼檔案（另有 .ai/changes 規格文件不計入），3eba2a3..0d52253（`main...HEAD`）

### 自動掃描

Checker 命令：`python .claude/skills/spec-driven-flow/scripts/checkers/runner.py --phase 3-1 --project-dir <資產管理> --diff-base main --json --output .cache/checker_3_1.json`
總違規：82 條（change_level_id_comments 7、function_too_large 3、file_too_long 1、duplicate_code 71）
Baseline 命中：0 條
完整報告：`.ai/changes/stock-total-cost-input/.cache/checker_3_1.json`

逐條復核結論：

- `change_level_id_comments`（7 條 checker 已標）：全數確認為真陽性，已併入下方 SAFE。人工掃描另外找出 checker 未報出的 4 處（docstring 內的 BR-9/BR-10/AD-7/task-ID 引用，checker 規則似乎只掃 `#` inline comment、不掃 docstring 內文），一併列入 SAFE。
- `function_too_large`（3 條 checker 已標）：逐條復核見下方 SUGGEST，判定為文件完整（docstring 佔比高）而非邏輯真的過度複雜，不建議在本輪清理中拆分。
- `file_too_long`（1 條 checker 已標，`tests/test_cost_basis.py` 542 行）：復核後判定為 false positive——對照本檔案既有測試檔行數（`test_house.py` 1063 行、`test_return.py` 825 行、`test_monthly_input.py` 778 行、`test_bootstrap.py` 733 行皆遠超 500 行門檻），500 行並非本專案實際遵守的門檻，拆分本檔反而打破現有慣例，不建議動作。
- `duplicate_code`（71 條 checker 已標，集中在 6 個檔案）：逐檔複核見下方 SUGGEST，結論為既有測試建構子模式（`_holding`/`_record`/`_asset` 等 factory helper 已用於消解重複）與參數化案例的必然重複，非本次引入的可清理重複，不建議清理。唯一落在生產碼的一處（`record_repository.py` 194/208）已個別評估，見 SUGGEST。

### SAFE

Change 級編號註解／docstring 引用（AD-N／BR-N／task-tN，歸檔後成 dead reference）。統一原則：保留 `@pytest.mark.scenario("SC-XXX")` marker 與 docstring 內對 SC-XXX 的描述性引用（此為本專案既有、跨多個 test 檔案沿用的 SSOT 慣例，見 `test_net_worth.py`/`test_return.py`/`test_monthly_input.py` 既有孤例，非本次引入，不清理）；只移除 AD-N／BR-N／task-tN 這類 Change 內部規劃文件的編號引用，改寫為單純描述行為/意圖的文字。

- `app.py:86` — inline comment 引用「BR-10」：改寫為純粹說明「為何在此處呼叫一次」的 WHY 註解，去掉編號（checker 已標）
- `src/asset_lab/amount_widget.py:1` — module docstring 引用「BR-9/BR-10」（checker 未報出，docstring 非 inline comment）
- `src/asset_lab/amount_widget.py:27` — inline comment 引用「BR-10」（checker 已標）
- `src/asset_lab/amount_widget.py:89` — `inject_amount_input_style` docstring 引用「BR-10」（checker 未報出）
- `tests/test_amount_widget.py:1-23` — module docstring 內 4 處引用需清理：L5「task t06 切片理由」、L13「BR-9」、L17「AD-7」、L22「t05（tests/test_core_utils.py）」；保留 L1/L8/L13/L18 對 SC-083/SC-081/SC-082 的描述性引用（checker 只標到本檔 L107/108/206，docstring 部分未報出）
- `tests/test_amount_widget.py:107-108` — inline comment 引用「AD-7」與「t09」：改寫為純技術說明，去掉編號與 task 引用（checker 已標）
- `tests/test_amount_widget.py:136` — class docstring 內「t05 的 tests/test_core_utils.py」：去掉「t05 的」，保留檔案路徑本身的描述性文字（checker 未報出）
- `tests/test_amount_widget.py:206` — inline comment（checker 已標，內容為 SC-083 描述性引用，複核後判定不含 AD/BR/task 編號，維持原樣不動；checker 疑似對含「SC-083」字樣的行整段誤判，建議 checker 規則未來排除純 SC- 引用）
- `tests/test_monthly_input.py:516-517` — inline comment 引用「design.md AD-3/AD-5」：改寫為純粹說明這些方法用途的 WHY 註解，去掉編號（checker 已標）
- `tests/test_monthly_input.py:575` — `TestUpsertRecordsBatch` docstring 引用「AD-5」（checker 未報出）
- `tests/test_monthly_input.py:631` — `TestDeleteRecordAndUpsertBatch` docstring 引用「AD-5」（checker 未報出）

### CAREFUL

（無）本次掃描未發現動態引用／反射風險相關的候選。

### RISKY

（無）本次掃描未發現需要「不建議自行移除、需使用者裁決」等級的項目。

### SUGGEST

- `src/asset_lab/services/cost_basis_service.py:40` — `derive` 共 58 行超過 50 行上限（checker 已標，MEDIUM）。復核：本體邏輯（前期總成本判斷＋推算）約 28 行，其餘為完整 docstring（Args/Returns/Raises，依 01-coding-style.md 規範必填）。此為本 Change 核心財務推算公式（t02 切片理由標註為「後續連動重算與轉移過濾共同依賴的核心公式」），建議暫不拆分——若要拆，應留待有專門重構任務與獨立測試覆蓋時再進行，本輪清理不動業務邏輯結構。
- `src/asset_lab/services/cost_basis_service.py:99` — `plan_save` 共 55 行超過 50 行上限（checker 已標，MEDIUM）。同上，docstring 占比高，且屬 AD-4「風險最高邏輯」範圍（task t03 切片理由），不建議本輪拆分。
- `views/input.py:176` — `_render_cost_basis_editor` 共 61 行超過 50 行上限（checker 已標，MEDIUM）。此為 UI 渲染函式，可考慮拆成「預覽渲染」＋「儲存/刪除處理」兩個子函式以降低行數，風險低於上述兩個 Service 方法；但目前結構清楚（預覽區塊／儲存區塊／刪除區塊依序排列，無深層巢狀），是否拆分留給主 AI 判斷是否值得在本輪執行。
- `src/asset_lab/repositories/record_repository.py:194,208` — `upsert_records` 與 `delete_record_and_upsert` 共用「逐筆 `cursor.execute(_UPSERT, _values(record))` ＋ try/except rollback/commit」的交易骨架（checker duplicate_code 已標）。可考慮抽出 `_transaction()` context manager 收斂 try/rollback/commit 樣板，但只有 2 處重複、每處只差開頭的 1 行語句，抽象後省下的行數有限、且會改變 Repository 層的控制流形狀；風險與效益不對等，建議維持現狀，不在本輪清理。
- `tests/test_cost_basis.py`（542 行，checker file_too_long 已標）、`tests/test_bootstrap.py`／`tests/test_cost_basis.py`／`tests/test_data_io.py`／`tests/test_input_view.py`／`tests/test_monthly_input.py` 內共 71 條 `duplicate_code`（checker 已標）：逐檔複核後皆為測試資料建構的必然重複（既有 `_holding`/`_record`/`_asset`/`_prev_record` 等 factory helper 已用於消解重複，剩餘重複是每個 scenario 需要不同的具體資料值，例如 `tests/test_cost_basis.py:114-186` 各 test 方法內的 `_record(...)` 呼叫序列）或既有慣例（`tests/test_bootstrap.py` 內 `libsql.connect(":memory:")` 起手式在本檔案已重複 8 次，其中 3 次為本次新增、5 次為既有，非本次引入的模式）。不建議清理，強行抽出共用 fixture 會犧牲各 test 獨立可讀性。


## 3-2 安全性審查

<!-- security-reviewer subagent 產出（涉及認證/付款/個資時才執行） -->

## 3-3 規則符合度審查

<!-- rules-reviewer subagent 產出（工程準則全面符合度檢查）-->

## 3-4 行為對映審查

<!-- scenario-mapper subagent 產出（AI 比對 SC 描述 vs test 內容，分「不對齊」「對齊」兩類）-->
