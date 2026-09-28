# Task t04: CostBasisService — transfer_records_to_write（轉移端過濾）

## 滿足 Scenarios
- SC-079 (happy)
- SC-080 (邊界)

## 實作範圍
- src/asset_lab/services/cost_basis_service.py（擴充：`transfer_records_to_write(*, pair, holdings) -> list[MonthlyRecordModel]`，從成對紀錄中濾掉走總成本推算那一端，回傳 0～2 筆）
- tests/test_cost_basis.py（擴充：SC-079/080 對映，含單端股票/ETF 與兩端皆股票/ETF 兩種情境）

## 依賴
- t02（沿用 `uses_cost_basis` 判斷哪一端要濾掉）

## 切片理由
與 t03 同樣依賴 t02 但彼此獨立（轉移過濾不涉及連動重算），拆開讓兩塊風險不同的邏輯各自成一個可獨立驗證與回滾的 commit；`MonthlyInputService.build_transfer_pair` 簽名與防呆本身不變，不在本 Task 範圍內。
