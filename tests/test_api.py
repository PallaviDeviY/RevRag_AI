"""End-to-end API tests using FastAPI's TestClient (httpx under the hood)."""

from __future__ import annotations

import copy

SCAN = "scan_000001"


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["service"] == "knowledge-engine"


def test_post_observation(client, observation):
    response = client.post("/observations", json=observation)
    assert response.status_code == 200
    body = response.json()
    assert body["observation_id"] == "obs_000001"
    assert body["screen"]["screen_id"] == "screen_000001"
    assert body["screen"]["fingerprint"]
    assert body["created"] is True


def test_repeat_observation_reuses_screen(client, observation):
    client.post("/observations", json=observation)
    repeat = copy.deepcopy(observation)
    repeat["observation_id"] = "obs_000002"
    body = client.post("/observations", json=repeat).json()
    assert body["created"] is False
    assert body["screen"]["observation_count"] == 2


def test_invalid_observation_rejected(client, observation):
    observation["elements"][0]["bounds"]["right"] = 0
    assert client.post("/observations", json=observation).status_code == 422
    assert client.post("/observations", json={}).status_code == 422


def test_duplicate_observation_id_conflict(client, observation):
    client.post("/observations", json=observation)
    response = client.post("/observations", json=observation)
    assert response.status_code == 409


def test_post_action(client, action):
    response = client.post("/actions", json=action)
    assert response.status_code == 200
    assert response.json()["action_id"] == "action_000001"


def test_unknown_action_type_warns_but_stores(client, action):
    action["action_type"] = "pinch_zoom"
    body = client.post("/actions", json=action).json()
    assert body["stored"] is True
    assert any("pinch_zoom" in w for w in body["warnings"])


def test_action_with_unknown_target_does_not_invent_screen(client, action, observation):
    client.post("/observations", json=observation)
    action["source_screen_id"] = "screen_000001"
    action["target_screen_id"] = "screen_000099"
    body = client.post("/actions", json=action).json()
    assert any("unknown screen" in w.lower() for w in body["warnings"])
    assert client.get("/app-map").json()["edges"] == []


def test_transition_endpoint(client, observation, second_observation, action):
    client.post("/observations", json=observation)
    client.post("/observations", json=second_observation)
    client.post("/actions", json=action)
    response = client.post(
        "/transitions",
        json={
            "source_screen_id": "screen_000001",
            "target_screen_id": "screen_000002",
            "action_id": "action_000001",
            "action_type": "tap",
            "element_id": "element_000001",
        },
    )
    assert response.status_code == 200
    assert response.json()["transition_id"] == "transition_000001"


def test_transition_with_unknown_screen_404(client, observation):
    client.post("/observations", json=observation)
    response = client.post(
        "/transitions",
        json={"source_screen_id": "screen_000001", "target_screen_id": "screen_000099"},
    )
    assert response.status_code == 404


def test_get_screens(client, observation, second_observation):
    client.post("/observations", json=observation)
    client.post("/observations", json=second_observation)
    screens = client.get("/screens").json()
    assert [s["screen_id"] for s in screens] == ["screen_000001", "screen_000002"]


def test_get_one_screen(client, observation):
    client.post("/observations", json=observation)
    assert client.get("/screens/screen_000001").status_code == 200
    assert client.get("/screens/screen_000404").status_code == 404


def test_app_map(client, observation, second_observation):
    client.post("/observations", json=observation)
    client.post("/observations", json=second_observation)
    client.post(
        "/transitions",
        json={
            "source_screen_id": "screen_000001",
            "target_screen_id": "screen_000002",
            "action_id": "action_000001",
            "action_type": "tap",
        },
    )
    body = client.get("/app-map").json()
    assert len(body["nodes"]) == 2
    assert body["edges"][0]["source"] == "screen_000001"
    assert body["statistics"]["node_count"] == 2


def test_journeys(client, observation, second_observation):
    client.post("/observations", json=observation)
    client.post("/observations", json=second_observation)
    client.post(
        "/transitions",
        json={
            "source_screen_id": "screen_000001",
            "target_screen_id": "screen_000002",
            "action_type": "tap",
        },
    )
    journeys = client.get("/journeys").json()
    assert len(journeys) == 1
    assert journeys[0]["screen_ids"] == ["screen_000001", "screen_000002"]


def test_knowledge_pack_generate_and_latest(client, observation, second_observation):
    client.post("/observations", json=observation)
    client.post("/observations", json=second_observation)
    generated = client.post("/knowledge-pack/generate", json={"save_to_disk": False}).json()
    assert generated["pack_id"] == "pack_000001"
    assert generated["source_observation_ids"] == ["obs_000001", "obs_000002"]
    latest = client.get("/knowledge-pack/latest").json()
    assert latest["pack_id"] == generated["pack_id"]


def test_latest_pack_404_before_generation(client):
    assert client.get("/knowledge-pack/latest").status_code == 404


def test_stability_compare(client, observation, second_observation):
    client.post("/observations", json=observation)
    second_scan_obs = copy.deepcopy(observation)
    second_scan_obs["scan_id"] = "scan_000002"
    client.post("/observations", json=second_scan_obs)
    report = client.post(
        "/stability/compare",
        json={"previous_scan_id": SCAN, "current_scan_id": "scan_000002"},
    ).json()
    assert report["stability_score"] == 1.0
    assert report["matched_screens"] == 1


def test_scan_isolation(client, observation):
    client.post("/observations", json=observation)
    other = copy.deepcopy(observation)
    other["scan_id"] = "scan_000002"
    client.post("/observations", json=other)
    assert len(client.get("/screens", params={"scan_id": SCAN}).json()) == 1
    assert len(client.get("/screens", params={"scan_id": "scan_000002"}).json()) == 1
