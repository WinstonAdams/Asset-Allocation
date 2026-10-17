# Task t01: monthly_records 加欄（total_cost/realized_income）+ Repository I/O 擴充

## 滿足 Scenarios
- SC-006（邊界，既有）— `read_range` 空集合欄位由 4 擴充為 6，行為不變，機械維持通過

## 實作範圍
- src/asset_lab/core/constants.py（`MONTHLY_RECORDS_TABLE` 新增 `TOTAL_COST`、`REALIZED_INCOME`）
- src/asset_lab/models/record.py（`MonthlyRecordModel` 新增 `total_cost: float | None = None`、`realized_income: float | None = None`）
- src/asset_lab/repositories/schema_repository.py（把 `_ensure_holdings_purpose_column` 抽成通用私有 helper `_add_column_if_missing(cursor, *, table, column, alter_sql)`；`_CREATE_MONTHLY_RECORDS` 新庫直接含兩個新欄；`ensure_schema` 對既有庫追加兩個新欄的加欄遷移）
- src/asset_lab/repositories/record_repository.py（`_COLUMNS`/`_row_to_model`/`_values`/`_INSERT`/`_UPSERT` 擴充到 6 欄；新增 `read_holding_records(*, holding_id)`、`upsert_records(*, records)`、`delete_record_and_upsert(*, holding_id, year_month, records)` 三個方法，後兩者為單一交易 compound method，失敗時 `rollback()` 後原樣往上拋）
- tests/test_monthly_input.py（`test_read_range_empty_preserves_columns` 欄位斷言擴充為 6 欄；新增 `read_holding_records`／`upsert_records`／`delete_record_and_upsert` 的 Repository 層測試，含批次寫入成功與中途失敗 rollback 的案例）
- tests/test_bootstrap.py（比照既有 holdings.purpose 遷移測試（`TestHoldingsPurposeMigration*`）的模式，新增 monthly_records 兩個新欄的舊庫升級／新庫直建／重複啟動三路徑測試）

## 依賴
- 無

## 切片理由
本層是後續所有工作（CostBasisService 推算、CSV 契約、View 整合）共用的資料底座，必須最先就緒且獨立成 commit：欄位擴充（AD-2）與 compound 寫入（AD-5）雖分屬不同 ADR，但都集中在 `RecordRepository` 同一檔案、同一次擴充動作，拆開反而增加中間態風險。純 I/O 層可用記憶體 libsql 連線窮舉遷移與交易邊界，不依賴任何業務 Service，回滾風險最低。
