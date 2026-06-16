from datetime import datetime
from math import isfinite

from irradiation_analysis.forecast import forecast_series, forecast_system
from irradiation_analysis.models import ForecastHorizon, MonitoringRecord, MonitoringStatus


def record(
    when: datetime,
    value: float,
    *,
    device_id: str = "R01-D01",
    monitor_type: str = "dose_rate",
    unit: str = "uSv/h",
    warning: float = 10.0,
    control: float = 20.0,
    import_order: int = 0,
) -> MonitoringRecord:
    return MonitoringRecord(
        monitored_at=when,
        date_only=False,
        room_id=device_id.split("-")[0],
        device_id=device_id,
        monitor_type=monitor_type,
        value=value,
        unit=unit,
        warning_threshold=warning,
        control_threshold=control,
        source_file="forecast.xlsx",
        source_sheet="monitoring",
        source_row=import_order + 2,
        import_order=import_order,
    )


def test_less_than_three_points_uses_last_value():
    records = [
        record(datetime(2026, 6, 10, 8), 1.0, import_order=1),
        record(datetime(2026, 6, 10, 14), 2.5, import_order=2),
    ]

    forecast = forecast_series(records, ForecastHorizon.NEXT_RECORD)

    assert forecast.method == "最近值"
    assert forecast.confidence == "低"
    assert forecast.predicted_value == 2.5
    assert forecast.predicted_at == datetime(2026, 6, 10, 20)
    assert forecast.sample_count == 2
    assert forecast.training_start == datetime(2026, 6, 10, 8)
    assert forecast.training_end == datetime(2026, 6, 10, 14)
    assert forecast.explanation


def test_three_or_more_points_can_select_last_value_candidate():
    records = [
        record(datetime(2026, 6, 1), 0.0, import_order=1),
        record(datetime(2026, 6, 2), 10.0, import_order=2),
        record(datetime(2026, 6, 3), 10.0, import_order=3),
        record(datetime(2026, 6, 4), 10.0, import_order=4),
    ]

    forecast = forecast_series(records, ForecastHorizon.NEXT_RECORD)

    assert forecast.method == "最近值"
    assert forecast.predicted_value == 10.0


def test_irregular_sampling_uses_elapsed_time():
    records = [
        record(datetime(2026, 6, 1), 3.0, import_order=1),
        record(datetime(2026, 6, 4), 4.0, import_order=2),
        record(datetime(2026, 6, 10), 6.0, import_order=3),
    ]

    forecast = forecast_series(records, ForecastHorizon.DAYS_7)

    assert forecast.predicted_at == datetime(2026, 6, 17)
    assert forecast.method in {"线性趋势", "指数平滑", "移动平均"}
    assert isfinite(forecast.predicted_value)
    assert -100.0 < forecast.predicted_value < 100.0
    assert "3" in forecast.explanation
    assert "2026-06-01" in forecast.explanation
    assert "2026-06-10" in forecast.explanation


def test_forecast_status_uses_latest_thresholds():
    records = [
        record(
            datetime(2026, 6, 1),
            4.0,
            warning=100.0,
            control=200.0,
            import_order=1,
        ),
        record(
            datetime(2026, 6, 2),
            6.0,
            warning=5.0,
            control=0.0,
            import_order=2,
        ),
    ]

    forecast = forecast_series(records, ForecastHorizon.NEXT_RECORD)

    assert forecast.warning_threshold == 5.0
    assert forecast.control_threshold == 0.0
    assert forecast.predicted_value == 6.0
    assert forecast.predicted_status is MonitoringStatus.WARNING


def test_forecast_status_ignores_non_positive_latest_thresholds():
    records = [
        record(datetime(2026, 6, 1), 30.0, warning=5.0, control=20.0, import_order=1),
        record(datetime(2026, 6, 2), 30.0, warning=-1.0, control=0.0, import_order=2),
    ]

    forecast = forecast_series(records, ForecastHorizon.NEXT_RECORD)

    assert forecast.warning_threshold == -1.0
    assert forecast.control_threshold == 0.0
    assert forecast.predicted_status is MonitoringStatus.NORMAL


def test_system_forecast_counts_worst_device_status():
    records = [
        record(
            datetime(2026, 6, 1),
            25.0,
            monitor_type="alpha",
            warning=10.0,
            control=20.0,
            import_order=1,
        ),
        record(
            datetime(2026, 6, 1),
            6.0,
            monitor_type="beta",
            warning=5.0,
            control=20.0,
            import_order=2,
        ),
        record(
            datetime(2026, 6, 1),
            1.0,
            device_id="R01-D02",
            warning=10.0,
            control=20.0,
            import_order=3,
        ),
    ]

    forecast = forecast_system(records, ForecastHorizon.NEXT_RECORD)

    assert [series.device_id for series in forecast.series_forecasts] == [
        "R01-D01",
        "R01-D01",
        "R01-D02",
    ]
    assert forecast.device_statuses["R01-D01"] is MonitoringStatus.ACCIDENT
    assert forecast.device_statuses["R01-D02"] is MonitoringStatus.NORMAL
    assert forecast.device_statuses["R01-D03"] is MonitoringStatus.NO_DATA
    assert forecast.normal_devices == 1
    assert forecast.warning_devices == 0
    assert forecast.accident_devices == 1
    assert forecast.no_data_devices == 198
