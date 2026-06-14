# Task t08: Repository 層 + Schema 建表（libsql I/O）

## 滿足 Scenarios
- SC-001 (happy) — 新增資產項目並記錄分類與初始市值/初始成本
- SC-002 (happy) — 新增負債項目不記分類與初始成本
- SC-003 (happy) — 改項目名稱不影響歷史報酬連乘（穩定 holding_id）
- SC-004 (happy) — 改項目分類後歷史月份以當前分類回溯重算
- SC-006 (happy) — 新增/編輯/刪除某月單一項目紀錄（upsert/delete）
- SC-007 (錯誤) — 同月同項目重複記錄須被拒絕（(holding_id, year_month) 唯一鍵）

## 實作範圍
- `src/asset_lab/repositories/__init__.py`
- `src/asset_lab/repositories/schema_repository.py`（SchemaRepository.ensure_schema：建三表 if not exists）
- `src/asset_lab/repositories/holding_repository.py`（list/get/add/update/replace_all；row↔HoldingModel）
- `src/asset_lab/repositories/record_repository.py`（read_month/read_range/read_all/latest_year_month/upsert/delete/replace_all；複合主鍵唯一約束）
- `src/asset_lab/repositories/target_repository.py`（read_targets/upsert/read_all）
- `tests/test_holding_master.py`（SC-001~004 對映）
- `tests/test_monthly_input.py`（新增 SC-006、SC-007 對映；upsert 不產生重複列、唯一鍵衝突拒絕）

## 依賴
- t01（models、core/constants 的表名欄名 schema、core/exceptions）

## 切片理由
Repository 是所有 I/O 落點，純運算層（t02~t07）完成後才接 I/O，符合「純邏輯先做、外部 I/O 後串」。建表（SchemaRepository）必須與 Repository 同切片，因 Repository 測試需先有 schema 才能讀寫。穩定 holding_id（SC-003）、分類回溯非版本化（SC-004）、複合主鍵唯一性（SC-007）皆由 schema + Repository 的 SQL 保證，故這些 SC 在此 Task 轉 GREEN。測試以記憶體/本地 libsql 連線（in-memory SQLite 相容）建表後驗證 CRUD 與唯一鍵衝突，不依賴遠端 Turso。SC-005/008/009 的帶入與轉移純運算已在 t07，本 Task 補齊月度紀錄的單列 CRUD I/O 行為（SC-006/007）。
