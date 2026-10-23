# Task t06: 資產配置頁各項目市值趨勢圖

## 滿足 Scenarios
- SC-104 (happy)
- SC-105 (邊界)

## 實作範圍
- src/asset_lab/models/results.py（新增 HoldingValueTrend、對應序列 model）
- src/asset_lab/services/allocation_service.py（新增 holding_value_trend）
- src/asset_lab/charts.py（新增 holding_value_lines）
- views/allocation.py（新增 _render_holding_trend，置於淨值趨勢之後；docstring 同步）
- tests/test_allocation.py
- tests/test_charts.py

## 依賴
- 無（與其他 Task 無資料或程式依賴，順序僅為排程；可在任一處插入）

## 切片理由
趨勢圖自成一條垂直切片（Service → 圖表元件 → 配置頁），與錄入流程完全解耦，獨立 commit、獨立回滾。純運算與純函式先行，頁面僅委派。
