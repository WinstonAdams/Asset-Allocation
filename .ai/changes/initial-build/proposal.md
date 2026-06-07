# 資產配置管理工具 — 初版建置 (initial-build)

## 背景動機
個人投資者目前缺乏一個能「每月手動記錄各項資產金額、視覺化配置與變動、並算出真實報酬率」的私有工具。市面工具多需串接行情／券商 API，或把資料攤在第三方平台。使用者（資料工程背景、SQL 為母語）只想要：每月花幾分鐘輸入金額，就能看到資產配置佔比、總資產趨勢，以及**排除每月本金增減後的真實報酬率**。

關鍵痛點：每月會手動增減本金（如某月多投入 5 萬），裸算「期末 ÷ 期初」會把新投入的錢誤算成報酬。必須以淨投入欄位排除資本流動。

## 目標
- 提供 Streamlit 介面，輸入與輸出全部在介面完成，使用者不需手動改資料庫。
- 每月以「每個資產項目一列」的粒度記錄市值與當月淨投入。
- 視覺化資產配置（圓餅圖）與總資產變動趨勢（折線圖）。
- 計算排除資本流動的報酬率，同時提供 TWR（時間加權）與 MWR（金額加權/XIRR），並可拆到整體／分類／單一標的三個維度。
- 資料存於 Turso（雲端 SQLite），免費層、每月一次使用頻率下無閒置喚醒摩擦。
- 部署於 Streamlit Community Cloud（從 GitHub repo 部署），取得常駐公開 URL，免本機啟動；以 viewer allowlist 限定僅本人 email 可檢視，保護財務資料。

## 範圍界定

### 本次做
- Turso 資料表設計（資產項目 × 月份的時間序列，含市值與當月淨投入）。
- Streamlit 月度輸入表單（新增／編輯某月各資產項目的市值與淨投入；資產分類為下拉選單）。
- 資產配置圓餅圖（選定月份各項目／分類佔比）。
- 總資產變動折線圖（跨月趨勢）。
- 報酬率計算：TWR（月報酬連乘）與 MWR（XIRR），維度涵蓋整體、各分類、各單一標的。
- Turso 連線設定：本機透過 `.streamlit/secrets.toml`（納入 `.gitignore`），雲端透過 Community Cloud 後台 Secrets UI；程式一律讀 `st.secrets`。
- 部署到 Streamlit Community Cloud（GitHub repo → share.streamlit.io），並於 app 設定啟用 viewer allowlist 限定本人 email 檢視。

### 本次不做
- 不串接任何行情／財報／券商 API（金額一律手動輸入）。
- 不做多幣別與匯率換算（金額一律以 TWD 輸入與儲存）。
- 不做多使用者／帳號權限（個人單庫使用；存取控制僅靠 Community Cloud viewer allowlist，不自建帳號系統）。
- 不做自動排程、通知、行動 App。
- 不做標的層級的交易明細（只記每月市值與淨投入彙總，不記逐筆買賣）。

## 成功標準
- 能在 Streamlit 介面新增一個月份、為多個資產項目輸入市值與當月淨投入並存入 Turso。
- 圓餅圖正確反映選定月份各項目／分類佔比；折線圖正確反映跨月總資產趨勢。
- 在含「某月額外投入本金」的情境下，報酬率不把新投入金額計為報酬：TWR 與 MWR 數值皆排除資本流動，且整體／分類／單一標的三維度皆可查得。
- Turso 憑證不出現在版控中（本機 secrets.toml gitignore、雲端走 Secrets UI）。
- App 部署於 Community Cloud 並啟用 viewer allowlist，非允許 email 無法檢視。

## 核心業務能力
1. **月度資料錄入**：以 (年月, 資產項目) 為粒度記錄市值與當月淨投入。
2. **配置視覺化**：圓餅圖（佔比）＋ 折線圖（趨勢）。
3. **報酬率計算**：TWR ＋ MWR，三維度彙總。

## 業務規則快照

| # | 規則 | 邊界條件 | 例外 |
|---|------|----------|------|
| BR-1 | 每筆紀錄以 (年月, 資產項目) 為唯一鍵，記錄 `市值` 與 `當月淨投入` 兩欄 | 同月同項目不可重複 | — |
| BR-2 | `當月淨投入` 正值為投入、負值為提領；無資本流動時為 0 | — | — |
| BR-3 | TWR 月報酬率 = (期末市值 − 當月淨投入 − 期初市值) ÷ 期初市值，跨月連乘得區間 TWR | 期初市值為 0（首次建倉月）該月不納入連乘 | 淨投入時點假設待設計階段定案（預設月底） |
| BR-4 | MWR 以 XIRR 計算：把各月淨投入視為現金流、期末市值視為終值，解年化內部報酬率 | 現金流方向需正確（投入為負、提領為正、終值為正） | 無法收斂時須有 fallback 呈現 |
| BR-5 | 報酬率可拆整體／分類／單一標的；分類佔比由單一標的彙總得出 | — | — |
| BR-6 | 所有金額為 TWD，無匯率欄位 | — | — |
| BR-7 | 資產分類為受控清單（下拉選單），初始值：台股/台股ETF、美股/美股ETF、現金/定存、保險 | 清單可後續擴充 | — |
| BR-8 | 存取控制由 Community Cloud viewer allowlist 提供，僅允許指定 email 檢視 app | 不自建帳號／密碼系統 | 本機開發無此限制 |
| BR-9 | Turso 憑證來源：本機 `.streamlit/secrets.toml`（gitignore）、雲端 Community Cloud Secrets UI；程式統一讀 `st.secrets` | 憑證不得進版控 | — |

## 外部依賴與接口契約
- **Turso**（雲端 SQLite）：透過 `libsql-client` 連線；URL 與 Auth Token 由使用者於 https://turso.tech 取得。
- **Streamlit**：UI 框架，提供表單與圖表。
- **Streamlit Community Cloud**：部署平台，從 GitHub repo 部署，提供 Secrets UI 與 viewer allowlist。需先有 GitHub repo。
- **GitHub repo**：作為 Community Cloud 部署來源；secrets 不進 repo。
- **計算依賴**：XIRR 需數值求解（numpy/scipy，實際選型於設計階段定）。

## 環境差異表

| 面向 | 本機開發 | Community Cloud（正式） |
|------|----------|------------------------|
| 啟動 | `streamlit run` | 由 GitHub repo 自動部署 |
| Turso 憑證 | `.streamlit/secrets.toml`（gitignore） | 後台 Secrets UI |
| 存取控制 | 無（本機） | viewer allowlist 限本人 email |
| 閒置行為 | 無 | 約 7 天無流量休眠，下次開啟點一下喚醒 |

## 已知缺陷與待確認
- **淨投入時點假設**：TWR 月報酬公式對「當月淨投入發生於月初/月中/月末」敏感，預設以月底發生（當月淨投入不賺取當月報酬）處理，設計階段確認。
- **分類／單一標的維度的 MWR 現金流歸屬**：XIRR 在子維度需以該維度自身的淨投入與期末市值計算，邊界（標的中途新增、清空、改分類）於設計階段細化。
- **缺月／不連續月份**：跨月連乘與 XIRR 對缺漏月份的處理規則，設計階段定義。
- **Community Cloud viewer allowlist 與 repo 隱私**：免費層 viewer 限制／private repo 數量限制以實際後台為準，部署時確認。
