# Task t05: AllocationService — 佔比/淨值/漂移純運算（含負債排除）

## 滿足 Scenarios
- SC-010 (happy) — 淨值等於總資產減總負債
- SC-011 (邊界) — 負債排除於配置佔比與報酬率之外
- SC-025 (happy) — 配置圓餅圖資料：選定月份資產佔比不含負債（佔比資料層）
- SC-026 (happy) — 配置漂移堆疊面積圖資料：各分類佔比隨月份變化（drift_series 資料層）
- SC-027 (happy) — 淨值折線圖資料：跨月趨勢可疊加總資產/總負債（net_worth_series 資料層）

## 實作範圍
- `src/asset_lab/services/allocation_service.py`（snapshot、net_worth_series、drift_series；權重一律 % 0–100；僅資產，負債排除於佔比）
- `tests/test_net_worth.py`（SC-010、SC-011 對映）
- `tests/test_allocation.py`（SC-025、SC-026、SC-027 佔比/淨值/漂移**資料層**對映）

## 依賴
- t01（models、constants）

## 切片理由
AllocationService 同為**純運算、無 I/O、無 Streamlit**，與 ReturnService 平行不互相依賴，但邏輯量較小且口徑單純（加總與佔比），獨立成切片。淨值（SC-010）、負債排除（SC-011）、佔比/淨值/漂移序列（SC-025~027 的資料計算部分）皆出自此 Service，可用固定月度紀錄 pytest 直接斷言佔比百分比與淨值。SC-025~028 的「圖表呈現」部分（Plotly 渲染）屬 Page/charts 元件，留待 t10 串接；此切片只覆蓋可純測的資料層。SC-028 報酬率走勢圖資料來自 ReturnService 累積 TWR，其資料層已含於 t04，圖表渲染同留 t10。
