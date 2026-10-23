# Task t08: 移除項目間轉移 Service/Repository 方法與測試

## 滿足 Scenarios
- SC-085 (邊界，本 Task 僅負責刪除 accumulate 相關測試 test_sc085_accumulate_failure_rolls_back_all_writes；其餘 SC-085 斷言由 t01、t07 完成)

## 實作範圍
- src/asset_lab/services/monthly_input_service.py（刪除 build_transfer_pair）
- src/asset_lab/services/cost_basis_service.py（刪除 transfer_records_to_write）
- src/asset_lab/repositories/record_repository.py（刪除 accumulate_net_investments、_ACCUMULATE；docstring 的 compound method 清單同步）
- tests/test_monthly_input.py（刪除 TestBuildTransferPair、TestTransferInputGuard、accumulate 測試群，含 test_sc085_accumulate_failure_rolls_back_all_writes；對應已 REMOVED 的 SC-008/037/086）
- tests/test_cost_basis.py（刪除 TestTransferRecordsToWrite；對應 SC-079/080）

## 依賴
- t07（View 已不再呼叫轉移方法）

## 切片理由
純刪除型 Task，放在 View 切換之後才不破壞既有功能；獨立 commit 讓「移除功能」與「新增功能」的 diff 分開，便於審查與回滾。
