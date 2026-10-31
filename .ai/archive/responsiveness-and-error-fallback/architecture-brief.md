# 架構分析：responsiveness-and-error-fallback

> 1-2b 產出，供 1-2 designer 整合。依據：`proposal.md`（BR-1～BR-6）、現有 codebase（`app.py`、`src/asset_lab/`、`views/`、`tests/`），以及已安裝的 Streamlit 1.66.1、libsql 0.1.11 原始碼與實測查證。
> 沿用既有偏離：initial-build AD-1（無 `main.py`/argparse，入口為 `app.py`）、AD-8（標準 `logging`、Page 層為唯一 catch 點，不用 structlog／utils_v2）。本分析不擴大偏離面。

---

## 0. 一頁結論

**核心問題**：讀取快取放哪一層、寫入後怎麼清除。

**建議**：快取放在 **Repository 之下的連線層**，做成包住 libsql 連線的 read-through 快取，Repository、Service、Page 都不用知道有快取。清除只看一個點：**`commit()` 成功就清**。交易進行中的讀取不走快取。快取存放在獨立的程序級 TTL store，生命週期跟連線脫鉤。理由見 §3 A1／A2。

| # | 建議 | 信心 |
|---|------|------|
| A1 | 快取層級：連線層 read-through（`CachingConnection`），對上層透明 | 中高（替代方案 R 見 §3） |
| A2 | 清除時機：`commit()` 成功才清（唯一清除點）；交易中讀取繞過快取；用世代計數防止競態寫回 | 高 |
| A3 | 快取儲存：自建 TTL store（注入時鐘、加鎖），用 `@st.cache_resource` 持有，不用 `st.cache_data`；整批過期，在每次重跑入口判定 | 高 |
| A4 | 會拿來規劃寫入或當守門條件的讀取，必須讀最新資料：寫入按鈕用 `on_click` 先清快取 | 中（須確認 Q2） |
| A5 | 連線檢查：建表移出每次重跑（每程序一次）；改用 `SELECT 1` 走「不經快取」的連線；fragment 入口也要檢查 | 高 |
| A6 | 量測：計數層放在快取**之下**（只算真的打到資料庫的次數）；每個重跑只由最外層記一行 log；**要先補上 logging 設定**，否則 INFO 會被丟掉 | 高 |
| A7 | 錯誤兜底分四層：`config.toml` 加 `st.set_option`（設定檔加腳本內設定，雙保險）、app 入口邊界、fragment 邊界，既有 Page 層的 `AssetLabError` catch 不動 | 高 |
| A8 | 月度錄入 fragment 只包「項目選擇＋編輯器＋預覽＋存刪」；**`AssetLabError` 的 catch 一定要搬進 fragment 內** | 高（已查原始碼） |
| A9 | 把「重跑入口三件事」（連線檢查、錯誤邊界、量測）包成專案自己的 fragment 裝飾器，給之後的城市總覽重用 | 中 |
| A10 | 同一次重跑內的重複查詢，仍在頁面層去除，因為存檔後的重跑是冷快取 | 高 |

**最需要注意的三個技術陷阱**（都已用原始碼或實測查證）：
1. **fragment 會吞掉例外**：Streamlit 1.66.1 中，任何從 fragment 函式拋出的 `Exception`，即使發生在整頁重跑時，也會先由 Streamlit 預設處理（記 log＋顯示），再改拋 `FragmentHandledException`。頁面外層的 `except AssetLabError` 因此接不到。如果 catch 不搬進 fragment，上一個 Change 建立的「存檔失敗，資料未變更，請重試」友善訊息會失效（`views/input.py:110-135`、`streamlit/runtime/fragment.py:768-782`）。
2. **INFO log 現在根本不會輸出**：專案沒有設定任何 logging handler（AD-8 寫「於 bootstrap 統一設定 level」，實際沒做）。Streamlit 只設定自己的 `streamlit` logger（`propagate=False`），root 沒有 handler，所以只會落到 Python 的 lastResort（WARNING 以上）。新增的「每次重跑一行耗時」log 如果用 INFO，**雲端與本機都看不到**。
3. **`config.toml` 可能在雲端被蓋掉**：Streamlit 設定優先序是「config.toml < 環境變數 < 命令列參數 < 腳本內 `st.set_option`」（`streamlit/config.py:3075-3138`）。Streamlit 原始碼註解指出 Community Cloud 仍使用舊版 `showErrorDetails=False`，相當於 `stacktrace`，會顯示堆疊。只改 `config.toml` 不保證雲端生效。

---

## 1. 現況分析

### 1.1 分層與組裝

```
app.py（守門 → 取容器 → st.navigation 路由）
  └ views/*.py（Page＝Controller/View，唯一 catch 點）
       ├ Services（純運算；只有 MonthlyInputService 經 Protocol 注入讀取用 repo）
       └ Repositories（SQL I/O，建構子注入 conn）→ Models（pydantic，非 frozen）
bootstrap.py（組裝根：get_connection／get_container 皆 @st.cache_resource；
              get_resilient_container 每次重跑用 ensure_schema 探測，失效就清兩層快取重建）
```

- 頁面大量**直接呼叫 Repository**（02-architecture §1、§4 允許 Controller 直接呼叫 Repository）。這代表快取如果放在 Service 層，大部分讀取根本不會經過。
- Service 幾乎都不碰 I/O（02 §5），只有 `MonthlyInputService.prefill_from_previous` 透過注入的 repo 讀資料。

### 1.2 每次整頁重跑的資料庫往返盤點（冷快取）

| 位置 | 查詢 | 次數 | 重複／重疊 |
|------|------|------|-----------|
| `app.py` → `get_resilient_container` → `ensure_schema` | 6 CREATE + 4 PRAGMA + commit | 約 11 | 純探測成本；重連時再執行 2 次（重建容器＋再驗證）共約 22 |
| 總覽 `views/overview.py` | read_params、list_holdings、read_all、read_triggers、latest_year_month、read_range、list_holdings、read_thresholds | 8 | `list_holdings` 重複 2 次；`read_all` 與 `read_range(EARLIEST..latest)` 資料相同只是形狀不同 |
| 月度錄入 `views/input.py` | list_holdings、read_month、read_holding_records（負債項目無）；按「帶入上月」再加 latest_year_month、read_month | 2–3（+2） | 編輯器在每次金額欄失焦都會重跑整頁 |
| 資產配置 `views/allocation.py` | list_holdings、latest_year_month、read_range、read_month（圓餅）、read_month（偏離）、read_targets | 6 | `read_month(latest)` 重複 2 次 |
| 報酬率 `views/returns.py` | latest_year_month、read_range（全區間，只為了取最早月）、read_range（選定區間）、list_holdings | 4 | 「自開始記錄」模式下兩次 `read_range` 完全相同 |
| 買房 `views/house.py` | read_params、list_holdings、read_all、read_triggers | 4 | 與總覽的買房摘要編排重疊（既有已知限制） |
| 設定 `views/settings.py` | list_holdings、read_targets、read_thresholds、read_params | 4 | — |
| 匯出入 `views/data_io.py` | list_holdings、read_all、read_all(targets)；按匯入再加 read_all、list_holdings | 3（+2） | — |
| 行為協定 `views/protocol.py` | 讀檔，不碰資料庫 | 0 | — |

與 proposal 的「連線檢查約 11 次＋各頁 3–8 次」一致。

### 1.3 寫入路徑盤點（快取清除必須涵蓋全部）

| 觸發 | 方法 | commit 形式 | 失敗呈現（現況） |
|------|------|-------------|-----------------|
| 月度錄入「儲存此列」 | `record_repo.upsert_records` | `write_transaction`（單一交易） | `PersistenceError` 轉友善訊息 |
| 月度錄入「刪除此列」 | `record_repo.delete_record_and_upsert` | `write_transaction` | 友善訊息 |
| 匯出入「執行匯入」 | `csv_import_writer.write_import`（三張表的 `*_with_context`） | `write_transaction` | 友善訊息（頁面自己的 `except PersistenceError`） |
| 設定「新增／儲存變更」 | `holding_repo.add_holding`／`update_holding` | 單句加 `commit()` | **libsql 原生 ValueError 顯示堆疊** |
| 設定「儲存 {分類}」 | `target_repo.upsert_target` | 單句加 `commit()` | 堆疊 |
| 設定「儲存門檻」 | 3 次 `upsert_threshold` | **3 個獨立 commit（非原子）** | 堆疊 |
| 設定「儲存買房參數」 | 9 次 `upsert_param` | **9 個獨立 commit（非原子）** | 堆疊 |
| 買房「主觀勾選」 | `subjective_trigger_repo.upsert_trigger` | 單句加 `commit()`，**在 `on_change` callback 內執行** | 堆疊（callback 不在頁面的 try 範圍內） |
| （頁面未使用） | `insert_record`／`upsert_record`／`delete_record` | 單句加 `commit()` | — |

**結構事實**：所有寫入路徑最後都會走到連線的 `commit()`。所以「commit 成功」是唯一而且完整的清除點（A2 的根據）。

### 1.4 連線存活與重連

- `ensure_schema()` 同時負責建表遷移與存活探測（職責混在一起），每次重跑約 11 次往返。
- 重連時會清掉 `get_connection` 和 `get_container` 兩層快取，`get_container` 重建時又會執行一次 `ensure_schema`，再驗證又一次，所以一次重連約 22 次往返。
- 失效樣態以訊息含 `stream not found` 判定。測試樣本是 Hrana over HTTP 的 `status=404`。**伺服器端 stream 閒置多久會過期目前沒有實測值**（AD-1 t16 記錄的是「閒置隔夜」）。如果過期時間比使用者操作間隔短，每次操作都會付出重連成本。這需要靠新的量測 log 確認（A6 建議把重連事件也記下來）。
- **只有整頁重跑的入口會做存活檢查**。`on_change` callback 在 `app.py` 主體之前就執行，fragment 重跑完全不經過 `app.py`，這兩條路徑都沒有重連保護（見 TD-6）。

### 1.5 錯誤呈現

- 各頁只 catch `AssetLabError`，其他例外交給 Streamlit 預設處理。`client.showErrorDetails` 預設為 `full`，雲端是舊版 `False`（等同 `stacktrace`），都會露出堆疊。
- 會露出堆疊的已知路徑：設定頁全部單筆寫入、所有讀取失敗（網路、SQL）、`_container()` 取不到容器、買房勾選 callback。

### 1.6 Logging

- 頁面與模組用 `logging.getLogger(__name__)`。Streamlit 以 `__main__` 模組名執行頁面腳本（`streamlit/navigation/page.py:508`），所以**所有頁面的 logger 名稱都是 `__main__`**，log 裡分不出是哪一頁。
- 沒有任何 handler 或 level 設定，所以 INFO 以下全部被丟掉（見 §0 陷阱 2）。目前 `logger.exception` 之所以看得到，是因為 ERROR 等級高於 lastResort 的 WARNING 門檻。

### 1.7 Streamlit 1.66.1 執行模型（已查原始碼，設計時必須遵守）

| 事實 | 來源 | 設計影響 |
|------|------|----------|
| `st.stop()`／`st.rerun()` 拋出的 `ScriptControlException` 繼承 **BaseException** | `runtime/scriptrunner_utils/exceptions.py:22` | 入口邊界用 `except Exception` 不會吞掉控制流程 |
| fragment 內拋出的 `Exception` 會先由 Streamlit 處理，再改拋 `FragmentHandledException(Exception)`；整頁重跑時也一樣 | `runtime/fragment.py:768-782`、`errors.py:54` | catch 要放進 fragment 內；入口邊界必須**放行** `FragmentHandledException`，避免重複顯示錯誤 |
| fragment 重跑只執行 fragment 函式本身，用的是上次整頁重跑時記下的參數 | `runtime/fragment.py` | `app.py` 的計時、連線檢查、錯誤邊界都不在呼叫堆疊上 |
| widget callback 在腳本主體之前執行 | ScriptRunner 流程 | callback 的寫入發生在 `app.py` 連線檢查之前；callback 的查詢次數會落到「下一行」量測 |
| `client.showErrorDetails` 可在腳本內 `st.set_option`（scriptable），而且腳本內設定優先序最高 | `config.py:154-200, 575-610, 3075-3138` | 用腳本內設定當主防線 |
| `st.exception()` **不受** `showErrorDetails` 影響，永遠顯示完整堆疊 | `elements/exception.py:253-262` | 開發模式顯示細節必須由程式自己判斷，不能無條件呼叫 `st.exception` |
| 預設的未捕捉例外訊息是英文通用文案，堆疊寫進伺服器 log | `elements/exception.py:50-56`、`error_util.py:84-111` | callback 路徑只能靠這一層 |
| `st.App(on_script_error=...)` 可以統一攔截腳本、callback、fragment 的錯誤，但要改用 Starlette App 入口 | `web/server/starlette/starlette_app.py:335-440` | 列為否決方案（A7） |
| AppTest 對 widget 的互動似乎一律觸發整頁重跑（看不到 fragment 範圍的重跑） | `testing/v1/app_test.py` | 「只有編輯器重跑」很難用 AppTest 直接驗證（Q8） |
| libsql 的查詢結果是 `list[tuple]`（不可變）；連線有 `in_transaction`，DML 後為 True，commit 後為 False | 本機 `:memory:` 實測 | 連線層快取可以直接共享 row，不會有別名污染；交易中讀取可以靠 `in_transaction` 判斷要不要繞過 |

---

## 2. 技術債與擴展性限制

| ID | 技術債 | 影響 | 本 Change 處理建議 |
|----|--------|------|-------------------|
| TD-1 | `ensure_schema` 同時負責建表與存活探測 | 每次重跑約 11 次往返；重連約 22 次 | 拆開（A5） |
| TD-2 | 沒有讀取快取，同一次重跑內重複查詢 | 主要延遲來源 | A1–A4、A10 |
| TD-3 | logging 沒有設定（AD-8 承諾的「bootstrap 統一設定 level」沒實作）；頁面 logger 名稱都是 `__main__` | INFO 遺失；log 分不出頁面 | A6 補上設定；頁面 logger 改用明確名稱屬於選配（Q7） |
| TD-4 | 設定頁單筆寫入沒有轉成領域例外，門檻（3 筆）與買房參數（9 筆）是逐筆 commit | 失敗露出堆疊；可能只寫入一部分 | 堆疊由 A7 的全站兜底處理；**非原子寫入不在本 Change 範圍**，建議另案（proposal 沒列） |
| TD-5 | 寫入用的 repo 被 callback 的 `kwargs` 抓住（買房勾選） | 重連後 callback 仍拿著舊連線 | 連線層包裝後 repo 參照的是穩定的 proxy，但 proxy 內部連線不會換，見 TD-6 |
| TD-6 | 只有整頁重跑入口有重連保護；callback 與（新增的）fragment 入口沒有 | 閒置後操作勾選框或 fragment 可能遇到失效連線，BR-1 沒涵蓋到 | fragment 入口必須補上（A5）；callback 屬既有缺口（Q4） |
| TD-7 | `views/input.py` 的「帶入上月」把結果寫進 `st.session_state["prefilled_records"]`，但全專案沒有地方讀 | 按鈕看起來沒效果，是死狀態 | 範圍外，記錄後另案 |
| TD-8 | 總覽與買房頁重複編排（`_to_month_records` 重複），是既有已知限制 | 讀取重疊 | 快取命中後成本趨近 0，不另外處理 |

**擴展性**：接下來的城市總覽元件也會頻繁觸發重跑，很可能需要 fragment。A9 的「專案 fragment 裝飾器」可以讓那個 Change 直接套用，不用再踩 §1.7 的陷阱。

---

## 3. 設計提案與權衡

### A1　讀取快取放哪一層（核心問題）

**推薦：方案 C，連線層 read-through 快取。**

在 libsql 連線外面包一層 `CachingConnection`／`CachingCursor`（裝飾器模式），由 bootstrap 組裝後注入各 Repository。`SELECT` 語句以 `(sql, params)` 為鍵快取「取回的 rows」，其他語句直接透傳。Repository 每次都從 rows 重新組出 Model 或 DataFrame。

- **優點**
  - 完全透明：Repository、Service、Page 的程式碼都不用改。符合 02-architecture §2 維度 C「技術迭代（分頁、重試、連線管理）→ Repository 內部，對上層透明」與 §6「基礎設施韌性由 I/O 層處理」。
  - **BR-6 的保證最強**：快取的是資料庫回傳的不可變 tuple，下游每次拿到的都是重新組出來的新物件。不可能因為某個 Service 或 Page 原地修改 DataFrame 或 Model 而污染快取（現有 Model 都不是 frozen，Service 目前沒有原地修改，但也沒有任何機制擋）。
  - 清除點只有一個，而且是**失敗安全**的：以後新增的寫入方法只要照現在的慣例 commit，就自動會清快取（A2）。
  - 涵蓋所有讀取入口：Page 直接讀、`MonthlyInputService` 經 Protocol 讀、callback、fragment 都一樣。
  - 計數層可以放在它下面，「真正打到資料庫的次數」自然就是量測要的數字（A6）。
- **缺點**
  - 需要模擬 cursor 介面。目前 repo 只用到 `cursor()`、`execute`、`fetchall`、`fetchone`、`lastrowid`、`commit`、`rollback`（已盤點）。之後如果用到 `description`、`fetchmany`、迭代或 `executemany`，命中快取時會失效。**proxy 必須對不支援的介面明確拋錯，不能默默給錯結果。**
  - 語句分類依賴 SQL 前綴（`SELECT`）。現有常數都以 `SELECT` 開頭，`PRAGMA` 與 DDL 一律透傳不快取。
  - 有點「魔法」：讀 Repository 的人看不出有快取。要在 bootstrap 與 proxy 模組的 docstring 寫清楚。
  - 存活探測（`SELECT 1`）**一定不能經過快取**，否則探測永遠命中、形同失效。必須讓探測走未快取的連線（A5）。

**替代：方案 R，Repository 裝飾器**（每個 repo 包一個快取版本，只覆寫讀取方法）

- 優點：快取是明確寫在 Repository API 上的；用方法語意當鍵，可讀性好。
- 缺點：要包 6 個 repo、12 個讀取方法；回傳的是可變物件（list[Model]、DataFrame），必須深拷貝或保證沒人修改，否則會違反 BR-6；清除要分散在每個寫入方法上，**以後新增寫入方法時是失敗不安全的**（忘了包就會讀到舊資料），需要另外寫內省式契約測試補救；`*_with_context` 的清除必須延後到交易 commit，邏輯比方案 C 複雜。
- 評價：可行，但 BR-2 與 BR-6 的保證都要靠紀律維持，不是靠結構。designer 如果比較重視「明確」勝過「透明」，可以選 R（Q1）。

**否決方案**

| 方案 | 否決理由 |
|------|----------|
| S：在 Page 層到處用 `st.cache_data` | 快取與清除散落在 8 個頁面，每個寫入點都要記得清（BR-2 容易漏）；函式要用 `_repo` 參數略過雜湊，所以快取鍵不含連線，**測試之間會互相污染**（`st.cache_data` 在非 runtime 下是程序全域）；違反 DRY，會長成 Big Ball of Mud |
| V：Service 層讀模型快照（整庫一次讀進記憶體，月份與區間篩選改在 Python 做） | 往返次數最少，但改變了「怎麼讀」（BETWEEN、排序、NULL 語意從 SQL 搬到 Python），BR-6 風險高、改動面大，Service 還要開始碰 I/O。屬於 premature optimization，否決 |
| 依資料表細分清除 | 資料量是個人等級，整批清除後重新讀取的成本很小。細分清除會增加錯誤機會卻沒有可觀收益，否決 |
| Turso embedded replica | proposal 明確排除 |

### A2　寫入後清除

**推薦：`commit()` 成功是唯一的清除點，再加上兩條防護。**

1. `CachingConnection.commit()` 呼叫內層 commit，**成功後**才清空快取；commit 失敗或 rollback 都不清。完全對應 BR-2 的「寫入成功才清除；寫入失敗不清除」。
   - 設定頁逐筆寫入門檻時，如果第 1 筆成功、第 2 筆失敗：第 1 筆的 commit 已經清過快取，所以快取不會殘留舊值。**以「每次 commit」為粒度天然正確**；如果改成「每個頁面動作清一次」就會出錯。
   - callback 裡的寫入（買房勾選）一樣經過 commit，所以也會清，接下來的重跑會讀到新值。
   - `ensure_schema` 的 DDL commit 也會清，只在啟動時發生，無害。
2. **交易中讀取繞過快取**：`inner.in_transaction` 為真時，`SELECT` 直接打資料庫而且不寫回快取，確保交易內能讀到自己剛寫的資料。現有程式沒有交易內讀取的情況，這是預防。遠端 Hrana 下 `in_transaction` 是否同樣準確需要實測；不準時改成由 proxy 自己追蹤「上次 commit 後是否執行過寫入」。
3. **世代計數**：每次清除時世代加一；未命中時先記下目前世代，查詢回來時世代沒變才寫回快取。這是防止多個分頁同時操作時，「寫入前發出的查詢」在寫入清除之後才回來、把舊資料寫回去而保留 5 分鐘（否則 BR-2 在多分頁下會破）。實作成本很低。

- 否決：「寫入前先清」——失敗時也會清，違反 BR-2 字面要求。
- 否決：「在每個 Repository 寫入方法上清」——等於方案 R，失敗不安全。

### A3　快取儲存與生命週期

**推薦：自建 `ReadCache`（純 Python，注入時鐘、`threading.Lock`、有世代計數），用一個獨立的 `@st.cache_resource` 持有，注入 `CachingConnection`。**

- **跟連線生命週期脫鉤**：重連只重建連線與容器，不清讀取快取。資料是否有效跟連線無關，重連後不用全部重讀。
- **整批過期，在重跑入口判定**：TTL 從「最後一次清除後第一筆寫入」起算，在每次重跑入口（`app.py` 主體開頭、fragment 入口）判斷是否超過 5 分鐘、超過就整批清除，**單一次重跑內不做逐筆過期判斷**。如果逐筆各自過期，同一頁可能一部分讀到 4 分鐘前的快照、一部分讀到最新資料（另一台機器寫入時，例如主檔是舊的、紀錄是新的）。整批過期保證每次重跑看到一致的快照，對 BR-6「讀到什麼」較穩。
- TTL 5 分鐘是 BR-3 寫定的業務值，建議放 `constants.py`（例如 `READ_CACHE.TTL_SECONDS`），由 bootstrap 注入，不寫在 store 裡（03-data-config §1）。
- 範圍是**程序全域、跨 session 共用**：允許清單內的人看的都是同一個資料庫，而且所有頁面都在守門之後才讀資料，不會外洩。側欄的「重新讀取資料」會清整個程序的快取（本機與雲端各自獨立，符合 BR-3 例外欄）。
- 為什麼不用 `st.cache_data`：TTL 過期無法用假時鐘測試；在程序全域下測試會互相污染；每次命中都要 pickle 往返；連線層要的是「依 SQL 鍵存取，由 commit 觸發清除」，這種語意用自建 store 一頁程式就寫得出來，套 `st.cache_data` 反而要繞路（避免 Golden Hammer）。

### A4　需要最新資料的讀取（新發現的風險，須確認 Q2）

快取的過期窗口從「同一次重跑的幾毫秒」拉長到「最多 5 分鐘」。有兩類讀取不只是拿來顯示：

| 讀取 | 用途 | 讀到舊資料的後果 |
|------|------|-----------------|
| `data_io._render_import` 的 `record_repo.read_all().empty and not holding_repo.list_holdings()` | **破壞性匯入的守門條件**（`replace_all` 會先 DELETE） | 另一台機器 5 分鐘內寫過資料、這裡卻還認為是空庫 → 守門被繞過，**資料被覆蓋** |
| 月度錄入編輯器的 `read_holding_records` → `plan_save`／`plan_delete` | 推算存檔列與後續受影響的月份 | 以舊鏈推算後 upsert，可能覆蓋另一處的寫入（lost update） |

**推薦：寫入或匯入按鈕用 `on_click=<清快取>`。** callback 在重跑前執行，所以這次重跑的規劃讀取一定是最新的。成本只有一次冷讀取，而存檔後原本就會重讀。匯入守門條件至少必須這樣做（破壞性操作）；存檔規劃建議也這樣做。顯示用途（表格、預覽、帶入值）照常走快取。

- 替代：Container 另外提供「不經快取」的 repo 給特定讀取用——介面會膨脹，否決。
- 替代：接受風險並在文件說明——匯入守門不建議接受；存檔規劃可以接受（使用者是同一人），由使用者決定（Q2）。

### A5　連線存活檢查

**推薦（P1，漸進式）**

1. **建表每個程序只做一次**：另外用一個 `@st.cache_resource` 保證 `ensure_schema` 每個程序只跑一次，跟 `get_container` 分開。重連只清連線與容器，**不重新建表**，符合 proposal「建表只在啟動時做一次」。
2. **用便宜的探測**：新增 `ping()`（`SELECT 1`）。建議放在一個獨立的小 Repository（單一職責），也可以加在 `SchemaRepository` 上，由 designer 決定。探測注入的是**計數層連線、不經快取**，這一次往返會被計入量測。
3. `_with_reconnect_on_stale_stream` 的結構保持不變（SC-042 的 4 個測試只要把 `ensure_schema` 換成 `ping`），重試上限仍是 1（BR-1）。
4. **每個重跑入口都要取得一次已驗證的容器**：`app.py` 主體與**每個 fragment 入口**。fragment 不能沿用上次整頁重跑時抓住的容器或 repo，要自己呼叫 `get_resilient_container()`。這樣每個入口最多 1 次往返，符合成功標準。
5. 重連時記一行 WARNING（例如「連線失效已重連」）並在量測 log 標記，用來實測 stream 過期頻率（§1.4 的未知數）。

**考慮過、本 Change 不採用：P3 自我修復連線 proxy**（連線層在閒置超過門檻、第一次真的要打資料庫前自動探測，失效就在 proxy 內部換掉底層連線）

- 優點：快取命中的重跑是 0 次往返；fragment 與 callback 一次涵蓋（也修掉 TD-5、TD-6）；不用再清 cache_resource 重建容器。
- 缺點：要處理交易進行中的語意（不能在交易中途換連線）；cursor 要能重新綁定；閒置門檻取決於還沒量測的 stream 過期時間；測試面大，還要改寫 SC-042 的機制。
- 結論：先用 P1 拿到量測數據。如果 log 顯示探測往返佔比明顯，或重連很頻繁，再另案改成 P3。

### A6　量測（每次重跑一行耗時與查詢次數）

1. **先補 logging 設定**（AD-8 的缺口）：在 bootstrap 提供 `configure_logging()`，用 `@st.cache_resource` 或冪等檢查確保每個程序只設定一次，避免每次重跑重複加 handler。root 維持 WARNING，專案的 logger（`asset_lab.*` 與頁面用的 logger）設 INFO，輸出到 stderr，雲端的 Manage app → Logs 看得到。
2. **計數層 `CountingConnection` 放在快取之下**：把 `execute`、`commit`、`rollback` 都算成一次往返（與 proposal「約 11 次」的算法一致：6 + 4 + commit）。
   - 每個執行緒一個計數器（threading.local 或 contextvars；Streamlit 每個 session 的腳本在自己的執行緒執行），避免多 session 的數字混在一起。
   - 另外保留一個程序累計值給測試用：AppTest 的執行緒模型不一定和測試主執行緒相同，用累計差值斷言比較穩。
3. **只由最外層記錄**：計時用一個可巢狀的 context，執行緒內記錄深度，只有最外層離開時才記一行並「讀取後歸零」計數。
   - 整頁重跑時 `app.py` 是最外層，fragment 在裡面，不重複記。
   - fragment 重跑時 fragment 裝飾器就是最外層，記一行並標記為 fragment。
   - 因為是在**結束時**歸零，callback 在腳本前產生的查詢會算進同一行（如果在開頭歸零，這些查詢就會不見）。這依賴「callback 與腳本在同一執行緒」，實作時要驗證。
4. 欄位建議：頁面名稱（`navigation.title`；fragment 由裝飾器參數指定）、重跑類型（full 或 fragment）、耗時毫秒、資料庫往返次數、快取命中與未命中數（選配，可以直接用 log 驗證「快取期間不再查詢」）、是否重連。**不得記錄 email 等個資**（sensitive-data-guard）。
5. 時間點：proposal 要求量測紀錄最先做。**main 會自動部署**，所以「雲端基準」必須先把只含量測的版本部署上去，才能做優化。這會讓交付變成兩階段（Q5）。

### A7　全站錯誤兜底（BR-5）

| 層 | 機制 | 涵蓋 | 備註 |
|----|------|------|------|
| L0 | `.streamlit/config.toml`：`[client] showErrorDetails = "none"` | 腳本還沒執行到 `set_option` 之前的錯誤（例如 import 失敗） | 防禦縱深；雲端可能被命令列參數或環境變數蓋掉 |
| L1 | `app.py` 一開頭 `st.set_option("client.showErrorDetails", …)`，值由**專案自己的環境變數開關**決定（預設 `none`，本機可設為 `full`） | Streamlit 預設處理的所有未捕捉例外，**包括 callback 與 fragment** | 腳本內設定優先序最高，是雲端的主防線。開關**必須用專案自己的環境變數**，因為 Streamlit 原生的 `--client.showErrorDetails` 會被 L1 蓋掉。由 `app.py` 讀取環境變數符合 AD-1／main 合約「解析參數」的定位 |
| L2 | `app.py` 入口邊界：包住守門與 `navigation.run()`，`except Exception`，但**放行 `FragmentHandledException`** | 整頁重跑中所有未預期錯誤 | `logger.exception`，再顯示中文通用訊息（例如「發生未預期錯誤，請稍後再試」）。開關開啟時改用 `st.exception`（它不受 showErrorDetails 管制，所以只能由這個開關決定是否呼叫）。`st.stop`／`st.rerun` 屬 BaseException，自然會放行 |
| L3 | fragment 邊界（由 A9 裝飾器提供，邏輯同 L2） | fragment 重跑 | 因為 L2 不在 fragment 重跑的呼叫堆疊上 |
| 既有 | 各頁 `except AssetLabError` 轉友善訊息 | 領域錯誤 | 不動；fragment 內那一段要搬進 fragment（A8） |

- callback 路徑只有 L0、L1 保護，看到的是 Streamlit 的英文通用訊息，沒有堆疊，符合「不露堆疊」，只是語言不一致（Q4）。
- **否決 `st.App(on_script_error=...)`**：它能一次統一腳本、callback、fragment 的錯誤處理（最乾淨），但要把入口改成 Starlette App 物件。Community Cloud 是否支援沒有驗證，而且會換掉整個伺服器堆疊，風險與本 Change 範圍不成比例。可以留到 Streamlit 雲端確認支援後再評估。
- 否決：只依賴 `config.toml`（雲端可能不生效）；只依賴 L2（漏掉 callback 與 fragment）。

### A8　月度錄入的 fragment 邊界

**推薦（F1）**

- fragment 內：「項目」下拉、四種編輯器、推算預覽、儲存與刪除按鈕。
- fragment 外：年月下拉、「帶入上月」按鈕、本月已存紀錄表格、flash 訊息。改年月本來就該整頁重跑。
- **只傳穩定的識別值當參數**（`target_ym` 字串）。fragment 內自己透過 A5 取得容器，再讀 holdings、month_records、holding_records（走快取）。不要傳 container、repo 或資料清單進去，因為 fragment 重跑沿用的是上次整頁重跑的參數，物件可能已經過時。
- **`except AssetLabError` 必須在 fragment 函式內**（§0 陷阱 1）。現有 `tests/test_input_view.py` 的三個 `_FRIENDLY_WRITE_FAILURE` 斷言（約第 900、920、931 行）在 catch 位置放錯時會失敗，可以當回歸護欄。
- 存檔或刪除成功後維持 `st.rerun()`（預設 scope 為 app）整頁重跑，表格與 flash 訊息在 fragment 外，必須整頁更新。這次重跑的成本是 1 次探測加上冷讀取 2–3 次（快取已被 commit 清掉）。
- 替代 F2：表格也放進 fragment，存檔改用 fragment 範圍重跑，可以省下一次整頁重跑，但 flash 與表格位置要重排，改動面較大。proposal 沒要求，不建議。

### A9　專案共用的「重跑入口」fragment 裝飾器

把 fragment 入口必須做的三件事包成一個裝飾器（例如 `app_fragment(label=...)`），內部組合：`st.fragment`、取得已驗證容器（A5）、錯誤邊界（A7 L3，包括 `AssetLabError` 友善訊息與未預期錯誤的通用訊息）、量測計時（A6，只有最外層才記錄）、整批 TTL 判定（A3）。

- 優點：月度錄入與之後的城市總覽共用；把 §1.7 的陷阱封裝在一個地方，避免每個新 fragment 重新踩一次。
- 缺點：多一層抽象。如果只有一個使用者，可以先直接寫在 `views/input.py`，等城市總覽出現時再抽出來（designer 決定，建議直接抽，因為城市總覽已在 roadmap 上）。
- 擺放：它使用 `st.*`，屬於 Streamlit runtime 黏合層，放在套件根目錄（與 `amount_widget.py`、`bootstrap.py` 同層）。不放 `core/`（core 必須純粹），也不放 `services/`（Service 不能碰 Streamlit）。

### A10　去除同一次重跑內的重複查詢

快取命中後重複查詢幾乎沒有成本，但**存檔、刪除、按「重新讀取」、TTL 到期後的那次重跑都是冷快取**，這時重複查詢仍是實際往返。建議在頁面層（Controller 的資料傳遞職責）做最小去重：

- 資產配置：`read_month(latest)` 讀一次，傳給圓餅與偏離。
- 總覽：`list_holdings` 讀一次，同時給買房摘要與協定區塊用（重構 `_compute_house_summary` 的參數）。
- 報酬率：最早月份改從同一份資料取得，或在「自開始記錄」模式下重用全區間的 `read_range`。

不建議為了去重改動 Service 的介面。總覽與買房頁的重疊（TD-8）維持現狀。

---

## 4. 元件職責與擺放建議

| 元件 | 層／模組（建議） | 職責 | 相依 | 不可做 |
|------|------------------|------|------|--------|
| `ReadCache` | `repositories/`（I/O 基礎設施） | TTL 整批過期、世代計數、加鎖的 get/put/clear | 注入時鐘、TTL | 不 import streamlit |
| `CachingConnection`／`CachingCursor` | `repositories/` | 快取 SELECT 的 rows；commit 成功後清除；交易中繞過；不支援的介面明確拋錯 | 內層連線、`ReadCache` | 不 log error（02 §6） |
| `CountingConnection` | `repositories/` | 計算 execute、commit、rollback；每執行緒計數＋程序累計 | 內層連線 | — |
| 存活探測 `ping()` | 獨立小 Repository（或 `SchemaRepository`） | `SELECT 1` | 計數層連線（**不經快取**） | — |
| 建表一次、重連、讀取快取資源、logging 設定、組裝 | `bootstrap.py`（組裝根） | 組裝順序：`libsql → Counting → Caching → repos`；探測 repo 接計數層 | `st.cache_resource`、`st.secrets` | 不放業務邏輯 |
| 重跑量測（巢狀計時、記一行） | 套件根目錄的 runtime 黏合模組 | 最外層記錄、讀取後歸零 | 計數器、logging | 不記錄個資 |
| 錯誤邊界 helper | 套件根目錄的 runtime 黏合模組 | `AssetLabError` 友善訊息、未預期錯誤通用訊息、依開關顯示細節、放行 `FragmentHandledException` | `st.error`／`st.exception`、logging | 不吞 BaseException |
| fragment 裝飾器（A9） | 套件根目錄的 runtime 黏合模組 | 組合上面三者與 `st.fragment` | 上面三者 | — |
| `app.py` | 入口 | `set_option`（讀環境變數開關）→ 守門 → 取容器 → 側欄「重新讀取資料」（`on_click` 清快取）→ 路由，外層包 L2 邊界與最外層計時 | 上面全部 | 守門之前不得碰資料、不得組容器（`test_app_guard` 的 fail-closed 契約） |
| `.streamlit/config.toml` | repo 內（新檔；`.gitignore` 只排除 `secrets.toml`） | L0 | — | 不放任何機密 |

建議組裝順序（示意，非實作）：

```
raw     = libsql.connect(...)                    # get_connection（cache_resource）
counted = CountingConnection(inner=raw)
cached  = CachingConnection(inner=counted, cache=get_read_cache())   # read cache 獨立 cache_resource
container = build_container(conn=cached, probe_conn=counted, read_cache=...)
```

`build_container` 的簽名會改變，`test_build_container_*` 要一併調整。

---

## 5. 未決選項（須確認）

| # | 問題 | 選項 | 架構建議 |
|---|------|------|----------|
| Q1 | 快取放哪一層 | C：連線層 read-through ／ R：Repository 裝飾器 | **C**（BR-2、BR-6 有結構保證、改動最小）；如果團隊更重視明確，選 R 並加內省式契約測試與深拷貝 |
| Q2 | 拿來規劃寫入或守門的讀取要不要強制最新 | 寫入按鈕用 `on_click` 清快取 ／ 接受 5 分鐘風險 | 匯入守門**必須**清；存檔規劃建議清（使用者決定是否接受跨裝置 lost update 風險） |
| Q3 | fragment 的連線檢查成本 | P1：每次 fragment 重跑 1 次探測 ／ P3：自我修復 proxy，通常 0 次 | 本 Change 採 P1，依量測結果決定是否另案做 P3 |
| Q4 | callback 路徑（買房勾選）的重連缺口與英文通用訊息 | 這次修（callback 內也取已驗證容器，該次重跑會多 1 次探測）／ 列為已知限制 | 列為已知限制（這是既有缺口，proposal 沒列）；如果使用者要求 BR-1 全面涵蓋，就這次修 |
| Q5 | 基準量測的方式與時機（proposal 已知缺陷） | M1：先部署只含量測的版本，在雲端操作取基準（要兩階段交付，因為 main 會自動部署）／ M2：本機 `streamlit run` 連正式 Turso（只讀），由使用者登入操作，量測 commit 前後兩版 ／ M3：AppTest 不經登入直接跑頁面（只能量讀取；**存檔會寫入正式庫，不能自動化**） | 查詢次數用自動化測試（記憶體 DB 加計數層）驗證；耗時以 M2 前後比較，如果使用者要雲端數字再加 M1。存檔的量測由使用者實際存一筆真實資料（或用相同值重存，upsert 結果不變） |
| Q6 | 開發用錯誤細節開關的名稱 | 專案環境變數（例如 `ASSET_LAB_SHOW_ERROR_DETAILS`）| README 要寫開法（BR-5）；雲端 Secrets 或環境變數不得設定此開關 |
| Q7 | log level 設定位置；頁面 logger 名稱 | level 用常數或環境變數；頁面 logger 改用明確名稱（例如 `asset_lab.views.input`）| level 放 `constants.py` 即可（專案沒有 config.yml，屬 AD-1/AD-8 既有偏離）；logger 名稱屬選配，會偏離 04 §1.1 的 `getLogger(__name__)`，但在 Streamlit 頁面 `__name__` 一律是 `__main__`，照規則寫反而沒有意義，要在 design 記錄理由 |
| Q8 | 「只有編輯器重跑」怎麼驗證 | 推測 AppTest 互動一律整頁重跑、看不到 fragment 重跑（只查到 fragment storage 會跨次保存，沒找到 fragment 範圍重跑的入口；未完整查證，scenario-author 或 implementor 寫測試前應先實測） | 結構斷言（編輯器入口有被 fragment 裝飾器包住）＋直接呼叫 fragment 函式本體測查詢數與錯誤處理＋2-Z 與上線時看 log 的 `kind=fragment` 行 |
| Q9 | 設定頁門檻與買房參數逐筆 commit 的非原子性（TD-4） | 本 Change 包進交易 ／ 另案 | 另案（proposal 範圍沒有）；本 Change 只保證「失敗不露堆疊」與「每次 commit 都清快取」 |

---

## 6. 對既有測試的影響

| 測試 | 影響 |
|------|------|
| `tests/test_bootstrap.py` SC-042（4 個重連測試） | 探測從 `ensure_schema` 換成 `ping`，替身改名即可；新增「重連不重新建表」的斷言 |
| `tests/test_bootstrap.py::test_build_container_*` | `build_container` 簽名改變（多了探測連線與快取）|
| `tests/test_app_guard.py`（SC-033／034 fail-closed） | `app.py` 新增的 `set_option`、logging 設定、計時、錯誤邊界**都不能在守門之前碰資料或組容器**；計時區塊在守門擋下時（`st.stop`）仍可記一行，但不得帶 email |
| `tests/test_input_view.py` | fragment 改造後，三個友善失敗訊息斷言就是 catch 位置的回歸護欄；替身容器要能被 fragment 內「自取容器」拿到（取得方式要讓測試注入得進去） |
| 新增 | `ReadCache`（假時鐘：TTL 整批過期、世代競態）；`CachingConnection`（命中與未命中、commit 成功才清、失敗與 rollback 不清、交易中繞過、不支援的介面拋錯、探測不經快取）；頁面查詢次數（記憶體 libsql 加計數層加快取，跑兩次 AppTest，第二次往返為 0）；BR-6（同一個種子庫，經快取與不經快取的服務輸出完全相同） |
| 注意 | `st.set_option` 是程序全域，在 AppTest 裡會延續到後續測試，要在 fixture 還原 |

---

## 7. Anti-pattern 檢核

| Anti-pattern | 本提案的對策 |
|--------------|--------------|
| God Object | 快取、計數、探測分成小型包裝層依序組合，不做一個萬能連線；bootstrap 只負責組裝，量測與錯誤邊界放在獨立模組 |
| Golden Hammer | 不因為 `st.cache_data` 是現成的就到處用；`st.fragment` 只用在 proposal 指定的月度錄入編輯器 |
| Premature optimization | 不做依表細分清除、讀模型快照、embedded replica、P3；先量測再決定 |
| Tight coupling | Repository、Service、`ReadCache` 不依賴 Streamlit；只有 bootstrap、`app.py` 與 runtime 黏合模組會碰 `st.*` |
| Big Ball of Mud | 拒絕在 8 個頁面各自寫快取與清除；清除只收斂在 commit 一個點 |
| Analysis paralysis | 每個未決選項都附了建議預設值，designer 可以直接採用 |
