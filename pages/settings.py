"""設定頁（View / Controller）。

職責：持有項目主檔的新增/編輯（含改名、改分類，holding_id 穩定不斷裂歷史）、各分類目標
比重設定（百分比 0–100），並以 AllocationService.compute_drift 呈現當月各分類相對目標的偏離
與是否需再平衡。委派 HoldingRepository、TargetRepository 與 AllocationService。本頁為唯一
catch 點。

主檔身分穩定性、偏離口徑（百分點、嚴格大於門檻）等業務正確性由下層的 SC 測試保證；本頁
只做委派與呈現。
"""

# ==== 原生（標準庫） ====
import logging

# ==== 第三方套件 ====
import streamlit as st

# ==== 專案內部 ====
from asset_lab.core.constants import ASSET_CATEGORIES, DEFAULT_REBALANCE_THRESHOLD, HOLDING_KIND
from asset_lab.core.exceptions import AssetLabError
from asset_lab.models.holding import HoldingModel
from asset_lab.models.target import TargetAllocationModel

logger = logging.getLogger(__name__)


def _container():
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

    try:
        _render_holdings(holding_repo=holding_repo)
        _render_targets(target_repo=target_repo)
        _render_drift(
            holding_repo=holding_repo,
            target_repo=target_repo,
            record_repo=record_repo,
            allocation_service=allocation_service,
        )
    except AssetLabError as error:
        logger.exception("設定頁操作失敗")
        st.error(str(error))


def _render_holdings(*, holding_repo) -> None:
    """持有項目主檔的新增與編輯（改名/改分類不更動 holding_id）。"""
    st.subheader("持有項目主檔")
    for holding in holding_repo.list_holdings():
        st.write(f"#{holding.holding_id} {holding.name}（{holding.kind}）")

    st.markdown("#### 新增項目")
    name = st.text_input("名稱", key="new_name")
    kind = st.selectbox("性質", options=list(HOLDING_KIND.ALL), key="new_kind")
    category = None
    initial_market_value = None
    initial_cost = None
    if kind == HOLDING_KIND.ASSET:
        category = st.selectbox("分類", options=list(ASSET_CATEGORIES.ALL), key="new_cat")
        initial_market_value = st.number_input("初始市值", value=0.0, step=1000.0)
        initial_cost = st.number_input("初始成本", value=0.0, step=1000.0)

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


def _render_targets(*, target_repo) -> None:
    """各分類目標比重設定（百分比 0–100）。"""
    st.subheader("目標比重")
    current = {t.category: t.target_weight for t in target_repo.read_targets()}
    for category in ASSET_CATEGORIES.ALL:
        weight = st.number_input(
            category,
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


def _render_drift(*, holding_repo, target_repo, record_repo, allocation_service) -> None:
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
