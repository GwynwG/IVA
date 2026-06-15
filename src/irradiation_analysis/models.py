from enum import Enum


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
