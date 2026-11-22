# Task t03: 幾何純模組（高度、坑洞、投影、障礙物、名稱牌、旗桿公式）

## 滿足 Scenarios
- SC-137 (建築高度，含邊界)
- SC-138 (負債坑洞深度)

## 實作範圍
- src/asset_lab/city/geometry.py（`CityGeometry` 與公式，design §6）
- tests/test_city_geometry.py

## 依賴
- t02

## 切片理由
純邏輯、無 I/O，且 design 實作順序約束第 2 點要求先於 layout。與 `city.js` 逐段對照的公式集中於此，獨立 commit 利於審查與回滾。
