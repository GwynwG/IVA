from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import datetime
from statistics import median

from irradiation_analysis.models import (
    AbnormalEvent,
    GrowthSignal,
    MonitoringRecord,
    MonitoringStatus,
    RiskResult,
    RoomRiskResult,
)
from irradiation_analysis.status import classify_record, worst_status


NEAR_WARNING_RATIO = 0.80
MIN_GROWTH_POINTS = 3
RAPID_GROWTH_MULTIPLIER = 2.0
RISK_WEIGHTS = {
    "severity": 0.40,
    "exceedance": 0.25,
    "duration": 0.15,
    "trend": 0.10,
    "recurrence": 0.10,
}

SeriesKey = tuple[str, str, str]


def build_abnormal_events(records: Iterable[MonitoringRecord]) -> list[AbnormalEvent]:
    events: list[AbnormalEvent] = []

    for series_records in _group_by_series(records).values():
        open_records: list[MonitoringRecord] = []
        for record in series_records:
            status = classify_record(record)
            if status.severity > MonitoringStatus.NORMAL.severity:
                open_records.append(record)
                continue

            if open_records:
                events.append(_build_event(open_records, ended_at=record.monitored_at))
                open_records = []

        if open_records:
            events.append(_build_event(open_records, ended_at=None))

    return sorted(
        events,
        key=lambda event: (
            event.started_at,
            event.device_id,
            event.monitor_type,
            event.unit,
        ),
    )


def find_near_threshold(
    records: Iterable[MonitoringRecord], ratio: float = NEAR_WARNING_RATIO
) -> list[MonitoringRecord]:
    candidates = [
        record
        for record in records
        if _is_near_warning(record, ratio)
    ]
    return sorted(
        candidates,
        key=lambda record: (
            -_warning_ratio(record),
            -record.monitored_at.timestamp(),
            record.device_id,
            record.monitor_type,
            record.unit,
            record.import_order,
        ),
    )


def find_growth_signals(
    records: Iterable[MonitoringRecord],
    multiplier: float = RAPID_GROWTH_MULTIPLIER,
) -> list[GrowthSignal]:
    signals: list[GrowthSignal] = []

    for series_records in _group_by_series(records).values():
        if len(series_records) < MIN_GROWTH_POINTS:
            continue

        previous = series_records[-2]
        latest = series_records[-1]
        elapsed_days = _elapsed_days(previous.monitored_at, latest.monitored_at)
        if elapsed_days <= 0:
            continue

        recent_change = latest.value - previous.value
        recent_slope = recent_change / elapsed_days
        if recent_slope <= 0:
            continue

        historical_steps = [
            abs(current.value - prior.value)
            for prior, current in zip(series_records[:-2], series_records[1:-1])
        ]
        median_abs_step = float(median(historical_steps)) if historical_steps else 0.0
        threshold = median_abs_step * multiplier
        if median_abs_step > 0 and recent_change <= threshold:
            continue
        if median_abs_step == 0 and recent_change <= 0:
            continue

        score = _growth_score(recent_change, threshold)
        signals.append(
            GrowthSignal(
                room_id=latest.room_id,
                device_id=latest.device_id,
                monitor_type=latest.monitor_type,
                unit=latest.unit,
                latest_at=latest.monitored_at,
                latest_value=latest.value,
                previous_value=previous.value,
                recent_change=round(recent_change, 6),
                recent_slope_per_day=round(recent_slope, 6),
                median_abs_step=round(median_abs_step, 6),
                sample_count=len(series_records),
                multiplier=multiplier,
                score=score,
                reasons=(
                    "recent growth exceeds historical variation",
                    f"recent_change={recent_change:.3f}",
                    f"median_abs_step={median_abs_step:.3f}",
                ),
            )
        )

    return sorted(
        signals,
        key=lambda signal: (
            -signal.score,
            signal.device_id,
            signal.monitor_type,
            signal.unit,
        ),
    )


def rank_device_risks(records: Iterable[MonitoringRecord]) -> list[RiskResult]:
    record_list = list(records)
    records_by_device = _group_by_device(record_list)
    events_by_device = _events_by_device(build_abnormal_events(record_list))
    signals_by_device = _signals_by_device(find_growth_signals(record_list))

    results = [
        _device_risk(
            device_id=device_id,
            records=device_records,
            events=events_by_device.get(device_id, ()),
            growth_signals=signals_by_device.get(device_id, ()),
        )
        for device_id, device_records in records_by_device.items()
    ]
    return sorted(results, key=lambda result: (-result.score, result.device_id))


def rank_room_risks(
    records: Iterable[MonitoringRecord],
    device_risks: Iterable[RiskResult] | None = None,
) -> list[RoomRiskResult]:
    record_list = list(records)
    risks = list(device_risks) if device_risks is not None else rank_device_risks(record_list)
    records_by_room = _group_by_room(record_list)
    risks_by_room: dict[str, list[RiskResult]] = defaultdict(list)
    for risk in risks:
        risks_by_room[risk.room_id].append(risk)

    results: list[RoomRiskResult] = []
    for room_id, room_records in records_by_room.items():
        room_risks = risks_by_room.get(room_id, [])
        device_ids = {record.device_id for record in room_records}
        abnormal_device_ids = {
            risk.device_id
            for risk in room_risks
            if risk.status.severity > MonitoringStatus.NORMAL.severity
        }
        device_count = len(device_ids)
        abnormal_count = len(abnormal_device_ids)
        abnormal_ratio = abnormal_count / device_count if device_count else 0.0
        max_device_score = max((risk.score for risk in room_risks), default=0.0)
        duration_score = max(
            (
                risk.component_scores.get("duration", 0.0)
                for risk in room_risks
            ),
            default=0.0,
        )
        room_events = [
            event
            for risk in room_risks
            for event in risk.events
        ]
        event_count = len(room_events)
        longest_event_duration = max(
            (event.duration_days for event in room_events),
            default=0.0,
        )
        score = _clamp_score(
            max_device_score * 0.60
            + abnormal_ratio * 100.0 * 0.25
            + duration_score * 0.15
        )
        results.append(
            RoomRiskResult(
                room_id=room_id,
                score=score,
                max_device_score=max_device_score,
                abnormal_device_ratio=round(abnormal_ratio, 6),
                duration_score=duration_score,
                device_count=device_count,
                abnormal_device_count=abnormal_count,
                event_count=event_count,
                longest_event_duration_days=round(longest_event_duration, 6),
                reasons=_room_reasons(
                    max_device_score,
                    abnormal_ratio,
                    duration_score,
                    event_count,
                    longest_event_duration,
                ),
            )
        )

    return sorted(results, key=lambda result: (-result.score, result.room_id))


def _build_event(
    abnormal_records: list[MonitoringRecord], ended_at: datetime | None
) -> AbnormalEvent:
    started_at = abnormal_records[0].monitored_at
    peak_record = max(abnormal_records, key=lambda record: (record.value, _record_order(record)))
    highest_status = worst_status(classify_record(record) for record in abnormal_records)
    evidence_end = ended_at or abnormal_records[-1].monitored_at
    duration_days = _elapsed_days(started_at, evidence_end)
    return AbnormalEvent(
        room_id=abnormal_records[0].room_id,
        device_id=abnormal_records[0].device_id,
        monitor_type=abnormal_records[0].monitor_type,
        unit=abnormal_records[0].unit,
        started_at=started_at,
        ended_at=ended_at,
        highest_status=highest_status,
        peak_value=peak_record.value,
        peak_time=peak_record.monitored_at,
        record_count=len(abnormal_records),
        duration_days=round(duration_days, 6),
        source_records=tuple(abnormal_records),
        reasons=(
            f"highest_status={highest_status.name}",
            f"peak_value={peak_record.value:g}",
            f"record_count={len(abnormal_records)}",
        ),
    )


def _device_risk(
    device_id: str,
    records: list[MonitoringRecord],
    events: tuple[AbnormalEvent, ...],
    growth_signals: tuple[GrowthSignal, ...],
) -> RiskResult:
    status = worst_status(classify_record(record) for record in records)
    component_scores = {
        "severity": _severity_score(status),
        "exceedance": _exceedance_score(records),
        "duration": _duration_score(events),
        "trend": max((signal.score for signal in growth_signals), default=0.0),
        "recurrence": _recurrence_score(events),
    }
    score = _clamp_score(
        sum(component_scores[name] * RISK_WEIGHTS[name] for name in RISK_WEIGHTS)
    )
    return RiskResult(
        room_id=records[0].room_id,
        device_id=device_id,
        score=score,
        status=status,
        component_scores={name: round(value, 6) for name, value in component_scores.items()},
        events=events,
        growth_signals=growth_signals,
        record_count=len(records),
        reasons=_risk_reasons(status, component_scores, events, growth_signals),
    )


def _group_by_series(
    records: Iterable[MonitoringRecord],
) -> dict[SeriesKey, list[MonitoringRecord]]:
    grouped: dict[SeriesKey, list[MonitoringRecord]] = defaultdict(list)
    for record in records:
        grouped[(record.device_id, record.monitor_type, record.unit)].append(record)
    for series_records in grouped.values():
        series_records.sort(key=_record_order)
    return dict(grouped)


def _group_by_device(
    records: Iterable[MonitoringRecord],
) -> dict[str, list[MonitoringRecord]]:
    grouped: dict[str, list[MonitoringRecord]] = defaultdict(list)
    for record in records:
        grouped[record.device_id].append(record)
    for device_records in grouped.values():
        device_records.sort(key=_record_order)
    return dict(grouped)


def _group_by_room(
    records: Iterable[MonitoringRecord],
) -> dict[str, list[MonitoringRecord]]:
    grouped: dict[str, list[MonitoringRecord]] = defaultdict(list)
    for record in records:
        grouped[record.room_id].append(record)
    return dict(sorted(grouped.items()))


def _events_by_device(
    events: Iterable[AbnormalEvent],
) -> dict[str, tuple[AbnormalEvent, ...]]:
    grouped: dict[str, list[AbnormalEvent]] = defaultdict(list)
    for event in events:
        grouped[event.device_id].append(event)
    return {device_id: tuple(device_events) for device_id, device_events in grouped.items()}


def _signals_by_device(
    signals: Iterable[GrowthSignal],
) -> dict[str, tuple[GrowthSignal, ...]]:
    grouped: dict[str, list[GrowthSignal]] = defaultdict(list)
    for signal in signals:
        grouped[signal.device_id].append(signal)
    return {
        device_id: tuple(device_signals)
        for device_id, device_signals in grouped.items()
    }


def _is_near_warning(record: MonitoringRecord, ratio: float) -> bool:
    if record.warning_threshold <= 0:
        return False
    if classify_record(record) is not MonitoringStatus.NORMAL:
        return False
    return record.value >= record.warning_threshold * ratio


def _warning_ratio(record: MonitoringRecord) -> float:
    if record.warning_threshold <= 0:
        return 0.0
    return record.value / record.warning_threshold


def _severity_score(status: MonitoringStatus) -> float:
    return {
        MonitoringStatus.NO_DATA: 0.0,
        MonitoringStatus.NORMAL: 0.0,
        MonitoringStatus.WARNING: 60.0,
        MonitoringStatus.ACCIDENT: 100.0,
    }[status]


def _exceedance_score(records: Iterable[MonitoringRecord]) -> float:
    return max((_record_exceedance_score(record) for record in records), default=0.0)


def _record_exceedance_score(record: MonitoringRecord) -> float:
    if record.control_threshold > 0 and record.value >= record.control_threshold:
        excess_ratio = (record.value - record.control_threshold) / record.control_threshold
        return _clamp_score(75.0 + excess_ratio * 25.0)
    if (
        record.warning_threshold > 0
        and record.control_threshold > record.warning_threshold
        and record.value >= record.warning_threshold
    ):
        span = record.control_threshold - record.warning_threshold
        position = (record.value - record.warning_threshold) / span
        return _clamp_score(40.0 + position * 35.0)
    if record.warning_threshold > 0:
        return _clamp_score(_warning_ratio(record) * 25.0)
    return 0.0


def _duration_score(events: Iterable[AbnormalEvent]) -> float:
    scores = [
        max(event.duration_days * 20.0, event.record_count * 20.0)
        for event in events
    ]
    return _clamp_score(max(scores, default=0.0))


def _recurrence_score(events: Iterable[AbnormalEvent]) -> float:
    event_count = len(tuple(events))
    if event_count == 0:
        return 0.0
    return _clamp_score(30.0 + max(0, event_count - 1) * 35.0)


def _growth_score(recent_change: float, threshold: float) -> float:
    if threshold <= 0:
        return 60.0
    excess_ratio = (recent_change - threshold) / threshold
    return _clamp_score(60.0 + excess_ratio * 40.0)


def _risk_reasons(
    status: MonitoringStatus,
    component_scores: dict[str, float],
    events: tuple[AbnormalEvent, ...],
    growth_signals: tuple[GrowthSignal, ...],
) -> tuple[str, ...]:
    reasons: list[str] = []
    if status.severity > MonitoringStatus.NORMAL.severity:
        reasons.append(f"highest status is {status.name}")
    if events:
        reasons.append(f"abnormal events={len(events)}")
    if growth_signals:
        reasons.append("rapid growth signal detected")

    contributors = sorted(
        component_scores.items(),
        key=lambda item: item[1] * RISK_WEIGHTS[item[0]],
        reverse=True,
    )
    for name, value in contributors:
        if value > 0 and len(reasons) < 4:
            reasons.append(f"{name}_score={value:.1f}")

    return tuple(reasons or ("no abnormal evidence",))


def _room_reasons(
    max_device_score: float,
    abnormal_ratio: float,
    duration_score: float,
    event_count: int,
    longest_event_duration: float,
) -> tuple[str, ...]:
    reasons = [
        f"max_device_score={max_device_score:.1f}",
        f"abnormal_device_ratio={abnormal_ratio:.2f}",
        f"event_count={event_count}",
    ]
    if duration_score > 0:
        reasons.append(f"duration_score={duration_score:.1f}")
    if longest_event_duration > 0:
        reasons.append(f"longest_event_duration_days={longest_event_duration:.1f}")
    return tuple(reasons)


def _record_order(record: MonitoringRecord) -> tuple[datetime, int, str, str, int]:
    return (
        record.monitored_at,
        record.import_order,
        record.source_file,
        record.source_sheet,
        record.source_row,
    )


def _elapsed_days(start: datetime, end: datetime) -> float:
    return max(0.0, (end - start).total_seconds() / 86400.0)


def _clamp_score(value: float) -> float:
    return round(max(0.0, min(100.0, value)), 6)
