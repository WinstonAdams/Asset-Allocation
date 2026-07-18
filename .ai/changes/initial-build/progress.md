# Progress: initial-build

## Phase 1：規劃

| 步驟 | 狀態 | 備註 |
|------|------|------|
| 1-1 提案 | 完成 | proposal.md 已確認 |
| 1-2a 技術選型 | 完成 | tech-research.md 已產出；發現 Turso 套件名需修正（libsql-client→libsql）|
| 1-2b 架構分析 | 跳過 | greenfield 新專案，無既有 codebase 可分析 |
| 1-2 設計 | 完成 | design.md 已確認（10 條 ADR）|
| 1-3 行為規格化 | 完成 | 34 張 SC（SC-001~034），open_questions 全數定案 |
| 1-4 任務拆解 | 完成 | 11 個 Task（t01~t11），SC 全覆蓋 |

## Phase 2：實作

| Task | 狀態 | 備註 |
|------|------|------|
| t01 專案骨架+模型+core | 完成 | 基礎設施＋core 純函式；25 tests 綠，ruff 綠 |
| t02 ReturnService TWR/PnL | 完成 | BR-4e 簽名隔離；19 tests 綠，累計 44 |
| t03 ReturnService MWR/XIRR | 完成 | SC-015,016；接 pyxirr，不收斂降級；11 tests 綠，累計 55 |
| t04 報酬三維度+區間 | 完成 | SC-019,020,021,028,035；PeriodService＋三維度；21 tests 綠，累計 76 |
| t05 Allocation 佔比/淨值/漂移 | 完成 | SC-010,011,025,026,027,036；22 tests 綠，累計 94 |
| t06 目標偏離/再平衡 | 完成 | SC-029,030；compute_drift 門檻嚴格大於；9 tests 綠，累計 103 |
| t07 MonthlyInput 帶入/轉移 | 完成 | SC-005,008,009,037（轉移防呆）；16 tests 綠，累計 120 |
| t08 Repository+Schema | 完成 | SC-001~004,006,007；libsql CRUD＋insert/upsert 分流；40 tests 綠，累計 143 |
| t09 DataIo CSV 匯出入 | 完成 | SC-031,032,038（孤兒紀錄拒絕）；含表頭標準 CSV 匯出入＋五種拒絕路徑；15 tests 綠，累計 158 |
| t10 登入守門判定 | 完成 | SC-033,034,039（email 正規化）；evaluate_access 純函式；10 tests 綠，累計 168 |
| t11 Streamlit 串接層 | 完成 | bootstrap/app.py/pages/charts；charts+bootstrap 走 TDD（18 tests，累計 186），app.py 守門以 AppTest 驗證 fail-closed；ruff 綠 |
| 2-Z 整合驗證 | 完成 | pytest 186 passed、AppTest 啟動 fail-closed 守門通過；scenario-lint 業務綁定 39/39 全覆蓋且 0 invalid，孤兒 FAIL 限 test_core_utils + test_bootstrap 兩非業務測試檔，列為【已知可接受偏差】（3-Z 重跑勿誤判迴歸）|
| t12 修正 pages/ 自動多頁繞過守門 | 完成 | 驗收回饋（§5.4 回繞）：`pages/`→`views/`（git mv 保留歷史），關閉 Streamlit 檔案系統自動多頁、導覽僅由 st.navigation 驅動；補 tests/test_navigation_guard.py 守門回歸測試（`pages/` 再現或自動多頁被重新偵測即 fail）；SC-PENDING-001 經使用者採用為 SC-040（access-control）；pytest 196 綠、ruff 綠、scenario-lint 40/40 |
| t13 補 streamlit[auth] 依賴 | 完成 | 驗收回饋：`st.login()` 需 Authlib（Streamlit `[auth]` extra），原 `streamlit>=1.42` 未帶 extra，登入時拋 StreamlitMissingAuthlibError（本機與 Cloud 部署皆會失敗）。改為 `streamlit[auth]>=1.42`、venv 裝妥 Authlib 1.7.2、刷新 uv.lock。**鐵則 3 單點小改自理、未經獨立驗收**（改一行依賴＋重裝驗證，無業務邏輯變動、無新增測試）|
| t14 固定瀏覽器分頁標題與圖示 | 完成 | 驗收回饋：st.navigation 預設以當前頁標題當瀏覽器分頁標題，切頁時標籤跟著變。app.py 頂層加 st.set_page_config(page_title="資產管理", page_icon="💰")；補 tests/test_page_config.py（攔截 LocalScriptRunner 讀原始 ForwardMsg 驗證登入/拒絕畫面標題圖示固定＋views 不覆蓋回歸）；SC-PENDING-002 經使用者採用為 SC-041（browser-tab-title，icon 沿用 💰 不變）；pytest 199 綠、ruff 綠、scenario-lint 41/41 |
| t15 修正 secrets 範本 allowed_emails 錯位 | 完成 | 驗收回饋：secrets.toml.example 的 allowed_emails 夾在 [turso] 與 [auth] 之間被 TOML 歸入 turso.allowed_emails，頂層讀不到 → 守門 fail-closed 擋掉本人。移到所有 [section] 之前成頂層 key＋註解提醒；補 test_bootstrap.py 回歸（tomllib 解析範本斷言頂層有 allowed_emails 且不在 turso/auth 內）；pytest 200 綠、ruff 綠、scenario-lint 41/41 |
| t16 Turso 連線 stream 過期自動重連 | 完成 | 驗收回饋：get_connection 以 @st.cache_resource 快取單一 Turso 連線，Hrana stream 閒置隔夜被伺服器端關閉後重用即拋「stream not found」404（本機與 Cloud 長駐皆會發生）。get_resilient_container 以 ensure_schema 探測、失效清雙層快取重連重試一次；SC-PENDING-003 採用為 SC-042 |
| t17 規避 pyarrow mimalloc segfault | 完成 | 驗收回饋：Streamlit 顯示 DataFrame 時 pandas→arrow 轉換觸發 pyarrow 25 內建 mimalloc 在 macOS arm64 的 thread-init segfault（EXC_BAD_ACCESS），整個進程崩潰。設 ARROW_DEFAULT_MEMORY_POOL=system 停用 mimalloc 已驗證可穩住；需在 import streamlit 前於 app.py 頂層設好，使自跑與 Cloud 部署都自動帶上 |
| t18 錄入月份預設當月＋年月下拉選擇 | 完成 | 使用者需求：月度錄入頁「錄入月份」改年+月下拉、預設帶入當月（沿用 Asia/Taipei 時區工具，抽純函式 core/utils.current_year_month 可測；年份範圍當年往前 5 年）；下游 YYYY-MM 介面與 SC-005/008/009/037 行為不變；純 view UX 無新 SC；新增 tests/test_input_view.py（AppTest 驅動）為第三個已接受孤兒測試檔（同 test_core_utils/test_bootstrap 偏差）；12 tests，累計 282 綠 |
| t19 設定頁呈現層調整（性質中文/市值成本無小數/目標比重加%） | 完成 | ①性質 selectbox 用 format_func 顯示中文「資產/負債」、內部值仍 asset/liability；②初始市值/成本 number_input format="%.0f" 去小數、內部仍 float；③目標比重因 Streamlit number_input format 無法附加 % 字面後綴（實測會拋 StreamlitInvalidNumberFormatError），改於 label 加註「（%）」。純呈現層無新 SC；新增 tests/test_settings_view.py（AppTest）為第 4 個已知可接受孤兒測試檔；7 tests，累計 289 綠 |
| t20 現金/定存分類拆為活存/定存＋成本自動帶入＋既有項目編輯入口 | 完成 | ASSET_CATEGORIES.CASH="現金/定存" 拆為 DEMAND_DEPOSIT="活存"/TIME_DEPOSIT="定存"（無既有資料遷移）；5 個測試檔的 ASSET_CATEGORIES.CASH 引用同步改為 DEMAND_DEPOSIT（test_monthly_input.py 實際未引用，無需改）。新增活存/定存分類新增或編輯項目時成本自動帶入市值（可手動覆蓋）：SC-PENDING-004 經使用者採用為 SC-043（適用新增＋改分類、僅活存/定存）。追加需求：`_render_holdings()` 補上既有項目編輯入口（st.expander 每列一個編輯區塊，可改名/分類/市值/成本，委派 HoldingRepository.update_holding），編輯 UI 本身為純委派層不掛 SC（業務正確性已由 SC-003/004 覆蓋），成本同步行為併入 SC-043。304 tests 綠、ruff 綠、scenario-lint marker 綁定正確 |

## Phase 3：審查

| 步驟 | 狀態 | 備註 |
|------|------|------|
| 3-1 程式碼清理 | 完成 | SAFE+主要SUGGEST 已修：移 adjacent_periods 死碼、清 AD-10 註解、抽 filter_asset_records 共用、allocation 頁 read_range 去重、0000-01 入 constants、刪 SPEC.md；179 tests 綠、ruff 綠；checker HIGH 1→0 |
| 3-2 安全審查 | 完成 | OWASP Top 10 全維度通過；唯一 LOW（依賴下限+pip-audit）已修：pip-audit 進 dev extras、直接依賴補保守下限、pip-audit 跑出 No known vulnerabilities、179 tests 綠、ruff 綠 |
| 3-3 規則符合度審查 | 完成 | 有條件通過；補 pages 型別提示（MEDIUM）；import 空行與 ruff I001 不可調和、以 ruff 綠為準（既知偏離）；HIGH 偽陽性屬 AD-1/2 既定偏離；179 tests 綠 |
| 3-4 行為對映審查 | 完成 | 有條件通過；4 落差+1 觀察全在 test 端已補（移 tautology 改驗持久化、MWR 缺月、SC-021 邊界、SC-039 拆案例、補 test_app_guard AppTest 守門回歸）；193 tests 綠，SC 39/39 |
| 3-Z 最終驗證 | 完成 | 三件事全 PASS：scenario-lint 業務綁定 39/39 全覆蓋、0 invalid marker、孤兒 FAIL 仍限 test_core_utils+test_bootstrap（偏差未擴大）；pytest 193 passed；AppTest 啟動 app.py 無 runtime 例外、fail-closed 守門 5 案全綠（SC-033/034 未登入/非本人/空清單）。Phase 3 審查改動未破壞 runtime |

## Phase 4：收尾

| 步驟 | 狀態 | 備註 |
|------|------|------|
| 4-1 README 同步 | 完成 | 全量生成 README.md（SIPOC、功能、架構、報酬率口徑、機密設定、部署） |
| 4-2 Windows 啟動器 | 跳過 | 雲端部署（Community Cloud）、macOS、非 uv，本機僅 streamlit run，不需 Windows 啟動器 |
| 4-3 歸檔 | 未開始 | — |

**狀態值**：未開始 / 進行中 / 完成 / 跳過
