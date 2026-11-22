# 城市總覽元件技術試做結論

> 2026-10-31，分支 `spike/city-overview`（只在本機，不合併進 main）。原型為等角城市 Canvas 2D 頁，資料全為虛構。
> 結論：路線可行，建議進正式 Change。技術上沒有卡關，要決策的是建築版位、`streamlit` 版本下限、Community Cloud 實測。
> 之後經六輪使用者目視迭代（v1–v6，至 2026-11-01），版位定案為「沿街長條街廓」，設計條件見最後一節「目視迭代與設計條件」。Q1–Q8 是 v1 當時的量測；外觀、標籤、旗桿、版位以最後一節為準。
> v1 獨立驗收：11 項全部通過（範圍、ruff、spike 測試、全套 869 passed、隔離、啟動、AppTest 煙霧、API 引用、轉義、截圖、假資料）。非阻擋備註：`city.js` 標籤的 `l.sub` 當時只含數字與固定字串所以安全，日後若帶入資料字串要補 `esc()`。

## 方法與證據來源

- 啟動：`uv run streamlit run spikes/city_overview/harness.py --server.port 8599 --server.headless true`
- 自動化：Chrome headless 加 CDP，只連 `localhost:8599`。送滑鼠點擊、鍵盤、改視窗、模擬深淺色，並讀元件內計數器。
- 元件把 `mount#`、`runs`、`frames`、`picks`、`themeReads` 寫在畫面下方一行（`city.js:361-363`），截圖看得到。
- 截圖存在當次 session 的 scratchpad，不進 repo。

## Q1 掛載

- API 位置：
  - `site-packages/streamlit/components/v2/__init__.py:246-253`：`component(name, *, html=None, css=None, js=None, isolate_styles=True) -> ComponentRenderer`
  - `components/v2/types.py:299-306`：`__call__(*, key=None, data=None, default=None, width="stretch", height="content", **on_callbacks)`
  - `streamlit/__init__.py:326`：載入 `streamlit.components.v2`
- 畫面：天空、九棟建築、購屋工地（吊車、五旗、鷹架）、坑洞、樹、雨雲星、窗燈、標籤全部正常。
- 文件與原始碼差異：
  - 文件說 mount 時可傳 `isolate_styles`；原始碼 `__init__.py:216-226` 會丟掉並警告。
  - `height` 預設 `"content"`，高度由 JS 依寬度撐開。
- 其餘（`default` 需搭配 `on_<key>_change`、inline 字串需含換行）與原始碼一致。

## Q2 Python 到 JS

- 改資料畫面會更新。滑桿 20 到 8 後，月份、天氣（L2 暴雨）、高度、旗子都更新。
- rerun 是原地更新：整段操作 `mount#` 恆為 1，`runs` 一路加，`frames` 連續累加。只有換 `key` 才重新掛載（`mount 1→2`、`runs` 歸 1、選取丟失）。
- 動畫跨 rerun 保留：`us` 高度 136.2 → 119.3，約 0.9 秒，期間目標值也在變（128.8 → 122.9 → 119.3），沒有跳變。機制是 `WeakMap` 以 `parentElement` 保存實例（`city.js:4`、`354-357`）。
- 「肉眼無閃爍」列入目視清單，試做只量到計數器連續。
- 設計含意：高度須用整段歷史最大值當分母。第一版用當月最大值，`tw` 任何月份都頂到 161.9，跨月不可比。已改為 `build_payload(max_asset=, max_liab=)` 並加測試。

## Q3 JS 到 Python

- 點建築可知是哪一棟。點 `tw` 再點 `house`，`result.selected` 與 `result.picked` 依序為 `tw`、`house`，`on_picked_change` log 為 `["tw","house"]`。
- trigger 與 state 的語義：
  - `setTriggerValue("picked", id)` 是事件，只在觸發那次 rerun 有值。按「只觸發 rerun」後 `result.picked` 變 `None`。
  - `setStateValue("selected", id)` 持久，存在 `st.session_state[key]`，rerun 後仍是 `house`。
  - 換 `key` 後兩者都重置為 `None`。
- callback 內讀 trigger 要用 `st.session_state[key].picked`，因為 callback 在腳本主體之前跑，還沒有 `result`（`harness.py:22-26`）。
- 控制迴圈：Python 把 `selected` 經 `data` 餵回，JS 以 `data.selected` 為準；點擊當下 JS 先本機高亮。
- 每次點擊觸發整頁 rerun，正式 app 要考慮 rerun 成本。

## Q4 寬度

- `width="stretch"` 加 `ResizeObserver`（`city.js:346`）可同寬。視窗 1280、900、390 時 canvas 寬 818、438、356，`mount#` 不變。
- 390 寬無水平捲動：`innerWidth`、`docScrollWidth`、`bodyScrollWidth`、`mainScrollWidth` 都是 390。
- 縮放時 rAF 保留、畫布重算，不重新掛載。
- 小缺點：390 寬時天氣面板與月份牌占比偏大，建築偏小。

## Q5 主題

- 元件在 shadow root 內（預設 `isolate_styles=True`），`getComputedStyle(wrap)` 讀得到 `--st-*`。實際用到的有：
  - `--st-background-color`（判深淺）
  - `--st-secondary-background-color`
  - `--st-text-color`
  - `--st-border-color`
  - `--st-primary-color`
  - `--st-font`
  - 位置見 `city.js:46-64`。
- canvas 不認 CSS 變數，所以用 1×1 canvas 的 `toHex` 把任意 CSS 色（rgb、color-mix、命名色）轉成 `#rrggbb`，再交給原型的 `mix/shade`。
- 背景亮度小於 128 視為夜景，在 `.city` 設 `data-night`，`city.css` 切換區域色票。
- 模擬系統深／淺色時 Streamlit 跟著切，default export 重跑，`night` true 與 false 互換。
- 注意：headless Chrome 預設 `prefers-reduced-motion: reduce` 與 `prefers-color-scheme: dark`。reduced-motion 下原型走靜態分支，這是原型既有行為；試做用 CDP 改成 `no-preference` 測動畫。
- 未驗證：自訂 `[theme]`（試做不能動 `.streamlit/`）。字型改用 `--st-font`，中文靠系統字型。

## Q6 可測性

- `uv run pytest spikes/city_overview -q` → 10 passed。涵蓋：
  - JSON 可序列化
  - 進度封頂
  - 等級、建照數驗證
  - 選取失效處理
  - 地塊重疊與出界
  - 歷史最大值覆寫
  - 假資料有大跌情境
- AppTest：部分推翻、部分確認。
  - 推翻「完全看不到」：`AppTest.from_file(harness).run()` 不報錯，元件以 `UnknownElement`（type `bidi_component`，帶 `key`、`proto`）出現，`result.*` 預設 `None`。`app_test.py:25,506-512` 為 AppTest 註冊了 `BidiComponentManager`，`element_tree.py` 沒有 bidi 專屬類別。
  - 確認「測不到行為」：JS 不執行，無法點擊、無法驗 trigger/state，`at.session_state["city_main"]` 恆為 `{}`。
- 建議測試策略：payload 單元測試、一個 AppTest 煙霧測試、一份人工目視清單。

## Q7 移植成本

- `city.js` 368 行、26.3 KB，`city.css` 2.3 KB。原型 script 約 530 行，整檔 51 KB（含 HTML 與 CSS）。
- 原樣搬入約 90%：
  - 幾何（`P/up/lerp/poly/inPoly`）
  - `draw`、`windowsOn`、`drawBuilding`、`drawPit`、`drawTree`、`drawHouse`、`drawZoneSigns`、`pill`、`drawLabels`
  - 命中測試、hover/tooltip、天氣粒子、`resize`、`mix/shade/hash`
- 改動：
  1. 全域狀態改 per-instance closure，並用 `WeakMap` 保存。
  2. 資料改讀 payload，高度分母由 payload 提供。
  3. 色票改讀 `--st-*`，加 `toHex`。
  4. 點擊走 `setTriggerValue/setStateValue`。
  5. 移除寫死 `tw` 的屋頂天線。
  6. 建照旗、警示牌、地塊位置改由 payload 驅動。
- 沒搬：右側面板、時間軸回放、月份滑桿，正式版改用 Streamlit 原生元件。`buildModel` 改成 Python 假資料。
- 原型的 Google Fonts CDN 不用，改用 `--st-font`。

## Q8 正式 Change 建議

### 畫面元素對應 app 既有資料

| 畫面元素 | app 來源 | 狀態 |
|---|---|---|
| 高度＝市值 | `MonthlyRecordModel`；`AllocationService.snapshot`／`holding_value_trend` | 有，需歷史最大值 |
| 建築種類／分區 | `HoldingModel.category`、`kind`（`constants.ASSET_CATEGORIES`） | 有，需新增 category→shape/zone 對照 |
| 天氣＝協定等級 | `ProtocolService.assess` → `ProtocolStatus.level_code`、`drawdown`、`status` | 有，僅最新月；逐月等級需另算 |
| 天氣名稱（晴／多雲／暴雨／颱風） | 無 | **缺**：`PROTOCOL_LEVELS` 只有必做與禁止文案 |
| 工地＝自備款進度 | `HouseService.bucket_value`／`bucket_progress` → `BucketProgress.progress_pct` | 有，超標不封頂，JS 端封頂 |
| 五支旗＝建照 | `HouseService.assess_triggers` → `TriggerChecklist.conditions`（anchor、income、down_payment、payment、cognition） | 有，`down_payment` 對應原型 `bucket` |
| 分區警示牌 | `AllocationService.compute_drift` → `DriftRow`（threshold 傳 5） | 有 |
| 購屋用途標記 | `HoldingModel.purpose == "house"` | 有 |
| **建築版位 lot** | 無 | **缺，最大設計題**：原型 9 棟固定格位，app 持有項目由使用者自訂、數量不定。試做已做出可用規則，見最後一節 |

「只在月結變、不做分數」：元件只吃已存檔月份的資料，沒有即時行情輸入，天生符合。

### 元件放哪

- `src/asset_lab/city/` 子套件：
  - `payload.py`：純函式，比照 `overview_presentation.py`。
  - `component.py`：註冊一次，加 wrapper。
  - `city.js`、`city.css`：由 Python 讀入。
- 不放 `views/*.py`，因為頁面檔尾端無條件呼叫 `render()`，不能被 import。
- `pyproject.toml` 的 `packages = ["src/asset_lab"]` 要確認 `.js`／`.css` 會被打包。

### 風險

1. Streamlit 下限：`pyproject.toml` 寫 `streamlit[auth]>=1.42`（`uv.lock` 鎖 1.66.1）。CCv2 在 1.42 沒有，下限要調高到實測可用版本，並確認 Cloud 安裝路徑吃 `uv.lock`。
2. Community Cloud 未實測。
3. 版位對應（見上表）。
4. 每次點擊整頁 rerun，需考慮成本與 `error_boundary`；點擊後開錄入要決定用 `st.dialog` 還是切頁。
5. 合成滑鼠事件不等於真手指，原型的 hover tooltip 在觸控裝置沒有等價物。
6. canvas 對螢幕閱讀器只是一張圖，需保留文字替代（總覽數字卡）。
7. 元件跑在頁面 DOM 權限下：holding 名稱是使用者輸入，tooltip 的 `esc()` 轉義要保留並加測試。
8. 字型不能用 CDN。

### 粗估 7 個 Task

1. category→zone/shape 對照與自動版位規則，加 payload 純函式與測試。
2. 資料組裝層：接 `ProtocolService`、`HouseService`、`AllocationService`，加歷史最大值。
3. 元件套件正式化，含轉義測試。
4. 頁面掛載，處理 `picked`／`selected`、rerun 與錯誤兜底。
5. 天氣名稱與文案常數，`no_data`／`insufficient_data` 的中性呈現。
6. 調高 `streamlit` 下限、確認打包、Community Cloud 實測。
7. AppTest 煙霧測試、README 與文件同步、目視驗收。

## 待使用者目視清單

1. 真實點擊所有建築與工地，Python 端名稱正確；手機觸控點得準（坑洞、小棟 `sat`）。
2. 拖滑桿時高度緩動是否順、有沒有整張重畫的閃爍。
3. hover tooltip 位置與遮擋（試做截圖中 tooltip 蓋住鄰棟一部分）。
4. 雨、雲、星、L3 閃電的觀感與 CPU 負載；reduced-motion 的靜態畫面。
5. 深淺主題在真實瀏覽器的觀感，尤其自訂 `[theme]` 的對比。
6. 手機 390 寬的可讀性：天氣面板、月份牌、標籤字級。
7. 視窗連續拖拉縮放有無殘影（試做只測了離散的三個尺寸）。
8. Community Cloud 上能否跑、載入速度。
9. 中文字型在實機的字形。

第 3、5、6 項的標籤、主題、手機部分，使用者已在 v1–v6 目視過，結論見下一節。

## 目視迭代與設計條件（v1–v6）

### 使用者定案的設計條件（依優先序，衝突時照此取捨）

1. **像城市街區**：
   - 街區沿等角格線切成平行四邊形，街區之間是沿格線的道路。
   - 整張地圖是一塊完整的菱形地盤，完全落在畫布內，不被切掉。
2. **同類別建築放在同一街區**。
3. **名稱位置**：名稱固定在自家建築正下方（底座前緣），所有建築用同一套相對位置。
   - 底板不透明。
   - 淺色、深色主題的對比都至少 4.5:1。底板用 `--st-secondary-background-color`，文字用 `--st-text-color`，不足時改用黑或白。
4. **名稱不擋建築**：
   - 標籤不蓋住任何建築、工地（含吊車）、負債坑洞。
   - 標籤彼此也不重疊。
   - 不把名稱移離建築來解決，用版位替名稱留空間。
5. **購屋條件用旗桿**：
   - 五根立體旗桿，放在購屋工地正前方，布旗等角透視、輕微飄動，reduced-motion 時靜止。
   - 高度比 v3 低 20%。
   - 達成升到桿頂並展開；未達成降半旗並垂掛。靠位置與形狀區分，不只靠顏色。
   - 顏色取場景色票，不要 UI 圖示風格（打勾、叉叉方框會被認為突兀）。
6. **分區名稱不單獨立牌**：分區用建築顏色與名稱牌色點表示；分區警示改成名稱牌上的警示三角，因為立牌會擋到名稱帶。
7. **速度**：版位要確定性計算，不做回溯搜尋（實作是 12 組候選參數加固定點迭代到收斂）。實測 30 棟約 25–28ms。
8. **建築盡量大**：優先序最低。

### 定案版位：沿街長條街廓

- 幾條平行大道把地盤切成街帶，名稱牌掛在建築前方的大道上。每條街帶通常只排一排建築；某類別在一條街帶放不下時才加深成 2–3 排（30 棟時股票類為 2 排）。
- 每個類別是街帶中的一段，類別之間用短橫街分隔；高的類別排在後方街帶。
- 只用兩條間距規則，直接算出：
  - 同一列：下一棟建築和旗桿都要落在上一棟名稱牌之外。
  - 列與列：前方所有物件（含吊車、旗桿）的投影頂端都要低於後方名稱牌的底緣。
- 縮放只看畫布寬度，畫布高度跟著內容伸縮，所以地圖一定完整在畫布內。
- 投影高度用各項目的歷史最高市值，所以版位逐月固定。
- 實測：9 棟縮放約 0.54，20 棟約 0.43；計算耗時 9、20、30 棟約 5、11–12、25–28ms（兩次獨立實測）。
- 20 棟時名稱牌只寫名稱，金額改在 hover 提示顯示；保留金額的話縮放會掉到約 0.3。
- 手機 390 寬放不下全部名稱，依序降級為完整名稱牌、只有名稱的精簡牌、10px 字級的精簡牌、小編號牌，地圖下方再列對照表。試做者實測 9 棟時約 8/10 有標示。畫出來的部分仍然零重疊、零遮擋。

### 走過的彎路（給正式設計的提醒）

- **v1–v2**：標籤找最近的空地放，結果位置散亂；旗子用 UI 圖示，風格突兀。
- **v4**：用回溯搜尋排版、放棄分區來換「不擋」。首次計算要 3 秒，同類也不再同區。
- **v5**：沿螢幕垂直方向切欄帶，不沿等角格線，結果看起來是斜磚紋色帶、不像街區。縮放只按寬度、列距用全場最高投影，造成地圖被切掉與大片空地。
- **教訓**：
  - 等角視角下前排本來就會擋後排，「名稱在建築正下方又不擋建築」必須靠版位預留名稱帶，不能靠事後挪標籤。
  - 街區必須沿等角格線切。
  - 版面是品味題，正式設計時應該出 2–3 個方案給使用者挑，不要一輪輪修。另一個候選方案「十字四象限」（仿原型）也做到全部條件，使用者選了長條街廓。
