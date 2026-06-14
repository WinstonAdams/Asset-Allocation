# Task t10: 登入守門判定（email 比對）

## 滿足 Scenarios
- SC-033 (happy) — 本人 email 登入後可進入並看到財務資料
- SC-034 (錯誤) — 非本人 email 登入後被擋下看不到任何財務資料

## 實作範圍
- `src/asset_lab/core/access.py`（純判定函式：依「是否登入」「email 是否在允許清單」回傳放行/拒絕決策，不 import streamlit）
- `tests/test_access_control.py`（SC-033、SC-034 對映）

## 依賴
- t01（core 套件、exceptions / constants）

## 切片理由
守門的「比對決策」是可獨立測的純邏輯（未登入→擋、已登入且 email 在清單→放行、已登入但 email 不在清單→擋），把它抽成不 import streamlit 的純函式，才能用 pytest 直接斷言三種決策（SC-033 放行、SC-034 拒絕），符合 AD-6「守門前置於任何資料存取」且不需起 Streamlit session。`st.login()` 按鈕渲染、`st.stop()`、`st.user.email` 取值等 Streamlit 副作用屬 app.py 的串接，留待 t11；本切片只鎖定可測的比對核心，與 Service 純運算同屬「先做可測邏輯」。
