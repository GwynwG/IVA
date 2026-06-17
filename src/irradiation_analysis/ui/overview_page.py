from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from irradiation_analysis.analytics import build_abnormal_events, rank_device_risks
from irradiation_analysis.excel_io import ImportResult
from irradiation_analysis.forecast import ForecastHorizon, forecast_system
from irradiation_analysis.layout import build_facility_figure
from irradiation_analysis.models import MonitoringRecord, MonitoringSnapshot, MonitoringStatus
from irradiation_analysis.snapshots import build_point_in_time_snapshot, build_range_snapshot
from irradiation_analysis.ui.styles import (
    format_datetime,
    format_number,
    render_metrics,
    status_counts,
    status_label,
)


def render_overview_page() -> None:
    st.header("二、空间总览")
    result = _import_result()
    if result is None or not result.records:
        st.info("请先在数据导入阶段完成有效记录导入，再查看空间态势。")
        return

    records = result.records
    snapshot = _render_snapshot_controls(records)
    filtered_device_ids, type_filter = _render_filters(records, snapshot)

    _render_status_metrics(snapshot)
    selected_device_id = _render_device_selector(filtered_device_ids, snapshot)
    st.plotly_chart(
        build_facility_figure(snapshot, selected_device_id=selected_device_id),
        use_container_width=True,
    )
    _render_device_detail(
        records=records,
        snapshot=snapshot,
        selected_device_id=selected_device_id,
        type_filter=type_filter,
    )


def _import_result() -> ImportResult | None:
    return st.session_state.get("import_result")


def _render_snapshot_controls(records: list[MonitoringRecord]) -> MonitoringSnapshot:
    st.subheader("快照控制")
    times = sorted({record.monitored_at for record in records})
    current_mode = st.session_state.get("snapshot_mode", "时间点")
    mode = st.radio(
        "快照模式",
        ["时间点", "时间范围"],
        index=0 if current_mode == "时间点" else 1,
        horizontal=True,
        key="snapshot_mode",
    )

    if mode == "时间范围" and len(times) > 1:
        start, end = st.select_slider(
            "选择时间范围",
            options=times,
            value=(times[0], times[-1]),
            format_func=format_datetime,
        )
        if start > end:
            start, end = end, start
        return build_range_snapshot(records, start, end)

    selected_at = st.select_slider(
        "选择快照时间",
        options=times,
        value=times[-1],
        format_func=format_datetime,
    )
    return build_point_in_time_snapshot(records, selected_at)


def _render_filters(
    records: list[MonitoringRecord],
    snapshot: MonitoringSnapshot,
) -> tuple[list[str], set[str]]:
    st.subheader("筛选条件")
    rooms = sorted({record.room_id for record in records})
    devices = sorted(snapshot.devices)
    monitor_types = sorted({record.monitor_type for record in records})
    statuses = list(MonitoringStatus)

    columns = st.columns(4)
    room_filter = set(columns[0].multiselect("房间", rooms, default=[]))
    device_filter = set(columns[1].multiselect("设备", devices, default=[]))
    type_filter = set(columns[2].multiselect("监测类型", monitor_types, default=[]))
    status_filter = set(
        columns[3].multiselect(
            "状态",
            statuses,
            default=[],
            format_func=status_label,
        )
    )

    devices_with_type = {
        record.device_id
        for record in records
        if not type_filter or record.monitor_type in type_filter
    }
    filtered = []
    for device_id, device_snapshot in snapshot.devices.items():
        if room_filter and device_snapshot.room_id not in room_filter:
            continue
        if device_filter and device_id not in device_filter:
            continue
        if type_filter and device_id not in devices_with_type:
            continue
        if status_filter and device_snapshot.status not in status_filter:
            continue
        filtered.append(device_id)
    return sorted(filtered), type_filter


def _render_status_metrics(snapshot: MonitoringSnapshot) -> None:
    counts = status_counts(device.status for device in snapshot.devices.values())
    render_metrics(
        [
            ("正常设备", counts[MonitoringStatus.NORMAL], None),
            ("预警设备", counts[MonitoringStatus.WARNING], None),
            ("事故级设备", counts[MonitoringStatus.ACCIDENT], None),
            ("无数据设备", counts[MonitoringStatus.NO_DATA], None),
        ]
    )


def _render_device_selector(
    device_ids: list[str],
    snapshot: MonitoringSnapshot,
) -> str | None:
    if not device_ids:
        st.warning("当前筛选条件下没有可展示的设备。")
        return None

    current = st.session_state.get("selected_device_id")
    preferred = current if current in device_ids else _first_attention_device(device_ids, snapshot)
    index = device_ids.index(preferred) if preferred in device_ids else 0
    selected = st.selectbox("设备详情", device_ids, index=index)
    st.session_state.selected_device_id = selected
    st.session_state.selected_room_id = snapshot.devices[selected].room_id
    return selected


def _first_attention_device(
    device_ids: list[str],
    snapshot: MonitoringSnapshot,
) -> str:
    return next(
        (
            device_id
            for device_id in device_ids
            if snapshot.devices[device_id].status.severity > MonitoringStatus.NORMAL.severity
        ),
        device_ids[0],
    )


def _render_device_detail(
    *,
    records: list[MonitoringRecord],
    snapshot: MonitoringSnapshot,
    selected_device_id: str | None,
    type_filter: set[str],
) -> None:
    st.subheader("设备详情")
    if selected_device_id is None:
        st.info("请选择一个设备查看明细。")
        return

    device_snapshot = snapshot.devices[selected_device_id]
    latest_records = sorted(
        (
            record
            for record in device_snapshot.latest_by_series.values()
            if not type_filter or record.monitor_type in type_filter
        ),
        key=lambda record: (record.monitor_type, record.unit),
    )
    render_metrics(
        [
            ("设备", selected_device_id, None),
            ("房间", device_snapshot.room_id, None),
            ("当前状态", status_label(device_snapshot.status), None),
            ("最新序列", len(latest_records), None),
        ]
    )

    if latest_records:
        st.dataframe(
            pd.DataFrame(_latest_record_row(record, snapshot.selected_at) for record in latest_records),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("该设备在当前快照下暂无有效监测序列。")

    device_events = [
        event for event in build_abnormal_events(records) if event.device_id == selected_device_id
    ]
    device_risks = {
        risk.device_id: risk for risk in rank_device_risks(records)
    }
    device_forecasts = _forecasts_for_device(records, selected_device_id)

    columns = st.columns(3)
    with columns[0]:
        st.markdown("**事件**")
        if device_events:
            st.dataframe(
                pd.DataFrame(
                    {
                        "开始": format_datetime(event.started_at),
                        "结束": format_datetime(event.ended_at),
                        "类型": event.monitor_type,
                        "峰值": event.peak_value,
                        "状态": status_label(event.highest_status),
                    }
                    for event in device_events
                ),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.caption("暂无异常事件。")
    with columns[1]:
        st.markdown("**风险**")
        risk = device_risks.get(selected_device_id)
        if risk:
            st.write(f"风险评分：{risk.score:.1f}")
            st.caption("；".join(risk.reasons))
        else:
            st.caption("暂无风险排序结果。")
    with columns[2]:
        st.markdown("**预测**")
        if device_forecasts:
            st.dataframe(
                pd.DataFrame(
                    {
                        "类型": forecast.monitor_type,
                        "预测时间": format_datetime(forecast.predicted_at),
                        "预测值": forecast.predicted_value,
                        "状态": status_label(forecast.predicted_status),
                    }
                    for forecast in device_forecasts[:5]
                ),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.caption("暂无预测结果。")


def _latest_record_row(record: MonitoringRecord, selected_at: datetime) -> dict[str, object]:
    age_days = max(0.0, (selected_at - record.monitored_at).total_seconds() / 86400.0)
    return {
        "监测类型": record.monitor_type,
        "数值": format_number(record.value),
        "单位": record.unit,
        "预警值": format_number(record.warning_threshold),
        "控制值": format_number(record.control_threshold),
        "记录时间": format_datetime(record.monitored_at),
        "记录年龄(天)": f"{age_days:.1f}",
    }


def _forecasts_for_device(records: list[MonitoringRecord], device_id: str):
    try:
        forecast = forecast_system(records, ForecastHorizon.NEXT_RECORD)
    except ValueError:
        return []
    return [
        series_forecast
        for series_forecast in forecast.series_forecasts
        if series_forecast.device_id == device_id
    ]
