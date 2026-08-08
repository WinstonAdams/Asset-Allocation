# Progress: house-dashboard

## Phase 1：規劃

| 步驟 | 狀態 | 備註 |
|------|------|------|
| 1-1 提案 | 完成 | 2026-07-19 使用者確認（BR-1~BR-9；個人化預設值出庫至私人參數檔）。平台層背景見 docs/ROADMAP.md 與 docs/DECISIONS.md |
| 1-2a 技術選型 | 跳過 | 純確定性數學＋既有 Streamlit/Turso 模式，無新技術選型 |
| 1-2b 架構分析 | 跳過 | 沿用既有分層（views→services→repositories），無架構議題 |
| 1-2 設計 | 完成 | 2026-07-19 使用者確認（10 AD＋2 TD；AD-7 政策比率拍板為通用值公開保留） |
| 1-3 行為規格化 | 完成 | 2026-07-19 使用者確認（SC-052~SC-071 共 20 張；5 項開放問題依使用者決策收斂） |
| 1-4 任務拆解 | 完成 | 2026-07-19 產出 t01–t08 共 8 個 Task，SC-052~071 全數分配 |

## Phase 2：實作

| Task | 狀態 | 備註 |
|------|------|------|
| 2-1 t01 可負擔性引擎 | 完成 | SC-052, SC-053；RED 發現邊界收編為 SC-072（月收未設定→月付占比 None，fail-closed 供 t06 引用） |
| 2-2 t02 買房參數與主觀勾選持久化 | 完成 | SC-054, SC-055, SC-068 |
| 2-3 t03 holdings 用途欄位與兩路徑遷移 | 完成 | SC-057, SC-058, SC-059（依賴 t02）|
| 2-4 t04 holdings CSV 契約附加 purpose | 完成 | SC-060, SC-061；非法值處理收編為 SC-073（依賴 t03）|
| 2-5 t05 bucket 口徑、進度與組成警示 | 完成 | SC-062, SC-063, SC-064, SC-065（依賴 t02, t03）|
| 2-6 t06 觸發條件檢核 | 完成 | SC-056, SC-069, SC-070（依賴 t01, t02, t05）|
| 2-7 t07 買房獨立頁 | 完成 | SC-066, SC-067（依賴 t01, t02, t05, t06）|
| 2-8 t08 總覽頁買房進度摘要 | 完成 | SC-071 |
| 2-9 修復本 Change 造成的孤兒 test | 完成 | 回繞：2-Z scenario_lint 發現孤兒 test；逐一 git blame 排查後確認僅 tests/test_house.py::test_completely_empty_state_renders_without_exception（t07 新增）屬本 Change，補掛 SC-056；其餘（test_input_view.py、test_settings_view.py、test_bootstrap.py、test_core_utils.py 全部）皆為本 Change 之前既有技術債，未動 |
| 2-Z 整合驗證 | 完成 | scenario_lint PASS（本 Change 範圍孤兒已清除，殘留 41 個既有技術債不計）；pytest PASS（421 tests）；啟動驗證：Streamlit app 無自動 dev mode，需瀏覽器互動不自動執行，使用者確認接受現狀視為通過 |
| 2-10 t10 修正月收未設定時可負擔總價誤導顯示 | 完成 | 回繞：3-4 發現 production 與 SC-056 看失一致。根因：AffordabilityService.affordable_total_price 於 monthly_income=0 時無防呆、照常算出 0 元。修正為回傳 None（比照 payment_for_price 慣例），views/house.py 既有 _format_amount 自動渲染「—」，無需改 view 層。修正舊 test 誤斷言＋新增 view 層 test。pytest 422 passed、ruff 全過、scenario_lint SC 覆蓋 73/73 |

## Phase 3：審查

| 步驟 | 狀態 | 備註 |
|------|------|------|
| 3-1 程式碼清理 | 完成 | Checker 57 條（HIGH 6/MEDIUM 50/LOW 1）+ 人工掃描；SAFE 項全數修正（6 條 `#` Change 級編號註解 + 17 處 docstring BR-N/AD-N/SC-N 引用 + affordability_service.py 過時 SC-PENDING-001→改寫；schema_repository.py 補 cursor 型別提示）；CAREFUL/SUGGEST 依主 AI 決策暫緩不動（測試固定資料重複為慣例、house/overview 編排重疊為 design.md §8 已知限制、3 個 function_too_large + 1 個 file_too_long 留待未來）；修正後 pytest 421 passed、ruff 全過、checker 複跑 HIGH 降至 0 |
| 3-2 安全審查 | 跳過 | 本次變更未涉及認證/付款；個人財務數值走既有私人參數出庫機制與 fail-closed 中性預設，比照既有 holdings/protocol_thresholds 慣例不觸發 |
| 3-3 規則符合度審查 | 完成 | 676 條 checker 原始發現逐條核對 baseline，675 條為既有慣例誤判排除，2 條真違規已修正：HoldingModel 預設值改字面值移除 constants import；bucket_composition_warning 的 purpose 篩選邏輯移入 Service（比照 bucket_value()）。修正後 pytest 421 passed、ruff 全過、checker HIGH 降至 0。核准判定：通過 |
| 3-4 行為對映審查 | 完成 | 22 張 SC × 105 個 marker 逐項核對，20 張原本對齊；2 項不對齊：SC-072 純補 test（production 已 fail-closed）、SC-056 production 與 SC 看失一致回繞 2-10 修正後複查對齊。修正後 pytest 423 passed、ruff 全過。核准判定：通過 |
| 3-Z 最終驗證 | 完成 | scenario_lint PASS（本 Change 孤兒清除，殘留 41 個既有技術債不計）；pytest PASS（423 tests）；啟動驗證 PASS（Streamlit app 無自動 dev mode，接受現狀） |

## Phase 4：收尾

| 步驟 | 狀態 | 備註 |
|------|------|------|
| 4-1 README 同步 | 完成 | 增量更新：新增買房功能（SIPOC、功能列表、系統架構 services/repositories 摘要、「關鍵邏輯：買房可負擔性與觸發條件」子段落、專案結構加 house.py）＋本機 watchdog 踩坑註記 |
| 4-2 Windows 啟動器 | 跳過 | 非新專案，使用者一直手動以 uv run streamlit run app.py 啟動，無啟動器需求 |
| 4-3 歸檔 | 未開始 | — |

**狀態值**：未開始 / 進行中 / 完成 / 跳過
