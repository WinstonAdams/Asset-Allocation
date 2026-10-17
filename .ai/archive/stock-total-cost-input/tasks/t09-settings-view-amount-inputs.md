# Task t09: views/settings.py 金額欄改用 amount_input

## 滿足 Scenarios
- 無新增（既有 SC-051 行為不變，僅 widget 機制由 `number_input` 改 `text_input` 的機械式更新；BR-10 放大範圍涵蓋本頁金額欄，視覺效果由 SC-083 的樣式與 2-Z 啟動驗證涵蓋）

## 實作範圍
- views/settings.py（初始市值、初始成本（新增與編輯表單）與四個買房金額參數：目標總價、家庭稅後月收、收入門檻、現金地板，改用 `amount_input`＋`parse_amount`；`_sync_cost_to_market_value` 經 `amount_input(on_change=..., kwargs=...)` 串接，widget key 不改名；比率、年份、年限、利率、目標比重、協定門檻不動）
- tests/test_settings_view.py（機械式更新：`TestInitialValueCostNoDecimal` 斷言改為千分位顯示；`TestNewHoldingCashLikeCategoryCostDefaultsToMarketValue`／`TestEditExistingHoldingCashLikeCategoryCostDefaultsToMarketValue`（SC-051）改用 `at.text_input(key=...)` 與字串值斷言；買房參數欄位測試同步改用 `at.text_input`）

## 依賴
- t06（`amount_input` 元件）

## 切片理由
與 t08（月度錄入頁）是不同頁面、不同檔案，彼此獨立，可平行進行；只依賴 t06 的 UI 元件，不涉及 CostBasisService，故單獨切片、單獨 commit，回滾範圍限於設定頁。
