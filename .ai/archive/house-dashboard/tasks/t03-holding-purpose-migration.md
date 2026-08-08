# Task t03: holdings 用途欄位與兩路徑遷移（含設定頁表單）

## 滿足 Scenarios
- SC-057 (happy)
- SC-058 (邊界)
- SC-059 (邊界)

## 實作範圍
- src/asset_lab/core/constants.py（新增 `HOLDING_PURPOSE`；`HOLDINGS_TABLE` 加 `PURPOSE`）
- src/asset_lab/models/holding.py（`HoldingModel` 加 `purpose` 欄位，預設 general）
- src/asset_lab/repositories/schema_repository.py（`_CREATE_HOLDINGS` 直接含 purpose 欄；PRAGMA table_info 探測 + 條件 ALTER 的 idempotent 加欄遷移，AD-6）
- src/asset_lab/repositories/holding_repository.py（`_COLUMNS` / `_INSERT` / `_UPDATE` / `replace_all` / `_row_to_model` 納入 purpose）
- views/settings.py（`_render_holdings` / `_render_edit_holding` 表單加「用途」selectbox）
- tests/test_bootstrap.py（擴充：舊庫升級 / 新庫直建 / 重複啟動三路徑）
- tests/test_holding_master.py（擴充：純附加不影響既有計算）
- tests/test_settings_view.py（擴充：表單用途欄）

## 依賴
- t02（SC-059 邊界含「全新庫首啟即支援買房參數與主觀勾選儲存」，需 t02 兩張新表已進 `ensure_schema`）

## 切片理由
用途標記是 bucket 口徑（t05）與 CSV 契約（t04）的前置。model + 遷移 + Repo + 表單一次成鏈，切在「既有引擎完全不讀 purpose」的純附加邊界上（BR-9 / D14）——既有 304 測試可即刻驗證不退步，commit 安全、可回滾。遷移（本 Change 唯一偏離既有 ensure_schema 的地方）集中在本 Task，風險隔離。
