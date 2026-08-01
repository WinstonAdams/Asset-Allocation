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

<!-- rules-reviewer subagent 產出（工程準則全面符合度檢查）-->

## 3-4 行為對映審查

<!-- scenario-mapper subagent 產出（AI 比對 SC 描述 vs test 內容，分「不對齊」「對齊」兩類）-->
