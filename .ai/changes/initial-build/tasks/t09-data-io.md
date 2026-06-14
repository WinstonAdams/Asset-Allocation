# Task t09: DataIoService — CSV 匯出/匯入整形與驗證

## 滿足 Scenarios
- SC-031 (happy) — 匯出 CSV 含完整紀錄並可匯入空庫還原一致
- SC-032 (錯誤) — 匯入 CSV 須驗證格式與唯一鍵避免污染

## 實作範圍
- `src/asset_lab/services/data_io_service.py`（export_holdings_csv/export_records_csv/export_targets_csv：含表頭 bytes；parse_and_validate：表頭齊全、(holding_id, year_month) 唯一鍵不重複、kind/分類合法、目標庫非空拒絕，失敗拋 DataValidationError）
- `tests/test_data_io.py`（SC-031、SC-032 對映）

## 依賴
- t08（匯入還原需 Repository.replace_all 批次寫入與「目標庫是否為空」查詢；匯出整形吃 read_all 產出）

## 切片理由
DataIoService 的整形與驗證為純運算（model↔DataFrame↔CSV bytes、唯一鍵/合法性檢查），可用固定 model 清單與構造的瑕疵 CSV（缺表頭、重複鍵、非法 kind、非空庫）pytest 斷言匯出位元組與驗證拒絕路徑（SC-032 四種錯誤）。但 round-trip 還原一致（SC-031）需與 Repository 的 replace_all 協作，故依賴排在 t08 之後。整形邏輯本身（Service）與批次寫入（Repository t08 已提供）職責分離，符合 AD-9。
