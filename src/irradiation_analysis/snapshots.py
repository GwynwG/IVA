from collections.abc import Iterable
from datetime import datetime

from irradiation_analysis.models import (
    DeviceSnapshot,
    MonitoringRecord,
    MonitoringSnapshot,
    MonitoringStatus,
)
from irradiation_analysis.status import classify_record, worst_status


SeriesKey = tuple[str, str]


def all_room_ids() -> list[str]:
    return [f"R{i:02d}" for i in range(1, 21)]


def all_device_ids() -> list[str]:
    return [
        f"R{room:02d}-D{device:02d}"
        for room in range(1, 21)
        for device in range(1, 11)
    ]


def build_point_in_time_snapshot(
    records: Iterable[MonitoringRecord], selected_at: datetime
) -> MonitoringSnapshot:
    device_ids = set(all_device_ids())
    latest_by_device: dict[str, dict[SeriesKey, MonitoringRecord]] = {}

    for record in records:
        if record.device_id not in device_ids or record.monitored_at > selected_at:
            continue
        _set_latest_record(latest_by_device, record)

    return _build_snapshot_from_device_records(
        selected_at=selected_at,
        latest_by_device=latest_by_device,
        status_records_by_device={
            device_id: latest_by_series.values()
            for device_id, latest_by_series in latest_by_device.items()
        },
    )


def build_range_snapshot(
    records: Iterable[MonitoringRecord], start: datetime, end: datetime
) -> MonitoringSnapshot:
    device_ids = set(all_device_ids())
    latest_by_device: dict[str, dict[SeriesKey, MonitoringRecord]] = {}
    range_records_by_device: dict[str, list[MonitoringRecord]] = {}

    for record in records:
        if record.device_id not in device_ids or not start <= record.monitored_at <= end:
            continue
        _set_latest_record(latest_by_device, record)
        range_records_by_device.setdefault(record.device_id, []).append(record)

    return _build_snapshot_from_device_records(
        selected_at=end,
        latest_by_device=latest_by_device,
        status_records_by_device=range_records_by_device,
    )


def _build_snapshot_from_device_records(
    selected_at: datetime,
    latest_by_device: dict[str, dict[SeriesKey, MonitoringRecord]],
    status_records_by_device: dict[str, Iterable[MonitoringRecord]],
) -> MonitoringSnapshot:
    devices: dict[str, DeviceSnapshot] = {}

    for device_id in all_device_ids():
        room_id = device_id.split("-")[0]
        latest_by_series = dict(latest_by_device.get(device_id, {}))
        status_records = list(status_records_by_device.get(device_id, []))
        devices[device_id] = DeviceSnapshot(
            device_id=device_id,
            room_id=room_id,
            status=worst_status(classify_record(record) for record in status_records),
            latest_by_series=latest_by_series,
            most_severe_record=_most_severe_record(status_records),
        )

    return MonitoringSnapshot(
        selected_at=selected_at,
        devices=devices,
        room_statuses=_room_statuses(devices),
    )


def _set_latest_record(
    latest_by_device: dict[str, dict[SeriesKey, MonitoringRecord]],
    record: MonitoringRecord,
) -> None:
    latest_by_series = latest_by_device.setdefault(record.device_id, {})
    series_key = (record.monitor_type, record.unit)
    current = latest_by_series.get(series_key)
    if current is None or _record_order(record) > _record_order(current):
        latest_by_series[series_key] = record


def _most_severe_record(
    records: Iterable[MonitoringRecord],
) -> MonitoringRecord | None:
    return max(records, key=_severity_order, default=None)


def _room_statuses(
    devices: dict[str, DeviceSnapshot],
) -> dict[str, MonitoringStatus]:
    return {
        room_id: worst_status(
            device.status for device in devices.values() if device.room_id == room_id
        )
        for room_id in all_room_ids()
    }


def _severity_order(record: MonitoringRecord) -> tuple[int, datetime, int, str, str, int]:
    return (
        classify_record(record).severity,
        record.monitored_at,
        record.import_order,
        record.source_file,
        record.source_sheet,
        record.source_row,
    )


def _record_order(record: MonitoringRecord) -> tuple[datetime, int, str, str, int]:
    return (
        record.monitored_at,
        record.import_order,
        record.source_file,
        record.source_sheet,
        record.source_row,
    )
