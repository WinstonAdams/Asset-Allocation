# Progress: stock-total-cost-input

## Phase 1：規劃

| 步驟 | 狀態 | 備註 |
|------|------|------|
| 1-1 提案 | 完成 | 股票/ETF 改填總成本＋已實現收益推算淨投入；全站金額欄放大＋整數千分位；BR-1~10 |
| 1-2a 技術選型 | 跳過 | 無新外部依賴；千分位輸入的做法由 designer 於 design.md 決定 |
| 1-2b 架構分析 | 跳過 | 既有架構（View/Service/Repository）已有前兩個 Change 的 design.md 可參照 |
| 1-2 設計 | 完成 | AD-1~10；推算值寫回 net_investment、新增 total_cost/realized_income 欄、CostBasisService、text_input 千分位；待確認 Q1~Q5 依推薦值（auto-gate，Phase 2 後統一回報） |
| 1-3 行為規格化 | 完成 | 新增 SC-074~084（11 張）、更新 SC-008/009/031；SC-075/078 open_questions（分類切換後舊列）主 AI 裁定：視同過渡列套用同一估算規則 |
| 1-4 任務拆解 | 完成 | t01~t09（9 個 Task），依賴鏈：t01→(t02→t03/t04)、t01→t07、t05→t06→(t08/t09) |

## Phase 2：實作

| Task | 狀態 | 備註 |
|------|------|------|
| t01 schema-model-repository | 完成 | monthly_records 加 total_cost/realized_income（可為 NULL）；`_add_column_if_missing` 通用加欄 helper（holdings.purpose 與新兩欄共用）；RecordRepository 擴充至 6 欄＋新增 read_holding_records/upsert_records/delete_record_and_upsert（AD-2/AD-5）；SC-006（機械擴充）；新增 SC-PENDING-001（批次寫入中途失敗的 rollback 保證，待主 AI/使用者裁決）；pytest 442 綠、ruff 綠 |
| t02 cost-basis-derive | 完成 | CostBasisService.uses_cost_basis/derive（建構子注入分類、過渡估算標記 is_transition_estimate）；SC-074/075/076；14 tests，累計 456 綠 |
| t03 cost-basis-recalc | 完成 | CostBasisService.plan_save/plan_delete（AD-4 往後掃描新制列、只回傳有變的列）；SC-077/078；+8 tests，累計 464 綠 |
| t04 cost-basis-transfer-filter | 完成 | CostBasisService.transfer_records_to_write（AD-6，濾掉股票/ETF 端，兩端皆股票回空清單）；SC-079/080；+4 tests，累計 468 綠 |
| t05 amount-format-parse | 完成 | core/utils.format_amount/parse_amount（NFKC、嚴格三位分組、四捨五入遠離零取整）；SC-081/082；+22 tests，累計 490 綠 |
| t06 amount-widget-css | 完成 | amount_widget.amount_input（text_input＋千分位初值＋on_change 正規化）＋inject_amount_input_style（st-key 前綴 CSS 只放大金額欄），app.py 登入後注入；SC-083（視覺效果待 2-Z 啟動驗證）；+14 tests，累計 504 綠 |
| t07 csv-records-contract | 完成 | RECORDS_COLUMNS 尾端附加 total_cost/realized_income，新增 RECORDS_REQUIRED_COLUMNS（舊 4 欄 CSV 可匯入）；SC-031/084；+3 tests，累計 507 綠 |
| t08 input-view-integration | 完成 | Container 組裝 cost_basis_service；views/input.py 股票/ETF 走總成本編輯器（推算預覽、plan_save/plan_delete）、轉移走 transfer_records_to_write、金額欄改 amount_input；+8 UI 機制 tests，累計 515 綠 |
| t09 settings-view-amount-inputs | 完成 | 設定頁初始市值/初始成本、買房四個金額參數改 amount_input，存檔時 parse_amount；非負檢核移交既有 HouseService.validate_params；SC-051 機械更新；累計 515 綠 |
| t10 回繞：新增/改名 test 補 SC marker | 完成 | 2-Z scenario_lint 發現本分支新增 8 個（test_input_view.py）＋改名 2 個（test_settings_view.py）孤兒 test；已補掛 SC-074/077/079/080/081，本分支孤兒歸零，515 綠 |
| 2-Z 整合驗證 | 完成 | 首輪 scenario_lint 失敗（本分支 10 個孤兒 test）→ 回繞 t10；重跑三件事全過：lint 85/85 SC 覆蓋（剩 37 個既有技術債孤兒）、pytest 515 綠、啟動 health ok 無異常 log；金額框視覺效果待使用者目視；SC-PENDING-001 待使用者裁決；移除 .auto-gate，Phase 3 恢復逐步確認 |

## Phase 3：審查

| 步驟 | 狀態 | 備註 |
|------|------|------|
| 3-1 程式碼清理 | 完成 | checker 82 條複核後只修 SAFE 11 處 Change 級編號註解（使用者決策）；SUGGEST（函式過長 ×3、檔案過長 ×1、重複碼 ×71）不動；515 綠 |
| 3-2 安全審查 | 跳過 | 本次未動登入/付款；使用者確認 Phase 3 範圍為 3-1/3-3/3-4/3-Z |
| 3-3 規則符合度審查 | 完成 | 核准通過（無 CRITICAL/HIGH）；checker 282 條複核皆為既有慣例或規則不適用；依使用者決策只補 _FailingCursor.execute 型別提示，read_holding_records docstring 留待未來；515 綠 |
| 3-4 行為對映審查 | 未開始 | AI 比對 SC 描述 vs test 內容 |
| 3-Z 最終驗證 | 未開始 | 重跑 2-Z 三件事，確認審查改動沒破壞 runtime |

## Phase 4：收尾

| 步驟 | 狀態 | 備註 |
|------|------|------|
| 4-1 README 同步 | 未開始 | — |
| 4-2 Windows 啟動器 | 未開始 | 新專案且需啟動器時 |
| 4-3 歸檔 | 未開始 | — |

**狀態值**：未開始 / 進行中 / 完成 / 跳過
