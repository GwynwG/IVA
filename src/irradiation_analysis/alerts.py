from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from irradiation_analysis.analytics import (
    find_growth_signals,
    find_near_threshold,
    build_abnormal_events,
)
from irradiation_analysis.forecast import ForecastHorizon, forecast_system
from irradiation_analysis.models import (
    GrowthSignal,
    MonitoringRecord,
    MonitoringStatus,
    SeriesForecast,
    WarningAlert,
)
from irradiation_analysis.status import classify_record


DEFAULT_ALERT_LIMIT = 200


def build_warning_alerts(
    records: Iterable[MonitoringRecord],
    horizon: ForecastHorizon = ForecastHorizon.DAYS_7,
    limit: int = DEFAULT_ALERT_LIMIT,
) -> list[WarningAlert]:
    record_list = list(records)
    latest_by_series = _latest_by_series(record_list)
    alerts: list[WarningAlert] = []

    alerts.extend(_current_threshold_alert(record) for record in latest_by_series.values())
    alerts.extend(_near_warning_alert(record) for record in find_near_threshold(latest_by_series.values()))
    alerts.extend(_growth_alert(signal) for signal in find_growth_signals(record_list))
    alerts.extend(_event_alert(event) for event in build_abnormal_events(record_list) if event.ended_at is None)
    alerts.extend(_forecast_alerts(record_list, latest_by_series, horizon))

    return _deduplicate_alerts(alerts)[:limit]


def _current_threshold_alert(record: MonitoringRecord) -> WarningAlert:
    status = classify_record(record)
    if status is MonitoringStatus.ACCIDENT:
        return WarningAlert(
            room_id=record.room_id,
            device_id=record.device_id,
            monitor_type=record.monitor_type,
            unit=record.unit,
            rule_code="current_accident",
            level="事故级",
            score=100.0,
            triggered_at=record.monitored_at,
            current_value=record.value,
            warning_threshold=record.warning_threshold,
            control_threshold=record.control_threshold,
            evidence=f"当前值 {record.value:g} 已达到或超过控制标准 {record.control_threshold:g}。",
            recommended_action="立即复核现场读数、仪器状态和安全处置记录。",
        )
    if status is MonitoringStatus.WARNING:
        return WarningAlert(
            room_id=record.room_id,
            device_id=record.device_id,
            monitor_type=record.monitor_type,
            unit=record.unit,
            rule_code="current_warning",
            level="预警",
            score=82.0,
            triggered_at=record.monitored_at,
            current_value=record.value,
            warning_threshold=record.warning_threshold,
            control_threshold=record.control_threshold,
            evidence=f"当前值 {record.value:g} 已达到或超过预警值 {record.warning_threshold:g}。",
            recommended_action="安排复测并确认近期作业、屏蔽和仪器校准状态。",
        )
    return _empty_alert(record)


def _near_warning_alert(record: MonitoringRecord) -> WarningAlert:
    ratio = record.value / record.warning_threshold if record.warning_threshold > 0 else 0.0
    return WarningAlert(
        room_id=record.room_id,
        device_id=record.device_id,
        monitor_type=record.monitor_type,
        unit=record.unit,
        rule_code="near_warning",
        level="关注",
        score=round(45.0 + min(ratio, 1.0) * 25.0, 6),
        triggered_at=record.monitored_at,
        current_value=record.value,
        warning_threshold=record.warning_threshold,
        control_threshold=record.control_threshold,
        evidence=f"当前值达到预警值的 {ratio:.1%}，尚未正式超阈。",
        recommended_action="保持观察，必要时缩短下一次采样间隔。",
    )


def _growth_alert(signal: GrowthSignal) -> WarningAlert:
    return WarningAlert(
        room_id=signal.room_id,
        device_id=signal.device_id,
        monitor_type=signal.monitor_type,
        unit=signal.unit,
        rule_code="rapid_growth",
        level="趋势预警",
        score=round(max(60.0, signal.score), 6),
        triggered_at=signal.latest_at,
        current_value=signal.latest_value,
        warning_threshold=None,
        control_threshold=None,
        evidence=(
            f"最新增量 {signal.recent_change:g}，历史中位步长 "
            f"{signal.median_abs_step:g}，日斜率 {signal.recent_slope_per_day:g}。"
        ),
        recommended_action="核对近期趋势，确认是否存在工况变化或传感器漂移。",
    )


def _event_alert(event) -> WarningAlert:
    level = "持续事故级" if event.highest_status is MonitoringStatus.ACCIDENT else "持续预警"
    score = 96.0 if event.highest_status is MonitoringStatus.ACCIDENT else 86.0
    return WarningAlert(
        room_id=event.room_id,
        device_id=event.device_id,
        monitor_type=event.monitor_type,
        unit=event.unit,
        rule_code="open_event",
        level=level,
        score=score,
        triggered_at=event.peak_time,
        current_value=event.peak_value,
        warning_threshold=None,
        control_threshold=None,
        evidence=f"异常事件尚未关闭，记录数 {event.record_count}，持续 {event.duration_days:.1f} 天。",
        recommended_action="跟踪事件闭环，补充处置记录并确认恢复条件。",
    )


def _forecast_alerts(
    records: list[MonitoringRecord],
    latest_by_series: dict[tuple[str, str, str], MonitoringRecord],
    horizon: ForecastHorizon,
) -> list[WarningAlert]:
    try:
        system_forecast = forecast_system(records, horizon)
    except ValueError:
        return []

    alerts = []
    for forecast in system_forecast.series_forecasts:
        latest = latest_by_series.get((forecast.device_id, forecast.monitor_type, forecast.unit))
        if latest is not None and classify_record(latest) is not MonitoringStatus.NORMAL:
            continue
        if forecast.predicted_status is MonitoringStatus.ACCIDENT:
            alerts.append(_forecast_alert(forecast, "预测事故级", 88.0))
        elif forecast.predicted_status is MonitoringStatus.WARNING:
            alerts.append(_forecast_alert(forecast, "预测预警", 72.0))
    return alerts


def _forecast_alert(forecast: SeriesForecast, level: str, base_score: float) -> WarningAlert:
    return WarningAlert(
        room_id=forecast.room_id,
        device_id=forecast.device_id,
        monitor_type=forecast.monitor_type,
        unit=forecast.unit,
        rule_code="forecast_threshold",
        level=level,
        score=base_score,
        triggered_at=forecast.predicted_at,
        current_value=forecast.predicted_value,
        warning_threshold=forecast.warning_threshold,
        control_threshold=forecast.control_threshold,
        evidence=(
            f"{forecast.horizon.value}预测值 {forecast.predicted_value:g}，"
            f"预测状态为 {forecast.predicted_status.value}，方法 {forecast.method}，"
            f"置信度 {forecast.confidence}。"
        ),
        recommended_action="提前安排复测计划，观察预测窗口内是否继续接近阈值。",
    )


def _latest_by_series(records: Iterable[MonitoringRecord]) -> dict[tuple[str, str, str], MonitoringRecord]:
    latest: dict[tuple[str, str, str], MonitoringRecord] = {}
    for record in records:
        key = (record.device_id, record.monitor_type, record.unit)
        prior = latest.get(key)
        if prior is None or _record_order(record) > _record_order(prior):
            latest[key] = record
    return latest


def _deduplicate_alerts(alerts: Iterable[WarningAlert]) -> list[WarningAlert]:
    filtered = [alert for alert in alerts if alert.rule_code]
    best_by_key: dict[tuple[str, str, str, str, str], WarningAlert] = {}
    for alert in filtered:
        key = (
            alert.device_id,
            alert.monitor_type,
            alert.unit,
            alert.rule_code,
            alert.level,
        )
        prior = best_by_key.get(key)
        if prior is None or _alert_order(alert) < _alert_order(prior):
            best_by_key[key] = alert
    return sorted(best_by_key.values(), key=_alert_order)


def _alert_order(alert: WarningAlert) -> tuple[float, float, str, str, str]:
    return (
        -alert.score,
        -alert.triggered_at.timestamp(),
        alert.room_id,
        alert.device_id,
        alert.rule_code,
    )


def _record_order(record: MonitoringRecord) -> tuple[datetime, int, str, str, int]:
    return (
        record.monitored_at,
        record.import_order,
        record.source_file,
        record.source_sheet,
        record.source_row,
    )


def _empty_alert(record: MonitoringRecord) -> WarningAlert:
    return WarningAlert(
        room_id=record.room_id,
        device_id=record.device_id,
        monitor_type=record.monitor_type,
        unit=record.unit,
        rule_code="",
        level="",
        score=0.0,
        triggered_at=record.monitored_at,
        current_value=None,
        warning_threshold=None,
        control_threshold=None,
        evidence="",
        recommended_action="",
    )
