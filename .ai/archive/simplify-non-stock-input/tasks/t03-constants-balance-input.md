# Task t03: 錄入方式常數與活存/定存餘額推算 Service

## 滿足 Scenarios
- SC-092 (happy)
- SC-093 (邊界)
- SC-094 (happy)
- SC-106 (邊界)
- SC-103 (happy，Service 層：活存端自動一出一進；View 層由 t07 完成)

## 實作範圍
- src/asset_lab/core/constants.py（新增 INPUT_MODE、PREMIUM_INPUT、BALANCE_INPUT；INPUT_MODE.BY_ASSET_CATEGORY 由三個分類集合 dict.fromkeys 組出；CSV_EXPORT docstring 補語意）
- src/asset_lab/services/balance_input_service.py（新增 BalanceInputService：derive / plan_save / plan_delete）
- src/asset_lab/models/results.py（新增 BalanceDerivation）
- src/asset_lab/bootstrap.py（Container 新增 balance_input_service 並組裝）
- tests/test_balance_input.py（新增）
- tests/test_bootstrap.py（補 balance_input_service 斷言）

## 依賴
- 無（與 t01、t02 無程式依賴，僅為排程順序）

## 切片理由
純運算且無 I/O，先獨立成 commit；常數一次定義齊（PREMIUM_INPUT、INPUT_MODE 供 t02、t03 使用），避免後續 Task 反覆改 constants。bootstrap 只新增欄位、不動既有注入，不破壞既有功能。
