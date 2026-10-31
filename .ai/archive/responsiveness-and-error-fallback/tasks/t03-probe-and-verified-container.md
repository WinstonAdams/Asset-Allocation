# Task t03: 連線檢查改為每程序建表一次加每次執行最多探測一次（verified_container）

## 滿足 Scenarios
- SC-108 (happy)
- SC-109 (happy)
- SC-110 (錯誤)
- SC-115 (邊界)

## 實作範圍
- src/asset_lab/repositories/health_repository.py（新增 ConnectionHealthRepository.ping）
- src/asset_lab/bootstrap.py（Container 新增 health_repo、新增 ensure_schema_once、改寫 _with_reconnect_on_stale_stream 簽名與 get_resilient_container、get_container 不再執行 ensure_schema、on_reconnect 記 WARNING 並 mark_reconnected）
- src/asset_lab/rerun_runtime.py（新增 CONTAINER_SESSION_KEY、verified_container，含 expire_if_stale 入口判定與本次暫存，並由 rerun_scope 離開時清暫存）
- app.py（以 verified_container() 取代 get_resilient_container 與 session 寫入）
- tests/test_bootstrap.py（SC-042 重連 4 測試改用 health_repo.ping 與新參數；新增重連不重新建表、on_reconnect 被呼叫）
- tests/test_rerun_runtime.py、tests/test_probe_roundtrips.py（以 :memory: libsql 與真實分層，比較兩次執行 total_roundtrips 差值）
- tests/test_input_view.py、tests/test_house.py、tests/test_app_guard.py（補 get_resilient_container 替身 fixture／回歸）

## 依賴
- t01
- t02

## 切片理由
探測必須走不經快取的計數層，且 TTL 到期判定與「整輪只驗一次」都落在 verified_container，所以放在 t02 之後。bootstrap 重連邏輯與 verified_container 同為「執行入口驗證」，一起改才不會出現 app.py 與重連函式簽名不一致的中間狀態。這是主要提速來源，先於 fragment 與 callback，後者都依賴 verified_container。
