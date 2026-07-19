# Task t02: ReturnService — TWR 與 P&L/簡單報酬率管線（BR-4e 護欄）

## 滿足 Scenarios
- SC-012 (happy) — TWR 跨月連乘排除當月淨投入
- SC-013 (happy) — 某月額外投入本金不被算成報酬
- SC-014 (邊界) — 建倉月期初市值為 0 不納入連乘
- SC-017 (happy) — 賺賠金額與簡單總報酬率以累積成本起算
- SC-018 (邊界) — 初始成本只影響賺賠不影響 TWR/MWR
- SC-022 (邊界) — 缺月以相鄰有資料月分段連乘
- SC-023 (邊界) — 保險以解約金為市值、已繳保費為初始成本
- SC-024 (邊界) — 某月未更新市值沿用上一個有值月份

## 實作範圍
- `src/asset_lab/services/__init__.py`
- `src/asset_lab/services/return_service.py`（先實作 `compute_twr`、`compute_pnl` 兩管線；建構子）
- `tests/test_return.py`（對映上列 SC 的 test 函式）

## 依賴
- t01（models、core/utils.adjacent_periods、constants）

## 切片理由
ReturnService 是全專案頭號風險（BR-4e 強制隔離初始市值 vs 初始成本），且為**純函式、無 I/O、無 Streamlit**，最適合用固定數列 pytest 餵驗。先做 TWR 與 P&L 兩條不需數值求解器的管線：兩者皆可用閉式公式直接斷言（SC-012 的 33.1%、SC-013 的 5%、SC-017 的 25%、SC-023 的 −16.67%），驗證最確定。缺月分段連乘（SC-022）與市值沿用（SC-024）屬 TWR 的序列前處理邊界，與 TWR 同管線故同切片。MWR/XIRR 牽涉外部求解器與不收斂降級，獨立成 t03 以隔離回滾粒度。三維度彙總（SC-020）依賴本管線與 t03，留待 t04。
