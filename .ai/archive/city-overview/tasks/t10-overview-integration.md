# Task t10: 總覽頁整合（版面順序、錯誤隔離、小卡、量測）

## 滿足 Scenarios
- SC-151 (無月結資料時不掛城市)
- SC-160 (城市在最上方、數字卡固定最新月結)
- SC-161 (滑桿與點擊只重跑城市區塊；結構斷言＋量測 log)
- SC-162 (城市出錯時數字卡照常)
- SC-165 (切頁耗時增加不超過 100ms，人工量測)

## 實作範圍
- src/asset_lab/views/overview.py（`_render_city()` 正式版：讀取、月份滑桿、`frame_at`、小卡 `st.*` 渲染、BR-11 降級；模組 docstring 更新，design §13、AD-9、AD-10）
- tests/test_overview.py（`test_sc151_*`、`test_sc160_*`、`test_sc161_*`、`test_sc162_*`；替身容器補 `city_service`）
- tests/test_read_cache_equivalence.py（確認快取斷言仍成立）
- 人工量測：main 與本分支各切總覽頁 10 次比較 `elapsed_ms` 中位數

## 依賴
- t01、t06、t08、t09

## 切片理由
最後串接所有層；放在最後才能以真實資料與元件驗證頁面行為，並在合併前做效能量測（design 約束第 5 點）。量測超出預算時依 TD-D 觸發條件處理，不自行擴大快取。
