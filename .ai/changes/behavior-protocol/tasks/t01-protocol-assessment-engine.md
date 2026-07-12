# Task t01: 協定等級判定引擎（ProtocolService.assess，純運算）

## 滿足 Scenarios
- SC-043 (happy) — 回撤基準以累積 TWR 成長指數計算、歷史高點納入起始建倉基準 1.0
- SC-044 (happy) — 回撤深度對應 L0/L1/L2/L3 四級，達門檻即進入較深一級
- SC-045 (邊界) — 累積 TWR 有效月數不足 3 時退回 L0 並回報「無資料 / 資料不足」，不誤報大跌

## 實作範圍
- src/asset_lab/models/protocol.py（新增 `ProtocolThresholdModel`、`ProtocolThresholds`；純資料）
- src/asset_lab/models/results.py（新增 `ProtocolStatus`，與既有 Result models 並列）
- src/asset_lab/core/constants.py（新增 `PROTOCOL_MIN_DATA_MONTHS = 3`、`PROTOCOL_LEVEL_CODE`）
- src/asset_lab/services/protocol_service.py（新增 `ProtocolService`，本 Task 僅實作 `assess(*, series, thresholds, min_data_months)`；建構子無依賴、不 import streamlit/libsql）
- tests/test_protocol.py（SC-043/044/045）

## 依賴
- 無

## 切片理由
最底層純運算，無任何 I/O、無 streamlit、建構子無依賴——最先獨立成 commit，餵固定累積 TWR 序列即可 pytest 驗回撤指數、四級邊界（含恰等門檻）與資料不足退回。`assess` 消費既有 `CumulativeTwrPoint`（不改 ReturnService），`thresholds` 以參數注入，故本 Task 建立 `ProtocolThresholds` model 但門檻的持久化/預設補齊延到 t02。`validate_thresholds` / `effective_thresholds` 亦為純運算，但因其對應 SC（046/047）的測試綁在門檻設定切片，故與 repo 一起放 t02，避免實作與測試跨 commit 分離。

## 備註
- 測試基礎設施（`tests/conftest.py` 的 scenario marker、`pyproject.toml` pytest 設定）既有專案已建立，本 Task 不需重建。
