"""月度錄入頁（View / Controller）。

職責：渲染月度錄入 UI、收集輸入、委派 MonthlyInputService／CostBasisService／
BalanceInputService 與 RecordRepository，並作為唯一 catch 點把下層例外（含寫入失敗的
PersistenceError）轉成 st.error 友善訊息（同時記 log）。不直接寫 SQL、不算任何業務值。

提供：年+月下拉選擇錄入月份（依 Asia/Taipei 時區預設帶入當月）、帶入上月仍持有清單、
本月已存紀錄唯讀表格（資產金額與負債應繳金額分欄，金額未填提醒）、單列新增/編輯/刪除。
選定項目後依錄入方式分派四個編輯器：股票/ETF 填總成本＋現值＋已實現損益＋現金股利、
保險填累計已繳保費＋解約金＋本月領回、活存/定存只填餘額、負債只填應繳金額；前三者存檔
前顯示推算淨投入預覽，淨投入一律由系統推算、不開放手填，項目間資金移動靠更新兩端數字
自然相抵，頁面沒有轉移功能。存檔與刪除一律由 Service 規劃完整寫入清單後交給 Repository
的批次方法，確保推算鏈要嘛全部落地、要嘛全部不變。每次成功寫入後整頁重繪，讓表格與錄入框
反映最新資料，成功訊息於下一輪顯示在頁面上方。業務正確性由下層 Service/Repository 的 SC
測試保證；本頁只做委派與呈現。
"""

# ==== 原生（標準庫） ====
import logging
from collections.abc import Callable
from typing import NamedTuple

# ==== 第三方套件 ====
import streamlit as st

# ==== 專案內部 ====
from asset_lab.amount_widget import amount_input, seed_amount_inputs
from asset_lab.bootstrap import Container
from asset_lab.core.constants import INPUT_MODE, TIMEZONE
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
from asset_lab.rerun_runtime import rerun_fragment
from asset_lab.services.balance_input_service import BalanceInputService
from asset_lab.services.cost_basis_service import CostBasisService
from asset_lab.services.monthly_input_service import MonthlyInputService
from asset_lab.services.period_service import today_in_timezone

logger = logging.getLogger("asset_lab.views.input")

# 年份下拉可選範圍：當年往前推 N 年到當年，不開放未來年份——月度錄入記的是已發生的市值/
# 淨投入，未來月份無實際數據可記；往前 5 年已足夠涵蓋近年回溯修正需求。
_YEAR_DROPDOWN_BACK_YEARS = 5

# 寫入成功後 st.rerun() 會丟掉本輪畫面，成功訊息先存進 session_state，下一輪開頭取出顯示一次。
_FLASH_KEY = "input_flash_message"

# 錄入框帶入值的播種來源記錄 key：來源改變（切換項目/月份或資料被存檔改動）才重新帶入。
# 四個編輯器各用獨立的 seed key 與 widget key，避免在不同錄入方式的項目間切換時讀到前一個
# 編輯器殘留的 session state。
_COST_BASIS_SEED_KEY = "input_cost_basis_seed"
_PREMIUM_SEED_KEY = "input_premium_seed"
_BALANCE_SEED_KEY = "input_balance_seed"
_AMOUNT_DUE_SEED_KEY = "input_amount_due_seed"

# 金額輸入框的 session_state key：播種（seed_amount_inputs）與建立 widget（amount_input）共用。
_KEY_COST_TOTAL_COST = "cost_basis_total_cost"
_KEY_COST_MARKET_VALUE = "cost_basis_market_value"
_KEY_COST_REALIZED_PNL = "cost_basis_realized_pnl"
_KEY_COST_CASH_DIVIDEND = "cost_basis_cash_dividend"
_KEY_PREMIUM_CUMULATIVE = "premium_cumulative_premium"
_KEY_PREMIUM_SURRENDER = "premium_surrender_value"
_KEY_PREMIUM_WITHDRAWAL = "premium_withdrawal"
_KEY_BALANCE = "balance_amount"
_KEY_AMOUNT_DUE = "amount_due_amount"

_PREVIEW_PLACEHOLDER = "輸入完成後顯示推算值"


class _Preview(NamedTuple):
    """推算預覽的顯示內容：前期基準值的標籤與數值、推算淨投入、是否為過渡期估算。"""

    previous_label: str
    previous_value: float
    net_investment: float
    is_transition_estimate: bool = False


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
        "賣出/不再持有：賣出當月把市值記 0，之後月份不再為該項目記列（缺列＝已不持有）。"
        "股票/ETF 把總成本與現值填 0、已實現損益填實際獲利（現金股利另填）；保險解約時解約金填 0、"
        "累計已繳保費維持不變、領回金額填實收金額；活存/定存清空時餘額填 0。"
        "淨投入由系統依填入的數字自動推算，資金在項目間移動時，直接更新兩端的數字即可。"
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

        # 每輪只讀一次；編輯器是獨立的局部重跑區塊，自己另行讀取（走讀取快取）
        holdings = holding_repo.list_holdings()
        month_records = record_repo.read_month(year_month=target_ym)

        _render_month_records(
            input_service=input_service, holdings=holdings, month_records=month_records
        )
        _render_record_editor(target_ym=target_ym)
    except AssetLabError as error:
        # Page 為唯一 catch 點：對使用者顯示友善訊息（含寫入失敗的 PersistenceError），
        # 技術細節進 log
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
    """本月已存紀錄唯讀表格：資產金額與負債應繳金額分欄，金額未填的列顯示提醒。"""
    st.subheader("本月已存紀錄")
    rows = input_service.summarize_month(records=month_records, holdings=holdings)
    if not rows:
        st.caption("本月尚無已存紀錄")
        return
    st.dataframe(
        [
            {
                "項目": row.name,
                "市值 / 餘額": "" if row.is_liability else format_amount(row.market_value),
                "應繳金額": format_amount(row.market_value) if row.is_liability else "",
                "淨投入": format_amount(row.net_investment),
                "總成本 / 累計保費": format_amount(row.total_cost),
                "已實現收益 / 領回": format_amount(row.realized_income),
                "提醒": _missing_amount_reminder(
                    is_liability=row.is_liability, missing=row.market_value_missing
                ),
            }
            for row in rows
        ],
        hide_index=True,
    )


def _missing_amount_reminder(*, is_liability: bool, missing: bool) -> str:
    """金額未填的提醒文字：負債稱應繳金額，資產稱市值。"""
    if not missing:
        return ""
    return "本月應繳金額尚未填" if is_liability else "本月市值尚未填"


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


@rerun_fragment(label="月度錄入編輯器")
def _render_record_editor(*, target_ym: str) -> None:
    """單列新增/編輯/刪除：依項目的錄入方式分派到對應編輯器。

    本函式是局部重跑區塊：改金額欄只重跑這裡，所以容器與資料都在函式內自己取得，
    不依賴整頁重跑時算好的物件。存檔或刪除成功後仍整頁重跑，讓表格與提示同步更新。
    年月沿用頁面上方「錄入年份／錄入月份」下拉選定值。錄入方式由 Service 解析；資產
    分類未指定時 Service 拒絕，這裡只顯示提示並不渲染任何錄入欄位，不默默當成某一種方式。
    """
    container = _container()
    input_service = container.monthly_input_service
    record_repo = container.record_repo
    cost_basis_service = container.cost_basis_service
    balance_service = container.balance_input_service
    holdings = container.holding_repo.list_holdings()
    month_records = record_repo.read_month(year_month=target_ym)

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

    try:
        mode = input_service.resolve_input_mode(holding=holding)
    except DataValidationError as error:
        st.error(str(error))
        return

    if mode == INPUT_MODE.COST_BASIS:
        _render_cost_basis_editor(
            record_repo=record_repo,
            cost_basis_service=cost_basis_service,
            holding=holding,
            target_ym=target_ym,
        )
    elif mode == INPUT_MODE.PREMIUM:
        _render_premium_editor(
            record_repo=record_repo,
            cost_basis_service=cost_basis_service,
            holding=holding,
            target_ym=target_ym,
        )
    elif mode == INPUT_MODE.BALANCE:
        _render_balance_editor(
            input_service=input_service,
            record_repo=record_repo,
            balance_service=balance_service,
            holding=holding,
            month_records=month_records,
            target_ym=target_ym,
        )
    else:
        _render_amount_due_editor(
            input_service=input_service,
            record_repo=record_repo,
            holding=holding,
            month_records=month_records,
            target_ym=target_ym,
        )


def _render_preview(
    *,
    parse_inputs: Callable[[], tuple],
    derive: Callable[[tuple], _Preview],
) -> None:
    """推算淨投入預覽的共用骨架。

    欄位尚未輸入完成（解析失敗）只顯示佔位提示，不當成錯誤攔下整頁；推算被拒絕（如現金
    股利或領回為負）則直接顯示拒絕原因，與「尚未輸入完成」區分。每次 rerun 都重新推算，
    讓使用者輸入到一半也能即時核對。
    """
    try:
        inputs = parse_inputs()
    except DataValidationError:
        st.caption(_PREVIEW_PLACEHOLDER)
        return
    try:
        preview = derive(inputs)
    except DataValidationError as error:
        st.error(str(error))
        return
    st.write(f"{preview.previous_label}：{format_amount(preview.previous_value)}")
    st.write(f"推算本月淨投入：{format_amount(preview.net_investment)}")
    if preview.is_transition_estimate:
        st.warning(
            f"{preview.previous_label}為過渡期估算值，可能與實際金額有落差，請留意核對。"
        )


def _render_save_delete(
    *,
    record_repo: RecordRepository,
    holding: HoldingModel,
    target_ym: str,
    plan_save: Callable[[], list[MonthlyRecordModel]],
    plan_delete: Callable[[], list[MonthlyRecordModel]],
) -> None:
    """儲存／刪除按鈕：Service 規劃完整寫入清單後，一次性交給 Repository 批次寫入。

    輸入解析與規劃只在按下按鈕時才執行；任何一步失敗都不會呼叫寫入、不會顯示成功訊息，
    使用者輸入留在錄入框可直接重試。
    """
    col_save, col_delete = st.columns(2)
    if col_save.button("儲存此列"):
        record_repo.upsert_records(records=plan_save())
        _flash_and_rerun("已儲存")
    if col_delete.button("刪除此列"):
        record_repo.delete_record_and_upsert(
            holding_id=holding.holding_id, year_month=target_ym, records=plan_delete()
        )
        _flash_and_rerun("已刪除")


def _render_cost_basis_editor(
    *,
    record_repo: RecordRepository,
    cost_basis_service: CostBasisService,
    holding: HoldingModel,
    target_ym: str,
) -> None:
    """股票/ETF：總成本＋現值＋已實現損益＋現金股利，存檔前顯示推算淨投入預覽。"""
    records = record_repo.read_holding_records(holding_id=holding.holding_id)

    prefill = cost_basis_service.build_cost_basis_prefill(records=records, year_month=target_ym)
    seed_amount_inputs(
        seed_key=_COST_BASIS_SEED_KEY,
        source=(holding.holding_id, target_ym, prefill),
        values={
            _KEY_COST_TOTAL_COST: prefill.total_cost,
            _KEY_COST_MARKET_VALUE: prefill.market_value,
            _KEY_COST_REALIZED_PNL: prefill.realized_pnl,
            _KEY_COST_CASH_DIVIDEND: prefill.cash_dividend,
        },
    )

    total_cost_text = amount_input("目前總成本", key=_KEY_COST_TOTAL_COST)
    market_value_text = amount_input("現值", key=_KEY_COST_MARKET_VALUE)
    realized_pnl_text = amount_input("本月已實現損益（可為負）", key=_KEY_COST_REALIZED_PNL)
    cash_dividend_text = amount_input("本月現金股利（不可為負）", key=_KEY_COST_CASH_DIVIDEND)

    def parse_inputs() -> tuple[float, float, float]:
        return (
            parse_amount(total_cost_text, field_label="目前總成本"),
            parse_amount(realized_pnl_text, field_label="本月已實現損益"),
            parse_amount(cash_dividend_text, field_label="本月現金股利"),
        )

    def derive(inputs: tuple) -> _Preview:
        total_cost, realized_pnl, cash_dividend = inputs
        result = cost_basis_service.derive(
            holding=holding,
            records=records,
            year_month=target_ym,
            total_cost=total_cost,
            realized_pnl=realized_pnl,
            cash_dividend=cash_dividend,
        )
        return _Preview(
            previous_label="前期總成本",
            previous_value=result.previous_total_cost,
            net_investment=result.net_investment,
            is_transition_estimate=result.is_transition_estimate,
        )

    _render_preview(parse_inputs=parse_inputs, derive=derive)

    def plan_save() -> list[MonthlyRecordModel]:
        return cost_basis_service.plan_save(
            holding=holding,
            records=records,
            year_month=target_ym,
            market_value=parse_amount(market_value_text, field_label="現值"),
            total_cost=parse_amount(total_cost_text, field_label="目前總成本"),
            realized_pnl=parse_amount(realized_pnl_text, field_label="本月已實現損益"),
            cash_dividend=parse_amount(cash_dividend_text, field_label="本月現金股利"),
        )

    _render_save_delete(
        record_repo=record_repo,
        holding=holding,
        target_ym=target_ym,
        plan_save=plan_save,
        plan_delete=lambda: cost_basis_service.plan_delete(
            holding=holding, records=records, year_month=target_ym
        ),
    )


def _render_premium_editor(
    *,
    record_repo: RecordRepository,
    cost_basis_service: CostBasisService,
    holding: HoldingModel,
    target_ym: str,
) -> None:
    """保險：累計已繳保費＋解約金＋本月領回金額，存檔前顯示推算淨投入預覽。

    累計已繳保費與解約金為必填：留空時解析失敗、不會呼叫規劃，避免空白被存成 0。
    """
    records = record_repo.read_holding_records(holding_id=holding.holding_id)

    prefill = cost_basis_service.build_premium_prefill(records=records, year_month=target_ym)
    seed_amount_inputs(
        seed_key=_PREMIUM_SEED_KEY,
        source=(holding.holding_id, target_ym, prefill),
        values={
            _KEY_PREMIUM_CUMULATIVE: prefill.cumulative_premium,
            _KEY_PREMIUM_SURRENDER: prefill.surrender_value,
            _KEY_PREMIUM_WITHDRAWAL: prefill.withdrawal,
        },
    )

    cumulative_text = amount_input("累計已繳保費", key=_KEY_PREMIUM_CUMULATIVE)
    surrender_text = amount_input("解約金", key=_KEY_PREMIUM_SURRENDER)
    withdrawal_text = amount_input("本月領回金額（不可為負）", key=_KEY_PREMIUM_WITHDRAWAL)

    def parse_inputs() -> tuple[float, float]:
        return (
            parse_amount(cumulative_text, field_label="累計已繳保費"),
            parse_amount(withdrawal_text, field_label="本月領回金額"),
        )

    def derive(inputs: tuple) -> _Preview:
        cumulative_premium, withdrawal = inputs
        result = cost_basis_service.derive_premium(
            holding=holding,
            records=records,
            year_month=target_ym,
            cumulative_premium=cumulative_premium,
            withdrawal=withdrawal,
        )
        return _Preview(
            previous_label="前期累計保費",
            previous_value=result.previous_total_cost,
            net_investment=result.net_investment,
            is_transition_estimate=result.is_transition_estimate,
        )

    _render_preview(parse_inputs=parse_inputs, derive=derive)

    def plan_save() -> list[MonthlyRecordModel]:
        return cost_basis_service.plan_save_premium(
            holding=holding,
            records=records,
            year_month=target_ym,
            surrender_value=parse_amount(surrender_text, field_label="解約金"),
            cumulative_premium=parse_amount(cumulative_text, field_label="累計已繳保費"),
            withdrawal=parse_amount(withdrawal_text, field_label="本月領回金額"),
        )

    _render_save_delete(
        record_repo=record_repo,
        holding=holding,
        target_ym=target_ym,
        plan_save=plan_save,
        plan_delete=lambda: cost_basis_service.plan_delete(
            holding=holding, records=records, year_month=target_ym
        ),
    )


def _render_balance_editor(
    *,
    input_service: MonthlyInputService,
    record_repo: RecordRepository,
    balance_service: BalanceInputService,
    holding: HoldingModel,
    month_records: list[MonthlyRecordModel],
    target_ym: str,
) -> None:
    """活存/定存：只填餘額，存檔前顯示前期餘額與推算淨投入預覽。

    餘額為必填：該月無紀錄時留空，避免沒填就存檔而把餘額存成 0。
    """
    records = record_repo.read_holding_records(holding_id=holding.holding_id)

    prefill = input_service.build_record_prefill(
        records=month_records, holding_id=holding.holding_id, year_month=target_ym
    )
    seed_amount_inputs(
        seed_key=_BALANCE_SEED_KEY,
        source=(holding.holding_id, target_ym, prefill),
        values={_KEY_BALANCE: prefill.market_value},
    )

    balance_text = amount_input("餘額", key=_KEY_BALANCE)

    def parse_inputs() -> tuple[float]:
        return (parse_amount(balance_text, field_label="餘額"),)

    def derive(inputs: tuple) -> _Preview:
        (balance,) = inputs
        result = balance_service.derive(
            holding=holding, records=records, year_month=target_ym, balance=balance
        )
        return _Preview(
            previous_label="前期餘額",
            previous_value=result.previous_balance,
            net_investment=result.net_investment,
        )

    _render_preview(parse_inputs=parse_inputs, derive=derive)

    _render_save_delete(
        record_repo=record_repo,
        holding=holding,
        target_ym=target_ym,
        plan_save=lambda: balance_service.plan_save(
            holding=holding,
            records=records,
            year_month=target_ym,
            balance=parse_amount(balance_text, field_label="餘額"),
        ),
        plan_delete=lambda: balance_service.plan_delete(
            holding=holding, records=records, year_month=target_ym
        ),
    )


def _render_amount_due_editor(
    *,
    input_service: MonthlyInputService,
    record_repo: RecordRepository,
    holding: HoldingModel,
    month_records: list[MonthlyRecordModel],
    target_ym: str,
) -> None:
    """負債：只填應繳金額（淨投入固定 0，不需預覽）；存檔與刪除同樣走批次寫入。"""
    prefill = input_service.build_record_prefill(
        records=month_records, holding_id=holding.holding_id, year_month=target_ym
    )
    seed_amount_inputs(
        seed_key=_AMOUNT_DUE_SEED_KEY,
        source=(holding.holding_id, target_ym, prefill),
        values={_KEY_AMOUNT_DUE: prefill.market_value},
    )

    amount_due_text = amount_input("應繳金額", key=_KEY_AMOUNT_DUE)

    def plan_save() -> list[MonthlyRecordModel]:
        return [
            input_service.build_amount_due_record(
                holding=holding,
                year_month=target_ym,
                amount_due=parse_amount(amount_due_text, field_label="應繳金額"),
            )
        ]

    _render_save_delete(
        record_repo=record_repo,
        holding=holding,
        target_ym=target_ym,
        plan_save=plan_save,
        plan_delete=list,
    )


render()
