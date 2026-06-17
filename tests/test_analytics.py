from datetime import datetime

from irradiation_analysis.analytics import (
    NEAR_WARNING_RATIO,
    RISK_WEIGHTS,
    build_abnormal_events,
    find_growth_signals,
    find_near_threshold,
    rank_device_risks,
    rank_room_risks,
)
from irradiation_analysis.models import MonitoringRecord, MonitoringStatus


def record(
    day: int,
    value: float,
    *,
    device_id: str = "R01-D01",
    monitor_type: str = "dose_rate",
    unit: str = "uSv/h",
    warning: float = 10.0,
    control: float = 20.0,
    import_order: int | None = None,
) -> MonitoringRecord:
    return MonitoringRecord(
        monitored_at=datetime(2026, 6, day),
        date_only=False,
        room_id=device_id.split("-")[0],
        device_id=device_id,
        monitor_type=monitor_type,
        value=value,
        unit=unit,
        warning_threshold=warning,
        control_threshold=control,
        source_file="analytics.xlsx",
        source_sheet="monitoring",
        source_row=day + 1,
        import_order=day if import_order is None else import_order,
    )


def test_contiguous_abnormal_records_form_one_event():
    events = build_abnormal_events(
        [
            record(1, 9.0),
            record(2, 11.0),
            record(3, 22.0),
            record(4, 18.0),
        ]
    )

    assert len(events) == 1
    assert events[0].device_id == "R01-D01"
    assert events[0].monitor_type == "dose_rate"
    assert events[0].unit == "uSv/h"
    assert events[0].started_at == datetime(2026, 6, 2)
    assert events[0].ended_at is None
    assert events[0].highest_status is MonitoringStatus.ACCIDENT
    assert events[0].peak_value == 22.0
    assert events[0].peak_time == datetime(2026, 6, 3)
    assert events[0].record_count == 3
    assert events[0].reasons


def test_normal_record_ends_an_event():
    events = build_abnormal_events(
        [
            record(1, 11.0),
            record(2, 21.0),
            record(3, 8.0),
            record(4, 12.0),
        ]
    )

    assert len(events) == 2
    assert events[0].ended_at == datetime(2026, 6, 3)
    assert events[0].duration_days == 2.0
    assert events[1].started_at == datetime(2026, 6, 4)
    assert events[1].ended_at is None


def test_near_threshold_uses_eighty_percent_default():
    candidates = find_near_threshold(
        [
            record(1, 7.9),
            record(2, 8.0),
            record(3, 9.5, device_id="R01-D02"),
            record(4, 10.0, device_id="R01-D03"),
            record(5, 8.0, device_id="R01-D04", warning=0.0),
        ]
    )

    assert NEAR_WARNING_RATIO == 0.80
    assert [candidate.device_id for candidate in candidates] == [
        "R01-D02",
        "R01-D01",
    ]
    assert all(candidate.value < candidate.warning_threshold for candidate in candidates)


def test_non_positive_thresholds_do_not_create_false_abnormal_risk():
    records = [
        record(1, 8.0, warning=10.0, control=0.0),
        record(2, 8.0, device_id="R01-D02", warning=-1.0, control=-2.0),
    ]

    assert build_abnormal_events(records) == []
    assert [candidate.device_id for candidate in find_near_threshold(records)] == [
        "R01-D01"
    ]

    risks = rank_device_risks(records)
    assert {risk.device_id: risk.status for risk in risks} == {
        "R01-D01": MonitoringStatus.NORMAL,
        "R01-D02": MonitoringStatus.NORMAL,
    }
    assert all(risk.score < 10 for risk in risks)


def test_growth_signal_uses_elapsed_days_and_median_step():
    signals = find_growth_signals(
        [
            record(1, 10.0),
            record(3, 11.0),
            record(10, 18.0),
            record(11, 31.0),
            record(1, 5.0, device_id="R01-D02"),
            record(2, 5.1, device_id="R01-D02"),
        ]
    )

    assert len(signals) == 1
    signal = signals[0]
    assert signal.device_id == "R01-D01"
    assert signal.sample_count == 4
    assert signal.recent_change == 13.0
    assert signal.recent_slope_per_day == 13.0
    assert signal.median_abs_step == 4.0
    assert signal.reasons


def test_risk_score_is_explainable_bounded_and_sorted():
    records = [
        record(1, 8.0, device_id="R01-D01"),
        record(2, 11.0, device_id="R01-D01"),
        record(3, 21.0, device_id="R01-D01"),
        record(4, 8.0, device_id="R01-D01"),
        record(5, 12.0, device_id="R01-D01"),
        record(1, 8.0, device_id="R01-D02"),
        record(2, 8.5, device_id="R01-D02"),
        record(3, 9.0, device_id="R01-D02"),
    ]

    results = rank_device_risks(records)

    assert RISK_WEIGHTS == {
        "severity": 0.40,
        "exceedance": 0.25,
        "duration": 0.15,
        "trend": 0.10,
        "recurrence": 0.10,
    }
    assert results[0].device_id == "R01-D01"
    assert [result.score for result in results] == sorted(
        (result.score for result in results), reverse=True
    )
    assert all(0 <= result.score <= 100 for result in results)
    assert results[0].status is MonitoringStatus.ACCIDENT
    assert results[0].reasons
    assert results[0].component_scores["severity"] == 100.0


def test_room_risk_aggregates_device_risk_and_abnormal_ratio():
    records = [
        record(1, 21.0, device_id="R01-D01"),
        record(2, 8.0, device_id="R01-D02"),
        record(1, 11.0, device_id="R02-D01"),
    ]

    room_risks = rank_room_risks(records)

    assert room_risks[0].room_id == "R01"
    assert all(0 <= result.score <= 100 for result in room_risks)
    assert room_risks[0].max_device_score >= room_risks[1].max_device_score
    assert room_risks[0].abnormal_device_count == 1
    assert room_risks[0].device_count == 2
    assert room_risks[0].abnormal_device_ratio == 0.5
    assert room_risks[0].event_count == 1
    assert room_risks[0].longest_event_duration_days == 0.0
    assert room_risks[0].reasons
