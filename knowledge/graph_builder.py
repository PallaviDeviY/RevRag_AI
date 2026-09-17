"""App map construction with NetworkX.

Nodes are screens, edges are transitions. A ``MultiDiGraph`` is used so two
different actions between the same pair of screens remain two distinct edges.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

import networkx as nx

from .screen_manager import screen_label


def build_graph(
    screens: Sequence[Mapping[str, Any]], transitions: Sequence[Mapping[str, Any]]
) -> nx.MultiDiGraph:
    """Build the directed multigraph.

    Transitions whose source or target screen is unknown are skipped: we never
    invent a node to satisfy an edge.
    """
    graph = nx.MultiDiGraph()
    known: set[str] = set()

    for screen in sorted(screens, key=lambda s: s["screen_id"]):
        screen_id = screen["screen_id"]
        known.add(screen_id)
        graph.add_node(
            screen_id,
            label=screen_label(screen),
            package_name=screen.get("package_name"),
            activity=screen.get("activity"),
            element_count=int(screen.get("element_count") or 0),
            observation_count=int(screen.get("observation_count") or 0),
        )

    for transition in sorted(transitions, key=lambda t: t["transition_id"]):
        source = transition["source_screen_id"]
        target = transition["target_screen_id"]
        if source not in known or target not in known:
            continue
        graph.add_edge(
            source,
            target,
            key=transition["transition_id"],
            transition_id=transition["transition_id"],
            action_id=transition.get("action_id"),
            action_type=transition.get("action_type"),
            element_id=transition.get("element_id"),
        )
    return graph


def skipped_transitions(
    screens: Sequence[Mapping[str, Any]], transitions: Sequence[Mapping[str, Any]]
) -> list[str]:
    """Return warnings for edges we could not place on the graph."""
    known = {s["screen_id"] for s in screens}
    warnings: list[str] = []
    for transition in transitions:
        missing = [
            side
            for side, value in (
                ("source", transition["source_screen_id"]),
                ("target", transition["target_screen_id"]),
            )
            if value not in known
        ]
        if missing:
            warnings.append(
                f"Transition {transition['transition_id']} skipped: unknown "
                f"{'/'.join(missing)} screen."
            )
    return warnings


def graph_statistics(graph: nx.MultiDiGraph) -> dict[str, Any]:
    """Cheap, dashboard-friendly graph metrics."""
    isolated = sorted(nx.isolates(graph))
    return {
        "node_count": graph.number_of_nodes(),
        "edge_count": graph.number_of_edges(),
        "isolated_screens": isolated,
        "isolated_screen_count": len(isolated),
        "has_cycle": bool(list(nx.simple_cycles(graph))) if graph.number_of_nodes() else False,
        "weakly_connected_components": (
            nx.number_weakly_connected_components(graph) if graph.number_of_nodes() else 0
        ),
        "entry_points": sorted(n for n, d in graph.in_degree() if d == 0),
        "dead_ends": sorted(n for n, d in graph.out_degree() if d == 0),
    }


def to_json(graph: nx.MultiDiGraph) -> dict[str, Any]:
    """Export nodes/edges in the shape the dashboard expects.

    Ordering is deterministic so repeated calls produce byte-identical output.
    """
    nodes = [
        {
            "id": node,
            "label": data.get("label") or node,
            "package_name": data.get("package_name"),
            "activity": data.get("activity"),
            "element_count": data.get("element_count", 0),
            "observation_count": data.get("observation_count", 0),
        }
        for node, data in sorted(graph.nodes(data=True))
    ]
    edges = []
    for source, target, key, data in sorted(
        graph.edges(keys=True, data=True), key=lambda e: (e[2], e[0], e[1])
    ):
        action_type = data.get("action_type")
        edges.append(
            {
                "source": source,
                "target": target,
                "transition_id": key,
                "action_id": data.get("action_id"),
                "action_type": action_type,
                "element_id": data.get("element_id"),
                "label": action_type or "transition",
            }
        )
    return {"nodes": nodes, "edges": edges}
