# Progress: transfer-accumulate-fix

## Phase 1：規劃

| 步驟 | 狀態 | 備註 |
|------|------|------|
| 1-1 提案 | 完成 | 轉移累加＋保留市值、錄入框帶入既有值、本月已存紀錄表＋市值未填提醒、股票/ETF 已實現收益拆為已實現損益＋現金股利兩格；BR-1~7 |
| 1-2a 技術選型 | 跳過 | 無新外部依賴 |
| 1-2b 架構分析 | 跳過 | 沿用前一 Change（stock-total-cost-input）design.md 的架構分析 |
| 1-2 設計 | 完成 | AD-1~7：轉移 SQL 原子累加保留市值、Service 產帶入值＋依資料來源重新播種、寫入後 st.rerun、本月紀錄表、realized_income 存合計＋附加 cash_dividend（否決改名，雲端共用 DB 相容）、股利非負、CSV 附加欄；Q1~Q5 使用者接受推薦值 |
| 1-3 行為規格化 | 完成 | 新增 SC-086~091（6 張）、修訂 SC-008/009/031/074/075/076/078/079/082/083/084/085（12 張）；新卡無 open_questions |
| 1-4 任務拆解 | 完成 | 拆成 t01~t06（見 tasks/）；t01 schema+累加 Repository、t02 MonthlyInputService 純方法、t03 CostBasisService 拆分、t04 CSV 契約、t05 amount_widget 播種機制、t06 View 整合 |

## Phase 2：實作

| Task | 狀態 | 備註 |
|------|------|------|
| t01 monthly_records 加欄（cash_dividend）+ 轉移累加 Repository 方法 | 未開始 | SC-006/085/086 |
| t02 MonthlyInputService 新增純方法（單列帶入值 + 本月已存紀錄彙總） | 未開始 | SC-087/089 |
| t03 CostBasisService 已實現損益／現金股利拆分與非負驗證 | 未開始 | SC-074/075/076/078/088/090/091 |
| t04 CSV records 契約附加 cash_dividend | 未開始 | SC-031/084 |
| t05 amount_widget 新增 seed_amount_inputs（帶入重新播種機制） | 未開始 | SC-087/088（widget 層落實） |
| t06 views/input.py 整合（累加轉移、帶入既有值、本月紀錄表、股利欄位） | 未開始 | SC-086~091、SC-079/080（既有測試機械更新） |
| 2-Z 整合驗證 | 未開始 | scenario-lint + pytest + 啟動驗證（fail-fast 順序）|

## Phase 3：審查

| 步驟 | 狀態 | 備註 |
|------|------|------|
| 3-1 程式碼清理 | 未開始 | 依規模判斷是否執行 |
| 3-2 安全審查 | 未開始 | 涉及認證/付款/個資時才執行 |
| 3-3 規則符合度審查 | 未開始 | 工程準則全面符合度檢查 |
| 3-4 行為對映審查 | 未開始 | AI 比對 SC 描述 vs test 內容 |
| 3-Z 最終驗證 | 未開始 | 重跑 2-Z 三件事，確認審查改動沒破壞 runtime |

## Phase 4：收尾

| 步驟 | 狀態 | 備註 |
|------|------|------|
| 4-1 README 同步 | 未開始 | — |
| 4-2 Windows 啟動器 | 未開始 | 新專案且需啟動器時 |
| 4-3 歸檔 | 未開始 | — |

**狀態值**：未開始 / 進行中 / 完成 / 跳過
