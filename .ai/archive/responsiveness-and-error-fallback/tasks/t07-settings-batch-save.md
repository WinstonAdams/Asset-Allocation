# Task t07: 設定頁門檻與買房參數整批交易寫入

## 滿足 Scenarios
- SC-128 (happy)
- SC-129 (錯誤)

## 實作範圍
- src/asset_lab/repositories/protocol_threshold_repository.py（新增 upsert_thresholds，走 write_transaction）
- src/asset_lab/repositories/house_param_repository.py（新增 upsert_params）
- src/asset_lab/services/protocol_service.py（build_threshold_models）
- src/asset_lab/services/house_service.py（build_param_models）
- views/settings.py（「儲存門檻」「儲存買房參數」改為驗證 → build models → 整批 upsert）
- tests/test_protocol_thresholds.py、tests/test_house_params.py、tests/test_settings_view.py（以 _FlakyConnection 手法在第 N 筆失敗，驗證全部維持原值與友善訊息；替身 repo 提供 upsert_thresholds／upsert_params）

## 依賴
- t01

## 切片理由
與快取、探測、錯誤兜底無相依，只靠既有 write_transaction，可獨立驗證與回滾。排在最後，避免干擾主要提速路徑的前後量測。只依賴 t01 的 logger 命名（views/settings.py）。
