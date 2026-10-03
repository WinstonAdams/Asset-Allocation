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

審查範圍：20 個生產／測試程式碼檔案（另有 .ai/changes 規格文件與新增 scenarios 不計入），`main...HEAD`
核准判定：**通過**

### 自動掃描

Checker 命令：`python .claude/skills/spec-driven-flow/scripts/checkers/runner.py --phase 3-3 --project-dir <資產管理> --diff-base main --json --output .ai/changes/stock-total-cost-input/.cache/checker_3_3.json`
總違規：282 條（CRITICAL: 0 / HIGH: 49 / MEDIUM: 12 / LOW: 221）
Baseline 命中：0 條
完整報告：`.ai/changes/stock-total-cost-input/.cache/checker_3_3.json`

逐條復核結論（按 rule_id 分組；本專案為 Streamlit Web App，無 `main.py`／`utils_v2`，已在 `.ai/archive/initial-build/design.md` AD-1/AD-8 記錄為既定 ADR 偏離，且前兩個 Change 的 3-3 審查已對多個 rule_id 建立「既有架構慣例、不違規」的判例）：

- **`root_main_exists`（1，HIGH，checker 已標）／`src_project_layout_missing`（1，HIGH，checker 已標）**：判定**不違規**。專案根目錄無 `main.py`、無 `controllers/` 目錄是本專案自 greenfield 起即記錄的 ADR 偏離（`initial-build/design.md` AD-1：以 `app.py` + Streamlit 多頁模型取代 RPA `main.py`；View/Page 身兼 Controller 角色），非本次改動觸及的檔案或結構，屬全 repo 結構性檢查、與本 diff 無關。
- **`import_block_format`（5，HIGH，checker 已標：`amount_widget.py`、`cost_basis_service.py`、`test_amount_widget.py`、`test_cost_basis.py`、`test_input_view.py`）**：判定**不違規**。checker 要求第三區塊標頭為 `# ==== AsiaYo 專案內部 ====`，但已核對本專案全部既有檔案（`bootstrap.py`、`core/constants.py`、`repositories/*.py`、`models/*.py` 等約 20 個既有檔案）一律使用 `# ==== 專案內部 ====`（不含「AsiaYo」——本專案非 AsiaYo 專案），此 5 個新增/修改檔案完全遵循此既有專案慣例。checker 的字面比對未適配此專案，非本次新增偏離。
- **`no_runtime_constants_access`（31）／`repository_no_runtime_constants`（6）／`service_no_runtime_constants`（1）／`no_module_level_constants_alias`（4）— 共 42 條，皆 HIGH，checker 已標**：逐條核對後判定**不違規**，理由分三類：
  1. `schema_repository.py:147/148/153/154/159/160`（`HOLDINGS_TABLE`/`MONTHLY_RECORDS_TABLE`）、`record_repository.py:51/52`（`_TOTAL_COST`/`_REALIZED_INCOME` 模組級別名）：與既有 `_ensure_holdings_purpose_column`／`_TABLE`/`_HOLDING_ID` 等既有欄位別名寫法同構，只是把既有「加欄遷移」與「SQL 組字串」模式套用到本次新增的 `total_cost`/`realized_income` 兩欄，非新架構模式。此 rule_id 家族已在 `house-dashboard/review.md` §3-3 明確判例：「既有架構慣例，非本 Change 新增偏離」（表名為全域固定常數、無 `--env` 多環境、SQL 模板須在模組級組裝）。
  2. `bootstrap.py:158`（`COST_BASIS_INPUT.CATEGORIES`）：`bootstrap.build_container()` 正是本專案的 DI 組裝根（`main.py` 對應角色，AD-1 已載明），在組裝時讀取 constants 後以 `cost_basis_categories=` keyword arg 注入 `CostBasisService` 建構子，完全符合 04-cross-cutting §3.1「Runtime 配置值一律由 main.py 讀取後透過建構子注入」的正確寫法，checker 誤判為「違規存取」是因為它未辨識 `bootstrap.py` 是本專案的組裝根。
  3. `views/settings.py:162/235`（`HOLDING_KIND.ASSET`）、`data_io_service.py:120`（`CSV_EXPORT.RECORDS_REQUIRED_COLUMNS`）、以及全部 tests/ 內命中（`test_bootstrap.py`／`test_cost_basis.py`／`test_input_view.py`／`test_monthly_input.py`）：View 層對 `HOLDING_KIND` 的判斷式為本次 diff 前後皆存在的未改動行（僅因鄰近新增程式碼而行號位移）；`data_io_service.py` 沿用既有 `CSV_EXPORT.HOLDINGS_REQUIRED_COLUMNS`/`TARGETS_COLUMNS` 同一方法內同構寫法，只是新增 `RECORDS_REQUIRED_COLUMNS` 一行；tests/ 命中皆為測試替身/fixture 建構直接引用 constants，非 runtime 環境差異值。三者皆與 `house-dashboard/review.md` §3-3 判例（views/settings.py、data_io_service.py、tests/ fixture 命中同款）一致。
- **checker 未標，人工掃描亦未發現新增的 DI／分層違規**：`CostBasisService` 全部 public 方法皆為純運算（無 I/O、無 Streamlit import）、建構子注入 `cost_basis_categories`（keyword-only）；`RecordRepository.upsert_records`/`delete_record_and_upsert` 為 compound method（多步 I/O 間無業務判斷，失敗 rollback 後原樣往上拋，不 log error），符合 02-architecture §6；`views/input.py`/`views/settings.py` 的新增程式碼皆為委派＋呈現，無資料篩選/轉換邏輯滯留於 View 層。

- **`docstring_required`（85）／`ANN201`（81）／`ANN001`（40）／`ANN202`（12）／`ANN002`（1）／`ANN003`（1）— 共 220 條，皆 LOW，checker 已標**：逐條核對後判定**不違規**（除下方一條建議項）。本專案 `pyproject.toml` 的 `[tool.ruff.lint] select = ["E", "F", "I", "UP", "B"]` 刻意不含 `ANN`/`D` 系列規則（`ruff check .` 已全過，複驗仍全過），220 條命中全數落在 tests/ 檔案的 `test_*` 方法或底線開頭的私有 helper 函式，與既有未觸及測試檔（如 `test_house.py` 的 `_record()` 無 docstring、`test_sc062_...(self, service):` 無回傳型別提示）呈現完全一致的既有測試慣例（描述性測試命名＋class/module docstring 取代逐方法 docstring，測試方法不加回傳型別提示）。非本次新增偏離。
  - 例外：`tests/test_monthly_input.py:687` `_FailingCursor.execute(self, *args, **kwargs)` 缺 `*args`/`**kwargs` 型別提示（`ANN002`/`ANN003`）。本專案內其實有更佳先例——`tests/test_page_config.py:46` 的同類 stub 建構子寫成 `def __init__(self, *args: object, **kwargs: object) -> None:`。**[LOW，已於第二段修正]**：比照該先例補上 `object` 型別提示（使用者決策：僅修此條；`record_repository.py:141` 的 Returns 區塊一致性建議留待未來不動）。
- **`docstring_returns_section`（12，MEDIUM，checker 已標）**：逐條核對後判定**不違規**。11 條落在 tests/ 私有 helper（`test_amount_widget.py`/`test_bootstrap.py`/`test_cost_basis.py`/`test_data_io.py`/`test_input_view.py` 的 `_run_single_field`/`_style_body`/`_holding`/`_record` 等），與既有測試檔同類 helper（如 `test_house.py::_record()` 完全無 docstring）呈現一致的既有慣例，非新增偏離；1 條在生產碼 `record_repository.py:141`（`read_holding_records`），其單行摘要式 docstring 與同檔案內三個既有手足方法 `read_month`/`read_range`/`read_all`（皆未改動、同樣只有單行摘要、無 Args/Returns）完全同構，是延續本檔既有寫法而非本次新增的降規格。**[LOW，建議可選**：若未來要補齊 Returns 區塊，應與 `read_month`/`read_range`/`read_all` 一併處理以維持檔案內一致性，非本 Change 範圍。
- **`model_naming_convention`（1，LOW，checker 已標：`models/results.py::NetInvestmentDerivation`）**：判定**不違規**。03-data-config.md §3 的「結果 Model 用 XxxResult」為慣例建議，但同一檔案 `results.py` 現有 13 個 Model 類別中僅 2 個（`ReturnResult`/`AffordabilityResult`）採此字尾，其餘 11 個（`CumulativeTwrPoint`/`AllocationSnapshot`/`NetWorthPoint`/`DriftRow`/`TriggerCondition`/`TriggerChecklist`/`BucketProgress`/`BucketCompositionWarning`/`HouseSummary`/`ProtocolStatus` 等）皆以領域概念命名、不加字尾，`NetInvestmentDerivation` 完全符合本檔案的主流既有慣例，非新增偏離。

### 規則審查發現

人工逐條比對 01～05 規則文件後，除上方 checker 已標項目的復核外，額外檢視要點：

- **架構分層**：`CostBasisService`（純運算，AD-3）、`RecordRepository` compound method（AD-5）、CSV 契約擴充（AD-9）、Page 委派（AD-10）皆與 design.md 的 ADR 決策一致，未發現 Service 做 I/O、Repository 含業務判斷、Controller 做資料轉換等歸屬錯誤。
- **錯誤處理**：`CostBasisService._ensure_uses_cost_basis` 拋 `DataValidationError` 不 log；`RecordRepository` 兩個 compound method 失敗時 `rollback()` 後原樣往上拋、不 log error，符合 02-architecture §6／04-cross-cutting §2.1 逐層矩陣；`views/input.py`／`views/settings.py` 皆由既有 `except AssetLabError` 單一 catch 點吸收（含新的 `DataValidationError`），`logger.exception(...)` + `st.error(...)`，符合本專案既定 AD-8 偏離（Page 為唯一 catch 點）。
- **Logging**：Service/Repository/`core/utils.py`/`amount_widget.py` 皆未新增任何 log 呼叫，維持 AD-8「下層不 log、Page 層統一 log」原則；未發現 f-string log、洩漏敏感值等問題。
- **DI**：`CostBasisService.__init__(*, cost_basis_categories)`、`bootstrap.build_container` 組裝皆為 keyword args；屬性命名不加底線前綴（`self.cost_basis_categories`），符合 01-coding-style §1。
- **Pydantic Model**：`MonthlyRecordModel` 新增兩欄純資料、`NetInvestmentDerivation` 純資料無業務邏輯，符合 03-data-config §3。
- **敏感資料／魔法字串**：未發現寫死密鑰或個資；金額千分位正則、字級/高度樣式常數等皆為模組私有常數並附 WHY 註解，未見未定義的魔法字串散落。
- **註解風格**：抽查 `amount_widget.py`／`cost_basis_service.py`／`core/utils.py`／`views/input.py` 的行內註解與 docstring，皆說明「為什麼」（如過渡規則為何要往後掃描、嚴格千分位分組要防什麼），未發現 WHAT 型或修改歷史型註解。
- **Import 分組**：抽查新增/修改檔案的三區塊標頭與空行格式，與既有慣例一致（含「空區塊＋緊接下一區塊、不留空行」的既有 ruff isort 慣例）。
- **`ruff check .`** 複驗全過（`All checks passed!`），與 progress.md 記載一致。

### 結論

本次變更（CostBasisService 推算、Repository compound 寫入、CSV 契約擴充、金額千分位輸入元件與放大樣式、Page 整合）未發現 CRITICAL 或 HIGH 等級的真實規則違規；checker 標出的 49 條 HIGH／12 條 MEDIUM 復核後全數判定為既有架構慣例延伸或 checker 未適配本專案慣例（皆有具體既有程式碼或前序 Change 判例佐證），220 條 LOW 中 218 條同屬既有測試慣例，僅 2 條為可選、非阻擋的 LOW 建議（`test_monthly_input.py:687` 型別提示、`record_repository.py:141` Returns 區塊一致性）。核准判定：**通過**。

### 第二段修正（使用者決策：僅修第 1 條）

- `tests/test_monthly_input.py:687` — `_FailingCursor.execute(self, *args, **kwargs)` 補上型別提示，改為 `def execute(self, *args: object, **kwargs: object):`，比照 `tests/test_page_config.py:46` 既有先例。
- `record_repository.py:141`（`read_holding_records` docstring 缺 Returns 區塊）：使用者決策留待未來不動，本次不修正。
- 驗證：`ruff check .` → All checks passed；`pytest tests/ -q` → 515 passed。

## 3-4 行為對映審查

審查範圍：本 Change 新增／更新的 15 張 SC 卡片（SC-008、SC-009、SC-031、SC-074~085）× 87 個掛 `@pytest.mark.scenario` marker 的 test 函式，分布於 `tests/test_cost_basis.py`、`tests/test_monthly_input.py`、`tests/test_input_view.py`、`tests/test_amount_widget.py`、`tests/test_core_utils.py`、`tests/test_data_io.py`、`tests/test_settings_view.py` 共 7 個 test 檔案
核准判定：**通過**

逐一讀取 15 張 SC 卡片的 `## 行為`／`## 邊界`／`## 錯誤` 區段，並讀取全部 87 個對映 test 函式的 mock 設定、輸入值與 assertion 內容逐條比對，數值、分類、方向（正負號）、呼叫序列與訊息語意皆與 SC 描述一致，未發現不對齊項目。另確認 15 張 SC 卡片本身的 `## 行為`／`## 邊界` 區段皆為業務語言（無 class 名／函式名／SQL／exception 類型等實作細節洩漏），符合格式規範；`SC-083` 卡片的實作細節字眼（CSS class 選擇器、AppTest）僅出現在允許技術語言的 `## 測試對映` 區段，不違規。

### 不對齊

（無）

### 對齊

| SC | test 函式（所在檔案） | 判斷依據 |
|----|----------------------|---------|
| SC-008 | `tests/test_monthly_input.py::TestBuildTransferPair` 4 個 test（`test_sc008_pair_records_opposite_net_investments` 等） | 2026-05、來源 id=2／目標 id=1、金額 50000 → 來源 −50000／目標 +50000，同月份、金額相等方向相反、市值留空，逐條對映 SC-008 的 GIVEN/WHEN/THEN 與邊界 |
| SC-009 | `tests/test_monthly_input.py` 的 `test_sc005_sold_item_not_carried`（雙掛 SC-005/SC-009）、`TestPrefillSoldExclusion::test_sc009_no_carry_after_sale_month`、`TestSaleMonthClearoutPersisted` 2 個 test | 賣出當月市值 0／淨投入 −530000 落地持久化為一筆有效紀錄、自下月起缺列不再帶入，對映 SC-009「賣出當月記市值0...後續月份缺列」 |
| SC-031 | `tests/test_data_io.py::TestExportImportRoundTrip` 6 個 test | 匯出 holdings/records/targets 三份 CSV 皆含表頭與完整列（records 含 total_cost/realized_income 兩新欄）、匯入空庫後還原一致（含負債 None 值不失真、全空資料集還原為空），對映 SC-031 全部 GIVEN/WHEN/THEN |
| SC-074 | `tests/test_cost_basis.py` 9 個 test（`TestUsesCostBasis`＋`TestDeriveHappyPath`＋`TestPlanSaveDeletePlanValidation`）、`tests/test_input_view.py` 5 個 test | 初始成本 300000 當首筆前期總成本、推算淨投入 50000；前一筆 350000 作新前期總成本；已實現收益 15000/−5000 分別從差額中扣除/加回（−35000/−15000）；非股票/ETF 分類呼叫 `derive`/`plan_save`/`plan_delete` 拋 `DataValidationError`；View 層預覽文字「前期總成本：300,000」「推算本月淨投入：-300,000」與存檔委派落地值，數值與公式皆逐條對應 SC-074 行為與邊界 |
| SC-075 | `tests/test_cost_basis.py::TestDeriveTransitionEstimate::test_sc075_*` | 鴻海、初始成本 200000，前兩筆舊制列淨投入 30000+20000，前期總成本估算 250000、`is_transition_estimate=True`、推算淨投入 30000，與 SC-075 數值完全一致 |
| SC-076 | `tests/test_cost_basis.py::TestDeriveLiquidation::test_sc076_*` | 聯發科，前期總成本 350000、本月總成本 0／已實現收益 50000 → 推算淨投入 −400000（恰為負的賣出實收），對映 SC-076 |
| SC-077 | `tests/test_cost_basis.py` 5 個 test（`TestPlanSaveRecalculatesImmediateFollowingRecord`＋`TestPlanDeleteRecalculatesImmediateFollowingRecord`）、`tests/test_input_view.py::test_delete_button_delegates_to_plan_delete_then_delete_record_and_upsert` | 修改 2026-05 總成本後只有 2026-06 跟著重算（60000/40000，2026-07 不在回傳列中即未變動）；刪除 2026-06 後僅 2026-07 重算為 70000、2026-05 不受影響，與 SC-077 兩段 WHEN/THEN 逐一對應 |
| SC-078 | `tests/test_cost_basis.py::TestPlanDeleteAcrossTransitionRecords::test_sc078_*` | 刪除 2026-01（舊制列）後，2026-02（舊制列）維持不變、真正重算的是 2026-03（新制列，前期總成本 315000、淨投入 25000），對映 SC-078「往後掃描到第一筆新制列」的核心斷言 |
| SC-079 | `tests/test_cost_basis.py::TestTransferRecordsToWrite` 3 個 test、`tests/test_input_view.py::test_transfer_involving_stock_end_writes_only_non_stock_leg` | 來源非股票/目標股票 → 只寫來源；來源股票/目標非股票 → 只寫目標；兩端皆非股票 → 兩端皆寫（SC-008 邊界的自審補充），皆對映 SC-079 |
| SC-080 | `tests/test_cost_basis.py::test_sc080_both_ends_stock_neither_written`、`tests/test_input_view.py::test_transfer_both_ends_stock_writes_nothing_and_shows_info` | 兩端皆股票 → `transfer_records_to_write` 回傳空清單、View 層不寫入且顯示「未寫入任何紀錄」info 提示（非錯誤提示），對映 SC-080「兩端皆不寫入且提示為合法情況」 |
| SC-081 | `tests/test_core_utils.py` 15 個 test（`TestFormatAmount`＋`TestParseAmount` 千分位部分）、`tests/test_amount_widget.py` 9 個 test、`tests/test_settings_view.py` 2 個 test | "1234567"→"1,234,567"、已有千分位逗號保留不變、負數加負號、小數四捨五入遠離零（1234567.6→1,234,568）、全形數字/逗號正規化，widget 層初值與 on_change 行為、settings 頁初始市值/成本欄同樣適用，逐條對映 SC-081 行為與邊界 |
| SC-082 | `tests/test_core_utils.py` 7 個 test（`TestParseAmount` 拒絕部分）、`tests/test_amount_widget.py` 2 個 test | 非標準分組 "1,00,000"、純文字 "abc"、空字串、純空白、None 皆拒絕並拋 `DataValidationError`（訊息含欄位名稱）；已實現收益欄顯式輸入 "0" 視為合法；widget 層 on_change 不崩潰、原樣保留文字供存檔時判定，對映 SC-082 全部行為與邊界 |
| SC-083 | `tests/test_amount_widget.py::TestInjectAmountInputStyleTargetsAmountFieldsOnly` 3 個 test | CSS 選擇器前綴與 `amount_input` container key 前綴一致、font-size/height 皆明顯大於 Streamlit 預設 1rem、非金額欄位（項目名稱）不在帶前綴 container 內因而不命中，對映 SC-083「放大且僅套用於金額欄」；卡片本身已註記視覺效果留待 2-Z 人工確認，與 2-Z 記錄一致 |
| SC-084 | `tests/test_data_io.py::TestLegacyRecordsCsvWithoutCostBasisColumns` 3 個 test | 僅 4 欄舊格式 CSV 匯入成功、市值/淨投入依原值還原、total_cost/realized_income 皆為 None；新格式欄位存在但留白同樣視為 None，對映 SC-084 全部行為 |
| SC-085 | `tests/test_monthly_input.py::TestBatchWriteRollbackOnFailure` 3 個 test | 批次 upsert 中途失敗（第 2 筆）→ 第 1 筆也不留存；delete_record_and_upsert 中途失敗 → 原本已存在的列維持存在、新批次列皆未落地；錯誤以 `pytest.raises(RuntimeError, match=...)` 確認原樣往上拋、未被轉譯或吞掉，對映 SC-085「批次寫入中途失敗不留下部分寫入結果」「錯誤原樣往上拋」 |
