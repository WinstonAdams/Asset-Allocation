# Task t06: amount_input UI 元件 + 全站放大樣式

## 滿足 Scenarios
- SC-083 (happy)

## 實作範圍
- src/asset_lab/amount_widget.py（新建檔案：`amount_input(label, *, key, value, on_change, kwargs)` 包裝 `st.text_input`＋外層有 key 的 `st.container`＋自帶 `on_change` 正規化；`inject_amount_input_style()` 用 `st.html` 注入 `[class*="st-key-<前綴>"] input` 選擇器樣式）
- app.py（`main()` 在 `_require_access()` 通過後、`navigation.run()` 之前呼叫一次 `inject_amount_input_style()`）
- tests/test_amount_widget.py（新建檔案：SC-083 對映，CSS class 選擇器與樣式字串存在性斷言；視覺效果本身因需經 app.py 才注入，2-Z 啟動驗證階段另行人工確認）

## 依賴
- t05（呼叫 `format_amount`／`parse_amount`）

## 切片理由
UI 元件與樣式是後續 views/input.py（t08）與 views/settings.py（t09）共同依賴的基礎設施，先獨立成一個可單元測試的 commit（元件本身用 AppTest 可測初值格式化與 on_change 正規化，不需要真正的頁面整合）。
