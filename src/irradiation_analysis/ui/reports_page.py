from __future__ import annotations

from datetime import date, datetime, time
from typing import Any

import pandas as pd
import streamlit as st

from irradiation_analysis.excel_io import ImportResult, UploadedWorkbook, import_workbooks
from irradiation_analysis.forecast import ForecastHorizon
from irradiation_analysis.generator import (
    DEFAULT_MONITOR_TYPES,
    SimulationConfig,
    build_blank_template,
    build_prefilled_template,
    generate_simulated_workbooks,
)
from irradiation_analysis.models import QualityIssue
from irradiation_analysis.report_service import build_analysis_report_from_import_result
from irradiation_analysis.ui.styles import EXCEL_MIME, FORECAST_DISCLAIMER, inject_styles, render_metrics


REPORT_APP_TITLE = "辐照监测报告生成器"
REPORT_STATE_KEYS = {
    "report_selected_sheet_by_file": {},
}
HORIZON_OPTIONS = {horizon.value: horizon for horizon in ForecastHorizon}


def run_report_app() -> None:
    st.set_page_config(page_title=REPORT_APP_TITLE, layout="wide")
    _ensure_report_state()
    inject_styles()

    st.title(REPORT_APP_TITLE)
    st.caption("独立运行的报告、模板和模拟数据生成单元。")
    render_reports_page()


def render_reports_page() -> None:
    tabs = st.tabs(("分析报告", "模板下载", "模拟数据"))
    with tabs[0]:
        _render_report_builder()
    with tabs[1]:
        _render_template_downloads()
    with tabs[2]:
        _render_simulation_download()


def _ensure_report_state() -> None:
    for key, value in REPORT_STATE_KEYS.items():
        if key not in st.session_state:
            st.session_state[key] = value.copy()


def _render_report_builder() -> None:
    st.header("分析报告")
    uploaded_files = st.file_uploader(
        "上传用于生成报告的监测数据工作簿（.xlsx，可多选）",
        type=["xlsx"],
        accept_multiple_files=True,
        help="报告生成器会独立完成工作表识别、数据校验、风险研判和预测汇总。",
    )
    workbooks = _uploaded_workbooks(uploaded_files or [])
    selected_label = st.selectbox(
        "预测周期",
        options=list(HORIZON_OPTIONS),
        index=list(HORIZON_OPTIONS).index(ForecastHorizon.DAYS_7.value),
    )
    horizon = HORIZON_OPTIONS[selected_label]

    if not workbooks:
        st.info("上传监测工作簿后，可生成多工作表分析报告。")
        return

    result = import_workbooks(workbooks, selected_sheets=_selected_sheets_for(workbooks))
    _render_candidate_sheets(result)
    _render_import_summary(result)
    _render_issue_tables(result.issues)

    if not result.records:
        st.warning("当前没有可用于生成报告的有效记录。")
        return

    report_bytes = build_analysis_report_from_import_result(result, horizon)
    st.download_button(
        "下载多工作表分析报告",
        data=report_bytes,
        file_name=f"irradiation_analysis_report_{datetime.now():%Y%m%d_%H%M%S}.xlsx",
        mime=EXCEL_MIME,
        type="primary",
    )
    st.caption(FORECAST_DISCLAIMER)


def _uploaded_workbooks(uploaded_files: list[Any]) -> list[UploadedWorkbook]:
    return [
        UploadedWorkbook(filename=file.name, content=file.getvalue())
        for file in uploaded_files
    ]


def _selected_sheets_for(workbooks: list[UploadedWorkbook]) -> dict[str, str]:
    selected_by_file = st.session_state.setdefault("report_selected_sheet_by_file", {})
    return {
        workbook.filename: selected_by_file[workbook.filename]
        for workbook in workbooks
        if selected_by_file.get(workbook.filename)
    }


def _render_candidate_sheets(result: ImportResult) -> None:
    rows = []
    selected_by_file = st.session_state.setdefault("report_selected_sheet_by_file", {})
    for filename, candidates in result.candidate_sheets.items():
        rows.append(
            {
                "文件": filename,
                "候选数量": len(candidates),
                "候选工作表": "、".join(candidates) if candidates else "未识别",
            }
        )
        if len(candidates) > 1:
            current = selected_by_file.get(filename)
            index = candidates.index(current) if current in candidates else 0
            selected_by_file[filename] = st.selectbox(
                f"{filename} 的报告工作表",
                options=list(candidates),
                index=index,
                key=f"report-sheet-select-{filename}",
            )
        elif len(candidates) == 1:
            selected_by_file[filename] = candidates[0]

    if rows:
        st.subheader("工作表识别")
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def _render_import_summary(result: ImportResult) -> None:
    st.subheader("数据摘要")
    summary = result.summary
    render_metrics(
        [
            ("文件数", summary.file_count, None),
            ("原始行", summary.raw_rows, None),
            ("有效记录", summary.valid_rows, None),
            ("阻断行", summary.blocked_rows, None),
        ]
    )
    render_metrics(
        [
            ("房间数", summary.room_count, None),
            ("设备数", summary.device_count, None),
            ("监测类型", len(summary.monitor_types), "已识别的监测类型数量"),
            ("冲突键", summary.conflict_keys, "同一监测键存在多版本记录的数量"),
        ]
    )


def _render_issue_tables(issues: list[QualityIssue]) -> None:
    st.subheader("质量问题")
    if not issues:
        st.success("未发现阻断或警告问题。")
        return

    rows = [
        {
            "级别": issue.level,
            "代码": issue.code,
            "信息": issue.message,
            "文件": issue.source_file,
            "工作表": issue.source_sheet,
            "行号": issue.source_row,
        }
        for issue in issues
    ]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def _render_template_downloads() -> None:
    st.header("模板下载")
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
    st.header("模拟数据")
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
