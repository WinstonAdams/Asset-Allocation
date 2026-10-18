# Task t02: CSV 整批匯入改為跨三張表單一交易

## 滿足 Scenarios
- SC-107 (錯誤)

## 實作範圍
- src/asset_lab/repositories/holding_repository.py（新增 replace_all_with_context；刪除 replace_all）
- src/asset_lab/repositories/record_repository.py（新增 replace_all_with_context；刪除 replace_all）
- src/asset_lab/repositories/target_repository.py（新增 upsert_targets_with_context；upsert_target 不變）
- views/data_io.py（_render_import 驗證通過後才開 transaction_repo.transaction()，依序呼叫三個 *_with_context，st.success 放在 with 之後；docstring 補整批單一交易）
- tests/test_data_io.py（新增 test_sc107_*：以真的記憶體 DB 搭配 TransactionRepository，注入中途失敗的 cursor 替身，斷言 PersistenceError 且三張表不變、可重新匯入；確認 SC-031/032 仍通過）

## 依賴
- t01（write_transaction、TransactionRepository、PersistenceError、Container.transaction_repo）

## 切片理由
CSV 匯入是獨立垂直切片，與月度錄入互不相干，獨立 commit 便於回滾。三個 *_with_context 與 data_io 改寫、兩個 replace_all 的刪除必須同 commit，否則刪除會留下呼叫端斷裂。
