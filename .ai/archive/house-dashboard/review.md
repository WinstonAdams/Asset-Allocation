# Review: [Change 名稱]

## 3-1 程式碼清理

掃描範圍：23 個檔案（src/ 10、views/ 3、app.py 1、tests/ 9），88afa9e..1a1f4c4

### 自動掃描

Checker 命令：`python .claude/skills/spec-driven-flow/scripts/checkers/runner.py --phase 3-1 --project-dir . --diff-base origin/main --json --output .ai/changes/house-dashboard/.cache/checker_3_1.json`
總違規：57 條（HIGH 6／MEDIUM 50／LOW 1）
Baseline 命中：0 條（全數為本 Change 新增）
完整報告：`.ai/changes/house-dashboard/.cache/checker_3_1.json`

違規分佈：
- `change_level_id_comments`（HIGH ×6）：`#` 註解引用 Change 級編號
- `function_too_large`（MEDIUM ×3）：`assess_triggers`（87 行）、`views/house.py::render`（61 行）、`_render_house_params`（111 行）
- `duplicate_code`（MEDIUM ×49）：測試檔固定資料塊重複 ×約 39、`views/house.py` vs `views/overview.py` 編排重疊 ×10
- `file_too_long`（LOW ×1）：`tests/test_house.py`（1018 行）

`ruff check .` 全過（含 F401/F841 未用 import/變數）；`vulture` 未安裝，跳過。

以下逐條復核 checker 命中，並補上 checker 規則設計外（docstring 內文、非 `#` token）checker 不會報但語意上同屬「Change 級編號」的案例。

### 執行結果（第二段，依主 AI 指示：只修 SAFE，SUGGEST 暫緩）

- SAFE 全部項目已修正（6 條 `#` Change 級編號註解、17 處生產碼 docstring BR-N/AD-N/SC-N 引用、`affordability_service.py` 過時 `SC-PENDING-001` 引用改寫為純 WHY 說明、`schema_repository.py::_ensure_holdings_purpose_column` 補 `cursor` 型別提示）
- `affordability_service.py` 的過時引用依主 AI 指示在本階段一併修掉，不留給 3-3 重複處理
- 其中一條原 SAFE 建議（兩個新 Repository 檔案補 import 區塊空行）執行時發現與 ruff isort 期望格式衝突，已撤回並還原，詳見下方「其他」小節
- CAREFUL／SUGGEST 依主 AI 指示暫緩，本階段未動
- 修正後驗證：`pytest tests/ -q` → 421 passed；`ruff check .` → All checks passed；checker 複跑 → HIGH 6→0，MEDIUM/LOW 不變（皆為暫緩的 CAREFUL/SUGGEST 項）

### SAFE

**checker 已標，復核後同意需修（6 條，皆為本 Change 新增、baseline 同類 `#` 註解掃描為 0 條，非既有慣例）：**

- `src/asset_lab/repositories/holding_repository.py:22` — `# 既有分類/報酬/配置計算完全不讀此欄（BR-9/D14），僅供買房功能讀寫。`；建議保留 D14（`docs/DECISIONS.md` 永久 SSOT，非 Change 級）、刪除 `BR-9`（proposal.md 業務規則編號，歸檔後失去索引）
- `tests/test_bootstrap.py:165` — `# === holdings 用途欄位加欄遷移：舊庫升級 / 新庫直建 / 重複啟動三路徑（SC-059）===`；下方已有 `@pytest.mark.scenario("SC-059")` 承載正式對映，此分隔註解的 SC 引用可整段改寫為純業務分隔說明（不含編號）
- `tests/test_data_io.py:399` — `# 匯出→清空→重新匯入，用途不遺失（純附加欄位須於備份鏈路中保存，AD-8）`；刪除 `AD-8`，WHY 說明本身已足夠清楚
- `tests/test_house.py:766` — `# 買房頁（views/house.py）呈現測試：SC-066/SC-067`；同上，改為純分隔說明
- `tests/test_overview.py:298` — `# 總覽頁買房進度摘要：SC-071`；同上
- `tests/test_overview.py:341` — `# 目標總價未設定時 progress_pct 為 None，但觸發計數不受影響照常呈現（SC-071 邊界）`；刪除 `SC-071 邊界`

**checker 未報出（docstring 內文引用，非 tokenize COMMENT，checker 規則刻意只掃 `#` token；語意上同屬「Change 級編號會隨歸檔失效」，故一併列出）：**

僅列生產碼（`src/`、`views/`）；測試檔的 docstring `SC-XXX` 引用（如 `"""SC-060：..."""`）經比對 baseline 既有測試（`test_protocol.py`/`test_allocation.py`/`test_holding_master.py` 等，SC-001~050 皆同此寫法）為專案既有、長期一致的慣例，不在此列，見下方「不建議動」說明。

- `src/asset_lab/core/constants.py:45` — `HOLDING_PURPOSE` docstring「...（BR-9/D14）」→ 留 D14、去 BR-9
- `src/asset_lab/models/holding.py:18` — 同上「...（BR-9/D14）」→ 留 D14、去 BR-9
- `src/asset_lab/models/results.py:93` — `TriggerCondition` docstring「（BR-5）」→ 去
- `src/asset_lab/models/results.py:109` — `TriggerChecklist` docstring「（BR-5）」→ 去
- `src/asset_lab/models/results.py:121` — `BucketProgress` docstring「（BR-3/4/6）」→ 去
- `src/asset_lab/models/results.py:142` — `BucketCompositionWarning` docstring「（BR-8/D15）」→ 留 D15、去 BR-8
- `src/asset_lab/models/results.py:155` — `HouseSummary` docstring「...同口徑（AD-9）」→ 去
- `src/asset_lab/services/house_service.py:4` — 模組 docstring「（BR-5 五條...）」→ 去
- `src/asset_lab/services/house_service.py:149` — `bucket_value` docstring「（BR-3）」→ 去
- `src/asset_lab/services/house_service.py:172` — `cash_reserve_value` docstring「（BR-4）」→ 去
- `src/asset_lab/services/house_service.py:202` — `bucket_progress` docstring「（BR-2/BR-6）」→ 去
- `src/asset_lab/services/house_service.py:248` — `bucket_composition_warning` docstring「（BR-8/D15）」→ 留 D15、去 BR-8
- `src/asset_lab/services/house_service.py:285` — `assess_triggers` docstring「（BR-5）」→ 去
- `src/asset_lab/services/house_service.py:373` — `overview_summary` docstring「...見 AD-9」→ 去
- `views/overview.py:9` — 模組 docstring「...摘要列（AD-9）」→ 去
- `views/overview.py:108` — `_compute_house_summary` docstring「...同口徑（AD-9）」→ 去
- `views/overview.py:227` — `_format_house_progress_percent` docstring「（SC-071 邊界：...）」→ 去，WHY 說明本身已清楚

**已知問題交叉引用（與 progress.md 3-3 已知待修項重疊，於此一併列出並標明分工）：**

- `src/asset_lab/services/affordability_service.py:104` — docstring「...月收為 0（尚未設定，見 SC-PENDING-001）時占比無法定義...」。`SC-PENDING-001` 為過時引用，正確編號應為 `SC-072`（已核對 `.ai/changes/house-dashboard/scenarios/SC-072.md` 語意完全對應）。progress.md 已將此列為 3-3 規則符合度審查的已知待修項（"應為 SC-072＋違反原始碼註解禁列 Change 級 SC 編號"）。**判定**：此條同時符合本階段（3-1）的 Change 級編號清理範圍，且是單行文字修正、零風險，建議直接在本階段修正（刪除整個 `見 SC-PENDING-001` 括號引用，WHY 說明「尚未設定」已足夠），可讓 3-3 免於重複處理；若主 AI 傾向留給 3-3 統一處理亦可，兩階段擇一即可、不需重複改動。

**其他（非編號註解類）：**

- ~~`house_param_repository.py`／`subjective_trigger_repository.py` import 區塊間缺空行~~ — 執行時發現此建議有誤：實際補上空行後 `ruff check` 立即報 `I001 Import block is un-sorted or un-formatted`（`ruff --diff` 確認其canonical 格式就是「# 無」後緊接下一區塊標頭、不留空行）。已比對 baseline `holding_repository.py`/`schema_repository.py` 同形狀、同樣無空行且 ruff 全過，確認這是 ruff isort 對「空區塊（僅 `# 無`）+ 前一區塊含 import」這個形狀的實際期望格式，非違規。**撤回此條**，兩檔皆恢復原狀（不留空行），已重新 `ruff check .` 全過驗證。
- `src/asset_lab/repositories/schema_repository.py:132` — `_ensure_holdings_purpose_column(cursor)` 為本 Change 新增方法，`cursor` 參數缺型別提示，違反 `01-coding-style.md` §1「型別提示：必填，遵循 PEP 484」。**已修正**：改為 `cursor: "Cursor"`，並在既有 `if TYPE_CHECKING: from libsql import Connection` 區塊一併 import `Cursor`。

註：`src/asset_lab/repositories/holding_repository.py:14` 與 `schema_repository.py:24` 亦有相同「import 區塊缺空行」現象，但經比對 baseline（88afa9e 版本）確認為本 Change 之前已存在的既有格式、非本次改動觸及的行，依掃描焦點原則不列入本次清理範圍（且如上所述，此形狀本就是 ruff 期望的正確格式，並非待清理項）。

### CAREFUL

- **測試檔 `duplicate_code` 命中（約 39 條，集中於 `test_house.py`／`test_bootstrap.py`／`test_data_io.py`／`test_settings_view.py`）**：逐條抽查（`test_house.py` 的 holdings/`_holding(...)` 建構區塊、`test_bootstrap.py` 的 schema SQL／`HoldingRepository(conn=connection)` 建構、`test_data_io.py` 的 CSV 欄位清單斷言、`test_settings_view.py` 的「範例定存」項目建構）判定為**測試慣例可接受的重複**：各測試案例的資料組合刻意不同（不同 purpose/category/金額組合驗證不同邊界），且已有共用 helper（`_holding`/`_record`/`_params`/`_subjective`/`_forward`）降低重複到呼叫端參數層級。checker 的行級相似度偵測對此類結構相似但語意不同的測試固定資料本就容易誤判。不建議進一步抽象化（會犧牲單一測試可獨立閱讀性），本階段不動。
- **`views/house.py` vs `views/overview.py` 的 `duplicate_code`（10 條，讀參數→算 bucket/現金預備金→`payment_for_price`→`bucket_progress`→讀主觀勾選→`assess_triggers` 編排區塊，以及 `_to_month_records` 整個輔助函式）**：核對 `.ai/changes/house-dashboard/design.md` §8「已知限制與技術債」，此重疊為 Phase 1-2 已使用者確認的**既定設計決策**（原文：「overview 與 house 頁的資料編排部分重疊...口徑經 HouseService 統一，但兩頁各自編排讀取（可接受的少量重複，未來若第三處需要再抽共用編排）」）。`views/overview.py` 的 `_compute_house_summary`/`_to_month_records` docstring 也明確自陳此重疊「有意」。**判定：不建議清理**，貿然抽共用編排會牴觸已拍板的設計決策；如未來第三處需要才依 design.md 指示的路徑抽共用。

### RISKY

無（vulture 未安裝無法產出動態引用類候選；其餘掃描到的項目風險皆可自行判斷，已歸入 SAFE/CAREFUL/SUGGEST）。

### SUGGEST

- `src/asset_lab/services/house_service.py::assess_triggers`（87 行，checker `function_too_large`）：實際邏輯本體約 58 行，其餘為必要的 fail-closed 邊界說明 docstring（9 行）。函式單一職責（組出五條觸發清單）、無深層巢狀，5 個 `TriggerCondition` 建構彼此欄位語意不同（kind/actual/required 各異），拆分子函式效益有限。低優先，不建議動。
- `views/settings.py::_render_house_params`（111 行，checker `function_too_large`）：核對同檔既有 `_render_protocol_thresholds`（3 個 `st.number_input` 逐一展開，未資料驅動化），本函式是同一慣例延伸到 9 個欄位（AD-4：沿用 protocol_thresholds 模式），非本 Change 新創的反模式。可考慮改資料驅動（欄位規格清單 + 迴圈）縮減行數，但會偏離本檔既有風格；低優先，建議留待未來若同檔再擴充時一併評估。
- `views/house.py::render()`（61 行，checker `function_too_large`）：與 `views/overview.py::render()` 對照，overview 已將「取買房摘要」的計算區塊抽成獨立的 `_compute_house_summary()` helper 讓 `render()` 維持精簡；`views/house.py::render()` 尚未套用同樣手法（讀參數→算 bucket/可負擔性/進度/警示/觸發檢核 全部內聯）。建議：可仿 `_compute_house_summary` 抽出一個 `_load_view_model()`（或類似命名）helper 承接純運算組裝部分，`render()` 僅留「取得 view model → 呼叫三個 `_render_*`」，可降到 50 行以內並與 overview.py 風格一致。低風險、可延後至第二段執行或留待下次觸碰此檔案時處理。
- `tests/test_house.py`（1018 行，checker `file_too_long`，LOW）：涵蓋 bucket 值/進度/組成警示/現金預備金/觸發檢核（3 個 class）/買房頁呈現（2 個 class）共 7 大測試群組。可考慮依職責拆為 `test_house_bucket.py`／`test_house_triggers.py`／`test_house_page.py`。因severity 僅 LOW、且拆分測試檔有動到 scenario_lint 對映與 test collection 的風險，效益/風險比不高，建議暫不處理，留待此檔案下次因新增測試而再變動時一併考慮。

## 3-2 安全性審查

<!-- security-reviewer subagent 產出（涉及認證/付款/個資時才執行） -->

## 3-3 規則符合度審查

審查範圍：23 個檔案（app.py 1、src/asset_lab 11、tests/ 8、views/ 3），88afa9e..HEAD（與 3-1 掃描範圍一致；docs/\*.md 與 .ai/changes/\* 非 Python，不列入規則審查）
核准判定：**通過**（第二段已修正僅有的 1 條 HIGH + 1 條 MEDIUM，複跑驗證全過，詳見下方「執行結果」）

### 自動掃描

**Diff-base 偏離說明（先於命令交代）**：標準命令的 `--diff-base origin/main` 在本次執行時已失真——`git fetch origin main` 後 `origin/main` 落在 `1a1f4c4`（本 Change 3-2 skip 標記提交），僅落後 HEAD 一個 commit（`dbdad1b`，3-1 清理），因為此 repo 有「Phase 邊界順手 push 到 GitHub 備份」的習慣，origin/main 並不代表「本 Change 開始前」的基準。若照字面用 `origin/main`，`git diff` 只會顯示 3-1 清理那 14 個檔案的 115 行改動，完全漏掉 Phase 2 八個 Task 產出的全部業務程式碼——不符合 3-3「工程準則全面符合度審查」的職責範圍。故改以 `88afa9e`（house-dashboard Change 的真正起點，1-1 提案提交的父 commit，`git merge-base --is-ancestor` 已驗證，且與 3-1 review.md 記載的掃描基準完全一致）作為實際 diff-base，兩者皆記錄於此供交叉核對。

Checker 命令（實際採用）：`python .claude/skills/spec-driven-flow/scripts/checkers/runner.py --phase 3-3 --project-dir . --diff-base 88afa9e --json --output .ai/changes/house-dashboard/.cache/checker_3_3.json`
退出碼：0（正常完成）
總違規：676 條（CRITICAL: 0 / HIGH: 316 / MEDIUM: 35 / LOW: 325）
Baseline 命中：0 條（尚未對本專案建立 3-3 baseline）
完整報告：`.ai/changes/house-dashboard/.cache/checker_3_3.json`

**重要提醒**：676 條中經逐類復核，**絕大多數（約 675 條）為 checker 規則模板與本專案既有架構不匹配的偽陽性**，而非本 Change 引入的新違規——詳見下方逐條復核。真正需要修正的僅 1 條（HIGH，見「規則審查發現」）。

### Checker 命中逐類復核

以下依 rule_id 分類復核（非逐條，因同類問題在本 Change 內大量重複、成因相同；已對每類抽樣核對 baseline 既有程式碼佐證判定）：

- **`no_runtime_constants_access`（257）／`service_no_runtime_constants`（30）／`repository_no_runtime_constants`（4）／`no_module_level_constants_alias`（8）—— checker 已標，復核判定：不違規（既有架構慣例，非本 Change 新增偏離）**。
  抽樣核對：`src/asset_lab/repositories/holding_repository.py:148`、`schema_repository.py:139/141`、`services/data_io_service.py:117/174/175`、`services/house_service.py`（27 條）、`views/house.py:90/92/48`、`views/overview.py:132`、`views/settings.py:407-415`、`house_param_repository.py:19-21`、`subjective_trigger_repository.py:19-21` 等生產碼命中，其餘集中於 tests/（fixture 資料建構直接引用 constants，非 runtime 環境值）。
  逐一比對 baseline（88afa9e 前）同構寫法：`holding_repository.py` 既有 `_COLUMNS = (HOLDINGS_TABLE.HOLDING_ID, ...)`（模組級常數 tuple）、`protocol_threshold_repository.py` 既有 `_TABLE = PROTOCOL_THRESHOLDS_TABLE.TABLE_NAME` 別名、`views/input.py` 既有 `from constants import TIMEZONE` 並於函式 body 直接用 `today_in_timezone(TIMEZONE)`、`views/settings.py::_render_protocol_thresholds` 既有於函式 body 直接組 `(PROTOCOL_LEVEL_CODE.L1, l1), (...)` tuple 供 upsert——本 Change 的 `house_param_repository.py`/`house_service.py`/`views/house.py`/`views/settings.py::_render_house_params` 等新增程式碼與這些既有寫法逐行同構。
  本專案首次 3-3 審查（`.ai/archive/initial-build/review.md`）已對此類 pattern 做出明確裁決：「Repository 的 `from constants import *_TABLE` 為模組級 schema 常數定義用於組 SQL 字串、非 runtime 環境差異值……本專案無 `--env` 多環境、表名為全域固定常數，且 SQL 模板須在模組級組裝，判定可接受、非違規」。本 Change 完全沿用同一模式，判定同樣不違規。
  Checker 對應：checker 已標，復核後不採信（規則模板針對 utils_v2/多環境 RPA 專案設計，與本專案既定架構不符；非新增偏離）。

- **`docstring_required`（108，全數在 tests/）／`ANN201`（99）／`ANN001`（88）／`ANN202`（15）／`ANN204`（8）／`ANN003`（1）—— checker 已標，復核判定：不違規（測試檔既有慣例）**。
  抽樣：test 方法無 docstring（僅 class docstring + `@pytest.mark.scenario` + inline `#` WHY 註解）、`def test_x(self, service):` fixture 參數無型別、內部 helper class `__init__` 無回傳型別註解。
  核對 baseline `tests/test_allocation.py`（`class TestCumulativeTwrSeries: """...(SC-028)"""` + 裸 `def test_sc028_...(self):`）、`tests/test_data_io.py`（`def test_sc031_...(self, service):` fixture 參數同樣無型別）——本 Change 新增測試與此 100% 一致，非新增偏離。且本專案 `pyproject.toml` 的 ruff `[tool.ruff.lint] select = ["E","F","I","UP","B"]` 本就不含 `ANN` 系列，checker 是額外用 ruff ANN 規則獨立掃描、與專案自身工具鏈設定脫鉤。
  Checker 對應：checker 已標，復核後不採信（與全專案 100% 一致的既有測試慣例；不因本 Change 而發生新退步）。

- **`docstring_returns_section`（35，生產碼 14 條 + tests 21 條）—— checker 已標，復核判定：不違規**。
  生產碼命中皆為單行 prose docstring（如 `_row_to_model`: 「把買房參數 row tuple 組回 HouseParamModel。」、`read_params`: 「讀全部已保存的買房參數，可能不完整（0～9 筆，任意順序）。」），已用一句話帶出回傳語意，未用 `Returns:` 標頭。核對 baseline `protocol_threshold_repository.py`（`house_param_repository.py` 明確依 AD-4「比照 ProtocolThresholdRepository」建構）之 `_row_to_model`/`read_thresholds()` 逐字同構，同樣是單行 prose、無 `Returns:` 標頭——本專案對「簡單函式」的既定慣例即是單行 prose 而非強制 Google-style 區塊，`initial-build` 3-3 審查已認定全專案「docstring 完整」（未要求補 Returns: 標頭）。
  Checker 對應：checker 已標，復核後不採信（比對同構前例，屬既有 docstring 風格慣例）。

- **`import_block_format`（10）—— checker 已標，復核判定：不違規（checker 規則模板誤判）**。
  訊息為「缺少 import 區塊註解：`# ==== AsiaYo 專案內部 ====`」。本專案（含全部 baseline 檔案）一律使用 `# ==== 專案內部 ====`（不含 "AsiaYo" 字樣，因本專案為 Winston 個人專案，非 AsiaYo 公司專案）——這是全庫 100% 一致的既有慣例，checker 規則模板誤把 `05-reference.md` 範例中的字面文字 "AsiaYo" 當成強制字串比對，與本專案身分不符。
  Checker 對應：checker 已標，復核後不採信（checker 規則校準問題，非本 Change 或本專案的程式碼違規；建議另行反映給 checker 維護者調整比對邏輯為結構性而非字面 "AsiaYo" 比對，不需、也不宜逐檔加 noqa——這是全庫皆有的既有格式，噪音成本過高）。

- **`model_naming_convention`（6）：`HouseParams`／`TriggerCondition`／`TriggerChecklist`／`BucketProgress`／`BucketCompositionWarning`／`HouseSummary` —— checker 已標，復核判定：不違規**。
  核對 baseline `models/results.py` 既有 `CumulativeTwrPoint`／`AllocationSnapshot`／`NetWorthPoint`／`DriftRow`／`ProtocolStatus`（5 個既有結果類別皆無 `Model`/`Result` 後綴）與 `models/protocol.py` 既有 `ProtocolThresholds`（合併後有效值類別，同樣無後綴）——本專案對「計算結果值物件」的實際命名慣例就是領域名詞直呼，不強制 `XxxResult`/`XxxModel` 後綴（僅持久化列模型如 `HouseParamModel`/`SubjectiveTriggerModel` 遵循 `XxxModel`）。本 Change 6 個新類別與此既定慣例完全一致。
  Checker 對應：checker 已標，復核後不採信（與 5/6 既有結果類別同構的命名慣例）。

- **`no_stdlib_get_logger`（1）／`event_name_format`（1）／`no_logger_exception`（1）／`note_required`（1）：`views/house.py:36,115` —— checker 已標，復核判定：不違規**。
  `logger = logging.getLogger(__name__)` + `logger.exception("買房頁渲染失敗")`，checker 期待 structlog + kwargs event-name 契約（04-cross-cutting.md）。核對 baseline **全部 7 個既有 View 檔案**（`data_io.py`/`allocation.py`/`input.py`/`returns.py`/`protocol.py`/`overview.py`/`settings.py`）100% 使用同一寫法：`logging.getLogger(__name__)` 模組頂層宣告 + 唯一 catch 點 `logger.exception("XX頁渲染失敗")`。此為本專案首次 3-3 審查已明確記載的既定偏離（`initial-build` design.md AD-8：「不採 structlog event-name/note/log_type 欄位契約……無 utils_v2 pipeline，硬套形同空轉」），非本 Change 新增。
  Checker 對應：checker 已標，復核後不採信（AD-8 既定且正當的專案級偏離，与既有 7 個 View 檔案逐字同構）。

- **`root_main_exists`（1）／`src_project_layout_missing`（1）—— checker 已標，復核判定：不違規**。
  與 `initial-build` 3-3 審查完全相同的既定裁決：本專案為 Streamlit 常駐 App（`app.py` 取代 RPA `main.py`；Page 即 View/Controller，無獨立 `controllers/` 目錄），AD-1/AD-2 已論證此偏離為正當設計，非缺漏。
  Checker 對應：checker 已標，復核後不採信（與 initial-build 3-3 同一組既定 ADR 偏離）。

### 規則審查發現

#### HIGH

- [HIGH] `src/asset_lab/models/holding.py:9` — `HoldingModel` 違規 import constants
  問題：`from asset_lab.core.constants import HOLDING_PURPOSE`，用於 `purpose: str = HOLDING_PURPOSE.GENERAL` 欄位預設值。明確違反 `03-data-config.md` §3「Model 與 constants Schema 的關係」：「Model 本身不 import constants（避免耦合）」。
  復核確認**非既有慣例**：檢查全部既有 `models/*.py`（`protocol.py`/`target.py`/`record.py`/`house.py` 等）與 baseline（88afa9e 前）`models/holding.py`，**無任何 Model 曾 import constants**；`kind: str` 等既有欄位皆無預設值、或用純字面量（`net_investment: float = 0.0`）。本 Change 是此模式的第一次出現，非沿用既有偏離。
  Checker 對應：checker 已標（`model_no_constants_import`），復核後同意需修（真實違規，非既有慣例、非誤判）。
  建議修法：Model 改用純字面量預設 `purpose: str = "general"`（與 `net_investment: float = 0.0` 同慣例），移除 constants import；`HOLDING_PURPOSE.GENERAL` 的 SSoT 定義保留在 constants.py，供其餘所有非-Model 程式碼（Service/Repository/View）引用即可，Model 層不需要重複引用同一常數來設預設值。

#### MEDIUM

- [MEDIUM] `views/house.py:92` — Controller 層執行資料篩選（`h.purpose == HOLDING_PURPOSE.HOUSE`）
  問題：`house_holdings = [h for h in holdings if h.purpose == HOLDING_PURPOSE.HOUSE]` 直接在 View/Controller 內對 `holdings` 做屬性篩選，餵給 `house_service.bucket_composition_warning(house_holdings=...)`。違反 `02-architecture.md` §4 Controller 合約「禁止：對資料結構的細部操作（篩選、轉換、欄位存取、資料合併）」。
  對照：`HouseService.bucket_value()` 對同一種篩選（`purpose == HOUSE`）是**在 Service 內部**做（house_service.py:160），但 `bucket_composition_warning()` 的介面設計成接收「呼叫端已篩選 purpose=house」的 `house_holdings` 參數（design.md 介面契約與 docstring 皆如此記載），導致同一個篩選邏輯被迫在 View 重複一次、且該次落在錯誤的層級。
  影響範圍：僅 1 處（`views/house.py:92`）；`views/overview.py` 不需要 `bucket_composition_warning`，未重複此問題。
  Checker 對應：checker 未報出（checker 在此行只標記 `no_runtime_constants_access`——即 constants 存取，而非本項「Controller 做篩選」的架構層級疑慮；此為人工架構審查獨立發現的語意層問題）。
  建議修法：讓 `bucket_composition_warning()` 改為接收原始 `holdings: list[HoldingModel]`（比照 `bucket_value` 的介面），內部自行篩選 `purpose == HOLDING_PURPOSE.HOUSE`，View 端直接傳整個 `holdings`，移除 `views/house.py:92` 這行篩選。屬於 Service 介面簽名調整，需同步改 `tests/test_house.py` 中 `bucket_composition_warning` 的呼叫端測試（若測試直接建構已篩選的 house_holdings 傳入）。

### 執行結果（第二段，依主 AI 指示：修正 HIGH + MEDIUM 這 2 條）

- **[HIGH 已修]** `src/asset_lab/models/holding.py`：`purpose: str = HOLDING_PURPOSE.GENERAL` 改為字面值 `purpose: str = "general"`；移除 `from asset_lab.core.constants import HOLDING_PURPOSE` import（第三方套件區塊改回 `# 無`）；docstring 補一句說明「Model 不 import constants（見 03-data-config.md），值與 constants.py 手動保持一致」，避免日後兩處值漂移不被察覺。`HOLDING_PURPOSE.GENERAL` 的 SSoT 定義維持在 constants.py 不變，其餘所有 Service/Repository/View 仍照舊引用該常數。

- **[MEDIUM 已修]** `src/asset_lab/services/house_service.py::bucket_composition_warning`：參數由預先篩選過的 `house_holdings: list[HoldingModel]` 改為原始 `holdings: list[HoldingModel]`，方法內部改為自行執行 `house_holdings = [h for h in holdings if h.purpose == HOLDING_PURPOSE.HOUSE]`（與 `bucket_value()` 的既有做法對稱一致）；docstring 同步更新為「本方法內部篩選 purpose=house，呼叫端不需預先篩選」。
  連動修正：`views/house.py` 移除呼叫端的 `house_holdings = [h for h in holdings if h.purpose == HOLDING_PURPOSE.HOUSE]` 篩選行，改為直接傳 `holdings=holdings`；因該檔案的 `HOLDING_PURPOSE` 常數自此無其他用途，一併移除其 import。`tests/test_house.py` 的 5 處 `bucket_composition_warning(house_holdings=house_holdings, ...)` 呼叫改為 `bucket_composition_warning(holdings=house_holdings, ...)`（測試本地變數名稱不變，僅 kwarg 名稱隨新介面調整；各測試既有的 fixture holdings 本就已標記 `purpose=HOLDING_PURPOSE.HOUSE`，語意不變）。

- **驗證**：
  - `pytest tests/ -q` → **421 passed**（與修正前一致，無迴歸）
  - `ruff check .` → **All checks passed**
  - checker 複跑（`--diff-base 88afa9e`，輸出另存 `.ai/changes/house-dashboard/.cache/checker_3_3_after.json` 供比對）：`model_no_constants_import` 1→0（HIGH 清除）；`service_no_runtime_constants` 30→31（+1，为 `bucket_composition_warning` 內部新增的 `HOLDING_PURPOSE.HOUSE` 篩選行，與 `bucket_value()` 既有同構寫法一樣屬「checker 已標、復核判定不違規」的既定架構慣例，非新增疑慮）；其餘 rule_id 計數不變，總數 676（機械上仍含前述已判定非違規的既有慣例類別，非新增問題）。

### 已知限制交叉引用（非本階段新增，僅存證）

- 3-1 review.md 已列的 SUGGEST 項（`views/house.py::render()` 61 行建議抽 `_load_view_model()`、`_render_house_params` 111 行資料驅動化、`assess_triggers` 87 行）與 `views/house.py` vs `views/overview.py` 編排重疊（design.md §8 已知限制）——皆非 3-3 規則違規範疇（無明確規則被打破），不重複列入本階段發現。

<!-- rules-reviewer subagent 產出（工程準則全面符合度檢查）-->

## 3-4 行為對映審查

審查範圍：22 張 SC 卡片（SC-052～SC-073）× 105 個 `@pytest.mark.scenario` 標記，橫跨 8 個
test 檔（test_affordability.py／test_house_params.py／test_data_io.py／
test_holding_master.py／test_settings_view.py／test_bootstrap.py／test_overview.py／
test_house.py）。逐一讀取 `scenarios/SC-0{52..73}.md` 的 GIVEN/WHEN/THEN 與對應
test 函式的 mock 設定、輸入值、assertion 比對；SC-056／SC-072 兩張額外對 production
code（`views/house.py`、`HouseService.assess_triggers`）做交叉探測驗證呈現層實際行為。

**核准判定：通過**（第一段發現 2 項不對齊；SC-056 已由另一 Task 2-10 修正 production 行為
並補 view 層 test，SC-072 已於本階段補上顯式 test，複查後皆對齊。修正後 pytest 423 passed、
ruff all checks passed）。

### 第一段發現、已於第二段解決的項目

**1.（已解決）SC-056 邊界子句「不得呈現為可負擔 0 元的誤導性結論」**

- 第一段發現：`tests/test_house.py::TestAffordableTotalPriceUnsetIncome::test_sc056_reverse_zero_income_returns_zero_not_exception`
  只斷言 `result.affordable_total_price == 0.0`，且以替身容器實跑 `views/house.py` 探測到
  「可負擔總價（反推） = 0 元」——與 SC-056 明文禁止的「可負擔 0 元」字面一致，屬 production
  未完全實現 SC 之缺陷，非 SC 寫錯。
- 解決方式（Task 2-10，非本 subagent 執行，本輪僅複查）：
  - `AffordabilityService.affordable_total_price`：`monthly_income` 為假值時提早回傳
    `AffordabilityResult(direction="reverse")`（三個反推欄位皆為 `None`），不再退化計算出
    `0.0`（見 `src/asset_lab/services/affordability_service.py` 該方法 docstring 已同步更新）。
  - 既有 test 更名為 `test_sc056_reverse_zero_income_returns_none_not_misleading_zero`，斷言
    `affordable_total_price is None`／`loan_ceiling is None`／`monthly_payment_cap is None`。
  - 新增 `tests/test_house.py::TestHousePageAffordabilityMetricUnsetIncomeDisplay::test_sc056_reverse_metric_shows_dash_not_zero_yuan_when_income_unset`：以替身容器跑
    `views/house.py`，斷言「可負擔總價（反推）」metric 值為 `"—"`（`_format_amount(None)` 的既有
    行為，view 本身無需改動）。
- 複查結論：`AffordabilityResult(None)` → `_format_amount` 走既有 `None → "—"` 分支，語意與
  SC-056「反推可負擔總價結果為 0 或呈現未設定，不得呈現為可負擔 0 元」完全一致，且今有 view
  層 test 直接釘住。**現已對齊**。

**2.（已解決）SC-072 邊界子句「月付占比為 None 時，月付觸發條件視為未達成（fail-closed）」**

- 第一段發現：`tests/test_house.py` 內 8 處以 `forward_result=_forward(None)` 呼叫
  `assess_triggers`，皆未對月付條件的 `met` 值做斷言；production code
  （`house_service.py::assess_triggers` 的 `payment_met` 判斷式）本身已正確 fail-closed，純屬
  test 覆蓋缺口。
- 解決方式（本階段執行）：新增
  `tests/test_house.py::TestAssessTriggersPaymentConditionFailClosedOnUnsetIncome::test_sc072_payment_condition_not_met_when_income_share_pct_is_none`，標記 `@pytest.mark.scenario("SC-072")`，
  以 `target_total_price=5_000_000.0`、`payment_cap_ratio=40.0`、`forward_result=_forward(None)`
  呼叫 `assess_triggers`，斷言月付條件 `met is False`。純補 test，未動 production code。
- 複查結論：**現已對齊**。

### 對齊

以下依 capability 分組列出審查結果（每組審查了該 SC 對映的全部 test 函式，非抽樣）：

| SC | capability | 對映 test 檔／class | 判斷依據 |
|----|-----------|---------------------|---------|
| SC-052 | affordability-engine | test_affordability.py::TestPaymentForPriceForward | 貸款 7,000,000／自備 3,000,000／月付≈38,821.83／占比≈38.82% 與 SC 給值一致；利率 0% 退化本金均分 7,200,000÷360=20,000 一致 |
| SC-053 | affordability-engine | test_affordability.py::TestAffordableTotalPriceReverse | 月付上限 40,000／貸款上限 9,600,000／可負擔總價 12,000,000 與 SC 一致；往返一致性與自備比率愈高總價愈高兩條邊界皆覆蓋 |
| SC-054 | house-params | test_house_params.py::TestEffectiveParamsDefaults／TestHouseParamsPersistence | 全未存→`HOUSE_PARAM_DEFAULTS`（個人化 0、政策比率 33/35/2.5/30）逐一比對常數定義一致；單鍵/部分鍵合併、int 還原、DB 落地生效（含容器重建）皆覆蓋 |
| SC-055 | house-params | test_house_params.py::TestValidateParamsRejectsInvalid／TestInvalidParamsDoNotPersist | 比率類 0/100/-5/120、利率 -0.5、年限 0/-1、金額類 -1、年份 -1 逐項覆蓋 SC「錯誤」清單；驗算利率 0 合法、非法值不落庫（DB 值維持 30）皆驗證 |
| SC-056 | house-params | test_house.py::TestAssessTriggersUnsetParamsNeutralPosture／TestBucketProgressUnsetTarget／TestAffordableTotalPriceUnsetIncome／TestHousePageAffordabilityMetricUnsetIncomeDisplay | 收入門檻/現金地板/目標總價未設定時不誤判達標、分母固定 5、進度不呈現百分比等邊界皆對齊；「不得呈現可負擔 0 元」半句已由 Task 2-10 修正 production 並補 view 層 test，複查對齊（見上方「已解決」1） |
| SC-057 | holding-purpose | test_settings_view.py::TestNewHoldingPurposeSelectbox／TestEditExistingHoldingPurposeSelectbox | 值域僅一般/購屋、新增預設一般、購屋↔一般雙向編輯持久化、改其他欄位不動用途、負債項目同樣可標記，皆對齊 |
| SC-058 | holding-purpose | test_holding_master.py::TestHoldingPurposeIsPurelyAdditive | 分類佔比/報酬率/配置偏離/淨值四項計算前後完全一致；用途正反改動不影響既有欄位，皆對齊（見下方備註：其中 1 個 test 標籤精準度可再議，非行為錯誤） |
| SC-059 | holding-purpose | test_bootstrap.py::TestHoldingsPurposeMigrationLegacyUpgrade／TestHoldingsPurposeMigrationFreshDb | 舊庫 3 筆自動補一般、既有欄位無遺失、可再編輯為購屋、`ensure_schema` 重跑 2/3 次冪等、新庫直接支援，皆對齊 |
| SC-060 | holdings-csv | test_data_io.py::TestHoldingsCsvPurposeRoundtrip | 匯出欄序含用途且附加於尾端、匯出入往返後購屋/一般保留，皆對齊 |
| SC-061 | holdings-csv | test_data_io.py::TestLegacyHoldingsCsvWithoutPurposeColumn | 僅 6 欄舊格式仍匯入成功並補一般、新格式留白同樣補一般，皆對齊 |
| SC-062 | house-bucket | test_house.py::TestBucketValueSumsHouseHoldings | 600,000+400,000=1,000,000（一般 500,000 不計）；無月度紀錄回退初始市值；無購屋項目為 0；最新月市值 0 不回退初始值；出清後不回退；市值留空不貢獻，皆逐條對齊 SC 行為與邊界 |
| SC-063 | house-bucket | test_house.py::TestBucketProgress | 目標 1,500,000／缺口 500,000／進度 66.67%／速率 250,000 與 SC 給值一致；超額不封頂 106.67%、剩 1 年速率=缺口全額、恰 100% 三邊界皆覆蓋 |
| SC-064 | house-bucket | test_house.py::TestBucketProgressTargetYearBoundaries | 目標年=當年/已過/未設定三態皆不呈現速率、不除以零，與 SC 一致 |
| SC-065 | house-bucket | test_house.py::TestBucketCompositionWarning | 剩 8 年一般強度、剩 5 年強化／6 年一般（邊界值精確覆蓋）、已到/已過強化、全現金不警示、目標年未設定僅一般強度，皆對齊 |
| SC-066 | house-triggers | test_house.py::TestHousePageAllTriggersMetShowsCanStart | 5/5 全達成、AppTest 渲染「可啟動購屋」與逐條「✅ 達成」，對齊 |
| SC-067 | house-triggers | test_house.py::TestHousePageNotAllTriggersMetShowsGapList | 3/5、不顯示可啟動、缺口清單含實際值與門檻值（收入）、主觀條件顯示未勾選（認知），對齊 |
| SC-068 | house-triggers | test_house_params.py::TestSubjectiveTriggerPersistence | 無紀錄回空清單、勾選持久化、定錨與認知互不影響、取消勾選持久化、容器重建後仍保留，皆對齊 |
| SC-069 | house-triggers | test_house.py::TestCashReserveValue／TestAssessTriggersDownPaymentDualThreshold | 雙門檻缺一不可（bucket 達標但地板不足 / 反之）、購屋標記現金不計入預備金、地板未設定 fail-closed、一般用途非現金分類不計入，皆對齊 |
| SC-070 | house-triggers | test_house.py::TestAssessTriggersExactBoundaryEquality | 三條件恰等於門檻皆判成立；差一單位（89,999／1,499,999／40.1%）皆判不成立，對齊 |
| SC-071 | house-summary | test_overview.py::TestHouseServiceOverviewSummary／TestOverviewPageHouseSummary／TestOverviewPageHouseSummaryMatchesHousePage | 66.7%＋3/5 組合、目標未設定時進度「—」但觸發計數照常、總覽頁與買房頁口徑逐一比對相同，皆對齊 |
| SC-072 | affordability-engine | test_affordability.py::TestForwardZeroIncome／test_house.py::TestAssessTriggersPaymentConditionFailClosedOnUnsetIncome | 月收 0 時 `income_share_pct` 回傳 None（非 0%、非例外），其餘欄位正常計算；「月付觸發條件 fail-closed」半句已於本階段補 test 直接斷言 `payment.met is False`，複查對齊（見上方「已解決」2） |
| SC-073 | holdings-csv | test_data_io.py::TestHoldingsCsvInvalidPurposeValue | 非法用途值（"vacation"）拒絕整批匯入且錯誤訊息點名該值，對齊 |

### 備註（非阻擋，供第二段參考）

- `tests/test_affordability.py::TestSamePurePureFunctionConsistency::test_sc052_same_input_yields_same_result_across_calls`
  標記 SC-052，但驗證的是「同輸入兩次呼叫結果相同」（純函式無隱藏狀態），SC-052 本文未描述
  此性質。不算不對齊（不違反 SC-052 給值），但嚴格說不是在驗證 SC-052 寫的行為，屬額外品質
  保證測試，掛錯 SC 標籤的可能性較高。建議可保留（低成本），無需列入本階段修正範圍。
- `tests/test_holding_master.py::TestHoldingPurposeIsPurelyAdditive::test_sc058_new_holding_defaults_to_general_purpose`
  標記 SC-058，但驗證內容（新增時預設一般）其實是 SC-057「邊界」段落的行為，SC-058 本文講的
  是「用途標記純附加、不影響既有計算」。`tests/test_settings_view.py` 已有 SC-057 標記的同義
  test（`test_sc057_new_holding_without_selecting_purpose_defaults_to_general`）於 view 層
  覆蓋同一行為，此處屬 repository 層重複驗證，非缺漏，只是 SC 標籤可再精準化。不影響核准判定。

<!-- scenario-mapper subagent 產出（AI 比對 SC 描述 vs test 內容，分「不對齊」「對齊」兩類）-->
