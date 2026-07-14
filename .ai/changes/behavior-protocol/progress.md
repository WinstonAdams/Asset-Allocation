# Progress: behavior-protocol

## Phase 1：規劃

| 步驟 | 狀態 | 備註 |
|------|------|------|
| 1-1 提案 | 完成 | proposal.md 已確認（新增總覽/首頁、行為協定唯讀頁、等級判定、門檻設定頁存 DB）|
| 1-2a 技術選型 | 跳過 | 無新技術選型，沿用既有 Streamlit/Turso 棧與 markdown 渲染 |
| 1-2b 架構分析 | 跳過 | 非 greenfield 但由 designer 直接讀 initial-build design.md 與既有 codebase 整合，不另出 architecture-brief |
| 1-2 設計 | 完成 | design.md 已確認（6 ADR）；回撤基準＝累積 TWR 指數回撤、資料不足<3 月退 L0、落地頁改總覽、門檻存 protocol_thresholds 表、必做/禁止 constants 結構化、零核心引擎改動 |
| 1-3 行為規格化 | 完成 | SC-043~SC-050（8 張）；涵蓋回撤等級判定/門檻設定/協定唯讀渲染/總覽落地頁；open_questions 全數定案（資料不足3月、落地頁改總覽、無紀錄vs資料不足分兩文案）|
| 1-4 任務拆解 | 完成 | 切成 t01–t04（4 個垂直切片）；SC-043~050 全覆蓋；線性相依 t01→t02→t03→t04 |

## Phase 2：實作

| Task | 狀態 | 備註 |
|------|------|------|
| t01 協定判定引擎（assess 純運算） | 完成 | SC-043/044/045；models/protocol.py + ProtocolStatus + constants + protocol_service.assess；回撤含起始基準1.0、達門檻進較深級、<3月退L0分無資料/資料不足；19 tests，累計 226 綠 |
| t02 門檻設定端到端 | 完成 | SC-046/047；比照 target_allocations：protocol_thresholds 表＋Repository＋effective_thresholds/validate_thresholds(0<L1<L2<L3)＋bootstrap 注入＋設定頁區段（非法即拒不落 DB）；13 tests，累計 239 綠 |
| t03 行為協定唯讀頁 + 文件 Repo | 完成 | SC-048；ProtocolDocRepository（__file__ 錨定讀 docs/PROTOCOL.md、失敗轉 ProtocolDocError）＋ views/protocol.py 唯讀渲染 ＋ app.py nav；docs/PROTOCOL.md 一併納入版控；6 tests，累計 245 綠 |
| t04 總覽落地頁 + 必做/禁止結構化 | 完成 | SC-049/050；PROTOCOL_LEVELS 結構化（依 §1 表＋L0）＋ overview_presentation 純函式（查表/狀態→呈現）＋ views/overview.py（default 落地）＋ app.py nav；資料不足分無紀錄/資料不足兩文案退 L0；21 tests，累計 266 綠 |
| t05 行為防火牆提醒改 L1+ 顯示 | 完成 | 驗收回饋（§5.4 回繞）：「只看本系統不看券商App」原綁 L0.must_not，反而只在平時/資料不足顯示、真跌時不顯示。改為僅 L1/L2/L3 顯示、L0 平時乾淨；同步修 SC-050 文字（Change 未歸檔可直接改）＋測試斷言（L0 不含防火牆/大跌文字、L1 含） |
| 2-Z 整合驗證 | 完成 | scenario-lint + pytest + 啟動驗證（fail-fast 順序）|

## Phase 3：審查

| 步驟 | 狀態 | 備註 |
|------|------|------|
| 3-1 程式碼清理 | 完成 | checker MEDIUM×3 復核皆判 false positive/不建議拆分；SAFE 1 項採納（views/overview.py 移除會失效的 Change 級 ADR 編號引用）、SUGGEST 1 項維持現狀（_series() 重複未達 Rule of Three）；pytest 282 綠、ruff 綠 |
| 3-2 安全審查 | 完成 | OWASP 全維度通過；checker 3 條 CRITICAL（SQL 注入）復核為 false positive（表名常數插值、資料值皆參數化綁定）；守門不變量（總覽改落地頁後仍先於一切渲染/DB 存取）與密鑰治理查證通過；LOW×2 中採納 1 項（讀檔失敗訊息移除伺服器路徑，路徑細節留 server log）；pip-audit 無 CVE；pytest 282 綠、ruff 綠 |
| 3-3 規則符合度審查 | 未開始 | 工程準則全面符合度檢查 |
| 3-4 行為對映審查 | 未開始 | AI 比對 SC 描述 vs test 內容 |
| 3-Z 最終驗證 | 未開始 | 重跑 2-Z 三件事，確認審查改動沒破壞 runtime |

## Phase 4：收尾

| 步驟 | 狀態 | 備註 |
|------|------|------|
| 4-1 README 同步 | 未開始 | — |
| 4-2 Windows 啟動器 | 未開始 | 新專案且需啟動器時 |
| 4-3 歸檔 | 未開始 | — |

**狀態值**：未開始 / 進行中 / 完成 / 跳過
