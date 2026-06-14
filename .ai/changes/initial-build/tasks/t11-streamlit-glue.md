# Task t11: Streamlit 串接層 — bootstrap、app.py、pages、charts

## 滿足 Scenarios
- 無新增 SC 轉 GREEN（本切片為 UI/組裝層；SC-001~034 的業務行為與資料層已由 t02~t10 的 Service/Repository/純判定覆蓋並 GREEN）。
  本切片完成 SC-025~028 圖表「呈現」部分（資料層分別在 t04/t05）、SC-033/034 守門的 Streamlit 副作用（`st.login()`/`st.stop()`，比對核心在 t10）等無法純測的 UI 串接。

## 實作範圍
- `src/asset_lab/bootstrap.py`（@st.cache_resource：get_connection 讀 st.secrets、get_container keyword-args 注入 Repo/Service、allowed_emails 讀 st.secrets）
- `app.py`（st.login() 守門 → 套用 t10 比對決策 → bootstrap 組裝 → st.navigation 路由）
- `src/asset_lab/charts.py`（Plotly 元件：px.pie 圓餅、px.area 堆疊面積 groupnorm=percent、px.line 淨值/報酬走勢）
- `pages/input.py`（月度錄入：帶入上月、單列 CRUD、轉移、賣出語意提示；委派 MonthlyInputService + RecordRepository）
- `pages/allocation.py`（圓餅 SC-025 / 堆疊面積 SC-026 / 淨值折線 SC-027 / 報酬走勢 SC-028；委派 AllocationService + ReturnService + charts）
- `pages/returns.py`（三維度報酬率 + 區間切換 + MWR 降級顯示；委派 ReturnService + PeriodService）
- `pages/settings.py`（持有項目主檔 CRUD + 目標比重設定；委派 HoldingRepository + TargetRepository + AllocationService.compute_drift）
- `pages/data_io.py`（CSV 匯出 download_button / 匯入 file_uploader；委派 DataIoService + Repository，Page 層唯一 catch → st.error）

## 依賴
- t04、t06、t07、t09、t10（所有 Service / Repository / 守門判定齊備後才能組裝串接）

## 切片理由
Streamlit 串接層（bootstrap 依賴組裝、app.py 路由與守門副作用、pages 的 View/Controller、charts 的 Plotly 渲染）是最後一層黏合，依賴前面所有純邏輯與 I/O 就緒，符合「外部框架副作用最後串」。此層因 rerun 模型與 st.* 副作用難以純單元測試（AD-1/AD-8），不掛新 SC marker——業務正確性已由下層 Task 的 SC 測試保證，本切片只做委派與渲染、不含可獨立斷言的業務運算。Page 層為唯一 catch 點（AD-8）的容錯邊界、cache_resource 單次組裝（AD-1）、守門前置（AD-6 的 st.* 部分）在此落地。獨立成最終 commit，使「app 可實際啟動」成為一個明確的整合里程碑（交 2-Z 啟動驗證）。
