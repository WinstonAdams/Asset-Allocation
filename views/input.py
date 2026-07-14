"""月度錄入頁（View / Controller）。

職責：渲染月度錄入 UI、收集輸入、委派 MonthlyInputService 與 RecordRepository，並作為
唯一 catch 點把下層例外轉成 st.error 友善訊息（同時記 log）。不直接寫 SQL、不算任何業務值。

提供：年+月下拉選擇錄入月份（依 Asia/Taipei 時區預設帶入當月）、帶入上月仍持有清單、單列
新增/編輯/刪除、項目間成對轉移、賣出語意提示（賣出當月記市值 0、淨投入記負提領金額，之後
月份不再記列）。業務正確性由下層 Service/Repository 的 SC 測試保證；本頁只做委派與呈現。
"""

# ==== 原生（標準庫） ====
import logging

# ==== 第三方套件 ====
import streamlit as st

# ==== 專案內部 ====
from asset_lab.bootstrap import Container
from asset_lab.core.constants import TIMEZONE
from asset_lab.core.exceptions import AssetLabError
from asset_lab.core.utils import current_year_month, parse_year_month
from asset_lab.models.record import MonthlyRecordModel
from asset_lab.repositories.holding_repository import HoldingRepository
from asset_lab.repositories.record_repository import RecordRepository
from asset_lab.services.monthly_input_service import MonthlyInputService
from asset_lab.services.period_service import today_in_timezone

logger = logging.getLogger(__name__)

# 年份下拉可選範圍：當年往前推 N 年到當年，不開放未來年份——月度錄入記的是已發生的市值/
# 淨投入，未來月份無實際數據可記；往前 5 年已足夠涵蓋近年回溯修正需求。
_YEAR_DROPDOWN_BACK_YEARS = 5


def _container() -> Container:
    """取放行後存入 session 的依賴容器。"""
    return st.session_state["container"]


def render() -> None:
    """渲染月度錄入頁。"""
    st.title("月度錄入")
    st.info(
        "賣出/不再持有：賣出當月請記市值 0、淨投入記為負的提領金額，之後月份不再為該項目記列"
        "（缺列＝已不持有）。"
    )

    container = _container()
    record_repo = container.record_repo
    holding_repo = container.holding_repo
    input_service = container.monthly_input_service

    target_ym = _select_target_year_month()

    try:
        if st.button("帶入上月仍持有項目"):
            prefilled = input_service.prefill_from_previous(target_ym=target_ym)
            st.session_state["prefilled_records"] = [r.model_dump() for r in prefilled]

        _render_record_editor(record_repo=record_repo, holding_repo=holding_repo)
        _render_transfer(
            input_service=input_service,
            record_repo=record_repo,
            holding_repo=holding_repo,
            target_ym=target_ym,
        )
    except AssetLabError as error:
        # Page 為唯一 catch 點：對使用者顯示友善訊息，技術細節進 log
        logger.exception("月度錄入操作失敗")
        st.error(str(error))


def _select_target_year_month() -> str:
    """年+月下拉選單選擇錄入月份，預設帶入當月（依 Asia/Taipei 時區判定）。

    Returns:
        使用者選定的月份，'YYYY-MM' 格式。
    """
    default_year, default_month = parse_year_month(
        current_year_month(today_in_timezone(TIMEZONE))
    )
    year_options = list(range(default_year - _YEAR_DROPDOWN_BACK_YEARS, default_year + 1))
    month_options = list(range(1, 13))

    col_year, col_month = st.columns(2)
    selected_year = col_year.selectbox(
        "錄入年份",
        options=year_options,
        index=year_options.index(default_year),
        key="input_target_year",
    )
    selected_month = col_month.selectbox(
        "錄入月份",
        options=month_options,
        index=default_month - 1,
        format_func=lambda month: f"{month:02d}",
        key="input_target_month",
    )
    return f"{selected_year:04d}-{selected_month:02d}"


def _render_record_editor(
    *, record_repo: RecordRepository, holding_repo: HoldingRepository
) -> None:
    """單列新增/編輯/刪除：收集欄位後委派 Repository 寫入。"""
    st.subheader("單列錄入")
    holdings = holding_repo.list_holdings()
    if not holdings:
        st.write("尚無持有項目，請先到「設定」頁建立主檔。")
        return

    name_by_id = {h.holding_id: h.name for h in holdings}
    holding_id = st.selectbox(
        "項目", options=list(name_by_id), format_func=lambda hid: name_by_id[hid]
    )
    year_month = st.text_input("年月（YYYY-MM）", key="row_ym")
    market_value = st.number_input("市值 / 餘額", value=0.0, step=1000.0)
    net_investment = st.number_input("當月淨投入（正投入 / 負提領）", value=0.0, step=1000.0)

    col_save, col_delete = st.columns(2)
    if col_save.button("儲存此列") and year_month:
        record = MonthlyRecordModel(
            holding_id=holding_id,
            year_month=year_month,
            market_value=market_value,
            net_investment=net_investment,
        )
        record_repo.upsert_record(record=record)
        st.success("已儲存")
    if col_delete.button("刪除此列") and year_month:
        record_repo.delete_record(holding_id=holding_id, year_month=year_month)
        st.success("已刪除")


def _render_transfer(
    *,
    input_service: MonthlyInputService,
    record_repo: RecordRepository,
    holding_repo: HoldingRepository,
    target_ym: str,
) -> None:
    """項目間成對轉移：委派 Service 產生成對紀錄後由 Repository 寫入。"""
    st.subheader("項目間轉移")
    options = {h.holding_id: h.name for h in holding_repo.list_holdings()}
    if len(options) < 2:
        st.write("至少需兩個項目才能轉移。")
        return

    source_id = st.selectbox(
        "轉出來源", options=list(options), format_func=lambda hid: options[hid], key="src"
    )
    dest_id = st.selectbox(
        "轉入目標", options=list(options), format_func=lambda hid: options[hid], key="dst"
    )
    amount = st.number_input("轉移金額（正數）", value=0.0, step=1000.0, key="amt")

    if st.button("建立轉移"):
        source, dest = input_service.build_transfer_pair(
            source_id=source_id, dest_id=dest_id, amount=amount, year_month=target_ym
        )
        record_repo.upsert_record(record=source)
        record_repo.upsert_record(record=dest)
        st.success("已建立成對轉移紀錄")


render()
