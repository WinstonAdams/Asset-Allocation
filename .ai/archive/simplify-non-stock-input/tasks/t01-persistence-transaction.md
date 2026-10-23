# Task t01: 寫入交易工具、PersistenceError 與月度紀錄批次寫入轉譯

## 滿足 Scenarios
- SC-085 (邊界，Repository 層：批次寫入失敗 rollback 並拋 PersistenceError、__cause__ 保留原始錯誤、commit 失敗也 rollback、rollback 失敗仍拋 PersistenceError；View 層由 t07 完成)

## 實作範圍
- src/asset_lab/core/exceptions.py（新增 PersistenceError(AssetLabError)，預設為友善訊息、不內插原始錯誤）
- src/asset_lab/repositories/transaction_repository.py（新增 write_transaction context manager 與 TransactionRepository.transaction）
- src/asset_lab/repositories/record_repository.py（upsert_records、delete_record_and_upsert 改用 write_transaction；簽名不變；此階段不刪除 accumulate_net_investments，留給 t08）
- src/asset_lab/bootstrap.py（Container 新增 transaction_repo，與其他 Repository 共用同一條連線）
- tests/test_monthly_input.py（既有 test_sc085_* 的 pytest.raises(RuntimeError) 改斷言 PersistenceError 與 __cause__；新增 commit 失敗、rollback 失敗兩種邊界；accumulate 測試群暫留）
- tests/test_bootstrap.py（補 transaction_repo 斷言與同連線斷言）

## 依賴
- 無

## 切片理由
交易邊界與例外轉譯是純基礎設施，且 t02（CSV 匯入）、t07（錄入頁）都依賴它，先獨立成 commit。簽名不變、只改失敗時的例外型別，既有頁面的 except AssetLabError 自然接住，不破壞既有功能。
