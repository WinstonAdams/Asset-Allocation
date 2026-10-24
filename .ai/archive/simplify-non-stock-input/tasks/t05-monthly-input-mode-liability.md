# Task t05: 錄入方式解析、負債應繳金額紀錄與本月紀錄表資料

## 滿足 Scenarios
- SC-005 (happy)
- SC-006 (happy)
- SC-009 (邊界)
- SC-087 (happy，Service 層 build_record_prefill)
- SC-089 (happy，Service 層 summarize_month／is_liability；表格呈現由 t07 完成)
- SC-100 (happy)
- SC-101 (happy，Service 層；View 層由 t07 完成)
- SC-102 (錯誤，Service 層 resolve_input_mode 拋 DataValidationError；畫面提示由 t07 完成)

## 實作範圍
- src/asset_lab/services/monthly_input_service.py（建構子新增 input_mode_by_category / liability_kind / liability_input_mode；新增 resolve_input_mode、build_amount_due_record；summarize_month 每列帶 is_liability；此階段先不刪除 build_transfer_pair，留給 t08）
- src/asset_lab/models/results.py（MonthRecordRow 新增 is_liability）
- src/asset_lab/bootstrap.py（MonthlyInputService 注入新增三個參數）
- tests/test_monthly_input.py（_service() 補參數；新增 SC-005/006/009/087/089/100/101/102 對應測試，修訂過時的手填淨投入敘述）
- tests/test_bootstrap.py（補注入值斷言）

## 依賴
- t03（INPUT_MODE 常數）
- t04（resolve_input_mode 的 PREMIUM 對照需保險分類常數已就緒，並與 CostBasisService 同步注入）

## 切片理由
錄入方式分派與負債處理屬純 Service 邏輯，先於 View 落地，讓 t05 的 View 只需委派。MonthRecordRow 新增欄位為向後相容的附加，既有 View 不受影響。
