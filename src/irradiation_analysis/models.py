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


class ForecastHorizon(str, Enum):
    NEXT_RECORD = "下一条记录"
    DAYS_1 = "未来1天"
    DAYS_7 = "未来7天"
    DAYS_30 = "未来30天"


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
class SeriesForecast:
    room_id: str
    device_id: str
    monitor_type: str
    unit: str
    horizon: ForecastHorizon
    predicted_at: datetime
    predicted_value: float
    predicted_status: MonitoringStatus
    warning_threshold: float
    control_threshold: float
    method: str
    sample_count: int
    training_start: datetime
    training_end: datetime
    confidence: str
    explanation: str


@dataclass(frozen=True)
class SystemForecast:
    horizon: ForecastHorizon
    series_forecasts: tuple[SeriesForecast, ...]
    device_statuses: dict[str, MonitoringStatus]
    normal_devices: int
    warning_devices: int
    accident_devices: int
    no_data_devices: int
    summary: str = ""
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class QualityIssue:
    level: str
    code: str
    message: str
    source_file: str
    source_sheet: str = ""
    source_row: int | None = None
    details: dict[str, Any] = field(default_factory=dict)


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


@dataclass(frozen=True)
class AbnormalEvent:
    room_id: str
    device_id: str
    monitor_type: str
    unit: str
    started_at: datetime
    ended_at: datetime | None
    highest_status: MonitoringStatus
    peak_value: float
    peak_time: datetime
    record_count: int
    duration_days: float
    source_records: tuple[MonitoringRecord, ...]
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class GrowthSignal:
    room_id: str
    device_id: str
    monitor_type: str
    unit: str
    latest_at: datetime
    latest_value: float
    previous_value: float
    recent_change: float
    recent_slope_per_day: float
    median_abs_step: float
    sample_count: int
    multiplier: float
    score: float
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class RiskResult:
    room_id: str
    device_id: str
    score: float
    status: MonitoringStatus
    component_scores: dict[str, float]
    events: tuple[AbnormalEvent, ...]
    growth_signals: tuple[GrowthSignal, ...]
    record_count: int
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class RoomRiskResult:
    room_id: str
    score: float
    max_device_score: float
    abnormal_device_ratio: float
    duration_score: float
    device_count: int
    abnormal_device_count: int
    event_count: int
    longest_event_duration_days: float
    reasons: tuple[str, ...]
