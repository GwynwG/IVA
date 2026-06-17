from __future__ import annotations

import pandas as pd
import streamlit as st

from irradiation_analysis.analytics import (
    find_growth_signals,
    find_near_threshold,
    rank_device_risks,
    rank_room_risks,
)
from irradiation_analysis.excel_io import ImportResult
from irradiation_analysis.forecast import ForecastHorizon, forecast_system
from irradiation_analysis.models import GrowthSignal, MonitoringRecord, RiskResult, RoomRiskResult
from irradiation_analysis.ui.styles import FORECAST_DISCLAIMER, format_datetime, status_label


def render_intelligence_page() -> None:
    st.header("四、智能研判")
    result = _import_result()
    if result is None or not result.records:
        st.info("请先导入有效记录，再查看智能研判。")
        return

    records = result.records
    device_risks = rank_device_risks(records)
    room_risks = rank_room_risks(records, device_risks)
    growth_signals = find_growth_signals(records)
    near_warning = find_near_threshold(records)

    _render_rankings(device_risks, room_risks)
    _render_attention_lists(growth_signals, near_warning)
    _render_forecasts(records)


def _import_result() -> ImportResult | None:
    return st.session_state.get("import_result")


def _render_rankings(
    device_risks: list[RiskResult],
    room_risks: list[RoomRiskResult],
) -> None:
    st.subheader("风险排名")
    columns = st.columns(2)
    with columns[0]:
        st.markdown("**设备风险排名**")
        st.dataframe(
            pd.DataFrame(_device_risk_row(risk, rank) for rank, risk in enumerate(device_risks[:20], start=1)),
            use_container_width=True,
            hide_index=True,
        )
    with columns[1]:
        st.markdown("**房间风险排名**")
        st.dataframe(
            pd.DataFrame(_room_risk_row(risk, rank) for rank, risk in enumerate(room_risks[:20], start=1)),
            use_container_width=True,
            hide_index=True,
        )


def _render_attention_lists(
    growth_signals: list[GrowthSignal],
    near_warning: list[MonitoringRecord],
) -> None:
    st.subheader("重点关注")
    columns = st.columns(2)
    with columns[0]:
        st.markdown("**快速增长**")
        if growth_signals:
            st.dataframe(
                pd.DataFrame(_growth_row(signal) for signal in growth_signals[:20]),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.caption("未检测到快速增长序列。")
    with columns[1]:
        st.markdown("**接近预警**")
        if near_warning:
            st.dataframe(
                pd.DataFrame(_near_warning_row(record) for record in near_warning[:20]),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.caption("未检测到接近预警的正常记录。")


def _render_forecasts(records: list[MonitoringRecord]) -> None:
    st.subheader("趋势预测")
    horizon = st.selectbox(
        "预测周期",
        list(ForecastHorizon),
        format_func=lambda value: value.value,
    )
    try:
        system_forecast = forecast_system(records, horizon)
    except ValueError as error:
        st.warning(f"预测暂不可用：{error}")
        return

    st.caption(FORECAST_DISCLAIMER)
    st.markdown("**系统预测**")
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "预测周期": system_forecast.horizon.value,
                    "预测序列数": len(system_forecast.series_forecasts),
                    "正常设备": system_forecast.normal_devices,
                    "预警设备": system_forecast.warning_devices,
                    "事故级设备": system_forecast.accident_devices,
                    "无数据设备": system_forecast.no_data_devices,
                    "摘要": system_forecast.summary,
                }
            ]
        ),
        use_container_width=True,
        hide_index=True,
    )

    st.markdown("**设备预测**")
    st.dataframe(
        pd.DataFrame(
            {
                "房间": forecast.room_id,
                "设备": forecast.device_id,
                "类型": forecast.monitor_type,
                "单位": forecast.unit,
                "预测时间": format_datetime(forecast.predicted_at),
                "预测值": forecast.predicted_value,
                "预测状态": status_label(forecast.predicted_status),
                "预警值": forecast.warning_threshold,
                "控制值": forecast.control_threshold,
                "方法": forecast.method,
                "样本数": forecast.sample_count,
                "置信度": forecast.confidence,
            }
            for forecast in system_forecast.series_forecasts
        ),
        use_container_width=True,
        hide_index=True,
    )


def _device_risk_row(risk: RiskResult, rank: int) -> dict[str, object]:
    return {
        "排名": rank,
        "房间": risk.room_id,
        "设备": risk.device_id,
        "评分": risk.score,
        "状态": status_label(risk.status),
        "记录数": risk.record_count,
        "事件数": len(risk.events),
        "增长信号": len(risk.growth_signals),
        "原因": "；".join(risk.reasons),
    }


def _room_risk_row(risk: RoomRiskResult, rank: int) -> dict[str, object]:
    return {
        "排名": rank,
        "房间": risk.room_id,
        "评分": risk.score,
        "最高设备评分": risk.max_device_score,
        "异常设备比例": risk.abnormal_device_ratio,
        "事件数": risk.event_count,
        "最长持续天数": risk.longest_event_duration_days,
        "原因": "；".join(risk.reasons),
    }


def _growth_row(signal: GrowthSignal) -> dict[str, object]:
    return {
        "房间": signal.room_id,
        "设备": signal.device_id,
        "类型": signal.monitor_type,
        "最新时间": format_datetime(signal.latest_at),
        "最新值": signal.latest_value,
        "前值": signal.previous_value,
        "变化": signal.recent_change,
        "日斜率": signal.recent_slope_per_day,
        "评分": signal.score,
    }


def _near_warning_row(record: MonitoringRecord) -> dict[str, object]:
    ratio = record.value / record.warning_threshold if record.warning_threshold > 0 else 0.0
    return {
        "房间": record.room_id,
        "设备": record.device_id,
        "类型": record.monitor_type,
        "时间": format_datetime(record.monitored_at),
        "数值": record.value,
        "预警值": record.warning_threshold,
        "占预警值": f"{ratio:.1%}",
    }
