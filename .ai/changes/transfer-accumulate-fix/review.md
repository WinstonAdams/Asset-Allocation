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

<!-- rules-reviewer subagent 產出（工程準則全面符合度檢查）-->

## 3-4 行為對映審查

<!-- scenario-mapper subagent 產出（AI 比對 SC 描述 vs test 內容，分「不對齊」「對齊」兩類）-->
