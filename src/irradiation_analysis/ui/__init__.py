from __future__ import annotations

from copy import deepcopy

import streamlit as st

from irradiation_analysis.ui.import_page import render_import_page
from irradiation_analysis.ui.intelligence_page import render_intelligence_page
from irradiation_analysis.ui.overview_page import render_overview_page
from irradiation_analysis.ui.reports_page import render_reports_page
from irradiation_analysis.ui.styles import APP_TITLE, STAGE_LABELS, inject_styles, render_stage_rail
from irradiation_analysis.ui.trends_page import render_trends_page


DEFAULT_STATE = {
    "import_result": None,
    "selected_sheet_by_file": {},
    "selected_device_id": None,
    "selected_room_id": None,
    "snapshot_mode": "时间点",
}


def run_app() -> None:
    st.set_page_config(page_title=APP_TITLE, layout="wide")
    _ensure_session_state()
    inject_styles()

    st.title(APP_TITLE)
    st.caption("面向辐照监测数据接入、空间态势、趋势研判、智能预测与报告生成的一体化工作台。")
    render_stage_rail()

    tabs = st.tabs(list(STAGE_LABELS))
    with tabs[0]:
        render_import_page()
    with tabs[1]:
        render_overview_page()
    with tabs[2]:
        render_trends_page()
    with tabs[3]:
        render_intelligence_page()
    with tabs[4]:
        render_reports_page()


def _ensure_session_state() -> None:
    for key, value in DEFAULT_STATE.items():
        if key not in st.session_state:
            st.session_state[key] = deepcopy(value)
