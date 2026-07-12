# Progress: behavior-protocol

## Phase 1：規劃

| 步驟 | 狀態 | 備註 |
|------|------|------|
| 1-1 提案 | 完成 | proposal.md 已確認（新增總覽/首頁、行為協定唯讀頁、等級判定、門檻設定頁存 DB）|
| 1-2a 技術選型 | 跳過 | 無新技術選型，沿用既有 Streamlit/Turso 棧與 markdown 渲染 |
| 1-2b 架構分析 | 跳過 | 非 greenfield 但由 designer 直接讀 initial-build design.md 與既有 codebase 整合，不另出 architecture-brief |
| 1-2 設計 | 未開始 | — |
| 1-3 行為規格化 | 未開始 | scenario-author 產 scenarios/ 卡片 |
| 1-4 任務拆解 | 未開始 | — |

## Phase 2：實作

| Task | 狀態 | 備註 |
|------|------|------|
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
