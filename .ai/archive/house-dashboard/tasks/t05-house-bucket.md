# Task t05: bucket 口徑、進度與組成警示（HouseService 純運算）

## 滿足 Scenarios
- SC-062 (happy)
- SC-063 (happy)
- SC-064 (邊界)
- SC-065 (happy)

## 實作範圍
- src/asset_lab/services/house_service.py（新增 `bucket_value` / `bucket_progress` / `bucket_composition_warning`）
- src/asset_lab/models/results.py（新增 `BucketProgress` / `BucketCompositionWarning`）
- tests/test_house.py（新增）

## 依賴
- t02（`HouseParams` 為輸入型別）
- t03（`HoldingModel.purpose` 為 bucket 過濾口徑）

## 切片理由
bucket 系列為純運算（接收 Repo 已取出的資料，無 I/O），集中於 HouseService 使「用途＝購屋」口徑單一定義（AD-3），可全用虛構資料獨立單測。須先於 t06——觸發檢核的自備條件消費 bucket 值與目標金額口徑。純邏輯先做、UI 後串；僅增量新增方法與結果模型，可獨立 commit。
