# Task t03: ReturnService — MWR/XIRR 管線與不收斂降級

## 滿足 Scenarios
- SC-015 (happy) — MWR 以 XIRR 計算現金流年化報酬
- SC-016 (錯誤) — MWR/XIRR 無法收斂時降級不拖垮其他指標

## 實作範圍
- `src/asset_lab/services/return_service.py`（新增 `compute_mwr`，回傳 (mwr, status)；接 pyxirr）
- `tests/test_return.py`（新增 SC-015、SC-016 對映 test 函式）

## 依賴
- t02（同檔 ReturnService、共用序列前處理）

## 切片理由
MWR 管線引入外部數值求解器（pyxirr）與「不收斂回 None + status 旗標」的降級建模（AD-5），與 t02 的閉式 TWR/P&L 性質不同：求解結果需以容差斷言、不收斂路徑須獨立構造現金流觸發。獨立成 commit 讓 pyxirr 整合與降級邏輯的回滾粒度與閉式管線分開；同時 BR-4e 護欄（compute_mwr 簽名只吃 initial_market_value、不吃 initial_cost）在此再次落實，與 t02 共享同一型別隔離原則。
