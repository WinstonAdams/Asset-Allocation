# Task t05: 金額千分位純函式 format_amount / parse_amount

## 滿足 Scenarios
- SC-081 (happy)
- SC-082 (錯誤)

## 實作範圍
- src/asset_lab/core/utils.py（新增：`format_amount(value)`、`parse_amount(text, *, field_label)`；NFKC 正規化、嚴格千分位分組比對、四捨五入遠離零取整、`DataValidationError` 帶欄位名稱）
- tests/test_core_utils.py（擴充：SC-081/082 對映）

## 依賴
- 無

## 切片理由
純函式、無 I/O、無業務流程判斷，可獨立於 CostBasisService 與任何 UI 元件之外先行完成與測試；是 t06 UI 元件與後續所有金額欄位改造（views/input.py、views/settings.py）的共同前置。
