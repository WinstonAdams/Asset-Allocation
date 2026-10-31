# Task t05: 月度錄入編輯器局部重跑（rerun_fragment）

## 滿足 Scenarios
- SC-120 (happy)
- SC-121 (happy)
- SC-122 (錯誤)
- SC-131 (邊界)

## 實作範圍
- src/asset_lab/rerun_runtime.py（新增 rerun_fragment：st.fragment → rerun_scope(kind=fragment) → error_boundary → verified_container）
- views/input.py（_render_record_editor 改為 @rerun_fragment(label="月度錄入編輯器")、簽名 (*, target_ym)，函式內自取容器與資料；render() 維持頁面層讀取；存檔／刪除成功後仍整頁 st.rerun）
- tests/test_rerun_runtime.py（rerun_fragment 裝飾器小腳本測：未預期例外、AssetLabError、st.rerun 不被攔截、fragment log 行）
- tests/test_input_view.py（結構斷言 AST 帶 rerun_fragment、直接跑 views/input.py 驗查詢數與友善訊息、caplog 的 kind=fragment；既有三個 _FRIENDLY_WRITE_FAILURE 斷言必須維持通過；autouse 替身 get_resilient_container）

## 依賴
- t03
- t04

## 切片理由
fragment 入口依賴 verified_container（t03）與 error_boundary（t04），所以排在其後。只動 input.py 一頁與一個裝飾器，回滾粒度小；實作前依設計先實測 AppTest 對 fragment 內互動的重跑範圍。
