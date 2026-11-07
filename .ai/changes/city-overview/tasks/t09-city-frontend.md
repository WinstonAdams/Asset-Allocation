# Task t09: city.js／city.css 改寫、component 正式版、靜態掃描

## 滿足 Scenarios
- SC-155 (對比 4.5:1、使用者名稱轉義)
- SC-156 (不依賴登入身分、機密設定、資料庫)
- SC-166 (減少動態偏好，人工目視)

## 實作範圍
- src/asset_lab/city/city.js、src/asset_lab/city/city.css（design §11：幾何常數由 Python 注入、無 innerHTML、無寫死文案）
- src/asset_lab/city/component.py（由 t01 最小版改為正式版：注入 GEOM、payload）
- tests/test_city_static.py（`test_sc155_*`、`test_sc156_*`，與 t01 的 `test_sc164_*` 同檔）
- 人工目視清單：點擊、動畫、深淺色、手機 390 寬、名稱牌降級（SC-154）、減少動態（SC-166）

## 依賴
- t08

## 切片理由
前端只負責繪圖，等契約（t08）穩定後再改寫；JS 行為無自動化測試（TD-H），以靜態掃描加人工目視兜底，與 Python 邏輯分開 commit。
