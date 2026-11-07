# Task t02: 常數、例外、共用轉換、結果模型

## 滿足 Scenarios
- 無新增 SC 由 RED 轉 GREEN（純基礎型別與常數；行為由 t03 以後各 Task 的 SC 驗證）

## 實作範圍
- src/asset_lab/core/constants.py（design §1：`CITY_*` 常數、`HOUSE_TRIGGER.LABEL` 等）
- src/asset_lab/core/exceptions.py（`CityLayoutError`）
- src/asset_lab/core/utils.py（`records_frame_to_models` 等 §3 共用轉換）
- src/asset_lab/models/results.py（§4 城市結果模型，pydantic frozen）
- src/asset_lab/views/house.py（`_TRIGGER_LABEL` 改用 `HOUSE_TRIGGER.LABEL`，顯示文字不變）
- tests/test_core_utils.py（共用轉換測試）
- tests/test_house.py（既有，確認標籤重構不破壞）

## 依賴
- t01

## 切片理由
design 實作順序約束第 4 點：常數先於 presentation 與 JS。把所有後續 Task 共用的型別與常數獨立成一個低風險 commit，讓 t03～t07 專注各自邏輯；買房頁標籤改動是文字不變的重構，一併收斂。
