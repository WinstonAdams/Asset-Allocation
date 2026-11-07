# Task t05: CityService.build_timeline 與 DI 組裝

## 滿足 Scenarios
- SC-133 (進版位條件)
- SC-134 (購屋用途不蓋建築)
- SC-135 (從未錄月度紀錄不佔版位)
- SC-136 (月份清單與最新月)
- SC-139 (三種月份狀態)
- SC-140 (市值留空不畫建築與名稱牌)
- SC-141 (留空只改畫法，不改其他口徑)
- SC-144 (購屋項目初始市值計入規則)

## 實作範圍
- src/asset_lab/services/city_service.py（`CityService` 建構子注入與 `build_timeline`，design §5、AD-2～AD-4）
- src/asset_lab/bootstrap.py（`Container.city_service`、`build_container` 組裝，§12）
- tests/test_city_service.py（上述 SC 的 test）
- tests/test_bootstrap.py（容器含 city_service）

## 依賴
- t02

## 切片理由
先做「時間軸與項目逐月狀態」這一半的 Service：純運算、虛構資料即可測，與 t04 可並行。與 `frame_at` 拆開是因為後者要截斷歷史並重用多個既有 Service，複雜度與風險更高。
