from __future__ import annotations

from datetime import date, datetime, time

import streamlit as st

from irradiation_analysis.analytics import build_abnormal_events, rank_device_risks, rank_room_risks
from irradiation_analysis.excel_io import ImportResult
from irradiation_analysis.forecast import ForecastHorizon, forecast_system
from irradiation_analysis.generator import (
    DEFAULT_MONITOR_TYPES,
    SimulationConfig,
    build_blank_template,
    build_prefilled_template,
    generate_simulated_workbooks,
)
from irradiation_analysis.reporting import AnalysisReportInput, build_analysis_report
from irradiation_analysis.snapshots import build_point_in_time_snapshot
from irradiation_analysis.ui.styles import EXCEL_MIME, FORECAST_DISCLAIMER


def render_reports_page() -> None:
    st.header("五、报告生成")
    result = _import_result()
    _render_analysis_report_download(result)
    _render_template_downloads()
    _render_simulation_download()


def _import_result() -> ImportResult | None:
    return st.session_state.get("import_result")


def _render_analysis_report_download(result: ImportResult | None) -> None:
    st.subheader("分析报告")
    if result is None or not result.records:
        st.info("导入有效记录后，可下载包含摘要、事件、风险、预测和清洗数据的多工作表分析报告。")
        return

    report_bytes = _build_report_bytes(result)
    st.download_button(
        "下载多工作表分析报告",
        data=report_bytes,
        file_name=f"irradiation_analysis_report_{datetime.now():%Y%m%d_%H%M%S}.xlsx",
        mime=EXCEL_MIME,
    )
    st.caption(FORECAST_DISCLAIMER)


def _render_template_downloads() -> None:
    st.subheader("模板下载")
    columns = st.columns(2)
    with columns[0]:
        st.download_button(
            "下载空白模板",
            data=build_blank_template(),
            file_name="irradiation_monitoring_blank_template.xlsx",
            mime=EXCEL_MIME,
        )
    with columns[1]:
        template_date = st.date_input("预填模板日期", value=date(2026, 1, 1))
        st.caption("默认监测类型：" + "、".join(DEFAULT_MONITOR_TYPES))
        config = SimulationConfig(
            start=datetime.combine(template_date, time.min),
            end=datetime.combine(template_date, time.min),
        )
        st.download_button(
            "下载预填模板",
            data=build_prefilled_template(config),
            file_name=f"irradiation_prefilled_template_{template_date:%Y%m%d}.xlsx",
            mime=EXCEL_MIME,
        )


def _render_simulation_download() -> None:
    st.subheader("模拟数据")
    columns = st.columns(4)
    start_date = columns[0].date_input("模拟开始日期", value=date(2026, 1, 1))
    end_date = columns[1].date_input("模拟结束日期", value=date(2026, 1, 7))
    sampling_hours = columns[2].number_input("采样间隔（小时）", min_value=1, max_value=168, value=24)
    seed = columns[3].number_input("随机种子", min_value=0, max_value=999999, value=2026)

    columns = st.columns(4)
    warning_ratio = columns[0].number_input("预警序列比例", min_value=0.0, max_value=1.0, value=0.05, step=0.01)
    accident_ratio = columns[1].number_input("事故级序列比例", min_value=0.0, max_value=1.0, value=0.02, step=0.01)
    rapid_ratio = columns[2].number_input("快速增长比例", min_value=0.0, max_value=1.0, value=0.02, step=0.01)
    event_duration = columns[3].number_input("事件持续采样数", min_value=1, max_value=30, value=3)

    config = SimulationConfig(
        start=datetime.combine(start_date, time.min),
        end=datetime.combine(end_date, time.min),
        sampling_hours=int(sampling_hours),
        output_mode="single",
        warning_ratio=float(warning_ratio),
        accident_ratio=float(accident_ratio),
        rapid_growth_ratio=float(rapid_ratio),
        event_duration=int(event_duration),
        seed=int(seed),
    )
    try:
        workbooks = generate_simulated_workbooks(config)
    except ValueError as error:
        st.warning(f"模拟数据暂不可生成：{error}")
        return

    workbook = workbooks[0]
    st.download_button(
        "下载模拟数据工作簿",
        data=workbook.content,
        file_name=workbook.filename,
        mime=EXCEL_MIME,
    )


def _build_report_bytes(result: ImportResult) -> bytes:
    records = result.records
    selected_at = max(record.monitored_at for record in records)
    snapshot = build_point_in_time_snapshot(records, selected_at)
    events = build_abnormal_events(records)
    device_risks = rank_device_risks(records)
    room_risks = rank_room_risks(records, device_risks)
    system_forecast = forecast_system(records, ForecastHorizon.DAYS_7)
    report_input = AnalysisReportInput(
        import_result=result,
        snapshot=snapshot,
        events=events,
        device_risks=device_risks,
        room_risks=room_risks,
        series_forecasts=system_forecast.series_forecasts,
        system_forecast=system_forecast,
    )
    return build_analysis_report(report_input)
