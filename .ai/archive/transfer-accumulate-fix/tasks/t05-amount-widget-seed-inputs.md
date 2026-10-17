# Task t05: amount_widget 新增 seed_amount_inputs（帶入重新播種機制）

## 滿足 Scenarios
- SC-087（happy）— 一般分類錄入框「帶入既有值、切換項目/月份跟著換、不切換時使用者輸入不被洗掉」這套機制在 widget 層的落實
- SC-088（happy）— 股票/ETF 錄入框帶入當月既有值、分開帶回已實現損益與現金股利，同一機制在 widget 層的落實

## 實作範圍
- src/asset_lab/amount_widget.py（新增 `seed_amount_inputs(*, seed_key: str, source: object, values: Mapping[str, float | None]) -> None`：`session_state.get(seed_key) != source`，或 `values` 中任一 key 不在 `session_state`（widget 上一輪沒渲染、state 已被 Streamlit 清掉）時，把 `values` 每個 key 的 session_state 改成 `format_amount(值)` 並把 `source` 記到 `session_state[seed_key]`；兩者皆不成立就不動；docstring 註明必須在對應的 `amount_input` 建立之前呼叫）
- tests/test_amount_widget.py（新增 `seed_amount_inputs` 機制測試：來源改變時重新播種、來源相同且 key 齊全時不重新播種（保留使用者還沒存檔的輸入）、key 缺失時即使來源相同也強制重新播種、在對應 `amount_input` 建立前呼叫不拋例外。**這些測試驗證的正是 BR-2／SC-087／SC-088「選定後帶入、切換跟著換、不切換不洗掉」規則在 widget 層的落實，屬於本 Change 新增的業務行為驗證，必須掛 `@pytest.mark.scenario("SC-087")` 或 `"SC-088"`，不可比照本檔既有「CSS 選擇器放大樣式」那類純技術機制測試的風格略過 marker——2-Z scenario_lint 會把未掛 marker 的新 test 一律判為孤兒 test 而 FAIL，前一個 Change 已踩過這個雷**）

## 依賴
- 無

## 切片理由
`seed_amount_inputs` 只吃 `Mapping[str, float | None]`，不依賴任何 Service 的 Prefill 模型結構，可用純 dict 與 AppTest 腳本窮舉「來源改變／不變／key 缺失」三種時機條件，不需等 t02／t03 的 Prefill 模型就緒。在 t06 View 整合之前先獨立驗證這個 Streamlit widget state 機制，讓整合時只需接線、不需同時除錯機制本身。
