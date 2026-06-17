from datetime import datetime

from irradiation_analysis.models import MonitoringRecord, MonitoringStatus
from irradiation_analysis.snapshots import (
    all_device_ids,
    all_room_ids,
    build_point_in_time_snapshot,
    build_range_snapshot,
)


GAMMA_DOSE_RATE = "\u03b3\u5242\u91cf\u7387"
DOSE_UNIT = "\u03bcSv/h"


def record(
    device_id: str,
    monitored_at: datetime,
    value: float,
    monitor_type: str = GAMMA_DOSE_RATE,
    unit: str = DOSE_UNIT,
    import_order: int = 0,
) -> MonitoringRecord:
    return MonitoringRecord(
        monitored_at=monitored_at,
        date_only=False,
        room_id=device_id.split("-")[0],
        device_id=device_id,
        monitor_type=monitor_type,
        value=value,
        unit=unit,
        warning_threshold=10.0,
        control_threshold=20.0,
        source_file="sample.xlsx",
        source_sheet="monitoring",
        source_row=import_order + 2,
        import_order=import_order,
    )


def test_snapshot_uses_latest_record_not_after_selected_time():
    records = [
        record("R01-D01", datetime(2026, 6, 1), 8.0, import_order=1),
        record("R01-D01", datetime(2026, 6, 2), 11.0, import_order=2),
        record("R01-D01", datetime(2026, 6, 4), 30.0, import_order=3),
    ]

    snapshot = build_point_in_time_snapshot(records, datetime(2026, 6, 3))

    device = snapshot.devices["R01-D01"]
    assert device.latest_by_series[(GAMMA_DOSE_RATE, DOSE_UNIT)].value == 11.0
    assert device.status is MonitoringStatus.WARNING


def test_snapshot_marks_devices_without_history_as_no_data():
    snapshot = build_point_in_time_snapshot([], datetime(2026, 6, 3))

    assert all_room_ids() == [f"R{i:02d}" for i in range(1, 21)]
    assert len(snapshot.room_statuses) == 20
    assert snapshot.room_statuses["R20"] is MonitoringStatus.NO_DATA
    assert all_device_ids() == [
        f"R{room:02d}-D{device:02d}"
        for room in range(1, 21)
        for device in range(1, 11)
    ]
    assert len(snapshot.devices) == 200
    assert snapshot.devices["R20-D10"].status is MonitoringStatus.NO_DATA
    assert snapshot.devices["R20-D10"].latest_by_series == {}
    assert snapshot.devices["R20-D10"].most_severe_record is None


def test_range_snapshot_uses_most_severe_status_in_range():
    start = datetime(2026, 6, 1)
    end = datetime(2026, 6, 3, 23, 59, 59)
    records = [
        record("R01-D01", datetime(2026, 5, 31), 50.0, import_order=1),
        record("R01-D01", datetime(2026, 6, 1), 11.0, import_order=2),
        record("R01-D01", datetime(2026, 6, 2), 30.0, import_order=3),
        record("R01-D01", datetime(2026, 6, 3), 8.0, import_order=4),
        record("R01-D01", datetime(2026, 6, 4), 50.0, import_order=5),
    ]

    snapshot = build_range_snapshot(records, start, end)

    device = snapshot.devices["R01-D01"]
    assert device.status is MonitoringStatus.ACCIDENT
    assert device.latest_by_series[(GAMMA_DOSE_RATE, DOSE_UNIT)].value == 8.0
    assert device.most_severe_record is not None
    assert device.most_severe_record.value == 30.0
    assert snapshot.room_statuses["R01"] is MonitoringStatus.ACCIDENT
