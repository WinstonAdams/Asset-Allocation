# Task t01: 可負擔性引擎（純數學）

## 滿足 Scenarios
- SC-052 (happy)
- SC-053 (happy)

## 實作範圍
- src/asset_lab/services/affordability_service.py（新增：`monthly_payment` / `affordable_total_price` / `payment_for_price`，AD-2 / TD-1）
- src/asset_lab/models/results.py（新增 `AffordabilityResult`）
- src/asset_lab/bootstrap.py（`Container` 注入 `affordability_service`）
- tests/test_affordability.py（新增）

## 依賴
- 無

## 切片理由
引擎是本 Change 風險最高、最需獨立驗證的純數學單元；零依賴（不碰 DB / Streamlit），全部參數顯式傳入，可用虛構值窮舉公式與往返一致性邊界，最先做。後續 t06（月付觸發條件）與 t07（買房頁）直接消費其輸出。僅新增檔案與 Container 一欄，不動既有功能，可獨立 commit。
