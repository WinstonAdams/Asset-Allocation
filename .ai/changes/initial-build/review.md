# Review: [Change 名稱]

## 3-1 程式碼清理

掃描範圍：原始碼 30 檔（src/asset_lab + app.py + pages）＋ 測試 13 檔，20a7ccb..c2d7668（全為 greenfield 新增檔）。
靜態工具：`ruff check .` 全綠（exit 0）；vulture 未安裝（跳過）。
專案脈絡：greenfield、無 utils_v2、AD-8 明定以標準庫 logging 取代 structlog——故 logging 欄位契約偏離不列入本階段清理（屬 AD 既定偏離，3-3 以 ADR 為依據）。

### 自動掃描

Checker 命令：`python .claude/skills/spec-driven-flow/scripts/checkers/runner.py --phase 3-1 --project-dir <資產管理> --diff-base origin/main --json --output .ai/changes/initial-build/.cache/checker_3_1.json`
退出碼：0（正常完成）
總違規：32 條（HIGH 1 / MEDIUM 30 / LOW 1）
Baseline 命中：0 條
完整報告：`.ai/changes/initial-build/.cache/checker_3_1.json`

逐條復核結論：

- **HIGH ×1 `change_level_id_comments`** — `tests/test_monthly_input.py:153` 註解含 `AD-10`。**確認屬實**，已列入 SAFE。注意：本專案 src/tests 內其餘 AD/BR/SC 字樣多為 `@pytest.mark.scenario("SC-xxx")` 標記與 docstring（SSOT test↔scenario 綁定，**必須保留**），唯獨此行是 inline `#` 註解的 dead reference。
- **MEDIUM `function_too_large` ×4**（charts.net_worth_line 51 行、allocation_service.snapshot 52、data_io_service.parse_and_validate 51、return_service._aggregate_monthly 54）— 皆僅略超 50 行門檻，且內部已是線性、單一職責、可讀。**判定不必強拆**（硬拆反增間接層，違背 04 的「函式語意完整優先」），列入 SUGGEST 供斟酌。
- **LOW `file_too_long` ×1**（tests/test_return.py 702 行）— 測試檔，涵蓋 SC-012~024+019/020/021/028 共十餘個情境，**判定可接受**；若 3-1 第二段有餘力可依「TWR / MWR / 三維度 / 走勢」拆檔，列入 SUGGEST。
- **MEDIUM `duplicate_code` ×24** — 絕大多數為**偽陽性 / 不可避免**：bootstrap.py vs test_bootstrap.py 的 repository import 區塊（測試本就須 import 受測對象）、constants.py vs test_data_io.py 的 CSV 欄名清單（前者是 SSOT 定義、後者是測試斷言該契約，移除任一即失去驗證意義）、各測試檔的 `HoldingModel(...)` / `NetWorthPoint(...)` 建構 factory。其中**測試 fixture 重複**（test_allocation / test_net_worth / test_monthly_input / test_charts 的 model 建構）為真實可整合項，列入 SUGGEST（測試輔助，非業務碼，低優先）。

checker **未報出**但人工掃描發現的語意層問題見下方 SAFE / SUGGEST（`adjacent_periods` 死碼、跨 service `_asset_records` 重複、頁面重複 read_range、`"0000-01"` 魔法字串）。

### SAFE

- `src/asset_lab/core/utils.py` — `adjacent_periods`（line 77）為**宣告即死碼**。t01 切片理由聲稱其「被 ReturnService/AllocationService 共用（AD-10 缺月分段連乘前處理）」，但兩個 Service 實際各自內聯分段邏輯（ReturnService 用 `_value_series` + `adjacent` zip、AllocationService 用 `_sorted_data_months`），**全專案無任何 src 端 import**，僅 `tests/test_core_utils.py` 為它而測。屬 TDD/scaffold 殘留。建議：移除 `adjacent_periods` 函式 + 其專屬單元測試（test_core_utils.py:72-106 該測試類）。checker 未報出（vulture 未裝；ruff 不查跨檔死碼）。

- `tests/test_monthly_input.py:153` — 註解 `# 上月已賣出（市值 0 = 出清，AD-10）的項目不帶入...` 含 Change 級編號 `AD-10`（歸檔後成 dead reference）。建議：保留 WHY（出清語意說明確有價值），僅刪去 `，AD-10` marker，改為 `# 上月已賣出（市值 0 = 出清）的項目不帶入新月份；仍持有的照常帶入`。checker 已標（唯一 HIGH）。

### CAREFUL

- 無。本批次無「移除有動態引用風險」的項目；Repository 的 `if TYPE_CHECKING: from libsql import Connection` 屬合法型別提示 import，連線由 bootstrap 延遲 `import libsql` 注入，皆非死碼，**不可移除**。

### RISKY

- 無自行移除即有破壞風險的項目。（`adjacent_periods` 雖列 SAFE，但因 t01 切片理由與實作不一致，移除前建議讓主 AI/使用者確認該函式確無計畫中的後續用途——見交接需決策項。）

### SUGGEST

- `src/asset_lab/services/return_service.py:239` 與 `src/asset_lab/services/allocation_service.py:244` — **跨 service 業務邏輯重複（DRY）**：`_asset_records(range_df, holdings)` 兩處 `@staticmethod` 實作幾乎逐字相同（皆「篩出 kind==ASSET 的 holding_id、過濾 range_df」，即「負債排除」核心口徑）。建議抽為 `core/utils.py` 純函式（無 I/O、無業務流程判斷，符合 §8）或共用 helper，單一定義「資產篩選」口徑，避免日後改負債判定時兩處不同步。checker 未報出（兩段排序/空檢查順序略異，未達連續逐字門檻）。屬 t02~t05 兩平行 Service 疊加後的結構性重複。

- `pages/allocation.py:88,98,111` — 同一頁 render 內 `_render_area` / `_render_net_worth` / `_render_cumulative_twr` 各自發一次 `record_repo.read_range(start_ym="0000-01", end_ym=latest_ym)`，**對 Turso 重複三次全區間讀取**（同參數同結果）。建議在 `render()` 取一次 range_df 後以參數傳入三個子函式（一次 I/O）。屬效能/重複 I/O；雲端 Turso 下三次往返有實際延遲成本。

- `pages/returns.py:77` 與 `pages/allocation.py:88,98,111` — 魔法字串 `"0000-01"` 共出現 4 次，作為「自最早記錄起」的區間下界 sentinel。違反 coding-style §1「禁止散落未定義魔法字串」。建議移至 `core/constants.py` 具名常數（如 `EARLIEST_YEAR_MONTH_SENTINEL = "0000-01"`）。屬命名/魔法字串。

- `src/asset_lab/services/allocation_service.py:34-36`（`_DRIFT_YEAR_MONTH/_DRIFT_DIMENSION_KEY/_DRIFT_WEIGHT`）與 `src/asset_lab/charts.py:28-30`（`_AREA_YEAR_MONTH/_AREA_DIMENSION_KEY/_AREA_WEIGHT`）— 生產者（drift_series 輸出長表欄名）與消費者（堆疊面積圖讀同欄名）各自定義同一組字串常數（`"year_month"/"dimension_key"/"weight"`），為**耦合契約的重複定義**。建議將此長表欄名契約收斂為單一來源（如 constants 或 results 模組常數），兩端引用。低優先。

- `pages/*.py` 的私有 helper（`_container()` 回傳值、`_render_*` 的 `record_repo`/`container`/`holdings` 參數）多數**缺型別提示**（coding-style §3 要求函式參數/回傳填型別）。因 Page 為 Streamlit 黏合層、接的是 Container 已具型別的屬性，影響有限；屬規則符合度範疇，**建議交 3-3 統一判定**，此處僅備註不主動列為清理動作。

- `src/asset_lab/repositories/target_repository.py:59` — `read_all` 僅 `return self.read_targets()`（薄別名）。屬刻意的語意命名（匯出語境用 read_all、設定/偏離用 read_targets，與其他 Repository 的 read_all 對外契約一致），**判定保留**；若日後欲精簡可改 data_io 頁直接呼叫 read_targets。極低優先，僅記錄。

- `tests/test_allocation.py` / `test_net_worth.py` / `test_monthly_input.py` / `test_charts.py` — 重複的 model 建構 factory（`HoldingModel(...)`、`NetWorthPoint(...)`、`points=[...]`，即 checker 報的多筆 MEDIUM duplicate）。可抽共用 fixture 至 conftest.py 或 test helper。屬測試輔助、非業務碼，低優先，第二段有餘力再做。

- `tests/test_return.py`（702 行，checker LOW）— 可依「TWR / MWR / 三維度＋區間 / 走勢」拆為多檔提升可維護性。低優先。

- `asset-allocation-tool-SPEC.md`（repo 根目錄，本次 diff 新增）— 為換資料夾前的「專案規格與決策交接」前置文件，內容已被 `.ai/changes/initial-build/proposal.md` + `design.md` 完整取代。屬已被取代的 scaffold 文件（非程式碼）。**是否移除需使用者決策**（見交接）。

<!-- code-cleaner subagent 產出 -->

## 3-2 安全性審查

<!-- security-reviewer subagent 產出（涉及認證/付款/個資時才執行） -->

## 3-3 規則符合度審查

<!-- rules-reviewer subagent 產出（工程準則全面符合度檢查）-->

## 3-4 行為對映審查

<!-- scenario-mapper subagent 產出（AI 比對 SC 描述 vs test 內容，分「不對齊」「對齊」兩類）-->
