# Irradiation Monitoring Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the legacy ground-point/glove-hole application with a modular Streamlit system that imports long-form Excel monitoring data for 20 rooms and 200 devices, visualizes the approved V5 layout, performs threshold analysis and simple forecasts, and exports Excel templates and multi-sheet analysis reports.

**Architecture:** Keep Streamlit and Plotly, but reduce `app.py` to an entry point. Put deterministic business logic in a `src/irradiation_analysis` package so Excel parsing, validation, status calculation, layout geometry, analytics, forecasting, generation, and reporting can be tested without Streamlit.

**Tech Stack:** Python 3.13, Streamlit, pandas, NumPy, openpyxl, Plotly, pytest

---

## File Structure

Create:

```text
pytest.ini
pyproject.toml
src/irradiation_analysis/__init__.py
src/irradiation_analysis/models.py
src/irradiation_analysis/validation.py
src/irradiation_analysis/status.py
src/irradiation_analysis/excel_io.py
src/irradiation_analysis/snapshots.py
src/irradiation_analysis/layout.py
src/irradiation_analysis/analytics.py
src/irradiation_analysis/forecast.py
src/irradiation_analysis/generator.py
src/irradiation_analysis/reporting.py
src/irradiation_analysis/ui/__init__.py
src/irradiation_analysis/ui/styles.py
src/irradiation_analysis/ui/import_page.py
src/irradiation_analysis/ui/overview_page.py
src/irradiation_analysis/ui/trends_page.py
src/irradiation_analysis/ui/intelligence_page.py
src/irradiation_analysis/ui/reports_page.py
tests/test_models_status.py
tests/test_excel_io.py
tests/test_snapshots.py
tests/test_layout.py
tests/test_analytics.py
tests/test_forecast.py
tests/test_generator.py
tests/test_reporting.py
tests/test_app_smoke.py
```

Modify:

```text
app.py
requirements.txt
README.md
USER_MANUAL_CN.md
.gitignore
```

Remove after replacement tests pass:

```text
tests/test_extract.py
tests/test_parse.py
污染普查数据生成器/
污染普查数据生成器_100个报告/
```

The legacy DOCX output files are not runtime dependencies. Remove them only in the final migration task, after the Excel generator and end-to-end tests pass.

---

### Task 1: Establish the Package and Test Baseline

**Files:**
- Create: `pytest.ini`
- Create: `pyproject.toml`
- Create: `src/irradiation_analysis/__init__.py`
- Create: `src/irradiation_analysis/models.py`
- Modify: `requirements.txt`
- Create: `tests/test_models_status.py`

- [ ] **Step 1: Write the failing package import test**

```python
# tests/test_models_status.py
from irradiation_analysis.models import MonitoringStatus


def test_monitoring_status_severity_order():
    assert MonitoringStatus.NO_DATA.severity < MonitoringStatus.NORMAL.severity
    assert MonitoringStatus.NORMAL.severity < MonitoringStatus.WARNING.severity
    assert MonitoringStatus.WARNING.severity < MonitoringStatus.ACCIDENT.severity
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run:

```powershell
python -m pytest tests/test_models_status.py -v
```

Expected: collection fails because `irradiation_analysis` does not exist.

- [ ] **Step 3: Add package discovery and runtime dependencies**

```ini
# pytest.ini
[pytest]
pythonpath = src
testpaths = tests
```

```toml
# pyproject.toml
[build-system]
requires = ["setuptools>=69"]
build-backend = "setuptools.build_meta"

[project]
name = "irradiation-analysis"
version = "0.1.0"
requires-python = ">=3.11"

[tool.setuptools.packages.find]
where = ["src"]
```

```text
# requirements.txt
-e .
streamlit==1.39.0
pandas==2.2.3
numpy==2.2.6
openpyxl==3.1.5
plotly==5.24.1
matplotlib==3.9.2
python-docx==1.1.2
pypdf==5.1.0
pillow==10.4.0
```

Keep the legacy app dependencies (`matplotlib`, `python-docx`, `pypdf`, and `pillow`) during the migration. Remove them only after the legacy UI and DOCX workflow are replaced in Tasks 10 and 11.

```python
# src/irradiation_analysis/__init__.py
"""Radiation monitoring visualization and analysis package."""
```

- [ ] **Step 4: Add the minimal status enum**

```python
# src/irradiation_analysis/models.py
from enum import Enum


class MonitoringStatus(str, Enum):
    NO_DATA = "无有效数据"
    NORMAL = "正常"
    WARNING = "预警"
    ACCIDENT = "事故级"

    @property
    def severity(self) -> int:
        return {
            MonitoringStatus.NO_DATA: -1,
            MonitoringStatus.NORMAL: 0,
            MonitoringStatus.WARNING: 1,
            MonitoringStatus.ACCIDENT: 2,
        }[self]
```

- [ ] **Step 5: Install the project and verify normal Python imports**

Run:

```powershell
python -m pip install -r requirements.txt
python -c "import irradiation_analysis; print(irradiation_analysis.__name__)"
```

Expected: the editable package installs and the import command prints `irradiation_analysis`.

- [ ] **Step 6: Run focused and full tests**

Run:

```powershell
python -m pytest tests/test_models_status.py -v
python -m pytest -q
```

Expected: the focused test passes and the full legacy-plus-package suite passes.

- [ ] **Step 7: Commit**

```powershell
git add pytest.ini pyproject.toml requirements.txt src/irradiation_analysis tests/test_models_status.py
git commit -m "chore: establish irradiation analysis package"
```

---

### Task 2: Implement IDs, Records, Validation, and Threshold Status

**Files:**
- Modify: `src/irradiation_analysis/models.py`
- Create: `src/irradiation_analysis/validation.py`
- Create: `src/irradiation_analysis/status.py`
- Modify: `tests/test_models_status.py`

- [ ] **Step 1: Add failing tests for IDs and exact threshold boundaries**

```python
from datetime import datetime

from irradiation_analysis.models import MonitoringRecord, MonitoringStatus
from irradiation_analysis.status import classify_record, worst_status
from irradiation_analysis.validation import validate_room_device_ids


def record(value: float, warning: float = 10.0, control: float = 20.0):
    return MonitoringRecord(
        monitored_at=datetime(2026, 6, 15),
        date_only=False,
        room_id="R01",
        device_id="R01-D01",
        monitor_type="γ剂量率",
        value=value,
        unit="μSv/h",
        warning_threshold=warning,
        control_threshold=control,
        source_file="sample.xlsx",
        source_sheet="监测数据",
        source_row=2,
        import_order=0,
    )


def test_validate_structured_ids():
    assert validate_room_device_ids("R01", "R01-D10") == []
    assert validate_room_device_ids("R21", "R21-D01")
    assert validate_room_device_ids("R01", "R02-D01")


def test_threshold_equality_enters_abnormal_state():
    assert classify_record(record(9.99)) is MonitoringStatus.NORMAL
    assert classify_record(record(10.0)) is MonitoringStatus.WARNING
    assert classify_record(record(20.0)) is MonitoringStatus.ACCIDENT


def test_worst_status_uses_most_severe_monitor_type():
    assert worst_status([MonitoringStatus.NORMAL, MonitoringStatus.ACCIDENT]) is MonitoringStatus.ACCIDENT
```

- [ ] **Step 2: Run tests and verify the new cases fail**

Run:

```powershell
python -m pytest tests/test_models_status.py -v
```

Expected: failures for missing record and validation functions.

- [ ] **Step 3: Define core immutable data models**

Implement in `models.py`:

```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class MonitoringRecord:
    monitored_at: datetime
    date_only: bool
    room_id: str
    device_id: str
    monitor_type: str
    value: float
    unit: str
    warning_threshold: float
    control_threshold: float
    source_file: str
    source_sheet: str
    source_row: int
    import_order: int
    room_name: str = ""
    device_name: str = ""
    data_source: str = ""
    note: str = ""

    @property
    def key(self) -> tuple[datetime, str, str, str]:
        return (self.monitored_at, self.room_id, self.device_id, self.monitor_type)


@dataclass(frozen=True)
class QualityIssue:
    level: str
    code: str
    message: str
    source_file: str
    source_sheet: str = ""
    source_row: int | None = None
    details: dict[str, Any] = field(default_factory=dict)
```

- [ ] **Step 4: Implement ID and numeric validation**

Implement in `validation.py`:

```python
import math
import re

ROOM_RE = re.compile(r"^R(0[1-9]|1[0-9]|20)$")
DEVICE_RE = re.compile(r"^(R(?:0[1-9]|1[0-9]|20))-D(0[1-9]|10)$")


def validate_room_device_ids(room_id: str, device_id: str) -> list[str]:
    errors: list[str] = []
    if not ROOM_RE.fullmatch(room_id):
        errors.append("房间ID必须为R01-R20")
    match = DEVICE_RE.fullmatch(device_id)
    if not match:
        errors.append("设备ID必须为R01-D01至R20-D10")
    elif match.group(1) != room_id:
        errors.append("设备ID所属房间与房间ID不一致")
    return errors


def is_finite_number(value: float) -> bool:
    return math.isfinite(value)
```

- [ ] **Step 5: Implement status calculation**

Implement in `status.py`:

```python
from collections.abc import Iterable

from .models import MonitoringRecord, MonitoringStatus


def classify_record(record: MonitoringRecord) -> MonitoringStatus:
    if record.value >= record.control_threshold:
        return MonitoringStatus.ACCIDENT
    if record.value >= record.warning_threshold:
        return MonitoringStatus.WARNING
    return MonitoringStatus.NORMAL


def worst_status(statuses: Iterable[MonitoringStatus]) -> MonitoringStatus:
    values = list(statuses)
    return max(values, key=lambda status: status.severity) if values else MonitoringStatus.NO_DATA
```

- [ ] **Step 6: Run the focused tests**

Run:

```powershell
python -m pytest tests/test_models_status.py -v
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```powershell
git add src/irradiation_analysis tests/test_models_status.py
git commit -m "feat: add monitoring models and threshold status"
```

---

### Task 3: Parse, Validate, Merge, and Audit Excel Workbooks

**Files:**
- Create: `src/irradiation_analysis/excel_io.py`
- Create: `tests/test_excel_io.py`

- [ ] **Step 1: Write failing workbook parsing tests**

Create in-memory `.xlsx` fixtures with openpyxl and test:

```python
from datetime import date, datetime
from io import BytesIO

from openpyxl import Workbook

from irradiation_analysis.excel_io import UploadedWorkbook, import_workbooks

HEADERS = ["监测时间", "房间ID", "设备ID", "监测类型", "监测值", "单位", "预警值", "控制标准"]


def workbook_bytes(rows: list[list[object]]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "监测数据"
    for row in rows:
        sheet.append(row)
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def test_import_long_form_excel_normalizes_date_and_datetime():
    result = import_workbooks([
        UploadedWorkbook("history.xlsx", workbook_bytes([
            HEADERS,
            [date(2026, 6, 1), "R01", "R01-D01", "γ剂量率", 5, "μSv/h", 10, 20],
            [datetime(2026, 6, 2, 8, 30), "R01", "R01-D01", "γ剂量率", 11, "μSv/h", 10, 20],
        ]))
    ])
    assert len(result.records) == 2
    assert result.records[0].date_only is True
    assert result.records[0].monitored_at.hour == 0
    assert result.records[1].date_only is False


def test_import_removes_exact_duplicates_and_audits_conflicts():
    content = workbook_bytes([
        HEADERS,
        [datetime(2026, 6, 2, 8, 30), "R01", "R01-D01", "γ剂量率", 10, "μSv/h", 10, 20],
        [datetime(2026, 6, 2, 8, 30), "R01", "R01-D01", "γ剂量率", 10, "μSv/h", 10, 20],
        [datetime(2026, 6, 2, 8, 30), "R01", "R01-D01", "γ剂量率", 12, "μSv/h", 10, 20],
    ])
    result = import_workbooks([UploadedWorkbook("conflicts.xlsx", content)])
    assert len(result.records) == 1
    assert result.records[0].value == 12
    assert result.summary.exact_duplicate_rows == 1
    assert result.summary.conflict_keys == 1
    assert any(issue.code == "conflicting_record" for issue in result.issues)


def test_invalid_threshold_relationship_blocks_row():
    content = workbook_bytes([
        HEADERS,
        [date(2026, 6, 1), "R01", "R01-D01", "γ剂量率", 5, "μSv/h", 20, 10],
    ])
    result = import_workbooks([UploadedWorkbook("invalid.xlsx", content)])
    assert result.records == []
    assert any(issue.code == "invalid_threshold_order" for issue in result.issues)
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
python -m pytest tests/test_excel_io.py -v
```

Expected: import errors because `excel_io` is missing.

- [ ] **Step 3: Implement workbook and result types**

Add:

```python
@dataclass(frozen=True)
class UploadedWorkbook:
    filename: str
    content: bytes


@dataclass(frozen=True)
class ImportSummary:
    file_count: int
    raw_rows: int
    valid_rows: int
    blocked_rows: int
    exact_duplicate_rows: int
    conflict_keys: int
    room_count: int
    device_count: int
    monitor_types: tuple[str, ...]


@dataclass(frozen=True)
class ImportResult:
    records: list[MonitoringRecord]
    issues: list[QualityIssue]
    summary: ImportSummary
    candidate_sheets: dict[str, tuple[str, ...]]
```

- [ ] **Step 4: Implement sheet detection and row normalization**

Use `openpyxl.load_workbook(io.BytesIO(content), data_only=True, read_only=True)`.

Required column constants:

```python
REQUIRED_COLUMNS = (
    "监测时间", "房间ID", "设备ID", "监测类型",
    "监测值", "单位", "预警值", "控制标准",
)
OPTIONAL_COLUMNS = ("房间名称", "设备名称", "数据来源", "备注")
```

Scan worksheets for a header row containing every required column. If multiple sheets qualify and no explicit selection is passed, return their names in `candidate_sheets` and do not silently choose one.

- [ ] **Step 5: Implement validation and merge policy**

For every row:

1. Parse date/datetime and set `date_only`.
2. Normalize IDs and text with `str(value).strip()`.
3. Convert numeric fields with `float`.
4. Reject non-finite numbers.
5. Reject invalid IDs and `warning_threshold > control_threshold`.
6. Group by record key.
7. Remove exact duplicates.
8. For conflicts, retain the highest `import_order` record and add a `conflicting_record` issue containing every source version.
9. Add warnings for threshold changes and unit changes across each device/type history.

- [ ] **Step 6: Run Excel tests**

Run:

```powershell
python -m pytest tests/test_excel_io.py -v
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```powershell
git add src/irradiation_analysis/excel_io.py tests/test_excel_io.py
git commit -m "feat: import and audit monitoring workbooks"
```

---

### Task 4: Build Time Snapshots and Status Aggregation

**Files:**
- Create: `src/irradiation_analysis/snapshots.py`
- Create: `tests/test_snapshots.py`

- [ ] **Step 1: Write failing snapshot tests**

```python
def test_snapshot_uses_latest_record_not_after_selected_time():
    snapshot = build_point_in_time_snapshot(records, datetime(2026, 6, 3))
    device = snapshot.devices["R01-D01"]
    assert device.latest_by_series[("γ剂量率", "μSv/h")].value == 11
    assert device.status is MonitoringStatus.WARNING


def test_snapshot_marks_devices_without_history_as_no_data():
    snapshot = build_point_in_time_snapshot([], datetime(2026, 6, 3))
    assert snapshot.devices["R20-D10"].status is MonitoringStatus.NO_DATA


def test_range_snapshot_uses_most_severe_status_in_range():
    snapshot = build_range_snapshot(records, start, end)
    assert snapshot.devices["R01-D01"].status is MonitoringStatus.ACCIDENT
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
python -m pytest tests/test_snapshots.py -v
```

- [ ] **Step 3: Add snapshot models**

Add to `models.py`:

```python
@dataclass(frozen=True)
class DeviceSnapshot:
    device_id: str
    room_id: str
    status: MonitoringStatus
    latest_by_series: dict[tuple[str, str], MonitoringRecord]
    most_severe_record: MonitoringRecord | None


@dataclass(frozen=True)
class MonitoringSnapshot:
    selected_at: datetime
    devices: dict[str, DeviceSnapshot]
    room_statuses: dict[str, MonitoringStatus]
```

- [ ] **Step 4: Implement deterministic snapshots**

Implement:

```python
def all_room_ids() -> list[str]:
    return [f"R{i:02d}" for i in range(1, 21)]


def all_device_ids() -> list[str]:
    return [f"R{room:02d}-D{device:02d}" for room in range(1, 21) for device in range(1, 11)]
```

`build_point_in_time_snapshot` groups by `(device_id, monitor_type, unit)`, selects the latest record at or before the selected time, then aggregates with `worst_status`.

`build_range_snapshot` uses the most severe record inside the inclusive range and exposes the latest record separately for detail views.

- [ ] **Step 5: Run snapshot and status tests**

Run:

```powershell
python -m pytest tests/test_models_status.py tests/test_snapshots.py -v
```

- [ ] **Step 6: Commit**

```powershell
git add src/irradiation_analysis/models.py src/irradiation_analysis/snapshots.py tests/test_snapshots.py
git commit -m "feat: build room and device status snapshots"
```

---

### Task 5: Implement the Approved V5 Facility Layout

**Files:**
- Create: `src/irradiation_analysis/layout.py`
- Create: `tests/test_layout.py`

- [ ] **Step 1: Write failing geometry tests**

```python
def test_facility_contains_twenty_rooms_and_two_aisles():
    layout = build_facility_layout()
    assert len(layout.rooms) == 20
    assert [aisle.label for aisle in layout.aisles] == ["主过道 A", "主过道 B"]


def test_each_room_has_ten_unique_devices():
    layout = build_facility_layout()
    ids = [device.device_id for room in layout.rooms for device in room.devices]
    assert len(ids) == len(set(ids)) == 200


def test_layout_a_is_six_plus_four_with_center_entrance_clearance():
    room = room_layout("R01")
    assert count_row(room, "far") == 6
    assert count_row(room, "entrance") == 4
    assert no_device_intersects(room.entrance_clearance)


def test_layout_b_is_four_four_plus_two_at_far_end():
    room = room_layout("R02")
    assert room.metadata == {"left": 4, "right": 4, "far_end": 2}
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
python -m pytest tests/test_layout.py -v
```

- [ ] **Step 3: Define layout data classes and normalized coordinates**

Use normalized facility coordinates so rendering size does not affect geometry:

```python
@dataclass(frozen=True)
class Rect:
    x0: float
    y0: float
    x1: float
    y1: float


@dataclass(frozen=True)
class DevicePlacement:
    device_id: str
    x: float
    y: float


@dataclass(frozen=True)
class RoomLayout:
    room_id: str
    layout_type: str
    bounds: Rect
    entrance_side: str
    devices: tuple[DevicePlacement, ...]
    paths: tuple[Rect, ...]
    metadata: dict[str, int]
```

- [ ] **Step 4: Encode room rows, aisles, entrances, and A/B/C device coordinates**

Map layout types:

```python
LAYOUT_BY_ROOM = {
    "R01": "A", "R02": "B", "R03": "C", "R04": "A", "R05": "B",
    "R06": "C", "R07": "A", "R08": "B", "R09": "C", "R10": "A",
    "R11": "B", "R12": "C", "R13": "A", "R14": "B", "R15": "C",
    "R16": "A", "R17": "B", "R18": "C", "R19": "A", "R20": "B",
}
```

Rows 1 and 3 use bottom entrances; rows 2 and 4 use top entrances.

- [ ] **Step 5: Add Plotly rendering**

Implement:

```python
import plotly.graph_objects as go


STATUS_COLORS = {
    MonitoringStatus.NO_DATA: "#94a3b8",
    MonitoringStatus.NORMAL: "#22c55e",
    MonitoringStatus.WARNING: "#f59e0b",
    MonitoringStatus.ACCIDENT: "#dc2626",
}


def build_facility_figure(
    snapshot: MonitoringSnapshot,
    selected_device_id: str | None = None,
) -> go.Figure:
    layout = build_facility_layout()
    figure = go.Figure()
    for aisle in layout.aisles:
        figure.add_shape(
            type="rect",
            x0=aisle.bounds.x0,
            y0=aisle.bounds.y0,
            x1=aisle.bounds.x1,
            y1=aisle.bounds.y1,
            fillcolor="#e2e8f0",
            line={"color": "#94a3b8"},
            layer="below",
        )
        figure.add_annotation(
            x=(aisle.bounds.x0 + aisle.bounds.x1) / 2,
            y=(aisle.bounds.y0 + aisle.bounds.y1) / 2,
            text=aisle.label,
            showarrow=False,
        )
    for room in layout.rooms:
        figure.add_shape(
            type="rect",
            x0=room.bounds.x0,
            y0=room.bounds.y0,
            x1=room.bounds.x1,
            y1=room.bounds.y1,
            fillcolor="#f8fafc",
            line={"color": "#334155", "width": 2},
            layer="below",
        )
        for path in room.paths:
            figure.add_shape(
                type="rect",
                x0=path.x0,
                y0=path.y0,
                x1=path.x1,
                y1=path.y1,
                fillcolor="#fff7ed",
                line={"color": "#f59e0b", "dash": "dot"},
                layer="below",
            )
        for placement in room.devices:
            device = snapshot.devices[placement.device_id]
            selected = placement.device_id == selected_device_id
            figure.add_trace(
                go.Scatter(
                    x=[placement.x],
                    y=[placement.y],
                    mode="markers+text",
                    text=[placement.device_id.split("-")[1]],
                    textposition="middle center",
                    customdata=[[placement.device_id, room.room_id, device.status.value]],
                    hovertemplate="%{customdata[0]}<br>%{customdata[2]}<extra></extra>",
                    marker={
                        "size": 23,
                        "color": STATUS_COLORS[device.status],
                        "line": {"color": "#0f172a" if selected else "#ffffff", "width": 3 if selected else 1},
                    },
                    showlegend=False,
                )
            )
    figure.update_layout(
        height=850,
        margin={"l": 10, "r": 10, "t": 40, "b": 10},
        xaxis={"visible": False, "fixedrange": True},
        yaxis={"visible": False, "fixedrange": True, "scaleanchor": "x"},
        clickmode="event+select",
    )
    return figure
```

Use room rectangles, path shapes, entrance labels, device markers, and hover text. Preserve status color when selected by using a thicker dark outline.

- [ ] **Step 6: Run layout tests**

Run:

```powershell
python -m pytest tests/test_layout.py -v
```

- [ ] **Step 7: Commit**

```powershell
git add src/irradiation_analysis/layout.py tests/test_layout.py
git commit -m "feat: add approved room and device layout"
```

---

### Task 6: Implement Events, Near-Threshold Detection, Growth, and Risk Ranking

**Files:**
- Create: `src/irradiation_analysis/analytics.py`
- Create: `tests/test_analytics.py`

- [ ] **Step 1: Write failing analytics tests**

```python
def test_contiguous_abnormal_records_form_one_event():
    events = build_abnormal_events(records)
    assert len(events) == 1
    assert events[0].highest_status is MonitoringStatus.ACCIDENT
    assert events[0].peak_value == 22


def test_normal_record_ends_an_event():
    events = build_abnormal_events(records_with_recovery)
    assert events[0].ended_at == datetime(2026, 6, 3)


def test_near_threshold_uses_eighty_percent_default():
    candidates = find_near_threshold(records)
    assert candidates[0].device_id == "R01-D01"


def test_risk_score_is_explainable_and_bounded():
    result = rank_device_risks(records)
    assert 0 <= result[0].score <= 100
    assert result[0].reasons
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
python -m pytest tests/test_analytics.py -v
```

- [ ] **Step 3: Add analytics result models**

Add `AbnormalEvent`, `GrowthSignal`, `RiskResult`, and `RoomRiskResult` dataclasses to `models.py`. Every result must include IDs, monitor type where relevant, numeric evidence, and human-readable reasons.

- [ ] **Step 4: Implement event grouping**

Group by `(device_id, monitor_type, unit)`, sort by `monitored_at`, begin an event on warning/accident, keep it open while records remain abnormal, and close it on the first normal record. Preserve highest status, peak value, and peak time.

- [ ] **Step 5: Implement growth and near-threshold rules**

Use:

```python
NEAR_WARNING_RATIO = 0.80
MIN_GROWTH_POINTS = 3
```

Calculate slopes using elapsed days. Mark rapid growth only when the recent slope is positive and the recent change exceeds the historical median absolute step by a documented multiplier.

- [ ] **Step 6: Implement risk scoring**

Use the approved weights:

```python
RISK_WEIGHTS = {
    "severity": 0.40,
    "exceedance": 0.25,
    "duration": 0.15,
    "trend": 0.10,
    "recurrence": 0.10,
}
```

Normalize each component to 0..100, return total score and top contributing reasons. Aggregate room risk from maximum device risk, abnormal-device ratio, and duration.

- [ ] **Step 7: Run analytics tests**

Run:

```powershell
python -m pytest tests/test_analytics.py -v
```

- [ ] **Step 8: Commit**

```powershell
git add src/irradiation_analysis/models.py src/irradiation_analysis/analytics.py tests/test_analytics.py
git commit -m "feat: add monitoring risk analytics"
```

---

### Task 7: Implement Explainable Simple Forecasts

**Files:**
- Create: `src/irradiation_analysis/forecast.py`
- Create: `tests/test_forecast.py`

- [ ] **Step 1: Write failing forecast tests**

```python
def test_less_than_three_points_uses_last_value():
    result = forecast_series(two_records, horizon=ForecastHorizon.NEXT_RECORD)
    assert result.method == "最近值"
    assert result.confidence == "低"


def test_irregular_sampling_uses_elapsed_time():
    result = forecast_series(irregular_records, horizon=ForecastHorizon.DAYS_7)
    assert result.predicted_at == datetime(2026, 6, 17)
    assert result.method in {"线性趋势", "指数平滑", "移动平均"}


def test_forecast_status_uses_latest_thresholds():
    result = forecast_series(records_with_changed_threshold, ForecastHorizon.DAYS_1)
    assert result.warning_threshold == records_with_changed_threshold[-1].warning_threshold


def test_system_forecast_counts_worst_device_status():
    result = forecast_system(records, ForecastHorizon.DAYS_7)
    assert result.warning_devices + result.accident_devices + result.normal_devices + result.no_data_devices == 200
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
python -m pytest tests/test_forecast.py -v
```

- [ ] **Step 3: Add forecast enums and result models**

Define:

```python
class ForecastHorizon(str, Enum):
    NEXT_RECORD = "下一条记录"
    DAYS_1 = "未来1天"
    DAYS_7 = "未来7天"
    DAYS_30 = "未来30天"
```

`SeriesForecast` includes predicted value/time, predicted status, thresholds, method, sample count, training range, confidence, and explanation.

- [ ] **Step 4: Implement candidate methods**

Implement pure functions for:

- Last value.
- Simple moving average.
- Linear regression over elapsed days using NumPy.
- Simple exponential smoothing without adding a new dependency.

For 3+ records, evaluate candidates using chronological holdout and mean absolute error. Do not select a method that produces non-finite output.

- [ ] **Step 5: Implement system aggregation**

Forecast every `(device, monitor_type, unit)` series, classify against latest thresholds, aggregate the worst predicted status per device, and count normal/warning/accident/no-data across all 200 devices.

- [ ] **Step 6: Run forecast tests**

Run:

```powershell
python -m pytest tests/test_forecast.py -v
```

- [ ] **Step 7: Commit**

```powershell
git add src/irradiation_analysis/models.py src/irradiation_analysis/forecast.py tests/test_forecast.py
git commit -m "feat: add explainable monitoring forecasts"
```

---

### Task 8: Build Excel Templates and Reproducible Simulated Data

**Files:**
- Create: `src/irradiation_analysis/generator.py`
- Create: `tests/test_generator.py`

- [ ] **Step 1: Write failing generator tests**

```python
def test_blank_template_has_required_headers_and_frozen_pane():
    content = build_blank_template()
    workbook = load_workbook(BytesIO(content))
    sheet = workbook["监测数据"]
    assert [cell.value for cell in sheet[1]][:8] == list(REQUIRED_COLUMNS)
    assert sheet.freeze_panes == "A2"


def test_prefilled_template_contains_two_hundred_devices_per_monitor_type():
    content = build_prefilled_template(config)
    rows = read_rows(content)
    assert len(rows) == 400


def test_simulation_is_reproducible_and_importable():
    first = generate_simulated_workbooks(config_with_seed_42)
    second = generate_simulated_workbooks(config_with_seed_42)
    assert first == second
    assert import_workbooks(first).summary.blocked_rows == 0
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
python -m pytest tests/test_generator.py -v
```

- [ ] **Step 3: Implement template generation**

Create workbooks with:

- `监测数据` sheet.
- Required and optional columns.
- Frozen header, auto-filter, status-neutral header style, date/number formats, and sensible widths.
- Blank mode and 200-device prefilled mode.
- One row per selected monitor type and device.

- [ ] **Step 4: Implement simulation configuration**

Define `SimulationConfig` with start/end, sampling frequency, monitor types, output mode, warning/accident ratios, rapid-growth ratio, event duration, and random seed.

- [ ] **Step 5: Generate valid normal, warning, accident, and rapid-growth series**

Use a seeded NumPy generator. Keep generated thresholds internally consistent and ensure every output conforms to the importer schema. Return either one `UploadedWorkbook` or a list split by natural day.

- [ ] **Step 6: Run generator and importer tests**

Run:

```powershell
python -m pytest tests/test_generator.py tests/test_excel_io.py -v
```

- [ ] **Step 7: Commit**

```powershell
git add src/irradiation_analysis/generator.py tests/test_generator.py
git commit -m "feat: generate monitoring Excel templates and samples"
```

---

### Task 9: Export the Multi-Sheet Analysis Workbook

**Files:**
- Create: `src/irradiation_analysis/reporting.py`
- Create: `tests/test_reporting.py`

- [ ] **Step 1: Write the failing report structure test**

```python
def test_analysis_report_contains_all_required_sheets():
    content = build_analysis_report(report_input)
    workbook = load_workbook(BytesIO(content), data_only=True)
    assert workbook.sheetnames == [
        "分析摘要",
        "异常事件",
        "设备风险排名",
        "房间风险排名",
        "趋势预测",
        "清洗后的监测数据",
        "数据质量问题",
    ]


def test_report_formats_status_and_freezes_headers():
    workbook = load_workbook(BytesIO(build_analysis_report(report_input)))
    assert workbook["异常事件"].freeze_panes == "A2"
    assert workbook["清洗后的监测数据"].auto_filter.ref
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
python -m pytest tests/test_reporting.py -v
```

- [ ] **Step 3: Define a single report input contract**

Create `AnalysisReportInput` containing the import result, snapshot, events, device risks, room risks, series forecasts, and system forecasts. The reporting layer must not recompute analytics.

- [ ] **Step 4: Implement workbook sheets and formatting**

Use openpyxl. Add:

- Consistent Chinese headers.
- Freeze panes and filters.
- Date/datetime and numeric formats.
- Status fills matching the UI.
- Source file/sheet/row columns in cleaned data and quality sheets.
- Forecast method, sample count, confidence, and disclaimer.

- [ ] **Step 5: Run reporting tests**

Run:

```powershell
python -m pytest tests/test_reporting.py -v
```

- [ ] **Step 6: Commit**

```powershell
git add src/irradiation_analysis/reporting.py tests/test_reporting.py
git commit -m "feat: export multi-sheet monitoring analysis reports"
```

---

### Task 10: Replace the Streamlit Application with the Five-Stage Workbench

**Files:**
- Replace: `app.py`
- Create: `src/irradiation_analysis/ui/styles.py`
- Create: `src/irradiation_analysis/ui/import_page.py`
- Create: `src/irradiation_analysis/ui/overview_page.py`
- Create: `src/irradiation_analysis/ui/trends_page.py`
- Create: `src/irradiation_analysis/ui/intelligence_page.py`
- Create: `src/irradiation_analysis/ui/reports_page.py`
- Create: `tests/test_app_smoke.py`

- [ ] **Step 1: Write a failing Streamlit smoke test**

```python
from streamlit.testing.v1 import AppTest


def test_app_renders_new_title_and_excel_uploader():
    app = AppTest.from_file("app.py").run(timeout=30)
    assert not app.exception
    assert any("辐照监测可视化与智能化分析系统" in title.value for title in app.title)
    assert len(app.file_uploader) == 1
    assert app.file_uploader[0].type == ["xlsx"]
```

- [ ] **Step 2: Run the smoke test and verify it fails against the legacy app**

Run:

```powershell
python -m pytest tests/test_app_smoke.py -v
```

Expected: title and uploader assertions fail.

- [ ] **Step 3: Replace `app.py` with an entry point**

```python
from irradiation_analysis.ui import run_app


if __name__ == "__main__":
    run_app()
```

Expose `run_app` from `ui/__init__.py`.

- [ ] **Step 4: Implement shared session state and styles**

State keys:

```python
DEFAULT_STATE = {
    "import_result": None,
    "selected_sheet_by_file": {},
    "selected_device_id": None,
    "selected_room_id": None,
    "snapshot_mode": "时间点",
}
```

Use the existing blue visual language, but remove all pollution, glove-hole, obstacle, and grid terminology.

- [ ] **Step 5: Implement the data import page**

Include:

- Multi-file `.xlsx` uploader.
- Candidate-sheet selection.
- Import button.
- Summary cards and issue tables.
- Valid-record preview.
- Disabled analysis navigation until valid records exist.

- [ ] **Step 6: Implement the spatial overview page**

Include:

- Time-point/range controls.
- Room/device/type/status filters.
- Status metric cards.
- `build_facility_figure`.
- Click selection using Streamlit Plotly selection events supported by the pinned Streamlit version.
- Device detail with latest values, thresholds, record age, trend, events, and forecasts.

- [ ] **Step 7: Implement trends and intelligence pages**

Trends page:

- Device/type/unit selector.
- Value line plus changing warning/control threshold lines.
- Room abnormal-count trend.
- Event table.

Intelligence page:

- Device and room risk rankings.
- Rapid-growth and near-warning lists.
- Forecast horizon selector.
- Device and system forecast tables with disclaimer.

- [ ] **Step 8: Implement reports and generator page**

Include:

- Multi-sheet analysis report download.
- Blank template download.
- Prefilled template controls and download.
- Simulation controls and download as one workbook or ZIP of daily workbooks.

- [ ] **Step 9: Run smoke and core tests**

Run:

```powershell
python -m pytest tests/test_app_smoke.py tests/test_layout.py tests/test_excel_io.py -v
```

Expected: all pass.

- [ ] **Step 10: Commit**

```powershell
git add app.py src/irradiation_analysis/ui tests/test_app_smoke.py
git commit -m "feat: replace legacy UI with monitoring workbench"
```

---

### Task 11: Migrate Documentation and Remove Legacy Runtime Assets

**Files:**
- Modify: `README.md`
- Modify: `USER_MANUAL_CN.md`
- Modify: `.gitignore`
- Modify: `requirements.txt`
- Remove: `tests/test_extract.py`
- Remove: `tests/test_parse.py`
- Remove: `污染普查数据生成器/`
- Remove: `污染普查数据生成器_100个报告/`

- [ ] **Step 1: Update README with exact run and data instructions**

Document:

```powershell
python -m pip install -r requirements.txt
streamlit run app.py
python -m pytest -q
```

Include required Excel columns, ID examples, threshold boundaries, supported upload modes, and export contents.

- [ ] **Step 2: Rewrite the Chinese user manual**

Cover the five-stage workbench, V5 facility layout, import quality handling, filters, device details, forecast disclaimer, template generator, and report download.

- [ ] **Step 3: Ignore generated and local-only artifacts**

Add:

```gitignore
__pycache__/
*.py[cod]
.pytest_cache/
.codegraph/
.superpowers/
generated/
*.xlsx
*.zip
```

Do not ignore committed test fixtures if any are later added under `tests/fixtures`.

- [ ] **Step 4: Remove legacy tests and DOCX generators**

Use native PowerShell after verifying every resolved target is under the workspace:

```powershell
Remove-Item -LiteralPath '.\tests\test_extract.py' -Force
Remove-Item -LiteralPath '.\tests\test_parse.py' -Force
Remove-Item -LiteralPath '.\污染普查数据生成器' -Recurse -Force
Remove-Item -LiteralPath '.\污染普查数据生成器_100个报告' -Recurse -Force
```

- [ ] **Step 5: Remove migration-only dependencies**

After Task 10 has replaced the legacy app and the legacy tests and DOCX generators above are removed, reduce `requirements.txt` to the new system dependencies:

```text
-e .
streamlit==1.39.0
pandas==2.2.3
numpy==2.2.6
openpyxl==3.1.5
plotly==5.24.1
```

This final requirements cleanup removes `matplotlib`, `python-docx`, `pypdf`, and `pillow`.

- [ ] **Step 6: Run the full test suite**

Run:

```powershell
python -m pytest -q
```

Expected: all new tests pass and no legacy imports remain.

- [ ] **Step 7: Commit**

```powershell
git add README.md USER_MANUAL_CN.md .gitignore requirements.txt tests
git add -u
git commit -m "docs: complete Excel monitoring migration"
```

---

### Task 12: End-to-End Verification and Release Readiness

**Files:**
- Modify only if verification exposes defects.

- [ ] **Step 1: Generate a reproducible mixed-risk dataset**

Run a small Python command using `SimulationConfig` with:

- 30 days.
- Daily sampling.
- Two monitor types.
- Normal, warning, accident, and rapid-growth cases.
- Seed `42`.

Write outputs under ignored `generated/`.

- [ ] **Step 2: Verify single-workbook and daily-workbook equivalence**

Import the single workbook and the daily split. Assert:

```python
assert single.records == daily.records
assert single.summary.valid_rows == daily.summary.valid_rows
```

- [ ] **Step 3: Run the full automated suite**

Run:

```powershell
python -m pytest -q
```

Expected: zero failures.

- [ ] **Step 4: Launch Streamlit and perform an HTTP smoke check**

Run the server hidden:

```powershell
Start-Process -FilePath python -ArgumentList @(
  '-m', 'streamlit', 'run', 'app.py',
  '--server.headless=true',
  '--server.port=8501'
) -WindowStyle Hidden
```

Then:

```powershell
Invoke-WebRequest 'http://localhost:8501/_stcore/health' -UseBasicParsing
```

Expected: HTTP 200 and body `ok`.

- [ ] **Step 5: Perform browser verification**

Use the generated dataset to verify:

- 20 rooms and 200 unique devices render.
- A/B/C layouts match V5.
- Entrances face the nearest aisle.
- Device/path/label geometry does not overlap at desktop width.
- Status colors match source records.
- Time, room, device, monitor type, and status filters work.
- Device detail matches its source row.
- Forecast method and disclaimer are visible.
- Template, simulation, and analysis report downloads succeed.

- [ ] **Step 6: Open generated Excel artifacts**

Load every generated `.xlsx` with openpyxl and assert required sheets, headers, freeze panes, filters, and non-empty records.

- [ ] **Step 7: Check repository hygiene**

Run:

```powershell
git status --short
git diff --check
```

Expected: only intended implementation changes before the final commit.

- [ ] **Step 8: Commit verification fixes**

```powershell
git add app.py src tests README.md USER_MANUAL_CN.md requirements.txt pytest.ini .gitignore
git commit -m "test: verify monitoring analysis workflow"
```

---

## Plan Self-Review

### Spec Coverage

- 20 rooms, 200 devices, structured IDs: Tasks 2, 4, 5.
- Approved V5 A/B/C layout and entrances: Task 5.
- Long-form Excel, single and multi-file input: Task 3.
- Date and datetime precision: Task 3.
- Exact warning/control boundaries: Task 2.
- Most-severe device and room status: Tasks 2 and 4.
- Duplicate/conflict audit: Task 3.
- Unit and threshold changes: Tasks 3, 6, 7.
- Five-stage Streamlit workbench: Task 10.
- Trends, events, growth, near-threshold, rankings: Task 6 and Task 10.
- Device and system forecasts for next/1/7/30 days: Task 7.
- Blank/prefilled templates and simulation: Task 8.
- Multi-sheet analysis report: Task 9.
- Legacy DOCX migration: Task 11.
- Automated and end-to-end verification: Task 12.

### Placeholder Scan

The plan contains no placeholder markers, deferred implementation notes, or unspecified error-handling steps.

### Type Consistency

The shared contracts are `MonitoringRecord`, `QualityIssue`, `ImportResult`, `MonitoringSnapshot`, analytics result dataclasses, forecast result dataclasses, and `AnalysisReportInput`. Later tasks consume these contracts rather than recomputing or redefining them.
