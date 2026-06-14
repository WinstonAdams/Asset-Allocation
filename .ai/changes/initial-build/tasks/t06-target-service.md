# Task t06: AllocationService — 目標偏離與再平衡判定

## 滿足 Scenarios
- SC-029 (happy) — 設定各分類目標比重並顯示現況偏離
- SC-030 (邊界) — 偏離超過門檻標示需再平衡

## 實作範圍
- `src/asset_lab/services/allocation_service.py`（新增 compute_drift：drift = 現況% − 目標%，needs_rebalance = |drift| > 門檻百分點；未設目標的分類不判定）
- `tests/test_target.py`（SC-029、SC-030 對映）

## 依賴
- t05（同檔 AllocationService、snapshot 產出現況佔比作為 compute_drift 輸入）

## 切片理由
目標偏離計算吃 t05 的 AllocationSnapshot（現況佔比）與 TargetAllocationModel（目標 %），是 AllocationService 的延伸純運算。獨立切片是因為它引入新業務語意（門檻判定、邊界=門檻不標示、未設目標不判定，SC-030），與 t05 的佔比/淨值口徑不同，分開 commit 讓再平衡規則的回滾粒度獨立。仍為純函式，可用固定 snapshot + targets pytest 斷言偏離百分點與 needs_rebalance 布林。
