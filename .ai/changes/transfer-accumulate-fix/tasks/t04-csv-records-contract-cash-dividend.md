# Task t04: CSV records 契約附加 cash_dividend

## 滿足 Scenarios
- SC-031（happy，修訂）— 匯出 CSV 含完整紀錄（含 cash_dividend）並可匯入空庫還原一致
- SC-084（邊界，修訂）— 舊格式 CSV（4 欄或前一 Change 的 6 欄，皆無 cash_dividend）仍可匯入，新欄位視為未填

## 實作範圍
- src/asset_lab/core/constants.py（`CSV_EXPORT.RECORDS_COLUMNS` 尾端附加 `"cash_dividend"` 成為 7 欄；`RECORDS_REQUIRED_COLUMNS` 由 `RECORDS_COLUMNS[:-2]` 改為明確固定的 `RECORDS_COLUMNS[:4]`；docstring 補充）
- src/asset_lab/services/data_io_service.py（`_build_records` 比照既有 `total_cost` 的寫法：CSV 有 `cash_dividend` 欄就讀（空白轉 None），沒有該欄就是 None）
- tests/test_data_io.py（匯出欄位斷言擴充為 7 欄；新增兩種舊格式 CSV 匯入測試——4 欄（無 total_cost/realized_income/cash_dividend）與前一 Change 的 6 欄（有 total_cost/realized_income，無 cash_dividend）——驗證 cash_dividend 視為未填、其餘欄位正確還原）

## 依賴
- t01（`MonthlyRecordModel.cash_dividend` 欄位需存在才能完整還原匯入/匯出資料）

## 切片理由
CSV 契約異動集中在常數與 `DataIoService` 同一組檔案，匯入匯出不呼叫 `derive`/`plan_save`，只依賴 t01 的欄位就緒、不依賴 t02／t03 的 Service 行為變更，可獨立於 Service 層重構之外驗證與回滾。
