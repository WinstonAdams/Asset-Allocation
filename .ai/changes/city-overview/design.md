# 設計文件：city-overview（城市總覽）

> 依據：`proposal.md`（BR-1～BR-15，含使用者對 architecture-brief Q1～Q12 的裁定，以及 2026-11-07 改定的 BR-13「市值留空的月份不畫建築與名稱牌」）、`architecture-brief.md`（1-2b，第 4 節已結案）、`spike-findings.md`（技術試做與 v1～v6 目視結論）。1-2a 已跳過，沒有 `tech-research.md`。
> 本文件只記錄架構決策與介面契約，不描述業務行為情境。**對應的 Scenarios 由 1-3 產出。**
> 沿用的既有偏離：initial-build AD-1（入口是 `app.py`＋`bootstrap.py`，沒有 `main.py`/argparse）、AD-8（標準 `logging`，Page 是領域例外的 catch 點，不用 structlog）；responsiveness-and-error-fallback AD-7（頁面 logger 用明確名稱）、AD-8／AD-9（`error_boundary`、`rerun_fragment`）。Import 區塊標頭沿用本專案的 `# ==== 專案內部 ====`。本 workspace 沒有 `utils_v2`，本 Change 也沒有可套用的 utils_v2 模組（不碰 Google Sheets、HTTP、通知、瀏覽器）。

---

## 現況評估

### 本 Change 要動的地方

| 項目 | 現況 | 位置 |
|------|------|------|
| 總覽頁 | 依序：協定燈號、必做與禁止、3 個 metric、買房摘要 2 個 metric。沒有任何圖表 | `views/overview.py` |
| 買房評估編排 | 「參數 → bucket → 預備金 → 正算月付 → 進度 → 觸發條件」在兩個頁面各寫一份；house-dashboard 設計記載「第三處需要時再抽共用編排」 | `views/house.py:57-115`、`views/overview.py:104-142` |
| DataFrame 轉 `MonthlyRecordModel` | 兩個頁面各有一份 `_to_month_records` | `views/house.py:116`、`views/overview.py:145` |
| 觸發條件中文標籤 | 只在買房頁的私有 dict | `views/house.py:40` `_TRIGGER_LABEL` |
| 協定等級 | 只算最新月；`cumulative_twr_series` 每點都是前綴計算，截斷等於重算 | `services/return_service.py:203-242` |
| Streamlit 下限 | `streamlit[auth]>=1.42`，該版沒有 Components v2；`uv.lock` 鎖 1.66.1 | `pyproject.toml` |
| 試做程式 | 只在本機分支 `spike/city-overview`：版位 659 行（模組級可變 `_NJ`）、payload 156 行、JS 576 行（寫死等級名、天氣名、「應繳」「自備款」、幾何常數兩份、`innerHTML`、dbg 列） | `spikes/city_overview/` |

### 沿用的既有慣例

| 慣例 | 出處 | 本 Change 怎麼用 |
|------|------|------------------|
| Page＝Controller/View：讀 Repository、呼叫 Service、渲染；Service 純運算、不做 I/O | initial-build AD-2 | 城市資料由頁面讀取後傳給新的 `CityService`；`CityService` 不碰 Repository |
| 純運算 Service 由 `bootstrap.build_container` 以 keyword args 組裝並放進 `Container` | 全部 Service | 新增 `city_service` 欄位 |
| 呈現純函式模組（模組級函式＋frozen dataclass，不碰 `st.*`），可獨立單元測試 | `charts.py`、`overview_presentation.py` | `asset_lab/city/` 下的 geometry、layout、presentation、payload 四個純模組 |
| 業務列舉、標籤、文案以巢狀 class 放 `core/constants.py`；呈現模組在函式內直接引用列舉與文案 | 03 §2；behavior-protocol 3-3 判定為既有慣例 | 新增 `CITY_*` 常數；可調的業務參數（最少資料月數、再平衡門檻）走建構子注入 |
| `rerun_fragment` 封裝 `st.fragment`、量測、錯誤兜底、連線驗證；被裝飾函式不帶物件參數 | responsiveness-and-error-fallback AD-9 | 城市區塊用 `@rerun_fragment(label="城市總覽")`，函式內自己取資料 |
| 讀取快取在連線層，同一次執行內重複查詢只往返一次 | 同上 AD-1、AD-12 | 城市區塊與下方數字卡讀同樣的表，整頁重跑時命中快取 |
| 領域例外繼承 `AssetLabError`，訊息可直接顯示給使用者 | `core/exceptions.py` | 新增 `CityLayoutError` |

### 偏離既有做法的地方（各有 ADR）

- **第一個依賴其他 Service 的 Service**（AD-2）：偏離 house-dashboard AD-3「由 Page 編排，不做 Service 間注入」。
- **前端程式碼進正式套件**（AD-7、AD-11）：`asset_lab/city/` 內有 `.js`、`.css`，由 Python 讀入註冊為 Components v2 元件；幾何常數由 Python 序列化後注入 JS。
- **模組級 `functools.lru_cache`**（AD-8）：只用在版位計算，key 是 frozen 輸入、值是 frozen 結果。
- **歷史月份沿用目前設定**（AD-5、AD-6）：買房參數、主觀勾選、目標比重、回撤門檻都沒有歷史，歷史月份一律用目前設定判定。

---

## 架構決策

### AD-1：分三層：`CityService`（領域組裝）＋ `asset_lab/city/` 呈現子套件 ＋ 總覽頁 fragment

- **背景**：城市要把既有服務的結果依月份切片後畫成 Canvas，牽涉三種關注：業務口徑（購屋排除、歷史月份切片、市值留空的月份不畫）、呈現轉換（版位、文案、JSON 契約）、Streamlit runtime（元件註冊、fragment、滑桿、點擊狀態）。`views/*.py` 檔尾無條件呼叫 `render()`，不能 import，放在頁面的邏輯無法單元測試。
- **選擇**：
  1. **領域組裝**：`services/city_service.py` 的 `CityService`，純運算類別，產出 pydantic 結果模型（放 `models/results.py`）。
  2. **呈現轉換**：`src/asset_lab/city/` 子套件，四個純模組加一個 runtime 黏合模組：
     - `geometry.py`：幾何常數（`CityGeometry`）與投影、障礙物、名稱牌、旗桿公式，和 `city.js` 一一對應。
     - `layout.py`：版位規格、`layout_city`、`check`（AD-8）。
     - `presentation.py`：分區與外形對照、金額與天氣顯示文字、小卡內容。
     - `payload.py`：選取 id、版位規格組裝、JSON payload（AD-7）。
     - `component.py`：Components v2 註冊與 wrapper，唯一 import `streamlit` 的城市模組。
     - `city.js`、`city.css`。
     - `__init__.py` 保持空白，不 re-export，避免測試 import 純模組時觸發元件註冊。
  3. **runtime 黏合**：`views/overview.py` 新增 `_render_city()`，以 `rerun_fragment` 包住；既有數字卡留在 fragment 外（AD-9）。
- **理由**：
  - 業務口徑放 Service 類別（02 §5），不放頁面（02 §4 禁止 Controller 做篩選轉換），也不放呈現模組（呈現模組不承載業務口徑，見 architecture-brief 附錄）。
  - 呈現模組比照 `charts.py`、`overview_presentation.py`，可不啟動 Streamlit 直接測。
  - 版位拆 geometry 與 layout 兩檔（A9）：geometry 與 JS 逐段對照審查，layout 只放排版規則。單檔 659 行是 God module；拆成五個以上的檔，演算法內部耦合高、跨檔跳讀反而難懂。
- **否決方案**：
  - **全部寫在 `views/overview.py`**：不可測，總覽頁變成 God view。
  - **城市資料組裝寫成模組級純函式**：購屋排除與歷史 bucket 屬業務口徑，依 02 §5 必須是 Service 類別。
  - **把元件放 `views/` 底下**：頁面檔不能被 import。
- **後果**：
  - 正面：每層都能單獨測試；JS 只剩繪圖。
  - 負面：新增 1 個 Service、7 個檔案；`city/` 子套件同時有純模組與 runtime 模組，靠「`__init__.py` 空白、只有 `component.py` import streamlit」的約定維持，以靜態測試把關（見「驗證方式建議」的靜態掃描列）。

### AD-2：`CityService` 以建構子注入既有純 Service（偏離 house-dashboard AD-3）

- **背景**：城市要對任一歷史月份 m 重算天氣、工地進度、旗桿、偏離。這段編排是現有「買房評估」的第三份（TD-1），而且多了「依月份截斷與過濾」的業務口徑。house-dashboard AD-3 當時否決 Service 間注入，理由是徒增耦合、偏離「Page 編排多個純 Service」；同一份設計也記載「未來若第三處需要再抽共用編排」。
- **選擇**：`CityService` 以 keyword args 注入 `ReturnService`、`ProtocolService`、`AllocationService`、`HouseService`、`AffordabilityService`，以及兩個業務參數 `min_data_months`（`PROTOCOL_MIN_DATA_MONTHS`）與 `rebalance_threshold`（`DEFAULT_REBALANCE_THRESHOLD`）。依賴單向：既有 Service 不知道 `CityService`，彼此之間仍無依賴。
- **理由**：
  - 逐月切片是篩選與轉換，依 02 §2 維度 A 屬 Service；放頁面就無法測，三份編排也沒有任何測試能防止分岔。
  - 放進 Service 後，可以寫「最新月的城市結果與買房頁、總覽頁、資產配置頁逐位相同」的一致性測試，把 TD-1 的分岔風險變成可驗證的事。
  - 重用既有 Service，不新增任何財務計算，符合 ROADMAP「城市只是呈現層」的邊界。
- **否決方案**：
  - **(a) 由頁面編排五個 Service**（延續 AD-3）：逐月切片會散在頁面裡，不可測，正是 AD-3 預留的「第三處」。
  - **(b) 在 `HouseService`、`ProtocolService` 加 `as_of` 參數**：會動到買房頁與總覽頁的既有路徑；`ProtocolService` 其實不需要改（截斷就等於重算）。
  - **(c) 本 Change 一併把買房頁與總覽頁改用 `CityService` 的編排**：改動外溢到兩個與城市無關的頁面與它們的 SC 測試；改以一致性測試守住，搬遷列為後續（技術債 TD-A）。
- **後果**：
  - 正面：口徑集中、可測；既有 Service 一行不改。
  - 負面：`CityService` 有 5 個 Service 依賴，是外觀（facade）類別。public 方法只有兩個（AD-3），內部以私有方法分段，避免長成 God Object。

### AD-3：介面粒度：`build_timeline` 與 `frame_at` 兩個方法；歷史月份以「截斷＋過濾」重用既有 Service

- **背景**：版位與月份滑桿要的是「整段歷史」（月份清單、各項目峰值）；天氣、工地、旗桿、偏離只要「選定月」。一次算完所有月份要做 O(月數 × 紀錄數) 的 bucket 預算，還要失效機制。
- **選擇**：
  - `build_timeline(holdings, records_df)`：只依主檔與紀錄，產出月份清單、進版位的項目（含各月數值）、兩個高度分母。
  - `frame_at(year_month, timeline, holdings, records_df, thresholds, house_params, subjective, targets, current_year)`：只算選定月。做法（A3）：
    1. `records(≤m)`：紀錄截斷到 `year_month ≤ m`。
    2. `holdings(m)`：從主檔排除「第一筆月度紀錄月份晚於 m」的項目。從未錄過紀錄的項目保留（沿用 HouseService「從無紀錄就以初始市值計」，即 BR-10 例外）。
    3. 天氣：`ReturnService.cumulative_twr_series(records(≤m), 全量 holdings)` → `ProtocolService.assess(..., thresholds, min_data_months)`。這裡**不用** `holdings(m)`：整體初始市值取自全量主檔，與總覽頁同口徑；前綴計算的性質保證結果等於全序列截斷到 m。
    4. 工地：`HouseService.bucket_value`、`cash_reserve_value` 吃 `records(≤m)` 與 `holdings(m)`；`AffordabilityService.payment_for_price` 吃目前參數；再 `bucket_progress`、`assess_triggers`。
    5. 偏離：`AllocationService.snapshot`（m 當月紀錄、全量 holdings、`by="category"`）→ `compute_drift(targets, rebalance_threshold)`。
  - 最新月時，過濾不會排除任何項目，截斷也等於沒截，結果與現行頁面逐位相同。
- **理由**：既有 Service 不改；兩個方法各自參數集中；每次 fragment 重跑只算一個月。
- **否決方案**：
  - **一次算完所有月份存進 `session_state`**：要失效機制（錄入後刷新），會和讀取快取的 TTL 交互，收益沒有量測證據。
  - **純截斷不過濾**：晚建立的購屋項目會以初始市值灌進早期月份，高估歷史進度。
  - **改用 `holdings.created_at`**：可為 NULL，語義是建檔時間不是開始持有時間，還要改 Model 與 Repository。
- **後果**：
  - 正面：一致性測試可直接比對最新月；歷史月口徑可用虛構資料逐條測。
  - 負面：「第一筆紀錄月份」是 `CityService` 的推定；`frame_at` 有 9 個 keyword 參數（全是頁面已讀好的資料，沒有隱藏依賴）。

### AD-4：項目的逐月狀態與高度口徑（BR-2、BR-8、BR-9、BR-13、BR-14、BR-15）

- **背景**：proposal 對單一建築在某月的畫法給了多條規則。BR-13 於 2026-11-07 由使用者改定：某月有紀錄但市值留空時，該月不畫此項目的建築，也不畫名稱牌，不論之前有沒有數值都一樣，取代原本的「沿用前值」。這些規則決定 `CityService` 的輸出欄位，必須先定清楚。
- **選擇**：
  - **進版位的項目**（`build_timeline`）：`purpose != house`（BR-8）且至少有一筆月度紀錄（BR-15）。資產與負債都算；負債畫坑洞。購屋標記以當下主檔為準，改標記後下一次重跑即重排（BR-8 邊界）。只有留空列的項目也算「有紀錄」，照樣進版位。
  - **月份清單**：所有紀錄（含負債、購屋項目）出現過的年月，遞增。最後一個就是「最新月結」，與現行總覽頁同口徑。
  - **各月數值**：每個項目記 `month → 市值或 None`。有 key 代表該月有列；值為 None 代表有列但市值留空。
  - **峰值**：該項目全歷史**非空**市值的最大值；留空月份不參與。全部留空時為 0（版位仍保留它的地塊，名稱牌寬度以「0.0 萬」估）。版位用峰值，所以逐月不動（BR-9）。
  - **高度分母**（BR-2）：`max_asset_value`＝進版位的資產項目峰值最大者；`max_liability_value`＝進版位的負債項目峰值最大者。留空月份不參與分母。高度 `H_TOP × √(當月市值 ÷ max_asset_value)`，下限 `H_MIN`，只有 `present` 狀態會畫；分母為 0 時一律畫最低高度。公式在 `geometry.asset_height` 與 JS 各一份（AD-7）。
  - **單月狀態**（`CITY_BUILDING_STATUS`，三選一）：

    | 狀態 | 條件 | 地塊 | 建築／坑洞 | 名稱牌 |
    |------|------|------|------------|--------|
    | `present` | 該月有列且有值 | 保留 | 依當月市值畫 | 正常 |
    | `unfilled` | 該月有列、市值留空（不論之前有沒有數值） | 保留，畫成空地 | 不畫 | **不畫**（BR-13） |
    | `absent` | 該月沒有列（尚未出現或已出清） | 保留，畫成空地 | 不畫 | 淡化（BR-9） |

    `unfilled` 的地塊不出現在圖例、沒有 hover 提示、不能點（見待確認 Q-D）。若使用者在別的月份選了這個項目再切過來，選取仍有效，小卡照常顯示並註明「本月未填」。
  - **與前一月相比**（BR-14）：比較基準＝月份清單上 m 的前一個月份（`previous_month`）；m 是最早月份時為 None，不顯示變化。差額＝m 的市值 − 前一月的市值，只在 m 與前一月**都是 `present`** 時才有值，其餘為 None（見待確認 Q-B）。
  - **不影響其他元素**（BR-13 例外欄）：留空只改城市的建築畫法。天氣（TWR 沿用前值）、工地（bucket 視為 0）、偏離（不貢獻佔比）一律照各既有 Service 的口徑，`CityService` 不另外處理。
- **理由**：
  - BR-13 是使用者的明確裁定。地塊保留，所以版位逐月不動（BR-9）；建築與名稱牌都不畫，就不會出現看起來像真實數值的高度。
  - `unfilled` 和 `absent` 都不畫建築，但名稱牌一個不畫、一個淡化，所以兩種情況在畫面上可以分辨。
  - 分母只看進版位的項目：購屋項目不畫建築（BR-8），若算進分母，最高的建築可能永遠頂不到天花板（見待確認 Q-A）。
- **否決方案**：
  - **沿用最近一個有值月份的高度**（原 BR-13）：使用者於 2026-11-07 改定，不採用。
  - **比照 BR-9 畫空地＋淡化名稱牌**：會和「本月沒有此項目」混在一起，而且使用者要求連名稱牌都不畫。
  - **畫最低高度並註明「未填」**：視覺上與真實的小金額無法區分。
  - **分母用「所有資產總市值」的歷史最高**：單棟高度會全部被壓扁，與試做定案（單一項目的歷史最高值）不符。
- **後果**：`CityBuildingState` 帶 `status`、`value`、`previous_month`、`previous_status`、`delta`，小卡與 payload 都只讀這些欄位，不再自行判斷。JS 只看 payload 的 `vacant` 與 `plate_mode` 兩個畫法旗標（§9），不知道 `unfilled` 和 `absent` 的業務差別。

### AD-5：歷史月份逐條可算性與「依目前設定判定」的註記範圍（BR-10）

- **背景**：proposal 要求設計階段逐條確認哪些條件可逐月計算。系統只存目前的買房參數、主觀勾選、目標比重與回撤門檻，沒有歷史。
- **選擇**：逐條結論如下。歷史月份（m 不是最新月）時，工地小卡整張註明「依目前設定判定」；最新月不加註記。

  | 畫面元素 | 逐月計算的部分 | 用目前設定的部分 |
  |----------|----------------|------------------|
  | 工地進度 | bucket 值（`records(≤m)`、`holdings(m)`） | 目標金額（目標總價 × 自備比率） |
  | 旗桿：定錨 `anchor` | 無 | 主觀勾選 |
  | 旗桿：收入 `income` | 無 | 稅後月收、收入門檻 |
  | 旗桿：自備 `down_payment` | bucket 值、現金預備金 | 目標總價、自備比率、現金地板 |
  | 旗桿：月付 `payment` | 無 | 目標總價、利率、年限、月收、月付上限 |
  | 旗桿：認知 `cognition` | 無 | 主觀勾選 |
  | 天氣 | 累積 TWR 序列與回撤 | 三級回撤門檻 |
  | 偏離三角 | 各類別現況佔比 | 目標比重（BR-7 已要求註明） |

  - 工地小卡不呈現 `years_to_target`、`required_annual_accumulation`：兩者以今天計算，放在歷史月份會誤導。`CitySite` 仍保留完整的 `BucketProgress`，由呈現層決定不顯示。
  - 天氣沒有小卡，歷史月份的天氣用目前門檻判定，不另加註記，列為已知限制（技術債 TD-F）。
- **理由**：五根旗桿中只有「自備」會逐月變，而且連它也依賴目前的目標與地板；整張小卡加一個註記，比逐條判斷該不該加更不容易漏。
- **否決方案**：**逐條加註**：自備條件同時有逐月與目前設定兩種成分，逐條標示反而更難讀。
- **後果**：`CityFrame.is_latest` 是呈現層決定是否加註記的唯一依據。

### AD-6：偏離三角口徑（BR-7、D14 未實作）

- **背景**：BR-7 要求偏離按資產類別計算，三角只標在該類別的建築上；`compute_drift` 仍含購屋用途金額（D14 未實作），城市卻不畫購屋項目。
- **選擇**：
  - 偏離沿用 `snapshot(by="category")` 加 `compute_drift(threshold=rebalance_threshold)`，不改。
  - 三角掛在「該類別、當月狀態為 `present`」的建築上。類別內沒有這種建築（只有購屋項目，或全部是 `absent`、`unfilled`）時不畫（BR-7 例外）。`absent` 的淡化名稱牌不掛三角；`unfilled` 沒有名稱牌，自然也不掛。
  - 小卡註明「含購屋用途金額」：只在該類別當月確實有購屋用途資產、且其市值非空時才註明（見待確認 Q-C）。`CityFrame.house_purpose_categories` 提供這份清單。
  - 歷史月份另註明「依目前設定判定」（目標比重沒有歷史）。
- **理由**：三角標在空地上會讓人以為已出清的項目還在偏離；「含購屋用途金額」只在真的有時才出現，避免每張小卡都掛同一句說明。
- **否決方案**：**本 Change 先實作 D14 排除**：屬 ROADMAP Change 2，proposal 明確不做。
- **後果**：D14 上線後只需改 `compute_drift` 的輸入，城市自動跟著變；屆時「含購屋用途金額」註記與 `house_purpose_categories` 可以一併拿掉（技術債 TD-E）。

### AD-7：Python 是唯一事實來源：JSON 契約、文案常數、幾何常數注入（A4、A8、BR-12）

- **背景**：試做 JS 寫死了協定等級名、天氣名、「資料未滿 3 個月」（等於寫死 `PROTOCOL_MIN_DATA_MONTHS`）、「應繳」「自備款」，旗桿鍵與 `HOUSE_TRIGGER` 不同名，幾何常數 Python 與 JS 各一份並註明「改一邊就要改另一邊」。
- **選擇**：
  1. **JS 不做任何業務判斷、不含任何業務文字**。Python 決定：狀態與空地、偏離三角、天氣代碼與嚴重度、旗桿達成與否、工地進度（已封頂到 0～1）、所有顯示文字（名稱牌第二行、hover 提示、圖例、天氣面板、月份牌、無障礙標籤）。JS 只做投影、動畫、命中測試、依畫布寬度降級名稱牌。
  2. **文案集中在 `core/constants.py`**：天氣規格 `CITY_WEATHER`（等級對天氣代碼、名稱、嚴重度，BR-12）、文案 `CITY_TEXT`、金額單位 `CITY_AMOUNT`、分區與外形 `CITY_ZONE`、`CITY_SHAPE`、狀態 `CITY_BUILDING_STATUS`。等級標籤直接引用既有 `PROTOCOL_LEVELS`；資料不足文案沿用 `overview_presentation.NO_DATA_MESSAGE`、`INSUFFICIENT_DATA_MESSAGE`；觸發條件標籤從買房頁私有 dict 搬到 `HOUSE_TRIGGER.LABEL`，買房頁改用它（同一份來源）。
  3. **旗桿**：鍵名就是 `HOUSE_TRIGGER` 的值，順序依 `HOUSE_TRIGGER.ALL`。
  4. **幾何常數只有一份**：定義在 `city/geometry.py` 的 frozen dataclass `CityGeometry`。`component.py` 註冊時把它序列化成一行 `const GEOM = {...}`，加在 `city.js` 內容最前面；JS 只讀 `GEOM.*`。坑洞深度常數（試做只在 JS）也搬進 `CityGeometry`。
  5. **JSON 契約**寫在介面契約 §9，`payload.build_payload` 是唯一產生者。
- **理由**：協定等級標籤與天氣名稱只有一份；常數不可能不同步；payload 不會因為每次重送不變的常數而變大。
- **否決方案**：
  - **維持兩份常數，測試以 regex 解析 JS 比對**：脆弱，而且只能比常數。
  - **常數每次放進 payload**：每次重跑重送不變的資料，設定和資料混在一起。可當次選。
  - **Python 算好螢幕座標再送給 JS**：縮放取決於瀏覽器的畫布寬度，Python 不知道。
  - **JS 保留 `LEVELS` 查表**：等級標籤兩份，違反 BR-12。
- **後果**：
  - 正面：改文案、改等級名只改 Python；靜態測試可斷言 `city.js` 沒有中日韓文字（註解除外）。
  - 負面：單獨打開 JS 看不到常數值；投影、障礙物、名稱牌、旗桿的**公式**仍兩邊各一份，靠 Python `check()` 測試加人工目視兜底（技術債 TD-C）。

### AD-8：版位模組重寫：無模組級可變狀態、結果 frozen、只快取版位（A5、A9、BR-1、BR-5）

- **背景**：試做 `city_layout.py` 用模組級 dict `_NJ` 記同列間距，`layout_city` 開頭結尾各 `clear()` 一次，多個 session 同時排版會互相清掉；`CityLayout` 是可變 dataclass。版位計算 30 棟約 25～28ms，每拖一次滑桿都重算並不必要。
- **選擇**：
  - **重寫，不搬**：演算法照試做（兩條間距規則、12 組候選參數、固定點迭代到收斂、`check()` 驗證器），命名、docstring、型別依 01 編碼風格；拿掉 `from __future__`、`# fmt: skip`。試做的 6 項測試移植為回歸基準（不重疊、同區同街廓、多種寬度都在畫布內、確定性、30 棟 50ms 內、跨月版位不變）。
  - **同列間距的 memo 改為單次呼叫的區域變數**：由 `layout_city` 建立，傳給內部函式，呼叫結束即丟。
  - **結果 frozen**：`CityLayout`、`CitySpec`、`PlateSize` 都是 frozen dataclass，集合欄位用 tuple。
  - **快取**：`layout_city` 以 `functools.lru_cache(maxsize=8)` 包裝，key 是 `(specs, max_asset)`，都是 hashable 的 frozen 值；內容本身就是 key，不需要失效。
  - **名稱牌尺寸的文字來源**：版位不碰業務文字。`CitySpec.sub_reference` 是「名稱牌第二行可能出現的最寬文字」，由 `payload.build_specs` 以峰值呼叫 `presentation.plate_sub` 產生；工地的參考金額是 `CityGeometry.site_reference_amount`。名稱牌第二行只在 `present` 月份出現，而當月市值不超過峰值，所以實際文字不會比參考更寬。
  - **無法收斂**時拋 `CityLayoutError`（AD-10）。
- **理由**：
  - 多 session 安全；`lru_cache` 本身執行緒安全，最壞情況是同一組輸入同時算兩次。
  - 版位快取的成本與收益都已實測，key 單純，不算過早最佳化。跨 session 共用在單一使用者的 app 可以接受。
  - timeline、frame、series 先不快取（A5），等量測證明超出預算再處理（AD-12 步驟 3）。
- **否決方案**：
  - **保留模組級 `_NJ` 並加鎖**：鎖住整個版位計算會讓多分頁互等，而且鎖是不必要的共享狀態。
  - **`st.cache_data`**：會讓純模組依賴 streamlit，每次命中還要 pickle。
  - **把 timeline、frame 也快取**：沒有量測證據，還要處理錄入後的失效。
- **後果**：
  - 正面：版位在月份之間只算一次；測試清掉快取（`layout_city.cache_clear()`）即可量冷啟動耗時。
  - 負面：快取是程序級；版位只量到 30 棟，超過沒有實測（技術債 TD-G）。

### AD-9：Fragment 範圍、版面順序、滑桿與點擊狀態（A6、目標「放置位置」「時間範圍」「點擊」）

- **背景**：proposal 要求城市在最上方，月份滑桿與小卡在城市下方；數字卡固定顯示最新月結、放在城市區塊外，拖滑桿不重跑。fragment 內的 widget 不能寫進 fragment 外建立的容器。
- **選擇**：
  - `render()` 順序：`st.title` → `_render_city()`（fragment）→ 既有內容（協定燈號、必做禁止、指標、買房摘要），既有內容的邏輯不改。
  - `_render_city()` 以 `@rerun_fragment(label="城市總覽")` 包住，不帶參數，函式內自己讀資料。
  - fragment 內的順序：讀資料 → `build_timeline` →（沒有任何月份就顯示中性提示並 return，AD-10）→ `slot = st.container()` 先佔位 → 月份滑桿 → `frame_at` → 版位與 payload → `with slot:` 掛元件 → 小卡。
  - **月份滑桿**：`st.select_slider`，選項為 `timeline.months`，預設最新月，key 固定。session 裡的值不在選項內時（資料被刪），先移除該 key 再建立 widget。只有一個月份時不渲染滑桿，直接用該月（`select_slider` 單一選項的行為由 tracer bullet 確認）。
  - **點擊狀態**：JS 只用 `setStateValue("selected", id)`（持久，存在 `session_state[key]`），不送 `setTriggerValue`、不註冊 `on_picked_change`（本 Change 不跳頁、不開錄入，YAGNI）。Python 掛元件前從 session 讀出上一次的選取，經 `payload.resolve_selection` 驗證後放回 payload（試做 Q3 驗證過的控制迴圈）；選取失效（項目已不在版位）時靜默清除。小卡以驗證後的選取為準。
  - **換頁再回來**：Streamlit 會清掉沒渲染的 widget state，滑桿回到最新月、選取清空，符合「預設顯示最新月結」。
- **理由**：拖滑桿、點建築只重跑 fragment，符合成功標準 5；fragment 自帶錯誤兜底；量測 log 以 `kind=fragment page=城市總覽` 區分。
- **否決方案**：
  - **不用 fragment**：每拖一次滑桿連登入守門與連線驗證整頁重跑，違反成功標準 5。
  - **數字卡也放進 fragment**：違反「數字卡固定最新月結、拖滑桿不重跑」。
  - **滑桿放 fragment 外**：滑桿變動就整頁重跑。
- **後果**：
  - 正面：版面順序與重跑範圍都符合 proposal。
  - 負面：整頁重跑時城市與數字卡各讀一次資料（命中讀取快取）、各算一次累積 TWR 序列（技術債 TD-D）；Components v2 在 fragment 內的行為尚未實測（AD-12）。

### AD-10：錯誤隔離與降級（BR-11）

- **背景**：城市區塊壞掉時，下方數字卡（也是文字替代）必須照常顯示；完全沒有資料或資料不足時不能報錯。
- **選擇**：
  - **錯誤隔離**：`rerun_fragment` 內含 `error_boundary`，城市區塊的例外只影響城市本身；數字卡在 fragment 外，維持原本的 `try/except AssetLabError`。
  - **沒有任何月度紀錄**（`timeline.months` 為空）：不掛元件、不渲染滑桿，只顯示 `st.info(NO_DATA_MESSAGE)`。這個判斷在讀 `holdings` 與 `read_all` 之後、其他讀取之前。
  - **協定資料不足**（`ProtocolStatus.status` 不是 `ok`）：天氣用中性規格 `CITY_WEATHER.NEUTRAL`（視覺代碼 `calm`：只有天空漸層，沒有太陽、雲、雨；面板嚴重度 `neutral`），副標用 `INSUFFICIENT_DATA_MESSAGE`；無紀錄（`no_data`）時副標用 `NO_DATA_MESSAGE`。
  - **版位無法收斂**：新增 `CityLayoutError(AssetLabError)`，訊息為中性文案（`CITY_TEXT.LAYOUT_FAILED`），由 `error_boundary` 以領域錯誤顯示並記 log。
  - payload 驗證失敗（地塊重疊、出界）與 `frame_at` 收到不在月份清單的月份，屬程式錯誤，拋 `ValueError`，落入「未預期錯誤」。
- **理由**：版位無法收斂是可預期的極端輸入（項目數遠超實測範圍），應給使用者看得懂的訊息；其他違反不變式的情況是 bug，應照未預期錯誤處理並露出 log。
- **否決方案**：**BR-11 改畫空地盤**：使用者已裁定（Q11）不掛元件。
- **後果**：城市區塊與數字卡在無資料時各自顯示中性訊息，畫面上會有兩段相近的提示，可以接受。

### AD-11：安全邊界（BR-4、BR-6）

- **背景**：持有項目名稱是使用者輸入；元件跑在頁面 DOM 權限下（shadow root，不是 iframe）；財務數字會進入瀏覽器端的元件。試做的 tooltip 與圖例用 `innerHTML` 搭配 `esc()`。
- **選擇**：
  - **`city.js` 完全不用 `innerHTML`、`outerHTML`、`insertAdjacentHTML`**：tooltip、圖例、天氣面板、月份牌一律以 `createElement`＋`textContent` 建構。canvas 的 `fillText` 不經 HTML 解析，不需要轉義。以 pytest 靜態掃描把關。
  - **BR-6**：`city/*.py` 不 import `bootstrap`、`repositories`，不引用 `st.user`、`st.login`、`st.secrets`；資料全部由頁面組好再傳入。以 pytest 靜態掃描把關。
  - payload 只放畫面需要的值：名稱、金額顯示文字、高度依據值、狀態旗標；不放 `holding_id` 以外的主檔欄位（初始成本、用途等）。
  - 字型只用 `--st-font`，不載入任何外部 CDN。
  - **3-2 安全審查要執行**（使用者輸入進 DOM、財務個資進瀏覽器端元件）。
- **理由**：完全禁用比「用了就要搭配 `esc()`」更容易靜態驗證，也不依賴每一處都記得轉義。
- **否決方案**：**保留 `innerHTML`＋`esc()`**：靜態測試只能檢查同一行有沒有 `esc(`，擋不住拼接錯誤。
- **後果**：JS 建構 DOM 的程式碼比字串拼接長幾行。

### AD-12：交付順序：tracer bullet 先行，以及失敗時的退路

- **背景**：最大的未驗證風險是 Components v2 元件放在 `st.fragment` 內時，互動會重跑多大範圍、元件會不會重新掛載；其次是打包與 Community Cloud。
- **選擇**：第一個 Task 做 tracer bullet：子套件骨架、最小 payload、`rerun_fragment` 掛進總覽頁、AppTest 煙霧測試、`streamlit` 下限、打包檢查。在真實瀏覽器確認三件事：
  1. 拖滑桿與點擊只產生 `kind=fragment page=城市總覽` 的量測 log。
  2. 元件不重新掛載（host 元素的 `data-mount` 不變），動畫跨重跑延續。
  3. `selected` 能回灌。
  另跑 `uv build`，確認 wheel 內有 `asset_lab/city/city.js` 與 `city.css`。

  **失敗時的退路**（不得自行改方案，結果回報主 AI）：

  | 不成立的項目 | 退路 |
  |--------------|------|
  | 點擊觸發整頁重跑，但滑桿只重跑 fragment | 可接受（成功標準 5 只約束滑桿），記錄即可 |
  | 拖滑桿觸發整頁重跑 | 違反成功標準 5，回報使用者決定 |
  | fragment 重跑時元件重新掛載 | 動畫中斷、選取可能丟失；回報使用者決定是否接受或改為整頁重跑 |
  | `selected` 無法回灌 | 改用 `setTriggerValue` 加 `on_picked_change` 回呼寫入 session，由 Python 持有選取 |
  | wheel 缺 `.js`/`.css` | 在 `pyproject.toml` 補 hatch 的 include 設定 |

  後續順序：版位重寫 → `build_timeline` → `frame_at`（含最新月一致性測試）→ 常數、payload 與 JS 改寫 → 頁面整合 → 量測與部署。
- **理由**：先用最小成本驗證最大風險，任一項不成立時還沒投入版位與資料組裝的工。
- **否決方案**：**先做完全部再整合**：tracer bullet 失敗時要大改的面積最大。
- **後果**：第一個 Task 的產出有一部分是「驗證結果」，需要人工在瀏覽器確認，不能只靠 pytest。

---

## 技術選型

### TD-1：Streamlit Components v2 inline 元件（`st.components.v2.component`）

- **推薦**：以 `component(name, html=, css=, js=)` 在模組載入時註冊一次，掛載時 `width="stretch"`、`height="content"`，JS 以 `setStateValue` 回傳選取（信心度：High）。
- **理由**：試做在 1.66.1 驗證過掛載、Python 到 JS 原地更新、JS 到 Python、寬度、主題、AppTest 可見性（`UnknownElement`／`bidi_component`）。shadow root 讀得到 `--st-*`，不必自訂 `[theme]`。

### TD-2：純 Canvas 2D 自繪，不引入 PixiJS 或外部美術素材

- **推薦**：沿用試做的 Canvas 2D 繪圖（信心度：High）。
- **理由**：proposal 明確排除；試做已達到使用者目視定案的畫面。美術升級另開 Change，只換畫法，JSON 契約不變。

### TD-3：`streamlit[auth]>=1.66`，精確版本交給 `uv.lock`

- **推薦**：下限調到試做實測的 1.66（信心度：High）。
- **理由**：1.42 沒有 Components v2，`pyproject.toml` 會與實際依賴矛盾。本專案只部署一處，往下相容沒有受益者，不必追查最早支援的版本；精確釘死 `==1.66.1` 會擋掉安全更新。Community Cloud 實測照使用者裁定（Q12）：合併前備份 CSV，合併後在正式站目視，有問題就 revert。

### TD-4：不新增任何第三方依賴；標準庫 `logging`；沒有 utils_v2

- **推薦**：版位、payload、快取都用標準庫（`functools.lru_cache`、`dataclasses`、`json`、`math`）（信心度：High）。
- **理由**：沿用 initial-build AD-8。本 workspace 沒有 `utils_v2`；`CityService` 是純運算，不打 log；錯誤 log 由 `error_boundary` 統一處理。

---

## 介面契約

> 以下為 public 介面與資料契約；私有 helper 由實作決定。所有建構子與方法一律 keyword-only。

### 1. 常數（`core/constants.py`，新增與調整）

```python
class HOUSE_TRIGGER:
    ...                                   # 既有內容不變
    LABEL = {                             # 新增：由 views/house.py 的 _TRIGGER_LABEL 搬入，買房頁改用此處
        ANCHOR: "定錨", INCOME: "收入", DOWN_PAYMENT: "自備", PAYMENT: "月付", COGNITION: "認知",
    }


class CITY_ZONE:
    """城市分區鍵（亦為 city.css 色票鍵）。台股與美股同屬股票分區（BR-1）。"""

    CASH = "cash"
    DEPOSIT = "deposit"
    STOCK = "stock"
    INSURANCE = "ins"
    DEBT = "debt"
    SITE = "house"                        # 購屋工地
    BY_CATEGORY = {
        ASSET_CATEGORIES.DEMAND_DEPOSIT: CASH,
        ASSET_CATEGORIES.TIME_DEPOSIT: DEPOSIT,
        ASSET_CATEGORIES.TW_STOCK: STOCK,
        ASSET_CATEGORIES.US_STOCK: STOCK,
        ASSET_CATEGORIES.INSURANCE: INSURANCE,
    }
    LIABILITY = DEBT
    ZONE_LABEL = {CASH: "現金", DEPOSIT: "存款", STOCK: "股票", INSURANCE: "保險", DEBT: "負債"}


class CITY_SHAPE:
    """建築外形鍵（city.js 依此選繪圖函式）。"""

    TANK = "tank"
    SILO = "silo"
    TOWER = "tower"
    STATION = "station"
    PIT = "pit"
    BY_ZONE = {
        CITY_ZONE.CASH: TANK, CITY_ZONE.DEPOSIT: SILO, CITY_ZONE.STOCK: TOWER,
        CITY_ZONE.INSURANCE: STATION, CITY_ZONE.DEBT: PIT,
    }


class CITY_BUILDING_STATUS:
    """項目在選定月份的狀態（見 design AD-4）。"""

    PRESENT = "present"
    UNFILLED = "unfilled"    # 有列但市值留空：不畫建築、不畫名稱牌（BR-13）
    ABSENT = "absent"        # 沒有列：空地＋淡化名稱牌（BR-9）
    VACANT = frozenset({UNFILLED, ABSENT})


@dataclass(frozen=True)
class CityWeatherSpec:
    """一種天氣的顯示規格：視覺代碼給 city.js 選畫法，名稱與嚴重度給天氣面板。"""

    sky: str          # clear / cloudy / rain / typhoon / calm
    name: str
    severity: str     # good / warn / bad / neutral


class CITY_WEATHER:
    """天氣＝大跌協定等級（BR-12）。等級標籤另取 PROTOCOL_LEVELS，不在此重抄。"""

    BY_LEVEL = {
        PROTOCOL_LEVEL_CODE.L0: CityWeatherSpec(sky="clear", name="晴", severity="good"),
        PROTOCOL_LEVEL_CODE.L1: CityWeatherSpec(sky="cloudy", name="多雲", severity="warn"),
        PROTOCOL_LEVEL_CODE.L2: CityWeatherSpec(sky="rain", name="暴雨", severity="bad"),
        PROTOCOL_LEVEL_CODE.L3: CityWeatherSpec(sky="typhoon", name="颱風", severity="bad"),
    }
    NEUTRAL = CityWeatherSpec(sky="calm", name="天氣未定", severity="neutral")   # 文案見待確認 Q-E


class CITY_AMOUNT:
    """名稱牌與提示的金額單位（萬，一位小數）。"""

    DIVISOR = 10_000
    UNIT = "萬"


class CITY_TEXT:
    """城市總覽的固定文案；含 {month}、{pct} 等佔位符者以 str.format 帶入。"""

    SITE_NAME = "購屋工地"
    LIABILITY_PREFIX = "應繳"
    SITE_AMOUNT_PREFIX = "自備款"
    MONTH_SLIDER_LABEL = "月份"
    ARIA_LABEL = "等角城市：資產狀態與購屋進度"
    CARD_HINT = "點建築或工地，查看該項目的細節"
    DRAWDOWN = "自高點回撤 {pct}"
    COMPARE_WITH = "較 {month}"
    PREVIOUS_ABSENT = "較 {month}：當時沒有此項目"
    PREVIOUS_UNFILLED = "較 {month}：當時未填"
    UNFILLED = "本月未填"
    ABSENT = "本月沒有此項目"
    BY_CURRENT_SETTINGS = "依目前設定判定"
    INCLUDES_HOUSE_PURPOSE = "含購屋用途金額"
    TARGET_UNSET = "目標未設定"
    MET = "達成"
    NOT_MET = "未達成"
    LAYOUT_FAILED = "城市版位暫時無法排出，請參考下方數字"
    # 小卡列標籤（類別、該月市值、與前一月相比、自備款、目標、進度、偏離）由實作補齊，不得散落在函式內
```

- 單元測試須斷言：`CITY_ZONE.BY_CATEGORY` 涵蓋 `ASSET_CATEGORIES.ALL`；`CITY_WEATHER.BY_LEVEL` 涵蓋 `PROTOCOL_LEVEL_CODE.ALL`；`HOUSE_TRIGGER.LABEL` 涵蓋 `HOUSE_TRIGGER.ALL`。
- 文字措辭（`NEUTRAL.name`、`CARD_HINT`、`LAYOUT_FAILED` 等）可在目視驗收時調整，只改常數。

### 2. 例外（`core/exceptions.py`，新增）

```python
class CityLayoutError(AssetLabError):
    """城市版位在迭代上限內無法收斂時拋出；訊息為可直接顯示的中性文案。"""
```

### 3. 共用轉換（`core/utils.py`，新增）

```python
def records_frame_to_models(records_df: pd.DataFrame) -> list[MonthlyRecordModel]:
    """把月度紀錄 DataFrame 轉為模型清單（holding_id、year_month、market_value、
    net_investment 四欄；NaN 市值轉 None）。與 views/house.py、views/overview.py 的
    _to_month_records 同口徑；兩頁的私有版本本 Change 不搬（技術債 TD-B）。"""
```

### 4. 結果模型（`models/results.py`，新增；pydantic，純資料）

```python
class CityHolding(BaseModel):
    """進版位的項目（非購屋用途、至少一筆月度紀錄）；月份之間不變的規格加各月數值。"""

    holding_id: int
    name: str
    kind: str                              # HOLDING_KIND.ASSET / LIABILITY
    category: str | None = None            # 負債為 None
    peak_value: float                      # 全歷史非空市值最大值；全部留空為 0
    month_values: dict[str, float | None]  # 有 key＝該月有列；值 None＝有列但市值留空


class CityTimeline(BaseModel):
    """整段歷史：月份清單、進版位的項目與高度分母。"""

    months: list[str]                      # 有任何月度紀錄的年月，遞增；空清單＝無資料
    latest_month: str | None = None
    holdings: list[CityHolding]            # 依 holding_id 遞增
    max_asset_value: float                 # 進版位資產的 peak_value 最大值（無則 0）
    max_liability_value: float             # 進版位負債的 peak_value 最大值（無則 0）


class CityBuildingState(BaseModel):
    """單一項目在選定月份的狀態（AD-4）。"""

    holding_id: int
    status: str                            # CITY_BUILDING_STATUS：present / unfilled / absent
    value: float | None = None             # 當月市值；只有 present 有值，也是高度依據
    previous_month: str | None = None      # 月份清單上的前一個月份；最早月為 None
    previous_status: str | None = None     # 前一個月份的狀態（小卡決定差額旁的說明）；最早月為 None
    delta: float | None = None             # 本月與前一月都是 present 才有值（AD-4）
    drift: DriftRow | None = None          # 該類別需再平衡且本建築為 present 時帶入（AD-6）


class CitySite(BaseModel):
    """選定月份的購屋工地：bucket 進度與五條觸發條件（AD-5）。"""

    progress: BucketProgress               # years_to_target 等以今天計算，呈現層不顯示
    checklist: TriggerChecklist            # conditions 依 HOUSE_TRIGGER.ALL 順序


class CityFrame(BaseModel):
    """選定月份的城市畫面資料。"""

    year_month: str
    is_latest: bool
    weather: ProtocolStatus
    site: CitySite
    buildings: list[CityBuildingState]     # 與 timeline.holdings 同順序、一對一
    drift_rows: list[DriftRow]             # compute_drift 全部結果（含未超標者）
    house_purpose_categories: list[str]    # 當月有非空市值購屋用途資產的類別（AD-6）
```

### 5. Service（`services/city_service.py`，新增）

```python
class CityService:
    """城市總覽的資料組裝（純運算）：依月份切片後重用既有 Service，不新增財務計算。"""

    def __init__(
        self,
        *,
        return_service: ReturnService,
        protocol_service: ProtocolService,
        allocation_service: AllocationService,
        house_service: HouseService,
        affordability_service: AffordabilityService,
        min_data_months: int,
        rebalance_threshold: float,
    ) -> None: ...

    def build_timeline(
        self, *, holdings: list[HoldingModel], records_df: pd.DataFrame
    ) -> CityTimeline:
        """產出月份清單、進版位的項目（BR-8、BR-15）、各月數值與兩個高度分母（BR-2）。"""

    def frame_at(
        self,
        *,
        year_month: str,
        timeline: CityTimeline,
        holdings: list[HoldingModel],
        records_df: pd.DataFrame,
        thresholds: ProtocolThresholds,
        house_params: HouseParams,
        subjective: list[SubjectiveTriggerModel],
        targets: list[TargetAllocationModel],
        current_year: int,
    ) -> CityFrame:
        """以截斷＋過濾（AD-3）算選定月份的天氣、工地、建築狀態與偏離。

        Raises:
            ValueError: year_month 不在 timeline.months。
        """
```

- `holdings`、`records_df` 是全量（含購屋用途項目、負債）；`thresholds`、`house_params` 由頁面先經 `effective_thresholds`、`effective_params` 合併預設。
- **一致性不變式**（必須有測試）：`year_month == timeline.latest_month` 時，`weather` 等於總覽頁的 `assess` 結果；`site.progress.progress_pct` 與 `site.checklist.met_count` 等於 `views/house.py` 同輸入的結果；`drift_rows` 等於資產配置頁對最新月的 `compute_drift` 結果。

### 6. 幾何（`city/geometry.py`，新增，純模組）

```python
Point = tuple[float, float]
Rect = tuple[float, float, float, float]   # x0, y0, x1, y1
Lot = tuple[int, int, int, int]            # i, j, 寬, 深


@dataclass(frozen=True)
class CityGeometry:
    """與 city.js 共用的幾何常數；唯一來源，序列化後以 GEOM 前置注入 JS（AD-7）。
    欄位涵蓋試做 city_layout.py 頂部全部常數，另加坑洞深度（pit_min_depth、pit_max_depth）
    與工地名稱牌參考金額（site_reference_amount）。"""


GEOMETRY = CityGeometry()


def geometry_json() -> str:
    """GEOMETRY 的 JSON 字串（給 component 產生 `const GEOM = ...;` 前置行）。"""

def project(*, i: float, j: float, scale: float) -> Point: ...
def asset_height(*, value: float, max_asset: float) -> float:
    """H_TOP × √(value ÷ max_asset)，下限 H_MIN；max_asset ≤ 0 時回 H_MIN（BR-2）。"""
def text_width(*, text: str, px: float) -> float: ...           # 依字元類別保守估算
def wrap_name(*, name: str) -> tuple[str, ...]: ...             # 最多兩行
def plate_size(*, lines: tuple[str, ...], sub: str | None) -> tuple[int, int]: ...
def flag_rect(*, lot: Lot, scale: float) -> Rect: ...
def plate_rect(*, kind: str, lot: Lot, width: float, height: float, scale: float) -> Rect: ...
def obstacles(*, kind: str, lot: Lot, height: float, roof: float, scale: float) -> list[tuple[str, list[Point]]]: ...
def fit_scale(*, ground_i: int, ground_j: int, canvas_w: float) -> float: ...
```

- 每個公式函式的 docstring 註明對應的 `city.js` 函式名，方便並排審查。

### 7. 版位（`city/layout.py`，新增，純模組）

```python
@dataclass(frozen=True)
class CitySpec:
    """一個版位物件：建築、坑洞或工地。"""

    id: str                     # payload.building_id(...) 或 payload.SITE_ID
    name: str
    zone: str                   # CITY_ZONE
    kind: str                   # "asset" / "liability" / "site"
    shape: str                  # CITY_SHAPE；工地為空字串
    peak: float                 # 版位高度依據；工地不用
    sub_reference: str | None   # 名稱牌第二行的最寬參考文字（AD-8）


@dataclass(frozen=True)
class PlateSize:
    width: int
    height: int
    lines: tuple[str, ...]      # 名稱各行（第二行市值不在此，由 payload 每月提供）


@dataclass(frozen=True)
class CityLayout:
    scale: float                                       # 設計寬度下的縮放
    ground_i: int
    ground_j: int
    top_pad: float
    lots: tuple[tuple[str, Lot], ...]                  # 依 spec 順序
    plates: tuple[tuple[str, PlateSize], ...]
    roads: tuple[tuple[int, int, int, int, str], ...]
    blocks: tuple[tuple[str, int, int, int, int], ...]
    compact: bool                                      # 物件數超過 COMPACT_N：名稱牌只放名稱


@functools.lru_cache(maxsize=8)
def layout_city(*, specs: tuple[CitySpec, ...], max_asset: float) -> CityLayout:
    """確定性排版（BR-1、BR-5）；specs 恰含一個 kind="site"。

    Raises:
        CityLayoutError: 迭代上限內無法收斂。
        ValueError: specs 沒有或有多個工地、id 重複。
    """

def check(
    *, layout: CityLayout, specs: tuple[CitySpec, ...], max_asset: float,
    canvas_w: float = GEOMETRY.design_width,
) -> list[tuple[str, str]]:
    """列出所有衝突（名稱牌碰到建築／工地／吊車／坑洞／旗桿、名稱牌互疊、出地盤、
    旗桿碰到建築、出畫布）；空清單＝合格。供測試使用。"""
```

### 8. 呈現（`city/presentation.py`，新增，純模組）

```python
@dataclass(frozen=True)
class CityWeatherDisplay:
    sky: str
    severity: str
    title: str          # 例：「暴雨・L2 熊市」；中性時為 CITY_WEATHER.NEUTRAL.name
    subtitle: str       # 回撤或資料不足文案


@dataclass(frozen=True)
class CityCard:
    title: str
    rows: tuple[tuple[str, str], ...]   # (標籤, 值)
    notes: tuple[str, ...]              # 註記（本月未填、本月沒有此項目、依目前設定判定、含購屋用途金額…）


def zone_for(*, kind: str, category: str | None) -> str: ...
def shape_for(*, zone: str) -> str: ...
def amount_text(*, value: float) -> str: ...                     # 「1,234.5 萬」
def plate_sub(*, kind: str, value: float) -> str: ...            # 負債加「應繳」前綴
def site_sub(*, bucket_value: float) -> str: ...
def weather_display(*, status: ProtocolStatus) -> CityWeatherDisplay: ...
def building_tip(*, holding: CityHolding, state: CityBuildingState) -> tuple[str, ...]: ...
def site_tip(*, site: CitySite) -> tuple[str, ...]: ...
def building_card(*, holding: CityHolding, state: CityBuildingState, frame: CityFrame) -> CityCard: ...
def site_card(*, site: CitySite, is_latest: bool) -> CityCard: ...
```

- 小卡內容口徑：建築小卡有名稱、類別（負債顯示分區標籤「負債」）、該月市值、與前一月相比；`unfilled` 時不顯示市值與差額，註明「本月未填」；`absent` 時註明「本月沒有此項目」。`building_tip` 對 `unfilled` 回空 tuple。工地小卡有自備款、目標、進度、五條條件的達成狀態，不含 `years_to_target`、`required_annual_accumulation`。註記規則依 AD-4、AD-5、AD-6。精確文案與顯示格式由 1-3 Scenario 定義。

### 9. Payload 與 JSON 契約（`city/payload.py`，新增，純模組）

```python
SITE_ID = "site"

def building_id(*, holding_id: int) -> str: ...                  # "holding-<id>"
def resolve_selection(*, selected: object, timeline: CityTimeline) -> str | None:
    """session 裡的選取值若是現存建築或工地的 id 就原樣回傳，否則 None（靜默清除）。"""
def build_specs(*, timeline: CityTimeline) -> tuple[CitySpec, ...]:
    """把進版位的項目與工地轉為版位規格（分區、外形、名稱牌參考文字）。"""
def build_payload(
    *, layout: CityLayout, timeline: CityTimeline, frame: CityFrame, selected: str | None
) -> dict[str, object]:
    """組成 JSON 可序列化的 payload；驗證地塊不出地盤、不重疊（失敗拋 ValueError）。"""
```

**JSON 契約**（Python → `city.js`，`build_payload` 是唯一產生者）：

```text
{
  "month": "2026-09",                         月份牌文字
  "aria_label": str,                          canvas 的無障礙標籤
  "ground": [ground_i, ground_j],
  "top_pad": float,
  "compact": bool,
  "roads":  [[i0, i1, j0, j1, kind], ...],
  "blocks": [[zone, i0, i1, j0, j1], ...],
  "max_asset": float,                         建築高度分母；0 時一律最低高度
  "max_liab": float,                          坑洞深度分母；0 時一律最淺
  "weather": {"sky": str, "severity": str, "title": str, "subtitle": str},
  "buildings": [
    {
      "id": "holding-12", "name": str, "zone": str, "kind": "asset" | "liability", "shape": str,
      "lot": [i, j, w, d],
      "plate": {"w": int, "h": int, "lines": [str, ...]},
      "value": float,                         高度或深度依據（present 的當月市值；其餘為 0）
      "vacant": bool,                         true＝不畫建築或坑洞，地塊畫成空地（absent、unfilled）
      "plate_mode": "normal" | "faded" | "hidden",
                                              normal＝present；faded＝absent（BR-9）；
                                              hidden＝unfilled（BR-13）：不畫名稱牌、不進圖例、
                                              無 hover 提示、不可點
      "sub": str,                             名稱牌第二行；非 present 為空字串
      "tip": [str, ...],                      hover 提示各行；plate_mode 為 hidden 時為空陣列
      "warn": bool                            名稱牌偏離三角（AD-6）；非 present 一律 false
    }
  ],
  "site": {
    "id": "site", "name": str, "lot": [i, j, w, d],
    "plate": {"w": int, "h": int, "lines": [str, ...]},
    "progress": float,                        0～1，已封頂；目標未設定時 0
    "sub": str, "tip": [str, ...],
    "flags": [{"key": str, "met": bool}, ...] 恰 5 筆，依 HOUSE_TRIGGER.ALL 順序
  },
  "selected": str | null
}
```

- 試做 payload 的 `level`、`drawdown`、`insufficient`、`warn_zones`、`purpose` 一律移除。

### 10. 元件（`city/component.py`，新增，Streamlit runtime 黏合）

```python
def render_city(*, payload: dict[str, object], key: str) -> None:
    """掛載城市元件（width="stretch"、height="content"）；只註冊 on_selected_change（no-op）。"""

def selected_in_session(*, key: str) -> object:
    """讀 session_state[key] 裡元件上一次回報的 selected；尚無時 None。原樣回傳，由
    payload.resolve_selection 驗證。"""
```

- 模組載入時註冊一次：`st.components.v2.component(name="asset_lab_city", html=..., css=city.css 內容, js="const GEOM = " + geometry_json() + ";\n" + city.js 內容)`；檔案以 `Path(__file__).parent` 讀取，editable 與 wheel 安裝都要成立。
- html 不含試做的 `.dbg` 列；canvas 的 `aria-label` 由 JS 從 payload 設定。

### 11. `city.js` 與 `city.css` 的行為契約

- 只讀 payload（§9）與 `GEOM`；不定義與 `GEOM` 重複的常數（`TW`、`TH`、`HMAX`、`UX`、`VY`、`LAB`、`FR`、`FLAG_*`、`EPS`）。
- 程式碼（註解除外）不含任何中日韓文字。
- 不使用 `innerHTML`、`outerHTML`、`insertAdjacentHTML`；文字一律 `textContent` 或 canvas `fillText`。
- 點擊只呼叫 `setStateValue("selected", id)`，本機先高亮；不呼叫 `setTriggerValue`。`plate_mode` 為 `faded` 的空地可點（命中區為地塊範圍）；`hidden` 的地塊不可點、沒有 hover 提示。
- 實例以 `WeakMap` 依 `parentElement` 保存，重跑時原地更新；回傳 cleanup 函式。可在 host 元素寫 `data-mount`、`data-runs` 供人工驗證，不在畫面顯示任何診斷文字，不掛 `parentElement.__city`。
- 天氣依 `weather.sky` 選畫法（`calm`＝只畫天空漸層）；面板以 `data-sev` 套嚴重度色，新增 `neutral` 色。
- `vacant` 為 true：畫空地塊，不畫建築或坑洞。
- `plate_mode`：
  - `faded`：名稱牌淡化但文字對比仍不低於 4.5:1（BR-4 與 BR-9 同時成立：以虛線框、空心分區色點、不畫第二行表現淡化，不降低文字對比）。
  - `hidden`：完全不畫名稱牌，也不放進圖例與名稱牌降級的排序（BR-13）。
- 從 `present` 切到 `vacant` 的月份，建築高度動畫降到 0 後不再繪製；反向時從 0 長出。
- reduced-motion 時靜態（BR-3）；名稱牌依畫布寬度降級與圖例沿用試做（BR-1）。
- `city.css`：沿用試做色票，移除 `.dbg`。

### 12. DI 組裝（`bootstrap.py`）

```python
# Container 新增欄位
city_service: CityService

# build_container 內（沿用同一批 Service 實例）
return_service = ReturnService()
protocol_service = ProtocolService()
allocation_service = AllocationService()
house_service = HouseService()
affordability_service = AffordabilityService()
city_service = CityService(
    return_service=return_service,
    protocol_service=protocol_service,
    allocation_service=allocation_service,
    house_service=house_service,
    affordability_service=affordability_service,
    min_data_months=PROTOCOL_MIN_DATA_MONTHS,
    rebalance_threshold=DEFAULT_REBALANCE_THRESHOLD,
)
```

### 13. View（`views/overview.py`）

- 模組常數：`_CITY_COMPONENT_KEY = "city_overview"`、`_CITY_MONTH_KEY = "city_month"`。
- `render()`：`st.title("總覽")` 之後先呼叫 `_render_city()`，其餘既有內容與邏輯不改。
- `@rerun_fragment(label="城市總覽") def _render_city() -> None`，順序見 AD-9。讀取：`holding_repo.list_holdings()`、`record_repo.read_all()`；有資料才再讀 `protocol_threshold_repo.read_thresholds()`、`house_param_repo.read_params()`、`subjective_trigger_repo.read_triggers()`、`target_repo.read_targets()`。`current_year` 用 `today_in_timezone(TIMEZONE).year`。
- 小卡：以 `presentation.building_card`／`site_card` 的結果用 `st.*` 渲染；沒有選取時顯示 `CITY_TEXT.CARD_HINT`。
- 模組 docstring 更新：說明城市區塊、fragment 與數字卡的關係。

### 14. 其他既有檔案

| 檔案 | 變更 |
|------|------|
| `views/house.py` | `_TRIGGER_LABEL` 改用 `HOUSE_TRIGGER.LABEL`，顯示文字不變 |
| `pyproject.toml` | `streamlit[auth]>=1.66`；若 tracer bullet 發現 wheel 缺 `.js`/`.css`，補 hatch include 設定 |
| `uv.lock` | 隨 `pyproject.toml` 重新鎖定（streamlit 仍為 1.66.1） |
| README（交給 4-1） | 總覽頁新增城市區塊、Streamlit 下限、人工目視清單 |

---

## 受影響的既有測試（交給 1-3／1-4）

| 測試 | 影響 | 處理 |
|------|------|------|
| `tests/test_overview.py` 的 SC-071 三個 AppTest | 替身容器沒有 `city_service`；fragment 入口的 `verified_container()` 會走真正的 `bootstrap.get_resilient_container()` 而失敗 | 比照 `tests/test_input_view.py` 的 `fragment_entry_probe`，patch `get_resilient_container` 與 `get_read_cache`；替身容器補 `city_service`（月度紀錄為空，走 BR-11 路徑，不需其他替身） |
| `tests/test_read_cache_equivalence.py` 的 SC-118 | 同上，fragment 入口需 patch；城市多讀 `read_targets` 等查詢 | patch 入口；「同一次冷重跑每個不同查詢只往返一次」的斷言仍應成立（城市的重複讀取命中快取） |
| 買房頁測試 | 標籤改由常數提供 | 文字不變，預期不需修改 |

---

## 驗證方式建議（交給 1-3／1-4）

| 層 | 驗什麼 | 工具 |
|----|--------|------|
| `CityService` | 進版位條件（BR-8、BR-15，含只有留空列的項目）、三種狀態（留空不論之前有沒有數值都是 `unfilled`）、留空月份不參與峰值與分母、前一月差額、截斷＋過濾、BR-10 例外、偏離三角掛載、`house_purpose_categories`；**最新月一致性不變式**（§5） | pytest，虛構資料 |
| `city.layout` | 移植試做 6 項；`layout_city.cache_clear()` 後量 30 棟耗時（取多次最佳值）；多 session 安全（並行呼叫結果相同） | pytest |
| `city.payload`／`presentation` | JSON 可序列化、契約欄位齊全、`selected` 失效清除、空地欄位、旗桿依 `HOUSE_TRIGGER.ALL`、常數對照表涵蓋全部類別與等級 | pytest |
| 靜態掃描 | `city.js` 無 `innerHTML` 類 API、程式碼無中日韓文字、不重定義 `GEOM` 常數、無 `setTriggerValue`；`city/*.py` 不引用 `st.user`／`st.secrets`／`st.login`／`bootstrap`／`repositories`；只有 `component.py` import streamlit | pytest 讀檔 |
| 頁面 | 有資料時總覽頁掛上 `bidi_component`（AppTest 中為 `UnknownElement`）、無例外；無資料時不掛元件並顯示中性提示；數字卡仍在 | AppTest，比照 `tests/test_data_io.py` 的暫存 libsql＋`build_container` |
| 打包 | wheel 內有 `city.js`、`city.css` | `uv build` 後列出 wheel 內容 |
| 效能（成功標準 5） | 本機以同一份資料，在 main 與本分支各切到總覽頁 10 次（讀取快取已暖），取 `kind=full page=總覽` 的 `elapsed_ms` 中位數比較，增加不超過 100ms；拖滑桿只出現 `kind=fragment page=城市總覽` | 量測 log |
| 視覺與互動 | 點擊、動畫、深淺色、手機 390 寬、空地與淡化名稱牌、留空月份不畫建築與名稱牌（版位不動）、中性天氣、Community Cloud | 人工目視清單（沿用 `spike-findings.md`，加上本 Change 新增的空地、淡化、留空、中性天氣） |

---

## 實作順序約束（交給 1-4）

1. Tracer bullet 必須第一個做，且三項瀏覽器驗證結果回報後才進入後續 Task（AD-12）。
2. `geometry.py` 先於 `layout.py`；`layout.py` 與 `CityService` 互不依賴，可並行。
3. `frame_at` 的一致性測試必須與 `frame_at` 同一個 Task 完成，不得延後。
4. 常數（§1）先於 `presentation.py` 與 JS 改寫。
5. 量測比對（成功標準 5）在頁面整合後、合併前做；超出預算時依技術債 TD-D 的觸發條件處理，不得自行擴大快取範圍。
6. 合併前提醒使用者備份 CSV；合併後在正式站目視（TD-3）。

---

## 已知技術債與限制

- **TD-A 買房評估編排三份**：`views/house.py`、`views/overview.py`、`CityService` 各一份。以 §5 一致性不變式測試守住。後續可讓兩個頁面改用 `CityService`（或抽出的共用編排）取得最新月結果。
- **TD-B DataFrame 轉模型兩份私有版本**：新增 `core/utils.records_frame_to_models` 供 `CityService` 用，兩個頁面的 `_to_month_records` 未搬。
- **TD-C 幾何公式兩份**：常數已單一來源（AD-7），投影、障礙物、名稱牌、旗桿公式 Python 與 JS 各一份，靠 `check()` 測試與人工目視兜底。
- **TD-D 累積 TWR 序列每次整頁重跑算兩次**：城市 fragment 與下方數字卡各算一次，`cumulative_twr_series` 是 O(月數²)。觸發條件：量測中位數增加超過 100ms。屆時再考慮「同一次執行只算一次」的 memo。
- **TD-E D14 未實作**：偏離含購屋用途金額，以小卡註記處理（AD-6）。
- **TD-F 歷史月份沿用目前設定**：買房參數、主觀勾選、目標比重、回撤門檻都沒有歷史。工地與偏離有註記；天氣沒有小卡，不加註記。
- **TD-G 版位規模**：只量到 30 棟（約 25～28ms）；物件超過 12 個改用精簡名稱牌；高度上限固定，資產規模懸殊時小棟會壓到最低高度。
- **TD-H JS 行為無自動化測試**：AppTest 不執行 JS，點擊、動畫、降級、對比只能人工驗。
- **TD-I 字寬估算兩套**：Python 依字元類別保守估算，JS 以 `measureText` 實量；不一致時只會比預期更安全。工地名稱牌以「9,999.9 萬」估寬，自備款達 1 億以上時第二行可能略超出名稱牌。
- **TD-J 版位快取是程序級**：單一使用者 app 可接受；多使用者時要重新評估。
- **城市與數字卡無資料時各顯示一次中性提示**（AD-10）。

---

## 待確認事項

以下為解讀上的細節，本設計已採用「預設」欄的做法；使用者若無異議即照此進行，若要改，只影響 `CityService` 或呈現層的少數幾行。

| # | 問題 | 預設 | 另一選項 |
|---|------|------|----------|
| Q-A | BR-2「所有資產整段歷史最高市值」是否包含不蓋建築的購屋用途項目 | 只算進版位的資產項目（AD-4） | 含購屋用途項目（最高的建築可能頂不到天花板） |
| Q-B | 「與前一月相比」的邊界：前一月此項目不存在或未填，或本月未填 | 都不顯示差額。前一月不存在時小卡寫「較 YYYY-MM：當時沒有此項目」；前一月未填時寫「較 YYYY-MM：當時未填」；本月未填時只寫「本月未填」（AD-4） | 前一月不存在或未填時視為 0，顯示整筆金額為增加；或往前找最近一個有值的月份比較 |
| Q-C | 「含購屋用途金額」何時註明 | 只在該類別當月確實有購屋用途金額時（AD-6） | 只要有偏離三角就一律註明 |
| Q-D | 市值留空（BR-13）的地塊能不能點 | 不能點、沒有 hover 提示、不進圖例，畫面上只剩空地塊；在別的月份已選取時，小卡照常顯示並註明「本月未填」（AD-4） | 地塊可點，點了顯示同一張小卡（畫面上仍不畫建築與名稱牌） |
| Q-E | 協定資料不足時的中性天氣名稱 | 「天氣未定」，天空只畫漸層（AD-10） | 其他措辭；或沿用晴天畫面只換面板文字 |

---

## 決策總覽

| ID | 類型 | 決策 | 信心度 |
|----|------|------|--------|
| AD-1 | 架構 | 分三層：`CityService`＋`asset_lab/city/` 純模組與元件＋總覽頁 fragment；版位拆 geometry 與 layout | High |
| AD-2 | 架構 | `CityService` 注入五個既有純 Service（偏離 house-dashboard AD-3），以最新月一致性測試防分岔 | High |
| AD-3 | 架構 | `build_timeline`＋`frame_at`；歷史月份以「截斷＋過濾」重用既有 Service，不改它們 | High |
| AD-4 | 架構 | 進版位條件、三種單月狀態（present／unfilled／absent）、高度分母只看非空市值、與前一月相比只在兩月都有值時計算；市值留空的月份不畫建築與名稱牌，版位不動（BR-13 改定） | Medium（Q-A、Q-B、Q-D） |
| AD-5 | 架構 | 逐條確認歷史可算性；歷史月份工地小卡整張註明「依目前設定判定」 | High |
| AD-6 | 架構 | 偏離三角只掛當月有值的建築；「含購屋用途金額」有才註明 | Medium（Q-C） |
| AD-7 | 架構 | Python 是唯一事實來源：JS 無業務判斷與文字；文案進 `CITY_*` 常數；幾何常數以 `GEOM` 前置注入 | High |
| AD-8 | 架構 | 版位重寫：無模組級可變狀態、結果 frozen、`lru_cache` 只快取版位 | High |
| AD-9 | 架構 | 城市、滑桿、小卡同一個 `rerun_fragment`，數字卡在外；選取以 `setStateValue` 回灌 | Medium（待 tracer bullet） |
| AD-10 | 架構 | 無資料不掛元件；資料不足用中性天氣；版位不收斂拋 `CityLayoutError` | High |
| AD-11 | 架構 | `city.js` 禁用 `innerHTML` 類 API；城市模組不碰身分與機密；3-2 安全審查要執行 | High |
| AD-12 | 架構 | tracer bullet 先行，並預先列出各項不成立時的退路 | High |
| TD-1 | 技術 | Streamlit Components v2 inline 元件 | High |
| TD-2 | 技術 | 純 Canvas 2D 自繪 | High |
| TD-3 | 技術 | `streamlit[auth]>=1.66`，精確版本交給 `uv.lock` | High |
| TD-4 | 技術 | 不新增依賴；標準庫 `logging`；沒有 utils_v2 | High |
