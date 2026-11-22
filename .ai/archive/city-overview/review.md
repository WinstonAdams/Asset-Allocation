# Review: [Change 名稱]

## 3-1 程式碼清理

掃描範圍：25 個 .py 檔 + city.js/css，main...HEAD（ruff 全綠；vulture 未安裝，跳過）

### 自動掃描

Checker 命令：`python .claude/skills/spec-driven-flow/scripts/checkers/runner.py --phase 3-1 --project-dir . --diff-base origin/main --json`（本機無 origin/main 仍成功執行）
總違規：41 條
Baseline 命中：0 條
完整報告：`.ai/changes/city-overview/.cache/checker_3_1.json`

逐條復核：
- change_level_id_comments（1，tests/test_overview.py:598）— 確認屬實，列 SAFE。
- duplicate_code（35 條）— 偽陽性：皆為 import 區塊與 keyword 引數清單（bootstrap 組 CityService、測試 `_city_service()`、各測試檔 fixture 參數）；無實質可抽象的重複，不處理。（如要豁免可補 `# checker:noqa duplicate_code`，建議不補。）
- function_too_large（3）— `layout.check`(56 行，測試用衝突檢查)、`CityService.frame_at`(72 行含 25 行 docstring，實際邏輯約 45 行)、`test_sc145_...`(74 行)。皆為線性流程，拆分收益低，列 SUGGEST 不動。
- file_too_long（2）— `city/layout.py` 713 行、`tests/test_city_service.py` 751 行；屬移植試做演算法與整合測試，拆檔屬結構決策，列 RISKY。

### SAFE
- `tests/test_overview.py:598` — 註解 `# ---- 城市總覽整合（SC-151、160、161、162）` 引用 SC 編號（checker 已標），改為描述性註解「城市總覽整合」。
- 其餘：無未使用 import／變數、無 print／debug／TODO／FIXME（src、views、city.js 皆查過；checker 未報、人工確認）。

### CAREFUL
- `views/overview.py:_to_month_records`、`views/house.py:_to_month_records` — 與本次新增的 `core/utils.records_frame_to_models` 逐行相同（checker 未報出）。新 util docstring 自述「與買房頁、總覽頁私有的轉換同口徑」。可改為呼叫共用函式並刪除兩份私有版。風險：這兩份是既有程式碼，overview 版 docstring 明載「頁面各自編排的可接受重複，見 design 已知限制」，與設計決策相關；且 house.py 非本次設計範圍。建議：僅在使用者同意時才收斂（測試若 patch 私有名稱需同步調整，已 grep：僅兩 view 自身使用）。

### RISKY
- `src/asset_lab/city/layout.py` 713 行 — 超過 500 行上限；為移植試做演算法，拆檔會動 import 結構與測試，建議留待 3-3 規則審查判斷，不在清理自行處理。
- `tests/test_city_service.py` 751 行 — 同上，可依 timeline／frame 拆兩檔，需使用者決定。

### SUGGEST
- `services/city_service.py:CityService.frame_at` — 已拆出 `_weather_at/_site_at/_buildings_at`，主流程可接受，不建議再拆。
- `city/layout.py:check` — 結尾「畫布邊界」段（約 10 行）可抽成 `_outside_canvas`，純美化，可不做。
- `tests/test_city_service.py::test_sc145_latest_month_matches_existing_page_results` 74 行 — 可抽 helper，可不做。
- `core/constants.py` 檔頭 `AD-7`、`views/overview.py` 的 design 引用 — AD-7 為既有（非本次 diff），不處理。

### 修正結果（第二段）

- `tests/test_overview.py` — SC 編號註解改為「城市總覽整合」。
- `views/overview.py`、`views/house.py` — 刪除私有 `_to_month_records`（含「可接受重複」docstring 說法），改呼叫 `core.utils.records_frame_to_models`；移除不再使用的 `MonthlyRecordModel`、`pandas` import。
- layout.py / test_city_service.py 長度：不拆，交 3-3 判斷。
- 驗證：pytest 1104 passed；ruff check 全綠；scenario_lint 無本分支新增問題（既有技術債不計）。

## 3-2 安全性審查

審查範圍：29 個檔案（`git diff main...HEAD` 中的 25 個 .py，加上 `city/city.js`、`city/city.css`、`pyproject.toml`、`uv.lock`）；另掃 `.ai/changes/city-overview/**`、`docs/ROADMAP.md` 是否含真實個資或財務數字（repo 公開）
核准判定：有條件通過（無 CRITICAL／HIGH；1 條 MEDIUM 是既有的依賴 CVE，不是本分支引入，適用性分析見「發現」第 1 條）

### 自動掃描

Checker 命令：`python .claude/skills/spec-driven-flow/scripts/checkers/runner.py --phase 3-2 --project-dir . --diff-base origin/main --json --output .ai/changes/city-overview/.cache/checker_3_2.json`
總違規：0 條（CRITICAL: 0 / HIGH: 0 / MEDIUM: 0 / LOW: 0）
Baseline 命中：0 條
完整報告：`.ai/changes/city-overview/.cache/checker_3_2.json`

Checker 只掃 .py，沒有涵蓋 `city.js`、`city.css`、`uv.lock`；這三個檔案與各維度的語意風險由下方人工審查補上。

### 依賴掃描

- `pip-audit`（.venv，與 uv.lock 一致；`uv lock --check` 通過）：3 個套件共 12 條已知漏洞，版本與 main 的 uv.lock 完全相同。本分支的 uv.lock 只改了 streamlit 下限的 specifier，沒有換任何套件版本，所以這些漏洞都是既有的，不是本分支引入。
  - `authlib 1.7.2`：9 條（PYSEC-2026-4354～4360、CVE-2026-96760、CVE-2026-116672），修補版本 1.9.1（最新 1.9.6）
  - `joserfc 1.7.3`：2 條（CVE-2026-119283、CVE-2026-119284），修補版本 1.7.6（最新 1.8.0）
  - `msgpack 1.2.1`：1 條（CVE-2026-114613），修補版本 1.2.3；依賴鏈是 pip-audit → cachecontrol，只出現在 dev 依賴，不進正式環境
- `uv pip list --outdated`：streamlit 1.66.1 → 1.67.0 等一般小版本落後，沒有其他已知 CVE。

### 發現

- [MEDIUM] A06 — `uv.lock`（既有，非本分支引入）— 認證鏈的 `authlib 1.7.2`、`joserfc 1.7.3` 有已知 CVE，修補版本已釋出
  問題：`streamlit[auth]` 的 `st.login` 經由 authlib（OIDC 用戶端）與 joserfc（Streamlit 自簽的 provider token，HS256）運作，兩個套件都落在修補版本以下。pip-audit 沒有提供 CVSS 分數。從描述看，其中幾條屬於簽章繞過或 token 偽造等級（例如 4355、4356、96760），一般評級可能在 High 以上。
  適用性（逐條對照 `.venv` 內 streamlit 1.66.1 的原始碼）：
  - Streamlit 走 authorization code flow，有 PKCE（S256）時會啟用（`starlette_auth_routes.py` 的 `authorize_access_token`）。4357（nonce 綁定繞過）的描述明寫 code flow 不受影響。
  - 4358、4359、4360、116672 都是 OAuth **授權伺服器端**的 grant 或端點；本專案是用戶端（RP），用不到這些功能。
  - 96760 是 `JsonWebSignature.deserialize_json` 的問題；authlib 的 `jwt.decode` 走的是 `deserialize_compact`，碰不到。
  - 4355、4356 是 authlib `OctKey` 的問題。Streamlit 簽 provider token 時優先用 joserfc，只有 joserfc 不存在時才退回 authlib；`cookie_secret` 由 secrets 設定，不會是空字串。
  - 4354（is_secure_transport）要求攻擊者能提供 URL；本專案的 `server_metadata_url` 由營運者設定。
  - joserfc 119284：未登入的請求可以把超大 provider token 送進 `/auth/login`，會造成約 1.1 倍的記憶體放大，屬於有上限的輕度 DoS。119283 是 JWE `decrypt_json` 的問題，本專案沒有使用。
  修復：另開 chore commit 或 PR，執行 `uv lock --upgrade-package authlib --upgrade-package joserfc`（必要時一併升 `msgpack`），然後在本機實測 Google 登入、登出與白名單拒絕三條路徑。main 合併後會自動部署到共用正式庫，所以建議不要跟城市總覽混在同一個 commit，否則 revert 時兩者會連動。
  影響：以現行設定與程式路徑判斷不可利用，殘餘風險是 provider token 端點的輕度 DoS。但認證層長期停在有 CVE 的版本，日後 Streamlit 改用受影響的 API 時會直接暴露。
  Checker 對應：checker 未報出（checker 不掃依賴）

- [LOW] A03（縱深防禦）— `tests/test_city_static.py` — `city.js` 危險 API 靜態掃描的 regex 還可以補幾條
  問題：目前禁用 `innerHTML|outerHTML|insertAdjacentHTML|document.write|DOMParser|createContextualFragment|eval(|new Function`，已涵蓋主要的 HTML 注入 sink。CCv2 inline 元件跑在主頁同源的 shadow DOM 裡（`getRootNode().host`），不受 iframe 隔離保護，所以這道靜態掃描是防 XSS 的主要護欄。目前缺的是 `setAttribute('on…')`、`.src=`／`.href=`／`srcdoc`、字串形式的 `setTimeout`／`setInterval`。
  修復：在既有 regex 補上 `|setAttribute\s*\(\s*['"]on|\.(src|href|srcdoc)\s*=|set(Timeout|Interval)\s*\(\s*['"\x60]`；現行 `city.js` 都沒有用到這些寫法，補上後測試仍會綠燈。
  影響：目前沒有可利用點。補上的效果是防止日後改 JS 時把使用者輸入的名稱帶進新的 sink。
  Checker 對應：checker 未報出

### 已確認無問題的維度（人工逐項）

- **A03 注入／XSS**：持有項目名稱（使用者輸入）在前端只透過 canvas `fillText`、`textContent`、`createTextNode` 輸出；小卡在 Python 端用 `st.text` 輸出，不經 markdown；`st.caption` 只輸出 `CITY_TEXT` 常數。`city.js` 裡唯一的 `setAttribute` 是 `aria-label`，值取自常數。`const GEOM = …` 是唯一拼進 JS 原始碼的內容，來源是 `GEOMETRY` 常數的 `json.dumps`，不含使用者資料；payload 走 CCv2 的 `data` 通道做 JSON 傳輸，不會拼成程式碼。建築 id 都是 `holding-<int>` 或 `site`，沒有 prototype pollution 的可能。JS／CSS 沒有任何外部 URL、`fetch`、storage 或 cookie 存取。BR-4、BR-6 由 `test_city_static.py` 守住。
- **A01 存取控制**：元件透過 `setStateValue` 回報的選取值會先經 `payload.resolve_selection` 檢查型別必須是 str，再比對白名單（本時間軸的建築 id 加上 `site`），不在白名單就靜默清除；月份值在 `_select_month` 先比對選項清單，`frame_at` 再擋一次。`rerun_fragment` 單獨重跑時不會經過 `app.py` 的登入守門，但 fragment 是每個 session 各自登記，只有守門通過、`render()` 執行過才存在，所以不構成繞過。這個模式和既有的 `views/input.py` 相同。
- **A02／A09 資料保護與日誌**：送到瀏覽器的 payload 只有已登入使用者本來就看得到的名稱與金額。新增程式碼沒有任何 logger 呼叫；fragment 的錯誤兜底只記 context 標籤和 traceback；`_validated_lots`、`frame_at` 的 ValueError 訊息只帶 `holding-N` id 和年月，不帶名稱或金額。`ERROR_DETAILS` 關閉時，使用者只會看到通用訊息。
- **A04／可用性**：`layout_city` 的迭代上限是 16、`lru_cache(maxsize=8)` 有上限；城市區塊出錯時由 fragment 兜底接住，下方的數字卡照常顯示。
- **A05 環境與密鑰**：本次 diff 沒有任何密鑰、email、Turso URL 或 token；`.streamlit/secrets.toml`、`.env`、`*.env` 都在 `.gitignore` 裡。`git log --all` 查過 `*.env`、`*.pem`、`*.key`，從未被提交；`*secrets*` 的歷史只有 `secrets.toml.example`，內容全是佔位值。
- **敏感資料（repo 公開）**：SC 卡片、design、spike-findings、測試 fixture 的項目名稱都是虛構命名（甲乙丙丁戊己庚、「範例活存」「虛構貸款」），金額都是整數示意值，沒有找到真實持有項目或財務數字。

### 範圍外觀察（不列入判定）

- `.devcontainer/devcontainer.json` 的 `postAttachCommand` 以 `--server.enableCORS false --server.enableXsrfProtection false` 啟動。這是既有檔案（Codespaces 預設範本），不在本次 diff 裡，只影響 Codespaces 開發環境，不影響 Community Cloud。如果不用 Codespaces，可以另案刪除或改掉這兩個旗標。

### 修正結果（第二段）

使用者決定兩條都在本分支修，分成兩個 commit。

- **MEDIUM（依賴升級）**：使用者決定不用剛發布的 authlib 1.9.6、joserfc 1.8.0（前者 2026-11-14 發布，當時距今 1 天），改鎖較早而且已含全部修補的版本。執行 `uv lock --upgrade-package authlib==1.9.5 --upgrade-package joserfc==1.7.7`，再 `uv sync --extra dev`。msgpack 不在範圍內。
  - `uv.lock` 相對 main 只改了兩個套件，加上本分支原本就有的 streamlit 下限那一行，沒有連帶升級其他套件，兩者的相依清單（cryptography、joserfc）也沒變。`uv lock --check` 通過。
    - `authlib` 1.7.2 → 1.9.5（2026-11-05 發布，最低修補版本是 1.9.1）
    - `joserfc` 1.7.3 → 1.7.7（2026-10-19 發布，最低修補版本是 1.7.6）
  - `pyproject.toml` 不用改：streamlit 對 authlib 的要求是 `>=1.3.2`。
  - 再跑一次 pip-audit：authlib 與 joserfc 的 11 條都已清除，只剩 msgpack 1.2.1 一條（dev 依賴，不在範圍內）。
  - 相容性檢查（實際鎖定版本）：
    - Streamlit 1.66.1 的 OIDC 路由模組可以正常 import。authlib 1.9.x 會印一條 `AuthlibDeprecationWarning`（httpx 模組改名），1.7.2 沒有，只是警告。
    - Streamlit 依賴的 session state key 格式 `_state_{provider}_{state}` 沒有改變。
    - provider token 用 joserfc 1.7.7 簽發、驗證可以往返，竄改過的 token 會被拒絕。
    - 「同一 provider 只保留最新一筆登入 state」在 1.9.5 仍然存在。但我比對了 authlib 1.7.2 的原始碼，`set_state_data` 的寫法完全相同，所以這是既有行為，**不是升級帶來的差異**。上一輪說它是「新版行為差異」是誤判，在此更正。
  - 未驗：Google 登入、登出、白名單拒絕三條路徑要由使用者在本機實測。
- **LOW（靜態掃描補強）**：在 `tests/test_city_static.py` 新增 `_SCRIPT_SINK_API`，掃描以下寫法：
  - `setAttribute('on…'／'src'／'href'／'srcdoc')`
  - `.src=`、`.href=`、`.srcdoc=`（不含 `==`、`===` 比較）
  - 字串形式的 `setTimeout`／`setInterval`

  新增三個測試，都掛 `SC-155`：
  - `test_sc155_js_never_loads_strings_as_script_or_url`：現行 `city.js` 沒有這些寫法。
  - `test_sc155_script_sink_scan_catches_each_forbidden_form`：8 個違規樣本逐一都要被抓到，避免 regex 寫錯而形同虛設。
  - `test_sc155_script_sink_scan_allows_safe_attributes_and_timers`：`aria-label`、比較運算子、函式型計時器不會誤報。
- **驗證**：
  - pytest 1114 passed（原本 1104，新增 10 個）。
  - `ruff check` 全綠，新檔通過 `ruff format --check`。
  - scenario_lint 結果和修正前相同：160/161 覆蓋，SC-165 是人工量測 WARN；孤兒 test 38 個都是既有的，`test_city_static.py` 沒有新增孤兒。

## 3-3 規則符合度審查

<!-- rules-reviewer subagent 產出（工程準則全面符合度檢查）-->

## 3-4 行為對映審查

審查範圍：33 個 SC（SC-133～166，SC-165 無 marker 屬人工量測）× 217 個 test 掛載（pytest 函式，以 AST 解析 marker）
核准判定：通過（第一段為有條件通過；使用者裁定 3 項、第二段修正完成後無未解不對齊，見「使用者裁定與第二段修正結果」）

### 不對齊

A. marker 掛錯 SC，且有更貼切的 SC（第二段改掛，不刪 marker，避免孤兒 FAIL）
- test_city_geometry.py::test_pit_depth_constants_are_ordered（掛 SC-152）— 驗坑洞深度常數大小，屬 SC-138。改掛 SC-138。
- test_city_geometry.py::test_text_width_by_character_class、test_text_width_empty_string_is_zero、test_short_name_stays_one_line、test_long_name_wraps_at_space、test_long_name_without_space_hard_cuts、test_very_long_name_truncates_second_line_with_ellipsis、test_empty_name_gives_single_empty_line、test_plate_size_with_sub_is_taller_and_wide_enough、test_plate_size_two_lines_adds_line_gap（掛 SC-154）— 驗字寬估算、換行、牌高公式；SC-154 只講「項目數超過 12 只寫名稱」。這些支撐的是 SC-152「名稱牌彼此不重疊、不擋建築」。改掛 SC-152。`test_plate_size_compact_has_name_only` 對齊 SC-154，保留。
- test_city_presentation.py::test_plate_sub_liability_has_prefix（掛 SC-157）— 驗「應繳」前綴，屬 SC-138。改掛 SC-138。
- test_city_payload.py::test_sc139_liability_sub_has_prefix（掛 SC-139）— 同上，屬 SC-138。改掛 SC-138。
- test_city_presentation.py::test_zone_for_asset_and_liability、test_shape_for_zone（掛 SC-157）— 分區與外形對映，屬 SC-152（同分區、負債分區）。改掛 SC-152。
- test_city_presentation.py::test_drift_row_and_notes_by_frame（掛 SC-157）— 驗偏離列、「依目前設定判定」、「含購屋用途金額」註記；SC-157 完全沒提，這是 SC-150 的邊界。改掛 SC-150。
- test_city_presentation.py::test_building_tip（掛 SC-157）— 驗滑過提示：未填無提示、無此項目有註記；屬 SC-140／SC-139。改掛 SC-139 與 SC-140（疊兩個 marker）。
- test_city_static.py::test_sc164_css_defines_neutral_weather_severity_without_diagnostics（掛 SC-164）— 驗中性天氣的 CSS 狀態，與版本下限／打包無關，屬 SC-148。改掛 SC-148。
- test_overview.py::test_sc160_card_shows_hint_without_selection、test_sc160_selected_site_shows_site_card、test_sc160_stale_selection_is_ignored（掛 SC-160）— SC-160 只講版面順序與數字卡固定最新月；這三個驗的是 SC-159（提示、失效選取靜默清除）與 SC-158（點工地小卡）。改掛 SC-159／SC-158（SC-160 其餘兩個測試保留）。

B. 數值／邊界與 SC 不一致
- tests/test_city_layout.py::test_sc153_thirty_buildings_cold_start_within_50ms
  SC 描述：「30 棟項目的冷啟動版位計算在 50ms 內」
  test 內容：`_many_specs(29)`＋工地＝30 個物件，實際只有 29 棟
  判斷：差 1 棟。改為 `_many_specs(30)`（跑完確認仍 < 50ms；試做量到 30 棟約 25～28ms，餘裕足）。
- tests/test_city_layout.py::test_sc154_not_compact_at_threshold／test_sc154_compact_above_threshold（SC-154）
  SC 描述：「項目數超過精簡門檻（12 個）」
  test／實作：`len(specs) > GEOMETRY.compact_n`，specs 含工地。12 個持有項目＋工地＝13 個物件 → 已精簡；SC 字面「12 個項目」不算超過。test 用常數而非字面 12，與實作一致但與 SC 字面差 1。
  判斷：SC 與實作口徑不一致，見下方「需使用者確認」第 1 項。

C. SC 行為有條件未被任何 test 驗證（覆蓋缺口，第二段補測）
- SC-163：THEN「顯示『城市版位暫時無法排出，請參考下方數字』、記 log、數字卡照常顯示」沒有任何 test。`test_city_layout.py::test_sc163_*` 只驗 `layout_city` 拋 CityLayoutError，沒驗訊息文字，`test_overview.py` 也沒有版位失敗的整頁測試（SC-162 的兜底測試用 RuntimeError）。第二段補一個 overview 測試：讓排版拋 CityLayoutError，斷言 st.error 為該文案、log 有紀錄、數字卡 metric 仍在。
- SC-141 AND 子句：「留空月份的天氣、自備款（視為 0）、配置偏離照既有口徑」沒有 test（現有 3 個 test 只驗峰值與分母）。邊界「全部月份留空：名稱牌寬度以『0.0 萬』估算」也沒有 payload 層斷言（只有 layout 驗 peak=0 能排版）。第二段補測。
- SC-142 AND 子句：「比較基準是滑桿上前一個月份，不是日曆上的上個月」。現有 service 測資月份連續（06/07/08），presentation 測試只驗字串不含 2026-08。第二段補一個 frame_at 測試：月份清單 06/07/09，選 09，previous_month 應為 07。

D. 勉強掛載，無更貼切 SC（不阻擋；列為需使用者確認或接受現狀）
- test_city_foundation.py::test_weather_spec_is_frozen（SC-147）、test_building_state_optional_fields_default_none（SC-139）、test_timeline_is_frozen_and_latest_defaults_none（SC-151）；test_city_geometry.py::test_geometry_json_round_trips_every_field、test_geometry_is_immutable（SC-152）；test_core_utils.py::test_converts_each_row_in_order（SC-139）：純型別不可變／預設值／轉換順序，SC 沒寫這些行為。
- test_city_service.py::test_frame_at_rejects_month_not_in_timeline（SC-143）：月份不在清單的 ValueError，SC-143 沒涵蓋。
- test_city_layout.py::test_sc163_specs_without_site_are_rejected、test_sc163_multiple_sites_are_rejected、test_sc163_duplicate_ids_are_rejected（SC-163）：輸入檢查 ValueError，SC-163 只講「無法收斂」，其邊界反而說地塊重疊／出界屬程式錯誤。
- test_city_payload.py::test_sc139_frame_not_aligned_with_timeline_raises_value_error（SC-139）、test_sc152_overlapping_lots／lot_outside_ground／missing_lot（SC-152）：程式錯誤防線；後三者接近 SC-163 邊界「地塊重疊或出界屬程式錯誤」。
- test_overview.py::test_sc161_page_no_longer_exports_transition_alias（SC-161）：檢查 component.py 沒有舊別名字串，是清理驗證，不是 SC-161 行為。
- test_city_static.py::test_sc156_js_reports_selection_only_as_state_value、…keeps_instances_in_weakmap_without_diagnostic_leftovers、…follows_payload_state_contract、…reads_geometry_from_injected_constant_only、…js_has_no_business_text_outside_comments、…component_script_prefixes_geometry_constant、…component_html_has_no_text_or_diagnostics（SC-156）：驗設計決策（AD-7）與實作慣例，SC-156 只要求不依賴身分／機密／資料庫、payload 只含顯示欄位。其餘 SC-156 測試對齊。
- 以上沒有更貼切的 SC，若改為不掛 marker，scenario_lint 會把它們列為孤兒 FAIL。

### 需使用者確認（不擅自改 SC）
1. SC-154 門檻口徑：「項目數超過 12 個」的「項目」是否含工地？實作與 test 含工地（12 個持有項目＋工地即精簡）。若不含，要改 `layout.py` 的判斷與 test；若含，要把 SC-154 改成「物件數（含工地）超過 12」。
2. D 類無 SC 可掛的測試：接受為「勉強掛載」維持現狀，還是補 SC-PENDING（例如「輸入不合法時視為程式錯誤」「結果模型不可變」）把它們收編？
3. SC-163 的 ValueError 輸入檢查（3 個）：是否在 SC-163 邊界補一句「版位輸入不合法（沒有工地、多個工地、id 重複）屬程式錯誤」？補了這三個測試才真正對齊。

### 對齊

| SC | test 函式（代表） | 判斷依據 |
|----|----------|---------|
| SC-133 | test_sc133_assets_and_liability_with_records_enter_layout 等 3 個 | 資產、負債（含只有留空列者）都進版位，id 順序確定 |
| SC-134 | test_sc134_* 3 個 | 購屋用途不進版位、不進分母；標記雙向變更後即時反映 |
| SC-135 | test_sc135_* 2 個 | 無紀錄項目不進版位；首筆紀錄後早期月份無 key（空地） |
| SC-136 | test_sc136_* 2 個 | 月份遞增、最新月含僅負債／購屋月份；無紀錄為空時間軸 |
| SC-137 | test_city_geometry.py::test_sc137_* 7 個＋payload 分母 0 | 400 萬／100 萬／25 萬 → 0.5／0.25，與 SC 數值一致；下限、分母 0、非正值皆驗 |
| SC-138 | test_city_geometry.py::test_sc138_* 5 個＋payload 坑洞規格 | 分母為負債自己的峰值、無峰值或 0 畫最淺 |
| SC-139 | test_city_service.py::test_sc139_*、payload 空地／淡化／保留地塊 | 有值／未填（None）／無此項目（無 key）三態與名稱牌模式 |
| SC-140 | test_sc140_* 4 個＋payload 未填隱藏 | 留空為 None、不沿用前值；未填無名稱牌、無提示、不可點 |
| SC-141 | test_sc141_* 3 個（僅峰值與分母部分） | 留空不入峰值與分母；全空項目峰值 0；資產與負債分母分開（AND 子句見 C） |
| SC-142 | test_sc142_* 6 個 | 130.0 萬、較 2026-07 增加 30.0 萬；減少／持平／最早月／前月無此項目／前月未填／本月未填 文案齊備 |
| SC-143 | test_sc143_* 3 個（service）＋小卡註記 | 歷史月 100 萬約 33%、最新月 180 萬 60%；歷史小卡註明「依目前設定判定」且不含年數與累積 |
| SC-144 | test_sc144_* 3 個 | 從未錄紀錄以初始值每月計入；晚建立項目早期月份不計，08 起計入（60 萬＋90 萬） |
| SC-145 | test_sc145_latest_month_matches_existing_page_results | 以既有 Service 獨立重算天氣、買房進度與條件數、偏離，與城市結果相等 |
| SC-146 | test_sc146_* 4 個 | 五旗固定順序、達成／未達成狀態、目標未設定 |
| SC-147 | test_sc147_* 與 payload 對映 | L0～L3 對晴、多雲、暴雨、颱風；標題含等級名稱；副標回撤 22.0% |
| SC-148 | test_sc148_* 3 個 | 資料不足為中性天空與中性名稱，副標含「資料」文案不含回撤 |
| SC-149 | test_sc149_* 2 個 | 06 月 -5%／L0、09 月 -25%／L2；少於 3 個月為中性 |
| SC-150 | test_sc150_* 6 個＋payload warn | 只標超標類別的建築；僅購屋類別不標；無此項目／未填不掛；含購屋用途註記；歷史月用當月比重 |
| SC-151 | test_overview.py::test_sc151_* | 無紀錄：無元件、無滑桿、有「尚無資料」提示、數字卡照常 |
| SC-152 | test_city_layout.py::test_sc152_* 12 個＋geometry 投影／縮放／名稱牌／障礙物＋payload 規格 | 分區街段、台股美股同街段、1280 寬等多寬度無衝突、落在畫布內 |
| SC-153 | test_sc153_* 其餘 4 個 | 重複排版結果相同、不同輸入互不影響、多執行緒結果一致；50ms 見 B |
| SC-154 | test_sc154_*（版位端旗標）＋test_plate_size_compact_has_name_only | 精簡旗標與只寫名稱；其餘為人工目視（SC 已註明）；門檻口徑見 B |
| SC-155 | test_city_static.py::test_sc155_* 6 個 | 靜態掃描禁用標記解析與字串載入 API；對比檢查程式碼存在（SC 邊界註明實際對比以人工目視） |
| SC-156 | test_city_static.py 前四項（相依、僅 component 引用 streamlit、payload 只含顯示欄位） | 與 SC 描述一致 |
| SC-157 | test_sc157_* 4 個 | 名稱、類別（含負債類別顯示「負債」）、130.0 萬、無此項目註記 |
| SC-158 | test_sc158_* 與 site_sub／site_tip | 180.0 萬／300.0 萬／60%，進度四捨五入，五條條件狀態 |
| SC-159 | test_sc159_*（除 hint 文案為常數對照外皆為行為） | 提示文案；非 id 與失效選取靜默為 None；有效選取保留 |
| SC-160 | test_sc160_city_component_precedes…、test_sc160_number_cards_stay_on_latest… | 城市在協定燈號與指標之前；滑桿拖到 2026-06 數字卡仍為最新月（淨值 502,000） |
| SC-161 | test_sc161_* 其餘 5 個 | 滑桿預設最新月、單月無滑桿、fragment 無參數且數字卡在外、重跑 log 標 kind=fragment；實際重跑範圍 SC 註明為人工量測 |
| SC-162 | test_sc162_city_failure_shows_fallback_and_keeps_number_cards | 兜底訊息、數字卡仍在、log 有 context=城市總覽 |
| SC-163 | test_sc163_non_convergence_raises_city_layout_error、test_sc163_failure_is_not_cached | 無法收斂拋專屬錯誤且不快取；顯示端見 C |
| SC-164 | test_sc164_* 前四個 | 版本下限 ≥ 1.66、資源檔存在、相依集合不變、無外部資源；打包以 uv build 人工核對（SC 已註明） |
| SC-165 | 無 marker | SC 註明人工量測，留 3-Z（使用者決定） |
| SC-166 | test_sc166_js_honors_reduced_motion_preference | 僅確認 JS 含 prefers-reduced-motion 字串，不驗行為；SC 註明以人工目視驗收，使用者已目視通過 |

### 已向使用者確認過的項目判定
- t02（基礎型別補掛）：D 類列出的 6 個勉強；SC-163 CityLayoutError 訊息可顯示、SC-139 留空為 None、SC-152 分區涵蓋、SC-146 條件標籤、SC-148 中性天氣常數則對齊。
- t03（幾何公式掛 SC-152／154）：投影、縮放、名稱牌位置、障礙物對齊 SC-152；字寬／換行／牌高改掛 SC-152（見 A）。
- t04（ValueError 掛 SC-163）：不對齊，列 D 與需確認第 3 項。
- t06（建築逐月狀態掛 SC-140、frame_at 月份不在清單掛 SC-143）：前者可接受（含 SC-140 未填狀態，其 previous／delta 部分屬 SC-142）；後者不對齊，列 D。
- t07（偏離列掛 SC-157）：不對齊，改掛 SC-150（見 A）。
- SC-144 分兩段驗：t05 驗時間軸端（購屋項目不進版位與分母）、t06 驗工地進度端，兩段合起來覆蓋 GIVEN／THEN／邊界，認可。
- SC-154／161／166 視覺部分與 SC-165：依使用者目視與決定，不再追。

### 使用者裁定與第二段修正結果

使用者裁定：
1. SC-154：改 SC 文字為「物件數（含購屋工地）超過精簡門檻（12 個）」，程式不動。現在 SC、實作、test 三者口徑一致，B 類第二項已解。
2. D 類勉強掛載：維持現狀，不補 SC-PENDING。清單與理由見下。
3. SC-163：SC 邊界新增「版位輸入不合法（沒有工地、多個工地、id 重複）屬程式錯誤，不屬本場景」。

**D 類維持現狀清單（約 20 個）與理由**
理由共通：這些測試守的是程式錯誤防線、型別不可變或設計決策（AD-7），不對應使用者可見的業務行為，沒有 SC 可收編；改成不掛 marker 會讓 scenario_lint 報孤兒 FAIL，所以維持掛在最接近的 SC，使用者同意不補 SC-PENDING。
- 型別不可變／預設值／轉換：`test_weather_spec_is_frozen`（SC-147）、`test_building_state_optional_fields_default_none`（SC-139）、`test_timeline_is_frozen_and_latest_defaults_none`（SC-151）、`test_geometry_json_round_trips_every_field`、`test_geometry_is_immutable`（SC-152）、`test_converts_each_row_in_order`（SC-139）。
- 輸入防線：`test_frame_at_rejects_month_not_in_timeline`（SC-143）、`test_sc139_frame_not_aligned_with_timeline_raises_value_error`（SC-139）、`test_sc152_overlapping_lots_raise_value_error`、`test_sc152_lot_outside_ground_raises_value_error`、`test_sc152_missing_lot_for_building_raises_value_error`（SC-152）。
- 清理驗證：`test_sc161_page_no_longer_exports_transition_alias`（SC-161）。
- JS／元件實作慣例（SC-156）：`test_sc156_js_reports_selection_only_as_state_value`、`…keeps_instances_in_weakmap_without_diagnostic_leftovers`、`…follows_payload_state_contract`、`…reads_geometry_from_injected_constant_only`、`…js_has_no_business_text_outside_comments`、`…component_script_prefixes_geometry_constant`、`…component_html_has_no_text_or_diagnostics`。
- SC-163 三個輸入檢查：見下方判斷。

**SC-163 三個輸入檢查測試是否已對齊：沒有**
`test_sc163_specs_without_site_are_rejected`、`test_sc163_multiple_sites_are_rejected`、`test_sc163_duplicate_ids_are_rejected` 驗的行為正是新邊界寫的「版位輸入不合法……不屬本場景」。SC 補完後，這三個測試的行為被 SC 明確劃在 SC-163 之外：行為內容有出處（程式錯誤），但掛 SC-163 與該句字面相反。同理，SC-163 原邊界「地塊重疊或出界屬程式錯誤，不屬本場景」使 SC-152 下三個 payload 地塊驗證測試也屬同類。措辭本身沒有問題，問題是這些測試沒有可掛的 SC。依使用者裁定維持現狀（掛 SC-163／SC-152 只為避免孤兒）。**已回報主 AI，未改 SC。**

**第二段改動**
- marker 改掛（不刪 marker）：
  - SC-138：`test_pit_depth_constants_are_ordered`、`test_plate_sub_liability_has_prefix`、`test_sc139_liability_sub_has_prefix`。
  - SC-152：`test_city_geometry.py` 字寬／換行／牌高 9 個測試、`test_zone_for_asset_and_liability`、`test_shape_for_zone`。
  - SC-150：`test_drift_row_and_notes_by_frame`。
  - SC-139＋SC-140：`test_building_tip`。
  - SC-148：`test_sc164_css_defines_neutral_weather_severity_without_diagnostics`。
  - SC-159：overview 兩個測試，改名為 `test_sc159_card_shows_hint_without_selection`、`test_sc159_stale_selection_is_ignored`。
  - SC-158：改名為 `test_sc158_selected_site_shows_site_card`。
- SC-153：`test_sc153_thirty_buildings_cold_start_within_50ms` 改為 30 棟項目＋工地（`_many_specs(30)`，31 個物件）。實測 7 次共 0.23 秒（單次約 33ms），三輪皆通過，仍小於 50ms。
- 補測：
  - SC-141：`test_city_service.py::test_sc141_blank_month_keeps_existing_weather_house_and_drift_rules`（留空月份累積報酬沿用前值、購屋項目留空視為 0、留空項目不貢獻佔比且建築不掛偏離）、`test_city_payload.py::test_sc141_all_blank_holding_plate_width_is_estimated_with_zero_wan`（全空項目名稱牌以「0.0 萬」估算）。
  - SC-142：`test_city_service.py::test_sc142_previous_month_is_previous_on_slider_not_calendar`（月份 06／07／09 選 09，previous_month 為 07，delta 30.0）。
  - SC-163：`test_overview.py::test_sc163_layout_failure_shows_message_and_keeps_number_cards`（排版拋 CityLayoutError → st.error 為「城市版位暫時無法排出，請參考下方數字」、log 含 context=城市總覽、數字卡淨值 502,000 與買房 bucket 仍在）。

**驗證**
- pytest：1121 passed（原 1117，新增 4 個測試）。
- ruff check：全綠；ruff format 只對動到的 7 個測試檔執行（1 個被重排）。
- scenario_lint：孤兒仍為既有 38 個、無 city 相關；覆蓋 160／161，SC-165 為人工量測 WARN。


## 3-3 規則符合度審查

審查範圍：80 個檔案（含 src 14、views 2、tests 15），main...HEAD（相對 main；本機 origin/main 與 main 一致）
核准判定：阻擋（僅 1 條 HIGH，無需使用者決策，修正範圍小）

### 自動掃描

Checker 命令：`python .claude/skills/spec-driven-flow/scripts/checkers/runner.py --phase 3-3 --project-dir . --diff-base main --json`
總違規：904 條（CRITICAL: 0 / HIGH: 363 / MEDIUM: 63 / LOW: 478）
Baseline 命中：未計（本次未提供 baseline）
完整報告：`.ai/changes/city-overview/.cache/checker_3_3.json`

逐類復核（HIGH 的 363 條絕大多數為偽陽性或專案既有慣例）：
- `root_main_exists`、`src_project_layout_missing`（各 1）— 偽陽性。專案入口是 `app.py` + `bootstrap.py`，views 即 Controller 層（architecture-brief 附錄）。
- `no_runtime_constants_access`／`service_no_runtime_constants`（328 條，含 tests 236）— 判定不違規。命中的都是「列舉鍵、文案、標籤」（`CITY_ZONE`、`CITY_SHAPE`、`CITY_BUILDING_STATUS`、`HOLDING_KIND`、`HOLDING_PURPOSE`），不是 runtime 可調配置值。真正的可調值（`min_data_months`、`rebalance_threshold`）已由 bootstrap 注入 CityService。既有 `house_service` 同寫法，design 亦明載「呈現模組在函式內直接引用列舉與文案」為既有慣例。`bootstrap.py:226-227` 是組裝根，本來就該讀常數。不建議大量補 noqa。
- `no_module_level_constants_alias`（`city/layout.py:39` `_ZONE_TIE_ORDER`）— 見下方 LOW-2。
- `import_block_format`（14 條）— 區塊名稱「專案內部」與既有 `house_service` 等一致，checker 要求的「AsiaYo 專案內部」是偽陽性；但 `city_service.py` 確實缺「原生」區塊，見 MEDIUM-3。
- `docstring_returns_section`（63 條）— 屬實，見 MEDIUM-2。
- `docstring_required`（243 條，tests 239）— src 內 4 條屬實（見 MEDIUM-3）；tests 內測試函式無 docstring 為專案既有做法，忽略。
- `model_naming_convention`（`Cityxxx` 5 條）— 偽陽性。`results.py` 既有 `HouseSummary`、`BucketProgress`、`ProtocolStatus` 等同樣不帶 `Result` 後綴。
- `ANN001/ANN201/ANN202/ANN003/ANN205`（230 條，皆 tests）— 專案 ruff 未啟用 ANN；僅 class-based 測試（`test_city_foundation.py` 等）缺 `-> None`，LOW，不處理。

### 規則審查發現

- [HIGH-1] `views/overview.py` — `_render_card` 在 Controller 層對資料結構做篩選
  `next((h, s) for h, s in zip(timeline.holdings, frame.buildings, strict=True) if city_payload.building_id(...) == selected)` 是依 id 查找項目與狀態的篩選／欄位存取，並順手決定「工地或建築」分支與卡片選擇。
  依據：02-architecture §4 Controller 合約（禁止篩選、欄位存取）；design 與模組 docstring 自述「本頁只讀取、串接與渲染」。
  建議：把「選取 id → CityCard」搬進 `city/presentation.py`（或 `city/payload.py`）的純函式，例如 `card_for(selected, timeline, frame)`；view 只呼叫它並渲染。
  Checker 對應：checker 未報出。

- [MEDIUM-1] `city/payload.py:40-42` — `PLATE_NORMAL`／`PLATE_FADED`／`PLATE_HIDDEN` 應放進 `core/constants.py`（交接事項 3 的判斷）
  這三個字串是 Python 與 `city.js` 共用的契約值（JS 以 `it.mode === 'faded'`、`'hidden'`、`'normal'` 比對），屬業務固定常數，不是模組私有實作細節。同一份契約的 `CITY_ZONE`、`CITY_SHAPE`、`CITY_BUILDING_STATUS` 都在 constants.py，放這裡不一致，且 AD-7 要求「契約鍵由 Python 單一來源」。
  依據：01-coding-style §1 魔法字串；03-data-config §1/§2（業務固定常數入 constants.py）。
  建議：新增 `class CITY_PLATE_MODE: NORMAL / FADED / HIDDEN` 並把 `_PLATE_MODE_BY_STATUS` 改引用它。同理 `layout.py` 的 `SPEC_KIND_*` 與 `payload.SITE_ID` 屬 Python 內部或單點契約，維持原位即可（JS 不比對 `SPEC_KIND_*`；`site: true` 另有旗標，`SITE_ID` 屬 id，無需動）。
  Checker 對應：checker 未報出。

- [MEDIUM-2] 新增 public 函式 docstring 缺 `Returns:` 區塊
  範圍：`city/geometry.py`（`geometry_json`、`project`、`asset_height`、`pit_depth`、`text_width`、`wrap_name`、`plate_size`、`flag_rect`、`plate_rect`、`obstacles`、`fit_scale`）、`city/presentation.py`（`zone_for`、`shape_for`、`amount_text`、`plate_sub`、`site_sub`、`weather_display`、`building_tip`、`site_tip`、`building_card`、`site_card`）、`city/payload.py`（`building_id`、`resolve_selection`、`build_specs`）、`city/component.py`（`component_script`、`selected_in_session`）、`views/overview.py:_select_month`。既有 `main` 的 service、charts 等 public 函式有 Returns/Args 區塊。
  依據：01-coding-style §3 文件規範（public 函式含 Args/Returns）。
  Checker 對應：`docstring_returns_section`（checker 已標）。
  私有 helper（`_` 開頭，約 35 條，含 layout.py 內全部）屬單行 docstring 已說清楚的內部函式，列 LOW，不要求補。

- [MEDIUM-3] 缺 docstring 與 import 區塊
  - `services/city_service.py:33` `CityService.__init__` 缺 docstring（既有 Service 皆有，如 `HouseService.__init__`）。
  - `city/presentation.py:37,45` `CityWeatherDisplay`、`CityCard` 兩個 public dataclass 缺 docstring。
  - `city/__init__.py` 空檔，沿用既有套件空 `__init__` 慣例，忽略。
  - `services/city_service.py` import 只有「第三方」「專案內部」，缺「原生（標準庫）」區塊（規則：無導入也要寫 `# 無`）。
  依據：01-coding-style §2、§3。
  Checker 對應：`docstring_required`、`import_block_format`（checker 已標，其中區塊名稱一項為偽陽性）。

- [LOW-1] `city/geometry.py`、`layout.py`、`payload.py`、`presentation.py` — 「第三方套件 / # 無」與「專案內部」之間沒有空行，區塊間應留空行。ruff 不抓。
  Checker 對應：checker 未報出。

- [LOW-2] `city/layout.py:39` `_ZONE_TIE_ORDER` 模組頂層引用 `CITY_ZONE.*`（checker 標 `no_module_level_constants_alias`）。內容是列舉鍵 tuple，不是 runtime 配置值，與上述慣例一致，判定可接受。若要讓 checker 安靜，可補 `# checker:noqa no_module_level_constants_alias`；不補也不影響判定。

- [LOW-3] 超長檔案（交接事項 2）— 判定不拆。
  - `city/layout.py`（713 行）：`py/` 工程準則內沒有檔案行數上限條文（僅 3-1 checker 的 500 行提示），不構成規則違規。內容是單一演算法（候選產生、間距規則、列距規則、組裝、驗證），內部已用分節註解切開，函式之間高度耦合共用內部型別 `_Obj/_Proto/_Draft`；拆檔會把私有型別變成跨檔 public，得不償失。且這是從試做移植的演算法，拆檔增加驗證風險。
  - `tests/test_city_service.py`（751 行）：同樣無規則依據。若使用者想拆，可依 timeline／frame 分兩檔，純屬偏好，不列為必修。
  Checker 對應：`file_too_long`（3-1 checker 已標）。

- [通過項] 其餘逐條人工檢視均符合：
  - 分層：CityService 是純運算類別、不做 I/O、不 log、不攔例外；`city/*.py` 呈現純模組不碰 st（僅 `component.py`），並有靜態掃描測試；`CityLayoutError` 繼承 `AssetLabError`，由 fragment 兜底處理。
  - DI（交接事項 1）：CityService 建構子注入 5 個 Service 與 2 個配置值，全部 keyword args，bootstrap 組裝時共用同一份 Service 實例；AD-2 偏離 house-dashboard AD-3 的理由合理，Service 內無跨 Service 隱藏建構，與 02 §5 不衝突。
  - Logging（交接事項 4）：新程式碼無 logger，也無 f-string log；`views/overview.py` 既有 stdlib `logging` 沿用專案慣例（附錄已說明），不要求 structlog。
  - Model：`results.py` 新增 `City*` 皆為純資料、frozen，無業務邏輯；`core/utils.records_frame_to_models` 為純函式、無 I/O，符合 02 §8，且已收斂兩份私有重複。
  - 敏感資料：無寫死密鑰；`city.js` 以 textContent、靜態掃描驗證。
  - 魔法字串：除 MEDIUM-1 外，文案、天氣、單位、分區、外形皆在 constants.py。
  - ruff 全綠。

### 第二段修正結果

- HIGH-1：新增 `city/payload.py:card_for(selected, timeline, frame)`，`views/overview.py:_render_card` 改呼叫它，並移除不再使用的 `city_presentation` import。新增 3 個單元測試（`tests/test_city_payload.py`，掛 SC-157／158／159）。
- MEDIUM-1：新增 `core/constants.py:CITY_PLATE_MODE`（NORMAL／FADED／HIDDEN），`payload.py` 的 `PLATE_*` 常數已刪並改引用。
- MEDIUM-2：geometry、presentation、payload、component 與 `views/overview._select_month` 的 public 函式補 `Returns:`（私有 helper 不動）。
- MEDIUM-3：`CityService.__init__` 補 docstring、`presentation.py` 兩個 dataclass 補 docstring、`city_service.py` 補「原生（標準庫）/ # 無」區塊。
- LOW-1：改動後 ruff isort（I001）會要求「# 無」與下一個區塊標題之間不留空行，與專案 ruff 設定衝突，已還原，以 ruff 為準，不再處理。
- LOW-2 不加 noqa；兩個超長檔不拆（依使用者決定）。
- 驗證：pytest 1117 passed（原 1114＋新增 3 個測試），ruff check 全綠，動到的檔案已 ruff format；scenario_lint 孤兒仍為既有 38 個、無 city 相關。
