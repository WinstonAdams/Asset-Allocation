# 架構分析：城市總覽（city-overview）

> 1-2b 產出，供 1-2 designer 整合。
> 輸入：`proposal.md`、`spike-findings.md`、現有 codebase（feature/city-overview 與 main 程式碼相同），以及本機分支 `spike/city-overview` 的試做程式。1-2a 技術選型已跳過，技術路線以試做結論為準。
> 標「須確認」的項目是未決事項，designer 不可自行定案，要回頭問使用者（集中列在第 4 節）。

---

## 0. 給 designer 的五個重點

1. **分三層**：
   - 領域組裝：新增 `CityService`，純運算類別，以 DI 注入三個既有 Service。
   - 呈現轉換：新增 `asset_lab/city/` 子套件，負責版位、payload、小卡文案，都是純函式。
   - runtime 黏合：`city/component.py` 註冊 CCv2；`views/overview.py` 用既有的 `rerun_fragment` 包住城市區塊。
2. **歷史月份不改既有 Service**：
   - 做法：把月度紀錄截斷到該月，並排除當時還沒出現的購屋項目，再重用 `HouseService`、`ProtocolService.assess`、`AllocationService.snapshot` 與 `compute_drift`。
   - 效果：最新月的結果與現行總覽頁、買房頁逐位相同，可以寫成測試。
3. **Python 是唯一事實來源**：
   - 幾何常數、天氣名稱、等級標籤、中性文案、旗桿鍵都由 Python 提供，JS 只負責畫圖。
   - 試做 JS 裡寫死的這些要拿掉：`LEVELS`、`'資料未滿 3 個月'`，以及與 `HOUSE_TRIGGER` 不同名的旗桿鍵。
4. **試做程式是規格與參考實作，不能直接搬**：
   - 版位模組有模組級可變狀態，在 Streamlit 多執行緒下不安全。
   - 全部檔案不符合 01 編碼風格。
   - 處理方式：重寫，並把試做測試當回歸基準。
5. **最大的未驗證風險**是 CCv2 元件放在 `st.fragment` 內時，互動會重跑多大範圍，以及元件會不會重新掛載。建議第一個 Task 先做 tracer bullet 驗證（見 §5）。

---

## 1. 現況分析

### 1.1 實際分層與 02-architecture 的對照

| 02 規範層 | 本專案實際 | 備註 |
|---|---|---|
| main.py | `app.py`（登入守門、量測、路由）＋ `bootstrap.py`（`Container` 以 keyword args 組裝，並用 `cache_resource` 快取） | Streamlit 版本的 main，模組 docstring 已說明不採 argparse 模型 |
| Controller | `views/*.py`，每頁一個 `render()`：讀 repo、呼叫 service、渲染畫面。頁面是唯一的 catch 點 | 檔尾無條件呼叫 `render()`，所以不能 import、不能做單元測試 |
| Service | `services/*.py`，全部是無依賴的純運算類別；`MonthlyInputService` 例外，建構子注入 repo 與常數 | 目前沒有 Service 呼叫 Service 的先例 |
| Repository | `repositories/*`；`CachingConnection`／`CountingConnection` 對上層透明 | 同一次執行內重複讀取會命中 `ReadCache`，成本低 |
| 呈現純函式 | `charts.py`、`overview_presentation.py`：模組級函式加 frozen dataclass，放在 `src/asset_lab/` 根目錄 | 抽出來是為了讓頁面邏輯可測，屬於「Service 必須是類別」規則下的既有例外 |
| runtime 黏合 | `rerun_runtime.py`（`rerun_scope`、`verified_container`、`rerun_fragment`）、`error_boundary.py`、`amount_widget.py` | `rerun_fragment` 已封裝四件事：`st.fragment`、量測、錯誤兜底、連線驗證 |

**Logging**：
- 現況：全專案用 stdlib `logging`（`logging.getLogger(__name__)`、`%s` 佔位），沒有引入 `utils`／`utils_v2`／structlog。
- 依 `utils-version-guard` 判定：檔案兩種 import 都沒有，`pyproject.toml` 也沒有，屬本專案自有慣例。
- 結論：新程式維持 stdlib logging，不引入 structlog。04-cross-cutting 的 structlog 欄位規範不直接適用，rules-reviewer 需要知道這點。

### 1.2 總覽頁現況

`views/overview.py`（233 行）目前依序做這些事：

1. 讀全歷史紀錄，算 `cumulative_twr_series`。
2. 用 `assess` 判定協定等級。
3. 用 `net_worth_series` 取淨值。
4. 另跑一套買房編排 `_compute_house_summary`，與 `views/house.py:57-115` 是同一段邏輯的第二份，docstring 已標為「已知限制」。
5. 渲染：燈號、必做與禁止、3 個 metric、買房摘要 2 個 metric。

**頁面上目前沒有任何圖表**（見 Q10）。

### 1.3 畫面元素、既有能力與歷史月份可算性

這是 designer 最需要的對照表。

| 畫面元素 | 既有來源 | 最新月 | 歷史月 m | 做法 |
|---|---|---|---|---|
| 建築高度、坑洞深度 | `monthly_records.market_value` | 可算 | 可算 | `CityService` 直接從 records_df 建（項目 × 月）值矩陣。`holding_value_trend` 只含資產，坑洞不能用它 |
| 高度分母 | — | — | — | 全歷史 `max_asset`／`max_liab`，是全域值（見 Q1） |
| 版位用峰值 | — | — | — | 各項目自己的全歷史最高值 |
| 分區與外形 | `HoldingModel.category`，封閉 5 類（`data_io_service.py:170` 有驗證） | — | — | 新增常數對照表（見 Q2） |
| 天氣 | `ProtocolService.assess(series)` | 可算 | 可算 | 把 series 截斷到 ≤ m 再 assess。`cumulative_twr_series` 每點都是前綴計算（`return_service.py:231-234`），截斷等價於重算，ProtocolService 不用改 |
| 工地進度 | `HouseService.bucket_value` → `bucket_progress` | 可算 | 可算，要截斷加過濾（A3） | `progress_pct` 不依賴 `current_year`。歷史月不要呈現 `years_to_target` 與 `required_annual_accumulation`，這兩個是以今天計算的 |
| 旗桿：自備 `down_payment` | `assess_triggers` | 可算 | 逐月值配目前門檻 | `bucket(m)` 與 `cash_reserve(m)` 逐月算；目標總價、自備比率、現金地板用目前設定 |
| 旗桿：收入 `income` | 只依參數 | 可算 | 只能用目前設定 | 參數沒有歷史 |
| 旗桿：月付 `payment` | `AffordabilityService.payment_for_price(params)` | 可算 | 只能用目前設定 | 同上 |
| 旗桿：定錨、認知 | `subjective_triggers` 表，只存目前勾選 | 可算 | 只能用目前設定 | 同上 |
| 偏離三角 | `snapshot(by="category")` 加 `compute_drift(threshold=DEFAULT_REBALANCE_THRESHOLD)` | 可算 | 現況％逐月算，目標用目前設定 | 目標比重沒有歷史 |
| 購屋排除 | `HoldingModel.purpose` | — | — | 以目前標記套用到所有月份（BR-8） |

**結論**：
- 五根旗桿中只有自備（`down_payment`）會逐月變化，其餘四根在歷史月份都是「依目前設定判定」。
- 偏離三角在歷史月份同樣是「現況逐月、目標用目前設定」，但 proposal BR-10 只提到購屋條件（見 Q7）。

### 1.4 試做程式盤點

| 檔案 | 行數 | 可沿用 | 必須改 |
|---|---|---|---|
| `city_layout.py` | 659 | 演算法：兩條間距規則、12 組候選參數加固定點迭代、`check()` 驗證器 | <ul><li>模組級可變 `_NJ`：`layout_city` 開頭與結尾各 `clear()` 一次，多 session 同時排版時會互相污染</li><li>單字母命名、沒有 docstring</li><li>用了 `from __future__`、`# fmt: skip`</li><li>`Spec.zone` 是試做自訂的鍵</li></ul> |
| `city_payload.py` | 156 | 驗證規則：地塊重疊、出界、`selected` 失效時靜默清除 | <ul><li>`PERMIT_KEYS` 寫成 `bucket`／`pay`，與 `HOUSE_TRIGGER` 的 `down_payment`／`payment` 不一致</li><li>`level` 用 int</li><li>沒有空地與名稱牌淡化的欄位</li><li>「購屋工地」寫死</li></ul> |
| `city_component.py` | 52 | 註冊方式、`width="stretch"`、`height="content"` | 拿掉 html 裡的 `.dbg` |
| `city.js` | 576 | 約九成：繪圖、命中測試、`WeakMap` 實例、讀主題色、手機降級 | <ul><li>業務文字寫死：`LEVELS` 的天氣名與等級標籤、`'資料未滿 3 個月'`（等於寫死 `PROTOCOL_MIN_DATA_MONTHS`）、`'應繳 '`、`'自備款 '`</li><li>幾何常數與 Python 各一份，檔頭註明「改一邊就要改另一邊」</li><li>畫面上的 dbg 計數列與 `parentElement.__city`</li><li>沒有空地與淡化名稱牌的畫法（新功能，需目視驗收）</li></ul> |
| `city.css` | 36 | 色票 | 5 個分區色（cash、deposit、stock、ins、debt）與 app 的 5 個資產類別不是一對一，台股與美股共用 stock（Q2） |
| `city_fake_data.py`、`harness.py` | — | 假資料可改寫成測試 fixture | 不進正式碼。試做把購屋用途項目（`cash2`、`dep1`）同時畫成建築又計入 bucket，**與 BR-8 相反** |
| `test_city_payload.py` | 166 | 移植成正式回歸測試：不重疊、同區同街廓、多種寬度都在畫布內、確定性、30 棟 50ms 內、跨月版位不變 | — |

### 1.5 技術債與擴展性限制

**既有技術債（會影響本 Change）**

- **TD-1 買房評估編排會有第三份**：
  - 現況：「參數 → bucket → 預備金 → 正算月付 → 進度 → 觸發條件」已在 `views/house.py` 與 `views/overview.py` 各寫一份。
  - 影響：城市需要同一套邏輯，而且要逐月算。如果再在頁面寫第三份，三份分岔的風險最高。
- **TD-2 Service 輸入型別混用**：
  - `AllocationService` 與 `ReturnService` 吃 DataFrame，`HouseService` 吃 `list[MonthlyRecordModel]`。
  - DataFrame 轉 Model 的 `_to_month_records` 在兩個 view 各有一份，城市兩種型別都要用。
- **TD-3 views 不能 import**：頁面內的邏輯都無法單元測試，可測邏輯必須外移（先例是 `overview_presentation`）。
- **TD-4 常數存取慣例不一致**：
  - `house_service.py:42` 與 `overview_presentation.py:25` 在模組頂層存取 constants，04 §3.2 列為違規。
  - `MonthlyInputService` 則走建構子注入。
  - 新程式要擇一，建議 `CityService` 走注入。
- **TD-5 D14 尚未實作**：
  - 現況：`compute_drift` 仍計入購屋標記資產。
  - 影響：城市不畫購屋項目，但偏離三角含購屋金額，會出現「某街段亮警示，可是讓它偏離的錢不在畫面上」（Q7）。
- **TD-6 `cumulative_twr_series` 是 O(月數²)**：
  - 原因：每個月都重算一次前綴 TWR。
  - 影響：fragment 必須自己取資料，所以整頁重跑時，城市區塊與下方數字卡會各算一次。

**擴展性限制（試做帶來的）**

- 版位只量到 30 棟（約 25–28ms，畫布寬 818），超過 30 棟沒有量測。物件超過 12 個時改用精簡名稱牌。
- 高度上限 `H_TOP` 固定。資產規模懸殊時，小棟會壓到最低高度 8px；平方根壓縮已經緩和這個問題。
- 字寬兩邊算法不同：Python 依字元類別保守估算，JS 用 `measureText` 實量後再降級。不一致時只會比預期更安全，可以接受。

---

## 2. 設計提案

### 2.1 元件與職責

```
views/overview.py                 Controller / View
  render()
    st.title
    _render_city()                ← @rerun_fragment(label="城市總覽")，不帶參數
    既有內容：協定燈號、必做與禁止、指標、買房摘要（文字替代；跟不跟滑桿見 Q6）
  _render_city()
    container = _container()
    讀取：holdings、records_df（全歷史）、thresholds、house params、subjective、targets
    series   = return_service.cumulative_twr_series(...)
    timeline = city_service.build_timeline(...)       → 月份、項目規格、峰值、值矩陣
    沒有任何月份 → 中性呈現（BR-11，Q11）
    slot     = st.container()                         ← 先佔城市的位置
    month    = 月份滑桿（畫在 slot 下方，預設最新月）
    frame    = city_service.frame_at(month=..., ...)  → 天氣、工地、旗桿、偏離、與前一月差額
    layout   = city.layout.layout_city(specs)         → 以 lru_cache 快取
    payload  = city.payload.build_payload(...)
    with slot: result = city.component.city_overview(payload, key=...)
    小卡     = city.presentation.card_for(result.selected, ...) → 用 st.* 渲染

services/city_service.py          CityService，純運算類別
  __init__(*, house_service, protocol_service, allocation_service,
           zone_by_category, house_purpose, ...)       ← 全部 keyword args 注入
  build_timeline(...) -> CityTimeline
  frame_at(...)       -> CityFrame
models/results.py                 新增 CityHoldingSpec、CityTimeline、CityFrame（pydantic，與其他 Service 輸出同處）

src/asset_lab/city/
  __init__.py      保持空白，不 re-export component，免得測試 import 時觸發元件註冊
  geometry.py      投影與障礙物公式，與 city.js 一一對應，方便並排審查
  layout.py        排版規則、layout_city、check（public，給測試用）
  payload.py       把版位、timeline、frame、selected、文案組成 JSON 契約
  presentation.py  小卡文案、天氣顯示文字（純函式，定位比照 overview_presentation）
  component.py     CCv2 註冊與 wrapper（BR-6：不碰 st.user、st.secrets、資料庫）
  city.js / city.css

core/constants.py   CITY_* 常數：類別對分區與外形、天氣名稱（BR-12）、「依目前設定判定」等文案
bootstrap.py        Container 增加 city_service
pyproject.toml      調高 streamlit 下限（A10），並確認 wheel 會打包 .js 與 .css
```

### 2.2 資料流與重跑範圍

- **進入總覽頁**（整頁執行）：`app.py` → `overview.render()` → 城市 fragment 首次 inline 執行 → 下方數字卡。
- **拖滑桿、點建築**：只重跑 `_render_city`。
  - 依據：CCv2 在原始碼中走 `register_widget`（`components/v2/bidi_component/main.py:481、496`），與一般 widget 同一套機制，推定在 fragment 內互動只會重跑該 fragment。
  - 試做沒有實測，要在 §5 第 1 步驗證。
  - 量測 log 會記 `kind=fragment page=城市總覽`，可以直接拿來檢查成功標準 5。
- **「城市在上、滑桿與小卡在下」的畫法**：
  - 在 fragment 內先開 `st.container()` 佔位，接著渲染滑桿取得值，再回頭把元件畫進佔位容器。
  - 限制：fragment 內的 widget 不能寫進 fragment 外建立的容器，所以佔位容器必須在 fragment 內建立。
- **點擊狀態**：
  - 小卡用 `setStateValue("selected")`，它是持久值，存在 `session_state[key]`。Python 再把 `selected` 經由 payload 傳回 JS（試做 Q3 驗證過的控制迴圈）。
  - 本 Change 不跳頁、也不開錄入，`setTriggerValue("picked")` 沒有用途。建議不註冊 `on_picked_change`，JS 也不送（YAGNI）。
- **換頁後再回來**：Streamlit 會清掉沒渲染的 widget state，所以滑桿回到最新月、選取清空。這符合「預設顯示最新月結」。

### 2.3 Python 與 JS 的契約原則

1. **JS 不做業務判斷**：
   - Python 決定：達成或未達、偏離與否、天氣等級與名稱、是否空地、名稱牌是否淡化、所有顯示文字。
   - JS 只負責：投影、動畫、命中測試、依畫布寬度降級名稱牌。
2. **幾何常數只有一份**（A4）。
3. **使用者輸入只用 `textContent` 放進 DOM**：
   - 例外是 `innerHTML`，用到時一律搭配 `esc()`。
   - canvas 的 `fillText` 不經過 HTML 解析，不需要轉義。
   - 以 pytest 靜態掃描 `city.js` 把關（BR-4）。
4. **旗桿鍵與順序**：鍵名直接用 `HOUSE_TRIGGER`，順序用 `HOUSE_TRIGGER.ALL`；顯示名稱由 Python 帶入。
5. **天氣 payload 是一個顯示物件**：包含 code、天氣名、等級標籤、嚴重度、副標文字。不傳 int 等級讓 JS 查表。

### 2.4 錯誤隔離與降級

- **城市壞了不影響數字卡**：`rerun_fragment` 內含 `error_boundary`，城市區塊的任何例外只會影響城市本身，下方數字卡（文字替代）照常顯示。
- **版位無法收斂**：試做會丟 `ValueError("版位無法收斂")`，現在會落入「未預期錯誤」，畫面只顯示通用訊息。designer 可以決定是否改成專屬的領域例外（`AssetLabError` 子類）並給中性文案。
- **無資料與資料不足**：沿用 `overview_presentation.NO_DATA_MESSAGE` 與 `INSUFFICIENT_DATA_MESSAGE` 兩種中性文案，不另寫第三套。

### 2.5 快取策略

- **版位**：
  - 做法：純函式加 `functools.lru_cache`，key 是 frozen 的 specs tuple（id、名稱、分區、kind、外形、峰值）。
  - 內容本身就是 key，不需要失效機制。跨 session 共用在單一使用者的 app 可以接受。
  - 理由：每拖一次滑桿省下最多約 28ms；成本已實測，key 也很單純，不算過早最佳化。
- **timeline、frame、series**：先不快取，等量測 log 證明超出預算再處理（A5）。

### 2.6 測試分層

| 層 | 測什麼 | 工具 |
|---|---|---|
| `CityService` | 歷史月的截斷與過濾語義、購屋排除、空地；**最新月結果與現行總覽頁及買房頁一致**（防 TD-1 分岔） | pytest，純函式 |
| `city.layout` | 移植試做的 6 項：不重疊、同區同街廓、多種寬度都在畫布內、確定性、30 棟 50ms 內、跨月版位不變 | pytest；計時取多次最佳值以免抖動 |
| `city.payload` | JSON 可序列化、`selected` 失效時清除、空地與淡化欄位、旗桿依 `HOUSE_TRIGGER.ALL` 排序 | pytest |
| `city.js` 靜態檢查 | `innerHTML` 一定搭配 `esc(`、沒有業務文案字串、幾何常數來自前置的 `GEOM` | pytest 讀檔掃描 |
| 頁面 | 總覽頁掛上 `bidi_component`（AppTest 中為 `UnknownElement`）、無例外、無資料時不報錯 | AppTest：`views/overview.py` 加 `build_container` 加暫存 libsql，比照 `tests/test_data_io.py:841` |
| 視覺與互動 | 點擊、動畫、深淺色、手機、Community Cloud | 人工目視清單，沿用 `spike-findings.md` 的清單 |

---

## 3. 權衡分析

### A1：領域組裝放在哪裡

**建議**：新增 `CityService`（純運算類別）。bootstrap 以 keyword args 注入：
- `HouseService`、`ProtocolService`、`AllocationService`
- 類別對分區的對照表

**優點**：
- 可以單元測試（TD-3）。
- 「截斷、過濾、逐月」屬於篩選與轉換，02 §4 禁止 Controller 做這類細部資料操作。
- 重用既有 Service，不新增財務計算，符合 ROADMAP「不新增任何決策、計算」的邊界。

**缺點**：
- 是第一個依賴其他 Service 的 Service（既有 Service 全都無依賴）。
- `Container` 多一個欄位。

**否決**：
- (a) 全部寫在 `views/overview.py`：不可測，overview 會變成 God view，也違反 Controller 禁止細部資料操作。
- (b) 寫成模組級純函式（像 `overview_presentation`）：這一層含業務口徑（購屋排除、歷史 bucket 語義），依 02 §5 屬於 Service，必須是類別。
- (c) 在 `HouseService`／`ProtocolService` 加 `as_of` 參數：會動到買房頁與總覽的既有路徑，風險外溢；ProtocolService 其實根本不需要改。

### A2：CityService 的介面粒度

**建議**：拆成兩個方法，只算選定月，不預先算全部月份。
- `build_timeline`：只依 holdings 與 records，產出月份清單、項目規格、峰值、值矩陣。版位與滑桿都用它。
- `frame_at`：選定月的天氣、工地、旗桿、偏離，以及與前一月的差額。

**優點**：
- 避免 O(月數 × 紀錄數) 的全月份 bucket 預算。`HouseService._current_market_values` 每次呼叫都會重建字典。
- 每個方法的參數集中，降低 God method 風險。

**缺點**：每次 fragment 重跑都要重建 timeline，不過是 O(紀錄數)，很便宜。

**否決**：一次算完所有月份的 frame 存進 `session_state`。這需要失效機制（錄入後要刷新），會和 ReadCache 的 TTL 交互，收益也還沒有量測證據。

### A3：歷史月份的口徑（截斷加過濾）

**建議**，`frame_at(m)` 的做法：
- HouseService：傳入 `year_month ≤ m` 的紀錄，並先從 holdings 排除「第一筆紀錄月份晚於 m」的購屋項目與現金項目，再呼叫 `bucket_value` 與 `cash_reserve_value`。
- ProtocolService：傳入 `year_month ≤ m` 的 series。
- AllocationService：`snapshot` 只傳 m 當月的紀錄。

**優點**：
- 既有 Service 一行都不用改。
- m 是最新月時，過濾不會排除任何項目，截斷也等於沒截，所以結果與現行頁面逐位相同，可以寫成一致性測試。

**缺點**：
- 「第一筆紀錄月份」是 CityService 自己的推定。
- 從未錄過紀錄的購屋項目，在每個歷史月都會以初始市值計入。這與現行「從沒有紀錄就用初始市值補」一致，但用在歷史月仍是推定（Q3）。

**否決**：
- 純截斷不過濾：晚建立的購屋項目會以初始市值灌進早期月份，高估歷史進度。
- 改用 `holdings.created_at`：要改 Model 與 Repository；這個欄位可為 NULL，語義是建檔時間而不是開始持有的時間。

### A4：幾何常數只留一份

**建議**：
- 以 Python 常數為準。`component.py` 註冊元件時，把常數序列化成一行 `const GEOM = {...}`，加在 `city.js` 內容的最前面，JS 改讀 `GEOM`。
- 公式層（`plate_rect`、`obstacles`、`flag_rect`）仍是兩邊各一份，用 Python 的 `check()` 測試加人工目視兜底，並記為已知技術債。

**優點**：常數不可能不同步，也不會讓每次 rerun 的 payload 變大。

**缺點**：單獨打開 JS 檔看不到常數值；公式層仍有重複。

**否決**：
- (a) 維持兩份，測試用 regex 解析 JS 來比對：脆弱，而且只能比常數。
- (b) 每次都放進 payload：可行，但每次 rerun 都重送不會變的資料，也把設定和資料混在一起。可以當次選。
- (c) Python 算好螢幕座標再送給 JS：縮放取決於瀏覽器的畫布寬度，Python 不知道寬度，做不到。

### A5：快取範圍

**建議**：只快取版位（§2.5），其餘等量測再說。

**觸發條件**：用成功標準 5 的量測 log 比較總覽頁切頁耗時中位數，若增加超過 100ms，再對 series 加「每次執行只算一次」的 memo（處理 TD-6）。

**否決**：一開始就用 `st.cache_data` 包住 timeline 或 series。DataFrame 雜湊與 pickle 本身也有成本，會讓純函式模組依賴 streamlit，而且目前沒有證據需要。

### A6：Fragment 的範圍

**建議**：城市、滑桿、小卡放在同一個 `rerun_fragment`；既有數字卡留在 fragment 外面。

**優點**：
- 符合成功標準 5（拖滑桿只重跑城市區塊）。
- 自帶錯誤兜底。
- log 可以區分是整頁還是 fragment 重跑。

**缺點**：
- fragment 要自己取資料，所以整頁重跑時，城市與下方數字卡會各讀一次資料（命中 ReadCache）、各算一次 series（TD-6）。
- CCv2 在 fragment 內的行為還沒實測。

**否決**：
- 不用 fragment：每拖一次滑桿就連登入守門、連線驗證一起整頁重跑，違反標準 5。
- 數字卡也放進 fragment：卡片會隨滑桿一起重跑，「文字替代」也會變成跟著歷史月走，要看 Q6 的決定。

### A7：資料型別

**建議**：
- `CityService` 的輸出用 pydantic，放在 `models/results.py`，與所有既有 Service 的輸出放在一起。
- payload builder 從型別化的輸入組出 dict，JSON 契約寫進 design 的「介面契約」一節。
- 小卡與天氣顯示資料用 frozen dataclass，比照 `OverviewPresentation`。

**否決**：從 Service 到 JS 全程傳裸 dict（試做的寫法）。沒有型別，Service 層也無法靜態檢查。

### A8：業務文字放在哪裡

**建議**：
- 天氣名稱（晴、多雲、暴雨、颱風）、嚴重度、「依目前設定判定」、工地名稱、「應繳」、「自備款」都集中在 `core/constants.py` 的 `CITY_*` 類別。
- 等級標籤直接引用既有的 `PROTOCOL_LEVELS`，不重抄一份。
- 由 `city/presentation.py` 組成顯示文字，放進 payload。

**否決**：讓 JS 保留 `LEVELS` 表。協定等級標籤會有兩份（`constants.py` 與 JS），違反 BR-12 與「禁止魔法字串」。

### A9：版位模組的結構

**建議**：拆成 `geometry.py`（投影、障礙物、名稱牌矩形，與 JS 一一對應）與 `layout.py`（排版規則、候選參數、`layout_city`、`check`）兩個檔。

**否決**：
- 維持單檔 659 行：God module，難以審查。
- 拆成五個以上的檔：演算法內部耦合高，跨檔跳讀反而更難懂。

### A10：Streamlit 版本下限

**建議**：`streamlit[auth]>=1.66`，也就是試做實測過的版本。不需要追查 CCv2 最早出現在哪一版：本專案只部署一處，`uv.lock` 已鎖在 1.66.1，往下相容沒有受益者。

**否決**：
- 維持 `>=1.42`：1.42 不支援 CCv2，`pyproject.toml` 會與實際依賴矛盾。
- 精確釘死 `==1.66.1`：會擋掉安全更新；精確鎖定交給 `uv.lock` 就好。

---

## 4. 須確認（未決，需使用者決定）

**Q1 BR-2 的文字與試做實作不符**
- 試做實作：高度＝`H_TOP × √(當月值 ÷ 所有資產的全歷史最高值)`，分母是全域值，再取平方根壓縮。「各項目自己的歷史最高值」只用來排版位。
- BR-2 字面是「該項目整段歷史最高市值作分母」。照字面做，每棟在自己的高峰都會一樣高，不同項目之間就不能比。
- 建議：proposal 改寫為「分母＝所有資產整段歷史最高值（負債另計）；高度取平方根壓縮」。
- 另請使用者確認接受平方根：成功標準寫「高度＝市值」，字面上是線性。

**Q2 台股與美股的分區**
- app 有 5 個資產類別；試做的 5 個分區色是 cash、deposit、stock、ins、debt，台股與美股都落在 stock。
- 選項 (a)：合併成一個「股票」街段、同色。偏離三角仍按類別計算，只出現在該類別建築的名稱牌上。BR-1 的「同類別同街段」與 BR-7 都要改成「同分區」。
- 選項 (b)：各自一段，新增第 6 色。要重新驗證色票對比，兩色也要能分辨。

**Q3 從未錄過月度紀錄的購屋項目（只有初始市值），歷史月份的 bucket 要不要算**
- 沿用現行口徑：每個歷史月都以初始市值計入。
- 或：歷史月不計，只有最新月計入。

**Q4 某月有列但市值留空（仍持有、未更新）時怎麼畫**
- 既有口徑各不相同：配置與淨值「不貢獻」、TWR「沿用上一個有值的月份」、bucket 算 0。
- 選項 (a)：畫成空地。
- 選項 (b)：畫最低高度，小卡註明「未填」。
- 選項 (c)：沿用前值。

**Q5 「與前一月相比」的前一月是哪一個**
- 選項 (a)：滑桿上前一個有資料的月份。
- 選項 (b)：日曆上的前一個月，缺月時顯示「無資料」。

**Q6 下方數字卡是否跟著滑桿月份**
- proposal 說數字卡是城市的文字替代。
- 如果固定顯示最新月結，回看歷史月份時，城市就沒有對應的文字替代。
- 如果跟著滑桿，數字卡要搬進 fragment，總覽頁的既有行為也會跟著改變。

**Q7 偏離三角的口徑（D14 尚未實作）**
- 問題 1：`compute_drift` 仍計入購屋標記金額，城市卻不畫購屋項目，某街段可能因為看不見的錢而亮警示。
- 問題 2：如果某類別只有購屋項目，警示就沒有名稱牌可掛。
- 選項：接受（proposal 已寫明沿用 `compute_drift`）並在小卡註明，或在本 Change 隱藏這類情況。
- 另外：歷史月份的偏離三角也是用目前目標判定，BR-10 的「依目前設定判定」註記是否同樣適用？

**Q8 從來沒有月度紀錄的非購屋項目要不要蓋建築**
- 這類項目只有主檔與初始市值。
- 不蓋：畫面比較單純。
- 蓋：與 bucket「用初始市值補」的口徑一致。

**Q9 「月結」是否等於最新月**
- 系統沒有「月結完成」旗標，最新月就是有任何紀錄的最大年月。
- 影響：當月錄到一半時，城市會出現很多空地。
- 問題：是否接受與現行總覽頁同口徑？

**Q10 「圖表」指的是什麼**
- 現行總覽頁沒有圖表，只有指標與摘要。
- proposal 寫「數字卡與圖表移到城市下方」，是否只是指既有內容？若要新增圖表，就超出範圍。

**Q11 完全沒有月結資料時（BR-11）怎麼呈現**
- 選項 (a)：掛元件、畫空地盤。要決定含不含工地；JS 要處理空陣列。
- 選項 (b)：不掛元件，只顯示中性提示。比較簡單，但不符合「空地盤」的字面。

**Q12 Community Cloud 怎麼實測**
- 已知部署事實：main 會自動部署，與正式 Turso 庫共用。
- 選項 (a)：合併後在正式站目視確認，出問題就 revert。
- 選項 (b)：另開一個 Cloud app 指向 feature 分支。會連到同一個正式庫；城市只讀不寫，風險低，但仍然是正式資料。

---

## 5. 風險與建議的驗證順序

1. **Tracer bullet，先做**：最小 payload，用 `rerun_fragment` 掛進總覽頁，加上 AppTest 煙霧測試。在真實瀏覽器確認三件事：
   - 拖滑桿與點擊只觸發 `kind=fragment` 的重跑。
   - 元件的 `mount#` 不變，動畫可以跨重跑延續。
   - `selected` 能回灌。

   **任一項不成立**，就要回頭重新評估 A6 的 fragment 方案，例如滑桿改放 fragment 外、城市每次整頁重跑。
2. **打包**：跑 `uv build`，確認 wheel 內有 `asset_lab/city/city.js` 與 `city.css`。hatchling 預設會帶入套件目錄下的非 Python 檔，但未實測。元件以 `Path(__file__).parent` 讀檔，editable 安裝與 wheel 安裝都要成立。
3. **效能預算**：總覽頁切頁耗時中位數增加不超過 100ms。新增的成本主要是 timeline、frame、第二次 series（TD-6）、首次版位計算。上線前用量測 log 比對前後。
4. **安全**：持有項目名稱是使用者輸入，元件跑在頁面 DOM 權限下（shadow root，不是 iframe）。財務個資也會進入瀏覽器端的元件。**建議 3-2 安全審查要執行。**
5. **Cloud 實測**：依 Q12 的決定。

---

## 6. 給任務拆解的切片建議（僅供參考）

1. Tracer bullet：子套件骨架、最小 payload、fragment 掛載、AppTest 煙霧測試、streamlit 下限、打包檢查（§5 第 1、2 步）。
2. 版位移植：`geometry.py` 與 `layout.py` 重寫，試做 6 項測試轉成回歸測試，拿掉模組級狀態。
3. `CityService.build_timeline`：值矩陣、峰值、購屋排除、空地、月份清單。
4. `CityService.frame_at`：天氣、工地、旗桿、偏離、前一月差額，加上最新月口徑一致性測試。
5. 契約與前端：`CITY_*` 常數、payload、JS 改讀 payload 與 `GEOM`、拿掉 dbg、空地與淡化畫法、轉義靜態測試。
6. 頁面整合：版面順序、小卡、錯誤降級、無資料。
7. 部署與目視：Cloud、量測 log 比對、目視清單。

---

## 附：給 rules-reviewer 的本專案慣例說明

- 入口是 `app.py` 加 `bootstrap.py`，不是 `main.py` 加 argparse。Streamlit 常駐進程沒有 CLI 參數，模組 docstring 已說明。
- views 就是 Controller 層，頁面是唯一的 catch 點；錯誤兜底由 `error_boundary` 與 `rerun_fragment` 統一處理。
- Logging 用 stdlib `logging`，不是 structlog（見 §1.1）。
- 呈現純函式模組（`charts.py`、`overview_presentation.py`、新的 `city/*.py`）是模組級函式，不是 Service 類別，屬於既有先例。業務口徑仍一律放在 Service 類別（A1）。
