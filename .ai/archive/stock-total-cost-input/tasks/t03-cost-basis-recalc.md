# Task t03: CostBasisService — plan_save / plan_delete（連動重算）

## 滿足 Scenarios
- SC-077 (happy)
- SC-078 (邊界)

## 實作範圍
- src/asset_lab/services/cost_basis_service.py（擴充：`plan_save(*, holding, records, year_month, market_value, total_cost, realized_income)`、`plan_delete(*, holding, records, year_month)`；往後掃描「異動月份之後的所有新制列」依時間順序重算，只回傳推算值有變的列）
- tests/test_cost_basis.py（擴充：SC-077/078 對映，含全新制列與跨越過渡列兩種情境）

## 依賴
- t02（重算依賴 `derive` 的前期總成本公式）

## 切片理由
AD-4 是本 Change 風險最高的邏輯（往後掃描而非字面「只影響緊接下一筆」），獨立成一個 commit 便於單獨審查與回滾；純運算、可用固定紀錄序列窮舉「全新制」與「跨過渡列」兩種邊界，不需要 DB 或 Repository。
