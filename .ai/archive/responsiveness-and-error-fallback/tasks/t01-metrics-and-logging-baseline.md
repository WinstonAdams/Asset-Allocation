# Task t01: 量測基礎與 logging（「改前」基準版本）

## 滿足 Scenarios
- SC-130 (happy)
- SC-132 (邊界)

## 實作範圍
- src/asset_lab/core/constants.py（新增 APP_LOGGING、RERUN_KIND）
- src/asset_lab/repositories/query_metrics.py（新增 QueryMetrics、QueryMetricsSnapshot）
- src/asset_lab/repositories/connection_layers.py（先只放 DbConnection／DbCursor Protocol、CountingConnection、CountingCursor）
- src/asset_lab/bootstrap.py（build_container 先只接計數層、get_query_metrics、configure_logging、ensure_logging_configured）
- src/asset_lab/rerun_runtime.py（先只放 RerunScope、rerun_scope；log 行格式 §10）
- app.py（接入 ensure_logging_configured 與最外層 rerun_scope，守門順序不變）
- views/*.py 共 8 檔（logger 改為 asset_lab.views.<檔名>）
- tests/conftest.py（若需補 fixture：還原 logger／cache_resource.clear）
- tests/test_query_metrics.py、tests/test_rerun_runtime.py、tests/test_bootstrap.py（build_container 簽名調整、logging 設定）、tests/test_app_guard.py／tests/test_page_config.py（回歸，預期不改）、tests/test_views_logger_names.py（結構測試）

## 依賴
- 無

## 切片理由
AD-13 要求「改前」量測版本單獨成為可執行 commit：只含 logging、計數層、計時區塊與 logger 改名，不含快取、探測改法、fragment，之後才能前後比較。計數層與 rerun_scope 都是不依賴快取的純邏輯加薄黏合，風險最低，先做。build_container 簽名此步只加 query_metrics，快取參數留給 t02。
