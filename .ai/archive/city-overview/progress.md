# Progress: [Change 名稱]

## Phase 1：規劃

| 步驟 | 狀態 | 備註 |
|------|------|------|
| 1-1 提案 | 完成 | 使用者確認 proposal；ROADMAP 第 4 節補城市總覽插入條目 |
| 1-2a 技術選型 | 跳過 | 技術試做已驗證路線（見 spike-findings.md），最低版本由設計階段處理 |
| 1-2b 架構分析 | 完成 | architecture-brief.md；使用者裁定 Q1–Q12，已寫回 proposal.md（BR-1/2/7/10/11 修正、新增 BR-13–15）|
| 1-2 設計 | 完成 | design.md；使用者改定 BR-13（市值留空不畫建築與名稱牌），Q-A～Q-E 照預設 |
| 1-3 行為規格化 | 完成 | SC-133～166 共 34 張（接續 archive 最大號 SC-132）；open_questions 依使用者 Q-A～Q-E 定案；lint 孤兒 38 為既有技術債 |
| 1-4 任務拆解 | 完成 | t01～t10 已產出；t02 無 SC 獨立成 Task（使用者確認）|

## Phase 2：實作

| Task | 狀態 | 備註 |
|------|------|------|
| t01 tracer bullet（骨架、元件掛載、下限、打包） | 完成 | SC-164；pytest 873 passed；瀏覽器三項（fragment 重跑範圍、不重掛載、selected 回灌）使用者確認通過；單一選項滑桿未驗，留 t10 |
| t02 常數、例外、共用轉換、結果模型 | 完成 | 基礎型別；測試補掛 SC-139/146/147/148/151/152/163，本分支無新孤兒；pytest 889 passed |
| t03 幾何純模組 | 完成 | SC-137, 138；常數與公式已對照 spike 原始碼，坑洞深度採試做公式 max(6, 44×√(v÷峰值))；pytest 935 passed |
| t04 版位純模組 | 完成 | SC-152, 153, 154, 163；移植試做演算法、去模組級狀態、lru_cache；輸入檢查 ValueError 掛 SC-163 待 3-4 確認；pytest 968 passed |
| t05 CityService.build_timeline＋DI | 完成 | SC-133~136, 139~141, 144（SC-144 只驗時間軸端，工地進度截斷過濾待 t06 補測）；pytest 986 passed |
| t06 CityService.frame_at＋一致性 | 完成 | SC-143, 144（工地截斷過濾端補測完畢）, 145, 149, 150；另補建築逐月狀態測試（掛 SC-140）；pytest 1002 passed；design AD-3 補「第一筆紀錄月份用全量紀錄判斷」 |
| t07 呈現純模組 | 完成 | SC-142, 146~148, 157, 158；另驗 SC-143 小卡註記（t06 交接）；偏離列掛 SC-157 待 3-4 確認；pytest 1031 passed |
| t08 Payload 與 JSON 契約 | 完成 | SC-159；其餘測試掛既有相關 SC；PLATE_* 常數留在 payload.py 待 3-3 判斷；pytest 1076 passed |
| t09 前端 JS/CSS＋靜態掃描 | 完成 | SC-155, 156, 166（＋SC-164 CSS）；人工目視清單併入 t10（使用者決定）；過渡別名 city_overview 待 t10 移除；工地名稱牌優先序維持最後（使用者決定）；pytest 1091 passed |
| t10 總覽頁整合 | 完成 | SC-151, 160~162；t09＋t10 目視使用者確認通過（高度動畫需關閉系統減少動態才看得到）；單一月份不顯示滑桿；SC-165 切頁耗時留 3-Z 量（使用者決定）；pytest 1104 passed |
| 2-Z 整合驗證 | 完成 | scenario_lint 160/161 覆蓋（SC-165 人工量測 WARN），本分支無新孤兒（既有 38 個技術債不計）；pytest 1104 passed；啟動驗證以使用者 t10 本機目視啟動代替（使用者決定）|

## Phase 3：審查

| 步驟 | 狀態 | 備註 |
|------|------|------|
| 3-1 程式碼清理 | 完成 | views 改用共用 records_frame_to_models、刪私有 _to_month_records；測試註解去 SC 編號；layout.py 與 test_city_service.py 超長交 3-3 判斷；pytest 1104 passed |
| 3-2 安全審查 | 完成 | 有條件通過→已修：authlib 1.9.5、joserfc 1.7.7 升級（獨立 commit，使用者本機登入實測通過）；補 JS script sink 靜態掃描；msgpack dev 依賴 CVE 未處理；pytest 1114 passed |
| 3-3 規則符合度審查 | 完成 | 阻擋→已修：小卡篩選移出 views（payload.card_for）、CITY_PLATE_MODE 移入 constants、public 函式補 Returns 與 docstring；LOW-1 與 ruff isort 衝突不改；AD-2 偏離判定合理；超長檔不拆；pytest 1117 passed |
| 3-4 行為對映審查 | 完成 | 有條件通過→已修：marker 改掛約 20 個、SC-153 改真 30 棟、補 SC-141/142/163 測試；SC-154 門檻改「含工地」、SC-163 邊界補輸入錯誤句；約 20 個技術防線測試維持勉強掛載（使用者決定，記於 review.md）；pytest 1121 passed |
| 3-Z 最終驗證 | 完成 | scenario-lint PASS（覆蓋 160/161，SC-165 屬人工量測 WARN，孤兒維持既有 38）；pytest 1121 passed；本機啟動無例外；SC-165 總覽切頁中位數 143ms vs main 118ms（+25ms，上限 100ms 內，不含冷載入） |

## Phase 4：收尾

| 步驟 | 狀態 | 備註 |
|------|------|------|
| 4-1 README 同步 | 完成 | 增量更新：開頭說明、SIPOC、功能、系統架構、新增「關鍵邏輯：城市總覽」、局部重跑、環境需求（Streamlit >= 1.66）、專案結構、注意事項（減少動態效果、瀏覽器目視） |
| 4-2 Windows 啟動器 | 跳過 | 非新專案，不需啟動器 |
| 4-3 歸檔 | 完成 | SC-133～166 共 34 張新建併入專案層 .ai/scenarios/（逐張比對一致）；Change 目錄搬至 .ai/archive/ |

**狀態值**：未開始 / 進行中 / 完成 / 跳過
