# Task t02: MonthlyInputService 新增純方法（單列帶入值 + 本月已存紀錄彙總）

## 滿足 Scenarios
- SC-087（happy，新增）— 一般分類月度錄入框帶入當月既有值
- SC-089（happy，新增）— 月度錄入頁顯示本月已存紀錄表格並提醒市值未填項目

## 實作範圍
- src/asset_lab/models/results.py（新增 `RecordEditorPrefill`、`MonthRecordRow` 兩個純資料模型）
- src/asset_lab/services/monthly_input_service.py（新增 `build_record_prefill(*, records, holding_id, year_month) -> RecordEditorPrefill`：沒有該 (holding_id, year_month) 的紀錄時回現行預設（market_value=0 的現行預設語意、net_investment=0）；有紀錄時照存的值帶入，market_value 為 None 時帶入空白；新增 `summarize_month(*, records, holdings) -> list[MonthRecordRow]`：依 `records` 原順序每筆組裝一列（項目名稱從 holdings 對應、市值、淨投入、總成本、已實現收益），`market_value_missing = market_value is None`，不另外判斷分類）
- tests/test_monthly_input.py（新增 `build_record_prefill` 測試：該月無紀錄回現行預設、有紀錄照值帶入、market_value 為 NULL 時帶入空白；新增 `summarize_month` 測試：多筆依序組裝且項目名稱正確對應、`market_value_missing` 判斷含負債列、當月無任何紀錄時回空清單）

## 依賴
- 無

## 切片理由
兩個方法皆為零 I/O 的純資料組裝，只讀既有的 `MonthlyRecordModel`／`HoldingModel` 欄位，不需要 t01 新增的 `cash_dividend`，和 t01 的 Repository 原子寫入互不相依，可獨立驗證與回滾。兩者同屬 `MonthlyInputService` 同一檔案、同屬「月度錄入頁的資料組裝」職責，合併一次 commit 比拆成兩個更小的 commit 更省切割成本。
