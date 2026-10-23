# Review: [Change 名稱]

## 3-1 程式碼清理

掃描範圍：26 個檔案（src 15 / views 3 / tests 8，不含 .ai），68ed557..df8447c

### 自動掃描

Checker 命令：`python .claude/skills/spec-driven-flow/scripts/checkers/runner.py --phase 3-1 --project-dir . --diff-base 68ed557 --json --output .ai/changes/simplify-non-stock-input/.cache/checker_3_1.json`
總違規：47 條（change_level_id_comments 6、function_too_large 3、file_too_long 2、duplicate_code 36 行級命中，合併後 7 處）
Baseline 命中：0 條
完整報告：`.ai/changes/simplify-non-stock-input/.cache/checker_3_1.json`

靜態工具：`ruff check .` 全過；vulture 未安裝，改以腳本檢查本次新增的所有 def 是否有 src/views 內的呼叫點，全部都有，無未使用的新增函式。src/views 的 diff 中無遺留 print / TODO / FIXME / Change 級編號註解。

### SAFE
- `tests/test_balance_input.py` L85/178/226/346/366 — `# === SC-092：... ===` 等 5 條區段註解引用 SC 編號（checker 已標，復核屬實）。建議改成只留業務描述（如 `# === 餘額推算 ===`），去掉 SC 編號。
- `tests/test_cost_basis.py` L698 — `# ==== 保險：...（SC-095~099） ====`（checker 已標，復核屬實）。同上，去掉括號內編號。
- `uses_premium`（`src/asset_lab/services/cost_basis_service.py`）— 評估：保留。它與既有 public 的 `uses_cost_basis` 對稱，有兩個內部呼叫點（`_ensure_uses_premium`、`_ensure_uses_cost_chain`），不是 dead code；`views/` 沒有呼叫（View 走 `resolve_input_mode`），所以可考慮降為 private。但降為 private 會與 `uses_cost_basis` 不對稱，且 tests 已有直接測試，建議保留 public，並在 design 的 public 介面清單補記（design 未列的這一點屬文件落差，不是程式問題）。

### CAREFUL
- `src/asset_lab/bootstrap.py` L47 / `tests/test_bootstrap.py` L53、`tests/test_input_view.py` L24 / `tests/test_monthly_input.py` L9 — checker 報 duplicate_code，復核為 import 區塊相似，偽陽性，不處理。
- `src/asset_lab/services/balance_input_service.py` L29/59/99 — checker 報 `derive` / `plan_save` / `plan_delete` 簽名區塊重複。復核為 keyword-only 參數簽名相似，偽陽性，不處理。
- `tests/test_cost_basis.py` L939~1010 — 兩個保險測試各自內聯相同的 records 準備（`_premium_record` 組合與 `plan_save_premium` 呼叫），checker 已標。可抽成 fixture/helper，但是測試內聯讓每個 SC 情境獨立可讀，抽出有可讀性代價；列為選擇性，需動測試檔，建議本輪不動，若要動僅限抽 records 準備。
- `views/input.py` L394 / L467 — `_render_save_delete(...)` 呼叫的 `plan_delete=lambda: cost_basis_service.plan_delete(...)` 在股票與保險編輯器重複（checker 已標）。兩處引數完全相同，屬 3 行呼叫樣板，保險與股票共用同一個累計成本鏈刪除；抽出收益極小，且兩個編輯器各自保持完整流程較易閱讀，不建議處理。
- `tests/test_input_view.py` 1054 行、`src/asset_lab/services/cost_basis_service.py` 502 行（checker file_too_long，LOW）— 前者是 AppTest 整合測試累積（本次 diff 為重寫該檔），後者只超 2 行。見 SUGGEST。

### RISKY
- `src/asset_lab/repositories/csv_import_writer.py::write_import` — 評估：可接受，建議保留現況，交 3-3 規則審查做最終判定。理由：它是無業務邏輯、僅在單一交易內依序呼叫三個 Repository 的 `*_with_context` 方法，符合 02-architecture §6「Compound method 合法」與 §9（Repository 方法在外部給定的交易 context 內執行、不自行 commit）；沒有反向呼叫 Service，函式命名有業務語意。與 design AD-10 文字的落差：design 寫「由 Page 持有交易 context」，實作改成由這個 module 函式持有 `with` 區塊，Page（`views/data_io.py`）只負責呼叫並 catch `PersistenceError`。這讓 Page 少接觸交易細節，是正向偏離。需使用者判斷的只有一點：是否接受 design 文字與實作不一致（建議做法：接受實作，補一句 design 註記；若堅持 design 原意，則要把 `with` 搬回 View，不建議，因為會讓 View 直接持有三個 Repository 與 transaction，更難測）。檔案放在 `repositories/` 但為模組級函式而非 Repository 類別，與「Repository 為類別」的慣例不同，也留給 3-3 判斷。

### SUGGEST
- `src/asset_lab/services/cost_basis_service.py::plan_save_premium`（54 行，checker 已標）— 超 50 行上限，但其中 docstring 佔 20 行，邏輯本體約 25 行，且與 `plan_save` 結構對稱。判定為偽陽性，不建議拆。
- `views/input.py::_render_premium_editor`（71 行）、`_render_balance_editor`（56 行）（checker 已標）— 各編輯器的流程為 seed、輸入框、parse/derive、預覽、存檔刪除，結構與既有 `_render_cost_basis_editor` 一致。可把 `plan_save` + `_render_save_delete` 收尾區塊抽成共用小函式，但每個編輯器參數不同，抽出後需傳入大量閉包，收益不明確。建議保持現況；若要處理，優先把 `_render_premium_editor` 的 widget 渲染與 seed 抽成 `_render_premium_inputs`。屬風格取捨，不是缺陷，留給使用者決定。
- `cost_basis_service.py` 502 行 — 只超標 2 行，不建議為此拆檔；之後若再新增分類才考慮把保險相關方法拆成獨立 mixin/Service（design 已選擇保險併入累計成本鏈，拆開會違背 AD-2/AD-4）。
- `tests/test_input_view.py` 1054 行 — 可依錄入方式（股票/保險/餘額/應繳/轉移移除）拆成多檔，但屬測試組織重構，超出本次清理範圍，建議另案。

### 建議第二段修正範圍
僅 SAFE 兩項（共 6 行註解，去掉 SC 編號）。其餘不動。
### 修正結果

使用者決定範圍：只修 6 行測試註解，風格題一律不動，design 落差接受實作（另請 designer 補記）。
- `tests/test_balance_input.py` 5 條區段註解去掉 SC 編號，保留業務描述。
- `tests/test_cost_basis.py` L698 去掉「（SC-095~099）」。
- 驗證：`ruff check .` 全過；`pytest tests` 685 passed。


## 3-2 安全性審查

審查範圍：26 個檔案（src 15 / views 3 / tests 8，68ed557..HEAD）；另掃本 Change 已進版控的 `.ai/changes/simplify-non-stock-input/` 文件，確認沒有真實資料
核准判定：有條件通過（本次變更沒有 CRITICAL / HIGH。依賴 CVE 是本次之前就有的，不是本次引入：pyproject / uv.lock 都沒動，而且在本 app 的用法下打不到。另開 chore 處理，不擋本 Change）
（第二段後使用者改採字面規則，判定更新見本區段末的「修正結果」）

### 自動掃描

Checker 命令：`python .claude/skills/spec-driven-flow/scripts/checkers/runner.py --phase 3-2 --project-dir . --diff-base 68ed557 --json --output .ai/changes/simplify-non-stock-input/.cache/checker_3_2.json`
總違規：1 條（CRITICAL: 1 / HIGH: 0 / MEDIUM: 0 / LOW: 0）
Baseline 命中：0 條
完整報告：`.ai/changes/simplify-non-stock-input/.cache/checker_3_2.json`

逐條復核：
- `sql_injection_risk`（CRITICAL）`src/asset_lab/repositories/holding_repository.py` L56 `_INSERT_WITH_ID`：判定為誤報，不構成漏洞。f-string 裡插入的只有 `HOLDINGS_TABLE.*` 這些常數的表名和欄名，沒有外部輸入；值一律走 `?` 參數綁定。這段 SQL 是把原本 `replace_all` 裡的內聯 f-string 原樣搬成模組常數，寫法和同檔的 `_INSERT` / `_UPDATE` 一致，只是因為落在 diff 範圍才被掃到。建議在 L56 行末補 `# checker:noqa sql_injection_risk`，標記為已評估的刻意寫法。

依賴掃描（`pip-audit`，以專案 .venv 為準；uv.lock 版本與 .venv 一致）：6 個套件有已知漏洞，全部是間接依賴，本 Change 沒有異動依賴。逐項評估見下方「發現」的 A06 條目。

### 發現

- [MEDIUM] A06 — `uv.lock`（本次之前就有，不是本 Change 引入）— 間接依賴有已知 CVE
  問題：
  - `certifi` 2026.6.17：CA 憑證庫仍包含 emSign ECC Root CA - G3，它底下的中繼 CA 私鑰已外洩。修補版 2026.10.19。
  - `urllib3` 2.7.0：3 筆。proxy 與目標站的 TLS 設定會混用；串流解壓有 DoS 風險。修補版 2.8.0。
  - `anyio` 4.14.1：3 筆。IDNA 網域的 TLS 驗證、子程序 extra_groups、process pool 的 stderr 卡死。修補版 4.14.2。
  - `gitpython` 3.1.58：13 筆。含惡意 repo 的 hook 執行與任意讀檔。修補版 3.1.60。
  - `pillow` 12.3.0：35 筆，都是影像解碼漏洞。修補版 13.0.0，但 streamlit 1.59.1 鎖了 `pillow<13`，不能單獨升級。
  - `pip` 26.1.2：只在 dev 工具鏈使用。
  影響：本 app 前面有 Google 登入加 email 允許清單，只有本人能操作，而且以下幾條路徑都吃不到攻擊者可控的輸入：
  - gitpython：只有 streamlit 讀本機 repo 資訊時會用到，app 沒有直接呼叫，也不會開外來 repo。
  - pillow：唯一的上傳入口只收 CSV，app 不解碼使用者提供的影像。
  - anyio：app 沒有用到受影響的子程序 API。
  實際可利用性最高的是 certifi：Google OIDC 登入時 requests/httpx 對外的 TLS 會用到它，但攻擊者必須同時站在網路路徑上、又持有外洩的中繼金鑰才能利用，門檻很高。所以依情境評為 MEDIUM（certifi）、LOW（其餘）。
  修復：另開 chore，比照既有 commit 5b446d4。先執行 `uv lock --upgrade-package certifi --upgrade-package urllib3 --upgrade-package anyio --upgrade-package gitpython`（pip 視需要一起升），再跑 pytest。pillow 要先確認新版 streamlit（目前最新 1.66.1）有沒有放寬 `pillow<13`，再決定要不要連 streamlit 一起升。
  Checker 對應：checker 未報出（3-2 runner 的 JSON 裡沒有依賴項，這部分由人工跑 `pip-audit` 補上）

- [LOW] A09 — `views/input.py` `render()` 的 `except AssetLabError` 搭配 `src/asset_lab/core/utils.py` `parse_amount`（後者是本次之前就有的程式）— 驗證錯誤的 log 可能帶出使用者輸入的金額原文
  問題：寫入失敗的路徑沒有問題，已確認乾淨（見下方「已檢視、無發現」）。這條要看的是另一條路徑：按「儲存此列」時，`plan_save()` 會呼叫 `parse_amount`，格式不合時拋出 `DataValidationError(f"{field_label}輸入無效，請輸入正確的金額格式：{text!r}")`。這個例外一路往上，由 `render()` 的 `logger.exception("月度錄入操作失敗")` 整段寫進 log。本 Change 讓保險的累計已繳保費、解約金、本月領回，活存/定存的餘額，以及負債的應繳金額都走這條路徑，所以使用者打錯格式的金額（例如 `'1,00,000'`、`'60萬'`）會以原文進入 log。本 Change 新增的 `DataValidationError` 訊息也會內插 `holding.name`（項目名稱），一樣會進 log。這種寫法在舊程式 `cost_basis_service` 就有先例。
  修復（選擇性）：
  - 最小改法：把 `parse_amount` 訊息裡的 `{text!r}` 拿掉。輸入框本身就會顯示使用者打的原文，畫面資訊不會因此變少。tests 裡沒有斷言這段訊息字樣，改動面只有一行。
  - 另一種做法：讓頁面對 `DataValidationError` 這類使用者輸入錯誤只寫 warning、不帶 traceback，只有 `PersistenceError` 和其他錯誤才用 `logger.exception`。
  - 兩種都會動到本次之前就有的程式，建議由使用者決定要在本 Change 修，還是另案處理。
  影響：只有 log 受影響。Streamlit Community Cloud 的 app log 只有擁有部署權限的開發者看得到，repo 公開不會連帶公開 log。外洩的值是本人打錯格式的輸入，不是資料庫裡的正式數值。風險低。
  Checker 對應：checker 未報出（logging_rules 沒有命中，因為 log 呼叫本身沒有內插變數，敏感內容是藏在例外訊息裡帶進去的）

- [LOW] A05 — 其他頁面的讀取與單筆寫入（本次之前就有，不在本 Change 範圍，design「已知技術債」已記載）— 失敗時仍可能顯示原始錯誤與堆疊
  問題：
  - 本 Change 的友善錯誤只涵蓋 `write_transaction` 管到的寫入：月度錄入的所有存檔與刪除，以及 CSV 匯入。
  - 其餘路徑拋出的 libsql `ValueError` 不是 `AssetLabError`，會落到 Streamlit 預設的例外畫面。這包括 `read_month`、`read_holding_records` 等讀取，以及設定頁的 `add_holding`、`update_holding`、`upsert_target`。
  - repo 沒有 `.streamlit/config.toml`，本機的 `client.showErrorDetails` 預設是 `full`，畫面會出現像 `UNIQUE constraint failed: holdings.name` 這種含表名、欄名的訊息和堆疊。Community Cloud 的平台預設值會不會遮蔽這些內容，本次無法驗證。
  修復（另案）：在 `.streamlit/config.toml` 加 `[client] showErrorDetails = "none"`（或 `"type"`）當全站兜底，或在 `app.py` 加一層全站錯誤處理。這和 design 已記載的建議一致。
  影響：只有通過登入守門的本人看得到，屬於縱深防禦的缺口。
  Checker 對應：checker 未報出

### 已檢視、無發現

針對派工點名的三個重點逐一確認：

1. **寫入失敗時，畫面不會洩漏 SQL、表名、原始錯誤或財務數值**：通過。
   - `PersistenceError` 的訊息是固定的 `DEFAULT_MESSAGE`，不內插原始錯誤。repo 內沒有任何地方用自訂訊息建構它。
   - 月度錄入頁的 `st.error(str(error))` 只會顯示這段友善訊息。`str()` 不含 `__cause__`，也不含 `add_note` 附上的附註。
   - 匯入頁用 `except PersistenceError` 接住後，顯示寫死的「匯入失敗，資料未變更，請重試」。
   - 三條寫入路徑（`upsert_records`、`delete_record_and_upsert`、`write_import`）的呼叫點都在對應頁面的 try 範圍內，沒有漏接。
   - 測試有斷言畫面不出現原始錯誤：`tests/test_input_view.py` 涵蓋四種錄入方式的存檔與刪除，斷言畫面沒有 "secret SQL"；`tests/test_data_io.py::test_sc107_failure_shows_friendly_error_without_raw_detail` 斷言紅字只有友善訊息。
   - 例外轉譯從寬，不是 `AssetLabError` 的 `Exception` 一律轉成 `PersistenceError`，所以就算區塊內出現程式錯誤，畫面也不會露出細節。
2. **log 裡的錯誤鏈不會帶出財務數值**：寫入失敗這條路徑通過，但另見上方 A09 的 LOW 條目（那是驗證錯誤的路徑）。
   - 用本機 libsql 記憶體 DB 實測，觸發唯一鍵、CHECK、NOT NULL、參數型別錯誤，並故意綁定一個標記金額 `987654321`。錯誤訊息只有約束名稱、`表.欄`、約束運算式或型別名稱，都不含綁定值。
   - 走一次 `write_transaction` 加 `logger.exception` 的完整 log，搜不到標記值。
   - traceback 只列原始碼行，不含區域變數。
   - `add_note` 附的是 rollback 錯誤的 repr，同樣不含資料值。
   - 殘留不確定性：連遠端 Turso（Hrana）時的錯誤字樣沒有實測，因為不可對正式庫做破壞性測試。依協定推估，訊息會是伺服器回傳的錯誤，最多帶出主機名稱；auth token 放在 header，不會出現在錯誤訊息裡。
3. **新增的程式碼與測試沒有寫死真實資料或密鑰**：通過。
   - 新增的行裡沒有 token、secret、password、`libsql://`、`turso.io`、email、電話、JWT 或 API key 這類樣式。
   - 測試用的項目名稱都是泛稱（活存、定存、信用卡、房貸、海外年金保單、台積電），沒有金融機構名、帳號或保單號。
   - 金額都是整數萬元，或明顯虛構的值（111111、999999）。
   - 測試裡的 "secret SQL detail" 是刻意放的洩漏偵測字串，不是真的密鑰。
   - `.ai/changes/simplify-non-stock-input/` 的文件裡沒有機構名、個資或非整數萬元的金額。

其他維度：
- **A01 / A07 認證與授權**：本 Change 沒動 `app.py` 的登入守門。新增的寫入入口（錄入頁的四個編輯器、匯入頁）都在守門通過之後才會渲染。
- **A03 注入**：新增的 SQL（`_INSERT_WITH_ID`，以及沿用既有常數的三個 `*_with_context`）全部參數化。趨勢圖的 trace 名稱用的是項目名稱，只有本人能設定；Plotly 的文字會限制可用的 HTML 標籤和連結協定，最多只是自己影響自己的 XSS，不構成風險。
- **A05 密鑰**：`.streamlit/secrets.toml` 已列入 `.gitignore`，從沒進過版控。`git log --all` 查 `*.env`、`*.json`、`*.pem`、`*.key`，只命中 `.devcontainer/devcontainer.json`，內容不含密鑰。本 Change 範圍的 commit 也沒有新增任何疑似密鑰的字串。
- **A08 反序列化**：CSV 匯入仍然先過 `parse_and_validate`（pydantic 驗證）才會開交易寫入，沒有引入新的反序列化入口。
- **資料完整性（附記，不是本次引入的問題）**：`bootstrap` 用 `st.cache_resource` 讓所有 session 共用同一條連線。如果本人同時開兩個分頁、又剛好同時寫入，一邊的 rollback 或 commit 理論上可能牽動另一邊還沒 commit 的寫入。這是既有架構，只影響單一使用者在多分頁同時寫入的極端情境，不列為發現。

### 建議第二段修正範圍

本 Change 內建議只做一件事：在 `holding_repository.py` L56 補 `# checker:noqa sql_injection_risk`（1 行，選擇性）。

其餘條目交由使用者決定：
- A09（`parse_amount` 訊息去掉原文）：可在本 Change 順手做，也可以另案處理。
- A06（依賴升級）：建議另開 chore。
- A05（全站錯誤畫面兜底）：建議另開 Change。

### 修正結果

使用者決定的範圍：
- A09：在本 Change 修。
- 補 noqa 標記。
- A06：照規則字面擋下，這次就升級；pillow 如果必須連 streamlit 一起升才能修，先不升 streamlit，回報後由使用者決定。
- A05：不在本輪範圍。

**1. A09：log 不再帶出金額原文（已修）**
- `src/asset_lab/core/utils.py::parse_amount` 的錯誤訊息拿掉了 `{text!r}`，改成「{欄位}輸入無效，請輸入正確的金額格式」，並在 docstring 補上不帶原文的原因。
- 這仍然符合 SC-082 的要求（「訊息帶欄位名稱」）。`test_sc082_error_message_includes_field_label` 照樣通過。
- 實測輸入 `'1,00,000'`、`'60萬'`、空字串、None，錯誤訊息都不含原文。
- 目前沒有測試鎖住「訊息不含原文」這一點。要鎖住的話，得先在 SC-082 補一條 THEN，再加對應的測試，這屬於規格異動，本輪沒做。

**2. noqa 標記（已補）**
- `holding_repository.py` L56 行末加上 `# checker:noqa sql_injection_risk`。
- 重跑 3-2 checker，違規數為 0（`.cache/checker_3_2_after.json`）。

**3. A06：依賴升級**

Community Cloud 用哪個檔案解析依賴：
- 依官方文件，優先序是 `uv.lock` > `Pipfile` > `environment.yml` > `requirements.txt` > `pyproject.toml`，只採用第一個找到的檔案。
- 本 repo 只有 `uv.lock`（另有 `pyproject.toml` 作為它的來源），沒有 `requirements.txt` 或 `Pipfile`，所以部署實際用的是 `uv.lock`。
- 這次只改了 `uv.lock`，套件的版本範圍不變，所以 `pyproject.toml` 不用改。`uv lock --check` 通過，兩者一致。
- `.devcontainer/devcontainer.json` 會在 `requirements.txt` 存在時才安裝它；目前沒有這個檔案，與部署無關。

`uv lock --upgrade-package certifi --upgrade-package urllib3 --upgrade-package anyio --upgrade-package gitpython --upgrade-package pip`，再執行 `uv sync --extra dev`：

| 套件 | 升級前 | 升級後 | 修補版 | 備註 |
|------|--------|--------|--------|------|
| certifi | 2026.6.17 | 2026.10.19 | 2026.10.19 | |
| urllib3 | 2.7.0 | 2.8.0 | 2.8.0 | |
| anyio | 4.14.1 | 4.15.1 | 4.14.2 | 版本範圍內的最新版 |
| gitpython | 3.1.58 | 3.2.1 | 3.1.60 / 3.2.1 | streamlit 1.59.1 要求 `<4` |
| pip | 26.1.2 | 26.2.2 | 26.2 | 有在 `uv.lock` 內，但只來自 dev extra（pip-audit → pip-api → pip），部署時不會安裝；照樣一起升 |
| pillow | 12.3.0 | 12.3.0（未升） | 13.0.0 | 見下方 |

- `uv.lock` 的變動只有上面這 5 個套件，外加 anyio 4.15.1 自帶的 typing-extensions marker 調整，沒有牽動其他套件。

升級後重跑 `pip-audit`：
- 升級前 6 個套件共 51 個不重複 ID，升級後只剩 pillow 12.3.0 的 35 筆（修補版 13.0.0）。
- certifi、urllib3、anyio、gitpython、pip 全部清零。

**pillow 的結論：必須連 streamlit 一起升，本輪依指示沒升。**
- streamlit 1.59.1 到 1.66.0 都要求 `pillow<13`。直到 1.66.1（2026-10-21 才發布）才放寬成 `<14`；1.66.0 到 1.66.1 之間唯一的功能變更就是「Allow Pillow 13」。
- 所以要修 pillow，最低得升到 streamlit 1.66.1。
- 連帶影響：
  - 1.66.1 排除了 `pyarrow 25.0.0`，pyarrow 會跟著升到 26.0.0。
  - 從 1.61.0 起 streamlit 不再依賴 GitPython，gitpython、gitdb、smmap 會從 lock 移除。
  - 另外會移除 blinker、cachetools、httptools、tenacity、toml。
- 試跑：我另外複製了一份程式到 scratchpad，鎖成 streamlit 1.66.1、pillow 13.0.0、pyarrow 26.0.0（不動專案本身的 lock 和 .venv）。
  - pip-audit 結果為 0 個已知漏洞，headless health 為 200。
  - pytest 有 127 個失敗，原因全部相同：1.61 起 `AppTest.from_file` 的相對路徑改成以「呼叫它的測試檔所在目錄」解析，不再以 repo 根目錄解析。
  - 把相對路徑改成以 repo 根目錄解析之後，685 個測試全數通過。
- 1.59.1 → 1.66.1 changelog 中可能影響本專案的變更：
  - **測試需要改（確定）**：`AppTest.from_file` 的相對路徑解析方式改變（1.61）。tests 裡有 9 個呼叫點傳的是 `"app.py"`、`"views/*.py"` 這種相對路徑，要改成以 `Path(__file__)` 推出的絕對路徑。這是機械式修改。
  - **需要人工目視確認**：
    - pyarrow 從 25 升到 26。app.py 有一段針對 pyarrow 25 mimalloc 在 macOS arm64 segfault 的規避設定（`ARROW_DEFAULT_MEMORY_POOL=system`）。要在本機實際操作月度錄入表格和切頁，確認不會崩潰。
    - 1.64 起「`st.rerun` 之後 widget 保留使用者選的值、不重設成預設值」。錄入頁存檔後靠 rerun 和 seed 機制重新帶入資料，測試雖然都通過，仍建議實際存檔一次，確認帶入值正確。
  - **檢查過、應該不受影響**：
    - 1.66 的 CSS selector 要去掉 `section` 標籤：本專案的 selector 只用 `st-key-*` class 和 `stMetric*` testid。
    - `st.html` 傳本機路徑被棄用：本專案傳的是 CSS 字串。
    - 1.62 移除 `st.cache`：本專案只用 `st.cache_resource`。
    - 1.63 的 `st.rerun` 在 callback 內生效：本專案沒有在 callback 裡呼叫 rerun。
    - 1.66 不再支援 Python 3.10：專案用 3.12，devcontainer 用 3.11。
    - auth（`st.login`、`st.user`）、`st.navigation`、`st.secrets`、`st.plotly_chart` 在這幾版都沒有破壞性變更。
- 風險提醒：1.66.1 發布才 2 天。
- 待使用者決定（使用者已選 (a)，見下方第二輪）：
  - (a) 本 Change 就升 streamlit 1.66.1，並改 9 個 AppTest 路徑；
  - (b) 另開 chore 升級；
  - (c) 暫不升，接受 pillow 風險（app 的上傳只收 CSV，不解碼使用者提供的影像）。

**驗證（專案本身，streamlit 1.59.1 加上上述升級）**
- `ruff check .`：All checks passed。
- `pytest tests`：685 passed。
- headless 啟動（`streamlit run app.py --server.headless true`）：`/_stcore/health` 回 200 `ok`，log 沒有錯誤或例外。過程中沒有開瀏覽器 session、沒有登入，所以 app.py 沒有執行，也沒有連線正式庫。

**修正後判定（第一輪，已被下方第二輪取代）**
- 本次變更的程式碼已沒有未處理的發現；A05 是本次之前就有的問題，另案處理。
- 依賴方面只剩 pillow 12.3.0 的 35 個 CVE 未解。依使用者採用的字面規則（有未修補的高風險 CVE 就阻擋），維持「阻擋」，等使用者對 pillow / streamlit 升級做出決定後再更新。

#### 第二輪：升級 streamlit 1.66.1（使用者選擇 (a)）

**依賴異動**
- `pyproject.toml` 是 `streamlit[auth]>=1.42`，沒有擋住 1.66.1，所以不用改。
- 執行 `uv lock --upgrade-package streamlit --upgrade-package pillow`，再執行 `uv sync --extra dev`。
- `uv lock --check` 通過；部署用的 `uv.lock` 已同步。

| 套件 | 升級前 | 升級後 |
|------|--------|--------|
| streamlit | 1.59.1 | 1.66.1 |
| pillow | 12.3.0 | 13.0.0 |
| pyarrow | 25.0.0 | 26.0.0（streamlit 1.66.1 要求 `pyarrow!=25.0.0`，連帶升級） |

從 lock 移除的套件（streamlit 不再依賴它們）：
- `gitpython` 3.2.1、`gitdb` 4.0.12、`smmap` 5.0.3：streamlit 1.61 起改用 git CLI，不再用 GitPython。
- `blinker` 1.9.0、`cachetools` 7.1.4、`tenacity` 9.1.4、`toml` 0.10.2。
- `httptools` 0.8.0：1.66 起改成 `streamlit[performance]` 的選用依賴。沒裝的話，uvicorn 會改用純 Python 的 HTTP 解析器，只影響效能。
- 專案原始碼與測試都沒有直接 import 以上任何一個套件（`test_bootstrap` 用的是標準庫 `tomllib`）。

**測試路徑修正**
- 1.61 起 `AppTest.from_file` 的相對路徑改以「呼叫它的測試檔所在目錄」解析，所以 9 個呼叫點全部改成用 repo 根目錄推出的絕對路徑。
- 做法沿用既有寫法：`test_overview`、`test_page_config`、`test_bootstrap`、`test_navigation_guard` 原本就在模組層級定義 `APP_DIR = Path(__file__).resolve().parent.parent`。
  - 已有 `APP_DIR` 的兩個檔（`test_overview`、`test_page_config`）直接改用它。
  - 其餘五個檔（`test_app_guard`、`test_data_io`、`test_house`、`test_input_view`、`test_settings_view`）補上同樣的常數和 `from pathlib import Path`。
- 沒有抽到 conftest：從 conftest import 共用函式不是 pytest 的慣用寫法，各檔自帶 `APP_DIR` 才是本專案既有的模式。
- 路徑寫法用 `APP_DIR / "views" / "input.py"`，同 `test_overview` 既有的寫法。

**app.py 的 pyarrow 規避設定（沒有改動，只做觀察）**
- `os.environ.setdefault("ARROW_DEFAULT_MEMORY_POOL", "system")` 不受 pyarrow 版本限制，是無條件設定，在 pyarrow 26 下照樣生效。
  - 實測：預設 memory pool 是 `mimalloc`，設了這個環境變數後變成 `system`。
  - `test_bootstrap::test_app_disables_pyarrow_mimalloc_before_importing_streamlit` 仍然通過。
- 只有文字提到「pyarrow 25」，邏輯沒有綁版本。提到的地方有：app.py 第 21 行的註解、`test_bootstrap` 那個測試的 docstring、README 第 166 行。
- 上游背景：
  - streamlit PR #15947 確認 pyarrow 25.0.0 內建的 mimalloc 3.3.1 會讓 ScriptRunner 執行緒 segfault，對應上游 apache/arrow#50471。該 issue 在 2026-07-21 關閉，並標記為 backport-candidate。
  - pyarrow 26.0.0 在 2026-10-09 發布，晚於修復時間；streamlit 1.66.1 也只排除 25.0.0。據此推斷 26 已修好，但沒有在 macOS arm64 上實際重現驗證。
- 建議：先保留設定。用系統 malloc 只有輕微的效能差異，保留比較安全。等使用者在本機目視確認 pyarrow 26 下不會崩潰後，再決定要不要把註解改成「pyarrow 25.0.0 已知問題，26 已修，保留作保險」，或連同測試一起移除。這是文字或設定的取捨，不影響本次安全審查結論。

**websockets / uvicorn 啟動警告（使用者決定一併處理，已處理）**
- streamlit 1.66 啟動時會發出警告：「Installed websockets 16.1 with uvicorn 0.51.0 can abort the /_stcore/stream handshake when a reverse proxy forwards non-ASCII headers」。
- 這兩個版本原本就在 lock 裡，不是這次升級帶進來的，1.66 只是新增了這個警告。Community Cloud 在 reverse proxy 後面，理論上會受影響。
- 處理方式：
  - 執行 `uv lock --upgrade-package uvicorn`，再執行 `uv sync --extra dev`。
  - uvicorn 從 0.51.0 升到 0.54.0，streamlit 要求 `>=0.30.0,<1`。
  - `uv.lock` 只有 uvicorn 這一項變動，沒有連帶升級或移除其他套件；websockets 維持 16.1。
  - `uv lock --check` 通過。
- 結果：重新 headless 啟動後，log 裡已沒有這則警告。

**第二輪驗證（專案本身：streamlit 1.66.1、pillow 13.0.0、pyarrow 26.0.0、uvicorn 0.54.0）**
- `pip-audit`：No known vulnerabilities found（只有本專案自己 asset-lab 因為不在 PyPI 被略過）。
- `ruff check .`：All checks passed。
- `pytest tests`：685 passed，沒有 warning。
- headless 啟動：`/_stcore/health` 回 200 `ok`。log 沒有任何警告、錯誤或例外，只有 Streamlit 建議本機安裝 Watchdog 的開發提示。過程中沒有開瀏覽器 session、沒有登入，也沒有連線正式庫。

**需要使用者目視確認的兩件事（自動化無法驗證）**
1. pyarrow 26 下，在本機實際操作月度錄入表格（`st.dataframe`）的編輯和反覆切頁，確認 Python 進程不會崩潰。
2. 在月度錄入頁存檔一次。1.64 起 `st.rerun` 之後 widget 會保留使用者選的值，所以要確認存檔、rerun 之後，成功訊息、本月紀錄表和錄入框的帶入值都正確，例如切換項目或月份後，帶入的是新資料，不是舊輸入。

**修正後判定（第二輪，取代上方第一輪的判定）**
- 有條件通過。
- 本次變更的發現都已修正：A09 已修；checker 誤報已補 noqa；A06 依賴 CVE 已全部清零（pip-audit 0）。
- 剩下 A05（全站錯誤畫面兜底），是本次之前就有的 LOW，另開 Change 處理。
- 上方兩件目視確認在合併前由使用者完成。

## 3-3 規則符合度審查

<!-- rules-reviewer subagent 產出（工程準則全面符合度檢查）-->

## 3-4 行為對映審查

<!-- scenario-mapper subagent 產出（AI 比對 SC 描述 vs test 內容，分「不對齊」「對齊」兩類）-->
