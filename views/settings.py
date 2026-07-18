"""設定頁（View / Controller）。

職責：持有項目主檔的新增/編輯（含改名、改分類，holding_id 穩定不斷裂歷史）、各分類目標
比重設定（百分比 0–100）、大跌行為協定回撤門檻設定（正幅度%，存前驗證），並以
AllocationService.compute_drift 呈現當月各分類相對目標的偏離與是否需再平衡。委派
HoldingRepository、TargetRepository、ProtocolThresholdRepository/ProtocolService 與
AllocationService。本頁為唯一 catch 點。

主檔身分穩定性、偏離口徑（百分點、嚴格大於門檻）、門檻合法性（0 < L1 < L2 < L3）等業務
正確性由下層的 SC 測試保證；本頁只做委派與呈現。
"""

# ==== 原生（標準庫） ====
import logging

# ==== 第三方套件 ====
import streamlit as st

# ==== 專案內部 ====
from asset_lab.bootstrap import Container
from asset_lab.core.constants import (
    ASSET_CATEGORIES,
    DEFAULT_REBALANCE_THRESHOLD,
    HOLDING_KIND,
    PROTOCOL_LEVEL_CODE,
)
from asset_lab.core.exceptions import AssetLabError
from asset_lab.models.holding import HoldingModel
from asset_lab.models.protocol import ProtocolThresholdModel
from asset_lab.models.target import TargetAllocationModel
from asset_lab.repositories.holding_repository import HoldingRepository
from asset_lab.repositories.protocol_threshold_repository import ProtocolThresholdRepository
from asset_lab.repositories.record_repository import RecordRepository
from asset_lab.repositories.target_repository import TargetRepository
from asset_lab.services.allocation_service import AllocationService
from asset_lab.services.protocol_service import ProtocolService

logger = logging.getLogger(__name__)

# 內部值（HOLDING_KIND.ASSET/LIABILITY）供 DB 與業務判斷使用，不可異動；
# 此對照僅供畫面顯示中文，不影響選取後取得的內部值。
_HOLDING_KIND_LABEL = {
    HOLDING_KIND.ASSET: "資產",
    HOLDING_KIND.LIABILITY: "負債",
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
    number_input 上，key 依表單而異——新增用固定 key，編輯用各項目的 holding_id 前綴 key）。
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
    record_repo = container.record_repo
    allocation_service = container.allocation_service
    protocol_threshold_repo = container.protocol_threshold_repo
    protocol_service = container.protocol_service

    try:
        _render_holdings(holding_repo=holding_repo)
        _render_targets(target_repo=target_repo)
        _render_protocol_thresholds(
            protocol_threshold_repo=protocol_threshold_repo,
            protocol_service=protocol_service,
        )
        _render_drift(
            holding_repo=holding_repo,
            target_repo=target_repo,
            record_repo=record_repo,
            allocation_service=allocation_service,
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
    initial_market_value = None
    initial_cost = None
    if kind == HOLDING_KIND.ASSET:
        category = st.selectbox(
            "分類",
            options=list(ASSET_CATEGORIES.ALL),
            key="new_cat",
            on_change=_sync_cost_to_market_value,
            kwargs=_NEW_HOLDING_SYNC_KEYS,
        )
        initial_market_value = st.number_input(
            "初始市值",
            value=0.0,
            step=1000.0,
            format="%.0f",
            key="new_market_value",
            on_change=_sync_cost_to_market_value,
            kwargs=_NEW_HOLDING_SYNC_KEYS,
        )
        initial_cost = st.number_input(
            "初始成本", value=0.0, step=1000.0, format="%.0f", key="new_cost"
        )

    if st.button("新增") and name:
        holding_repo.add_holding(
            holding=HoldingModel(
                name=name,
                kind=kind,
                category=category,
                initial_market_value=initial_market_value,
                initial_cost=initial_cost,
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
    initial_market_value = holding.initial_market_value
    initial_cost = holding.initial_cost
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
        initial_market_value = st.number_input(
            "初始市值",
            value=float(holding.initial_market_value or 0.0),
            step=1000.0,
            format="%.0f",
            key=sync_keys["market_value_key"],
            on_change=_sync_cost_to_market_value,
            kwargs=sync_keys,
        )
        initial_cost = st.number_input(
            "初始成本",
            value=float(holding.initial_cost or 0.0),
            step=1000.0,
            format="%.0f",
            key=sync_keys["cost_key"],
        )

    if st.button("儲存變更", key=f"{prefix}save"):
        holding_repo.update_holding(
            holding=HoldingModel(
                holding_id=holding.holding_id,
                name=name,
                kind=holding.kind,
                category=category,
                initial_market_value=initial_market_value,
                initial_cost=initial_cost,
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


def _render_drift(
    *,
    holding_repo: HoldingRepository,
    target_repo: TargetRepository,
    record_repo: RecordRepository,
    allocation_service: AllocationService,
) -> None:
    """當月各分類相對目標的偏離與是否需再平衡。"""
    st.subheader("目標偏離")
    latest_ym = record_repo.latest_year_month()
    if latest_ym is None:
        st.write("尚無月度紀錄，無法計算偏離。")
        return

    holdings = holding_repo.list_holdings()
    month_records = record_repo.read_month(year_month=latest_ym)
    snapshot = allocation_service.snapshot(
        month_records=month_records, holdings=holdings, by="category"
    )
    drift_rows = allocation_service.compute_drift(
        snapshot=snapshot,
        targets=target_repo.read_targets(),
        threshold=DEFAULT_REBALANCE_THRESHOLD,
    )
    if not drift_rows:
        st.write("尚未設定任何分類目標比重。")
        return

    st.dataframe(
        [
            {
                "分類": row.category,
                "現況%": round(row.current_weight, 2),
                "目標%": round(row.target_weight, 2),
                "偏離（百分點）": round(row.drift, 2),
                "需再平衡": "是" if row.needs_rebalance else "否",
            }
            for row in drift_rows
        ]
    )


render()
