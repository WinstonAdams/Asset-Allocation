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
