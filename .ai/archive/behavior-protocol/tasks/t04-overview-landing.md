# Task t04: 總覽落地頁 + 必做/禁止結構化 + 落地頁切換

## 滿足 Scenarios
- SC-049 (happy) — 總覽為登入落地頁，顯示等級燈號、回撤帶、必做/禁止摘要與關鍵指標；L3 僅顯示規則文字不算加碼金額；資料不足時 L0 姿態 + 中性文案、不顯示回撤數值
- SC-050 (happy) — 各級必做/禁止摘要內容忠實對齊協定「情境分級」表（L0–L3）

## 實作範圍
- src/asset_lab/core/constants.py（新增 frozen dataclass `ProtocolLevelSpec`（code/label/band_text/must_do/must_not）與 `PROTOCOL_LEVELS` tuple，L0–L3 內容依 `docs/PROTOCOL.md` §1 表人工謄寫）
- views/overview.py（新增登入落地頁：取 container → `record_repo.latest_year_month()`，None 直接 `no_data` 姿態；否則 `read_range(EARLIEST_YEAR_MONTH_SENTINEL, latest_ym)` → `cumulative_twr_series` → `effective_thresholds(stored=protocol_threshold_repo.read_thresholds())` → `protocol_service.assess(...)` → 依 `level_code` 查 `PROTOCOL_LEVELS` → 渲染燈號/等級/回撤帶 + 必做/禁止 + 指標（累積 TWR / 淨值 via `AllocationService.net_worth_series` / 回撤%）；`no_data`/`insufficient_data` 顯示中性文案 + L0、不顯示紅色警示與回撤數值；`try/except AssetLabError → logger.exception + st.error`；尾端 `render()`）
- app.py（`st.navigation` 清單將 `st.Page("views/overview.py", title="總覽", icon=":material/dashboard:", default=True)` 置於首位，取代原「月度錄入」落地）
- tests/test_overview.py（SC-049/050：等級→spec 查表、L3 僅規則文字、資料不足文案分流、`PROTOCOL_LEVELS` 內容對齊協定表）

## 依賴
- t03（共用 `app.py` nav 累加編輯依序 commit；功能上需 t01 的 `assess`、t02 的 `effective_thresholds` + `protocol_threshold_repo` + `protocol_service`（已於 t02 進 Container））

## 切片理由
整合收尾切片，消費前三個 Task 的成品（判定引擎 + 有效門檻 + 既有 ReturnService/AllocationService 輸出，AD-6 不改核心引擎）並落地為登入首頁。必做/禁止以 `PROTOCOL_LEVELS` 結構化編碼（可查表、可對協定表斷言，SC-050），與總覽渲染同 Task 才能端到端驗證 SC-049 各分支（L2 完整呈現、L3 僅規則文字、資料不足中性文案）。落地頁 `default=True` 切換排最後，確保前置頁面與判定鏈已就緒。

## 備註
- `PROTOCOL_LEVELS` 與 `docs/PROTOCOL.md` §1 須人工同步（design AD-5 / BR-5 已知維護點）；謄寫時以協定文本為準。
- 落地頁由「月度錄入」改「總覽」屬預期需求（design AD-5）；專案層 `.ai/scenarios/` 無既有「錄入頁為落地頁」SC，不需 REMOVED 標記。
