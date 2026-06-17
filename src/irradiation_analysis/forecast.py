from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from math import isfinite
from statistics import fmean

import numpy as np

from irradiation_analysis.models import (
    ForecastHorizon,
    MonitoringRecord,
    MonitoringStatus,
    SeriesForecast,
    SystemForecast,
)
from irradiation_analysis.snapshots import all_device_ids
from irradiation_analysis.status import classify_record, worst_status


SeriesKey = tuple[str, str, str]
Predictor = Callable[[list[MonitoringRecord], float], float]

_HORIZON_DAYS = {
    ForecastHorizon.DAYS_1: 1,
    ForecastHorizon.DAYS_7: 7,
    ForecastHorizon.DAYS_30: 30,
}
HOLDOUT_MAX_POINTS = 30
NEXT_RECORD_FALLBACK_INTERVAL = timedelta(days=1)

_CANDIDATES: tuple[tuple[str, Predictor], ...] = (
    ("最近值", lambda records, target_elapsed: _predict_last_value(records, target_elapsed)),
    ("线性趋势", lambda records, target_elapsed: _predict_linear_trend(records, target_elapsed)),
    ("指数平滑", lambda records, target_elapsed: _predict_exponential_smoothing(records)),
    ("移动平均", lambda records, target_elapsed: _predict_moving_average(records)),
)


@dataclass(frozen=True)
class _CandidateResult:
    method: str
    predicted_value: float
    mean_absolute_error: float


def forecast_series(
    records: Iterable[MonitoringRecord], horizon: ForecastHorizon
) -> SeriesForecast:
    series_records = sorted(records, key=_record_order)
    if not series_records:
        raise ValueError("forecast_series requires at least one record")
    _validate_finite_values(series_records)

    latest = series_records[-1]
    predicted_at = _predicted_at(series_records, horizon)
    target_elapsed = _elapsed_days(series_records[0].monitored_at, predicted_at)

    if len(series_records) < 3:
        predicted_value = _predict_last_value(series_records, target_elapsed)
        method = "最近值"
        confidence = "低"
        explanation = _last_value_explanation(series_records)
    else:
        winner = _best_candidate(series_records, target_elapsed)
        if winner is None:
            predicted_value = _predict_last_value(series_records, target_elapsed)
            method = "最近值"
            confidence = "低"
            explanation = _fallback_explanation(series_records)
        else:
            predicted_value = winner.predicted_value
            method = winner.method
            confidence = _confidence(winner.mean_absolute_error, series_records)
            explanation = _candidate_explanation(series_records, winner)

    predicted_value = float(predicted_value)
    if not isfinite(predicted_value):
        raise ValueError("forecast predicted value must be finite")
    predicted_value = round(predicted_value, 6)
    predicted_status = _classify_forecast_value(latest, predicted_at, predicted_value)

    return SeriesForecast(
        room_id=latest.room_id,
        device_id=latest.device_id,
        monitor_type=latest.monitor_type,
        unit=latest.unit,
        horizon=horizon,
        predicted_at=predicted_at,
        predicted_value=predicted_value,
        predicted_status=predicted_status,
        warning_threshold=latest.warning_threshold,
        control_threshold=latest.control_threshold,
        method=method,
        sample_count=len(series_records),
        training_start=series_records[0].monitored_at,
        training_end=latest.monitored_at,
        confidence=confidence,
        explanation=explanation,
    )


def forecast_system(
    records: Iterable[MonitoringRecord], horizon: ForecastHorizon
) -> SystemForecast:
    grouped = _group_by_series(records)
    series_forecasts = tuple(
        forecast_series(grouped[key], horizon)
        for key in sorted(grouped)
    )

    statuses_by_device: dict[str, list[MonitoringStatus]] = defaultdict(list)
    for series_forecast in series_forecasts:
        statuses_by_device[series_forecast.device_id].append(
            series_forecast.predicted_status
        )

    device_statuses = {
        device_id: worst_status(statuses_by_device.get(device_id, ()))
        for device_id in all_device_ids()
    }
    normal_devices = sum(
        status is MonitoringStatus.NORMAL for status in device_statuses.values()
    )
    warning_devices = sum(
        status is MonitoringStatus.WARNING for status in device_statuses.values()
    )
    accident_devices = sum(
        status is MonitoringStatus.ACCIDENT for status in device_statuses.values()
    )
    no_data_devices = sum(
        status is MonitoringStatus.NO_DATA for status in device_statuses.values()
    )

    return SystemForecast(
        horizon=horizon,
        series_forecasts=series_forecasts,
        device_statuses=device_statuses,
        normal_devices=normal_devices,
        warning_devices=warning_devices,
        accident_devices=accident_devices,
        no_data_devices=no_data_devices,
        summary=(
            f"forecasted_series={len(series_forecasts)}, "
            f"normal_devices={normal_devices}, "
            f"warning_devices={warning_devices}, "
            f"accident_devices={accident_devices}, "
            f"no_data_devices={no_data_devices}"
        ),
    )


def _predict_last_value(records: list[MonitoringRecord], target_elapsed: float) -> float:
    return float(records[-1].value)


def _predict_moving_average(records: list[MonitoringRecord], window: int = 3) -> float:
    values = [record.value for record in records[-window:]]
    return float(fmean(values))


def _predict_linear_trend(
    records: list[MonitoringRecord], target_elapsed: float
) -> float:
    origin = records[0].monitored_at
    elapsed_days = np.array(
        [_elapsed_days(origin, record.monitored_at) for record in records],
        dtype=float,
    )
    values = np.array([record.value for record in records], dtype=float)
    if len(np.unique(elapsed_days)) < 2:
        return float("nan")

    slope, intercept = np.polyfit(elapsed_days, values, 1)
    return float(slope * target_elapsed + intercept)


def _predict_exponential_smoothing(
    records: list[MonitoringRecord], alpha: float = 0.5
) -> float:
    level = float(records[0].value)
    for record in records[1:]:
        level = alpha * float(record.value) + (1.0 - alpha) * level
    return level


def _best_candidate(
    records: list[MonitoringRecord], target_elapsed: float
) -> _CandidateResult | None:
    results: list[_CandidateResult] = []
    for method, predictor in _CANDIDATES:
        predicted_value = predictor(records, target_elapsed)
        if not isfinite(predicted_value):
            continue

        mean_absolute_error = _chronological_holdout_error(records, predictor)
        if mean_absolute_error is None or not isfinite(mean_absolute_error):
            continue

        results.append(
            _CandidateResult(
                method=method,
                predicted_value=float(predicted_value),
                mean_absolute_error=mean_absolute_error,
            )
        )

    return min(
        results,
        key=lambda result: (
            result.mean_absolute_error,
            _candidate_order(result.method),
        ),
        default=None,
    )


def _chronological_holdout_error(
    records: list[MonitoringRecord], predictor: Predictor
) -> float | None:
    errors: list[float] = []
    start_index = max(2, len(records) - HOLDOUT_MAX_POINTS)
    for index in range(start_index, len(records)):
        training_records = records[:index]
        target = records[index]
        target_elapsed = _elapsed_days(
            training_records[0].monitored_at,
            target.monitored_at,
        )
        predicted = predictor(training_records, target_elapsed)
        if not isfinite(predicted):
            return None
        errors.append(abs(predicted - target.value))

    if not errors:
        return None
    return float(fmean(errors))


def _classify_forecast_value(
    latest: MonitoringRecord, predicted_at: datetime, predicted_value: float
) -> MonitoringStatus:
    forecast_record = MonitoringRecord(
        monitored_at=predicted_at,
        date_only=latest.date_only,
        room_id=latest.room_id,
        device_id=latest.device_id,
        monitor_type=latest.monitor_type,
        value=predicted_value,
        unit=latest.unit,
        warning_threshold=latest.warning_threshold,
        control_threshold=latest.control_threshold,
        source_file=latest.source_file,
        source_sheet=latest.source_sheet,
        source_row=latest.source_row,
        import_order=latest.import_order,
        room_name=latest.room_name,
        device_name=latest.device_name,
        data_source=latest.data_source,
        note=latest.note,
    )
    return classify_record(forecast_record)


def _group_by_series(
    records: Iterable[MonitoringRecord],
) -> dict[SeriesKey, list[MonitoringRecord]]:
    grouped: dict[SeriesKey, list[MonitoringRecord]] = defaultdict(list)
    for record in records:
        grouped[(record.device_id, record.monitor_type, record.unit)].append(record)
    for series_records in grouped.values():
        series_records.sort(key=_record_order)
    return dict(grouped)


def _predicted_at(
    records: list[MonitoringRecord], horizon: ForecastHorizon
) -> datetime:
    latest = records[-1]
    if horizon is ForecastHorizon.NEXT_RECORD:
        for prior in reversed(records[:-1]):
            interval = latest.monitored_at - prior.monitored_at
            if interval.total_seconds() > 0:
                return latest.monitored_at + interval
        return latest.monitored_at + NEXT_RECORD_FALLBACK_INTERVAL

    return latest.monitored_at + timedelta(days=_HORIZON_DAYS[horizon])


def _last_value_explanation(records: list[MonitoringRecord]) -> str:
    return (
        f"样本数={len(records)}，训练范围"
        f"{records[0].monitored_at.date()}至{records[-1].monitored_at.date()}；"
        "少于3个点，使用最近值作为保守预测。"
    )


def _fallback_explanation(records: list[MonitoringRecord]) -> str:
    return (
        f"样本数={len(records)}，训练范围"
        f"{records[0].monitored_at.date()}至{records[-1].monitored_at.date()}；"
        "候选方法未产生有效有限结果，回退到最近值。"
    )


def _candidate_explanation(
    records: list[MonitoringRecord], winner: _CandidateResult
) -> str:
    return (
        f"样本数={len(records)}，训练范围"
        f"{records[0].monitored_at.date()}至{records[-1].monitored_at.date()}；"
        f"通过按时间顺序留出验证比较平均绝对误差，选择{winner.method}，"
        f"MAE={winner.mean_absolute_error:.3f}。"
    )


def _confidence(error: float, records: list[MonitoringRecord]) -> str:
    scale = max(max(abs(record.value) for record in records), 1.0)
    ratio = error / scale
    if ratio <= 0.10:
        return "高"
    if ratio <= 0.25:
        return "中"
    return "低"


def _candidate_order(method: str) -> int:
    return {
        "最近值": 0,
        "线性趋势": 1,
        "指数平滑": 2,
        "移动平均": 3,
    }[method]


def _validate_finite_values(records: list[MonitoringRecord]) -> None:
    for record in records:
        if not isfinite(float(record.value)):
            raise ValueError("forecast record values must be finite")


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
