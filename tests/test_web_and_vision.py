import pytest
from flask import Flask

from app import connections as store
from app.admin_routes import admin_bp
from app.api_routes import api_bp
from app.llm import registry
from app.llm.local_llm import VisionLLM
from app.routes import bp as main_bp
from app.settings_service import SettingsService
from app.tools import web_access
from tests.test_access import client_for

ADMIN = {"id": 1, "role": "admin", "username": "admin"}


@pytest.fixture
def app(db, monkeypatch):
    monkeypatch.setattr(registry, "fetch_remote_models", lambda c, force=False: ["m1", "m2"])
    app = Flask(__name__)
    app.secret_key = "t"
    app.extensions["ingestion_status"] = {"is_ingesting": False, "knowledge_id": None}
    for bp in (main_bp, api_bp, admin_bp):
        app.register_blueprint(bp)
    return app


def set_settings(db, **values):
    s = db.get_session()
    SettingsService(s).set_batch(values)
    s.close()


def test_web_search_needs_searxng_and_an_active_pii_filter(db):
    assert web_access.web_search_available() is False
    set_settings(db, SEARCH_SEARXNG_URL="http://sx:8080")
    assert web_access.web_search_available() is False  # PII fehlt
    set_settings(db, PII_FILTER_URL="http://pii:9500/api/v1/sanitize", PII_FILTER_ENABLED="false")
    assert web_access.web_search_available() is False  # PII abgeschaltet
    set_settings(db, PII_FILTER_ENABLED="true")
    assert web_access.web_search_available() is True
    assert web_access.build_web_search_tool().name == "web_search_tool"
    set_settings(db, SEARCH_SEARXNG_URL="")
    assert web_access.build_web_search_tool() is None


def test_web_search_per_model_is_off_by_default_and_blocked_without_pii(app, db):
    admin = client_for(app, ADMIN)
    conn = store.create_connection("C", "http://127.0.0.1:9/v1", "k")
    ref = store.make_base_ref(conn["id"], "m1")
    assert registry.resolve_model(ref).web_search is False

    blocked = admin.put("/api/models/config", json={"ref": ref, "web_search": True})
    assert blocked.status_code == 400 and "PII-Filter" in blocked.json["error"]
    assert registry.resolve_model(ref).web_search is False
    assert admin.get("/api/models").json["web_search_available"] is False

    set_settings(db, SEARCH_SEARXNG_URL="http://sx:8080", PII_FILTER_URL="http://pii:9500/x")
    assert admin.get("/api/models").json["web_search_available"] is True
    ok = admin.put("/api/models/config", json={"ref": ref, "web_search": True})
    assert ok.status_code == 200 and ok.json["web_search"] is True
    resolved = registry.resolve_model(ref)
    assert resolved.web_search is True

    # Der Agent-Cache unterscheidet Modelle mit und ohne Websuche-Werkzeug
    a = resolved.signature()
    admin.put("/api/models/config", json={"ref": ref, "web_search": False})
    assert registry.resolve_model(ref).signature() != a


def test_clone_inherits_web_search(app, db):
    set_settings(db, SEARCH_SEARXNG_URL="http://sx:8080", PII_FILTER_URL="http://pii:9500/x")
    conn = store.create_connection("C", "http://127.0.0.1:9/v1", "k")
    ref = store.make_base_ref(conn["id"], "m1")
    store.save_model_config(ref, {"web_search": True})
    clone = store.clone_model(ref, "Kopie")
    assert clone["web_search"] is True


def test_infrastructure_settings_come_from_the_environment_not_the_database(db, monkeypatch):
    s = db.get_session()
    svc = SettingsService(s)
    svc.set("QDRANT_HOST", "alt-aus-der-db")
    monkeypatch.setenv("QDRANT_HOST", "qdrant")
    assert svc.get("QDRANT_HOST", "localhost") == "qdrant"
    monkeypatch.delenv("QDRANT_HOST")
    assert svc.get("QDRANT_HOST", "localhost") == "localhost"
    s.close()


def test_tools_api_is_admin_only_and_validates(app, db):
    from tests.test_access import add_user

    ed = add_user(db, "ed", "editor")
    assert client_for(app, ed).get("/api/admin/tools").status_code == 403
    assert client_for(app, ed).put("/api/admin/tools", json={}).status_code == 403
    admin = client_for(app, ADMIN)
    assert admin.put("/api/admin/tools", json={"search": {"url": "ftp://x"}}).status_code == 400
    assert admin.put("/api/admin/tools", json={"pii": {"url": "http://169.254.169.254/x"}}).status_code == 400
    assert admin.put("/api/admin/tools", json={"stt": {"base_url": "http://169.254.169.254/v1"}}).status_code == 400
    assert admin.post("/api/admin/tools/test", json={"kind": "nope"}).status_code == 400


def test_tools_test_uses_form_values_and_stored_key_only_for_the_stored_url(app, db, monkeypatch):
    import app.user_routes as ur

    seen = []
    monkeypatch.setattr(ur, "_test_stt", lambda s: seen.append((s.get("STT_BASEURL"), s.get("STT_API_KEY"))) or {"success": True})
    admin = client_for(app, ADMIN)
    admin.put("/api/admin/tools", json={"stt": {"base_url": "http://stt:5001/v1", "api_key": "geheim"}})
    assert admin.post("/api/admin/tools/test", json={"kind": "stt", "values": {"base_url": "http://stt:5001/v1", "api_key": ""}}).status_code == 200
    assert admin.post("/api/admin/tools/test", json={"kind": "stt", "values": {"base_url": "http://anderer:5001/v1", "api_key": ""}}).status_code == 200
    assert seen[0] == ("http://stt:5001/v1", "geheim")
    assert seen[1] == ("http://anderer:5001/v1", "")  # gespeicherter Key geht nie an eine fremde Adresse


def test_vision_model_comes_from_connections(app, db, monkeypatch):
    admin = client_for(app, ADMIN)
    conn = store.create_connection("C", "http://127.0.0.1:9/v1", "k")
    default_ref = store.make_base_ref(conn["id"], "m1")
    vision_ref = store.make_base_ref(conn["id"], "m2")
    store.set_default_model(default_ref)

    llm = VisionLLM()
    llm.llm  # loest auf
    assert llm.vision_model == "m1"  # ohne Auswahl: Standardmodell

    assert admin.put("/api/admin/embedding", json={"vision_model": vision_ref}).json["vision_model"] == vision_ref
    llm.llm
    assert llm.vision_model == "m2"

    bad = admin.put("/api/admin/embedding", json={"vision_model": "base:99:x"})
    assert bad.status_code == 400
    assert admin.put("/api/admin/embedding", json={"vision_model": ""}).json["vision_model"] == ""


def test_vision_can_be_switched_off(app, db):
    from app.components.preprocess_base import _vision_enabled

    admin = client_for(app, ADMIN)
    assert _vision_enabled() is True
    r = admin.put("/api/admin/embedding", json={"ingest": {"vision_enabled": False}})
    assert r.status_code == 200 and r.json["ingest"]["vision_enabled"] is False
    assert _vision_enabled() is False


def test_hidden_models_stay_selectable_for_vision(app, db):
    admin = client_for(app, ADMIN)
    conn = store.create_connection("C", "http://127.0.0.1:9/v1", "k")
    ref = store.make_base_ref(conn["id"], "m2")
    admin.put("/api/models/config", json={"ref": ref, "visible": False})
    assert ref not in [m["ref"] for m in admin.get("/api/models?visible=1").json["models"]]
    assert ref in [m["ref"] for m in admin.get("/api/models").json["models"]]
    assert admin.put("/api/admin/embedding", json={"vision_model": ref}).status_code == 200
