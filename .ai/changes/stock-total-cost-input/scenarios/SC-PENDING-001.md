---
id: SC-PENDING-001
category: 邊界
capability: monthly-input
title: 批次寫入月度紀錄時，中途失敗不留下部分寫入結果
origin: implementor
discovered_at: 2026-09-28
open_questions:
  - 失敗時是否需要在畫面上顯示特定錯誤訊息，或沿用既有頁面層錯誤處理機制的一般錯誤提示即可？
  - 這個「要嘛全部成功、要嘛全部不生效」的保證，是否也該延伸到既有的單筆寫入方法（upsert_record／replace_all），還是僅限本次新增的批次寫入方法？
---

# SC-PENDING-001: 批次寫入月度紀錄時，中途失敗不留下部分寫入結果

## 行為（暫定）
- **GIVEN** 使用者對某股票/ETF 項目存檔或刪除，觸發多筆月度紀錄一次寫入（存檔列＋受影響的後續重算列，或刪除一列＋受影響的後續重算列）
- **WHEN** 這次批次寫入過程中任何一筆失敗（任何原因，例如儲存層當下發生錯誤）
- **THEN** 暫定：這批寫入中已處理的部分不會被留存，資料庫維持在這次批次寫入開始之前的狀態（不留下只寫了一半的推算鏈）
- **AND** 錯誤原樣往上拋，交由既有的錯誤處理機制呈現，不在此處吞掉或另外記錄

## 為什麼需要這張卡片
t01（schema-model-repository）依 design.md AD-5 新增 `upsert_records`／`delete_record_and_upsert` 兩個 compound method，供後續股票/ETF 總成本推算（AD-3/AD-4）的多列連動寫入使用。design.md 已就技術契約（單一交易、失敗 rollback 後原樣往上拋）做出明確架構決策，但目前沒有任何 Scenario 卡片以業務語言描述「批次寫入中途失敗時，資料是否/如何保持一致」這件事，故建此待認可卡片記錄該行為，供主 AI 與使用者確認是否要正式收斂為 SC。

## 測試對映
- tests/test_monthly_input.py::test_scpending001_*
