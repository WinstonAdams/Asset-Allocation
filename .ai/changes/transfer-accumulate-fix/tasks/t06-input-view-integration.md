# Task t06: views/input.py 整合（累加轉移、帶入既有值、本月紀錄表、股利欄位）

## 滿足 Scenarios
- SC-086（happy）— View 整合層：轉移寫入改走 `accumulate_net_investments`，累加線路串接
- SC-087（happy）— View 整合層：一般分類錄入框選取項目/月份後帶入既有值、不修改直接存檔不洗資料、切換後恢復預設
- SC-088（happy）— View 整合層：股票/ETF 錄入框帶入當月既有值，已實現損益／現金股利分開欄位
- SC-089（happy）— View 整合層：本月已存紀錄表格渲染、市值未填提醒、存檔或轉移後即時反映
- SC-090（happy）— View 整合層：已實現損益／現金股利兩欄輸入＋BR-7 提示文字
- SC-091（錯誤）— View 整合層：現金股利負數時預覽區顯示拒絕原因、存檔同樣被拒絕
- SC-079（happy，既有）— 轉移涉及股票端測試因 Repository 呼叫方法替換（`upsert_records` → `accumulate_net_investments`）需機械更新 stub／斷言，行為不變
- SC-080（邊界，既有）— 轉移兩端皆股票端測試因共用 stub 類別需同步更新，行為不變

## 實作範圍
- views/input.py（`render()` 開頭 pop `_FLASH_KEY` 顯示成功訊息；try 內讀一次 `holdings`、`month_records` 往下傳；新增 `_render_month_records`：呼叫 `input_service.summarize_month(...)` 以 `st.dataframe([{標籤: format_amount(值)}...])` 呈現，`market_value_missing` 的列顯示提醒，當月無紀錄顯示空狀態；`_render_record_editor` 改收 `input_service`/`holdings`/`month_records`，接入 `build_record_prefill` → `seed_amount_inputs(seed_key=_RECORD_SEED_KEY, source=(holding_id, target_ym, prefill), ...)`；`_render_cost_basis_editor` 改用 `build_cost_basis_prefill` → `seed_amount_inputs(seed_key=_COST_BASIS_SEED_KEY, ...)`，新增 `cost_basis_realized_pnl`／`cost_basis_cash_dividend` 兩個 `amount_input`（取代原本單一 `cost_basis_realized_income`）＋ BR-7 提示文字，預覽區拆兩段 try 區分「未填完」與「被拒絕」，`plan_save` 改傳 `realized_pnl`/`cash_dividend`；`_render_transfer` 改收 `holdings`（不再自己讀），寫入呼叫由 `upsert_records` 改為 `accumulate_net_investments`；新增私有 `_flash_and_rerun(message)`（寫入 `session_state[_FLASH_KEY]` 後 `st.rerun()`）；新增模組常數 `_FLASH_KEY`/`_RECORD_SEED_KEY`/`_COST_BASIS_SEED_KEY`；頁首說明文案改兩格版本）
- tests/test_input_view.py（`_StubRecordRepo` 補 `read_month`、`accumulate_net_investments`；既有轉移測試（SC-079/SC-080）斷言從 `batch_upserted` 改為 `accumulate_net_investments` 的呼叫記錄；`cost_basis_realized_income` key 相關斷言改成 `cost_basis_realized_pnl`/`cost_basis_cash_dividend` 兩個 key；存檔/刪除/轉移成功訊息斷言改為 `st.rerun()` 後的 flash 顯示；新增整合測試：切換項目/月份時欄位帶入既有值、不切換時使用者輸入不被覆蓋、轉移後欄位與本月紀錄表重新帶入最新值、本月已存紀錄表格渲染與市值未填提醒、現金股利填負數時預覽與存檔皆拒絕。**這些新增測試是本 Change 業務行為（SC-086～SC-091）在 View 整合層的驗證，即使測試手法看起來像是「UI 機制」（AppTest 操作 selectbox/text_input/button），仍必須依其驗證的業務規則掛對應 `@pytest.mark.scenario` marker；不可比照本檔既有「年月下拉選單」那類無新業務語義的純重構測試省略 marker——兩者性質不同，2-Z scenario_lint 會把未掛 marker 的新 test 一律判為孤兒 test 而 FAIL，前一個 Change 已踩過這個雷**）

## 依賴
- t01（`accumulate_net_investments`）
- t02（`build_record_prefill`／`summarize_month`）
- t03（`build_cost_basis_prefill`／新簽名的 `derive`／`plan_save`）
- t05（`seed_amount_inputs`）

## 切片理由
View 層本身不新增業務判斷，只做委派與呈現；待所有下層 Service／Repository／UI 元件（t01/t02/t03/t05）就緒後才整合，符合「純邏輯先做、外部 I/O／Streamlit 後串」。`render()` 一輪只讀一次 `holdings`/`month_records` 並往下傳是單一函式簽名的連動改動，`_render_record_editor`／`_render_month_records`／`_render_transfer` 三者共用同一份資料來源，拆成多個 commit 會讓部分子渲染函式還在自行讀取、部分已改吃傳入參數，產生簽名不一致的中間態；整合進一個 commit 可一次驗證 AD-1～AD-4／AD-6 在同一頁面組裝起來的線路是否正確，避免拆成多個 commit 時頁面處於編譯不過或行為互相矛盾的中間態。
