from datetime import datetime
from typing import get_type_hints

import plotly.graph_objects as go

from irradiation_analysis.layout import (
    build_facility_figure,
    build_facility_layout,
)
from irradiation_analysis.models import (
    DeviceSnapshot,
    MonitoringSnapshot,
    MonitoringStatus,
)
from irradiation_analysis.snapshots import all_device_ids


EXPECTED_LAYOUT_BY_ROOM = {
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

EXPECTED_STATUS_COLORS = {
    MonitoringStatus.NO_DATA: "#94a3b8",
    MonitoringStatus.NORMAL: "#22c55e",
    MonitoringStatus.WARNING: "#f59e0b",
    MonitoringStatus.ACCIDENT: "#dc2626",
}


def room_layout(layout, room_id):
    return next(room for room in layout.rooms if room.room_id == room_id)


def count_row(room, row_name):
    return sum(1 for row in room.row_by_device.values() if row == row_name)


def no_device_intersects(room, rect):
    return all(not device.footprint.intersects(rect) for device in room.devices)


def sample_snapshot(status_by_device=None):
    status_by_device = status_by_device or {}
    devices = {}
    for device_id in all_device_ids():
        status = status_by_device.get(device_id, MonitoringStatus.NO_DATA)
        devices[device_id] = DeviceSnapshot(
            device_id=device_id,
            room_id=device_id.split("-")[0],
            status=status,
            latest_by_series={},
            most_severe_record=None,
        )

    room_statuses = {
        f"R{room:02d}": max(
            (
                devices[f"R{room:02d}-D{device:02d}"].status
                for device in range(1, 11)
            ),
            key=lambda status: status.severity,
        )
        for room in range(1, 21)
    }
    return MonitoringSnapshot(
        selected_at=datetime(2026, 6, 16),
        devices=devices,
        room_statuses=room_statuses,
    )


def test_facility_layout_has_approved_room_sequence_and_main_aisles():
    layout = build_facility_layout()

    assert [room.room_id for room in layout.rooms] == [
        f"R{room:02d}" for room in range(1, 21)
    ]
    assert [aisle.label for aisle in layout.aisles] == ["主过道 A", "主过道 B"]
    assert len(layout.main_aisles) == 2

    all_placed_ids = [
        device.device_id for room in layout.rooms for device in room.devices
    ]
    assert len(all_placed_ids) == 200
    assert sorted(all_placed_ids) == all_device_ids()

    first_row = [room_layout(layout, f"R{room:02d}") for room in range(1, 6)]
    second_row = [room_layout(layout, f"R{room:02d}") for room in range(6, 11)]
    third_row = [room_layout(layout, f"R{room:02d}") for room in range(11, 16)]
    fourth_row = [room_layout(layout, f"R{room:02d}") for room in range(16, 21)]

    assert {room.entrance_side for room in first_row} == {"bottom"}
    assert {room.entrance_side for room in second_row} == {"top"}
    assert {room.entrance_side for room in third_row} == {"bottom"}
    assert {room.entrance_side for room in fourth_row} == {"top"}

    assert (
        first_row[0].bounds.y0
        > second_row[0].bounds.y0
        > third_row[0].bounds.y0
        > fourth_row[0].bounds.y0
    )
    assert min(room.bounds.y0 for room in first_row) >= layout.main_aisles[0].y1
    assert max(room.bounds.y1 for room in second_row) <= layout.main_aisles[0].y0
    assert min(room.bounds.y0 for room in third_row) >= layout.main_aisles[1].y1
    assert max(room.bounds.y1 for room in fourth_row) <= layout.main_aisles[1].y0


def test_layout_type_assignment_matches_v5_specification():
    layout = build_facility_layout()

    assert {
        room.room_id: room.layout_type for room in layout.rooms
    } == EXPECTED_LAYOUT_BY_ROOM


def test_a_layout_keeps_entry_axis_clear_with_six_far_and_four_entry_devices():
    layout = build_facility_layout()

    for room_id, layout_type in EXPECTED_LAYOUT_BY_ROOM.items():
        if layout_type != "A":
            continue
        room = room_layout(layout, room_id)

        assert count_row(room, "far") == 6
        assert count_row(room, "entrance") == 4
        assert no_device_intersects(room, room.entrance_clearance)
        assert room.metadata == {"far": 6, "entrance": 4}


def test_b_layout_uses_side_banks_and_far_end_pair():
    layout = build_facility_layout()

    for room_id, layout_type in EXPECTED_LAYOUT_BY_ROOM.items():
        if layout_type != "B":
            continue
        room = room_layout(layout, room_id)

        assert room.metadata == {"left": 4, "right": 4, "far_end": 2}
        assert count_row(room, "left") == 4
        assert count_row(room, "right") == 4
        assert count_row(room, "far_end") == 2
        assert no_device_intersects(room, room.entrance_clearance)


def test_c_layout_keeps_center_ring_and_radial_entrance_clear():
    layout = build_facility_layout()

    for room_id, layout_type in EXPECTED_LAYOUT_BY_ROOM.items():
        if layout_type != "C":
            continue
        room = room_layout(layout, room_id)

        assert len(room.devices) == 10
        assert room.metadata == {"perimeter": 10}
        assert "center" in room.aisles
        assert "radial_entrance" in room.aisles
        assert len(room.paths) >= 5
        assert no_device_intersects(room, room.entrance_clearance)
        assert no_device_intersects(room, room.aisles["center"])
        assert no_device_intersects(room, room.aisles["radial_entrance"])


def test_facility_figure_renders_status_colors_and_selected_outline():
    device_statuses = {
        "R01-D01": MonitoringStatus.ACCIDENT,
        "R01-D02": MonitoringStatus.WARNING,
        "R01-D03": MonitoringStatus.NORMAL,
        "R01-D04": MonitoringStatus.NO_DATA,
    }
    snapshot = sample_snapshot(device_statuses)

    fig = build_facility_figure(snapshot, selected_device_id="R01-D01")

    assert get_type_hints(build_facility_figure)["return"] is go.Figure
    assert isinstance(fig, go.Figure)
    assert len(fig.layout.shapes) >= 20 + 2
    assert fig.layout.title.text == "V5设施布局"

    annotation_texts = [annotation.text for annotation in fig.layout.annotations]
    assert annotation_texts.count("入口") == 20
    assert "主过道 A" in annotation_texts
    assert "主过道 B" in annotation_texts

    device_trace = next(trace for trace in fig.data if trace.name == "设备")
    selected_index = list(device_trace.customdata).index("R01-D01")

    for device_id, status in device_statuses.items():
        index = list(device_trace.customdata).index(device_id)
        assert device_trace.marker.color[index] == EXPECTED_STATUS_COLORS[status]

    assert device_trace.marker.line.width[selected_index] > max(
        width
        for index, width in enumerate(device_trace.marker.line.width)
        if index != selected_index
    )
    assert "R01-D01" in device_trace.hovertext[selected_index]
    assert "房间: R01" in device_trace.hovertext[selected_index]
    assert "布局: A" in device_trace.hovertext[selected_index]
    assert "状态:" in device_trace.hovertext[selected_index]
    assert "Room:" not in device_trace.hovertext[selected_index]
    assert "Layout:" not in device_trace.hovertext[selected_index]
    assert "Status:" not in device_trace.hovertext[selected_index]
