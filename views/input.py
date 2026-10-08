"""月度錄入頁（View / Controller）。

職責：渲染月度錄入 UI、收集輸入、委派 MonthlyInputService／CostBasisService 與
RecordRepository，並作為唯一 catch 點把下層例外轉成 st.error 友善訊息（同時記 log）。
不直接寫 SQL、不算任何業務值。

提供：年+月下拉選擇錄入月份（依 Asia/Taipei 時區預設帶入當月）、帶入上月仍持有清單、
本月已存紀錄唯讀表格（含市值未填提醒）、單列新增/編輯/刪除（選定項目與月份後帶入既有值；
依項目分類切換欄位：股票/ETF 改以總成本＋現值＋已實現損益＋現金股利輸入，存檔前顯示
推算淨投入預覽；其餘分類維持市值/餘額＋淨投入直接輸入）、項目間成對轉移（累加到既有
紀錄；涉及股票/ETF 端的淨投入交由推算負責，不重複寫入）、賣出語意提示。每次成功寫入後
整頁重繪，讓表格與錄入框反映最新資料，成功訊息於下一輪顯示在頁面上方。業務正確性由
下層 Service/Repository 的 SC 測試保證；本頁只做委派與呈現。
"""

# ==== 原生（標準庫） ====
import logging

# ==== 第三方套件 ====
import streamlit as st

# ==== 專案內部 ====
from asset_lab.amount_widget import amount_input, seed_amount_inputs
from asset_lab.bootstrap import Container
from asset_lab.core.constants import TIMEZONE
from asset_lab.core.exceptions import AssetLabError, DataValidationError
from asset_lab.core.utils import (
    current_year_month,
    format_amount,
    parse_amount,
    parse_year_month,
)
from asset_lab.models.holding import HoldingModel
from asset_lab.models.record import MonthlyRecordModel
from asset_lab.repositories.record_repository import RecordRepository
from asset_lab.services.cost_basis_service import CostBasisService
from asset_lab.services.monthly_input_service import MonthlyInputService
from asset_lab.services.period_service import today_in_timezone

logger = logging.getLogger(__name__)

# 年份下拉可選範圍：當年往前推 N 年到當年，不開放未來年份——月度錄入記的是已發生的市值/
# 淨投入，未來月份無實際數據可記；往前 5 年已足夠涵蓋近年回溯修正需求。
_YEAR_DROPDOWN_BACK_YEARS = 5

# 寫入成功後 st.rerun() 會丟掉本輪畫面，成功訊息先存進 session_state，下一輪開頭取出顯示一次。
_FLASH_KEY = "input_flash_message"

# 錄入框帶入值的播種來源記錄 key：來源改變（切換項目/月份或資料被存檔、轉移改動）才重新帶入。
_RECORD_SEED_KEY = "input_record_seed"
_COST_BASIS_SEED_KEY = "input_cost_basis_seed"


def _container() -> Container:
    """取放行後存入 session 的依賴容器。"""
    return st.session_state["container"]


def render() -> None:
    """渲染月度錄入頁。"""
    st.title("月度錄入")
    flash_message = st.session_state.pop(_FLASH_KEY, None)
    if flash_message:
        st.success(flash_message)
    st.info(
        "賣出/不再持有：賣出當月請記市值 0、淨投入記為負的提領金額，之後月份不再為該項目記列"
        "（缺列＝已不持有）。股票/ETF 項目賣出時，請把目前總成本與現值填 0、已實現損益填實際"
        "獲利金額（現金股利另填），淨投入將自動推算。"
    )

    container = _container()
    record_repo = container.record_repo
    holding_repo = container.holding_repo
    input_service = container.monthly_input_service
    cost_basis_service = container.cost_basis_service

    target_ym = _select_target_year_month()

    try:
        if st.button("帶入上月仍持有項目"):
            prefilled = input_service.prefill_from_previous(target_ym=target_ym)
            st.session_state["prefilled_records"] = [r.model_dump() for r in prefilled]

        # 每輪只讀一次，表格、錄入框、轉移共用同一份資料來源
        holdings = holding_repo.list_holdings()
        month_records = record_repo.read_month(year_month=target_ym)

        _render_month_records(
            input_service=input_service, holdings=holdings, month_records=month_records
        )
        _render_record_editor(
            input_service=input_service,
            record_repo=record_repo,
            cost_basis_service=cost_basis_service,
            holdings=holdings,
            month_records=month_records,
            target_ym=target_ym,
        )
        _render_transfer(
            input_service=input_service,
            record_repo=record_repo,
            cost_basis_service=cost_basis_service,
            holdings=holdings,
            target_ym=target_ym,
        )
    except AssetLabError as error:
        # Page 為唯一 catch 點：對使用者顯示友善訊息，技術細節進 log
        logger.exception("月度錄入操作失敗")
        st.error(str(error))


def _flash_and_rerun(message: str) -> None:
    """暫存成功訊息後整頁重繪，讓本月表格與錄入框以寫入後的資料重新渲染。"""
    st.session_state[_FLASH_KEY] = message
    st.rerun()


def _render_month_records(
    *,
    input_service: MonthlyInputService,
    holdings: list[HoldingModel],
    month_records: list[MonthlyRecordModel],
) -> None:
    """本月已存紀錄唯讀表格：市值（或餘額）未填的列顯示提醒，無紀錄顯示空狀態。"""
    st.subheader("本月已存紀錄")
    rows = input_service.summarize_month(records=month_records, holdings=holdings)
    if not rows:
        st.caption("本月尚無已存紀錄")
        return
    st.dataframe(
        [
            {
                "項目": row.name,
                "市值 / 餘額": format_amount(row.market_value),
                "淨投入": format_amount(row.net_investment),
                "總成本": format_amount(row.total_cost),
                "已實現收益": format_amount(row.realized_income),
                "提醒": "本月市值尚未填" if row.market_value_missing else "",
            }
            for row in rows
        ],
        hide_index=True,
    )


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
    *,
    input_service: MonthlyInputService,
    record_repo: RecordRepository,
    cost_basis_service: CostBasisService,
    holdings: list[HoldingModel],
    month_records: list[MonthlyRecordModel],
    target_ym: str,
) -> None:
    """單列新增/編輯/刪除：依項目分類切換輸入欄位後委派 Repository 寫入。

    年月沿用頁面上方「錄入年份／錄入月份」下拉選定值，與「項目間轉移」共用同一選擇，
    避免與獨立文字輸入框脫節而永遠空白。股票/ETF 分類的項目改走總成本輸入方式，交由
    `_render_cost_basis_editor` 處理；其餘分類維持市值/餘額與淨投入直接輸入，並依選定
    項目與月份帶入當月既有值（來源改變才重新帶入，使用者尚未存檔的輸入不被洗掉）。
    """
    st.subheader("單列錄入")
    if not holdings:
        st.write("尚無持有項目，請先到「設定」頁建立主檔。")
        return

    name_by_id = {h.holding_id: h.name for h in holdings}
    holding_by_id = {h.holding_id: h for h in holdings}
    holding_id = st.selectbox(
        "項目", options=list(name_by_id), format_func=lambda hid: name_by_id[hid]
    )
    holding = holding_by_id[holding_id]

    if cost_basis_service.uses_cost_basis(holding=holding):
        _render_cost_basis_editor(
            record_repo=record_repo,
            cost_basis_service=cost_basis_service,
            holding=holding,
            target_ym=target_ym,
        )
        return

    prefill = input_service.build_record_prefill(
        records=month_records, holding_id=holding_id, year_month=target_ym
    )
    seed_amount_inputs(
        seed_key=_RECORD_SEED_KEY,
        source=(holding_id, target_ym, prefill),
        values={
            "record_market_value": prefill.market_value,
            "record_net_investment": prefill.net_investment,
        },
    )
    market_value_text = amount_input("市值 / 餘額", key="record_market_value")
    net_investment_text = amount_input(
        "當月淨投入（正投入 / 負提領）", key="record_net_investment"
    )

    col_save, col_delete = st.columns(2)
    if col_save.button("儲存此列"):
        record = MonthlyRecordModel(
            holding_id=holding_id,
            year_month=target_ym,
            market_value=parse_amount(market_value_text, field_label="市值/餘額"),
            net_investment=parse_amount(net_investment_text, field_label="當月淨投入"),
        )
        record_repo.upsert_record(record=record)
        _flash_and_rerun("已儲存")
    if col_delete.button("刪除此列"):
        record_repo.delete_record(holding_id=holding_id, year_month=target_ym)
        _flash_and_rerun("已刪除")


def _render_cost_basis_editor(
    *,
    record_repo: RecordRepository,
    cost_basis_service: CostBasisService,
    holding: HoldingModel,
    target_ym: str,
) -> None:
    """股票/ETF 項目：以總成本＋現值＋已實現損益＋現金股利輸入，存檔前顯示推算淨投入預覽。

    每次 rerun 都重新讀取該項目全部紀錄並呼叫 derive 更新預覽，讓使用者輸入到一半也
    能即時核對；解析失敗（欄位尚未輸入完成）只顯示佔位提示，不當成錯誤攔下整頁；推算被
    拒絕（如現金股利為負）則直接顯示拒絕原因，與「尚未輸入完成」區分。儲存
    與刪除則需要完整規劃（含連動重算受影響的後續列），交由 CostBasisService 的
    plan_save／plan_delete 產生完整寫入清單，再一次性交給 Repository 的 compound
    寫入方法，確保推算鏈要嘛全部落地、要嘛全部不變。
    """
    records = record_repo.read_holding_records(holding_id=holding.holding_id)

    prefill = cost_basis_service.build_cost_basis_prefill(records=records, year_month=target_ym)
    seed_amount_inputs(
        seed_key=_COST_BASIS_SEED_KEY,
        source=(holding.holding_id, target_ym, prefill),
        values={
            "cost_basis_total_cost": prefill.total_cost,
            "cost_basis_market_value": prefill.market_value,
            "cost_basis_realized_pnl": prefill.realized_pnl,
            "cost_basis_cash_dividend": prefill.cash_dividend,
        },
    )

    total_cost_text = amount_input("目前總成本", key="cost_basis_total_cost")
    market_value_text = amount_input("現值", key="cost_basis_market_value")
    realized_pnl_text = amount_input("本月已實現損益（可為負）", key="cost_basis_realized_pnl")
    cash_dividend_text = amount_input("本月現金股利（不可為負）", key="cost_basis_cash_dividend")
    st.caption(
        "若賣出款項或股利存入本工具有追蹤的帳戶（例如活存），請另外用「項目間轉移」記錄該帳戶端，"
        "否則整體報酬率會重複計入資金流入；若存入的是工具未追蹤的帳戶則不需轉移。"
    )

    try:
        total_cost = parse_amount(total_cost_text, field_label="目前總成本")
        realized_pnl = parse_amount(realized_pnl_text, field_label="本月已實現損益")
        cash_dividend = parse_amount(cash_dividend_text, field_label="本月現金股利")
    except DataValidationError:
        st.caption("輸入完成後顯示推算值")
    else:
        try:
            preview = cost_basis_service.derive(
                holding=holding,
                records=records,
                year_month=target_ym,
                total_cost=total_cost,
                realized_pnl=realized_pnl,
                cash_dividend=cash_dividend,
            )
        except DataValidationError as error:
            st.error(str(error))
        else:
            st.write(f"前期總成本：{format_amount(preview.previous_total_cost)}")
            st.write(f"推算本月淨投入：{format_amount(preview.net_investment)}")
            if preview.is_transition_estimate:
                st.warning(
                    "前期總成本為過渡期估算值，可能與券商實際總成本有落差，請留意核對。"
                )

    col_save, col_delete = st.columns(2)
    if col_save.button("儲存此列"):
        plan = cost_basis_service.plan_save(
            holding=holding,
            records=records,
            year_month=target_ym,
            market_value=parse_amount(market_value_text, field_label="現值"),
            total_cost=parse_amount(total_cost_text, field_label="目前總成本"),
            realized_pnl=parse_amount(realized_pnl_text, field_label="本月已實現損益"),
            cash_dividend=parse_amount(cash_dividend_text, field_label="本月現金股利"),
        )
        record_repo.upsert_records(records=plan)
        _flash_and_rerun("已儲存")
    if col_delete.button("刪除此列"):
        plan = cost_basis_service.plan_delete(
            holding=holding, records=records, year_month=target_ym
        )
        record_repo.delete_record_and_upsert(
            holding_id=holding.holding_id, year_month=target_ym, records=plan
        )
        _flash_and_rerun("已刪除")


def _render_transfer(
    *,
    input_service: MonthlyInputService,
    record_repo: RecordRepository,
    cost_basis_service: CostBasisService,
    holdings: list[HoldingModel],
    target_ym: str,
) -> None:
    """項目間成對轉移：委派 Service 產生成對紀錄，濾掉股票/ETF 端後累加寫入。

    兩端皆為股票/ETF 時濾完為空清單，屬合法情況（雙方淨投入都改由總成本推算），以
    提示訊息告知使用者，不當成輸入錯誤處理。
    """
    st.subheader("項目間轉移")
    options = {h.holding_id: h.name for h in holdings}
    if len(options) < 2:
        st.write("至少需兩個項目才能轉移。")
        return

    source_id = st.selectbox(
        "轉出來源", options=list(options), format_func=lambda hid: options[hid], key="src"
    )
    dest_id = st.selectbox(
        "轉入目標", options=list(options), format_func=lambda hid: options[hid], key="dst"
    )
    amount_text = amount_input("轉移金額（正數）", key="amt")

    if st.button("建立轉移"):
        pair = input_service.build_transfer_pair(
            source_id=source_id,
            dest_id=dest_id,
            amount=parse_amount(amount_text, field_label="轉移金額"),
            year_month=target_ym,
        )
        records_to_write = cost_basis_service.transfer_records_to_write(
            pair=pair, holdings=holdings
        )
        if records_to_write:
            record_repo.accumulate_net_investments(records=records_to_write)
            _flash_and_rerun("已建立成對轉移紀錄")
        else:
            st.info(
                "來源與目標皆為股票/ETF 項目，淨投入改由總成本推算，未寫入任何紀錄。"
            )


render()
