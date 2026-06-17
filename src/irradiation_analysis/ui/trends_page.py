from __future__ import annotations

from collections import defaultdict

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from irradiation_analysis.analytics import build_abnormal_events
from irradiation_analysis.excel_io import ImportResult
from irradiation_analysis.models import MonitoringRecord, MonitoringStatus
from irradiation_analysis.status import classify_record
from irradiation_analysis.ui.styles import format_datetime, status_label


def render_trends_page() -> None:
    st.header("三、趋势分析")
    result = _import_result()
    if result is None or not result.records:
        st.info("请先导入有效记录，再查看趋势分析。")
        return

    records = result.records
    selected_device, selected_type, selected_unit = _render_series_selectors(records)
    series_records = _series_records(records, selected_device, selected_type, selected_unit)

    if series_records:
        st.plotly_chart(_series_figure(series_records), use_container_width=True)
    else:
        st.warning("当前选择下没有可绘制的监测序列。")

    selected_room = selected_device.split("-")[0] if selected_device else sorted({r.room_id for r in records})[0]
    st.plotly_chart(_room_abnormal_figure(records, selected_room), use_container_width=True)
    _render_event_table(records)


def _import_result() -> ImportResult | None:
    return st.session_state.get("import_result")


def _render_series_selectors(records: list[MonitoringRecord]) -> tuple[str, str, str]:
    devices = sorted({record.device_id for record in records})
    selected_device = st.selectbox(
        "设备",
        devices,
        index=devices.index(st.session_state.selected_device_id)
        if st.session_state.get("selected_device_id") in devices
        else 0,
    )
    st.session_state.selected_device_id = selected_device

    type_options = sorted(
        {record.monitor_type for record in records if record.device_id == selected_device}
    )
    selected_type = st.selectbox("监测类型", type_options)

    unit_options = sorted(
        {
            record.unit
            for record in records
            if record.device_id == selected_device and record.monitor_type == selected_type
        }
    )
    selected_unit = st.selectbox("单位", unit_options)
    return selected_device, selected_type, selected_unit


def _series_records(
    records: list[MonitoringRecord],
    device_id: str,
    monitor_type: str,
    unit: str,
) -> list[MonitoringRecord]:
    return sorted(
        (
            record
            for record in records
            if record.device_id == device_id
            and record.monitor_type == monitor_type
            and record.unit == unit
        ),
        key=lambda record: (record.monitored_at, record.import_order),
    )


def _series_figure(records: list[MonitoringRecord]) -> go.Figure:
    figure = go.Figure()
    times = [record.monitored_at for record in records]
    figure.add_trace(
        go.Scatter(
            x=times,
            y=[record.value for record in records],
            mode="lines+markers",
            name="监测值",
            line={"color": "#2563eb", "width": 3},
        )
    )
    figure.add_trace(
        go.Scatter(
            x=times,
            y=[record.warning_threshold for record in records],
            mode="lines",
            name="预警值",
            line={"color": "#f59e0b", "dash": "dash"},
        )
    )
    figure.add_trace(
        go.Scatter(
            x=times,
            y=[record.control_threshold for record in records],
            mode="lines",
            name="控制值",
            line={"color": "#dc2626", "dash": "dot"},
        )
    )
    latest = records[-1]
    figure.update_layout(
        title=f"{latest.device_id} / {latest.monitor_type}（{latest.unit}）",
        xaxis_title="时间",
        yaxis_title=latest.unit,
        hovermode="x unified",
        legend={"orientation": "h"},
    )
    return figure


def _room_abnormal_figure(records: list[MonitoringRecord], room_id: str) -> go.Figure:
    abnormal_by_day: dict[object, set[str]] = defaultdict(set)
    for record in records:
        if record.room_id != room_id:
            continue
        if classify_record(record).severity > MonitoringStatus.NORMAL.severity:
            abnormal_by_day[record.monitored_at.date()].add(record.device_id)

    days = sorted({record.monitored_at.date() for record in records if record.room_id == room_id})
    counts = [len(abnormal_by_day.get(day, set())) for day in days]
    figure = go.Figure(
        go.Bar(
            x=days,
            y=counts,
            marker={"color": "#3b82f6"},
            name="异常设备数",
        )
    )
    figure.update_layout(
        title=f"{room_id} 房间异常设备数趋势",
        xaxis_title="日期",
        yaxis_title="异常设备数",
    )
    return figure


def _render_event_table(records: list[MonitoringRecord]) -> None:
    st.subheader("事件表")
    events = build_abnormal_events(records)
    if not events:
        st.info("当前数据未形成异常事件。")
        return

    st.dataframe(
        pd.DataFrame(
            {
                "房间": event.room_id,
                "设备": event.device_id,
                "类型": event.monitor_type,
                "单位": event.unit,
                "开始": format_datetime(event.started_at),
                "结束": format_datetime(event.ended_at),
                "最高状态": status_label(event.highest_status),
                "峰值": event.peak_value,
                "峰值时间": format_datetime(event.peak_time),
                "记录数": event.record_count,
                "持续天数": event.duration_days,
            }
            for event in events
        ),
        use_container_width=True,
        hide_index=True,
    )
