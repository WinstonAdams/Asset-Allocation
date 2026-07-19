# Review: [Change 名稱]

## 3-1 程式碼清理

掃描範圍：原始碼 30 檔（src/asset_lab + app.py + pages）＋ 測試 13 檔，20a7ccb..c2d7668（全為 greenfield 新增檔）。
靜態工具：`ruff check .` 全綠（exit 0）；vulture 未安裝（跳過）。
專案脈絡：greenfield、無 utils_v2、AD-8 明定以標準庫 logging 取代 structlog——故 logging 欄位契約偏離不列入本階段清理（屬 AD 既定偏離，3-3 以 ADR 為依據）。

### 自動掃描

Checker 命令：`python .claude/skills/spec-driven-flow/scripts/checkers/runner.py --phase 3-1 --project-dir <資產管理> --diff-base origin/main --json --output .ai/changes/initial-build/.cache/checker_3_1.json`
退出碼：0（正常完成）
總違規：32 條（HIGH 1 / MEDIUM 30 / LOW 1）
Baseline 命中：0 條
完整報告：`.ai/changes/initial-build/.cache/checker_3_1.json`

逐條復核結論：

- **HIGH ×1 `change_level_id_comments`** — `tests/test_monthly_input.py:153` 註解含 `AD-10`。**確認屬實**，已列入 SAFE。注意：本專案 src/tests 內其餘 AD/BR/SC 字樣多為 `@pytest.mark.scenario("SC-xxx")` 標記與 docstring（SSOT test↔scenario 綁定，**必須保留**），唯獨此行是 inline `#` 註解的 dead reference。
- **MEDIUM `function_too_large` ×4**（charts.net_worth_line 51 行、allocation_service.snapshot 52、data_io_service.parse_and_validate 51、return_service._aggregate_monthly 54）— 皆僅略超 50 行門檻，且內部已是線性、單一職責、可讀。**判定不必強拆**（硬拆反增間接層，違背 04 的「函式語意完整優先」），列入 SUGGEST 供斟酌。
- **LOW `file_too_long` ×1**（tests/test_return.py 702 行）— 測試檔，涵蓋 SC-012~024+019/020/021/028 共十餘個情境，**判定可接受**；若 3-1 第二段有餘力可依「TWR / MWR / 三維度 / 走勢」拆檔，列入 SUGGEST。
- **MEDIUM `duplicate_code` ×24** — 絕大多數為**偽陽性 / 不可避免**：bootstrap.py vs test_bootstrap.py 的 repository import 區塊（測試本就須 import 受測對象）、constants.py vs test_data_io.py 的 CSV 欄名清單（前者是 SSOT 定義、後者是測試斷言該契約，移除任一即失去驗證意義）、各測試檔的 `HoldingModel(...)` / `NetWorthPoint(...)` 建構 factory。其中**測試 fixture 重複**（test_allocation / test_net_worth / test_monthly_input / test_charts 的 model 建構）為真實可整合項，列入 SUGGEST（測試輔助，非業務碼，低優先）。

checker **未報出**但人工掃描發現的語意層問題見下方 SAFE / SUGGEST（`adjacent_periods` 死碼、跨 service `_asset_records` 重複、頁面重複 read_range、`"0000-01"` 魔法字串）。

### SAFE

- `src/asset_lab/core/utils.py` — `adjacent_periods`（line 77）為**宣告即死碼**。t01 切片理由聲稱其「被 ReturnService/AllocationService 共用（AD-10 缺月分段連乘前處理）」，但兩個 Service 實際各自內聯分段邏輯（ReturnService 用 `_value_series` + `adjacent` zip、AllocationService 用 `_sorted_data_months`），**全專案無任何 src 端 import**，僅 `tests/test_core_utils.py` 為它而測。屬 TDD/scaffold 殘留。建議：移除 `adjacent_periods` 函式 + 其專屬單元測試（test_core_utils.py:72-106 該測試類）。checker 未報出（vulture 未裝；ruff 不查跨檔死碼）。

- `tests/test_monthly_input.py:153` — 註解 `# 上月已賣出（市值 0 = 出清，AD-10）的項目不帶入...` 含 Change 級編號 `AD-10`（歸檔後成 dead reference）。建議：保留 WHY（出清語意說明確有價值），僅刪去 `，AD-10` marker，改為 `# 上月已賣出（市值 0 = 出清）的項目不帶入新月份；仍持有的照常帶入`。checker 已標（唯一 HIGH）。

### CAREFUL

- 無。本批次無「移除有動態引用風險」的項目；Repository 的 `if TYPE_CHECKING: from libsql import Connection` 屬合法型別提示 import，連線由 bootstrap 延遲 `import libsql` 注入，皆非死碼，**不可移除**。

### RISKY

- 無自行移除即有破壞風險的項目。（`adjacent_periods` 雖列 SAFE，但因 t01 切片理由與實作不一致，移除前建議讓主 AI/使用者確認該函式確無計畫中的後續用途——見交接需決策項。）

### SUGGEST

- `src/asset_lab/services/return_service.py:239` 與 `src/asset_lab/services/allocation_service.py:244` — **跨 service 業務邏輯重複（DRY）**：`_asset_records(range_df, holdings)` 兩處 `@staticmethod` 實作幾乎逐字相同（皆「篩出 kind==ASSET 的 holding_id、過濾 range_df」，即「負債排除」核心口徑）。建議抽為 `core/utils.py` 純函式（無 I/O、無業務流程判斷，符合 §8）或共用 helper，單一定義「資產篩選」口徑，避免日後改負債判定時兩處不同步。checker 未報出（兩段排序/空檢查順序略異，未達連續逐字門檻）。屬 t02~t05 兩平行 Service 疊加後的結構性重複。

- `pages/allocation.py:88,98,111` — 同一頁 render 內 `_render_area` / `_render_net_worth` / `_render_cumulative_twr` 各自發一次 `record_repo.read_range(start_ym="0000-01", end_ym=latest_ym)`，**對 Turso 重複三次全區間讀取**（同參數同結果）。建議在 `render()` 取一次 range_df 後以參數傳入三個子函式（一次 I/O）。屬效能/重複 I/O；雲端 Turso 下三次往返有實際延遲成本。

- `pages/returns.py:77` 與 `pages/allocation.py:88,98,111` — 魔法字串 `"0000-01"` 共出現 4 次，作為「自最早記錄起」的區間下界 sentinel。違反 coding-style §1「禁止散落未定義魔法字串」。建議移至 `core/constants.py` 具名常數（如 `EARLIEST_YEAR_MONTH_SENTINEL = "0000-01"`）。屬命名/魔法字串。

- `src/asset_lab/services/allocation_service.py:34-36`（`_DRIFT_YEAR_MONTH/_DRIFT_DIMENSION_KEY/_DRIFT_WEIGHT`）與 `src/asset_lab/charts.py:28-30`（`_AREA_YEAR_MONTH/_AREA_DIMENSION_KEY/_AREA_WEIGHT`）— 生產者（drift_series 輸出長表欄名）與消費者（堆疊面積圖讀同欄名）各自定義同一組字串常數（`"year_month"/"dimension_key"/"weight"`），為**耦合契約的重複定義**。建議將此長表欄名契約收斂為單一來源（如 constants 或 results 模組常數），兩端引用。低優先。

- `pages/*.py` 的私有 helper（`_container()` 回傳值、`_render_*` 的 `record_repo`/`container`/`holdings` 參數）多數**缺型別提示**（coding-style §3 要求函式參數/回傳填型別）。因 Page 為 Streamlit 黏合層、接的是 Container 已具型別的屬性，影響有限；屬規則符合度範疇，**建議交 3-3 統一判定**，此處僅備註不主動列為清理動作。

- `src/asset_lab/repositories/target_repository.py:59` — `read_all` 僅 `return self.read_targets()`（薄別名）。屬刻意的語意命名（匯出語境用 read_all、設定/偏離用 read_targets，與其他 Repository 的 read_all 對外契約一致），**判定保留**；若日後欲精簡可改 data_io 頁直接呼叫 read_targets。極低優先，僅記錄。

- `tests/test_allocation.py` / `test_net_worth.py` / `test_monthly_input.py` / `test_charts.py` — 重複的 model 建構 factory（`HoldingModel(...)`、`NetWorthPoint(...)`、`points=[...]`，即 checker 報的多筆 MEDIUM duplicate）。可抽共用 fixture 至 conftest.py 或 test helper。屬測試輔助、非業務碼，低優先，第二段有餘力再做。

- `tests/test_return.py`（702 行，checker LOW）— 可依「TWR / MWR / 三維度＋區間 / 走勢」拆為多檔提升可維護性。低優先。

- `asset-allocation-tool-SPEC.md`（repo 根目錄，本次 diff 新增）— 為換資料夾前的「專案規格與決策交接」前置文件，內容已被 `.ai/changes/initial-build/proposal.md` + `design.md` 完整取代。屬已被取代的 scaffold 文件（非程式碼）。**是否移除需使用者決策**（見交接）。

<!-- code-cleaner subagent 產出 -->

## 3-2 安全性審查

審查範圍：src/asset_lab 全樹（access.py、bootstrap.py、4 個 repositories、data_io_service.py）＋ app.py ＋ pages/ 5 檔 ＋ .gitignore ＋ .streamlit/secrets.toml.example。本 Change 為 greenfield initial-build，以 OWASP Top 10 逐維度全檢視。
核准判定：通過（無 CRITICAL / HIGH；唯一 LOW 已於第二段修正，餘 2 條觀察事項維持觀察、無需動作）

### 自動掃描

Checker 命令：`python ../.claude/skills/spec-driven-flow/scripts/checkers/runner.py --phase 3-2 --project-dir . --diff-base origin/main --json --output .ai/changes/initial-build/.cache/checker_3_2.json`
退出碼：0（正常完成）
總違規：0 條（CRITICAL: 0 / HIGH: 0 / MEDIUM: 0 / LOW: 0）
Baseline 命中：0 條
完整報告：`.ai/changes/initial-build/.cache/checker_3_2.json`

**重要前提（scan_targets 為空的成因）**：checker 以 `git diff --merge-base origin/main HEAD` 取掃描目標，而本機 `HEAD == origin/main`（initial-build 全部 commit 已合入 origin/main），故 diff 回 0 檔、scan_targets=[]、0 違規。**這不代表「無程式碼」或「無風險」，而是 diff 基準與已合併狀態重合**。因此本次安全結論完全以下方人工全樹審查為準，checker 0 違規僅作「無新增 diff 級機械違規」的輔助佐證，不替代審查職責。

依賴掃描（第二段已補執行）：`pip-audit` 已加入 dev extras 並裝入 .venv，跑 `.venv/bin/pip-audit` 結果 **No known vulnerabilities found**（唯一 skip 為本地套件 `asset-lab` 自身——未上 PyPI，預期且無安全意涵）。`pip list --outdated` 僅顯示 anyio/certifi/numpy/pydantic_core/pytest/ruff 各落後一個小版本，無安全急迫性。

### 發現

- [LOW — 已修正] A06:依賴與元件 — `pyproject.toml` — 依賴版本下限過寬且未跑 CVE 掃描
  問題：`libsql`、`pyxirr`、`plotly`、`pandas`、`pydantic` 皆無版本下限（僅 `streamlit>=1.42`）。原本環境無 `pip-audit`／`uvx`，無法對已安裝版本（streamlit 1.58.0、pandas 3.0.3、libsql 0.1.11 等）做 CVE 比對，等於少了一道自動化關卡。
  修復（第二段已實施）：
    1. `pyproject.toml` dev extras 加入 `pip-audit`。
    2. 直接依賴補上保守下限（以 .venv 已驗證版本為基準、不過度收緊）：`libsql>=0.1`、`pyxirr>=0.10`、`plotly>=5`、`pandas>=2.2`、`pydantic>=2`；`streamlit>=1.42` 維持不降。
    3. 裝入 .venv 後跑 `.venv/bin/pip-audit`：**No known vulnerabilities found**。
    4. 回歸驗證：`pytest` 179 passed、`ruff check .` All checks passed。
  影響：低；已關閉「缺自動化 CVE 偵測手段」的流程缺口。
  Checker 對應：checker 未報出（3-2 checker 不含依賴 CVE 掃描；且 diff 基準為空）。

- [觀察 / INFO] A09:日誌與監控 — `pages/*.py` — `logger.exception(...)` 寫入完整堆疊
  問題：5 個頁面在 catch `AssetLabError` 時呼叫 `logger.exception(...)`，會把完整 traceback 寫入 stdlib logging。當前被 catch 的僅領域例外（友善中文訊息，不含機密）；但若未來把連線/bootstrap 例外也納入同一 catch，traceback 可能帶出 Turso URL 等連線字串。
  現況判定：**不構成漏洞**。連線建立（`get_connection` 讀 `st.secrets`）發生在 bootstrap、不在這些 catch 範圍內；目前 log 內容不含機密。列為觀察，提醒日後擴大 catch 範圍時須確認不記敏感連線字串。
  Checker 對應：checker 未報出。

- [觀察 / INFO] A09:日誌與監控 — `app.py:67` — `st.caption(f"已登入：{st.user.email}")`
  問題：側欄顯示登入者自身 email。此為**守門放行後**、僅顯示給該使用者本人，且 email 即其登入身分，非他人個資外洩。
  現況判定：**不構成漏洞**，符合常見「顯示目前登入帳號」慣例。列為觀察僅為記錄個資出現點。
  Checker 對應：checker 未報出。

### 各維度逐項結論（OWASP Top 10）

- **A01 權限控制失效**：守門 `_require_access()` 置於 `main()` 最頂、先於 `bootstrap.get_container()`（連線/讀取）與 `st.navigation`，任一未放行決策皆 `st.stop()`，非本人在登入後不會觸發任何 Repository 讀取或頁面渲染。`evaluate_access` 為 fail-closed：未登入→擋、無 email→擋、email 不在清單→擋，僅命中允許清單才放行。**無越權路徑**。（註：此為單一資料庫、單一擁有者模型，無多租戶/RBAC 需求，故無水平越權面。）
- **A02 加密失效**：本程式不自行做加解密；機密（Turso token、OAuth secret、cookie_secret）全交由 Streamlit `st.secrets` 與 `st.login()` OIDC 管理。Turso 連線為 `libsql://`（TLS）。**無自製弱加密**。
- **A03 注入**：所有 SQL（record/holding/schema/target repository）皆參數化 `cursor.execute(sql, (?...))`；SQL 字串中的表名/欄名一律來自 `core/constants.py` 受控常數，**無任何使用者輸入拼接進 SQL**。CSV 匯入經 `DataIoService.parse_and_validate` 驗證性質/分類/唯一鍵/孤兒紀錄後才以參數化 `replace_all` 寫入，數值欄走 `float()`、字串欄落 model，無公式注入回寫風險（匯出用 `df.to_csv`，未對 `=`/`+`/`@` 開頭做 CSV formula-injection 轉義——但本工具 CSV 僅供使用者自身下載/回匯，非分享給第三方開啟，風險可接受，列為極低）。**無 SQL/命令/路徑注入**。
- **A04 不安全設計**：守門邏輯抽為不依賴 Streamlit 的純函式 `evaluate_access`，以單元測試覆蓋三種決策（SC-033/034/039 email 正規化）；fail-closed 為刻意設計（漏設 secrets→空 set→不放行；`StreamlitSecretNotFoundError`→回空 set 而非崩潰）。設計穩健。
- **A05 安全設定錯誤**：`.streamlit/secrets.toml` 已被 `.gitignore` 第 3 行排除（`git check-ignore` 確認命中），磁碟上不存在實體 secrets.toml；`secrets.toml.example` 範本所有值皆為佔位（`PASTE_YOUR_...`、`your-db-name`、`owner@example.com`、`GENERATE_A_RANDOM_HIGH_ENTROPY_STRING`），無真值。`getattr(st.user, ...)` 對 `[auth]` 未設定退化為未登入而非整頁崩潰。**設定安全**。
- **A06 易受攻擊與過時的元件**：見上方 LOW（缺 pip-audit、依賴下限寬鬆）。
- **A07 識別與驗證失效**：採 `st.login()` Google OIDC，零自建密碼/session 機制；session 與 cookie 由 Streamlit OIDC（`cookie_secret`）管理。email 比對前以 `_normalize_email`（strip+lower）正規化兩側，避免大小寫/空白造成誤放行或誤擋。**無自建認證弱點**。
- **A08 軟體與資料完整性失效**：無不安全反序列化——CSV 走 `pd.read_csv`（非 pickle/eval）；無 `pickle.loads`、無 `yaml.load`、無動態 `eval/exec`。`model_dump()` 僅序列化自家 pydantic model 進 session_state。**無風險**。
- **A09 記錄與監控失敗**：見上方兩條觀察。錯誤對使用者僅顯示領域例外友善訊息（`st.error(str(error))`），底層堆疊不噴到畫面。**目前無機密外洩**。
- **A10 SSRF**：本程式不依使用者輸入發出任何外連請求；唯一外連目標 Turso URL 來自受控 `st.secrets`。**無 SSRF 面**。

### 密鑰歷史檢查

`git log --all -p` 全歷史掃描：無 `.env`/`secrets.toml`/`.pem`/`.key` 曾進版控；無任何 JWT(`eyJ`)、`sk-`、`GOCSPX-`、真實 `auth_token` 或真實 `libsql://*.turso` 值（僅範本佔位）；src/pages 無寫死真實 email（僅 `example.com`）。tracked files 僅 `.streamlit/secrets.toml.example`（佔位範本，合法進版控）。**機密零進版控，無需輪換**。

<!-- security-reviewer subagent 產出（涉及認證/付款/個資時才執行） -->

## 3-3 規則符合度審查

審查範圍：原始碼 24 檔（src/asset_lab 全樹 + app.py + pages/ 5 檔），全為 greenfield 新增。git diff vs origin/main 為空（HEAD == origin/main，全部 commit 已合入），故以「整個新建 codebase」為審查對象、逐檔逐條比對工程準則。
專案脈絡：greenfield、**無 utils_v2**（已確認該目錄不存在）；design.md AD-1/AD-2/AD-8 為既定且正當的偏離依據（Streamlit 入口模型取代 RPA main.py、頁面即 Controller、stdlib logging 取代 structlog/biz_job）。ruff（E/F/I/UP/B，line-length 100）全綠。
核准判定：**有條件通過**（無 CRITICAL / HIGH 真實違規；checker 兩條 HIGH 經復核皆為對 ADR 既定偏離的偽陽性；實質發現為 1 MEDIUM + 數條 LOW）

### 自動掃描

Checker 命令：`python <monorepo>/.claude/skills/spec-driven-flow/scripts/checkers/runner.py --phase 3-3 --project-dir . --diff-base origin/main --json --output .ai/changes/initial-build/.cache/checker_3_3.json`
退出碼：0（正常完成）
總違規：2 條（CRITICAL: 0 / HIGH: 2 / MEDIUM: 0 / LOW: 0）
Baseline 命中：0 條
完整報告：`.ai/changes/initial-build/.cache/checker_3_3.json`

> 註：checker 以 `git diff --merge-base origin/main HEAD` 取掃描目標，本機 diff 為空（scan_targets=[]），故兩條 HIGH 屬「專案結構級」靜態檢查（檢 main.py / controllers 目錄是否存在），非 diff 級。

逐條復核：

- **HIGH `root_main_exists`**（checker 已標）「專案根目錄缺少 main.py」— **判定不違規（偽陽性）**。本專案為 Streamlit 互動式 Web App，入口為 `streamlit run app.py`，AD-1 明確記錄「以 Streamlit 多頁 App 取代 RPA main.py 入口模型」並逐項論證 RPA 的 argparse/biz_job/批次退出語意在常駐 Web App 無對應、硬套會產生死碼。checker 規則對應的是 02-architecture §3 main.py 合約，該合約前提是 CLI/RPA 腳本，不適用本專案。屬 ADR 既定且正當的偏離。
- **HIGH `src_project_layout_missing`**（checker 已標）「缺少 asset_lab/controllers 目錄」— **判定不違規（偽陽性）**。AD-2 明定分層為 `Page(View/Controller) → Service → Repository → Model`：頁面（`pages/*.py`）扮演 Controller/View 複合角色，是 Streamlit 社群慣例，符合「流程決策歸 Controller」精神。`services/` `repositories/` `models/` `core/` 皆齊備且職責切分清楚。無獨立 controllers/ 目錄是 AD-2 的刻意設計，非缺漏。
- **checker 未報出**但人工掃描發現的語意層問題見下方「規則審查發現」（pages 型別提示缺漏、import 空區塊空行、薄別名等）。

### 規則審查發現

#### MEDIUM

- [MEDIUM] `pages/input.py`、`pages/allocation.py`、`pages/returns.py`、`pages/settings.py`、`pages/data_io.py` — **私有 helper 與 `_container()` 普遍缺型別提示**
  問題：每頁的 `def _container():`（回傳值無型別）、以及所有 `_render_*` / `_resolve_period` / `_render_results` 的 keyword 參數（`record_repo`、`holding_repo`、`container`、`allocation_service`、`results`、`holdings`、`range_df` 等）缺型別標註。`render() -> None` 與少數已標（`latest_ym: str`、`value: float | None`）為例外。違反 coding-style §3「型別提示：函式參數與回傳值必填」。
  範例：`pages/allocation.py:71 def _render_pie(*, record_repo, allocation_service, holdings, latest_ym: str) -> None:`（前三參數無型別）、`pages/returns.py:90 def _render_results(results) -> None:`、各頁 `def _container():`。
  建議修法：`_container()` 標 `-> Container`（`from asset_lab.bootstrap import Container`）；helper 參數標對應 Repository/Service/Model 型別（`record_repo: RecordRepository`、`holdings: list[HoldingModel]`、`range_df: pd.DataFrame`、`results: list[ReturnResult]` 等）。Page 為 Streamlit 黏合層、接的是 Container 已具型別的屬性，補上即為純機械工，無行為風險。
  影響範圍：5 檔、約 12 個函式簽名。3-1 清理階段已將此項列為 SUGGEST 並註記「建議交 3-3 統一判定」（review.md §3-1 SUGGEST 倒數第 4 條）——本階段確認為應修之規則違規。
  Checker 對應：checker 未報出（ruff 選用集 E/F/I/UP/B 不含 ANN 系列強制型別標註；屬語意層人工檢出）。

#### LOW

- [LOW] `src/asset_lab/repositories/holding_repository.py:12-14`、`schema_repository.py:14-16`、`target_repository.py:11-13`、`services/monthly_input_service.py:21-23`、`services/period_service.py:12-14` 等 — **空 import 區塊（`# 無`）與下一個區塊標頭之間缺空行**
  問題：當「第三方套件」區塊為 `# 無`（無實際 import）時，`# 無` 與接續的 `# ==== 專案內部 ====` 標頭之間沒有空行，形如：
  ```
  # ==== 第三方套件 ====
  # 無
  # ==== 專案內部 ====
  from asset_lab.core.constants import ...
  ```
  嚴格依 coding-style §2「三個區塊、區塊間留空行」應於 `# 無` 後保留空行。**判定為可接受的工具驅動偏離**：本專案 ruff 啟用 `I`（isort），實際有 import 的相鄰區塊間（如「原生」與「第三方」、「第三方」與「專案內部」）凡含真實 import 處皆已正確留空行並通過 I001；唯獨「空區塊（# 無）緊接下一標頭」這一情形，與 isort 對「連續註解 + import 群組」的歸併判定產生張力。implementor 過程已記錄此為「utils import 區塊空行（I001 與風格規則衝突）」的既知偏離。屬純排版、零行為影響、ruff 綠。**建議維持現狀**；若要消弭，可在報告第二段於各空區塊 `# 無` 後補一空行並複跑 ruff 確認仍綠（風險極低）。
  Checker 對應：checker 未報出（ruff I001 通過；屬風格細則人工檢出）。

- [LOW] `src/asset_lab/repositories/target_repository.py:59` — `read_all()` 為 `read_targets()` 的薄別名（`return self.read_targets()`）
  問題：兩方法同結果，純為語意命名（匯出語境用 read_all、設定/偏離語境用 read_targets，與其他 Repository 的 read_all 對外契約一致）。不違反任何硬性規則。3-1 已記錄並判定保留。**判定可接受**，僅記錄，無需動作。
  Checker 對應：checker 未報出。

- [LOW] `src/asset_lab/services/allocation_service.py:34-36`（`_DRIFT_*`）與 `src/asset_lab/charts.py:28-30`（`_AREA_*`）— 長表欄名契約（`"year_month"/"dimension_key"/"weight"`）在生產者（drift_series）與消費者（allocation_area）各自定義一組同值常數
  問題：耦合契約的重複定義，日後改欄名須兩處同步。3-1 已列 SUGGEST（低優先）。不違反硬性規則（兩端皆以具名常數而非散落字面，已優於魔法字串）。**判定可接受**；若第二段有餘力可收斂為單一來源（如 results 模組或 constants 常數），兩端引用。
  Checker 對應：checker 未報出。

### 各規則檔逐項符合度結論

- **01-coding-style**：雙引號、snake_case/PascalCase、kwargs（DI 與多參數方法一律 keyword args，符合）皆遵守。docstring 完整（public 函式/方法/類別含 Args/Returns/Raises、繁中、註解說明 WHY）。型別提示——**Service/Repository/Model/core/charts/bootstrap/app 層完整**，唯 **pages helper 缺型別（上方 MEDIUM）**。Import 三區塊用語正確、`# 無` 佔位保留順序，唯空區塊空行細節（上方 LOW）。魔法字串：`"0000-01"` 已於 3-1 收斂為 `EARLIEST_YEAR_MONTH_SENTINEL`，狀態值/維度名/欄名皆具名常數，未見散落魔法字串。
- **02-architecture**：分層歸屬正確——Service 純運算無 I/O 無 Streamlit（ReturnService/AllocationService/PeriodService/DataIoService 建構子無依賴；MonthlyInputService 經 Protocol 注入 reader 僅讀取、不寫入）；Repository 只做 SQL 執行與 row↔model 轉換、不含業務判斷（資產篩選、目標總和校驗皆在上層）；Page 委派不算業務值。`core/utils.py` `filter_asset_records`/`parse_year_month`/`year_month_add`/`months_between` 為純函式、無 I/O、無流程判斷，符合 §8。Repository 皆有建構子且 conn 由 bootstrap keyword 注入。main.py/controllers 結構偏離為 AD-1/AD-2 既定（見自動掃描復核）。
- **03-data-config**：constants.py 以嵌套 class + 模組級具名常數組織，Sheet-schema 規則不適用（本專案為 Turso 而非 Google Sheet），DB 表/欄 schema 以扁平 class（`HOLDINGS_TABLE` 等）承載、無 URL 混入、無 SCHEMA 中間層，精神一致。Pydantic Model 皆純資料結構（無業務邏輯、無 I/O、無 Service/Repository 呼叫、無 field_validator），Result model 與主檔 model 分離。機密（Turso 憑證、OAuth、允許 email）全走 st.secrets，無寫死（與 3-2 安全審查一致）。`Optional[T]` 改採 `T | None`——見下方既定偏離評估。
- **04-cross-cutting**：Logging 以 stdlib `logging.getLogger(__name__)` 模組頂層宣告、未經建構子注入（保留 §1.1 精神）；不採 structlog event-name/note/log_type 欄位契約為 **AD-8 既定偏離**（無 utils_v2 pipeline，硬套形同空轉）。Error handling：Repository/Service 錯誤往上拋（RecordRepository 將 UNIQUE 衝突、DataIoService 將解析失敗「轉譯例外類型後 raise」屬合法的加 context 轉拋，非吞例外）；**Page 為唯一 catch 點**（取代 RPA Controller 角色），catch 後 `st.error` + `logger.exception`，符合「單一 catch 點、不重複 log、不吞例外」核心原則。DI：runtime 值一律 bootstrap 讀取後 keyword 注入，下層不自行從 constants 提取 runtime 值（Repository 的 `from constants import *_TABLE` 為模組級 schema 常數定義用於組 SQL 字串、非 runtime 環境差異值；屬 §3.2 表中「業務規格 schema」灰區，但本專案無 --env 多環境、表名為全域固定常數，且 SQL 模板須在模組級組裝，判定可接受、非違規）。
- **05-reference**：作為前四檔的具現化參考，差異點（Optional vs |None、structlog vs logging、main.py vs app.py）均已由 AD-1/AD-8 與 UP045 涵蓋。

### 既定偏離評估（implementor 記錄的兩項 + ADR 偏離）

- **`Optional[X]` → `X | None`（ruff UP045 要求）— 可接受**。03-data-config §3 與 05-reference 範例寫 `Optional[T] = Field(default=None)`，但本專案 ruff 啟用 `UP`（pyupgrade），UP045 會將 `Optional[X]` 標為應改寫為 `X | None`（py312 target）。`X | None` 與 `Optional[X]` 語意完全等價，且為 PEP 604 現代寫法。規則檔的 `Optional` 寫法早於工具設定、屬範例用語非硬性禁止 `|`。判定：**遵守 ruff（工具強制）優先，無需改回 Optional**。全 Model/簽名一致採 `X | None`，未見混用。
- **utils import 區塊空行（I001 與風格規則張力）— 可接受**。見上方 LOW；ruff I001 綠、純排版、零行為影響。
- **AD-1 / AD-2 / AD-8（Streamlit 入口、頁面即 Controller、stdlib logging）— 既定且正當**。design.md 逐項論證偏離理由與否決方案，3-1/3-2 亦以此為基準，本階段確認接受。

### 第二段修正結果（使用者裁決範圍：MEDIUM 型別提示 + LOW 空行）

- **[MEDIUM 已修] pages/ 5 檔型別提示補齊**。對 `pages/input.py`、`allocation.py`、`returns.py`、`settings.py`、`data_io.py` 的 `_container()`（回傳型別補 `-> Container`）與全部私有 helper 參數（共 12 個函式簽名）補上正確型別：依設計介面契約使用 `Container`、`RecordRepository`/`HoldingRepository`/`TargetRepository`、`AllocationService`/`ReturnService`/`PeriodService`/`MonthlyInputService`、`list[HoldingModel]`、`list[ReturnResult]`、`pd.DataFrame` 等；並補入對應 import（皆為既有公開類別，無循環引用）。純機械補標，不改任何行為。coding-style §3「函式參數與回傳值必填」此項已關閉。

- **[LOW 未採用——以 ruff 綠為準]** 空 import 區塊（`# 無`）後補空行的嘗試**與 ruff I001 直接衝突，無法兩全**。實測：於 `# 無` 與 `# ==== 專案內部 ====` 間補空行後，`ruff check`（啟用 `I`）報 5 個 I001「Import block is un-sorted or un-formatted」，且 `ruff --fix` 的修法正是**移除**該空行（isort 將 `# 無` 視為附屬於後續 import 群組，群組與其註解間不得有空行）。依使用者裁決的 fallback 條款「ruff 與補空行衝突無法兩全時以 ruff 綠為準」，已 `ruff --fix` 回原狀（5 檔的 `# 無` 緊接 `# ==== 專案內部 ====`，無空行）。此即 implementor 過程記錄的既知偏離（「utils import 區塊空行 = I001 與風格規則衝突」）的最終確認：**coding-style §2「區塊間留空行」與 ruff I001 在「空區塊」情形下不可調和，採 ruff 綠**。其餘 LOW（`read_all` 薄別名、長表欄名常數重複）依裁決維持現狀未動。

- **驗證**：`.venv/bin/ruff check .` All checks passed；`.venv/bin/python -m pytest tests/` **179 passed**（與修正前一致，無迴歸）；`py_compile` 5 頁全過。

<!-- rules-reviewer subagent 產出（工程準則全面符合度檢查）-->

## 3-4 行為對映審查

<!-- scenario-mapper subagent 產出（AI 比對 SC 描述 vs test 內容，分「不對齊」「對齊」兩類）-->

審查範圍：39 個 SC（SC-001~039）× 約 130 個帶 marker 的 test 函式
Marker 覆蓋：39/39 SC 皆有對應 test marker（無孤兒 SC）
核准判定：**有條件通過 → 第二段全數修正完成，現為通過**

比對方式：逐張 SC 讀 `## 行為`（GIVEN/WHEN/THEN）、`## 邊界`、`## 錯誤`，對照掛該 marker 的 test 函式之輸入值、mock 設定與 assertion，判斷 test 是否真的在驗證 SC 寫的行為。

### 第二段修正結果（使用者裁決：全修；只動 test，不改 SC、不改 production 行為）

| 編號 | 處置 | 動作摘要 |
|------|------|---------|
| N1 SC-009 | 改 test | 移除 `test_sc009_sale_month_zero_value_negative_net_investment_recorded`（tautology）；於 repo 層新增 `TestSaleMonthClearoutPersisted` 兩個 test，經 `RecordRepository.upsert_record` 真實寫入後 `read_month`/`read_range` 讀回，驗賣出當月市值 0／淨投入 −530000 被持久化為有效節點（非空列）。`tests/test_monthly_input.py` |
| N2 SC-022 | 補 test | 新增 `TestComputeMwrGapMonths` 兩個 test：直接檢視 `_cash_flows` 確認現金流節點＝有資料月（無 2026-03 缺月節點），並以「多一個真實中途月會改變 MWR」反證缺月未被插值。`tests/test_return.py` |
| N3 SC-021 | 確認歸層後補 test | 確認「無資料不顯示／至少一完整月」不在 `PeriodService.resolve_period`（僅做模式→起訖月映射），而在 `ReturnService` 計算層：空區間→三指標皆 None、`cumulative_twr_series`→空；一個完整月→有值；僅建倉段→None。新增 `TestComputeReturnsRangeBoundaries` 四個 test。`tests/test_return.py` |
| N4 SC-039 | 補 test | 將大小寫＋空白合併案例拆出 `test_case_only_difference_*`、`test_whitespace_only_difference_*` 兩個分離案例（合併案例保留）。`tests/test_access_control.py` |
| O1 SC-033/034 | 補 test（新檔） | 新增 `tests/test_app_guard.py`：以 Streamlit AppTest 實跑 `app.py`，驗未登入→登入入口並停止、非本人→「無權限」拒絕並停止、空允許清單→擋下；三情境皆斷言未組裝依賴容器（`CONTAINER_SESSION_KEY` 不在 session）＝未觸發任何財務資料讀取／未進入頁面路由（fail-closed）。 |

驗證：`pytest tests/` 193 passed（第二段前基線 179 → 淨 +14：N1 −1+2、N2 +2、N3 +4、N4 +2、O1 +5）；`ruff check .` All checks passed；SC marker 覆蓋仍 39/39。
**無修改任何 SC 卡片、無修改任何 production 程式碼**（純 test 異動）。

---

### 不對齊（需第二段處理）

#### N1〔改 test〕SC-009 `test_sc009_sale_month_zero_value_negative_net_investment_recorded`
- 檔案：`tests/test_monthly_input.py:176-181`
- SC-009 THEN：「2026-05 仍捕捉到該項目最後一期報酬與資金流出」「賣出當月的『市值 0』是出清語意」
- test 內容：函式只 `_prev_record(1, "2026-05", 0.0, net_investment=-530000.0)` 建一個 model，然後 `assert record.market_value == 0.0` / `assert record.net_investment == -530000.0`。
- 判斷：**斷言的是 test 自己剛塞進 model 的值，未呼叫任何 production 行為**（無 service/repo 互動）。這是 tautology，掛了 SC-009 marker 卻沒驗到「系統如何捕捉出清語意」。SC-009 的「不帶入後續月份」面向另由 `test_sc009_no_carry_after_sale_month` 與 `test_sc005_sold_item_not_carried` 真正覆蓋，故此函式對 SC-009 無增量驗證價值。
- 建議：改成驗證真實行為（例如經 `RecordRepository.upsert_record` 寫入後讀回，確認市值 0／淨投入 −530000 被持久化為一筆有效紀錄，而非空列），或移除並讓 SC-009 的「出清當月仍是有效紀錄」由 repo CRUD test 承接。

#### N2〔多面向漏測〕SC-022 缺月分段在 XIRR/MWR 維度未涵蓋
- 檔案：`tests/test_return.py:137-162`（`test_sc022_gap_month_segmented_not_filled`、`test_sc022_unsorted_input_is_ordered_chronologically`）
- SC-022 THEN：「TWR 逐段連乘、**XIRR 現金流**、所有圖表節點皆以有資料月為準」
- test 內容：兩個 test 都只呼叫 `compute_twr`，驗 TWR 缺月分段；**無任一 test 對 `compute_mwr`/XIRR 餵入含缺月序列驗證「缺月不補插、以有資料月為現金流節點」**。
- 判斷：SC-022 明列 XIRR 為其行為面向之一，test 僅覆蓋 TWR 面向，XIRR 面向漏測。
- 建議：補一個掛 SC-022 的 test，對 `compute_mwr` 餵入含整月缺漏（如 2026-03 缺）的序列，斷言現金流以有資料月為節點、缺月不插值。

#### N3〔多面向漏測〕SC-021 區間邊界「無資料／至少一個完整月」未驗
- 檔案：`tests/test_period.py`（全檔 7 個 test）
- SC-021 邊界：「區間須涵蓋至少一個完整月報酬」「區間內無資料時不顯示」
- test 內容：`test_period.py` 全部測 `resolve_period`（mode→起訖月映射，含 inception/ytd/last_12m/custom/時區/未知模式/custom 缺日期）。涵蓋 SC-021 主行為（區間切換重算映射）與「Asia/Taipei 時區」邊界，對齊良好；但**「區間內無資料時不顯示」「至少一個完整月」兩條邊界沒有任何 assertion**。
- 判斷：主行為對齊，邊界面向部分漏測。屬「一張 SC 多個面向漏測」。
- 備註：此兩邊界可能落在更上層（呼叫 `compute_returns` / 串接層）才有意義，`resolve_period` 本身不負責。第二段可確認該行為歸屬哪層、是否已被別處隱含覆蓋；若確實無處驗證則補測。

#### N4〔多面向漏測，輕微〕SC-039 大小寫／空白兩觸發未分離驗證
- 檔案：`tests/test_access_control.py:119-128`（`test_uppercase_and_whitespace_email_matches_lowercase_allowlist`）
- SC-039 WHEN：email「僅在『英文字母大小寫』**或**『前後空白』上不同」；邊界區分兩種獨立觸發。
- test 內容：唯一一個 SC-039 test 用 `"  OWNER@Example.TEST  "` 同時帶大小寫＋前後空白，一次測完。
- 判斷：production（`access.py::_normalize_email` = `strip().lower()`）行為正確，但 test 未分離「只有大小寫差異」「只有前後空白差異」兩種單獨情境，多面向合併在一個案例。屬輕微 multi-facet 不足，非錯誤。
- 備註：`tests/test_bootstrap.py` 的 `parse_allowed_emails` 系列（掛 SC-033/034）有獨立驗大小寫去重與空白片段，部分補足；但 access 守門層本身仍只有合併案例。第二段可補兩個分離案例（純大小寫、純空白）。

---

### 觀察事項（非 marker 對映問題，列予主 AI 判斷，第二段不一定要動）

#### O1 SC-033/034「不渲染任何頁面」串接層 THEN 無自動化 test
- SC-033 THEN：「未登入前不渲染任何頁面、不載入任何財務資料」；SC-034 THEN：「不渲染任何頁面、不觸發任何財務資料讀取」。
- 現況：守門「判定」邏輯由 `evaluate_access` 純函式完整覆蓋（`test_access_control.py` granted/denied 三態齊全，且 `test_any_denied_decision_never_grants` 守住 fail-closed 語意），對齊良好。但「擋下時 app.py 確實 `st.stop()`、不渲染頁面」屬串接層副作用——progress（t11／2-Z）稱以 AppTest 驗證過 fail-closed，然**目前 test 樹內查無任何 `AppTest`**（`grep -rn AppTest tests/ src/` 為空）。
- 判斷：SC-033/034 的「判定」面向對映無誤；「停止渲染」面向目前無回歸保護。是否補 AppTest 串接層測試，請主 AI 與使用者決定（屬覆蓋範圍取捨，非既有 test 對映錯誤）。

#### O2 非業務測試檔（已知可接受偏差，承 2-Z）
- `test_core_utils.py`、`test_bootstrap.py` 中 `build_container` 系列無 SC marker，屬基礎設施／純組裝測試，承 2-Z 列「孤兒 FAIL 限此二檔、已知可接受偏差」。本次審查確認其不掛任何 SC marker、不影響 SC↔test 對映完整性，不視為問題。

---

### 對齊（抽樣列示判斷依據；未列者均逐一比對為對齊）

| SC | 代表 test 函式 | 判斷依據 |
|----|---------------|---------|
| SC-001 | test_sc001_add_asset_persists_category_and_initials 等 5 個 | 初始市值 500000／成本 300000、穩定 id、新買=舊持倉兩邊界皆對齊 GIVEN/邊界 |
| SC-002 | test_sc002_add_liability_has_no_category_or_initials | 負債 category/initial_* 皆 None，對齊 THEN |
| SC-003 | test_sc003_history_records_still_bound_to_same_id_after_rename | 改名後 holding_id 與市值序列不變＝連乘輸入不變，對齊 THEN |
| SC-004 | test_sc004_category_change_applies_to_all_history | 改分類後主檔只存當前分類、紀錄無 category 欄＝非時間版本化，對齊 THEN |
| SC-005 | test_sc005_* 7 個 | 帶入清單、市值留空/淨投入 0、首月 fallback、已賣出不帶入皆對齊行為與邊界 |
| SC-006 | test_sc006_edit_updates_in_place_without_duplicate | upsert 不產生重複列、刪除移除，對齊三段 WHEN/THEN |
| SC-007 | test_sc007_strict_insert_duplicate_rejected | insert 重複鍵拋 DataValidationError、原紀錄不污染，對齊錯誤 |
| SC-008 | test_sc008_pair_records_opposite_net_investments | 來源 −50000／目標 +50000、合計 0，對齊 THEN 與「不改整體」邊界 |
| SC-010 | test_sc010_net_worth_is_assets_minus_liabilities | 1000000−200000=800000；無負債=總資產、可為負，對齊行為與邊界 |
| SC-011 | test_sc011_liability_excluded_from_*_weights | 佔比分母僅資產、負債不出現，對齊 THEN |
| SC-012 | test_sc012_chain_links_periods_excluding_net_investment | 1.1³−1=33.1% 且排除淨投入，對齊 |
| SC-013 | test_sc013_extra_capital_not_counted_as_return | (155000−50000−100000)/100000=5%，含 55% 裸算反例，對齊 |
| SC-014 | test_sc014_zero_opening_building_month_excluded | 期初 0 段跳過、自下一段起算 21%，對齊 |
| SC-015 | test_sc015_* 5 個 | 投入=負流、提領=正流、終值=正流、留空沿用，對齊現金流方向 |
| SC-016 | test_sc016_mwr_failure_does_not_affect_twr_and_pnl | 不收斂回 (None,'not_converged')、不拋例外、TWR/PnL 照算，對齊降級語意 |
| SC-017 | test_sc017_pnl_and_simple_return_from_cumulative_cost | 累積成本 400000、賺賠 100000、25%；成本 0 不顯示，對齊 |
| SC-018 | test_sc018_* 6 個 | TWR/MWR 以市值起算、PnL 以成本起算、簽名拒絕混用參數，對齊隔離行為 |
| SC-019 | test_sc019_six/eleven/twelve_month | 6、11 月不年化、12 月年化，對齊邊界 |
| SC-020 | test_sc020_* 6 個 | 三維度各自序列、分類彙總、負債永不入、各維度自身現金流，對齊 |
| SC-023 | test_sc023_insurance_surrender_value_below_premium_is_negative | (250000−300000)/300000=−16.67%，對齊保險口徑 |
| SC-024 | test_sc024_blank_value_carries_forward_previous_month | 留空沿用 250000、不計為變動，對齊 BR-10b |
| SC-025 | test_sc025_* + charts test_sc025_pie_uses_only_asset_weights | 53%/47%、按項目/分類兩粒度、留空不貢獻、圓餅僅資產，對齊 |
| SC-026 | test_sc026_* + test_sc026_area_is_percent_stacked | 各分類跨月佔比、缺月跳過、負債排除、百分比堆疊，對齊 |
| SC-027 | test_sc027_* + net_worth_line 預設/疊加 | 淨值節點＋可疊加總資產/總負債線，對齊 |
| SC-028 | test_sc028_* + cumulative_twr_line 單線 | 累積 TWR 逐月、缺月跳過、僅資產、固定單折線無切換，對齊邊界 |
| SC-029 | test_sc029_drift_is_current_minus_target | 偏離=現況−目標→+8/−8，攜帶現況%/目標%，對齊 |
| SC-030 | test_sc030_abs_drift_equal_to_threshold_not_flagged | 5=5 不標示（嚴格大於）、未設目標不判定，對齊邊界 |
| SC-031 | test_sc031_roundtrip_restores_identical_data_into_empty_db | 三類 CSV 含表頭、匯入空庫還原一致、負債 None 保留，對齊 |
| SC-032 | test_sc032_* 8 個 | 缺表頭/重複鍵/非法 kind/非法分類/非空庫五路徑皆拒並友善訊息，對齊錯誤清單 |
| SC-033 | test_sc033_* + bootstrap parse/allowed_emails | 已登入本人放行、未登入擋下且優先、secrets 缺失 fail-closed，對齊（渲染面向見 O1）|
| SC-034 | test_sc034_* + test_any_denied_decision_never_grants | 非本人/空清單/無 email/空字串皆擋、擋下恆不放行，對齊（渲染面向見 O1）|
| SC-035 | test_sc035_twelve_month_span_with_gaps_still_annualized | 日曆跨度滿 12 月即年化，缺月致實際 3 個有資料月仍年化，對齊 |
| SC-036 | test_sc036_snapshot/drift_skips_zero_total_month | 合計 0 月佔比圖略過、其餘月照常，對齊 |
| SC-037 | test_sc037_* 4 個 | 金額 0/負/來源=目標皆拋 DataValidationError、正金額不同項目通過，對齊防呆 |
| SC-038 | test_sc038_record_referencing_unknown_holding_is_rejected | 孤兒紀錄 holding_id=999 拒整批且點名 999，對齊 |
| SC-039 | test_uppercase_and_whitespace_email_matches_lowercase_allowlist | strip().lower() 後比對放行，對齊（兩觸發分離見 N4）|

---

### 第二段建議修正範圍（待主 AI 與使用者確認）

| 編號 | 方向 | 動作 | 風險 |
|------|------|------|------|
| N1 | 改 test | SC-009 tautology test 改為驗真實 repo 行為，或移除（行為已被其他 test 覆蓋）| 低 |
| N2 | 補 test | SC-022 補 compute_mwr/XIRR 缺月分段 test | 低 |
| N3 | 確認後補 test | 先確認 SC-021「無資料/至少一完整月」邊界歸屬層級，再決定補測或標記為他層職責 | 低 |
| N4 | 補 test | SC-039 補純大小寫、純空白兩分離案例 | 低 |
| O1 | 需使用者確認 | 是否補 app.py 串接層 AppTest 驗「擋下時停止渲染」（progress 稱驗過但 test 樹無此檔）| 中（涉測試策略取捨）|

> 所有「不對齊」項皆指向 test 端（漏測或 tautology），**無一項需要修改 SC 卡片本身**——SC 描述均為合法業務語言且行為自洽。故無「需使用者確認是否改 SC」的阻擋項；O1 屬測試覆蓋策略，非 SC 對映錯誤。
