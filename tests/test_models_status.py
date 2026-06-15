from irradiation_analysis.models import MonitoringStatus


def test_monitoring_status_severity_order():
    assert MonitoringStatus.NORMAL.severity < MonitoringStatus.WARNING.severity
    assert MonitoringStatus.WARNING.severity < MonitoringStatus.ACCIDENT.severity
