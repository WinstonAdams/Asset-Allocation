# Task t08: 總覽頁買房進度摘要

## 滿足 Scenarios
- SC-071 (happy)

## 實作範圍
- src/asset_lab/services/house_service.py（新增 `overview_summary`）
- src/asset_lab/models/results.py（新增 `HouseSummary`）
- views/overview.py（編排讀買房參數/主觀勾選/主檔/最新月紀錄 → `overview_summary` → 渲染買房摘要列，與協定等級摘要同層）
- tests/test_overview.py（擴充）

## 依賴
- t05、t06（`BucketProgress` / `TriggerChecklist` 為輸入）
- t07（SC-071 邊界「摘要口徑與買房獨立頁完全一致」需買房頁已存在以對照）

## 切片理由
摘要是消費鏈最末端：等 bucket / 觸發口徑與買房頁都定案後收尾，摘要值經 `HouseService.overview_summary` 統一口徑（AD-9），避免兩頁各算各的造成漂移。變更面窄（一個方法 + 一個結果模型 + overview 一列），獨立 commit 易驗證。
