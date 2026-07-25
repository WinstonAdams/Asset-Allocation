# Task t02: 買房參數與主觀勾選持久化（含設定頁區塊）

## 滿足 Scenarios
- SC-054 (happy)
- SC-055 (錯誤)
- SC-068 (happy)

## 實作範圍
- src/asset_lab/core/constants.py（新增 `HOUSE_PARAM_KEY` / `HOUSE_PARAM_DEFAULTS` / `HOUSE_TRIGGER` / `HOUSE_PARAMS_TABLE` / `SUBJECTIVE_TRIGGERS_TABLE`）
- src/asset_lab/models/house.py（新增 `HouseParamModel` / `SubjectiveTriggerModel` / `HouseParams`）
- src/asset_lab/repositories/schema_repository.py（`ensure_schema` 新增 `house_params` / `subjective_triggers` 兩表 CREATE IF NOT EXISTS）
- src/asset_lab/repositories/house_param_repository.py（新增：`read_params` / `upsert_param`）
- src/asset_lab/repositories/subjective_trigger_repository.py（新增：`read_triggers` / `upsert_trigger`）
- src/asset_lab/services/house_service.py（新增，本 Task 先建 `effective_params` / `validate_params` 兩方法；其餘方法由 t05 / t06 / t08 增量補齊）
- src/asset_lab/bootstrap.py（`Container` 注入 `house_param_repo` / `subjective_trigger_repo` / `house_service`）
- views/settings.py（新增 `_render_house_params` 區塊，比照 `_render_protocol_thresholds`）
- tests/test_house_params.py（新增）

## 依賴
- 無

## 切片理由
買房參數與主觀勾選是後續 bucket（t05）、觸發檢核（t06）、頁面（t07/t08）的共同輸入，先落地。沿用 protocol_thresholds 現成範式（AD-4 / AD-5），「表 → Repo → effective 合併 → 存前驗證 → 設定頁」一次成垂直切片，可獨立驗證存取與驗證規則；與 t01 互不依賴。僅新增表與檔案，既有功能不受影響，可獨立 commit。
