# Task t03: CostBasisService 已實現損益／現金股利拆分與非負驗證

## 滿足 Scenarios
- SC-074（happy，修訂）— 總成本與前期總成本推算當月淨投入，公式輸入改為已實現損益＋現金股利兩欄相加
- SC-075（邊界，修訂）— 過渡期前期總成本估算，公式輸入同上改為兩欄相加
- SC-076（邊界，修訂）— 清倉月總成本與現值皆填 0，推算淨投入等於負的賣出實收
- SC-078（邊界，修訂）— 連動重算跨越本功能上線前紀錄時影響範圍延伸
- SC-088（happy，新增）— 股票/ETF 錄入框帶入當月既有值，已實現損益與現金股利分開帶回
- SC-090（happy，新增）— 已實現損益與現金股利分開輸入，相加為原已實現收益合計
- SC-091（錯誤，新增）— 現金股利填負數時存檔前即遭拒絕

## 實作範圍
- src/asset_lab/models/results.py（新增 `CostBasisEditorPrefill` 純資料模型）
- src/asset_lab/services/cost_basis_service.py（`derive`／`plan_save` 簽名由 `realized_income` 改為 `realized_pnl` ＋ `cash_dividend`；新增私有 `_derive_from_realized_income(...)`（輸入合計），由 `derive`（驗證後呼叫）與 `_recalculate_following`（已存列直接用存下來的合計呼叫，不需先拆再合）共用；`derive` 開頭檢查 `cash_dividend < 0`，違反拋 `DataValidationError`（訊息帶欄位名稱）；`plan_save` 存檔列寫 `realized_income = realized_pnl + cash_dividend`、`cash_dividend = cash_dividend`；新增 `build_cost_basis_prefill(*, records, year_month) -> CostBasisEditorPrefill`：沒有紀錄回現行預設（四欄皆 0）；有紀錄時 `total_cost`/`market_value` 照存的值（None 帶空白）、`cash_dividend = 存的值或 0`、`realized_pnl = (realized_income 或 0) − cash_dividend`；`transfer_records_to_write` docstring 補一句與 `accumulate_net_investments` 的交接說明，簽名與行為不變）
- tests/test_cost_basis.py（既有呼叫 `derive(...)`/`plan_save(...)` 的 `realized_income=` 參數機械式改成 `realized_pnl=..., cash_dividend=0.0`；直接建構 `MonthlyRecordModel(realized_income=...)` 的測試資料不動；新增 `cash_dividend < 0` 時 `derive`／`plan_save` 皆拒絕的測試；新增已實現損益（含負值）與現金股利相加計入推算公式的測試；新增 `build_cost_basis_prefill` 測試：無紀錄預設、有紀錄分開帶回、`total_cost`/`market_value` 為 NULL 時帶空白、`cash_dividend` 為 NULL 的舊值全數歸為已實現損益）

## 依賴
- t01（`MonthlyRecordModel.cash_dividend` 欄位與 `MONTHLY_RECORDS_TABLE.CASH_DIVIDEND` 常數）

## 切片理由
簽名改變、非負驗證、帶入值拆分都是同一個業務語意變更（已實現收益拆成兩格）在 `CostBasisService` 這一個檔案內的連動後果，且會同時牽動 `tests/test_cost_basis.py` 既有呼叫的參數名稱，拆開會讓測試檔案停在「一半呼叫新簽名、一半呼叫舊簽名」編譯不過的中間態，必須一次完成並獨立成 commit。需要 t01 先把 `cash_dividend` 欄位與常數就緒，才能讀寫完整的 `MonthlyRecordModel`。
