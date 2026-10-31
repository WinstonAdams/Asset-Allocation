# Task t04: 全站錯誤兜底（error_boundary 與錯誤細節開關）

## 滿足 Scenarios
- SC-123 (錯誤)
- SC-124 (邊界)
- SC-125 (happy)
- SC-126 (邊界)

## 實作範圍
- src/asset_lab/core/constants.py（新增 ERROR_DETAILS）
- src/asset_lab/bootstrap.py（新增 resolve_error_detail_mode）
- src/asset_lab/error_boundary.py（新增 UNEXPECTED_ERROR_MESSAGE、error_details_enabled、error_boundary；guarded_callback 留給 t06）
- app.py（st.set_option("client.showErrorDetails", ...)；守門與整個腳本包在 error_boundary(context="app") 內，守門順序不變）
- .streamlit/config.toml（新增，showErrorDetails = "none"）
- tests/test_error_boundary.py（AppTest.from_function 小腳本）、tests/test_error_details_switch.py（開關純函式）、tests/test_app_guard.py（SC-033／034／041 回歸）、tests/test_page_config.py（回歸）；凡改 st.set_option 的測試以 fixture 還原

## 依賴
- t01
- t03

## 切片理由
error_boundary 是 app.py 與後續 fragment／callback 共用的邏輯，必須先於 t05、t06。它與快取、探測無資料相依，但 app.py 的區塊結構在 t03 定案，放在 t03 後以避免對同一段 app.py 重複衝突。
