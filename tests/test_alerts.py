from datetime import datetime

from irradiation_analysis.alerts import build_warning_alerts
from irradiation_analysis.forecast import ForecastHorizon
from irradiation_analysis.models import MonitoringRecord


def record(
    day: int,
    value: float,
    *,
    device_id: str = "R01-D01",
    warning: float = 10.0,
    control: float = 20.0,
    import_order: int | None = None,
) -> MonitoringRecord:
    return MonitoringRecord(
        monitored_at=datetime(2026, 6, day),
        date_only=False,
        room_id=device_id.split("-")[0],
        device_id=device_id,
        monitor_type="dose_rate",
        value=value,
        unit="uSv/h",
        warning_threshold=warning,
        control_threshold=control,
        source_file="alerts.xlsx",
        source_sheet="monitoring",
        source_row=day + 1,
        import_order=day if import_order is None else import_order,
    )


def test_current_threshold_alerts_are_ranked_first():
    alerts = build_warning_alerts(
        [
            record(1, 9.0),
            record(2, 22.0),
            record(1, 8.0, device_id="R01-D02"),
            record(2, 11.0, device_id="R01-D02"),
        ],
        horizon=ForecastHorizon.DAYS_1,
    )

    assert alerts[0].rule_code == "current_accident"
    assert alerts[0].level == "事故级"
    assert alerts[0].score == 100.0
    assert any(alert.rule_code == "current_warning" for alert in alerts)


def test_near_warning_alert_uses_latest_normal_record():
    alerts = build_warning_alerts(
        [
            record(1, 9.1),
            record(2, 7.0),
            record(3, 8.5, device_id="R01-D02"),
        ],
        horizon=ForecastHorizon.DAYS_1,
    )

    near_alerts = [alert for alert in alerts if alert.rule_code == "near_warning"]

    assert [alert.device_id for alert in near_alerts] == ["R01-D02"]
    assert near_alerts[0].level == "关注"
    assert "尚未正式超阈" in near_alerts[0].evidence


def test_growth_and_forecast_alerts_include_evidence_and_actions():
    alerts = build_warning_alerts(
        [
            record(1, 10.0, warning=15.0, control=25.0),
            record(2, 11.0, warning=15.0, control=25.0),
            record(3, 14.0, warning=15.0, control=25.0),
        ],
        horizon=ForecastHorizon.DAYS_1,
    )

    by_rule = {alert.rule_code: alert for alert in alerts}

    assert by_rule["rapid_growth"].level == "趋势预警"
    assert "历史中位步长" in by_rule["rapid_growth"].evidence
    assert "传感器漂移" in by_rule["rapid_growth"].recommended_action
    assert by_rule["forecast_threshold"].level == "预测预警"
    assert "未来1天预测值" in by_rule["forecast_threshold"].evidence
