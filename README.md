# 資產配置管理工具（asset-lab）

個人用的資產配置與報酬率管理工具。每月手動輸入各項資產的市值與當月淨投入，工具計算**排除資本流動後的真實報酬率**、視覺化資產配置與淨值變動，並支援負債與目標配置管理。不串接任何行情／財報／券商 API，金額一律手動輸入。

核心難點在報酬率：使用者每月會手動增減本金，單純比較「期末 ÷ 期初」會把新投入的錢誤算成報酬。本工具以「市值＋當月淨投入」兩欄記錄，計算時排除資本流動，提供 TWR、MWR、簡單總報酬率三種口徑。

另針對大跌時的行為紀律，工具內建「大跌行為協定」：以累積 TWR 自歷史高點的回撤幅度判斷目前處於平時／修正／熊市／深熊哪個情境，登入後的總覽頁主動顯示對應的必做／禁止摘要，把「翻文件提醒自己」的自律負擔改由系統承擔。

## SIPOC 總覽

| 項目 | 內容 |
|------|------|
| **Suppliers（供應商）** | 使用者本人（手動輸入）。市值、解約金、外幣換算後金額由使用者自行查得，工具不串任何外部資料源；大跌行為協定亦以自身投組回撤為 proxy，不接行情 API。 |
| **Inputs（輸入）** | 持有項目主檔（項目名、性質＝資產／負債、分類、初始市值、初始成本）、每月各項目的市值與當月淨投入（負債記餘額）、各分類目標比重、大跌協定回撤門檻（L1/L2/L3）。 |
| **Process（流程）** | 月度錄入（自動帶入上月仍持有項目）→ 寫入 Turso → 計算報酬率／淨值／配置佔比／目標偏離／協定等級 → Plotly 視覺化＋總覽儀表；另提供 CSV 匯出與還原。 |
| **Outputs（輸出）** | 配置圓餅圖、配置漂移堆疊面積圖、淨值趨勢折線、累積 TWR 走勢、三維度報酬率與賺賠金額、再平衡提示、協定等級燈號與必做／禁止摘要、行為協定全文、CSV 備份；資料存於 Turso 雲端 SQLite。 |
| **Customers（客戶）** | 使用者本人（單一使用者，以 Google 登入＋email 允許清單控管）。 |

## 功能

- 月度資料錄入：以 (年月, 項目) 為粒度記錄市值與當月淨投入；錄入月份以年＋月下拉選擇、預設帶入當月；新月份自動帶入上月仍持有項目，只需更新數字；支援新增／編輯／刪除單列與「項目間轉移」成對輸入。
- 持有項目主檔：以穩定 ID 識別項目（改名不斷裂歷史報酬連乘），每個資產項目歸屬一個分類（含活存／定存／台股／美股／保險等）並記初始市值與初始成本；活存／定存新增或編輯時初始成本自動帶入初始市值（可手動覆蓋）；既有項目可就地編輯改名／改分類／改初始值。
- 負債與淨值：負債項目每月記餘額，淨值＝總資產 − 總負債；負債排除於配置佔比與報酬率之外。
- 報酬率計算：TWR（時間加權）、MWR（XIRR 金額加權）、簡單總報酬率（相對成本）三種，加上絕對賺賠金額，可拆整體／分類／單一標的三維度；計算區間可選（自開始記錄以來／YTD／近一年／自訂）。
- 配置視覺化：單月資產佔比圓餅圖、配置佔比隨時間漂移的堆疊面積圖、淨值趨勢折線（可疊加總資產／總負債）、累積 TWR 走勢折線。
- 目標配置：設定各分類目標比重，顯示現況對目標的偏離，超過門檻提示再平衡。
- 大跌行為協定：登入後總覽頁顯示目前協定等級（L0 平時／L1 修正／L2 熊市／L3 深熊）、該等級必做／禁止摘要與關鍵指標（累積 TWR、淨值、目前回撤%）；等級門檻可於設定頁調整並持久化；另有唯讀頁完整呈現協定全文（`docs/PROTOCOL.md`）。
- 資料保全：CSV 匯出與匯入還原（成對）。

## 系統架構與流程

採分層架構，相依方向單向（Page → Service → Repository → Model）；Service 為純運算、不碰 I/O 與 Streamlit，故可獨立單元測試。

1. `app.py` 入口：登入守門（未登入顯示登入入口、非本人顯示拒絕，皆停止後續渲染）→ 組裝依賴容器（連線與建表就緒，連線失效時自動清快取重連重試一次）→ `st.navigation` 多頁路由，登入後預設落地頁為「總覽」。
2. 各 `views/` 頁面為 View／Controller：讀使用者操作 → 委派 Service 運算 → 經 Repository 存取 Turso → 以 Plotly 呈現。頁面路由僅由 `app.py` 的 `st.navigation` 註冊——資料夾刻意不命名為 `pages/`，因該名稱是 Streamlit 保留字，會觸發框架自動多頁探索，使子頁可繞過登入守門直接以 URL 存取。
3. `services/` 純運算：報酬率三管線、配置／淨值／漂移、目標偏離、月度錄入整形、CSV 匯出入驗證、大跌協定等級判定（`ProtocolService`）。
4. `repositories/` 以 `libsql` 連 Turso，四張表（持有項目主檔、月度紀錄、目標配置、協定回撤門檻），月度紀錄以 (holding_id, year_month) 複合主鍵保證同月同項目唯一；另有 `ProtocolDocRepository` 以 `__file__` 錨定路徑唯讀讀取 repo 內 `docs/PROTOCOL.md`。

### 關鍵邏輯：報酬率口徑

報酬率的正確性是本工具的核心，三種口徑的「起算基準」嚴格分工，不可混用：

- **TWR／MWR（%）以「初始市值」起算** — 衡量開始記錄後的投資績效。TWR 逐月以 `(期末市值 − 當月淨投入 − 期初市值) ÷ 期初市值` 連乘排除資本流動；MWR 以 pyxirr 解現金流年化內部報酬率，不收斂時降級不拖垮其他指標。
- **絕對賺賠金額與簡單總報酬率以「初始成本」起算** — 含記錄前歷史。累積成本＝初始成本＋Σ後續淨投入；賺賠＝市值 − 累積成本；簡單總報酬率＝賺賠 ÷ 累積成本。
- 之所以分工：若把記錄前的成本到現值價差塞進第一期，會讓 TWR/MWR 失真。介面以函式簽名強制隔離（TWR/MWR 管線拿不到初始成本，反之亦然）。

其他規則：未滿 12 個日曆月的區間只顯示累積報酬、不年化；缺月以相鄰有資料月分段連乘、不補插；某月市值留空＝沿用上一有值月份；賣出當月記市值 0＋提領淨投入、之後缺列＝不再持有；外幣資產由使用者換算為 TWD 輸入，報酬率因此內含匯率波動（看台幣淨值，為刻意取捨）。

### 關鍵邏輯：大跌行為協定等級判定

工具無任何行情 API，因此「大盤回撤」以使用者自身投組的**累積 TWR 成長指數**自歷史高點的回撤幅度當 proxy（不用淨值序列，因淨值會混入資金進出與負債變動而失真；累積 TWR 天生排除資本流動，且與 `docs/PROTOCOL.md` 本身「看累積 TWR 走勢」的指示一致）。歷史高點計算納入起始基準 1.0，避免只跌不漲的投組低報跌幅。

- 四級門檻預設 L1 −10%／L2 −20%／L3 −30%（正幅度百分比），回撤深度達門檻即進入該級（含邊界）；可於設定頁調整，並強制驗證 0 < L1 < L2 < L3。
- 累積 TWR 有效月數少於 3 個月時視為資料不足，一律退回 L0 平時姿態、不誤報大跌，且區分「尚無資料」與「資料不足」兩種文案。
- 各等級的必做／禁止摘要在程式內以結構化常數編碼（依 `docs/PROTOCOL.md` §1 表謄寫）；「只看本系統、不看券商 App」等行為防火牆提醒僅在 L1 以上（真的偵測到下跌）才顯示，L0 平時維持乾淨、不冗贅提醒。

## 環境需求

- Python >= 3.12
- 一個 Turso 資料庫（雲端 SQLite，免費層即可）
- 一組 Google OAuth 2.0 用戶端（供 `st.login()` OIDC 登入）

## 機密設定

本專案不使用 `.env`，機密走 Streamlit 的 `st.secrets`。本機開發複製範本並填入實際值：

```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
```

`secrets.toml` 已被 `.gitignore` 排除、絕不可進版控；雲端部署改用 Community Cloud 後台 Secrets UI 貼上相同結構。

| 設定鍵 | 必填 | 說明 |
|--------|------|------|
| `turso.database_url` | 是 | Turso 資料庫 URL（`libsql://...turso.io`），於 https://turso.tech 取得 |
| `turso.auth_token` | 是 | Turso 存取權杖，等同資料庫密碼 |
| `allowed_emails` | 是 | 允許登入檢視的 Google email 清單（陣列或逗號字串）；漏設＝不放行任何人 |
| `auth.client_id` / `auth.client_secret` | 是 | Google OAuth 2.0 用戶端憑證 |
| `auth.redirect_uri` | 是 | OIDC 回呼網址（本機 `http://localhost:8501/oauth2callback`、雲端為 `.streamlit.app` 對應網址，兩者都要登記到 Google） |
| `auth.cookie_secret` | 是 | session cookie 簽章用高熵隨機字串（自行產生） |
| `auth.server_metadata_url` | 是 | OIDC metadata，Google 固定為 `https://accounts.google.com/.well-known/openid-configuration` |

## 安裝

```bash
cd 資產管理
pip install -e ".[dev]"
```

## 執行

本機開發：

```bash
streamlit run app.py
```

啟動後於瀏覽器以允許清單內的 Google 帳號登入即可使用。

部署：推送到 GitHub repo，於 [Streamlit Community Cloud](https://share.streamlit.io) 連結該 repo、指定主檔 `app.py`，並在後台 Secrets UI 貼上與 `secrets.toml` 相同的內容；Google OAuth 的 redirect_uri 需加入雲端網址。

測試：

```bash
pytest          # 全套行為與單元測試
ruff check .    # 風格與靜態檢查
pip-audit       # 依賴漏洞掃描
```

## 專案結構

```
資產管理/
├── app.py                       # Streamlit 入口：登入守門 → 依賴組裝 → 多頁路由（總覽為預設落地頁）
├── views/                       # 功能頁（overview/input/allocation/returns/protocol/settings/data_io；非 `pages/`，避免觸發 Streamlit 自動多頁探索）
├── src/asset_lab/
│   ├── models/                  # pydantic 資料模型（項目/紀錄/目標/協定門檻/結果）
│   ├── core/                    # 常數（含協定等級結構）、例外、純工具、登入存取判定
│   ├── repositories/            # Turso (libsql) 資料存取與建表、協定文件唯讀讀取
│   ├── services/                # 報酬率/配置/淨值/錄入/匯出入/大跌協定判定 純運算
│   ├── charts.py                # Plotly 圖表元件
│   ├── overview_presentation.py # 總覽頁純呈現轉換（等級查表、狀態→顯示資料）
│   └── bootstrap.py             # 依賴組裝（連線 → Repository → Service，連線失效自動重連）
├── tests/                       # pytest 行為與單元測試
├── docs/PROTOCOL.md             # 大跌行為協定全文（唯讀展示於「行為協定」頁）
├── .streamlit/secrets.toml.example  # 機密範本（Turso / OAuth / 允許 email）
└── pyproject.toml               # 依賴與工具設定
```

## 注意事項

- 財務資料完整存於 Turso；`secrets.toml` 內的 Turso 權杖等同資料庫密碼，外洩請立即至 Turso 後台 rotate。
- app 部署於公開 URL，存取控制僅靠 `st.login()` 登入＋email 允許清單；非清單內帳號登入後即被擋下，看不到任何資料。
- Turso 免費單庫，建議定期以「匯出 CSV」備份；匯入還原僅支援空庫（目標庫非空會被拒絕，避免污染既有資料）。
- **已知環境事項**：`app.py` 開頭在 `import streamlit` 之前搶先設定 `os.environ.setdefault("ARROW_DEFAULT_MEMORY_POOL", "system")`，用意是規避 pyarrow 25 內建 mimalloc 配置器在 macOS arm64 的 thread-init segfault——顯示 DataFrame（`st.dataframe` / `st.data_editor`）觸發 pandas→Arrow 轉換時，曾實測整個 Python 進程 `EXC_BAD_ACCESS` 崩潰；停用 mimalloc、改用系統 malloc 後已驗證穩定。此設定必須早於 Streamlit（連帶 import pyarrow）之前才生效，故 import 順序看似不合慣例，維護者請勿因「風格統一」而移動或刪除這行。
