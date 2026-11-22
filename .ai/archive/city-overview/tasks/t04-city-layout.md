# Task t04: 版位純模組（layout_city、check、快取）

## 滿足 Scenarios
- SC-152 (分區、名稱牌不擋建築、不重疊、落在畫布內)
- SC-153 (確定性、跨月位置不動、30 棟 50ms)
- SC-154 (精簡名稱牌旗標；降級的視覺部分為人工目視)
- SC-163 (版位無法排出時的 `CityLayoutError` 路徑)

## 實作範圍
- src/asset_lab/city/layout.py（design §7、AD-8：frozen 輸入輸出、`functools.lru_cache`）
- tests/test_city_layout.py

## 依賴
- t03

## 切片理由
版位演算法與 `CityService` 互不依賴（design 約束第 2 點），先於資料組裝完成，並移植試做的六項檢查。與資料層分開 commit，失敗時回滾面積小。
