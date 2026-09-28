# Task t02: CostBasisService — uses_cost_basis + derive（總成本推算淨投入）

## 滿足 Scenarios
- SC-074 (happy)
- SC-075 (邊界)
- SC-076 (邊界)

## 實作範圍
- src/asset_lab/core/constants.py（新增 `COST_BASIS_INPUT` 類別，`CATEGORIES = frozenset({ASSET_CATEGORIES.TW_STOCK, ASSET_CATEGORIES.US_STOCK})`）
- src/asset_lab/models/results.py（新增 `NetInvestmentDerivation`：`previous_total_cost`、`is_transition_estimate`、`net_investment`）
- src/asset_lab/services/cost_basis_service.py（新建檔案：`CostBasisService.__init__(*, cost_basis_categories)`、`uses_cost_basis(*, holding)`、`derive(*, holding, records, year_month, total_cost, realized_income)`）
- tests/test_cost_basis.py（新建檔案：SC-074/075/076 對映）

## 依賴
- t01（`MonthlyRecordModel` 需含 `total_cost`/`realized_income` 欄）

## 切片理由
純運算、無 I/O、無 Streamlit，可用固定紀錄序列窮舉首筆、過渡期、清倉三種前期總成本邊界，不需要 DB。`derive` 是後續連動重算（t03）與轉移過濾（t04）共同依賴的核心公式，必須先獨立成一個可信賴的 commit。
