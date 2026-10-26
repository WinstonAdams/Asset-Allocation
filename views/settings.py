"""設定頁（View / Controller）。

職責：持有項目主檔的新增/編輯（含改名、改分類、改用途，holding_id 穩定不斷裂歷史）、各分類目標
比重設定（百分比 0–100）、大跌行為協定回撤門檻設定（正幅度%，存前驗證）、買房參數設定
（金額/比率/年份，存前驗證）。委派 HoldingRepository、TargetRepository、
ProtocolThresholdRepository/ProtocolService 與 HouseParamRepository/HouseService。
本頁為唯一 catch 點。

目標偏離的呈現（現況對目標比重的偏離與是否需再平衡）改置於「資產配置」頁，與其他配置
相關圖表並列；本頁僅負責目標比重本身的設定。

主檔身分穩定性、門檻合法性（0 < L1 < L2 < L3）、買房參數合法域（比率開區間、金額/年份
非負）等業務正確性由下層的 SC 測試保證；本頁只做委派與呈現。
"""

# ==== 原生（標準庫） ====
import logging

# ==== 第三方套件 ====
import streamlit as st

# ==== 專案內部 ====
from asset_lab.amount_widget import amount_input
from asset_lab.bootstrap import Container
from asset_lab.core.constants import (
    ASSET_CATEGORIES,
    HOLDING_KIND,
    HOLDING_PURPOSE,
    HOUSE_PARAM_KEY,
    PROTOCOL_LEVEL_CODE,
)
from asset_lab.core.exceptions import AssetLabError
from asset_lab.core.utils import parse_amount
from asset_lab.models.holding import HoldingModel
from asset_lab.models.house import HouseParamModel, HouseParams
from asset_lab.models.protocol import ProtocolThresholdModel
from asset_lab.models.target import TargetAllocationModel
from asset_lab.repositories.holding_repository import HoldingRepository
from asset_lab.repositories.house_param_repository import HouseParamRepository
from asset_lab.repositories.protocol_threshold_repository import ProtocolThresholdRepository
from asset_lab.repositories.target_repository import TargetRepository
from asset_lab.services.house_service import HouseService
from asset_lab.services.protocol_service import ProtocolService

logger = logging.getLogger("asset_lab.views.settings")

# 內部值（HOLDING_KIND.ASSET/LIABILITY）供 DB 與業務判斷使用，不可異動；
# 此對照僅供畫面顯示中文，不影響選取後取得的內部值。
_HOLDING_KIND_LABEL = {
    HOLDING_KIND.ASSET: "資產",
    HOLDING_KIND.LIABILITY: "負債",
}

# 內部值（HOLDING_PURPOSE.GENERAL/HOUSE）供 DB 與買房功能判斷使用，不可異動；
# 此對照僅供畫面顯示中文，不影響選取後取得的內部值。
_HOLDING_PURPOSE_LABEL = {
    HOLDING_PURPOSE.GENERAL: "一般",
    HOLDING_PURPOSE.HOUSE: "購屋",
}

# 活存/定存無明顯已實現損益概念，成本與市值理論上應相等，新增與編輯表單皆比照預設帶入。
_CASH_LIKE_CATEGORIES = (ASSET_CATEGORIES.DEMAND_DEPOSIT, ASSET_CATEGORIES.TIME_DEPOSIT)

# 新增表單三個欄位固定的 session_state key，供 _sync_cost_to_market_value 的 on_change 共用。
_NEW_HOLDING_SYNC_KEYS = {
    "cat_key": "new_cat",
    "market_value_key": "new_market_value",
    "cost_key": "new_cost",
}


def _sync_cost_to_market_value(*, cat_key: str, market_value_key: str, cost_key: str) -> None:
    """活存/定存分類下，初始成本預設帶入初始市值；使用者仍可事後手動改成別的值。

    新增與編輯既有項目共用此同步邏輯：只要當下選定分類為活存/定存，改市值或改分類
    皆會觸發（呼叫方以 on_change + kwargs 掛在對應的分類 selectbox 與市值
    amount_input 上，key 依表單而異——新增用固定 key，編輯用各項目的 holding_id 前綴 key）。
    """
    if st.session_state.get(cat_key) in _CASH_LIKE_CATEGORIES:
        st.session_state[cost_key] = st.session_state[market_value_key]


def _container() -> Container:
    """取放行後存入 session 的依賴容器。"""
    return st.session_state["container"]


def render() -> None:
    """渲染設定頁。"""
    st.title("設定")
    container = _container()
    holding_repo = container.holding_repo
    target_repo = container.target_repo
    protocol_threshold_repo = container.protocol_threshold_repo
    protocol_service = container.protocol_service
    house_param_repo = container.house_param_repo
    house_service = container.house_service

    try:
        _render_holdings(holding_repo=holding_repo)
        _render_targets(target_repo=target_repo)
        _render_protocol_thresholds(
            protocol_threshold_repo=protocol_threshold_repo,
            protocol_service=protocol_service,
        )
        _render_house_params(
            house_param_repo=house_param_repo,
            house_service=house_service,
        )
    except AssetLabError as error:
        logger.exception("設定頁操作失敗")
        st.error(str(error))


def _render_holdings(*, holding_repo: HoldingRepository) -> None:
    """持有項目主檔的新增與編輯（改名/改分類不更動 holding_id）。"""
    st.subheader("持有項目主檔")
    for holding in holding_repo.list_holdings():
        label = f"#{holding.holding_id} {holding.name}（{_HOLDING_KIND_LABEL[holding.kind]}）"
        with st.expander(label):
            _render_edit_holding(holding=holding, holding_repo=holding_repo)

    st.markdown("#### 新增項目")
    name = st.text_input("名稱", key="new_name")
    kind = st.selectbox(
        "性質",
        options=list(HOLDING_KIND.ALL),
        format_func=lambda k: _HOLDING_KIND_LABEL[k],
        key="new_kind",
    )
    category = None
    initial_market_value_text = None
    initial_cost_text = None
    if kind == HOLDING_KIND.ASSET:
        category = st.selectbox(
            "分類",
            options=list(ASSET_CATEGORIES.ALL),
            key="new_cat",
            on_change=_sync_cost_to_market_value,
            kwargs=_NEW_HOLDING_SYNC_KEYS,
        )
        initial_market_value_text = amount_input(
            "初始市值",
            key="new_market_value",
            on_change=_sync_cost_to_market_value,
            kwargs=_NEW_HOLDING_SYNC_KEYS,
        )
        initial_cost_text = amount_input("初始成本", key="new_cost")

    purpose = HOLDING_PURPOSE.GENERAL
    if kind == HOLDING_KIND.ASSET:
        purpose = st.selectbox(
            "用途",
            options=list(HOLDING_PURPOSE.ALL),
            format_func=lambda p: _HOLDING_PURPOSE_LABEL[p],
            key="new_purpose",
        )

    if st.button("新增") and name:
        initial_market_value = None
        initial_cost = None
        if kind == HOLDING_KIND.ASSET:
            initial_market_value = parse_amount(initial_market_value_text, field_label="初始市值")
            initial_cost = parse_amount(initial_cost_text, field_label="初始成本")
        holding_repo.add_holding(
            holding=HoldingModel(
                name=name,
                kind=kind,
                category=category,
                initial_market_value=initial_market_value,
                initial_cost=initial_cost,
                purpose=purpose,
            )
        )
        st.success("已新增項目")


def _render_edit_holding(*, holding: HoldingModel, holding_repo: HoldingRepository) -> None:
    """既有項目的編輯區塊：可改名、改分類（資產）、改初始市值/成本，holding_id 不變。"""
    prefix = f"edit_{holding.holding_id}_"
    sync_keys = {
        "cat_key": f"{prefix}cat",
        "market_value_key": f"{prefix}market_value",
        "cost_key": f"{prefix}cost",
    }

    name = st.text_input("名稱", value=holding.name, key=f"{prefix}name")

    category = holding.category
    initial_market_value_text = None
    initial_cost_text = None
    if holding.kind == HOLDING_KIND.ASSET:
        options = list(ASSET_CATEGORIES.ALL)
        # 既有分類理應皆落在受控清單內；不在清單內時（如未來清單變動）退回第一項，不崩畫面。
        current_index = options.index(holding.category) if holding.category in options else 0
        category = st.selectbox(
            "分類",
            options=options,
            index=current_index,
            key=sync_keys["cat_key"],
            on_change=_sync_cost_to_market_value,
            kwargs=sync_keys,
        )
        initial_market_value_text = amount_input(
            "初始市值",
            value=holding.initial_market_value or 0.0,
            key=sync_keys["market_value_key"],
            on_change=_sync_cost_to_market_value,
            kwargs=sync_keys,
        )
        initial_cost_text = amount_input(
            "初始成本",
            value=holding.initial_cost or 0.0,
            key=sync_keys["cost_key"],
        )

    purpose = holding.purpose
    if holding.kind == HOLDING_KIND.ASSET:
        purpose_options = list(HOLDING_PURPOSE.ALL)
        # 既有用途理應皆落在受控清單內；不在清單內時退回第一項（一般），不崩畫面。
        purpose_index = (
            purpose_options.index(holding.purpose) if holding.purpose in purpose_options else 0
        )
        purpose = st.selectbox(
            "用途",
            options=purpose_options,
            index=purpose_index,
            format_func=lambda p: _HOLDING_PURPOSE_LABEL[p],
            key=f"{prefix}purpose",
        )

    if st.button("儲存變更", key=f"{prefix}save"):
        initial_market_value = holding.initial_market_value
        initial_cost = holding.initial_cost
        if holding.kind == HOLDING_KIND.ASSET:
            initial_market_value = parse_amount(initial_market_value_text, field_label="初始市值")
            initial_cost = parse_amount(initial_cost_text, field_label="初始成本")
        holding_repo.update_holding(
            holding=HoldingModel(
                holding_id=holding.holding_id,
                name=name,
                kind=holding.kind,
                category=category,
                initial_market_value=initial_market_value,
                initial_cost=initial_cost,
                purpose=purpose,
            )
        )
        st.success("已更新項目")


def _render_targets(*, target_repo: TargetRepository) -> None:
    """各分類目標比重設定（百分比 0–100）。"""
    st.subheader("目標比重")
    current = {t.category: t.target_weight for t in target_repo.read_targets()}
    for category in ASSET_CATEGORIES.ALL:
        # st.number_input 的 format 需能還原成合法 float（Streamlit 內部驗證），無法附加 "%"
        # 文字後綴，因此改在 label 加註「（%）」呈現單位，不影響輸入值本身。
        weight = st.number_input(
            f"{category}（%）",
            value=float(current.get(category, 0.0)),
            min_value=0.0,
            max_value=100.0,
            step=1.0,
            key=f"target_{category}",
        )
        if st.button(f"儲存 {category}", key=f"save_{category}"):
            target_repo.upsert_target(
                target=TargetAllocationModel(category=category, target_weight=weight)
            )
            st.success(f"已儲存 {category} 目標比重")


def _render_protocol_thresholds(
    *,
    protocol_threshold_repo: ProtocolThresholdRepository,
    protocol_service: ProtocolService,
) -> None:
    """大跌行為協定回撤門檻設定（正幅度%）。存前驗證，失敗即拒絕、不落 DB。"""
    st.subheader("大跌行為協定門檻")
    current = protocol_service.effective_thresholds(
        stored=protocol_threshold_repo.read_thresholds()
    )
    l1 = st.number_input(
        "L1 門檻（回撤%）", value=float(current.l1), min_value=0.0, step=1.0, key="protocol_l1"
    )
    l2 = st.number_input(
        "L2 門檻（回撤%）", value=float(current.l2), min_value=0.0, step=1.0, key="protocol_l2"
    )
    l3 = st.number_input(
        "L3 門檻（回撤%）", value=float(current.l3), min_value=0.0, step=1.0, key="protocol_l3"
    )

    if st.button("儲存門檻"):
        protocol_service.validate_thresholds(l1=l1, l2=l2, l3=l3)
        for level, value in (
            (PROTOCOL_LEVEL_CODE.L1, l1),
            (PROTOCOL_LEVEL_CODE.L2, l2),
            (PROTOCOL_LEVEL_CODE.L3, l3),
        ):
            protocol_threshold_repo.upsert_threshold(
                threshold=ProtocolThresholdModel(level=level, drawdown_threshold=value)
            )
        st.success("已儲存回撤門檻")


def _render_house_params(
    *,
    house_param_repo: HouseParamRepository,
    house_service: HouseService,
) -> None:
    """買房政策與個人化參數設定。存前驗證，失敗即拒絕、不落 DB。

    個人化參數（金額/收入/年份）初值一律中性 0（尚未設定），真實值僅由使用者
    於此頁輸入後落 DB，程式碼不內建任何個人化預設數字。
    """
    st.subheader("買房參數")
    current = house_service.effective_params(stored=house_param_repo.read_params())

    target_total_price_text = amount_input(
        "目標總價（TWD）",
        value=current.target_total_price,
        key="house_target_total_price",
    )
    target_year = st.number_input(
        "目標購屋年份",
        value=int(current.target_year),
        min_value=0,
        step=1,
        key="house_target_year",
    )
    monthly_after_tax_income_text = amount_input(
        "家庭稅後月收（TWD）",
        value=current.monthly_after_tax_income,
        key="house_monthly_after_tax_income",
    )
    income_threshold_text = amount_input(
        "收入門檻（TWD/月）",
        value=current.income_threshold,
        key="house_income_threshold",
    )
    cash_floor_text = amount_input(
        "現金地板（TWD）",
        value=current.cash_floor,
        key="house_cash_floor",
    )
    down_payment_ratio = st.number_input(
        "自備比率（%）",
        value=float(current.down_payment_ratio),
        min_value=0.0,
        max_value=100.0,
        step=1.0,
        key="house_down_payment_ratio",
    )
    payment_cap_ratio = st.number_input(
        "月付上限比率（%）",
        value=float(current.payment_cap_ratio),
        min_value=0.0,
        max_value=100.0,
        step=1.0,
        key="house_payment_cap_ratio",
    )
    test_annual_rate = st.number_input(
        "驗算利率（年化%）",
        value=float(current.test_annual_rate),
        min_value=0.0,
        step=0.1,
        key="house_test_annual_rate",
    )
    loan_years = st.number_input(
        "貸款年限（年）",
        value=int(current.loan_years),
        min_value=1,
        step=1,
        key="house_loan_years",
    )

    if st.button("儲存買房參數"):
        candidate = HouseParams(
            target_total_price=parse_amount(target_total_price_text, field_label="目標總價"),
            target_year=int(target_year),
            monthly_after_tax_income=parse_amount(
                monthly_after_tax_income_text, field_label="家庭稅後月收"
            ),
            income_threshold=parse_amount(income_threshold_text, field_label="收入門檻"),
            cash_floor=parse_amount(cash_floor_text, field_label="現金地板"),
            down_payment_ratio=down_payment_ratio,
            payment_cap_ratio=payment_cap_ratio,
            test_annual_rate=test_annual_rate,
            loan_years=int(loan_years),
        )
        house_service.validate_params(params=candidate)
        for key, value in (
            (HOUSE_PARAM_KEY.TARGET_TOTAL_PRICE, candidate.target_total_price),
            (HOUSE_PARAM_KEY.TARGET_YEAR, float(candidate.target_year)),
            (HOUSE_PARAM_KEY.MONTHLY_AFTER_TAX_INCOME, candidate.monthly_after_tax_income),
            (HOUSE_PARAM_KEY.INCOME_THRESHOLD, candidate.income_threshold),
            (HOUSE_PARAM_KEY.CASH_FLOOR, candidate.cash_floor),
            (HOUSE_PARAM_KEY.DOWN_PAYMENT_RATIO, candidate.down_payment_ratio),
            (HOUSE_PARAM_KEY.PAYMENT_CAP_RATIO, candidate.payment_cap_ratio),
            (HOUSE_PARAM_KEY.TEST_ANNUAL_RATE, candidate.test_annual_rate),
            (HOUSE_PARAM_KEY.LOAN_YEARS, float(candidate.loan_years)),
        ):
            house_param_repo.upsert_param(
                param=HouseParamModel(param_key=key, param_value=value)
            )
        st.success("已儲存買房參數")


render()
