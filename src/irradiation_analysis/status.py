from collections.abc import Iterable

from irradiation_analysis.models import MonitoringRecord, MonitoringStatus


def classify_record(record: MonitoringRecord) -> MonitoringStatus:
    if record.value >= record.control_threshold:
        return MonitoringStatus.ACCIDENT
    if record.value >= record.warning_threshold:
        return MonitoringStatus.WARNING
    return MonitoringStatus.NORMAL


def worst_status(statuses: Iterable[MonitoringStatus]) -> MonitoringStatus:
    return max(
        statuses,
        key=lambda status: status.severity,
        default=MonitoringStatus.NO_DATA,
    )
