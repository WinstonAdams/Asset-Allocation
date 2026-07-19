# Task t01: 專案骨架 + 純資料模型 + core 純函式

## 滿足 Scenarios
- 無（基礎設施 + 純資料結構切片；本切片不直接使 SC 轉 GREEN，但為後續所有 Task 的前置）

## 實作範圍
- `pyproject.toml`（宣告套件與依賴草案：streamlit>=1.42、libsql、pyxirr、plotly、pandas、pydantic；dev：pytest）
- `src/asset_lab/__init__.py`
- `src/asset_lab/models/__init__.py`
- `src/asset_lab/models/holding.py`（HoldingModel）
- `src/asset_lab/models/record.py`（MonthlyRecordModel）
- `src/asset_lab/models/target.py`（TargetAllocationModel）
- `src/asset_lab/models/results.py`（ReturnResult、AllocationSnapshot、NetWorthPoint、DriftRow）
- `src/asset_lab/core/__init__.py`
- `src/asset_lab/core/constants.py`（ASSET_CATEGORIES、HOLDING_KIND、PERIOD_MODE、DEFAULT_REBALANCE_THRESHOLD、YEAR_MONTH_FORMAT、DB 表名/欄名 schema、TIMEZONE）
- `src/asset_lab/core/exceptions.py`（DataValidationError、SchemaError）
- `src/asset_lab/core/utils.py`（year_month_add、parse_year_month、adjacent_periods）
- `tests/__init__.py`
- `tests/conftest.py`（註冊 scenario marker：SC-XXX 與 SC-PENDING-XXX）
- `tests/test_core_utils.py`（core/utils.py 純函式單元測試）

## 依賴
- 無

## 切片理由
全新空專案，必須先建立可被 pytest 收集的測試基礎設施（`tests/` + `conftest.py` 註冊 scenario marker），否則後續任何 Task 的 SC marker 無法掛載。本切片只含「無 I/O、無 Streamlit、無業務流程判斷」的最底層：pydantic 純資料模型、業務常數、純工具函式（`adjacent_periods` 是 AD-10 缺月分段連乘的共用前處理，被 ReturnService/AllocationService 共用，必須最先就緒）。這些是所有上層的型別與常數依賴，先獨立成 commit、零回滾風險。core/utils 的純函式自身可單元測試，故一併納入測試檔；models 為純宣告由後續使用它的 Task 覆蓋。
