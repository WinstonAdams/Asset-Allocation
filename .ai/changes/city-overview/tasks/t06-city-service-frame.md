# Task t06: CityService.frame_at（歷史截斷、工地、天氣、偏離三角）與最新月一致性

## 滿足 Scenarios
- SC-143 (歷史月份購屋工地進度與註記)
- SC-145 (最新月與買房頁／總覽頁／配置頁一致)
- SC-149 (歷史月份天氣逐月判定)
- SC-150 (配置偏離三角，只標該類別建築)

## 實作範圍
- src/asset_lab/services/city_service.py（`frame_at`，design §5、AD-3、AD-5、AD-6）
- tests/test_city_service.py（上述 SC；最新月一致性不變式必須同 Task 完成）

## 依賴
- t05

## 切片理由
design 實作順序約束第 3 點：`frame_at` 的一致性測試與 `frame_at` 同一 Task 完成，不得延後。此 Task 是整個 Change 業務口徑風險最集中處，單獨 commit 利於回滾與審查。
