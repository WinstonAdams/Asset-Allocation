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

<!-- security-reviewer subagent 產出（涉及認證/付款/個資時才執行） -->

## 3-3 規則符合度審查

<!-- rules-reviewer subagent 產出（工程準則全面符合度檢查）-->

## 3-4 行為對映審查

<!-- scenario-mapper subagent 產出（AI 比對 SC 描述 vs test 內容，分「不對齊」「對齊」兩類）-->
