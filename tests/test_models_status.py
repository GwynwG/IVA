from datetime import datetime

from irradiation_analysis.models import MonitoringRecord, MonitoringStatus
from irradiation_analysis.status import classify_record, worst_status
from irradiation_analysis.validation import is_finite_number, validate_room_device_ids


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


def test_monitoring_status_severity_order():
    assert MonitoringStatus.NO_DATA.severity < MonitoringStatus.NORMAL.severity
    assert MonitoringStatus.NORMAL.severity < MonitoringStatus.WARNING.severity
    assert MonitoringStatus.WARNING.severity < MonitoringStatus.ACCIDENT.severity


def test_monitoring_record_key():
    monitoring_record = record(1.0)

    assert monitoring_record.key == (
        datetime(2026, 6, 15),
        "R01",
        "R01-D01",
        "γ剂量率",
    )


def test_validate_structured_ids():
    assert validate_room_device_ids("R01", "R01-D10") == []
    assert validate_room_device_ids("R21", "R21-D01")
    assert validate_room_device_ids("R01", "R02-D01")


def test_validate_device_number_upper_bound():
    assert validate_room_device_ids("R01", "R01-D11")


def test_is_finite_number_rejects_nan_and_infinity():
    assert is_finite_number(1.0)
    assert not is_finite_number(float("nan"))
    assert not is_finite_number(float("inf"))
    assert not is_finite_number(float("-inf"))


def test_threshold_equality_enters_abnormal_state():
    assert classify_record(record(9.99)) is MonitoringStatus.NORMAL
    assert classify_record(record(10.0)) is MonitoringStatus.WARNING
    assert classify_record(record(20.0)) is MonitoringStatus.ACCIDENT


def test_worst_status_uses_most_severe_monitor_type():
    assert worst_status(
        [MonitoringStatus.NORMAL, MonitoringStatus.ACCIDENT]
    ) is MonitoringStatus.ACCIDENT


def test_worst_status_returns_no_data_for_empty_input():
    assert worst_status([]) is MonitoringStatus.NO_DATA
