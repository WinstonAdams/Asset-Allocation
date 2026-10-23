# Task t04: 保險併入 CostBasisService 累計成本鏈

## 滿足 Scenarios
- SC-095 (happy)
- SC-096 (錯誤)
- SC-097 (邊界)
- SC-098 (邊界)
- SC-099 (happy，Service 層 build_premium_prefill；View 層由 t07 完成)

## 實作範圍
- src/asset_lab/services/cost_basis_service.py（建構子新增 premium_categories；新增 derive_premium / plan_save_premium / build_premium_prefill；plan_delete 守門放寬為股票/ETF 或保險；此階段先不刪除 transfer_records_to_write，留給 t08）
- src/asset_lab/models/results.py（新增 PremiumEditorPrefill；NetInvestmentDerivation docstring 補保險語意）
- src/asset_lab/models/record.py（MonthlyRecordModel docstring 更新）
- src/asset_lab/bootstrap.py（CostBasisService 注入 premium_categories）
- tests/test_cost_basis.py（service fixture 補 premium_categories；新增保險測試）
- tests/test_bootstrap.py（補注入值斷言）

## 依賴
- t03（使用 PREMIUM_INPUT 常數）

## 切片理由
保險重用股票既有的累計成本鏈與過渡估算，與活存/定存推算互不相干，獨立成 commit 以便回滾。建構子新增參數與 bootstrap、fixture 同步修改，維持每個 commit 可執行；View 尚未切換，既有流程不受影響。
