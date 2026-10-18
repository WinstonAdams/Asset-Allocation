# Task t07: 月度錄入頁依錄入方式分派四個編輯器並移除項目間轉移 UI

## 滿足 Scenarios
- SC-099 (happy，View 層：保險錄入框帶入)
- SC-101 (happy，View 層：負債「應繳金額」與紀錄表兩欄)
- SC-102 (錯誤，View 層：st.error 提示先到設定頁指定分類)
- SC-103 (happy，View 層：頁面無轉移功能與提示)
- SC-087 (happy，View 層：餘額/應繳金額帶入)
- SC-089 (happy，View 層：本月紀錄表與未填提醒)
- SC-083 (happy，新增的金額欄全數套用放大樣式)
- SC-090 (邊界，股票編輯器旁移除轉移提示)
- SC-100 (happy，View 層：負債存檔／刪除改走批次寫入，寫入失敗顯示友善訊息)
- SC-085 (邊界，View 層：PersistenceError 只顯示友善訊息、不露堆疊，輸入值保留)

## 實作範圍
- views/input.py（_render_record_editor 依 resolve_input_mode 分派；新增 _render_premium_editor / _render_balance_editor / _render_amount_due_editor；移除一般編輯器、_render_transfer、股票編輯器轉移提示；本月紀錄表依 is_liability 拆「市值 / 餘額」與「應繳金額」兩欄，成本欄表頭改「總成本 / 累計保費」「已實現收益 / 領回」；頁首賣出說明改寫；負債存檔改呼叫 upsert_records、刪除改呼叫 delete_record_and_upsert（不再用 upsert_record／delete_record）；PersistenceError 由既有 except AssetLabError 處理、不新增 catch；共用預覽骨架抽成私有函式；docstring 同步）
- src/asset_lab/amount_widget.py（僅在新金額欄需要時補 widget/seed key 支援）
- tests/test_input_view.py（刪除轉移與一般編輯器相關測試；替身補 resolve_input_mode、balance_input_service；新增 SC-099/101/102/103 view 測試；新增 SC-085 用 Record 替身拋 PersistenceError 的畫面測試、負債走批次寫入的測試）
- tests/test_amount_widget.py（SC-083 涵蓋新金額欄標籤）

## 依賴
- t01（PersistenceError 與批次寫入轉譯）
- t03、t04、t05

## 切片理由
View 整合必須等交易工具與三個 Service 都就緒才能一次切換分派；四個編輯器共用同一檔案與預覽骨架，拆開會留下半新半舊的暫時分流，故合為一個 commit。此 Task 後 View 不再呼叫任何轉移方法，t08 才能安全刪除 dead code。（體量偏大，若實作時過重，主 AI 可依「balance／amount_due」與「premium」再拆；使用者已決定維持單一 Task，不拆。）
