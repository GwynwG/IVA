from __future__ import annotations

from dataclasses import dataclass

import plotly.graph_objects as go

from irradiation_analysis.models import MonitoringSnapshot, MonitoringStatus
from irradiation_analysis.snapshots import all_room_ids


STATUS_COLORS = {
    MonitoringStatus.NO_DATA: "#94a3b8",
    MonitoringStatus.NORMAL: "#22c55e",
    MonitoringStatus.WARNING: "#f59e0b",
    MonitoringStatus.ACCIDENT: "#dc2626",
}

STATUS_LABELS = {
    MonitoringStatus.NO_DATA: "无数据",
    MonitoringStatus.NORMAL: "正常",
    MonitoringStatus.WARNING: "预警",
    MonitoringStatus.ACCIDENT: "事故级",
}

LAYOUT_BY_ROOM = {
    "R01": "A",
    "R02": "B",
    "R03": "C",
    "R04": "A",
    "R05": "B",
    "R06": "C",
    "R07": "A",
    "R08": "B",
    "R09": "C",
    "R10": "A",
    "R11": "B",
    "R12": "C",
    "R13": "A",
    "R14": "B",
    "R15": "C",
    "R16": "A",
    "R17": "B",
    "R18": "C",
    "R19": "A",
    "R20": "B",
}

ROOM_WIDTH = 100.0
ROOM_HEIGHT = 80.0
ROOM_GAP = 10.0
MAIN_AISLE_HEIGHT = 18.0
FACILITY_WIDTH = ROOM_WIDTH * 5 + ROOM_GAP * 4

ROW4_Y = 0.0
AISLE_B_Y = ROW4_Y + ROOM_HEIGHT
ROW3_Y = AISLE_B_Y + MAIN_AISLE_HEIGHT
ROW2_Y = ROW3_Y + ROOM_HEIGHT
AISLE_A_Y = ROW2_Y + ROOM_HEIGHT
ROW1_Y = AISLE_A_Y + MAIN_AISLE_HEIGHT
FACILITY_HEIGHT = ROW1_Y + ROOM_HEIGHT

ROW_Y_BY_INDEX = {
    1: ROW1_Y,
    2: ROW2_Y,
    3: ROW3_Y,
    4: ROW4_Y,
}


@dataclass(frozen=True)
class Rect:
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0

    @property
    def center_x(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def center_y(self) -> float:
        return (self.y0 + self.y1) / 2

    def intersects(self, other: Rect) -> bool:
        return (
            self.x0 < other.x1
            and self.x1 > other.x0
            and self.y0 < other.y1
            and self.y1 > other.y0
        )


@dataclass(frozen=True)
class DevicePlacement:
    device_id: str
    x: float
    y: float
    footprint: Rect


@dataclass(frozen=True)
class RoomLayout:
    room_id: str
    layout_type: str
    bounds: Rect
    entrance_side: str
    devices: tuple[DevicePlacement, ...]
    paths: tuple[Rect, ...]
    metadata: dict[str, int]
    entrance_clearance: Rect
    row_by_device: dict[str, str]
    aisles: dict[str, Rect]


@dataclass(frozen=True)
class AisleLayout:
    label: str
    bounds: Rect


@dataclass(frozen=True)
class FacilityLayout:
    rooms: tuple[RoomLayout, ...]
    aisles: tuple[AisleLayout, AisleLayout]
    main_aisles: tuple[Rect, Rect]
    bounds: Rect


def build_facility_layout() -> FacilityLayout:
    rooms = tuple(_build_room(room_id) for room_id in all_room_ids())
    aisles = (
        AisleLayout(
            label="主过道 A",
            bounds=Rect(0.0, AISLE_A_Y, FACILITY_WIDTH, AISLE_A_Y + MAIN_AISLE_HEIGHT),
        ),
        AisleLayout(
            label="主过道 B",
            bounds=Rect(0.0, AISLE_B_Y, FACILITY_WIDTH, AISLE_B_Y + MAIN_AISLE_HEIGHT),
        ),
    )
    return FacilityLayout(
        rooms=rooms,
        aisles=aisles,
        main_aisles=tuple(aisle.bounds for aisle in aisles),
        bounds=Rect(0.0, 0.0, FACILITY_WIDTH, FACILITY_HEIGHT),
    )


def build_facility_figure(
    snapshot: MonitoringSnapshot, selected_device_id: str | None = None
) -> go.Figure:
    layout = build_facility_layout()
    fig = go.Figure()

    for aisle in layout.aisles:
        _add_rect_shape(fig, aisle.bounds, fillcolor="#dbeafe", line_color="#bfdbfe")
        fig.add_annotation(
            x=aisle.bounds.center_x,
            y=aisle.bounds.center_y,
            text=aisle.label,
            showarrow=False,
            font={"size": 11, "color": "#1e3a8a"},
        )

    xs: list[float] = []
    ys: list[float] = []
    labels: list[str] = []
    colors: list[str] = []
    line_colors: list[str] = []
    line_widths: list[int] = []
    hover_text: list[str] = []
    customdata: list[str] = []

    for room in layout.rooms:
        _add_rect_shape(fig, room.bounds, fillcolor="#f8fafc", line_color="#475569")
        for path in room.paths:
            _add_rect_shape(fig, path, fillcolor="#e2e8f0", line_color="#cbd5e1")

        fig.add_annotation(
            x=room.bounds.x0 + 6,
            y=room.bounds.y1 - 6,
            text=f"{room.room_id}（{room.layout_type}型）",
            showarrow=False,
            font={"size": 10, "color": "#0f172a"},
            xanchor="left",
        )
        _add_entrance_label(fig, room)

        for device in room.devices:
            status = snapshot.devices.get(device.device_id)
            device_status = (
                status.status if status is not None else MonitoringStatus.NO_DATA
            )
            selected = device.device_id == selected_device_id

            xs.append(device.x)
            ys.append(device.y)
            labels.append(device.device_id.split("-")[1])
            colors.append(STATUS_COLORS[device_status])
            line_colors.append("#0f172a" if selected else "#ffffff")
            line_widths.append(4 if selected else 1)
            hover_text.append(
                f"{device.device_id}<br>"
                f"房间: {room.room_id}<br>"
                f"布局: {room.layout_type}<br>"
                f"状态: {STATUS_LABELS[device_status]}"
            )
            customdata.append(device.device_id)

    fig.add_trace(
        go.Scatter(
            x=xs,
            y=ys,
            mode="markers+text",
            name="设备",
            text=labels,
            textposition="middle center",
            textfont={"size": 8, "color": "#0f172a"},
            customdata=customdata,
            hovertext=hover_text,
            hoverinfo="text",
            marker={
                "size": 18,
                "symbol": "circle",
                "color": colors,
                "line": {"color": line_colors, "width": line_widths},
            },
        )
    )

    fig.update_layout(
        title="V5设施布局",
        showlegend=False,
        plot_bgcolor="#ffffff",
        paper_bgcolor="#ffffff",
        margin={"l": 16, "r": 16, "t": 48, "b": 16},
        height=760,
        xaxis={
            "visible": False,
            "range": [layout.bounds.x0 - 8, layout.bounds.x1 + 8],
            "constrain": "domain",
        },
        yaxis={
            "visible": False,
            "range": [layout.bounds.y0 - 8, layout.bounds.y1 + 8],
            "scaleanchor": "x",
            "scaleratio": 1,
        },
    )
    return fig


def _build_room(room_id: str) -> RoomLayout:
    number = int(room_id[1:])
    row_index = (number - 1) // 5 + 1
    entrance_side = "bottom" if row_index in {1, 3} else "top"
    bounds = _room_bounds(number, row_index)
    layout_type = LAYOUT_BY_ROOM[room_id]

    if layout_type == "A":
        return _build_a_room(room_id, bounds, entrance_side)
    if layout_type == "B":
        return _build_b_room(room_id, bounds, entrance_side)
    return _build_c_room(room_id, bounds, entrance_side)


def _build_a_room(room_id: str, bounds: Rect, entrance_side: str) -> RoomLayout:
    devices: list[DevicePlacement] = []
    row_by_device: dict[str, str] = {}

    if entrance_side == "bottom":
        far_numbers = range(1, 7)
        entrance_numbers = range(7, 11)
        far_y = 72.0
        entrance_y = 22.0
        entrance_clearance = _local_rect(bounds, 42.0, 0.0, 58.0, 42.0)
    else:
        entrance_numbers = range(1, 5)
        far_numbers = range(5, 11)
        far_y = 28.0
        entrance_y = 78.0
        entrance_clearance = _local_rect(bounds, 42.0, 58.0, 58.0, 100.0)

    for device_number, x_percent in zip(
        far_numbers, [8.33, 25.0, 41.67, 58.33, 75.0, 91.67], strict=True
    ):
        device = _device(room_id, device_number, bounds, x_percent, far_y)
        devices.append(device)
        row_by_device[device.device_id] = "far"

    for device_number, x_percent in zip(
        entrance_numbers, [10.0, 30.0, 70.0, 90.0], strict=True
    ):
        device = _device(room_id, device_number, bounds, x_percent, entrance_y)
        devices.append(device)
        row_by_device[device.device_id] = "entrance"

    return RoomLayout(
        room_id=room_id,
        layout_type="A",
        bounds=bounds,
        entrance_side=entrance_side,
        devices=tuple(sorted(devices, key=lambda device: device.device_id)),
        paths=(
            entrance_clearance,
            _local_rect(bounds, 8.0, 44.0, 92.0, 56.0),
        ),
        metadata={"far": 6, "entrance": 4},
        entrance_clearance=entrance_clearance,
        row_by_device=row_by_device,
        aisles={"entrance": entrance_clearance},
    )


def _build_b_room(room_id: str, bounds: Rect, entrance_side: str) -> RoomLayout:
    devices: list[DevicePlacement] = []
    row_by_device: dict[str, str] = {}
    side_y_positions = [22.0, 38.0, 54.0, 70.0]
    far_end_y = 74.0
    entrance_clearance = _local_rect(bounds, 46.0, 0.0, 54.0, 62.0)

    if entrance_side == "top":
        side_y_positions = [_mirror_y(y) for y in side_y_positions]
        far_end_y = _mirror_y(far_end_y)
        entrance_clearance = _local_rect(bounds, 46.0, 38.0, 54.0, 100.0)

    for device_number, y_percent in zip(range(1, 5), side_y_positions, strict=True):
        device = _device(room_id, device_number, bounds, 16.0, y_percent)
        devices.append(device)
        row_by_device[device.device_id] = "left"

    for device_number, y_percent in zip(range(5, 9), side_y_positions, strict=True):
        device = _device(room_id, device_number, bounds, 84.0, y_percent)
        devices.append(device)
        row_by_device[device.device_id] = "right"

    for device_number, x_percent in zip(range(9, 11), [42.0, 58.0], strict=True):
        device = _device(room_id, device_number, bounds, x_percent, far_end_y)
        devices.append(device)
        row_by_device[device.device_id] = "far_end"

    return RoomLayout(
        room_id=room_id,
        layout_type="B",
        bounds=bounds,
        entrance_side=entrance_side,
        devices=tuple(sorted(devices, key=lambda device: device.device_id)),
        paths=(
            entrance_clearance,
            _local_rect(bounds, 26.0, 42.0, 74.0, 58.0),
        ),
        metadata={"left": 4, "right": 4, "far_end": 2},
        entrance_clearance=entrance_clearance,
        row_by_device=row_by_device,
        aisles={"entrance": entrance_clearance},
    )


def _build_c_room(room_id: str, bounds: Rect, entrance_side: str) -> RoomLayout:
    positions = [
        (30.0, 82.0),
        (70.0, 82.0),
        (12.0, 66.0),
        (12.0, 44.0),
        (88.0, 66.0),
        (88.0, 44.0),
        (15.0, 18.0),
        (30.0, 18.0),
        (70.0, 18.0),
        (85.0, 18.0),
    ]
    if entrance_side == "top":
        positions = [(x, _mirror_y(y)) for x, y in positions]

    devices = tuple(
        _device(room_id, device_number, bounds, x_percent, y_percent)
        for device_number, (x_percent, y_percent) in enumerate(positions, start=1)
    )

    if entrance_side == "bottom":
        radial_entrance = _local_rect(bounds, 44.0, 0.0, 56.0, 42.0)
    else:
        radial_entrance = _local_rect(bounds, 44.0, 58.0, 56.0, 100.0)

    center = _local_rect(bounds, 34.0, 34.0, 66.0, 66.0)
    paths = (
        _local_rect(bounds, 34.0, 34.0, 66.0, 42.0),
        _local_rect(bounds, 34.0, 58.0, 66.0, 66.0),
        _local_rect(bounds, 28.0, 42.0, 36.0, 58.0),
        _local_rect(bounds, 64.0, 42.0, 72.0, 58.0),
        radial_entrance,
    )
    return RoomLayout(
        room_id=room_id,
        layout_type="C",
        bounds=bounds,
        entrance_side=entrance_side,
        devices=devices,
        paths=paths,
        metadata={"perimeter": 10},
        entrance_clearance=radial_entrance,
        row_by_device={device.device_id: "perimeter" for device in devices},
        aisles={"center": center, "radial_entrance": radial_entrance},
    )


def _room_bounds(number: int, row_index: int) -> Rect:
    column_index = (number - 1) % 5
    x0 = column_index * (ROOM_WIDTH + ROOM_GAP)
    y0 = ROW_Y_BY_INDEX[row_index]
    return Rect(x0, y0, x0 + ROOM_WIDTH, y0 + ROOM_HEIGHT)


def _device(
    room_id: str,
    device_number: int,
    bounds: Rect,
    x_percent: float,
    y_percent: float,
) -> DevicePlacement:
    x, y = _local_point(bounds, x_percent, y_percent)
    half_width = bounds.width * 0.035
    half_height = bounds.height * 0.045
    return DevicePlacement(
        device_id=f"{room_id}-D{device_number:02d}",
        x=x,
        y=y,
        footprint=Rect(x - half_width, y - half_height, x + half_width, y + half_height),
    )


def _local_point(bounds: Rect, x_percent: float, y_percent: float) -> tuple[float, float]:
    return (
        bounds.x0 + bounds.width * x_percent / 100.0,
        bounds.y0 + bounds.height * y_percent / 100.0,
    )


def _local_rect(
    bounds: Rect,
    x0_percent: float,
    y0_percent: float,
    x1_percent: float,
    y1_percent: float,
) -> Rect:
    x0, y0 = _local_point(bounds, x0_percent, y0_percent)
    x1, y1 = _local_point(bounds, x1_percent, y1_percent)
    return Rect(x0, y0, x1, y1)


def _mirror_y(y_percent: float) -> float:
    return 100.0 - y_percent


def _add_rect_shape(fig, rect: Rect, fillcolor: str, line_color: str) -> None:
    fig.add_shape(
        type="rect",
        x0=rect.x0,
        y0=rect.y0,
        x1=rect.x1,
        y1=rect.y1,
        fillcolor=fillcolor,
        opacity=1.0,
        line={"color": line_color, "width": 1},
        layer="below",
    )


def _add_entrance_label(fig, room: RoomLayout) -> None:
    y = room.bounds.y0 + 2 if room.entrance_side == "bottom" else room.bounds.y1 - 2
    fig.add_annotation(
        x=room.bounds.center_x,
        y=y,
        text="入口",
        showarrow=False,
        font={"size": 8, "color": "#334155"},
    )
