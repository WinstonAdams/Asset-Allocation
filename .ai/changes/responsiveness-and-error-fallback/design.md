# 設計文件：responsiveness-and-error-fallback（線上版重跑提速與全站錯誤兜底）

> 依據：`proposal.md`（BR-1～BR-8）、`architecture-brief.md`（1-2b）、使用者在 1-2b 對 Q1～Q9 的決定。1-2a 已跳過，沒有 `tech-research.md`。
> 本文件只記錄架構決策與介面契約，不描述業務行為情境。**對應的 Scenarios 由 1-3 產出。**
> 沿用的既有偏離：initial-build AD-1（入口是 `app.py`，沒有 `main.py`/argparse）、AD-8（用標準 `logging`，Page 層是領域例外的 catch 點，不用 structlog／utils_v2）。本 workspace 沒有 `utils_v2`，本 Change 也沒有可套用的 utils_v2 模組（不碰 Google Sheets，也不走 `init()`/`biz_job` 的批次入口）。

---

## 現況評估

### 目前的重跑成本與錯誤呈現（本 Change 要改的地方）

| 項目 | 現況 | 位置 |
|------|------|------|
| 連線存活檢查 | 每次整頁重跑都執行 `ensure_schema()`（6 個 CREATE、4 個 PRAGMA、1 次 commit，約 11 次往返）；重連時再跑 2 次，約 22 次 | `bootstrap._with_reconnect_on_stale_stream` |
| 讀取 | 沒有任何讀取快取，各頁每次重跑查 3～8 次；同一次重跑內有完全相同的重複查詢（總覽 `list_holdings` 2 次、資產配置 `read_month(latest)` 2 次、報酬率「自開始記錄」時 `read_range` 2 次） | `views/*.py` |
| 月度錄入 | 每個金額欄失焦就整頁重跑；存檔後 `st.rerun()` 再整頁重跑一次 | `views/input.py` |
| 重連保護 | 只有 `app.py` 整頁重跑的入口有。買房勾選的 `on_change` callback 在腳本主體之前執行，用的是上一輪抓住的 repo，沒有重連保護 | `views/house.py:211-232` |
| 錯誤呈現 | 各頁只 catch `AssetLabError`；其他例外交給 Streamlit 預設處理，`client.showErrorDetails` 本機預設 `full`、雲端是舊版 `False`（等同 `stacktrace`），都會露出堆疊 | 全站 |
| 設定頁寫入 | 門檻 3 筆、買房參數 9 筆，每筆各自 commit；中途失敗會留下部分寫入，而且露出 libsql 原生錯誤 | `views/settings.py:294-407` |
| Logging | 專案沒有設定任何 handler，INFO 全部被丟掉（AD-8 說要在 bootstrap 設定 level，實際沒做）；頁面 logger 名稱一律是 `__main__` | 全站 |

### 沿用的既有慣例

| 慣例 | 出處 | 本 Change 怎麼用 |
|------|------|------------------|
| Page = Controller/View，是領域例外（`AssetLabError`）的 catch 點 | initial-build AD-2、AD-8 | 各頁既有的 `except AssetLabError` 不動；新增的入口邊界只是「最後防線」，不取代頁面的 catch |
| 多句寫入走 `write_transaction`，失敗時 rollback 並轉成 `PersistenceError` | simplify-non-stock-input AD-10 | 設定頁門檻與買房參數的整批寫入也走它（BR-7） |
| `@st.cache_resource` 持有連線與容器；`bootstrap` 是組裝根，下層不讀 `st.secrets` | initial-build AD-1、AD-7 | 讀取快取、查詢計數器、「建表一次」都用獨立的 `cache_resource` 持有，生命週期與連線脫鉤 |
| 重連：以訊息含 `stream not found` 判斷，最多重試一次 | initial-build AD-1（t16）、SC-042 | 結構不變，只把探測從 `ensure_schema` 換成 `ping` |
| `build_container` 是純組裝（沒有 I/O、沒有 `st.*`），可獨立測試 | initial-build AD-1 | 連線分層也在這裡組裝，測試直接注入記憶體 DB 與假時鐘 |
| 頁面從 `st.session_state["container"]` 取容器（`_container()`） | 全部 views | 不變；fragment 與 callback 入口負責把已驗證的容器寫回同一個 key |
| 業務常數在 `constants.py`，用巢狀 class | 03-data-config §2 | 快取時效、log level、錯誤細節開關都放這裡（專案沒有 `config.yml`，屬 AD-1/AD-8 既有偏離） |

### 偏離既有做法的地方（各有 ADR）

- **Repository 底下多一層連線包裝**（AD-1、AD-2、AD-6）：Repository 拿到的連線改成「計數層＋快取層」包住的 libsql 連線，Repository 本身的程式碼不變。
- **頁面 logger 改用明確名稱**（AD-7）：偏離 04-cross-cutting §1.1 的 `getLogger(__name__)`，因為 Streamlit 頁面的 `__name__` 一律是 `__main__`。
- **入口邊界 catch `Exception`**（AD-8）：initial-build AD-8 規定 Page 是唯一 catch 點。本 Change 在 `app.py` 與 fragment／callback 入口加一層最後防線，只處理頁面沒接住的未預期例外，不改變頁面處理領域例外的方式。
- **`app.py` 讀取專案自己的環境變數**（AD-8）：比照 main 合約「入口讀取環境差異值後注入」的定位。
- **新增兩個 Streamlit runtime 黏合模組**（AD-5、AD-8、AD-9、AD-10）：`rerun_runtime.py`、`error_boundary.py`，與 `bootstrap.py`、`amount_widget.py` 同樣放在套件根目錄，不放 `core/`（core 必須純粹），也不放 `services/`（Service 不碰 Streamlit）。

---

## 架構決策

### AD-1：讀取快取放在連線層，做成 read-through，對 Repository 以上透明（Q1）

- **背景**：頁面大量直接呼叫 Repository（02 §1 允許），只有 `MonthlyInputService` 經 Protocol 讀資料。快取如果放在 Service 層，大部分讀取根本不會經過。快取的位置也決定 BR-2（寫入後立即反映）與 BR-6（快取只改何時讀，不改讀到什麼）靠什麼保證。
- **選擇**：方案 C。在 libsql 連線外包一層 `CachingConnection`／`CachingCursor`（裝飾器模式），由 `build_container` 組裝後注入各 Repository。
  - `SELECT` 開頭的語句（去掉前導空白後、不分大小寫）以 `(sql, tuple(parameters))` 為鍵，快取取回的 rows（`list[tuple]`）。參數不是 tuple 或 list 時直接透傳、不快取。
  - 其他語句一律透傳到內層，並標記「有未 commit 的寫入」（見 AD-2）。
  - 命中時，cursor 把快取的 rows 複製到自己的緩衝區（`list(rows)`），之後的 `fetchall`／`fetchone` 都從緩衝區讀。未命中時立刻 `fetchall` 取回全部 rows。
  - **只提供目前 Repository 用到的介面**：連線的 `cursor()`、`commit()`、`rollback()`；cursor 的 `execute()`、`fetchall()`、`fetchone()`、`lastrowid`。不用 `__getattr__` 轉發，所以以後有人用到 `description`、`fetchmany`、`executemany`、迭代等介面時，會直接拋 `AttributeError`，不會默默拿到錯的結果。
  - Repository 每次都用 rows 重新組出 Model 或 DataFrame，跟現在一樣。
- **理由**：
  - Repository、Service、Page 的程式碼都不用改，符合 02 §2 維度 C「技術迭代（重試、連線管理）由 I/O 層內部處理、對上層透明」。
  - BR-6 有結構上的保證：快取的是資料庫回傳的不可變 tuple，下游每次拿到的都是新組出的物件，不可能因為某個 Service 或 Page 原地改了 DataFrame 而污染快取（現有 Model 都不是 frozen）。
  - 所有讀取入口都涵蓋：Page 直接讀、Service 經 Protocol 讀、fragment、callback。
  - 清除點只有一個（AD-2），以後新增的寫入方法只要照慣例 commit，就自動會清快取。這是失敗安全的設計。
- **否決方案**：
  - **方案 R：每個 Repository 包一個快取版本**：要包 6 個 repo、12 個讀取方法；回傳的是可變物件，必須深拷貝才能守住 BR-6；清除要散在每個寫入方法上，以後新增寫入方法忘了包就會讀到舊資料，BR-2 只能靠紀律維持。
  - **方案 S：各頁用 `st.cache_data`**：快取與清除散在 8 個頁面（Big Ball of Mud）；要用 `_repo` 參數略過雜湊，快取鍵不含連線，測試之間會互相污染；TTL 沒辦法用假時鐘測。
  - **方案 V：整庫讀成記憶體快照，月份與區間篩選改在 Python 做**：改變了「怎麼讀」（BETWEEN、排序、NULL 語意從 SQL 搬到 Python），BR-6 風險高、改動面大，屬於過早優化。
  - **依資料表細分清除**：資料量是個人等級，整批清掉再讀的成本很小；細分只會多出錯的機會。
  - **Turso embedded replica**：proposal 明確排除。
- **後果**：
  - 正面：改動集中在連線層與組裝根；Repository 測試完全不受影響；查詢計數可以放在它下面，「真的打到資料庫的次數」就是量測要的數字（AD-6）。
  - 負面：讀 Repository 的人看不出有快取，必須在 `connection_layers.py` 與 `bootstrap.build_container` 的 docstring 寫清楚；語句分類靠 `SELECT` 前綴，`WITH … SELECT` 這類 CTE 會被當成寫入透傳（目前沒有任何 CTE）；Repository 的型別提示仍寫 libsql 的 `Connection`，包裝層是結構上的替身（見技術債）。

### AD-2：commit 成功是唯一清除點；有未 commit 的寫入時讀取繞過快取；用世代計數擋住競態寫回（BR-2）

- **背景**：BR-2 要求「寫入成功才清除；寫入失敗不清除」。全專案所有寫入路徑（月度錄入兩個批次方法、CSV 匯入、設定頁、買房勾選）最後都會呼叫連線的 `commit()`（architecture-brief §1.3 盤點）。另外，Streamlit 每個 session 在自己的執行緒跑腳本，所有 session 共用同一條連線與同一份快取，多分頁同時操作時會有競態。
- **選擇**：
  1. **清除**：`CachingConnection.commit()` 先呼叫內層 commit，**成功之後**才清空快取並推進世代。commit 拋錯時不清（BR-2）。以「每次 commit」為粒度：設定頁新增項目後，同一輪後面的讀取就是冷讀取，下一輪也一樣。
  2. **寫入進行中繞過快取**：`CachingConnection` 自己記一個「有未 commit 的寫入」旗標。執行非 `SELECT` 語句**之前**就設為真（執行失敗也維持為真）；commit 成功或 rollback 成功時才設回假。旗標為真時，`SELECT` 直接打資料庫，結果不寫回快取。不依賴 libsql 的 `in_transaction`，因為遠端 Hrana 下的準確度沒有驗證過，而且旗標必須在內層執行之前就成立，才擋得住「別的執行緒讀到還沒 commit 的資料」。
  3. **世代計數**：未命中時先記下目前的世代，查詢回來後，只有在「旗標仍為假、世代沒變」時才寫回快取。commit 成功（清除）與 rollback（不論成敗）都會推進世代；rollback 只推進世代、**不清除既有項目**（BR-2：失敗不清除）。這樣「寫入前發出、寫入後才回來」或「讀到別的執行緒最後被 rollback 的資料」的查詢結果都不會被寫回並保留 5 分鐘。
- **理由**：清除點收斂在一個地方，而且失敗安全；BR-2 的字面要求（成功才清、失敗不清）直接對應 commit 的成敗。旗標與世代都是幾行程式，換來多分頁下的正確性。
- **否決方案**：
  - **寫入前先清**：失敗時也會清，違反 BR-2 字面要求。
  - **在每個 Repository 寫入方法上清**：等於方案 R，失敗不安全。
  - **依賴 libsql 的 `in_transaction`**：本機 `:memory:` 實測 DML 後為真、commit 後為假，但遠端 Hrana 沒有驗證；而且它只能在內層執行之後才反映，擋不住上述競態。
- **後果**：
  - 正面：BR-2 有結構保證；callback 裡的寫入（買房勾選）也會清，下一輪讀到新值。
  - 負面：單句寫入（設定頁新增項目等）如果 execute 失敗、又沒有人呼叫 rollback，旗標會維持為真，直到下一次 commit 或 rollback 為止。這段期間所有讀取都繞過快取，只影響速度、不影響正確性（列為技術債）。

### AD-3：快取存放用自建 `ReadCache`，程序級、跨 session 共用；整批過期，在每次執行的入口判定（BR-3）

- **背景**：BR-3 要求另一處改了資料後，這裡最慢 5 分鐘內看到，並提供「重新讀取資料」按鈕。快取的生命週期要不要跟連線綁在一起、過期要逐筆判還是整批判，都會影響一致性與可測性。
- **選擇**：
  - 新增純 Python 的 `ReadCache`（不 import streamlit）：建構子注入 TTL 秒數與時鐘（預設 `time.monotonic`），內部用 `threading.Lock` 保護，提供 get／put（帶世代）／clear／fence／expire_if_stale。
  - 由 `bootstrap.get_read_cache()`（獨立的 `@st.cache_resource`）持有，**重連時不清**。資料是否有效跟連線無關，重連後不用全部重讀。
  - TTL 從「上次清除後第一筆寫入快取」起算。**只在每次執行的入口判定**（`verified_container()` 第一次被呼叫時，見 AD-5），超過就整批清除；同一次執行內不做逐筆過期判斷。
  - TTL 5 分鐘是 BR-3 的業務值，放 `constants.READ_CACHE.TTL_SECONDS`，由 bootstrap 注入。
  - 側欄新增「重新讀取資料」按鈕，`on_click=bootstrap.clear_read_cache`。callback 在腳本主體之前執行，所以按下後的那一輪就是冷讀取。
- **理由**：
  - 整批過期保證同一次執行看到一致的快照。如果逐筆各自過期，同一頁可能主檔是 4 分鐘前的、紀錄是剛讀的，對 BR-6 不利。
  - 程序級共用：允許清單裡只有使用者本人，所有頁面都在登入守門之後才讀資料，不會外洩。本機與雲端各自一個程序、各自一份快取，正好對應 BR-3 例外欄。
  - 自建 store 可以注入假時鐘測 TTL，也能直接表達「依 SQL 鍵存取、由 commit 觸發清除」的語意。
- **否決方案**：
  - **`st.cache_data`**：TTL 無法用假時鐘測；非 runtime 下是程序全域，測試會互相污染；每次命中都要 pickle 往返；語意不合，硬套是 Golden Hammer。
  - **快取跟著容器（`get_container` 的 `cache_resource`）走**：重連會連快取一起丟，重連後的那一輪變成全部冷讀取，沒有必要。
  - **逐筆 TTL**：會出現同一頁新舊資料混雜，否決。
- **後果**：
  - 正面：快取的正確性與 Streamlit 無關，可以完整單元測試。
  - 負面：「重新讀取資料」會清掉整個程序的快取（其他分頁下一輪也是冷讀取），成本可以忽略。快取沒有容量上限，靠 TTL 與 commit 清除控制大小，個人資料量下不成問題。

### AD-4：需要讀最新資料的例外點只有 CSV 匯入守門（BR-8、Q2）

- **背景**：快取把資料的有效窗口從「同一次重跑的幾毫秒」拉長到「最多 5 分鐘」。有兩類讀取不只是拿來顯示：CSV 匯入前的「資料庫必須是空的」守門條件（破壞性操作），以及月度錄入存檔前推算鏈用的 `read_holding_records`。
- **選擇**：
  - `views/data_io.py` 的「執行匯入」按鈕加上 `on_click=bootstrap.clear_read_cache`。callback 在重跑前執行，所以這一輪的匯出區塊與守門讀取都是從資料庫重新讀；守門讀取與同一輪匯出區塊的查詢相同，會命中這一輪剛讀進來的資料，仍然是最新的。
  - 月度錄入存檔**沿用快取**，不另外清。使用者已接受跨裝置 5 分鐘內的覆蓋風險（proposal「已接受的風險」）。
- **理由**：匯入守門被繞過的後果是資料被整批覆蓋，不能接受；月度錄入的使用者是同一個人，風險由使用者決定接受。
- **否決方案**：
  - **容器另外提供「不經快取」的 repo 給特定讀取用**：介面膨脹，每個呼叫點都要選對 repo，否決。
  - **所有寫入按鈕都先清快取**：使用者已在 Q2 決定只做匯入守門。
- **後果**：匯入那一輪多付一次冷讀取（3～5 次往返），可以忽略。月度錄入的跨裝置覆蓋風險列入技術債。

### AD-5：連線檢查改成「建表每個程序一次＋每次執行最多探測一次」；fragment 與 callback 入口也要驗證（BR-1、Q3、Q4）

- **背景**：`ensure_schema()` 同時負責建表遷移與存活探測，每次重跑約 11 次往返。只有 `app.py` 主體有重連保護，fragment 重跑不經過 `app.py`，`on_change` callback 又在 `app.py` 主體之前執行，兩條路徑都沒有保護。成功標準要求「每次重跑用於連線檢查的往返最多 1 次」。
- **選擇**：
  1. **建表每個程序只做一次**：新增 `@st.cache_resource ensure_schema_once()`，與 `get_container` 分開，**重連時不清**。重連只清連線與容器，不重新建表。
  2. **便宜的探測**：新增 `ConnectionHealthRepository.ping()`（`SELECT 1`）。探測與建表的 Repository 注入的是**計數層、不經快取**的連線；否則探測會永遠命中快取，形同失效。
  3. `_with_reconnect_on_stale_stream` 結構不變，改成「`ensure_schema_once()` → `health_repo.ping()`」，兩者都在同一個 try 內；偵測到 `stream not found` 時清連線與容器兩層快取、呼叫 `on_reconnect`（記 WARNING、在量測標記已重連），再取容器、再驗證一次。重試上限仍是 1（BR-1）。
  4. **每次執行最多探測一次**：在 `rerun_runtime.py` 新增 `verified_container()`。它在同一次執行內（同一個腳本執行緒）只呼叫一次 `bootstrap.get_resilient_container()`，結果暫存在執行緒區域的狀態裡，並寫入 `st.session_state["container"]`；同時在第一次呼叫時做快取 TTL 判定（AD-3）。暫存值在最外層 `rerun_scope` 結束時清掉（AD-6）。
  5. 三個入口都改呼叫 `verified_container()`：
     - `app.py` 主體（取代直接呼叫 `get_resilient_container()`）；
     - fragment 入口（AD-9）：整頁重跑時 `app.py` 已經驗證過，直接拿暫存值，不再探測；fragment 單獨重跑時才探測 1 次（Q3 P1）；
     - 買房勾選 callback（AD-10）：callback 先驗證並暫存，接下來 `app.py` 主體直接拿暫存值，整輪仍只探測 1 次。
- **理由**：
  - 依 Streamlit 1.66.1 原始碼（`script_runner.py` 的 `code_to_exec`），widget callback 與腳本主體在同一個執行緒、同一次 `code_to_exec` 內依序執行，所以執行緒區域的暫存可以讓 callback 與 `app.py` 共用同一次驗證結果。
  - 每次正式執行都會經過一個最外層 `rerun_scope`（整頁重跑是 `app.py`，fragment 單獨重跑是 fragment 裝飾器），暫存值在那裡清掉，不會跨次殘留。
- **否決方案**：
  - **P3 自我修復連線 proxy**（閒置超過門檻才探測，失效就在 proxy 內換掉底層連線，快取命中時 0 次往返）：要處理交易中途換連線、cursor 重新綁定，閒置門檻又取決於還沒量測的 stream 過期時間，測試面大。先用 P1 拿到量測數據，若重連頻繁或探測佔比明顯，再另案處理。
  - **fragment 入口用 Streamlit 內部的 `fragment_ids_this_run` 判斷是否為 fragment 單獨重跑**：依賴未公開 API；用自己的暫存值判斷就夠了。
  - **callback 內直接呼叫 `get_resilient_container()`、不做暫存**：勾選那一輪會探測 2 次，不符合成功標準。
  - **把探測加在 `SchemaRepository`**：建表與探測職責不同，拆開較清楚（單一職責）。
- **後果**：
  - 正面：一般重跑 1 次往返；重連約 2 次往返加上建立連線；fragment 與 callback 都有重連保護（BR-1 例外欄）。
  - 負面：程序啟動後的第一輪仍要建表（約 11 次往返，只一次）；`views/input.py` 的 AppTest 會因為 fragment 入口呼叫 `bootstrap.get_resilient_container()` 而需要替身（見「受影響的既有測試」）。

### AD-6：量測——計數層放在快取之下，每次執行只由最外層記一行；先補上 logging 設定（Q5、Q7）

- **背景**：proposal 要求每次重跑在 log 記一行耗時與資料庫查詢次數，畫面不變；改前改後比較；查詢次數要能用自動化測試驗證。目前 INFO log 根本不會輸出（沒有 handler）。
- **選擇**：
  1. **logging 設定**：`bootstrap.configure_logging()` 在 `asset_lab` 這個 logger 上掛一個輸出到 stderr 的 `StreamHandler`，level 與格式來自 `constants.APP_LOGGING`。以 handler 名稱判斷是否已掛過，所以每次重跑呼叫都安全（冪等）。root logger 不動；`asset_lab` 的 `propagate` 維持預設的 True，pytest 的 `caplog`（掛在 root）才收得到（既有 SC-085／SC-107 測試依賴這點）。Streamlit 只設定自己的 `streamlit` logger（`propagate=False`），root 沒有 handler，不會重複輸出。雲端的 Manage app → Logs 會收到 stderr。
  2. **計數層 `CountingConnection`／`CountingCursor`**：放在快取層之下，把每次 `execute`、`commit`、`rollback` 都算成一次往返（與 proposal「約 11 次」的算法一致）。`cursor()` 與 `fetch*` 不算。計數寫進 `QueryMetrics`。
  3. **`QueryMetrics`**：每個執行緒各自累計（`threading.local`），避免多個 session 的數字混在一起；另外保留一個加鎖的程序累計往返數，給測試用差值斷言（AppTest 在另一個執行緒跑腳本）。也記快取命中次數與是否重連。由 `bootstrap.get_query_metrics()`（獨立 `cache_resource`）持有，重連時不清。
  4. **`rerun_scope`**：可巢狀的計時 context，執行緒區域記錄深度。只有最外層離開時才「讀取並歸零」本執行緒的計數、記一行 INFO、清掉 AD-5 的容器暫存。整頁重跑時 `app.py` 是最外層，裡面的 fragment 不重複記；fragment 單獨重跑時 fragment 裝飾器就是最外層，記一行 `kind=fragment`。因為是在**結束時**歸零，callback 在腳本主體之前產生的往返會算進同一行。
  5. log 行格式見「介面契約 §10」。欄位不含 email 或任何個資（sensitive-data-guard）。
- **理由**：計數層在快取之下，數字就是真的打到資料庫的次數，可以直接用在自動化測試；最外層才記錄，保證一次執行一行。
- **否決方案**：
  - **計數層放在快取之上**：命中也會被算進去，量不到優化效果。
  - **在 `rerun_scope` 開始時歸零**：callback 在腳本主體之前產生的往返（例如買房勾選的寫入）會不見。
  - **用 `contextvars`**：Streamlit 每個 session 的腳本跑在自己的執行緒，`threading.local` 就足夠，也比較好理解。
- **後果**：
  - 正面：量測與自動化測試共用同一份計數；log 一行就能看出快取有沒有生效（`db_roundtrips` 與 `cache_hits`）。
  - 負面：耗時只量伺服器端腳本執行時間，不含網路與瀏覽器繪製，使用者感受到的等待會比這個數字長（列入技術債）；計數是「往返」的近似值，遠端 libsql 的 `cursor()` 是否有往返未驗證。

### AD-7：頁面 logger 改用明確名稱，偏離 `getLogger(__name__)`（Q7）

- **背景**：04-cross-cutting §1.1 規定 `logger = get_logger(__name__)`。Streamlit 以 `__main__` 模組名執行頁面腳本（`streamlit/navigation/page.py`），所以 8 個頁面的 logger 名稱全都是 `__main__`：log 裡分不出是哪一頁，而且不在 `asset_lab` 底下，AD-6 掛的 handler 收不到它們的 INFO。
- **選擇**：`views/*.py` 一律改成 `logger = logging.getLogger("asset_lab.views.<頁面檔名>")`（例如 `asset_lab.views.input`、`asset_lab.views.data_io`），仍在模組頂層宣告、不經建構子注入。`src/asset_lab/` 底下的套件模組維持 `getLogger(__name__)`，因為它們的 `__name__` 本來就是 `asset_lab.*`。log level 放 `constants.APP_LOGGING.LEVEL`。
- **理由**：照規則寫 `__name__` 在 Streamlit 頁面裡沒有意義；明確名稱保留了規則的目的（看得出來源、可依層級設定 level）。
- **否決方案**：
  - **維持 `__name__`**：log 無法區分頁面，INFO 也收不到，否決。
  - **用 `APP_LOGGING.LOGGER_NAMESPACE` 拼接名稱**：多一層間接，可讀性變差；改用結構測試確保每個頁面的 logger 名稱都以 `asset_lab.views.` 開頭即可。
- **後果**：3-3 規則符合度審查以本 ADR 為偏離依據；頁面檔改名時要記得同步 logger 名稱（結構測試會擋）。

### AD-8：全站錯誤兜底分四層，錯誤細節用專案環境變數開關（BR-5、Q6）

- **背景**：Streamlit 的設定優先序是「config.toml < 環境變數 < 命令列參數 < 腳本內 `st.set_option`」。Community Cloud 仍使用舊版 `showErrorDetails=False`（等同 `stacktrace`），只改 `config.toml` 不保證雲端生效。另外，fragment 內拋出的例外會先由 Streamlit 顯示，再改拋 `FragmentHandledException`，外層接不到原例外；`st.exception()` 不受 `showErrorDetails` 管制，永遠顯示完整堆疊。
- **選擇**：

  | 層 | 機制 | 涵蓋 |
  |----|------|------|
  | L0 | 新增 `.streamlit/config.toml`：`[client] showErrorDetails = "none"` | 腳本還沒跑到 `set_option` 之前的錯誤（例如 import 失敗） |
  | L1 | `app.py` 每次執行一開始就 `st.set_option("client.showErrorDetails", 模式)`；模式由環境變數 `ASSET_LAB_SHOW_ERROR_DETAILS` 決定（值去空白、轉小寫後在 `{"1","true","yes","on"}` 內才是 `full`，其他一律 `none`） | Streamlit 預設處理的所有未捕捉例外，包括 callback 與 fragment |
  | L2 | `app.py` 主體包在 `error_boundary(context="app")` 內 | 整頁重跑中頁面沒接住的未預期例外 |
  | L3 | fragment 入口（AD-9）與 widget callback 入口（AD-10）各自的邊界 | fragment 單獨重跑、callback |
  | 既有 | 各頁 `except AssetLabError` 轉友善訊息 | 領域例外，不動 |

  `error_boundary` 的行為：
  - `FragmentHandledException`：原樣往上拋（Streamlit 已經顯示並記錄過，不重複）。
  - `AssetLabError`：`logger.exception(...)`，畫面 `st.error(str(error))`（領域例外的訊息本來就是給使用者看的）。
  - 其他 `Exception`：開關**關閉**時，`logger.exception(...)` 後畫面只顯示 `UNEXPECTED_ERROR_MESSAGE`；開關**開啟**時原樣往上拋，交給 Streamlit 以 `full` 模式顯示完整錯誤。
  - `BaseException`（`st.stop()`、`st.rerun()` 的控制例外）不攔截。
  - 開關是否開啟由 `st.get_option("client.showErrorDetails") == "full"` 判斷，也就是以 L1 設定的值為唯一依據，邊界本身不讀環境變數。
- **理由**：
  - L1 優先序最高，是雲端的主防線；L0 是縱深防禦。開關必須用專案自己的環境變數，因為 Streamlit 原生的 `--client.showErrorDetails` 會被 L1 蓋掉。
  - 開發模式改成「原樣往上拋」，讓 Streamlit 用它自己的完整錯誤畫面顯示，不必呼叫 `st.exception`（它不受設定管制，容易在雲端誤露）。
  - 錯誤細節開關由 `app.py` 讀環境變數，符合 main 合約「入口讀取環境差異值」的定位；下游只讀 Streamlit 的設定值。
- **否決方案**：
  - **`st.App(on_script_error=...)`**：可以一次統一腳本、callback、fragment 的錯誤處理，但要把入口改成 Starlette App 物件，Community Cloud 是否支援沒有驗證，風險與範圍不成比例。等雲端確認支援後再評估。
  - **只靠 `config.toml`**：雲端可能不生效。
  - **只靠 L2**：漏掉 fragment 與 callback。
  - **開發模式呼叫 `st.exception(error)`**：它不受 `showErrorDetails` 管制，判斷寫錯就會在雲端露出堆疊；原樣往上拋更安全。
- **後果**：
  - 正面：雲端任何未預期錯誤都只看到中文通用訊息，細節在伺服器 log；本機設環境變數即可看完整錯誤。
  - 負面：`FragmentHandledException` 來自 `streamlit.errors`，不是文件化的公開 API，升級 Streamlit 時可能變動（列入技術債，由測試把關）；`st.set_option` 是程序全域設定，測試要在 fixture 還原；雲端 Secrets 的頂層鍵會變成環境變數，README 必須寫明雲端不得設定這個鍵。

### AD-9：月度錄入編輯器改為 fragment；專案共用的 `rerun_fragment` 裝飾器（BR-4、Q8）

- **背景**：月度錄入頁每個金額欄失焦就整頁重跑。`st.fragment` 可以讓編輯器自己重跑，但有三個陷阱：fragment 內拋出的例外外層接不到（上一個 Change 的友善訊息會失效）；fragment 單獨重跑時 `app.py` 的計時、連線檢查、錯誤邊界都不在呼叫堆疊上；fragment 重跑沿用的是上一次整頁重跑時傳入的參數。接下來的城市總覽元件也會用到 fragment。
- **選擇**：
  - 在 `rerun_runtime.py` 新增 `rerun_fragment(*, label)` 裝飾器，由外到內組合：`st.fragment` → `rerun_scope(kind="fragment", page=label)` → `error_boundary(context=label)` → `verified_container()` → 原函式。內部的 wrapper 用 `functools.wraps` 保留原函式的 `__module__`／`__qualname__`（Streamlit 以此計算 fragment id）。
  - `views/input.py` 的 fragment 範圍（architecture-brief 方案 F1）：
    - **fragment 內**：「單列錄入」小標題、「項目」下拉、四種編輯器、推算預覽、儲存與刪除按鈕。
    - **fragment 外**：年月下拉、「帶入上月仍持有項目」按鈕、本月已存紀錄表格、flash 訊息。改年月本來就該整頁重跑。
  - fragment 函式只接收穩定的識別值 `target_ym: str`。容器、holdings、month_records、holding_records 都在 fragment 內自己取得與讀取（走快取）；不把 container、repo 或資料清單當參數傳進去，因為 fragment 單獨重跑時沿用的是上一次的參數，物件可能已經過時。
  - `AssetLabError` 的處理由裝飾器的 `error_boundary` 在 fragment 內完成，畫面呈現與現在相同（`st.error(str(error))`）。
  - 存檔或刪除成功後維持 `st.rerun()`（預設 scope 為整個 app），因為表格與 flash 在 fragment 外，必須整頁更新。
- **理由**：把 §1.7 的陷阱封裝在一個地方，月度錄入與之後的城市總覽共用，不必每個 fragment 重新踩一次。城市總覽已在 roadmap 上，所以直接抽出。
- **否決方案**：
  - **方案 F2：表格也放進 fragment，存檔改成只重跑 fragment**：可以省一次整頁重跑，但 flash 與表格位置要重排，改動面較大，proposal 沒要求。
  - **直接在 `views/input.py` 寫 `@st.fragment`，各自處理連線、錯誤、量測**：城市總覽會再寫一次，容易漏掉其中一項。
- **後果**：
  - 正面：修改金額欄只重跑編輯器，預覽仍即時更新（BR-4）；fragment 單獨重跑時也有連線驗證、錯誤兜底與量測。
  - 負面：AppTest 的 widget 互動看起來一律觸發整頁重跑（architecture-brief Q8，未完整查證），「只有編輯器重跑」無法用 AppTest 直接觀察；驗證改用結構斷言、在沒有外層 scope 的情況下直接跑頁面（此時 fragment 就是最外層，走的正是 fragment 單獨重跑的路徑），以及 2-Z／上線時看 `kind=fragment` 的 log 行。`st.fragment` 在 Streamlit runtime 之外呼叫會直接回傳 None、不執行函式，所以 fragment 本體只能在 AppTest 裡跑。

### AD-10：widget callback 的重連與錯誤處理：`guarded_callback` 裝飾器（BR-1 例外欄、Q4）

- **背景**：買房頁的主觀勾選在 `on_change` callback 內寫入，用的是上一輪透過 `kwargs` 抓住的 repo，閒置後連線失效時不會重連；callback 拋出的例外只有 L0／L1 保護，畫面顯示 Streamlit 的英文通用訊息，而且整輪腳本被中止，頁面不會渲染。使用者決定這次修。
- **選擇**：
  - 在 `error_boundary.py` 新增 `guarded_callback(*, context)` 裝飾器：
    - `AssetLabError`：記 log，把 `str(error)` 暫存到 `st.session_state[CALLBACK_ERROR_SESSION_KEY]`；
    - 其他 `Exception`：開關關閉時記 log、暫存 `UNEXPECTED_ERROR_MESSAGE`；開關開啟時原樣往上拋；
    - 不攔截 `BaseException`。
  - 新增 `show_callback_error()`：取出並清掉暫存訊息，有的話 `st.error(...)`。由註冊 guarded callback 的頁面在標題下方呼叫（本 Change 只有買房頁）。
  - `views/house.py`：
    - callback 的 `kwargs` 只傳 `trigger_key` 與 `widget_key`，**不再傳 repo**；
    - callback 內呼叫 `verified_container()` 取得已驗證的容器，再用 `container.subjective_trigger_repo` 寫入；
    - `_render_triggers` 與 `_render_subjective_checkbox` 不再接收 repo 參數。
- **理由**：callback 失敗時頁面照常渲染，訊息與全站一致是中文；重連沿用 AD-5 的同一套機制，整輪仍只探測一次。用 session_state 暫存訊息是本專案已有的做法（月度錄入的 flash），比在 callback 內直接輸出元素更好預測，也比較好測。
- **否決方案**：
  - **列為已知限制**：使用者在 Q4 決定這次修。
  - **在 callback 內直接 `st.error`**：callback 輸出的元素位置不固定，也不好測。
- **後果**：買房勾選寫入失敗時顯示通用訊息（`upsert_trigger` 是單句 commit，不會轉成 `PersistenceError`），勾選框的畫面狀態可能與資料庫不一致（既有行為，列入技術債）。

### AD-11：設定頁門檻與買房參數改為單一交易整批寫入（BR-7、Q9）

- **背景**：門檻 3 筆、買房參數 9 筆是逐筆 commit，中途失敗會留下部分寫入，而且失敗時露出 libsql 原生錯誤。頁面目前在迴圈裡組裝 (鍵, 值) 並逐筆呼叫 repo，屬於 Controller 內的資料轉換（02 §4 不允許）。
- **選擇**：
  - Repository 新增 compound method（02 §2 維度 B「整批成敗一致 → Service 或 Repository」）：
    - `ProtocolThresholdRepository.upsert_thresholds(*, thresholds)`；
    - `HouseParamRepository.upsert_params(*, params)`。
    兩者都用既有的 `write_transaction`：同一交易內逐筆 upsert、最後 commit 一次；任一步失敗就 rollback 並拋 `PersistenceError`；空清單不開交易。
  - Service 新增把輸入轉成 Model 清單的純方法（與既有 `effective_*` 互為反向）：
    - `ProtocolService.build_threshold_models(*, l1, l2, l3)`；
    - `HouseService.build_param_models(*, params)`。
  - `views/settings.py`：驗證 → Service 組清單 → Repository 整批寫入。失敗由頁面既有的 `except AssetLabError` 顯示 `PersistenceError` 的預設訊息「存檔失敗，資料未變更，請重試」。
  - 保留既有單筆方法 `upsert_threshold`／`upsert_param`：既有 SC 測試用它們播種資料，頁面不再使用。
- **理由**：沿用上一個 Change 建立的交易邊界與友善訊息，改動最小；資料轉換移到 Service，頁面只剩「呼叫 Service／Repository＋錯誤處理」。
- **否決方案**：
  - **在頁面持有 `transaction_repo.transaction()`，逐筆呼叫 `*_with_context`**：跨 Repository 才需要這樣（CSV 匯入）；同一張表的整批寫入用 compound method 較簡單。
  - **只處理「不露堆疊」、不改原子性**：使用者在 Q9 決定這次修。
- **後果**：一次 commit 只清一次快取；新增項目、改目標比重等其他單筆寫入維持原狀，失敗時顯示 AD-8 的通用訊息（見待確認事項 2）。

### AD-12：同一次重跑內完全相同的重複查詢交給快取去重，不改頁面程式

- **背景**：proposal 要求「去除同一次重跑內的重複查詢」。architecture-brief A10 建議在頁面層去重，理由是「存檔後的重跑是冷快取，重複查詢仍是實際往返」。
- **選擇**：不改頁面程式。快取以 `(sql, 參數)` 為鍵，同一次執行內第一次查詢未命中後就會寫回快取（沒有未 commit 的寫入、世代沒變），第二次完全相同的查詢就會命中，冷快取的那一輪也一樣。中間如果有 commit（例如設定頁存檔），第二次會重新讀，這正是正確行為。
- **理由**：architecture-brief A10 的前提不成立：冷快取時，完全相同的查詢只有第一次是真的往返。改頁面只會多出 diff 與回歸風險。
- **否決方案**：
  - **在資產配置、總覽、報酬率頁傳遞已讀資料**：收益為零（往返數相同），而且要改 Service 或 Page 的參數。
- **後果**：程式碼裡仍看得到重複呼叫，實際成本是記憶體讀取。資料相同但形狀不同的查詢（`read_all` 與 `read_range(最早..最新)`、總覽與買房頁重疊）不會去重，維持既有技術債 TD-8。驗證方式：冷快取的整頁重跑中，每個不同的查詢只算一次往返。

### AD-13：量測方式與交付順序（Q5）

- **背景**：proposal 要求先取得優化前的基準。main 會自動部署，使用者決定不做雲端基準、單次交付：查詢次數用自動化測試驗證，耗時在本機比較前後兩版。
- **選擇**：
  - **「改前」版本**：只含量測的 commit，也就是 logging 設定、`QueryMetrics`、`CountingConnection`、`rerun_scope` 接進 `app.py`、頁面 logger 改名。**不得**含快取、探測改法、fragment。這個 commit 必須能獨立執行。
  - **「改後」版本**：全部完成的 commit。
  - **量測流程**（由使用者登入操作，讀共用的 Turso 正式庫）：
    1. 本機 `streamlit run app.py`，開啟頁面後先完整載入一次總覽頁（第一輪含程序啟動的建表，不採計）。
    2. 以下四個動作各做 3 次，每次取對應的 log 行：
       - **切頁**：總覽 → 資產配置；
       - **改下拉選單**：報酬率頁的「區間」；
       - **改金額欄**：月度錄入某個活存項目的「餘額」欄，改值後離開欄位；
       - **存檔**：月度錄入以原本的值按「儲存此列」。存檔會產生兩行 log：存檔那一行（`interrupted=true`）加上接著的整頁重跑那一行，兩行相加算一次存檔。
    3. 每個動作取 3 次的中位數，記錄 `elapsed_ms` 與 `db_roundtrips`。
    4. 改後版本在 5 分鐘內完成（快取有效期間）。
  - **結果**寫進 `review.md`，表格欄位：動作、改前耗時、改前往返數、改後耗時、改後往返數、改後 `kind`。
  - 改前的量測可以在量測 commit 完成後立刻做，也可以最後用 `git checkout <量測 commit>` 回去量；兩種都可以，由使用者決定時機。
- **理由**：本機前後比較就能看出相對改善；查詢次數另有自動化測試，不依賴手動量測。
- **否決方案**：
  - **先部署只含量測的版本取雲端基準**：要兩階段交付，使用者已否決。
  - **AppTest 不經登入跑頁面量耗時**：只能量讀取，存檔會寫入正式庫，不能自動化。
- **後果**：本機往返延遲與雲端不同，數字只能做相對比較；proposal 不設硬性秒數目標，以前後比較為準。

---

## 技術選型

### TD-1：Streamlit 1.66.1 原生 `st.fragment`
- **推薦**：沿用已安裝的 Streamlit 1.66.1，使用 `st.fragment`（不帶 `run_every`、不帶 `parallel`）（信心度：High）
- **理由**：proposal 已列為可用；原始碼已查證例外處理（`runtime/fragment.py:768-782`）與 fragment id 的計算方式。不需要升級版本。

### TD-2：快取、計數、錯誤邊界都用標準庫自建，不用 `st.cache_data`／`st.App(on_script_error)`
- **推薦**：`threading.Lock`、`threading.local`、`time.monotonic`、`time.perf_counter`、`contextlib.contextmanager`、`functools.wraps`（信心度：High）
- **理由**：語意要求（依 SQL 鍵存取、commit 觸發清除、可注入假時鐘、每執行緒計數）用標準庫各幾十行就能表達，而且可以完整單元測試；兩個 Streamlit 現成方案的否決理由見 AD-3、AD-8。

### TD-3：標準庫 `logging`，在 `asset_lab` logger 上掛一個 stderr handler
- **推薦**：沿用 initial-build AD-8 的標準 `logging`，不導入 structlog／utils_v2（信心度：High）
- **理由**：本 workspace 沒有 utils_v2；Streamlit Community Cloud 的 Logs 會收 stderr。log 行用 `key=value` 格式，方便 grep 與量測（AD-6）。

### TD-4：不新增任何第三方依賴
- **推薦**：`pyproject.toml` 不變（信心度：High）
- **理由**：上述功能全部由 Streamlit 1.66.1、libsql 與標準庫提供。

---

## 介面契約

> 簽名是給 1-4／Phase 2 的契約；私有輔助函式由實作決定。所有建構子與 DI 參數一律 keyword-only。

### 1. 常數（`core/constants.py`，新增）

```python
class READ_CACHE:
    """讀取快取的時效（BR-3）：另一處的修改最慢在此秒數後的下一次操作反映。"""

    TTL_SECONDS = 300


class APP_LOGGING:
    """App 的 log 設定。專案沒有 config.yml（initial-build AD-1/AD-8 偏離），運維參數集中於此。"""

    LOGGER_NAMESPACE = "asset_lab"  # 專案 logger 共同前綴；頁面 logger 皆掛在其下（AD-7）
    LEVEL = "INFO"
    FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


class ERROR_DETAILS:
    """錯誤細節顯示開關（BR-5）。SHOW/HIDE 為 Streamlit client.showErrorDetails 的值。"""

    ENV_VAR = "ASSET_LAB_SHOW_ERROR_DETAILS"
    ENABLED_VALUES = frozenset({"1", "true", "yes", "on"})  # 比對前先去空白、轉小寫
    SHOW = "full"
    HIDE = "none"


class RERUN_KIND:
    """重跑量測 log 的重跑類型。"""

    FULL = "full"
    FRAGMENT = "fragment"
```

### 2. Repositories

#### 2.1 `repositories/read_cache.py`（新增）

```python
CacheKey = tuple[str, tuple[object, ...]]


class ReadCache:
    """程序級的查詢結果快取：整批過期、世代計數、執行緒安全；不依賴 Streamlit。"""

    def __init__(self, *, ttl_seconds: float, clock: Callable[[], float] = time.monotonic) -> None: ...
    def get(self, key: CacheKey) -> list[tuple] | None:
        """命中回傳快取的 rows（呼叫端不得修改）；未命中回傳 None。空清單是合法的命中值。"""
    def generation(self) -> int:
        """目前世代；未命中查詢前先取得，寫回時帶入。"""
    def put(self, key: CacheKey, rows: list[tuple], *, generation: int) -> bool:
        """世代仍等於 generation 才寫入並回傳 True；這是清除後第一筆時記下 TTL 起算時間。"""
    def clear(self) -> None:
        """清空全部項目、推進世代、重設 TTL 起算時間（commit 成功、重新讀取、TTL 到期）。"""
    def fence(self) -> None:
        """只推進世代、保留既有項目（rollback 時用，讓進行中的未命中查詢不寫回）。"""
    def expire_if_stale(self) -> bool:
        """距 TTL 起算時間已達 ttl_seconds 就 clear() 並回傳 True；只在每次執行的入口呼叫。"""
```

#### 2.2 `repositories/query_metrics.py`（新增）

```python
@dataclass(frozen=True)
class QueryMetricsSnapshot:
    """一次執行的量測值。"""

    db_roundtrips: int
    cache_hits: int
    reconnected: bool


class QueryMetrics:
    """每執行緒累計的查詢量測，加上程序累計往返數（測試用）；不依賴 Streamlit。"""

    def add_roundtrip(self) -> None: ...
    def add_cache_hit(self) -> None: ...
    def mark_reconnected(self) -> None: ...
    def take(self) -> QueryMetricsSnapshot:
        """讀取本執行緒累計值並歸零。"""
    def total_roundtrips(self) -> int:
        """程序啟動以來的總往返數（不歸零）；測試以前後差值斷言。"""
```

#### 2.3 `repositories/connection_layers.py`（新增）

```python
class DbCursor(Protocol):
    def execute(self, sql: str, parameters: Sequence[object] = ...) -> object: ...
    def fetchall(self) -> list[tuple]: ...
    def fetchone(self) -> tuple | None: ...
    @property
    def lastrowid(self) -> int | None: ...


class DbConnection(Protocol):
    def cursor(self) -> DbCursor: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...


class CountingConnection:
    """計數層：每次 execute／commit／rollback 記一次往返後轉給內層（失敗也算）。"""

    def __init__(self, *, inner: DbConnection, metrics: QueryMetrics) -> None: ...
    def cursor(self) -> "CountingCursor": ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...


class CountingCursor:
    def execute(self, sql: str, parameters: Sequence[object] = ()) -> "CountingCursor": ...
    def fetchall(self) -> list[tuple]: ...
    def fetchone(self) -> tuple | None: ...
    @property
    def lastrowid(self) -> int | None: ...


class CachingConnection:
    """快取層：SELECT read-through；commit 成功才清；有未 commit 的寫入時繞過快取（AD-1、AD-2）。

    只提供上列介面，不轉發其他屬性；用到未提供的介面會拋 AttributeError。
    """

    def __init__(self, *, inner: DbConnection, cache: ReadCache, metrics: QueryMetrics) -> None: ...
    def cursor(self) -> "CachingCursor": ...
    def commit(self) -> None:
        """內層 commit 成功 → cache.clear()、清除寫入旗標；失敗原樣往上拋、不清。"""
    def rollback(self) -> None:
        """不論成敗都 cache.fence()；成功才清除寫入旗標；失敗原樣往上拋。"""


class CachingCursor:
    def execute(self, sql: str, parameters: Sequence[object] = ()) -> "CachingCursor":
        """SELECT：無寫入旗標且命中 → 緩衝 rows、記一次命中；
        未命中 → 先取世代，內層 execute＋fetchall，旗標仍為假才 put。
        非 SELECT：先設寫入旗標，再轉給內層。"""
    def fetchall(self) -> list[tuple]: ...
    def fetchone(self) -> tuple | None: ...
    @property
    def lastrowid(self) -> int | None: ...
```

內層 cursor 只在需要打資料庫時才建立（命中時不建立）。

#### 2.4 `repositories/health_repository.py`（新增）

```python
class ConnectionHealthRepository:
    """連線存活探測。必須注入不經快取的連線（計數層），否則探測永遠命中。"""

    def __init__(self, *, conn: DbConnection) -> None: ...
    def ping(self) -> None:
        """執行 SELECT 1 並取回結果；失敗原樣往上拋（交由重連邏輯判斷）。"""
```

#### 2.5 既有 Repository（新增方法，其他不變）

```python
class ProtocolThresholdRepository:
    def upsert_thresholds(self, *, thresholds: list[ProtocolThresholdModel]) -> None:
        """單一交易內整批 upsert；空清單不開交易；任一步失敗 rollback 並拋 PersistenceError。"""


class HouseParamRepository:
    def upsert_params(self, *, params: list[HouseParamModel]) -> None:
        """同上。"""
```

兩者都用 `transaction_repository.write_transaction(self._conn)`，寫法比照 `RecordRepository.upsert_records`。既有單筆 `upsert_threshold`／`upsert_param` 保留。

### 3. Services（新增方法）

```python
class ProtocolService:
    def build_threshold_models(self, *, l1: float, l2: float, l3: float) -> list[ProtocolThresholdModel]:
        """依 L1、L2、L3 順序組出門檻 Model 清單（不驗證；驗證仍由 validate_thresholds 負責）。"""


class HouseService:
    def build_param_models(self, *, params: HouseParams) -> list[HouseParamModel]:
        """把 9 個參數組成 Model 清單（target_year、loan_years 轉 float），是 effective_params 的反向。"""
```

### 4. `bootstrap.py`

```python
@dataclass(frozen=True)
class Container:
    # ……既有欄位不變……
    health_repo: ConnectionHealthRepository  # 新增


def build_container(
    *, conn: DbConnection, read_cache: ReadCache, query_metrics: QueryMetrics
) -> Container:
    """純組裝（無 I/O、無 st.*）。連線分層的唯一組裝點：
    counted = CountingConnection(inner=conn, metrics=query_metrics)
    cached  = CachingConnection(inner=counted, cache=read_cache, metrics=query_metrics)
    schema_repo、health_repo ← counted（不經快取）；
    其他 Repository 與 TransactionRepository ← cached。
    """


@st.cache_resource
def get_connection() -> "Connection": ...          # 不變

@st.cache_resource
def get_read_cache() -> ReadCache: ...              # ttl_seconds=READ_CACHE.TTL_SECONDS；重連時不清

@st.cache_resource
def get_query_metrics() -> QueryMetrics: ...        # 重連時不清

@st.cache_resource
def get_container() -> Container:
    """build_container(conn=get_connection(), read_cache=get_read_cache(),
    query_metrics=get_query_metrics())；不再執行 ensure_schema。"""

@st.cache_resource
def ensure_schema_once() -> bool:
    """get_container().schema_repo.ensure_schema()，回傳 True；每個程序一次，重連時不清。"""


def clear_read_cache() -> None:
    """清除讀取快取（側欄「重新讀取資料」與匯入按鈕的 on_click 用），記一行 INFO。"""


def _with_reconnect_on_stale_stream(
    *,
    get_container: Callable[[], Container],
    ensure_schema_once: Callable[[], object],
    clear_connection_cache: Callable[[], None],
    clear_container_cache: Callable[[], None],
    on_reconnect: Callable[[], None],
) -> Container:
    """try: ensure_schema_once(); container.health_repo.ping()
    偵測到 stream not found → 清連線與容器快取 → on_reconnect() → 重取容器 → 再驗證一次；
    其他例外原樣往上拋；第二次仍失敗也原樣往上拋。"""


def get_resilient_container() -> Container:
    """以實際的 cache_resource 函式呼叫上式；on_reconnect 會 get_query_metrics().mark_reconnected()
    並記一行 WARNING。"""


def configure_logging(*, logger_name: str, level: str, fmt: str) -> None:
    """在 logger_name 上掛 stderr handler 並設 level；以 handler 名稱判斷，重複呼叫不會重複掛。
    不動 root，propagate 維持 True。"""


def ensure_logging_configured() -> None:
    """以 APP_LOGGING 常數呼叫 configure_logging。"""


def resolve_error_detail_mode(*, raw: str | None) -> str:
    """環境變數原始值 → ERROR_DETAILS.SHOW 或 ERROR_DETAILS.HIDE（純函式）。"""
```

### 5. `rerun_runtime.py`（新增，Streamlit runtime 黏合）

```python
CONTAINER_SESSION_KEY = "container"  # 由 app.py 移來；值不變


@dataclass
class RerunScope:
    kind: str
    page: str | None
    is_outermost: bool


@contextmanager
def rerun_scope(
    *, kind: str, metrics: QueryMetrics, page: str | None = None
) -> Iterator[RerunScope]:
    """可巢狀的計時區塊。最外層離開時（不論正常結束或被例外中斷）：
    metrics.take() → 記一行 INFO（§10）→ 清掉 verified_container 的本次暫存。
    不攔截任何例外。"""


def verified_container() -> Container:
    """本次執行第一次呼叫時：bootstrap.get_resilient_container() → bootstrap.get_read_cache().expire_if_stale()
    → 暫存；之後同一次執行直接回傳暫存值。每次呼叫都把結果寫入 st.session_state[CONTAINER_SESSION_KEY]。"""


def rerun_fragment(*, label: str) -> Callable[[F], F]:
    """st.fragment → rerun_scope(kind=RERUN_KIND.FRAGMENT, page=label,
    metrics=bootstrap.get_query_metrics()) → error_boundary(context=label) → verified_container() → 原函式。"""
```

`bootstrap.get_resilient_container` 與 `bootstrap.get_query_metrics` 一律在呼叫時透過模組屬性取用（不在 import 或裝飾時綁定），測試才能用 `mock.patch("asset_lab.bootstrap.…")` 替換。

### 6. `error_boundary.py`（新增，Streamlit runtime 黏合）

```python
UNEXPECTED_ERROR_MESSAGE = "發生未預期錯誤，請稍後再試"
CALLBACK_ERROR_SESSION_KEY = "callback_error_message"


def error_details_enabled() -> bool:
    """st.get_option("client.showErrorDetails") == ERROR_DETAILS.SHOW。"""


@contextmanager
def error_boundary(*, context: str) -> Iterator[None]:
    """FragmentHandledException 原樣往上拋；AssetLabError → log＋st.error(str(error))；
    其他 Exception → 開關關閉時 log＋st.error(UNEXPECTED_ERROR_MESSAGE)、開啟時原樣往上拋。
    不攔截 BaseException。"""


def guarded_callback(*, context: str) -> Callable[[F], F]:
    """widget callback 用：同 error_boundary 的分類，但不輸出元素，而是把訊息暫存到
    st.session_state[CALLBACK_ERROR_SESSION_KEY]。"""


def show_callback_error() -> None:
    """取出並清掉暫存訊息，有的話 st.error(...)。"""
```

log 一律 `logger.exception(...)`，訊息帶 `context`；畫面上的訊息不得內插原始錯誤。

### 7. `app.py`（入口）

執行順序（每次整頁重跑）：

1. 維持現有的 `ARROW_DEFAULT_MEMORY_POOL` 設定與 `st.set_page_config`（不變）。
2. `st.set_option("client.showErrorDetails", bootstrap.resolve_error_detail_mode(raw=os.environ.get(ERROR_DETAILS.ENV_VAR)))`。
3. `bootstrap.ensure_logging_configured()`。
4. `with rerun_scope(kind=RERUN_KIND.FULL, metrics=bootstrap.get_query_metrics()) as scope:`
   `with error_boundary(context="app"):`
   1. `_require_access()`（不變；守門之前不得讀資料、不得組容器，SC-033／034 的 fail-closed 契約）；
   2. `inject_amount_input_style()`；
   3. 側欄：已登入 email、「登出」、「重新讀取資料」（`on_click=bootstrap.clear_read_cache`）。放在取容器之前，資料庫故障時仍能登出；
   4. `verified_container()`（取代原本的 `bootstrap.get_resilient_container()` 與 session 寫入）；
   5. `navigation = st.navigation([...])`（頁面清單不變）；`scope.page = navigation.title`；
   6. `navigation.run()`。

`CONTAINER_SESSION_KEY` 改由 `rerun_runtime` 匯入。

### 8. Views

| 檔案 | 變更 |
|------|------|
| 全部 8 個 `views/*.py` | `logger = logging.getLogger("asset_lab.views.<檔名>")`（AD-7） |
| `views/input.py` | `_render_record_editor` 改為 `@rerun_fragment(label="月度錄入編輯器")`，簽名 `(*, target_ym: str) -> None`；在函式內取 `_container()`，讀 holdings、month_records，再依錄入方式分派四個編輯器（編輯器 helper 的簽名可以不變）。`render()` 只在頁面層讀 holdings、month_records 給本月表格用，呼叫位置維持在原本的 try 區塊內 |
| `views/house.py` | `render()` 在 `st.title` 之後呼叫 `show_callback_error()`；`_persist_subjective_trigger(*, trigger_key: str, widget_key: str)` 加上 `@guarded_callback(context="買房主觀勾選")`，內部用 `verified_container().subjective_trigger_repo`；`_render_triggers`、`_render_subjective_checkbox` 移除 repo 參數 |
| `views/data_io.py` | 「執行匯入」按鈕加 `on_click=bootstrap.clear_read_cache`（AD-4） |
| `views/settings.py` | 「儲存門檻」：`validate_thresholds` → `build_threshold_models` → `upsert_thresholds`；「儲存買房參數」：`validate_params` → `build_param_models` → `upsert_params`（AD-11） |

### 9. `.streamlit/config.toml`（新增，進版控）

```toml
[client]
showErrorDetails = "none"
```

不放任何機密。`.gitignore` 只排除 `secrets.toml`，這個檔會進版控。

### 10. log 行格式

```
重跑量測 kind=<full|fragment> page=<頁面或 fragment 標籤，未知時為 -> elapsed_ms=<整數> db_roundtrips=<整數> cache_hits=<整數> reconnected=<true|false> interrupted=<true|false>
```

- logger：`asset_lab.rerun_runtime`，level INFO。
- `interrupted`：最外層 scope 因例外離開時為 true，包括 `st.stop()`（例如登入守門擋下）與 `st.rerun()`（例如存檔後重跑）。
- 重連時另記一行 WARNING（logger `asset_lab.bootstrap`），訊息含「連線失效已重連」。
- 不得記錄 email 或任何個資。

### 11. README（交給 4-1）

要補充的內容：`ASSET_LAB_SHOW_ERROR_DETAILS=1 streamlit run app.py` 的開法；雲端（含 Secrets 的頂層鍵）不得設定此值；Streamlit 原生的 `--client.showErrorDetails` 會被程式覆蓋、無效；側欄「重新讀取資料」的用途與 5 分鐘時效；log 行各欄位的意義。

---

## 受影響的既有測試（交給 1-3／1-4）

| 測試 | 影響 |
|------|------|
| `tests/test_bootstrap.py::test_build_container_*` | `build_container` 簽名改變（多了 `read_cache`、`query_metrics`）；Repository 的 `_conn` 變成包裝層：schema_repo、health_repo 接計數層，其他接快取層 |
| `tests/test_bootstrap.py` SC-042（4 個重連測試） | 假容器從 `schema_repo.ensure_schema` 改為 `health_repo.ping`；新增參數 `ensure_schema_once`、`on_reconnect` 要傳替身；建議新增「重連不重新建表」「重連會呼叫 on_reconnect」的斷言 |
| `tests/test_input_view.py` | fragment 入口會呼叫 `verified_container()` → `bootstrap.get_resilient_container()`。`_run_app` 之後的每一次 `.run()` 都要有替身，建議用模組層級的 autouse fixture，把 `asset_lab.bootstrap.get_resilient_container` 換成「回傳 `st.session_state["container"]`」的函式。三個 `_FRIENDLY_WRITE_FAILURE` 斷言（SC-085／SC-100）是 catch 位置的回歸護欄，必須維持通過 |
| `tests/test_house.py` | `_render_triggers` 簽名變了；既有測試沒有點勾選框，預期不用改。新增勾選相關測試時要替換 `get_resilient_container` |
| `tests/test_app_guard.py`、`tests/test_page_config.py` | `app.py` 在守門之前新增 `set_option`、logging 設定、計時區塊，都不碰資料；SC-033／034／041 預期不用改，但必須維持通過 |
| `tests/test_data_io.py` SC-107 | 匯入按鈕的 `on_click` 會呼叫 `bootstrap.get_read_cache()`（`cache_resource`，不需要 secrets），預期不用改 |
| `tests/test_settings_view.py` | 既有測試沒有按「儲存門檻」「儲存買房參數」，預期不用改；新增測試時替身 repo 要提供 `upsert_thresholds`／`upsert_params` |
| 全部 | `st.set_option` 是程序全域設定，凡是跑 `app.py` 或修改這個設定的測試，fixture 要還原；`get_container`、`get_read_cache`、`get_query_metrics`、`ensure_schema_once` 是 `cache_resource`，跨測試共用時要 `.clear()` |

## 驗證方式建議（交給 1-3／1-4）

- **查詢次數（成功標準）**：用 `:memory:` libsql 加上真正的 `build_container` 分層與 `QueryMetrics`，以已登入的替身跑 `app.py` 的 AppTest（替換 `allowed_emails`、`st.user`、`get_connection`），比較兩次執行的 `total_roundtrips()` 差值：第二次應只剩 1 次探測。
- **快取語意**：`ReadCache` 用假時鐘測整批過期與世代；`CachingConnection` 測命中與未命中、commit 成功才清、commit 失敗不清、rollback 推進世代但保留項目、有未 commit 的寫入時繞過快取、未提供的介面拋 `AttributeError`、探測與建表不經快取。
- **BR-6**：同一個種子庫，經快取與不經快取的容器跑各 Service，輸出完全相同。
- **AD-12 去重**：冷快取的整頁重跑中，各個不同的查詢只算一次往返。
- **fragment（Q8）**：用 AST 斷言 `views/input.py` 的 `_render_record_editor` 帶有 `rerun_fragment` 裝飾器；直接用 AppTest 跑 `views/input.py`（此時 fragment 是最外層，等同 fragment 單獨重跑的路徑），驗查詢數、友善錯誤訊息，以及 caplog 裡的 `kind=fragment` 行；2-Z 與上線時看 log。實作前先實測 AppTest 對 fragment 內互動的重跑範圍。
- **裝飾器本身**：`rerun_fragment`、`error_boundary`、`guarded_callback` 用 `AppTest.from_function` 的小腳本測（未預期例外只顯示通用訊息、log 有細節、開關開啟時改為原樣往上拋、`AssetLabError` 顯示原訊息、`st.rerun` 不被攔截）。
- **錯誤兜底（BR-5）**：已登入的 `app.py` AppTest 中讓頁面拋出非領域例外，畫面只有通用訊息、沒有 exception 元素；設定環境變數後改為 Streamlit 完整顯示。
- **BR-7**：沿用 `test_data_io` 的 `_FlakyConnection` 手法，在第 N 筆失敗時，資料庫全部維持原值，頁面只顯示友善訊息。
- **BR-8**：先讓快取記住「空庫」的結果，再用另一條連線寫入資料，按匯入時守門應拒絕。
- **Q4**：AppTest 跑 `views/house.py` 並點勾選框：替身 `get_resilient_container` 只被呼叫一次，寫入走它回傳的容器；寫入失敗時頁面上方顯示訊息、沒有堆疊、頁面照常渲染。
- **AD-7**：結構測試，確認每個 `views/*.py` 的 logger 名稱都以 `asset_lab.views.` 開頭。

## 實作順序約束（交給 1-4）

1. **量測基礎最先做**，而且要單獨成為一個可執行的 commit（AD-13 的「改前」版本）：`APP_LOGGING`、`configure_logging`、`QueryMetrics`、`CountingConnection`、`rerun_scope` 接進 `app.py`、頁面 logger 改名。這個 commit 不得含快取、探測改法、fragment。此時 `build_container` 只接計數層，簽名可以分兩步才到最終版。
2. 探測（AD-5）與快取（AD-1～AD-4）有相依：探測必須走不經快取的連線。
3. `error_boundary`（AD-8）可以獨立進行；`rerun_fragment`（AD-9）依賴 `error_boundary` 與 `verified_container`；`guarded_callback` 的 callback 改造（AD-10）也依賴這兩者。
4. 設定頁整批寫入（AD-11）可以獨立進行。
5. 「改後」量測在全部完成後做，結果寫進 `review.md`。

---

## 已知技術債與限制

| # | 項目 | 影響 | 後續 |
|---|------|------|------|
| 1 | 連線包裝層只提供目前用到的介面 | 以後 Repository 用到 `description`、`fetchmany`、`executemany` 等會拋 `AttributeError` | 用到時擴充包裝層並補測試 |
| 2 | 語句分類靠 `SELECT` 前綴 | `WITH … SELECT` 會被當成寫入透傳並設旗標（目前沒有 CTE） | 新增 CTE 時調整分類 |
| 3 | 單句寫入的 execute 失敗、沒有 rollback 時，寫入旗標維持為真 | 直到下一次 commit 或 rollback 前，讀取都繞過快取（只影響速度） | 若量測看到這種情況，再把單句寫入也改走 `write_transaction` |
| 4 | 月度錄入存檔沿用快取 | 另一處在 5 分鐘內改過同一個月時，這裡可能用舊資料推算淨投入後覆蓋（使用者已接受） | — |
| 5 | 每次重跑仍有 1 次探測往返；stream 實際過期時間未知 | 速度上限受探測影響 | 依 `reconnected` 欄位與耗時佔比，另案評估 P3 自我修復連線 |
| 6 | `FragmentHandledException` 來自 `streamlit.errors`，不是文件化 API | 升級 Streamlit 時可能變動 | 由 error_boundary 的測試把關 |
| 7 | AppTest 看不到 fragment 範圍的重跑 | 「只有編輯器重跑」只能靠結構斷言與 log 驗證 | — |
| 8 | 設定頁新增或編輯項目、改目標比重、買房勾選這幾個單句寫入，失敗時顯示通用訊息而不是「存檔失敗」；勾選失敗時勾選框的畫面狀態可能與資料庫不一致 | 訊息較籠統（不露堆疊，符合 BR-5） | 見待確認事項 2 |
| 9 | Repository 的型別提示仍寫 libsql 的 `Connection` | 包裝層是結構上的替身；專案沒有跑 mypy，不影響執行 | 之後統一改為 `DbConnection` Protocol |
| 10 | 單筆 `upsert_threshold`／`upsert_param` 保留 | 頁面不再使用，只剩測試在用 | 3-1 可評估是否把測試改用整批方法後移除 |
| 11 | 量測的耗時只含伺服器端腳本時間 | 使用者感受到的等待還包含網路與瀏覽器繪製 | 只做前後比較 |
| 12 | 驗證暫存依賴兩個前提：callback 與腳本在同一個執行緒（1.66.1 原始碼已查證），以及每次執行都經過最外層 scope | Streamlit 執行模型改變時要重新確認 | 升級 Streamlit 時重跑 AD-5／AD-10 的測試 |
| 13 | `asset_lab` logger 的 `propagate` 為 True | 若之後有套件在 root 掛 handler，log 會重複輸出 | 出現時再調整 |
| 14 | architecture-brief TD-7（「帶入上月」寫入沒人讀的 session 狀態）、TD-8（總覽與買房頁的讀取重疊） | 維持現狀 | 範圍外，另案 |
| 15 | `st.App(on_script_error)` 未採用 | callback、fragment、腳本仍分三處處理錯誤 | Community Cloud 確認支援後再評估 |
| 16 | 錯誤細節的主防線 L1（`app.py` 的 `st.set_option`）要到 `main()` 才執行；`main()` 之前的錯誤（例如部署後某個依賴或專案模組 import 失敗，每次執行都失敗在同一處）只靠 L0 `config.toml` | 若雲端以命令列參數或環境變數蓋掉 L0，未登入訪客可能看到 stacktrace 模式（通用訊息加程式堆疊，內容是公開 repo 的程式碼與路徑，不含機密或財務資料）；只在 import 層壞掉時發生 | 3-2 決定不改程式；上線後照 review.md 3-2「上線目視檢查」確認 L0 在雲端是否生效，未生效再評估把 `set_option` 提前到專案模組 import 之前 |

## 待確認事項

以下各項都有預設值，不阻擋 1-3／1-4；若使用者要調整，在 1-3 確認 Scenarios 時一併決定。

1. **通用錯誤訊息的文字**：預設「發生未預期錯誤，請稍後再試」。
2. **設定頁其他單句寫入（新增或編輯項目、目標比重）與買房勾選的失敗訊息**：預設維持通用訊息（AD-8）。另一個選項是把這些單句寫入也改走 `write_transaction`，失敗時顯示「存檔失敗，資料未變更，請重試」；改動約 4 個 Repository 方法，不在 proposal 範圍內。
3. **量測次數**：預設每個動作 3 次取中位數（AD-13）。
4. **錯誤細節開關的有效值**：預設 `1`、`true`、`yes`、`on`（不分大小寫）。

---

## 決策總覽

| ID | 類型 | 決策 | 信心度 |
|----|------|------|--------|
| AD-1 | 架構 | 讀取快取放連線層（read-through），Repository 以上透明；只提供目前用到的 cursor 介面 | High |
| AD-2 | 架構 | commit 成功是唯一清除點；有未 commit 的寫入時繞過快取；世代計數擋住競態寫回 | High |
| AD-3 | 架構 | 自建 `ReadCache`，程序級共用、與連線脫鉤；整批 TTL 5 分鐘，在入口判定；側欄「重新讀取資料」 | High |
| AD-4 | 架構 | 只有 CSV 匯入守門先清快取；月度錄入存檔沿用快取 | High |
| AD-5 | 架構 | 建表每個程序一次；探測改 `SELECT 1` 且不經快取；`verified_container()` 讓每次執行最多探測一次，涵蓋 fragment 與 callback | High |
| AD-6 | 架構 | 補 logging 設定；計數層在快取之下；最外層 `rerun_scope` 每次執行記一行 | High |
| AD-7 | 架構 | 頁面 logger 用明確名稱 `asset_lab.views.<頁>`（偏離 `__name__`） | High |
| AD-8 | 架構 | 錯誤兜底四層（config.toml、`set_option`、app 邊界、fragment／callback 邊界）；`ASSET_LAB_SHOW_ERROR_DETAILS` 開關 | High |
| AD-9 | 架構 | 月度錄入編輯器改為 fragment；共用 `rerun_fragment` 裝飾器 | High |
| AD-10 | 架構 | `guarded_callback`：買房勾選 callback 自取已驗證容器，錯誤改由頁面顯示 | Medium |
| AD-11 | 架構 | 設定頁門檻與買房參數整批單一交易；Model 清單由 Service 組 | High |
| AD-12 | 架構 | 完全相同的重複查詢由快取去重，不改頁面 | High |
| AD-13 | 架構 | 量測：只含量測的 commit 當改前版本；本機前後比較，四個動作各 3 次取中位數，結果寫進 review.md | Medium |
| TD-1 | 技術 | Streamlit 1.66.1 原生 `st.fragment` | High |
| TD-2 | 技術 | 快取、計數、錯誤邊界用標準庫自建，不用 `st.cache_data`／`st.App` | High |
| TD-3 | 技術 | 標準庫 `logging`＋stderr handler（沿用 AD-8 偏離） | High |
| TD-4 | 技術 | 不新增第三方依賴 | High |
