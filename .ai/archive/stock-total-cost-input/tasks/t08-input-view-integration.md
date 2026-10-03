# Task t08: views/input.py 整合 — 股票/ETF 分類切換輸入與轉移過濾

## 滿足 Scenarios
- 無新增（業務行為已由 t02～t04 的 Service 層 SC-074~080 測試保證；本 Task 為 Container 組裝與 View 層委派/UI 機制的整合更新，不含新的業務判斷）

## 實作範圍
- src/asset_lab/bootstrap.py（`Container` 新增 `cost_basis_service: CostBasisService` 欄位；`build_container` 以 `CostBasisService(cost_basis_categories=COST_BASIS_INPUT.CATEGORIES)` 組裝）
- views/input.py（`_render_record_editor` 依 `cost_basis_service.uses_cost_basis(holding=...)` 分流；新增 `_render_cost_basis_editor`：三個 `amount_input`（總成本／現值／已實現收益）＋存檔前呼叫 `derive` 顯示前期總成本與推算淨投入預覽（`is_transition_estimate` 時額外標示過渡估算）；儲存走 `plan_save`→`upsert_records`、刪除走 `plan_delete`→`delete_record_and_upsert`；非股票/ETF 欄位改用 `amount_input`＋`parse_amount`；轉移改走 `build_transfer_pair`→`transfer_records_to_write`→非空清單才 `upsert_records`，空清單（兩端皆股票/ETF）時 `st.info` 提示為合法情況而非錯誤）
- tests/test_bootstrap.py（`test_build_container_wires_services` 擴充：斷言 `container.cost_basis_service` 為 `CostBasisService` 且分類集合等於 `COST_BASIS_INPUT.CATEGORIES`）
- tests/test_input_view.py（機械式更新：金額欄 `at.number_input`→`at.text_input`；`_StubHoldingRepo` 補 `category`；`_StubRecordRepo` 補 `upsert_records`；容器替身補 `cost_basis_service`）

## 依賴
- t01（Repository compound 寫入方法）
- t02（`uses_cost_basis`／`derive`）
- t03（`plan_save`／`plan_delete`）
- t04（`transfer_records_to_write`）
- t06（`amount_input` 元件）

## 切片理由
待所有下層 Service 與 UI 元件就緒後才整合到頁面，符合「純邏輯先做、外部 I/O／Streamlit 後串」；本頁本身不新增業務判斷，只做委派與呈現，機械式的既有 UI 測試更新集中在此一個 commit，避免與下層邏輯變更混在一起難以個別回滾。
