import pytest
from flask import Flask

from app import connections as store
from app.admin_routes import admin_bp
from app.llm import registry


@pytest.fixture
def client(db):
    # Als geseedeter Admin angemeldet (id 1); es geht um die Key-Weitergabe.
    app = Flask(__name__)
    app.secret_key = "t"
    app.register_blueprint(admin_bp)
    with app.test_client() as c:
        with c.session_transaction() as s:
            s["user_id"] = 1
        yield c


@pytest.fixture
def seen_keys(monkeypatch):
    seen = []

    def fake(connection):
        seen.append((connection["base_url"], connection["api_key"]))
        return {"success": True, "message": "ok", "models": []}

    monkeypatch.setattr(registry, "test_connection", fake)
    return seen


@pytest.fixture
def conn(db):
    return store.create_connection("A", "http://good:4000/v1", "sk-geheim")


def test_stored_key_is_only_used_for_the_stored_url(client, conn, seen_keys):
    client.post(
        "/api/connections/test", json={"id": conn["id"], "base_url": "http://good:4000/v1/"}
    )
    client.post(
        "/api/connections/test", json={"id": conn["id"], "base_url": "http://evil.example/v1"}
    )
    assert seen_keys == [
        ("http://good:4000/v1", "sk-geheim"),
        ("http://evil.example/v1", ""),  # Key wird NICHT mitgeschickt
    ]


def test_explicit_key_is_always_used(client, conn, seen_keys):
    client.post(
        "/api/connections/test",
        json={"id": conn["id"], "base_url": "http://other/v1", "api_key": "sk-neu"},
    )
    assert seen_keys == [("http://other/v1", "sk-neu")]


def test_changing_url_requires_new_key(client, conn):
    res = client.patch(f"/api/connections/{conn['id']}", json={"base_url": "http://evil/v1"})
    assert res.status_code == 400
    assert store.get_connection(conn["id"], with_key=True)["base_url"] == "http://good:4000/v1"

    ok = client.patch(
        f"/api/connections/{conn['id']}", json={"base_url": "http://new/v1", "api_key": "sk-2"}
    )
    assert ok.status_code == 200
    assert store.get_connection(conn["id"], with_key=True)["api_key"] == "sk-2"


def test_same_url_or_other_fields_keep_key_without_reentry(client, conn):
    res = client.patch(
        f"/api/connections/{conn['id']}",
        json={"name": "B", "base_url": "http://good:4000/v1/", "enabled": False},
    )
    assert res.status_code == 200
    full = store.get_connection(conn["id"], with_key=True)
    assert (full["name"], full["api_key"], full["enabled"]) == ("B", "sk-geheim", False)
