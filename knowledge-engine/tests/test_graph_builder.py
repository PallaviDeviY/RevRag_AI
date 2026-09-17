"""App map construction."""

from __future__ import annotations

from knowledge.graph_builder import build_graph, graph_statistics, skipped_transitions, to_json


def _screens(*ids):
    return [
        {
            "screen_id": sid,
            "activity": f"com.example.app.{sid}",
            "package_name": "com.example.app",
            "element_count": 0,
            "observation_count": 1,
            "elements": [],
        }
        for sid in ids
    ]


def _transition(index, source, target, action_type="tap"):
    return {
        "transition_id": f"transition_{index:06d}",
        "source_screen_id": source,
        "target_screen_id": target,
        "action_id": f"action_{index:06d}",
        "action_type": action_type,
        "element_id": f"element_{index:06d}",
    }


def test_nodes_and_edges():
    graph = build_graph(
        _screens("screen_000001", "screen_000002"),
        [_transition(1, "screen_000001", "screen_000002")],
    )
    assert graph.number_of_nodes() == 2
    assert graph.number_of_edges() == 1


def test_isolated_screen_is_kept():
    graph = build_graph(_screens("screen_000001", "screen_000002"), [])
    stats = graph_statistics(graph)
    assert stats["isolated_screen_count"] == 2
    assert stats["edge_count"] == 0


def test_unknown_target_is_skipped():
    screens = _screens("screen_000001")
    transitions = [_transition(1, "screen_000001", "screen_000099")]
    graph = build_graph(screens, transitions)
    assert graph.number_of_edges() == 0
    assert "screen_000099" not in graph
    warnings = skipped_transitions(screens, transitions)
    assert len(warnings) == 1 and "target" in warnings[0]


def test_multiple_actions_between_same_screens():
    graph = build_graph(
        _screens("screen_000001", "screen_000002"),
        [
            _transition(1, "screen_000001", "screen_000002", "tap"),
            _transition(2, "screen_000001", "screen_000002", "swipe"),
        ],
    )
    assert graph.number_of_edges() == 2
    assert {e["action_type"] for e in to_json(graph)["edges"]} == {"tap", "swipe"}


def test_cycle_is_detected():
    graph = build_graph(
        _screens("screen_000001", "screen_000002"),
        [
            _transition(1, "screen_000001", "screen_000002"),
            _transition(2, "screen_000002", "screen_000001", "back"),
        ],
    )
    assert graph_statistics(graph)["has_cycle"] is True


def test_export_is_deterministic():
    screens = _screens("screen_000002", "screen_000001")
    transitions = [_transition(2, "screen_000001", "screen_000002")]
    first = to_json(build_graph(screens, transitions))
    second = to_json(build_graph(list(reversed(screens)), transitions))
    assert first == second
    assert [n["id"] for n in first["nodes"]] == ["screen_000001", "screen_000002"]


def test_empty_graph_statistics():
    stats = graph_statistics(build_graph([], []))
    assert stats["node_count"] == 0
    assert stats["has_cycle"] is False
