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

<!-- rules-reviewer subagent 產出（工程準則全面符合度檢查）-->

## 3-4 行為對映審查

<!-- scenario-mapper subagent 產出（AI 比對 SC 描述 vs test 內容，分「不對齊」「對齊」兩類）-->
