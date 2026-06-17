from __future__ import annotations

import json
from typing import Any

import pandas as pd
import streamlit as st

from irradiation_analysis.excel_io import ImportResult, UploadedWorkbook, import_workbooks
from irradiation_analysis.models import MonitoringRecord, QualityIssue
from irradiation_analysis.ui.styles import format_datetime, render_metrics


def render_import_page() -> None:
    st.header("一、数据导入")
    st.write("上传监测工作簿，选择候选工作表，并统一完成结构校验与记录清洗。")

    uploaded_files = st.file_uploader(
        "上传监测数据工作簿（.xlsx，可多选）",
        type=["xlsx"],
        accept_multiple_files=True,
        help="支持一次导入多个标准监测工作簿。",
    )
    workbooks = _uploaded_workbooks(uploaded_files or [])

    if workbooks:
        selected_sheets = _selected_sheets_for(workbooks)
        preview_result = import_workbooks(workbooks, selected_sheets=selected_sheets)
        _render_candidate_sheets(preview_result)

        if st.button("导入并校验", type="primary"):
            result = import_workbooks(workbooks, selected_sheets=_selected_sheets_for(workbooks))
            st.session_state.import_result = result
            st.session_state.selected_device_id = None
            st.session_state.selected_room_id = None
            st.success(f"导入完成：{result.summary.valid_rows} 条有效记录。")
    else:
        st.info("请上传一个或多个 `.xlsx` 监测数据工作簿。导入有效记录后，后续分析阶段将自动启用。")

    result = st.session_state.get("import_result")
    if result is None:
        st.warning("当前尚未导入有效记录；空间总览、趋势分析和智能研判会保持信息提示状态。")
        return

    _render_import_summary(result)
    _render_issue_tables(result.issues)
    _render_record_preview(result.records)


def _uploaded_workbooks(uploaded_files: list[Any]) -> list[UploadedWorkbook]:
    return [
        UploadedWorkbook(filename=file.name, content=file.getvalue())
        for file in uploaded_files
    ]


def _selected_sheets_for(workbooks: list[UploadedWorkbook]) -> dict[str, str]:
    selected_by_file = st.session_state.setdefault("selected_sheet_by_file", {})
    return {
        workbook.filename: selected_by_file[workbook.filename]
        for workbook in workbooks
        if selected_by_file.get(workbook.filename)
    }


def _render_candidate_sheets(result: ImportResult) -> None:
    st.subheader("候选工作表")
    rows = []
    selected_by_file = st.session_state.setdefault("selected_sheet_by_file", {})
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
                f"{filename} 的导入工作表",
                options=list(candidates),
                index=index,
                key=f"sheet-select-{filename}",
            )
        elif len(candidates) == 1:
            selected_by_file[filename] = candidates[0]

    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def _render_import_summary(result: ImportResult) -> None:
    st.subheader("导入摘要")
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
    st.subheader("数据质量问题")
    if not issues:
        st.success("未发现阻断或警告问题。")
        return

    issue_rows = [_issue_row(issue) for issue in issues]
    errors = [row for row in issue_rows if row["级别"] == "error"]
    warnings = [row for row in issue_rows if row["级别"] != "error"]
    if errors:
        st.markdown("**阻断问题**")
        st.dataframe(pd.DataFrame(errors), use_container_width=True, hide_index=True)
    if warnings:
        st.markdown("**提示问题**")
        st.dataframe(pd.DataFrame(warnings), use_container_width=True, hide_index=True)


def _render_record_preview(records: list[MonitoringRecord]) -> None:
    st.subheader("有效记录预览")
    if not records:
        st.info("本次导入尚未得到有效记录，请检查工作表选择和质量问题。")
        return
    st.dataframe(
        pd.DataFrame(_record_row(record) for record in records[:200]),
        use_container_width=True,
        hide_index=True,
    )


def _issue_row(issue: QualityIssue) -> dict[str, object]:
    return {
        "级别": issue.level,
        "代码": issue.code,
        "信息": issue.message,
        "文件": issue.source_file,
        "工作表": issue.source_sheet,
        "行号": issue.source_row,
        "详情": json.dumps(issue.details, ensure_ascii=False, default=str),
    }


def _record_row(record: MonitoringRecord) -> dict[str, object]:
    return {
        "监测时间": format_datetime(record.monitored_at),
        "房间": record.room_id,
        "设备": record.device_id,
        "类型": record.monitor_type,
        "数值": record.value,
        "单位": record.unit,
        "预警值": record.warning_threshold,
        "控制值": record.control_threshold,
        "来源文件": record.source_file,
        "工作表": record.source_sheet,
        "行号": record.source_row,
    }
