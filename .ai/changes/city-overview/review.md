# Review: [Change 名稱]

## 3-1 程式碼清理

掃描範圍：25 個 .py 檔 + city.js/css，main...HEAD（ruff 全綠；vulture 未安裝，跳過）

### 自動掃描

Checker 命令：`python .claude/skills/spec-driven-flow/scripts/checkers/runner.py --phase 3-1 --project-dir . --diff-base origin/main --json`（本機無 origin/main 仍成功執行）
總違規：41 條
Baseline 命中：0 條
完整報告：`.ai/changes/city-overview/.cache/checker_3_1.json`

逐條復核：
- change_level_id_comments（1，tests/test_overview.py:598）— 確認屬實，列 SAFE。
- duplicate_code（35 條）— 偽陽性：皆為 import 區塊與 keyword 引數清單（bootstrap 組 CityService、測試 `_city_service()`、各測試檔 fixture 參數）；無實質可抽象的重複，不處理。（如要豁免可補 `# checker:noqa duplicate_code`，建議不補。）
- function_too_large（3）— `layout.check`(56 行，測試用衝突檢查)、`CityService.frame_at`(72 行含 25 行 docstring，實際邏輯約 45 行)、`test_sc145_...`(74 行)。皆為線性流程，拆分收益低，列 SUGGEST 不動。
- file_too_long（2）— `city/layout.py` 713 行、`tests/test_city_service.py` 751 行；屬移植試做演算法與整合測試，拆檔屬結構決策，列 RISKY。

### SAFE
- `tests/test_overview.py:598` — 註解 `# ---- 城市總覽整合（SC-151、160、161、162）` 引用 SC 編號（checker 已標），改為描述性註解「城市總覽整合」。
- 其餘：無未使用 import／變數、無 print／debug／TODO／FIXME（src、views、city.js 皆查過；checker 未報、人工確認）。

### CAREFUL
- `views/overview.py:_to_month_records`、`views/house.py:_to_month_records` — 與本次新增的 `core/utils.records_frame_to_models` 逐行相同（checker 未報出）。新 util docstring 自述「與買房頁、總覽頁私有的轉換同口徑」。可改為呼叫共用函式並刪除兩份私有版。風險：這兩份是既有程式碼，overview 版 docstring 明載「頁面各自編排的可接受重複，見 design 已知限制」，與設計決策相關；且 house.py 非本次設計範圍。建議：僅在使用者同意時才收斂（測試若 patch 私有名稱需同步調整，已 grep：僅兩 view 自身使用）。

### RISKY
- `src/asset_lab/city/layout.py` 713 行 — 超過 500 行上限；為移植試做演算法，拆檔會動 import 結構與測試，建議留待 3-3 規則審查判斷，不在清理自行處理。
- `tests/test_city_service.py` 751 行 — 同上，可依 timeline／frame 拆兩檔，需使用者決定。

### SUGGEST
- `services/city_service.py:CityService.frame_at` — 已拆出 `_weather_at/_site_at/_buildings_at`，主流程可接受，不建議再拆。
- `city/layout.py:check` — 結尾「畫布邊界」段（約 10 行）可抽成 `_outside_canvas`，純美化，可不做。
- `tests/test_city_service.py::test_sc145_latest_month_matches_existing_page_results` 74 行 — 可抽 helper，可不做。
- `core/constants.py` 檔頭 `AD-7`、`views/overview.py` 的 design 引用 — AD-7 為既有（非本次 diff），不處理。

### 修正結果（第二段）

- `tests/test_overview.py` — SC 編號註解改為「城市總覽整合」。
- `views/overview.py`、`views/house.py` — 刪除私有 `_to_month_records`（含「可接受重複」docstring 說法），改呼叫 `core.utils.records_frame_to_models`；移除不再使用的 `MonthlyRecordModel`、`pandas` import。
- layout.py / test_city_service.py 長度：不拆，交 3-3 判斷。
- 驗證：pytest 1104 passed；ruff check 全綠；scenario_lint 無本分支新增問題（既有技術債不計）。

## 3-2 安全性審查

<!-- security-reviewer subagent 產出（涉及認證/付款/個資時才執行） -->

## 3-3 規則符合度審查

<!-- rules-reviewer subagent 產出（工程準則全面符合度檢查）-->

## 3-4 行為對映審查

<!-- scenario-mapper subagent 產出（AI 比對 SC 描述 vs test 內容，分「不對齊」「對齊」兩類）-->
