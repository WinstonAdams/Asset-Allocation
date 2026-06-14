# Task t04: 報酬率三維度彙總 + 區間解析（PeriodService）

## 滿足 Scenarios
- SC-019 (邊界) — 未滿 12 個月區間只顯示累積報酬不年化
- SC-020 (邊界) — 報酬率三維度拆整體/分類/單一標的
- SC-021 (happy) — 報酬率計算區間可切換並重算
- SC-028 (happy) — 報酬率走勢圖累積 TWR 折線（**資料層**：逐有資料月累積 TWR 序列；圖表渲染留 t11）

## 實作範圍
- `src/asset_lab/services/return_service.py`（新增 `compute_returns`：彙總 overall/category/holding 三維度，組各維度自身現金流序列，套用未滿 12 月不年化；產出逐有資料月累積 TWR 序列供走勢圖）
- `src/asset_lab/services/period_service.py`（PeriodService.resolve_period，Asia/Taipei 時區）
- `tests/test_return.py`（新增 SC-019、SC-020、SC-021、SC-028 資料層對映 test 函式）

## 依賴
- t03（compute_twr / compute_mwr / compute_pnl 三管線齊備）

## 切片理由
三維度彙總（SC-020）是「以單一標的為原子、分類/整體彙總」的編排層，必須在三條底層管線（t02+t03）齊備後才能組裝；區間解析（SC-021 的 inception/YTD/last_12m/custom）與年化判斷（SC-019 未滿 12 月）是餵給彙總的時間視窗前處理，與彙總同屬「序列範圍決策」故同切片。PeriodService 為純函式（時區換算 + 月份算術），可獨立用固定 latest_ym pytest 驗證 YTD/近一年邊界。此切片完成後 return-calculation 能力（SC-012~024）全數 GREEN，純運算核心收斂完畢，後續才接 I/O。
