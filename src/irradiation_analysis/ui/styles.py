from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from datetime import datetime

import streamlit as st

from irradiation_analysis.models import MonitoringStatus


APP_TITLE = "辐照监测可视化与智能化分析系统"
STAGE_LABELS = ("数据导入", "空间总览", "趋势分析", "智能研判", "报告生成")
EXCEL_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
FORECAST_DISCLAIMER = (
    "预测结果仅供趋势研判参考，不替代现场复核、仪器校准或安全处置决策。"
)

STATUS_TEXT = {
    MonitoringStatus.NO_DATA: "无数据",
    MonitoringStatus.NORMAL: "正常",
    MonitoringStatus.WARNING: "预警",
    MonitoringStatus.ACCIDENT: "事故级",
}


def inject_styles() -> None:
    st.markdown(
        """
        <style>
        .main .block-container {
            padding-top: 2rem;
            padding-bottom: 3rem;
        }
        .stage-rail {
            display: flex;
            flex-wrap: wrap;
            gap: 0.75rem;
            margin: 0.75rem 0 1.25rem;
        }
        .stage-card {
            flex: 1 1 10rem;
            border: 1px solid #bfdbfe;
            border-radius: 1rem;
            background: linear-gradient(135deg, #eff6ff 0%, #ffffff 100%);
            padding: 0.85rem 1rem;
            color: #0f172a;
            box-shadow: 0 10px 24px rgba(37, 99, 235, 0.08);
        }
        .stage-card strong {
            color: #1d4ed8;
        }
        .soft-panel {
            border: 1px solid #dbeafe;
            border-radius: 1rem;
            background: #f8fbff;
            padding: 1rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_stage_rail() -> None:
    cards = "\n".join(
        f"<div class='stage-card'><strong>{index}</strong><br>{label}</div>"
        for index, label in enumerate(STAGE_LABELS, start=1)
    )
    st.markdown(f"<div class='stage-rail'>{cards}</div>", unsafe_allow_html=True)


def status_label(status: MonitoringStatus) -> str:
    return STATUS_TEXT.get(status, str(status))


def status_counts(statuses: Iterable[MonitoringStatus]) -> Counter[MonitoringStatus]:
    counts: Counter[MonitoringStatus] = Counter(statuses)
    for status in MonitoringStatus:
        counts.setdefault(status, 0)
    return counts


def format_datetime(value: datetime | None) -> str:
    if value is None:
        return ""
    return value.strftime("%Y-%m-%d %H:%M")


def format_number(value: float | int | None) -> str:
    if value is None:
        return ""
    return f"{float(value):.3f}"


def render_metrics(items: list[tuple[str, object, str | None]]) -> None:
    columns = st.columns(len(items))
    for column, (label, value, help_text) in zip(columns, items, strict=True):
        column.metric(label, value, help=help_text)
