# Task t07: MonthlyInputService — 帶入上月與成對轉移純運算

## 滿足 Scenarios
- SC-005 (happy) — 新增月份自動帶入上月仍持有項目清單
- SC-008 (happy) — 項目間轉移成對記錄淨投入
- SC-009 (邊界) — 賣出當月記市值 0 與負淨投入、後續月份缺列（帶入排除邏輯）

## 實作範圍
- `src/asset_lab/services/monthly_input_service.py`（prefill_from_previous：帶入上月仍持有清單、市值留空淨投入 0、上月缺列項目不帶入、首月從主檔挑；build_transfer_pair：來源 −amount / 目標 +amount）
- `tests/test_monthly_input.py`（SC-005、SC-008、SC-009 對映）

## 依賴
- t01（models、constants）

## 切片理由
MonthlyInputService 的兩個方法（帶入、轉移配對）為**純運算**，輸入輸出皆 model 清單，可用 stub repo 回傳的固定上月紀錄 pytest 驗證帶入與排除邏輯（SC-005 帶入三項、SC-009 已賣出不帶入）、轉移配對金額方向（SC-008）。雖然建構子型別簽名持有 repo 依賴，但本切片只測純運算邏輯（餵假資料），不觸真實 I/O。SC-006/SC-007（單列 CRUD 與唯一鍵拒絕）屬 Repository 的 upsert/唯一約束行為，歸 t08（I/O 層）。
