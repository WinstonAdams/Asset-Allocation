# Task t06: widget callback 重連與錯誤處理（guarded_callback、買房勾選）

## 滿足 Scenarios
- SC-111 (happy)
- SC-127 (錯誤)

## 實作範圍
- src/asset_lab/error_boundary.py（新增 CALLBACK_ERROR_SESSION_KEY、guarded_callback、show_callback_error）
- views/house.py（render() 在 st.title 後呼叫 show_callback_error；_persist_subjective_trigger 改簽名 (*, trigger_key, widget_key) 並加 @guarded_callback，內部用 verified_container().subjective_trigger_repo；_render_triggers、_render_subjective_checkbox 移除 repo 參數）
- tests/test_error_boundary.py（guarded_callback 小腳本測）
- tests/test_house.py（AppTest 點勾選框：替身 get_resilient_container 只被呼叫一次、寫入走其容器、寫入失敗時標題下方有訊息且頁面照常渲染）

## 依賴
- t03
- t04

## 切片理由
callback 在腳本主體之前執行，必須自行驗證連線，所以依賴 verified_container（t03）與 error_boundary 的分類邏輯（t04）。與 t05 彼此獨立，各動不同頁面，分開 commit 方便回滾。
