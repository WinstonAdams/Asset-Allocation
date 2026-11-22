# Task t01: Tracer bullet（骨架、元件掛載、Streamlit 下限、打包）

## 滿足 Scenarios
- SC-164 (打包與版本下限)

## 實作範圍
- src/asset_lab/city/__init__.py（保持空白）
- src/asset_lab/city/component.py（Components v2 註冊與 wrapper，最小版）
- src/asset_lab/city/city.js、src/asset_lab/city/city.css（最小可掛載版本，僅供驗證 data-mount、selected 回灌）
- src/asset_lab/views/overview.py（`_render_city()` 以 `rerun_fragment(label="城市總覽")` 包住，最小 payload；既有內容不動）
- pyproject.toml（`streamlit[auth]>=1.66`；若 wheel 缺 `.js`/`.css` 補 hatch include）
- uv.lock（重新鎖定）
- tests/test_city_static.py（僅 `test_sc164_*`：下限與資源檔存在）
- tests/test_overview.py（SC-071 三個 AppTest 比照 `fragment_entry_probe` patch fragment 入口）
- tests/test_read_cache_equivalence.py（SC-118 fragment 入口 patch）
- 人工驗證（AD-12）：瀏覽器確認 fragment 重跑範圍、元件不重掛載、`selected` 回灌；`uv build` 列出 wheel 內容

## 依賴
- 無

## 切片理由
design AD-12 與「實作順序約束」第 1 點：最大未驗證風險（Components v2 放進 fragment 的重跑與掛載行為、打包）先以最小成本驗證，任一項不成立時還沒投入版位與資料組裝。三項瀏覽器驗證結果須回報主 AI 後才進入 t02 以後。此 Task 同時處理受影響的既有測試，確保 commit 不破壞既有功能。
