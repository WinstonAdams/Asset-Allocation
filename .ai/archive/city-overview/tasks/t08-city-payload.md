# Task t08: Payload 與 JSON 契約（選取 id、版位規格組裝、序列化）

## 滿足 Scenarios
- SC-159 (沒有選取的提示、失效選取靜默清除)

## 實作範圍
- src/asset_lab/city/payload.py（design §9、AD-7）
- tests/test_city_payload.py（JSON 可序列化、契約欄位齊全、空地欄位、旗桿依 `HOUSE_TRIGGER.ALL`、常數對照涵蓋全部類別與等級）

## 依賴
- t04、t06、t07

## 切片理由
串接 layout、frame 與 presentation，產出前後端唯一契約；先於 JS 改寫，讓 JS 只剩繪圖並以 payload 為準。
