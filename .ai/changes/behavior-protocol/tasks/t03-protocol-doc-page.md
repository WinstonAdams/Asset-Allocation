# Task t03: 行為協定唯讀頁 + 協定文件 Repository

## 滿足 Scenarios
- SC-048 (happy) — 行為協定頁以 markdown 唯讀渲染 `docs/PROTOCOL.md` 全文；文件缺失時友善錯誤、不整頁崩壞

## 實作範圍
- src/asset_lab/core/exceptions.py（新增 `ProtocolDocError(AssetLabError)`，供文件缺失走 Page catch）
- src/asset_lab/core/constants.py（新增 `PROTOCOL_DOC_RELATIVE_PATH = "docs/PROTOCOL.md"`）
- src/asset_lab/repositories/protocol_doc_repository.py（新增 `ProtocolDocRepository(*, doc_path: Path)`，`read_protocol_markdown() -> str` 以 UTF-8 讀全文；檔案不存在拋 `ProtocolDocError`）
- src/asset_lab/bootstrap.py（`Container` 追加 `protocol_doc_repo`；模組層 `_PROTOCOL_DOC_PATH = Path(__file__).resolve().parents[2] / PROTOCOL_DOC_RELATIVE_PATH`；`build_container` 組裝 `ProtocolDocRepository(doc_path=_PROTOCOL_DOC_PATH)`）
- views/protocol.py（新增唯讀頁：`container.protocol_doc_repo.read_protocol_markdown()` → `st.markdown(...)`；`try/except AssetLabError → st.error`；尾端 `render()`）
- app.py（`st.navigation` 清單新增 `st.Page("views/protocol.py", title="行為協定", icon=":material/menu_book:")`）
- tests/test_protocol_doc.py（SC-048：讀全文成功 / 檔案缺失拋 `ProtocolDocError`）

## 依賴
- t02（共用 `bootstrap.Container` / `build_container` 與 `app.py` nav 的累加編輯，依序 commit 避免衝突；功能上不依賴門檻設定）

## 切片理由
獨立葉節點：文件讀取歸 Repository（可注入暫存檔測「缺失」分支），view 僅 `st.markdown` 一行渲染，與判定引擎/門檻解耦，可單獨 commit 並在 app 掛頁後手動驗證。SC-048 的可測核心（讀全文 / 缺失拋例外）落在 `ProtocolDocRepository`（test_protocol_doc.py），view + nav 為薄 UI glue。排在總覽（t04）之前，讓總覽切片專注於判定整合。
