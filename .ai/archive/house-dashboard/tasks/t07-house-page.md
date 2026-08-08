# Task t07: 買房獨立頁（views/house.py + 導覽註冊）

## 滿足 Scenarios
- SC-066 (happy)
- SC-067 (happy)

## 實作範圍
- views/house.py（新增：編排 `effective_params` → 主檔/最新月紀錄 → `bucket_value` / `cash_reserve_value` → `affordable_total_price` / `payment_for_price` → `bucket_progress` / `bucket_composition_warning` / `assess_triggers` → 渲染；正/反算輸入、五條觸發清單、主觀 checkbox 即時 `upsert_trigger`、bucket 進度與警示；單一 catch 點、尾端 `render()`，AD-9）
- app.py（`st.navigation` 註冊，置「行為協定」後、「設定」前）
- tests/test_house.py（擴充：5/5 顯示「可啟動購屋」、缺口清單呈現實際值與門檻值）

## 依賴
- t01、t02、t05、t06（頁面為純編排 Controller，消費全部已就緒的 Service / Repo，不自算業務值）

## 切片理由
外部 I/O 與 UI 最後串（純邏輯先做原則）。SC-066/067 的 THEN 是頁面級呈現（可啟動購屋／缺口清單），放在頁面組裝 Task 端到端轉 GREEN，同時以 happy path 全鏈路覆蓋前面各 Service 的接線正確性。新增頁面 + 導覽一列，不動既有頁面，可獨立 commit。
