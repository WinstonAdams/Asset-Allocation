# Progress: transfer-accumulate-fix

## Phase 1：規劃

| 步驟 | 狀態 | 備註 |
|------|------|------|
| 1-1 提案 | 完成 | 轉移累加＋保留市值、錄入框帶入既有值、本月已存紀錄表＋市值未填提醒、股票/ETF 已實現收益拆為已實現損益＋現金股利兩格；BR-1~7 |
| 1-2a 技術選型 | 跳過 | 無新外部依賴 |
| 1-2b 架構分析 | 跳過 | 沿用前一 Change（stock-total-cost-input）design.md 的架構分析 |
| 1-2 設計 | 完成 | AD-1~7：轉移 SQL 原子累加保留市值、Service 產帶入值＋依資料來源重新播種、寫入後 st.rerun、本月紀錄表、realized_income 存合計＋附加 cash_dividend（否決改名，雲端共用 DB 相容）、股利非負、CSV 附加欄；Q1~Q5 使用者接受推薦值 |
| 1-3 行為規格化 | 完成 | 新增 SC-086~091（6 張）、修訂 SC-008/009/031/074/075/076/078/079/082/083/084/085（12 張）；新卡無 open_questions |
| 1-4 任務拆解 | 完成 | 拆成 t01~t06（見 tasks/）；t01 schema+累加 Repository、t02 MonthlyInputService 純方法、t03 CostBasisService 拆分、t04 CSV 契約、t05 amount_widget 播種機制、t06 View 整合 |

## Phase 2：實作

| Task | 狀態 | 備註 |
|------|------|------|
| t01 monthly_records 加欄（cash_dividend）+ 轉移累加 Repository 方法 | 完成 | SC-006/085/086；cash_dividend 附加欄（idempotent 遷移）、accumulate_net_investments 單一交易 ON CONFLICT 累加保留市值；+11 tests，累計 526 綠 |
| t02 MonthlyInputService 新增純方法（單列帶入值 + 本月已存紀錄彙總） | 完成 | SC-087/089；build_record_prefill（市值 NULL 帶空白）、summarize_month（市值空白即提醒、不分類）；+8 tests，累計 534 綠（未先跑紅燈、未跑 lint，留 2-Z 檢查） |
| t03 CostBasisService 已實現損益／現金股利拆分與非負驗證 | 完成 | SC-074/075/076/078/088/090/091；derive/plan_save 改收 realized_pnl＋cash_dividend、股利負值拒絕、build_cost_basis_prefill；views/input.py 兩處呼叫最小橋接（t06 再整合）；+13 tests，累計 547 綠 |
| t04 CSV records 契約附加 cash_dividend | 完成 | SC-031/084；RECORDS_COLUMNS 7 欄、必填改 RECORDS_COLUMNS[:4]（4 欄與 6 欄舊 CSV 皆可匯入）；+3 tests，累計 550 綠 |
| t05 amount_widget 新增 seed_amount_inputs（帶入重新播種機制） | 完成 | SC-087/088；來源改變或 key 被清掉才重新播種、來源相同保留使用者未存檔輸入；+5 tests，累計 555 綠 |
| t06 views/input.py 整合（累加轉移、帶入既有值、本月紀錄表、股利欄位） | 完成 | SC-086~091、SC-079/080；轉移改 accumulate_net_investments、兩種錄入框接帶入與播種、本月紀錄表＋市值未填提醒、股利兩格＋BR-7 提示、寫入後 flash＋rerun；+17 tests，累計 572 綠；待回報：一般分類無紀錄時市值帶 0（沿用設計預設），SC-087 文字寫「留空」 |
| t07 回繞：無紀錄時市值/總成本/現值留空必填 | 完成 | 2-Z 後使用者決策：該項目該月尚無紀錄時，一般分類市值、股票/ETF 總成本與現值預設留空（不填拒存）；淨投入、已實現損益、現金股利維持 0；SC-087/088 文字同步；574 綠、無新增孤兒 |
| t08 回繞：本月紀錄表欄名改為「已實現收益（損益＋股利）」 | 完成 | 3-3 後使用者決策：仍為一欄合計，只改欄名文案；SC-089 THEN 句與測試斷言同步；先紅後綠，574 綠、無新增孤兒；README 第 5、23 行「已實現收益」一格敘述留給 4-1 |
| 2-Z 整合驗證 | 完成 | 首輪 haiku 誤報 20 個孤兒（以註解式 marker 為判準），主 AI 核對 lint 輸出不成立，升 sonnet 重跑：lint 91/91 SC 覆蓋、38 個既有技術債孤兒、本 Change 新增 0；pytest 572 綠；啟動 health ok 無異常 log；畫面待使用者目視；移除 .auto-gate，Phase 3 恢復逐步確認 |

## Phase 3：審查

| 步驟 | 狀態 | 備註 |
|------|------|------|
| 3-1 程式碼清理 | 完成 | 無必要修正；使用者選做 SUGGEST (1)(2)：抽出 _render_derivation_preview、測試以 fixture 共用 record_repo 替身；574 綠、無新增孤兒 |
| 3-2 安全審查 | 跳過 | 未動登入/付款；使用者確認 Phase 3 範圍為 3-1/3-3/3-4/3-Z |
| 3-3 規則符合度審查 | 完成 | 有條件通過（無 CRITICAL/新增 HIGH）；使用者選修 MEDIUM-1（3 處測試輔助 docstring 補 Returns）＋LOW-3（錄入頁 6 個 widget key 抽常數）；不補 noqa；欄名「已實現收益」另開 t08；574 綠、無新增孤兒 |
| 3-4 行為對映審查 | 完成 | 有條件通過（18 張 SC 無矛盾）；補 SC-075 過渡警語 view test、SC-089 轉移後表格與補值後提醒消失斷言、SC-088 單欄留空 parametrize、SC-086 牽強 marker 改掛 SC-008、SC-084 6 欄 CSV 補 net_investment 斷言；使用者決定 BR-7 提示補進 SC-090；578 綠、無新增孤兒 |
| 3-Z 最終驗證 | 完成 | sonnet 執行：lint 91/91 SC 覆蓋、38 個既有技術債孤兒、本 Change 新增 0；pytest 578 綠；headless 啟動 health ok、log 無例外；畫面待使用者目視 |

## Phase 4：收尾

| 步驟 | 狀態 | 備註 |
|------|------|------|
| 4-1 README 同步 | 未開始 | — |
| 4-2 Windows 啟動器 | 未開始 | 新專案且需啟動器時 |
| 4-3 歸檔 | 未開始 | — |

**狀態值**：未開始 / 進行中 / 完成 / 跳過
