# Task t01: monthly_records 加欄（cash_dividend）+ 轉移累加 Repository 方法

## 滿足 Scenarios
- SC-006（happy，既有）— `read_range`／`read_holding_records` 等既有欄位組裝因新增 `cash_dividend` 由 6 欄擴充為 7 欄，行為不變、機械維持通過；`test_bootstrap.py` 另補一條「前一 Change 的 6 欄 schema 升級到含 cash_dividend」的遷移路徑
- SC-085（邊界，修訂）— 批次寫入中途失敗不留部分結果的交易保證，延伸覆蓋 `accumulate_net_investments`
- SC-086（happy，新增）— 項目間轉移在既有紀錄上累加淨投入並保留既有市值，含同月多次累加、沒有既有列時新建只有淨投入的空市值列

## 實作範圍
- src/asset_lab/core/constants.py（`MONTHLY_RECORDS_TABLE` 新增 `CASH_DIVIDEND = "cash_dividend"`；docstring 補語意說明）
- src/asset_lab/models/record.py（`MonthlyRecordModel` 新增 `cash_dividend: float | None = None`；docstring 補充 realized_income／cash_dividend 的關係）
- src/asset_lab/repositories/schema_repository.py（`_CREATE_MONTHLY_RECORDS` 新庫直接含 `cash_dividend REAL`；`ensure_schema` 追加一次 `_add_column_if_missing` 遷移既有庫）
- src/asset_lab/repositories/record_repository.py（`_COLUMNS`/`_row_to_model`/`_values`/`_INSERT`/`_UPSERT` 擴充為 7 欄；新增 `accumulate_net_investments(*, records)` compound method：單一交易內對每筆記錄執行 `INSERT ... ON CONFLICT(holding_id, year_month) DO UPDATE SET net_investment = net_investment + excluded.net_investment`，只累加 `net_investment`、其餘欄位（market_value/total_cost/realized_income/cash_dividend）不動；沒有既有列時新建一列，其餘欄位皆 NULL；空清單不做任何事；任一步失敗 `rollback()` 後原樣上拋）
- tests/test_bootstrap.py（比照既有 `TestMonthlyRecordsCostColumnsMigrationLegacyUpgrade`/`...FreshDb` 模式，新增「前一 Change 的 6 欄 schema（即本 Change之前的 `_CREATE_MONTHLY_RECORDS`）→ 升級後含 `cash_dividend`、既有值不變」的遷移測試，含重複呼叫 `ensure_schema` 的 idempotent 驗證）
- tests/test_monthly_input.py（既有 `read_range`/`read_holding_records` 相關欄位斷言擴充為 7 欄；新增 `accumulate_net_investments` 測試：既有列只累加 `net_investment`、其餘欄位不變；沒有既有列時新建只有淨投入、market_value 為 NULL 的列；同一列連續兩次累加逐次相加；空清單無操作；批次中途失敗 rollback 後不留部分結果）

## 依賴
- 無

## 切片理由
欄位擴充（AD-5 的儲存層）與原子累加方法（AD-1）雖分屬不同 ADR，但都集中在 `record_repository.py`／`schema_repository.py` 同一組檔案的同一次擴充動作，拆開會讓 Repository 處於「欄位已加但累加方法未就緒」（或反過來）的中間態。本層純 I/O、可用記憶體 libsql 窮舉遷移與交易邊界，不依賴任何業務 Service，是 t02～t06 共用的資料底座，須最先就緒並獨立成 commit。
