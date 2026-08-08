# Task t06: 觸發條件檢核（assess_triggers 判定核心）

## 滿足 Scenarios
- SC-056 (邊界)
- SC-069 (邊界)
- SC-070 (邊界)

## 實作範圍
- src/asset_lab/services/house_service.py（新增 `cash_reserve_value` / `assess_triggers`）
- src/asset_lab/models/results.py（新增 `TriggerCondition` / `TriggerChecklist`）
- tests/test_house.py（擴充）

## 依賴
- t01（月付條件消費 `AffordabilityResult.income_share_pct`）
- t02（`HouseParams` / `SubjectiveTriggerModel` 為輸入型別）
- t05（自備條件消費 bucket 值與目標金額口徑；SC-056 的目標總價未設定邊界同時行使 t05 的 `progress_pct` 中性姿態）

## 切片理由
觸發檢核是本 Change 判定密度最高的純運算（雙門檻缺一不可、恰等於邊界含等號、未設定 fail-closed），與頁面呈現分離先行單測，邊界卡（SC-056/069/070）在 Service 層轉 GREEN；happy path 的頁面級呈現（SC-066/067）留給 t07 端到端接線驗證。`cash_reserve_value`（預備金口徑）與消費它的自備條件同 Task 定義，避免口徑分裂。
