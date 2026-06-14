# 技術選型分析：initial-build（資產配置管理工具）

> 產出者：tech-researcher｜日期：2026-06-14
> 範圍：本專案為 greenfield，無 `utils_v2/` 現有工具庫，「Existing Internal」層次不適用，全部為新引入工具。
> 原則：proposal 已拍板的主技術棧（Streamlit / Turso / Community Cloud / Google OIDC）僅做可行性確認，不重新推翻；真正開放的選型是 XIRR 函式庫、Turso Python 套件、圖表函式庫三項。

---

## 摘要：本次三項決策

| 主題 | 推薦 | 信心度 | 性質 |
|------|------|--------|------|
| Turso Python 連線套件 | **`libsql`**（非 proposal 寫的 `libsql-client`） | High | 修正 — proposal 套件名已過時 |
| XIRR（MWR）求解 | **`pyxirr`** | High | 釘住 proposal 候選 |
| 圖表函式庫 | **Plotly** 為主（圓餅圖）＋ 視需要 Altair（堆疊面積圖） | Medium | proposal 未指定 |

主結論：**proposal 主技術棧全部可行，可直接進入設計階段**，但需修正一處時效性問題（見下方 TD-1，最高優先）。

---

## TD-1：Turso 連線套件【最高優先 — 需主 AI／使用者確認】

### 解決的痛點
proposal §外部依賴 與 SPEC §二 都寫 `libsql-client`。經查證，**此套件已被 Turso 官方棄用**，且舊的 websocket-based driver 在 Turso 基礎設施從 Fly.io 遷移到 AWS 後已停止運作。沿用舊套件名會導致連線直接失敗或裝不到正確套件。

### 結論
- **正確套件：`pip install libsql`**（官方現行 SDK，透過 HTTP 連遠端 Turso Cloud，無需本地檔案）。
- 用法：
  ```python
  import libsql
  conn = libsql.connect(
      database=st.secrets["turso"]["url"],        # libsql://...turso.io
      auth_token=st.secrets["turso"]["auth_token"],
  )
  ```
- 已棄用、勿用：`libsql-client`、`libsql-experimental`。
- `sqlalchemy-libsql` 為 ORM 場景的官方搭配；本專案資料量極小（一年約 12×N 列）、使用者 SQL 為母語，**不需要 ORM**，直接用 `libsql` + 原生 SQL 即可，避免過度工程。

### 候選方案比較
| 方案 | 優點 | 缺點 | 判定 |
|------|------|------|------|
| `libsql`（官方 HTTP SDK） | 官方現行、遠端連線、無編譯依賴、API 近似 sqlite3 | 需確認 Community Cloud 上 wheel 可用 | **採用** |
| `libsql-client`（proposal 原寫） | — | 已棄用、websocket driver 已隨 AWS 遷移失效 | 否決（時效性） |
| `sqlalchemy-libsql` | ORM、可換後端 | 對 12 列規模＋SQL 母語使用者是過度工程 | 否決 |

### 決策建議
推薦改用 `libsql`，理由：官方唯一現行的遠端連線套件，且原 proposal 寫法已失效。**此項屬 proposal 修正，建議設計階段把 SPEC §二／proposal §外部依賴 的套件名同步更正為 `libsql`。**

---

## TD-2：XIRR / MWR 數值求解 — `pyxirr`

### 解決的痛點
BR-4 / BR-4c 需要 XIRR（金額加權報酬率）數值求解。proposal 明示「避免引入肥大的 scipy」，候選 `pyxirr`，待設計階段定案。

### 結論
- **採用 `pyxirr`（現行 0.10.x，活躍維護）**。Rust 實作，提供 `xirr()`、`irr()`、`npv()` 等財務函式。
- 部署相容性已確認：PyPI 提供 **manylinux x86_64 prebuilt wheel（含 cp312）**，Streamlit Community Cloud（Linux x86_64）可直接 pip 安裝，**無需 C 編譯器、無需 Rust toolchain**，對純 Python 部署環境零摩擦。
- 體積遠小於 scipy（scipy 數十 MB＋BLAS 依賴；pyxirr 為單一輕量 Rust 擴充）。

### 候選方案比較
| 方案 | 優點 | 缺點 | 判定 |
|------|------|------|------|
| `pyxirr` | 輕量、快、有 prebuilt wheel、API 直接給 XIRR | 不收斂時需自行寫 fallback（BR-4 已預期） | **採用** |
| `scipy.optimize`（自寫 Newton/brentq） | 已是科學計算標準 | 肥大依賴、proposal 明確排除 | 否決 |
| 自寫 Newton-Raphson 求解 | 零依賴 | 自行處理收斂/邊界/負現金流，維護成本高、易錯 | 否決（重造輪子） |

### 風險與緩解
- **收斂失敗**：BR-4 已要求 fallback 呈現。設計階段建議：`pyxirr.xirr` 拋例外或回 None 時，降級顯示「MWR 無法計算」並仍呈現 TWR/簡單報酬率，不讓單一指標失敗拖垮整頁。

### 決策建議
推薦 `pyxirr`，信心度 High。完全契合「不引入 scipy」的取捨，且部署環境 wheel 確認可用。

---

## TD-3：圖表函式庫 — Plotly 為主，Altair 視需要

### 解決的痛點
需求含四類圖：圓餅圖（BR-5c）、堆疊面積圖（BR-5d 配置漂移）、折線圖（淨值趨勢 BR-5b、報酬率走勢 BR-5g）。Streamlit 原生 `st.line_chart` 等可畫折線/面積，但**原生不支援圓餅圖**，且 hover/百分比標註客製化有限。

### 結論
- **圓餅圖：必用 Plotly（`px.pie`）或 Altair**——Streamlit 原生無圓餅圖，這是硬需求。
- **折線圖／堆疊面積圖**：Plotly 與 Altair 皆可；為降低心智負擔，建議**單一函式庫統一**，推薦 **Plotly** 作主力：
  - `px.pie`（圓餅）、`px.line`（淨值/報酬走勢）、`px.area`（堆疊面積，`groupnorm='percent'` 直接出百分比堆疊）一套語法到底。
  - 互動性（hover 顯示金額/佔比、圖例點選隱藏分類）開箱即用，貼合「視覺化看變動」的使用情境。
- Altair 為合理替代（grammar of graphics、與 Streamlit 主題整合佳）。若團隊偏好宣告式語法，Altair 同樣勝任堆疊面積圖（`mark_area`）。**二選一即可，不需同時引入兩套。**

### 候選方案比較
| 方案 | 圓餅圖 | 堆疊面積 | 互動性 | 學習曲線 | 判定 |
|------|--------|----------|--------|----------|------|
| Streamlit 原生 | 不支援 | 支援 | 低 | 最低 | 不足（缺圓餅） |
| **Plotly** | px.pie | px.area | 高（開箱） | 中 | **推薦主力** |
| Altair | arc mark | mark_area | 高 | 中（GoG 概念） | 合理替代 |
| Matplotlib | 支援 | 支援 | 無（靜態） | 中 | 否決（無互動、不適合 dashboard） |

### 決策建議
推薦 **Plotly** 一套到底，信心度 Medium（之所以非 High：Altair 是同級可接受替代，屬團隊偏好而非對錯）。關鍵硬約束是「原生無圓餅圖，必須引入第三方圖表庫」。

---

## TD-4：身分驗證 — `st.login()`（已拍板，確認可行）

### 結論（確認，非新決策）
- proposal 採 `st.login()` 原生 OIDC（Streamlit ≥ 1.42）接 Google OAuth — **已驗證為現行官方推薦做法**，1.42 起原生支援 OIDC。
- 設計階段須落實的設定點（皆已在 proposal §已知缺陷列出，此處確認無技術阻礙）：
  - secrets 需 `[auth]` 區塊：`redirect_uri` / `cookie_secret` / `client_id` / `client_secret` / `server_metadata_url`（Google 為 `https://accounts.google.com/.well-known/openid-configuration`）。
  - `redirect_uri` 必須同時登記 localhost:8501（本機）與 `.streamlit.app`（雲端）兩個網址。
  - 登入後比對 `st.user.email` 做單一本人放行（BR-8）。
- **版本下限要求：`streamlit>=1.42`**（設計階段釘進 requirements）。建議直接鎖較新穩定版以涵蓋 1.42 後的 auth 修正。

---

## 整體技術棧確認（給設計階段的 requirements 草案）

| 用途 | 套件 | 版本約束 | 來源決策 |
|------|------|----------|----------|
| UI 框架＋原生 OIDC 登入 | `streamlit` | `>=1.42` | TD-4 |
| Turso 遠端連線 | `libsql` | 現行版 | **TD-1（修正 proposal）** |
| XIRR / MWR | `pyxirr` | 現行 0.10.x | TD-2 |
| 圖表 | `plotly` | 現行版 | TD-3 |
| 資料整形（report 彙總/連乘） | `pandas` | 現行版 | 隱含需求（建議納入，TWR 連乘/區間切分用 DataFrame 最自然） |

> 注：`pandas` 非 proposal 明列，但 TWR 跨月連乘、區間切分（YTD/近一年/自訂）、三維度彙總用 DataFrame groupby 最直接，建議設計階段確認納入。資料量極小，無效能顧慮。

---

## 待確認項目（交接主 AI）

1. **【必確認】Turso 套件名修正**：proposal §外部依賴 與 SPEC §二 的 `libsql-client` 應更正為 `libsql`。此為時效性硬問題（舊套件已隨 AWS 遷移失效），建議設計階段同步更正 SSOT 文件。
2. **【請使用者選擇】圖表函式庫**：Plotly（推薦，一套到底）vs Altair（宣告式替代）。二選一即可，影響語法風格但不影響功能達成。
3. **【建議確認】是否納入 `pandas`**：用於報酬率彙總與連乘的資料整形（推薦納入）。
