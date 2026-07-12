# Task t02: 回撤門檻設定端到端（驗證 + 預設補齊 + 持久化 + 設定頁）

## 滿足 Scenarios
- SC-046 (happy) — 門檻可於設定頁調整並持久化、重啟後生效；未設定 / 缺級時採預設補齊
- SC-047 (錯誤) — 不合法門檻（順序顛倒 / 非嚴格遞增 / 含 0 或負值）被拒絕、不變更既有門檻

## 實作範圍
- src/asset_lab/core/constants.py（新增 `PROTOCOL_LEVEL_DEFAULTS`（L1=10.0/L2=20.0/L3=30.0）、`PROTOCOL_THRESHOLDS_TABLE`（TABLE_NAME/LEVEL/DRAWDOWN_THRESHOLD））
- src/asset_lab/services/protocol_service.py（新增 `effective_thresholds(*, stored)`：以 stored 覆蓋預設、缺級補預設；`validate_thresholds(*, l1, l2, l3)`：檢查 `0 < l1 < l2 < l3`，違反拋 `DataValidationError`）
- src/asset_lab/repositories/protocol_threshold_repository.py（新增 `ProtocolThresholdRepository`，比照 `TargetRepository`：`read_thresholds()` / `upsert_threshold(*, threshold)` 用 `ON CONFLICT(level) DO UPDATE`）
- src/asset_lab/repositories/schema_repository.py（`ensure_schema()` 追加 `CREATE TABLE IF NOT EXISTS protocol_thresholds`，既有三表 DDL 不變）
- src/asset_lab/bootstrap.py（`Container` 追加 `protocol_threshold_repo`、`protocol_service`；`build_container` 以 keyword args 組裝 `ProtocolThresholdRepository(conn=conn)`、`ProtocolService()`）
- views/settings.py（新增 `_render_protocol_thresholds(*, protocol_threshold_repo, protocol_service)` 區段，比照既有 `_render_targets`：載入 `effective_thresholds` 為 number_input 預設，儲存前先 `validate_thresholds` 失敗即 `st.error` 拒絕、不落 DB，通過則對三級各 `upsert_threshold`；納入既有 `try/except AssetLabError`）
- tests/test_protocol_thresholds.py（SC-046/047）

## 依賴
- t01（需 `ProtocolThresholds` / `ProtocolThresholdModel` model 與 `ProtocolService` 類別已存在）

## 切片理由
單一能力（門檻設定）的垂直切片：純運算驗證/預設補齊、DB 持久化、設定頁編輯一次到位，才能對 SC-046（存→讀→重啟仍在→缺級補預設）與 SC-047（非法拒絕）做端到端驗證。完全比照既有 `target_allocations`（表→Repo→Container→設定頁）已驗證路徑，低風險。`protocol_service` 於本 Task 進 Container，後續總覽頁（t03）直接取用。驗證方法（`validate_thresholds`/`effective_thresholds`）與其對應 SC 測試同 commit，符合 TDD「測試與實作不跨 commit 分離」。

## 備註
- 門檻不納入既有 CSV 匯出入（design AD-4 已知限制），本 Task 不動 `data_io_service` / `data_io.py`。
