"""
Tests für backend/api/topics.py (O-111).

Der Router ist komplett admin-only (`dependencies=[Depends(require_admin)]` bei
app.include_router in main.py) -- das war bisher an keiner Stelle geprüft. Die
Gating-Prüfung zielt bewusst auf nicht existierende IDs: schlüge sie fehl,
würde ein 404 aus der Routenlogik selbst ein fälschlich grünes 403 vortäuschen.
"""

from models.database import Project, Team, Topic, TopicNode

TEST_TOPIC_NAME = "TestTopicX"
TEST_TOPIC_NAME_2 = "TestTopicY"

ADMIN_GATED_ROUTES = [
    ("get", "/topics", None),
    ("post", "/topics", {"name": "x"}),
    ("patch", "/topics/999999", {"name": "x"}),
    ("delete", "/topics/999999", None),
    ("get", "/topics/999999/nodes", None),
    ("post", "/topics/999999/nodes", {"node_type": "project", "node_id": 1, "node_label": "x"}),
    ("delete", "/topics/999999/nodes/999999", None),
    ("get", "/topics/search-nodes", None),
]


def _cleanup_topic(db_session, name=TEST_TOPIC_NAME):
    db_session.query(Topic).filter(Topic.name == name).delete()
    db_session.commit()


def test_admin_gating_blocks_every_route_for_a_non_admin(member_client):
    for method, path, payload in ADMIN_GATED_ROUTES:
        kwargs = {"json": payload} if payload is not None else {}
        res = getattr(member_client, method)(path, **kwargs)
        assert res.status_code == 403, f"{method.upper()} {path} sollte 403 liefern, war {res.status_code}"


def test_create_list_update_delete_topic(client, db_session):
    _cleanup_topic(db_session)
    _cleanup_topic(db_session, f"{TEST_TOPIC_NAME}-Renamed")
    try:
        res = client.post("/topics", json={"name": TEST_TOPIC_NAME, "description": "Testzweck"})
        assert res.status_code == 201
        created = res.json()
        assert created["name"] == TEST_TOPIC_NAME
        assert created["description"] == "Testzweck"
        assert created["node_count"] == 0
        topic_id = created["id"]

        res = client.get("/topics")
        assert res.status_code == 200
        assert any(t["id"] == topic_id for t in res.json())

        # Teilweises Update: nur der Name ändert sich, die Beschreibung bleibt.
        res = client.patch(f"/topics/{topic_id}", json={"name": f"{TEST_TOPIC_NAME}-Renamed"})
        assert res.status_code == 200
        updated = res.json()
        assert updated["name"] == f"{TEST_TOPIC_NAME}-Renamed"
        assert updated["description"] == "Testzweck"

        res = client.delete(f"/topics/{topic_id}")
        assert res.status_code == 200

        res = client.get("/topics")
        assert not any(t["id"] == topic_id for t in res.json())
    finally:
        _cleanup_topic(db_session)
        _cleanup_topic(db_session, f"{TEST_TOPIC_NAME}-Renamed")


def test_create_defaults_color_to_indigo_when_omitted(client, db_session):
    _cleanup_topic(db_session)
    try:
        res = client.post("/topics", json={"name": TEST_TOPIC_NAME})
        assert res.status_code == 201
        assert res.json()["color"] == "indigo"
    finally:
        _cleanup_topic(db_session)


def test_update_and_delete_of_a_missing_topic_returns_404(client):
    assert client.patch("/topics/9999999", json={"name": "x"}).status_code == 404
    assert client.delete("/topics/9999999").status_code == 404


def test_deleting_a_topic_cascades_its_node_links(client, db_session):
    _cleanup_topic(db_session)
    try:
        topic_id = client.post("/topics", json={"name": TEST_TOPIC_NAME}).json()["id"]
        client.post(f"/topics/{topic_id}/nodes", json={
            "node_type": "project", "node_id": 1, "node_label": "Irgendein Projekt",
        })
        assert db_session.query(TopicNode).filter(TopicNode.topic_id == topic_id).count() == 1

        res = client.delete(f"/topics/{topic_id}")
        assert res.status_code == 200
        assert db_session.query(TopicNode).filter(TopicNode.topic_id == topic_id).count() == 0
    finally:
        _cleanup_topic(db_session)


def test_attach_list_and_detach_node(client, db_session):
    _cleanup_topic(db_session)
    try:
        topic_id = client.post("/topics", json={"name": TEST_TOPIC_NAME}).json()["id"]

        res = client.post(f"/topics/{topic_id}/nodes", json={
            "node_type": "project", "node_id": 42, "node_label": "Kernbanking",
            "node_url": None, "node_meta": {"is_archived": False},
        })
        assert res.status_code == 201
        node = res.json()
        assert node["node_label"] == "Kernbanking"
        assert node["topic_id"] == topic_id

        res = client.get(f"/topics/{topic_id}/nodes")
        assert res.status_code == 200
        assert len(res.json()) == 1

        # node_count auf dem Topic selbst spiegelt den angehängten Knoten.
        res = client.get("/topics")
        assert next(t for t in res.json() if t["id"] == topic_id)["node_count"] == 1

        res = client.delete(f"/topics/{topic_id}/nodes/{node['id']}")
        assert res.status_code == 200
        assert client.get(f"/topics/{topic_id}/nodes").json() == []
    finally:
        _cleanup_topic(db_session)


def test_attaching_the_same_node_twice_is_rejected(client, db_session):
    _cleanup_topic(db_session)
    try:
        topic_id = client.post("/topics", json={"name": TEST_TOPIC_NAME}).json()["id"]
        payload = {"node_type": "project", "node_id": 42, "node_label": "Kernbanking"}
        assert client.post(f"/topics/{topic_id}/nodes", json=payload).status_code == 201

        res = client.post(f"/topics/{topic_id}/nodes", json=payload)
        assert res.status_code == 409
    finally:
        _cleanup_topic(db_session)


def test_node_routes_404_for_a_missing_topic_or_node(client):
    assert client.get("/topics/9999999/nodes").status_code == 404
    payload = {"node_type": "project", "node_id": 1, "node_label": "x"}
    assert client.post("/topics/9999999/nodes", json=payload).status_code == 404
    assert client.delete("/topics/9999999/nodes/9999999").status_code == 404


def test_detaching_a_node_from_the_wrong_topic_is_rejected(client, db_session):
    # detach_node filtert nach (node_id, topic_id) gemeinsam -- eine Node-ID, die
    # existiert aber zu einem ANDEREN Topic gehört, darf darüber nicht löschbar sein.
    _cleanup_topic(db_session)
    _cleanup_topic(db_session, TEST_TOPIC_NAME_2)
    try:
        topic_a = client.post("/topics", json={"name": TEST_TOPIC_NAME}).json()["id"]
        topic_b = client.post("/topics", json={"name": TEST_TOPIC_NAME_2}).json()["id"]
        node = client.post(f"/topics/{topic_a}/nodes", json={
            "node_type": "project", "node_id": 1, "node_label": "x",
        }).json()

        res = client.delete(f"/topics/{topic_b}/nodes/{node['id']}")
        assert res.status_code == 404
        assert client.get(f"/topics/{topic_a}/nodes").json() != []
    finally:
        _cleanup_topic(db_session)
        _cleanup_topic(db_session, TEST_TOPIC_NAME_2)


def test_search_nodes_finds_a_visible_project(client, db_session):
    default_team = db_session.query(Team).filter(Team.name == "Default Team").first()
    project = Project(name="TestSearchProjectX", team_id=default_team.id)
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)
    try:
        res = client.get("/topics/search-nodes", params={"q": "TestSearchProjectX", "types": "project"})
        assert res.status_code == 200
        results = res.json()
        assert any(r["node_type"] == "project" and r["node_id"] == project.id for r in results)
    finally:
        db_session.delete(project)
        db_session.commit()
