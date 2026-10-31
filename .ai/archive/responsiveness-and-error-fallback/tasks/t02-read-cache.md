# Task t02: 連線層讀取快取（ReadCache、CachingConnection）與重新讀取按鈕

## 滿足 Scenarios
- SC-112 (happy)
- SC-113 (happy)
- SC-114 (錯誤)
- SC-116 (happy)
- SC-117 (邊界)
- SC-118 (邊界)
- SC-119 (happy)

## 實作範圍
- src/asset_lab/core/constants.py（新增 READ_CACHE）
- src/asset_lab/repositories/read_cache.py（新增 ReadCache：整批過期、世代、fence）
- src/asset_lab/repositories/connection_layers.py（新增 CachingConnection、CachingCursor）
- src/asset_lab/bootstrap.py（build_container 改為 counted→cached 兩層、新增 get_read_cache、clear_read_cache；schema_repo 接 counted、其餘 Repository 與 TransactionRepository 接 cached）
- app.py（側欄「重新讀取資料」按鈕 on_click=clear_read_cache，放在取容器之前）
- views/data_io.py（「執行匯入」按鈕 on_click=clear_read_cache，AD-4）
- tests/test_read_cache.py、tests/test_connection_layers.py、tests/test_bootstrap.py（build_container 測試更新）、tests/test_data_io.py（SC-117 守門）、tests/test_read_cache_equivalence.py（SC-119 有無快取結果一致、SC-118 去重）、tests/test_app_guard.py／tests/test_page_config.py（回歸）

## 依賴
- t01

## 切片理由
快取放在連線層、對 Repository 以上透明，所以整體是一個內聚單元：ReadCache（純邏輯、假時鐘可測）先於 CachingConnection，再於 build_container 組裝；按鈕與匯入守門是清除快取的兩個入口，與快取同一 commit 才不會出現「有快取卻沒有手動清除」的中間狀態。TTL 到期的入口判定（expire_if_stale 的呼叫）留給 t03 的 verified_container。
