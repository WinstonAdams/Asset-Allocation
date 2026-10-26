"""買房獨立頁（View / Controller）。

職責：編排可負擔性試算（AffordabilityService）與買房評估（HouseService）——讀
`effective_params` → 讀主檔與全部月度紀錄算 `bucket_value`/`cash_reserve_value` →
算 `affordable_total_price`（由月收反推）與目標總價的 `payment_for_price`（正算）→
`bucket_progress`/`bucket_composition_warning`/`assess_triggers` → 渲染。含可負擔性
試算結果、bucket 進度與組成警示、五條觸發條件清單（定錨/認知兩條主觀勾選即時
`upsert_trigger`，無需另按儲存）。本頁為唯一 catch 點。

引擎與評估的業務正確性由 AffordabilityService/HouseService 的 SC 測試保證；本頁只做
委派、資料組裝（含月度紀錄 DataFrame→模型清單的轉換）與渲染，不算任何業務值。
"""

# ==== 原生（標準庫） ====
import logging

# ==== 第三方套件 ====
import pandas as pd
import streamlit as st

# ==== 專案內部 ====
from asset_lab.bootstrap import Container
from asset_lab.core.constants import HOUSE_TRIGGER, TIMEZONE
from asset_lab.core.exceptions import AssetLabError
from asset_lab.error_boundary import guarded_callback, show_callback_error
from asset_lab.models.house import SubjectiveTriggerModel
from asset_lab.models.record import MonthlyRecordModel
from asset_lab.models.results import (
    AffordabilityResult,
    BucketCompositionWarning,
    BucketProgress,
    TriggerChecklist,
)
from asset_lab.rerun_runtime import verified_container
from asset_lab.services.period_service import today_in_timezone

logger = logging.getLogger("asset_lab.views.house")

# 觸發條件鍵→中文標籤，供五條檢核清單與缺口清單顯示（HOUSE_TRIGGER.ALL 值域固定五條）。
_TRIGGER_LABEL = {
    HOUSE_TRIGGER.ANCHOR: "定錨",
    HOUSE_TRIGGER.INCOME: "收入",
    HOUSE_TRIGGER.DOWN_PAYMENT: "自備",
    HOUSE_TRIGGER.PAYMENT: "月付",
    HOUSE_TRIGGER.COGNITION: "認知",
}

# 客觀觸發條件的 actual/required 呈現單位：月付為百分比，收入/自備為金額（TWD）。
_PERCENT_TRIGGERS = (HOUSE_TRIGGER.PAYMENT,)


def _container() -> Container:
    """取放行後存入 session 的依賴容器。"""
    return st.session_state["container"]


def render() -> None:
    """渲染買房頁：可負擔性試算、bucket 進度與組成警示、五條觸發條件檢核。"""
    st.title("買房")
    show_callback_error()
    container = _container()

    try:
        house_service = container.house_service
        affordability_service = container.affordability_service

        params = house_service.effective_params(stored=container.house_param_repo.read_params())
        holdings = container.holding_repo.list_holdings()
        month_records = _to_month_records(container.record_repo.read_all())

        bucket_value = house_service.bucket_value(month_records=month_records, holdings=holdings)
        cash_reserve_value = house_service.cash_reserve_value(
            month_records=month_records, holdings=holdings
        )
        reverse_result = affordability_service.affordable_total_price(
            monthly_income=params.monthly_after_tax_income,
            payment_cap_ratio_pct=params.payment_cap_ratio,
            test_annual_rate_pct=params.test_annual_rate,
            loan_years=params.loan_years,
            down_payment_ratio_pct=params.down_payment_ratio,
        )
        forward_result = affordability_service.payment_for_price(
            total_price=params.target_total_price,
            down_payment_ratio_pct=params.down_payment_ratio,
            test_annual_rate_pct=params.test_annual_rate,
            loan_years=params.loan_years,
            monthly_income=params.monthly_after_tax_income,
        )
        progress = house_service.bucket_progress(
            bucket_value=bucket_value,
            params=params,
            current_year=today_in_timezone(TIMEZONE).year,
        )
        warning = house_service.bucket_composition_warning(
            holdings=holdings,
            month_records=month_records,
            years_to_target=progress.years_to_target,
        )
        subjective = container.subjective_trigger_repo.read_triggers()
        checklist = house_service.assess_triggers(
            params=params,
            bucket_value=bucket_value,
            cash_reserve_value=cash_reserve_value,
            forward_result=forward_result,
            subjective=subjective,
        )

        _render_affordability(reverse_result=reverse_result, forward_result=forward_result)
        _render_bucket(progress=progress, warning=warning)
        _render_triggers(checklist=checklist, subjective=subjective)
    except AssetLabError as error:
        logger.exception("買房頁渲染失敗")
        st.error(str(error))


def _to_month_records(records_df: pd.DataFrame) -> list[MonthlyRecordModel]:
    """把月度紀錄 DataFrame（RecordRepository.read_all 產出）轉為 HouseService 消費的模型清單。

    HouseService 的 bucket/現金預備金口徑須橫跨全歷史月份（判定「是否曾有任何紀錄」，
    見 HouseService._current_market_values），故取全量而非僅最新月。
    """
    return [
        MonthlyRecordModel(
            holding_id=row.holding_id,
            year_month=row.year_month,
            market_value=None if pd.isna(row.market_value) else row.market_value,
            net_investment=row.net_investment,
        )
        for row in records_df.itertuples(index=False)
    ]


def _render_affordability(
    *, reverse_result: AffordabilityResult, forward_result: AffordabilityResult
) -> None:
    """可負擔性試算：依目前買房參數反推可負擔總價，並正算目標總價的月付占比。"""
    st.subheader("可負擔性試算")
    columns = st.columns(2)
    columns[0].metric("可負擔總價（反推）", _format_amount(reverse_result.affordable_total_price))
    columns[1].metric("目標總價月付占比（正算）", _format_percent(forward_result.income_share_pct))


def _render_bucket(*, progress: BucketProgress, warning: BucketCompositionWarning) -> None:
    """自備款 bucket 進度與組成序列風險提示。"""
    st.subheader("自備款 bucket 進度")
    columns = st.columns(3)
    columns[0].metric("目前 bucket", _format_amount(progress.bucket_value))
    columns[1].metric("目標金額", _format_amount(progress.target_amount))
    columns[2].metric("進度", _format_percent(progress.progress_pct))

    if progress.reached_target_year:
        st.info("已到或已過目標購屋年份")
    elif progress.required_annual_accumulation is not None:
        st.write(f"每年需累積：{_format_amount(progress.required_annual_accumulation)}")

    if warning.has_non_cash:
        non_cash_amount = _format_amount(warning.non_cash_value)
        message = f"bucket 含非活存/定存資產（{non_cash_amount}），有序列風險"
        if warning.intensified:
            st.error(f"{message}，距目標年剩餘年限已短，建議優先調整組成")
        else:
            st.warning(message)


def _render_triggers(
    *, checklist: TriggerChecklist, subjective: list[SubjectiveTriggerModel]
) -> None:
    """五條觸發條件檢核：逐條顯示達成狀態、達成計數；5/5 顯示可啟動購屋，否則列缺口清單。"""
    st.subheader("觸發條件檢核")
    checked_map = {row.trigger_key: row.checked for row in subjective}

    for condition in checklist.conditions:
        label = _TRIGGER_LABEL[condition.key]
        if condition.kind == "subjective":
            _render_subjective_checkbox(
                trigger_key=condition.key,
                label=label,
                checked=checked_map.get(condition.key, False),
            )
        else:
            icon = "✅" if condition.met else "⬜"
            st.write(f"{icon} {label}：{'達成' if condition.met else '未達成'}")

    st.metric("達成計數", f"{checklist.met_count}/{len(checklist.conditions)}")

    if checklist.all_met:
        st.success("可啟動購屋")
        return

    st.warning("尚未達成全部觸發條件")
    st.markdown("**缺口清單**")
    for condition in checklist.conditions:
        if condition.met:
            continue
        label = _TRIGGER_LABEL[condition.key]
        if condition.kind == "subjective":
            st.write(f"- {label}（未勾選）")
        else:
            unit = "%" if condition.key in _PERCENT_TRIGGERS else "元"
            actual_text = _format_gap_value(condition.actual, unit)
            required_text = _format_gap_value(condition.required, unit)
            st.write(f"- {label}（實際 {actual_text} vs 門檻 {required_text}）")


def _render_subjective_checkbox(*, trigger_key: str, label: str, checked: bool) -> None:
    """主觀觸發勾選框：勾選狀態變動即時持久化，不需另按儲存按鈕。"""
    key = f"house_trigger_{trigger_key}"
    st.checkbox(
        label,
        value=checked,
        key=key,
        on_change=_persist_subjective_trigger,
        kwargs={"trigger_key": trigger_key, "widget_key": key},
    )


@guarded_callback(context="買房主觀勾選")
def _persist_subjective_trigger(*, trigger_key: str, widget_key: str) -> None:
    """把使用者剛勾選/取消的主觀觸發狀態即時寫回 DB。

    callback 在腳本主體之前執行，不能沿用上一輪抓住的 repo（閒置後連線可能已失效），
    所以自行取已驗證連線的容器。
    """
    checked = st.session_state[widget_key]
    verified_container().subjective_trigger_repo.upsert_trigger(
        trigger=SubjectiveTriggerModel(trigger_key=trigger_key, checked=checked)
    )


def _format_amount(value: float | None) -> str:
    """金額格式化（TWD）；None 顯示破折號。"""
    if value is None:
        return "—"
    return f"{value:,.0f} 元"


def _format_percent(value: float | None) -> str:
    """百分比格式化（已換算的百分比數值）；None 顯示破折號。"""
    if value is None:
        return "—"
    return f"{value:.1f}%"


def _format_gap_value(value: float | None, unit: str) -> str:
    """依單位格式化缺口清單的 actual/required 數值；None 代表對應參數尚未設定。"""
    if value is None:
        return "未設定"
    if unit == "%":
        return f"{value:.1f}%"
    return f"{value:,.0f} 元"


render()
