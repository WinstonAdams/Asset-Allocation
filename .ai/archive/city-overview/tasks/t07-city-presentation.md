# Task t07: 呈現純模組（分區外形、金額文字、天氣、小卡內容）

## 滿足 Scenarios
- SC-142 (小卡顯示當月市值與前一月相比)
- SC-146 (工地前五根旗桿)
- SC-147 (天氣依協定等級)
- SC-148 (協定資料不足的中性天氣)
- SC-157 (建築小卡)
- SC-158 (工地小卡)

## 實作範圍
- src/asset_lab/city/presentation.py（design §8）
- tests/test_city_presentation.py

## 依賴
- t02、t06

## 切片理由
純函式、不碰 `st.*`，吃 t06 的 frame 結果模型與 t02 常數；先於 payload（payload 引用其文案與小卡）。
