from app import id_to_row_col, parse_point_ids, parse_report_text, row_col_to_id
from app import (
    apply_selection_action,
    extract_selected_ids,
    id_to_row_col,
    parse_point_ids,
    parse_report_text,
    row_col_to_id,
from app import (
    apply_pollution_action,
    apply_selection_action,
    build_analytics_snapshot,
    build_centroid_window_points,
    build_frequency_map,
    build_cross_report_summary,
    build_playback_labels,
    build_point_history_stats,
    build_report_history,
    build_report_switch_options,
    build_risk_candidates,
    build_source_diffusion_figure,
    build_source_candidates,
    build_plotly_grid,
    default_analysis_config,
    default_obstacle_ids,
    extract_date_from_text,
    extract_declared_floor_count,
    extract_selected_ids,
    extract_task_end_date,
    forecast_next_pollution_count,
    has_selection_payload,
    id_to_row_col,
    merge_selected_ids,
    parse_point_ids,
    parse_report_text,
    recommend_centroid_smoothing_window,
    row_col_to_id,
    rows_to_csv_bytes,
)


def test_parse_report_text_sections_and_deduplicate():
    text = """
辐射超标地面点位ID
130
131
748
130
辐射超标手套孔名称
手套孔1#
手套孔2#
手套孔1#
"""
    result = parse_report_text(text)
    assert result.floor_ids == [130, 131, 748]
    assert result.glove_names == ["手套孔1#", "手套孔2#"]


def test_parse_report_text_table_tokens_do_not_take_measurement_as_id():
    text = """
辐射超标
地面
点位ID
α辐射测量值
312
0
.12
313
0
.123
辐射超标
手套孔
名称
手套孔
1
#
"""
    result = parse_report_text(text)
    assert result.floor_ids == [312, 313]


def test_parse_report_text_handles_split_id_tokens_in_table():
    text = """
辐射超标
地面
点位ID
α辐射测量值
53
6
0
.12
566
0
.12
辐射超标
手套孔
名称
"""
    result = parse_report_text(text)
    assert result.floor_ids == [536, 566]


def test_extract_declared_floor_count_from_report_summary():
    text = """
探测地面网格数：740
辐射超标地面网格个数：
3
探测手套孔数：20
"""
    assert extract_declared_floor_count(text) == 3


def test_rule_prefers_actual_id_count_when_declared_count_mismatches():
    text = """
辐射超标地面网格个数：5
辐射超标地面点位ID
130
131
748
辐射超标手套孔名称
手套孔1#
"""
    result = parse_report_text(text)
    assert result.floor_ids == [130, 131, 748]
    assert result.declared_floor_count == 5
    assert result.floor_count_mismatch


def test_id_mapping_roundtrip():
    assert id_to_row_col(1) == (1, 1)
    assert id_to_row_col(31) == (1, 2)
    assert id_to_row_col(60) == (30, 2)
    assert row_col_to_id(30, 28) == 840


def test_parse_point_ids():
    ids = parse_point_ids("1, 2 2\n841\n0\n840")
    assert ids == [1, 2, 840]


def test_recommend_centroid_smoothing_window_scales_with_history_length():
    assert recommend_centroid_smoothing_window(4, 10) == 1
    assert recommend_centroid_smoothing_window(10, 10) == 2
    assert recommend_centroid_smoothing_window(20, 20) == 4


def test_build_centroid_window_points_snaps_to_real_polluted_point():
    day1_ids = {row_col_to_id(10, 10), row_col_to_id(10, 11)}
    day2_ids = {row_col_to_id(10, 12), row_col_to_id(11, 12)}
    day3_ids = {row_col_to_id(20, 20)}

    history = [
        {
            "switch_label": "20250101",
            "date": "20250101",
            "centroid": (10.0, 10.5),
            "polluted_ids": day1_ids,
            "polluted_count": len(day1_ids),
            "cluster_count": 1,
        },
        {
            "switch_label": "20250102",
            "date": "20250102",
            "centroid": (10.5, 12.0),
            "polluted_ids": day2_ids,
            "polluted_count": len(day2_ids),
            "cluster_count": 1,
        },
        {
            "switch_label": "20250103",
            "date": "20250103",
            "centroid": (20.0, 20.0),
            "polluted_ids": day3_ids,
            "polluted_count": len(day3_ids),
            "cluster_count": 1,
        },
    ]

    points = build_centroid_window_points(history, window_size=2)
    assert len(points) == 2
    assert points[0]["point_id"] in day2_ids
    assert points[0]["period_label"] == "2025-01-01 ~ 2025-01-02"
    assert points[1]["point_id"] == row_col_to_id(20, 20)


def test_apply_selection_action():
    obstacle, pending = apply_selection_action("set_obstacle", {1, 2}, {5}, {2, 9})
    assert obstacle == {1, 2, 5}
    assert pending == {9}

    obstacle, pending = apply_selection_action("set_pending", {5, 9}, obstacle, pending)
    assert obstacle == {1, 2}
    assert pending == {5, 9}

    obstacle, pending = apply_selection_action("clear", {1, 9}, obstacle, pending)
    assert obstacle == {2}
    assert pending == {5}


def test_apply_pollution_action():
    polluted = apply_pollution_action("set_polluted", {1, 2}, {5})
    assert polluted == {1, 2, 5}

    polluted = apply_pollution_action("set_clean", {2, 5}, polluted)
    assert polluted == {1}


def test_extract_selected_ids():
    event = {"selection": {"points": [{"customdata": 7}, {"customdata": [8]}]}}
    assert extract_selected_ids(event) == {7, 8}


def test_merge_selected_ids_accumulates_across_multiple_drags():
    assert merge_selected_ids({7, 8}, {8, 9}) == {7, 8, 9}


def test_has_selection_payload():
    assert has_selection_payload({"selection": {"points": [{"customdata": 7}]}})
    assert has_selection_payload({"selection": {"points": []}})
    assert not has_selection_payload({})


def test_default_obstacle_ids_matches_layout():
    obstacle_ids = default_obstacle_ids()

    assert 67 in obstacle_ids
    assert 51 in obstacle_ids
    assert 89 in obstacle_ids
    assert 50 not in obstacle_ids
    assert 59 not in obstacle_ids
    assert 681 not in obstacle_ids


def test_build_plotly_grid_marks_highlight_ids_red():
    fig = build_plotly_grid({131}, set(), set())
    trace = fig.data[0]
    ids = list(trace.customdata)
    index = ids.index(131)

    assert trace.marker.color[index] == "#ff4d4f"
    assert trace.textfont.color[index] == "#ffffff"


def test_build_plotly_grid_prioritizes_staged_selection_color():
    fig = build_plotly_grid({131}, set(), set(), {131})
    trace = fig.data[0]
    ids = list(trace.customdata)
    index = ids.index(131)

    assert trace.marker.color[index] == "#2e6ea9"
    assert trace.textfont.color[index] == "#ffffff"


def test_extract_date_from_text_supports_multiple_formats():
    assert extract_date_from_text("report_2026-03-18.txt") == "20260318"
    assert extract_date_from_text("report_20260319.docx") == "20260319"
    assert extract_date_from_text("report_2026年3月7日.pdf") == "20260307"


def test_extract_task_end_date_prefers_task_end_field():
    text = """
任务开始时间：2025-07-01 02:03:04
任务结束时间：2025-07-02 05:06:07
"""
    assert extract_task_end_date(text) == "20250702"


def test_extract_task_end_date_handles_split_table_tokens():
    text = """
任务
结束
时间
：
2025-0
7
-0
1
 05
:
06:07
"""
    assert extract_task_end_date(text) == "20250701"


def test_extract_date_from_text_handles_split_digits():
    text = "任务结束时间：2025-0\n9\n-0\n2 05:06:07"
    assert extract_date_from_text(text) == "20250902"


def test_build_report_switch_options_sorts_by_date_and_handles_duplicates():
    report_store = {
        "k1": {"date": "20260318", "file_name": "b.txt"},
        "k2": {"date": "20260317", "file_name": "x.txt"},
        "k3": {"date": "20260318", "file_name": "a.txt"},
        "k4": {"date": None, "file_name": "z.txt"},
    }

    options = build_report_switch_options(["k1", "k2", "k3", "k4"], report_store)

    assert options == [
        ("k2", "20260317"),
        ("k3", "20260318 (1)"),
        ("k1", "20260318 (2)"),
        ("k4", "未识别日期"),
    ]


def test_build_cross_report_summary_tracks_add_remove_against_previous():
    report_store = {
        "k1": {
            "date": "20260317",
            "file_name": "a.txt",
            "report_text": "辐射超标地面点位ID\n131\n132\n",
        },
        "k2": {
            "date": "20260318",
            "file_name": "b.txt",
            "report_text": "辐射超标地面点位ID\n132\n140\n",
        },
    }
    options = [("k1", "20260317"), ("k2", "20260318")]

    rows = build_cross_report_summary(options, report_store)

    assert rows[0]["较前一日变化"] == "基线"
    assert rows[0]["新增点位数"] == 2
    assert rows[0]["减少点位数"] == 0
    assert rows[1]["较前一日变化"] == "+0"
    assert rows[1]["新增点位数"] == 1
    assert rows[1]["减少点位数"] == 1


def test_build_cross_report_summary_prefers_manual_polluted_ids():
    report_store = {
        "k1": {
            "date": "20260317",
            "file_name": "a.txt",
            "report_text": "辐射超标地面点位ID\n131\n132\n",
            "polluted_ids": {131, 140},
        }
    }

    rows = build_cross_report_summary([("k1", "20260317")], report_store)

    assert rows[0]["污染地面点位数"] == 2
    assert rows[0]["新增点位ID(预览)"] == "131、140"


def test_build_report_history_tracks_counts_and_centroid():
    report_store = {
        "k1": {
            "date": "20260317",
            "file_name": "a.txt",
            "report_text": "辐射超标地面点位ID\n31\n61\n",
            "polluted_ids": {31, 61},
            "obstacle_ids": set(),
            "pending_ids": set(),
        },
        "k2": {
            "date": "20260318",
            "file_name": "b.txt",
            "report_text": "辐射超标地面点位ID\n61\n91\n121\n",
            "polluted_ids": {61, 91, 121},
            "obstacle_ids": set(),
            "pending_ids": set(),
        },
    }

    history = build_report_history([("k1", "20260317"), ("k2", "20260318")], report_store)

    assert history[0]["polluted_count"] == 2
    assert history[1]["added_ids"] == {91, 121}
    assert history[1]["removed_ids"] == {31}
    assert history[1]["centroid"] == (1.0, 4.0)


def test_build_playback_labels_and_snapshot_clip_history():
    report_store = {
        "k1": {
            "date": "20260317",
            "file_name": "a.txt",
            "report_text": "辐射超标地面点位ID\n31\n61\n",
            "polluted_ids": {31, 61},
            "obstacle_ids": set(),
            "pending_ids": set(),
        },
        "k2": {
            "date": "20260318",
            "file_name": "b.txt",
            "report_text": "辐射超标地面点位ID\n61\n91\n121\n",
            "polluted_ids": {61, 91, 121},
            "obstacle_ids": set(),
            "pending_ids": set(),
        },
    }
    history = build_report_history([("k1", "20260317"), ("k2", "20260318")], report_store)

    assert build_playback_labels(history) == ["第 1 期 | 20260317", "第 2 期 | 20260318"]

    snapshot = build_analytics_snapshot(history, 0)

    assert len(snapshot["history"]) == 1
    assert snapshot["latest"]["date"] == "20260317"
    assert snapshot["forecast_count"] == 2


def test_build_point_history_stats_and_frequency_map():
    history = [
        {"polluted_ids": {131, 132}},
        {"polluted_ids": {132, 140}},
        {"polluted_ids": {132}},
    ]

    stats = build_point_history_stats(history)
    frequency_map = build_frequency_map(history)

    assert stats[132]["occurrences"] == 3
    assert stats[132]["max_streak"] == 3
    assert stats[132]["current_streak"] == 3
    assert frequency_map[132] == 3
    assert frequency_map[140] == 1


def test_forecast_next_pollution_count_follows_recent_trend():
    history = [
        {"polluted_count": 2},
        {"polluted_count": 4},
        {"polluted_count": 5},
        {"polluted_count": 7},
    ]

    assert forecast_next_pollution_count(history) >= 6


def test_forecast_next_pollution_count_respects_config():
    history = [
        {"polluted_count": 2},
        {"polluted_count": 4},
        {"polluted_count": 5},
        {"polluted_count": 7},
    ]
    config = default_analysis_config()
    config["forecast_smooth_weight"] = 0.0
    config["forecast_trend_weight"] = 1.0
    config["forecast_drift_scale"] = 1.5

    assert forecast_next_pollution_count(history, config) >= 8


def test_build_risk_candidates_prioritizes_current_hotspot():
    history = [
        {
            "polluted_ids": {131, 132},
            "obstacle_ids": set(),
            "pending_ids": set(),
        },
        {
            "polluted_ids": {131, 132, 162},
            "obstacle_ids": set(),
            "pending_ids": set(),
        },
        {
            "polluted_ids": {131, 132, 162},
            "obstacle_ids": set(),
            "pending_ids": set(),
        },
    ]

    candidates = build_risk_candidates(history)

    assert candidates[0]["point_id"] in {131, 132, 162}
    assert candidates[0]["score"] >= candidates[-1]["score"]


def test_build_risk_candidates_respects_threshold_config():
    history = [
        {
            "polluted_ids": {131, 132},
            "obstacle_ids": set(),
            "pending_ids": set(),
        },
        {
            "polluted_ids": {131, 132, 162},
            "obstacle_ids": set(),
            "pending_ids": set(),
        },
        {
            "polluted_ids": {131, 132, 162},
            "obstacle_ids": set(),
            "pending_ids": set(),
        },
    ]
    config = default_analysis_config()
    config["risk_threshold"] = 0.95

    assert build_risk_candidates(history, config) == []


def test_build_source_candidates_prefers_early_and_persistent_points():
    history = [
        {"polluted_ids": {131}},
        {"polluted_ids": {131, 132}},
        {"polluted_ids": {131, 132, 162}},
    ]

    candidates = build_source_candidates(history)

    assert candidates[0]["point_id"] == 131
    assert candidates[0]["first_seen_index"] == 0


def test_build_source_candidates_respects_weight_config():
    history = [
        {"polluted_ids": {131}},
        {"polluted_ids": {131, 132}},
        {"polluted_ids": {131, 132, 162}},
    ]
    config = default_analysis_config()
    config["source_weight_first"] = 1.0
    config["source_weight_persistence"] = 0.0
    config["source_weight_spread"] = 0.0
    config["source_weight_frequency"] = 0.0
    config["source_weight_centroid"] = 0.0

    candidates = build_source_candidates(history, config)

    assert candidates[0]["point_id"] == 131


def test_build_source_diffusion_figure_from_snapshot():
    report_store = {
        "k1": {
            "date": "20260317",
            "file_name": "a.txt",
            "report_text": "辐射超标地面点位ID\n131\n",
            "polluted_ids": {131},
            "obstacle_ids": set(),
            "pending_ids": set(),
        },
        "k2": {
            "date": "20260318",
            "file_name": "b.txt",
            "report_text": "辐射超标地面点位ID\n131\n132\n",
            "polluted_ids": {131, 132},
            "obstacle_ids": set(),
            "pending_ids": set(),
        },
        "k3": {
            "date": "20260319",
            "file_name": "c.txt",
            "report_text": "辐射超标地面点位ID\n131\n132\n162\n",
            "polluted_ids": {131, 132, 162},
            "obstacle_ids": set(),
            "pending_ids": set(),
        },
    }
    history = build_report_history(
        [("k1", "20260317"), ("k2", "20260318"), ("k3", "20260319")],
        report_store,
    )
    snapshot = build_analytics_snapshot(history, 2)

    fig = build_source_diffusion_figure(snapshot)

    assert fig.layout.title.text == "疑似源点扩散链路回放"
    assert len(fig.data) >= 1


def test_rows_to_csv_bytes_exports_header_and_values():
    csv_bytes = rows_to_csv_bytes(
        [
            {"日期": "20260319", "污染点位数": 3},
            {"日期": "20260320", "污染点位数": 5},
        ]
    )
    csv_text = csv_bytes.decode("utf-8-sig")

    assert "日期,污染点位数" in csv_text
    assert "20260319,3" in csv_text
    assert "20260320,5" in csv_text
