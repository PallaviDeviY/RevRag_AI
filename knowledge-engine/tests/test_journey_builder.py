"""Journey discovery."""

from __future__ import annotations

from knowledge.graph_builder import build_graph
from knowledge.journey_builder import discover_journeys, element_text_index, shortest_journey


def _screens(*ids):
    return [
        {
            "screen_id": sid,
            "activity": None,
            "element_count": 0,
            "observation_count": 1,
            "elements": [],
        }
        for sid in ids
    ]


def _t(index, source, target):
    return {
        "transition_id": f"transition_{index:06d}",
        "source_screen_id": source,
        "target_screen_id": target,
        "action_id": f"action_{index:06d}",
        "action_type": "tap",
        "element_id": f"element_{index:06d}",
    }


def _chain(count):
    ids = [f"screen_{i:06d}" for i in range(1, count + 1)]
    transitions = [_t(i, ids[i - 1], ids[i]) for i in range(1, count)]
    return build_graph(_screens(*ids), transitions)


def test_linear_paths_are_found():
    journeys = discover_journeys(_chain(3))
    ends = {j["end_screen_id"] for j in journeys}
    assert ends == {"screen_000002", "screen_000003"}
    longest = max(journeys, key=lambda j: j["length"])
    assert longest["screen_ids"] == ["screen_000001", "screen_000002", "screen_000003"]
    assert longest["action_ids"] == ["action_000001", "action_000002"]


def test_no_journeys_without_edges():
    assert discover_journeys(build_graph(_screens("screen_000001"), [])) == []


def test_empty_graph():
    assert discover_journeys(build_graph([], [])) == []


def test_max_length_is_respected():
    journeys = discover_journeys(_chain(6), max_length=2)
    assert max(j["length"] for j in journeys) == 2


def test_cycle_does_not_hang():
    graph = build_graph(
        _screens("screen_000001", "screen_000002", "screen_000003"),
        [
            _t(1, "screen_000001", "screen_000002"),
            _t(2, "screen_000002", "screen_000003"),
            _t(3, "screen_000003", "screen_000001"),
        ],
    )
    journeys = discover_journeys(graph, max_length=4)
    assert journeys  # a fully cyclic component still yields journeys
    for journey in journeys:
        assert len(journey["screen_ids"]) == len(set(journey["screen_ids"]))


def test_max_journeys_cap():
    journeys = discover_journeys(_chain(20), max_length=20, max_journeys=3)
    assert len(journeys) <= 3


def test_names_are_unique():
    journeys = discover_journeys(_chain(4))
    names = [j["name"] for j in journeys]
    assert len(names) == len(set(names))


def test_semantic_name_from_element_text():
    graph = build_graph(
        _screens("screen_000001", "screen_000002"), [_t(1, "screen_000001", "screen_000002")]
    )
    journeys = discover_journeys(graph, element_text_by_id={"element_000001": "Login"})
    assert journeys[0]["name"] == "Login Journey"


def test_journeys_are_not_marked_user_confirmed():
    journeys = discover_journeys(_chain(2))
    assert journeys[0]["metadata"]["user_confirmed"] is False


def test_shortest_journey_helper():
    graph = _chain(3)
    assert shortest_journey(graph, "screen_000001", "screen_000003") == [
        "screen_000001",
        "screen_000002",
        "screen_000003",
    ]
    assert shortest_journey(graph, "screen_000003", "screen_000001") is None
    assert shortest_journey(graph, "screen_000001", "screen_999999") is None


def test_element_text_index():
    index = element_text_index(
        [{"elements": [{"element_id": "e1", "text": "", "content_description": "Back"}]}]
    )
    assert index["e1"] == "Back"
