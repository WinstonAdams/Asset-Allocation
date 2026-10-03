# Task t07: CSV records 契約擴充（total_cost/realized_income）

## 滿足 Scenarios
- SC-031 (happy，既有)
- SC-084 (邊界)

## 實作範圍
- src/asset_lab/core/constants.py（`CSV_EXPORT.RECORDS_COLUMNS` 尾端附加 `total_cost`、`realized_income`；新增 `RECORDS_REQUIRED_COLUMNS = RECORDS_COLUMNS[:-2]`）
- src/asset_lab/services/data_io_service.py（`parse_and_validate` 表頭驗證改用 `RECORDS_REQUIRED_COLUMNS`；`_build_records` 讀取兩個新欄，缺欄或空白轉 `None`）
- tests/test_data_io.py（`_records_df()` fixture 擴充為 6 欄；`test_sc031_export_records_has_header_and_all_rows`／`test_sc031_roundtrip_restores_identical_data_into_empty_db` 擴充斷言含新欄；新增 SC-084：僅原本 4 欄的舊格式 CSV 仍可匯入且新欄還原為 `None`）

## 依賴
- t01（`RecordRepository.read_all` 需已回傳 6 欄，`export_records_csv` 才有完整來源可 reindex）

## 切片理由
CSV 契約是獨立的對外介面關注點，不涉及 CostBasisService 或 UI，只依賴 t01 的資料底座；與 t02～t06 完全獨立，可平行進行，故單獨切片、單獨 commit。
