# Progress: initial-build

## Phase 1：規劃

| 步驟 | 狀態 | 備註 |
|------|------|------|
| 1-1 提案 | 完成 | proposal.md 已確認 |
| 1-2a 技術選型 | 完成 | tech-research.md 已產出；發現 Turso 套件名需修正（libsql-client→libsql）|
| 1-2b 架構分析 | 跳過 | greenfield 新專案，無既有 codebase 可分析 |
| 1-2 設計 | 完成 | design.md 已確認（10 條 ADR）|
| 1-3 行為規格化 | 完成 | 34 張 SC（SC-001~034），open_questions 全數定案 |
| 1-4 任務拆解 | 完成 | 11 個 Task（t01~t11），SC 全覆蓋 |

## Phase 2：實作

| Task | 狀態 | 備註 |
|------|------|------|
| t01 專案骨架+模型+core | 完成 | 基礎設施＋core 純函式；25 tests 綠，ruff 綠 |
| t02 ReturnService TWR/PnL | 完成 | BR-4e 簽名隔離；19 tests 綠，累計 44 |
| t03 ReturnService MWR/XIRR | 完成 | SC-015,016；接 pyxirr，不收斂降級；11 tests 綠，累計 55 |
| t04 報酬三維度+區間 | 完成 | SC-019,020,021,028,035；PeriodService＋三維度；21 tests 綠，累計 76 |
| t05 Allocation 佔比/淨值/漂移 | 完成 | SC-010,011,025,026,027,036；22 tests 綠，累計 94 |
| t06 目標偏離/再平衡 | 未開始 | SC-029,030 |
| t07 MonthlyInput 帶入/轉移 | 未開始 | SC-005,008,009 |
| t08 Repository+Schema | 未開始 | SC-001,002,003,004,006,007 |
| t09 DataIo CSV 匯出入 | 未開始 | SC-031,032 |
| t10 登入守門判定 | 未開始 | SC-033,034 |
| t11 Streamlit 串接層 | 未開始 | bootstrap/app.py/pages/charts；UI 串接，無新 SC |
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
