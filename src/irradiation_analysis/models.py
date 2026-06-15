from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


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
