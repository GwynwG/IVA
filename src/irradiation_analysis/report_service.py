from __future__ import annotations

from irradiation_analysis.alerts import build_warning_alerts
from irradiation_analysis.analytics import build_abnormal_events, rank_device_risks, rank_room_risks
from irradiation_analysis.excel_io import ImportResult
from irradiation_analysis.forecast import ForecastHorizon, forecast_system
from irradiation_analysis.reporting import AnalysisReportInput, build_analysis_report
from irradiation_analysis.snapshots import build_point_in_time_snapshot


def build_analysis_report_from_import_result(
    result: ImportResult,
    horizon: ForecastHorizon = ForecastHorizon.DAYS_7,
) -> bytes:
    if not result.records:
        raise ValueError("报告生成需要至少一条有效监测记录。")

    records = result.records
    selected_at = max(record.monitored_at for record in records)
    snapshot = build_point_in_time_snapshot(records, selected_at)
    events = build_abnormal_events(records)
    device_risks = rank_device_risks(records)
    room_risks = rank_room_risks(records, device_risks)
    system_forecast = forecast_system(records, horizon)
    warning_alerts = build_warning_alerts(records, horizon)
    report_input = AnalysisReportInput(
        import_result=result,
        snapshot=snapshot,
        events=events,
        device_risks=device_risks,
        room_risks=room_risks,
        series_forecasts=system_forecast.series_forecasts,
        system_forecast=system_forecast,
        warning_alerts=warning_alerts,
    )
    return build_analysis_report(report_input)
