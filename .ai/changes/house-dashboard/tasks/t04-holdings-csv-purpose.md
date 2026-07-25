# Task t04: holdings CSV 契約附加 purpose 欄（向後相容匯入）

## 滿足 Scenarios
- SC-060 (happy)
- SC-061 (邊界)

## 實作範圍
- src/asset_lab/core/constants.py（`CSV_EXPORT.HOLDINGS_COLUMNS` 末端附加 purpose，既有欄序不變）
- src/asset_lab/services/data_io_service.py（`export_holdings_csv` 輸出 purpose；`_build_holdings` 存在時讀 purpose、缺欄補 general；purpose 不列入 `_require_headers` 強制欄位集，AD-8）
- tests/test_data_io.py（擴充：新舊 CSV 兩路徑）

## 依賴
- t03

## 切片理由
CSV 是 purpose 欄位的資料完整性收尾（匯出→清庫→匯入往返不遺失），緊跟 t03 完成，避免「標記已存在但備份即遺失」的中間態拉長。獨立於運算鏈（t05–t08），變更面窄（常數 + 單一 Service），獨立 commit 易回滾；`replace_all` 的 purpose 保留已由 t03 涵蓋，本 Task 只動 CSV 契約兩端。
