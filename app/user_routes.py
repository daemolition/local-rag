# Local Document RAG - A privacy-focused, local RAG system
# Copyright (C) 2026 Christopher Abanilla
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

"""
User Routes für Dokumentenverwaltung, Vektordatenbank, Settings und Summaries
(Single-User)
"""

import os
from datetime import datetime
from logging import getLogger
from pathlib import Path

import requests
from flask import (
    Blueprint,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from qdrant_client import models
from werkzeug.security import check_password_hash, generate_password_hash

from app.auth import auth_required
from app.database_service import get_db_service
from app.settings_service import SettingsService

logger = getLogger(__name__)

user_bp = Blueprint("user", __name__, url_prefix="/user")

COLLECTION_NAME = "local_rag"


@user_bp.route("/documents")
@auth_required
def my_documents():
    """Alle Dokumente im file-level View"""
    db = get_db_service()
    user_docs = db.get_all_documents()

    client = current_app.extensions.get("client")
    documents = []

    if client:
        for user_doc in user_docs:
            try:
                points, _ = client.scroll(
                    collection_name=COLLECTION_NAME,
                    scroll_filter=models.Filter(
                        must=[
                            models.FieldCondition(
                                key="file_group_id",
                                match=models.MatchValue(value=user_doc.document_id),
                            )
                        ]
                    ),
                    limit=1,
                    with_payload=True,
                    with_vectors=False,
                )
                if points:
                    payload = points[0].payload or {}

                    from app.utils.file_manager import check_data_file_exists

                    has_data_file = check_data_file_exists(user_doc.filename)

                    documents.append(
                        {
                            "id": user_doc.id,
                            "document_id": user_doc.document_id,
                            "filename": user_doc.filename,
                            "uploaded_at": user_doc.uploaded_at,
                            "content_preview": (
                                payload.get("page_content", "")
                                or payload.get("original_content", "")
                            )[:100]
                            + "...",
                            "source": payload.get("source", "N/A"),
                            "has_data_file": has_data_file,
                        }
                    )
                else:
                    documents.append(
                        {
                            "id": user_doc.id,
                            "document_id": user_doc.document_id,
                            "filename": user_doc.filename,
                            "uploaded_at": user_doc.uploaded_at,
                            "content_preview": "[Nicht mehr in Qdrant]",
                            "source": "N/A",
                        }
                    )
            except Exception as e:
                documents.append(
                    {
                        "id": user_doc.id,
                        "document_id": user_doc.document_id,
                        "filename": user_doc.filename,
                        "uploaded_at": user_doc.uploaded_at,
                        "content_preview": f"[Fehler: {e!s}]",
                        "source": "N/A",
                    }
                )

    return render_template("user/documents.html", documents=documents)


@user_bp.route("/documents/upload", methods=["GET", "POST"])
@auth_required
def upload_document():
    """Dokumente hochladen - GET zeigt Formular, POST verarbeitet Upload"""
    if request.method == "GET":
        return render_template("user/upload.html")

    project_root = Path(current_app.root_path).parent
    files = request.files.getlist("files")

    target_dir = project_root / "data" / "files"
    processed_dir = project_root / "data" / "processed_files"
    target_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)

    saved_files = []

    for file in files:
        if file.filename == "":
            continue

        ext = Path(file.filename).suffix.lower()
        allowed_exts = [".pdf", ".docx", ".doc", ".xlsx", ".xls", ".csv"]
        if ext not in allowed_exts:
            continue

        processed_path = processed_dir / file.filename
        if processed_path.exists():
            return jsonify(
                {
                    "success": False,
                    "error": f'Datei "{file.filename}" wurde bereits hochgeladen und verarbeitet. '
                    f"Bitte zuerst das bestehende Dokument löschen, um es zu ersetzen.",
                }
            ), 409

        filepath = target_dir / file.filename
        file.save(filepath)
        saved_files.append(file.filename)

    if saved_files:
        return jsonify(
            {
                "success": True,
                "files": saved_files,
                "message": f"{len(saved_files)} Datei(en) hochgeladen. Bitte Ingestion starten.",
            }
        )

    return jsonify({"success": False, "error": "Keine gültigen Dateien"}), 400


@user_bp.route("/documents/upload/clear", methods=["POST"])
@auth_required
def clear_uploaded_files():
    """Löscht alle noch nicht ingesteten Dateien aus data/files."""
    project_root = Path(current_app.root_path).parent
    target_dir = project_root / "data" / "files"
    deleted = 0
    errors = []

    if target_dir.exists():
        for file_path in target_dir.iterdir():
            if not file_path.is_file():
                continue
            try:
                file_path.unlink()
                deleted += 1
            except Exception as e:
                logger.warning(f"Konnte {file_path} nicht löschen: {e}")
                errors.append(str(e))

    return jsonify({"success": True, "deleted": deleted, "errors": errors})


@user_bp.route("/documents/<int:doc_id>/delete", methods=["POST"])
@auth_required
def delete_my_document(doc_id):
    """Dokument löschen + zugehörige Datei automatisch"""
    db = get_db_service()

    from app.models import UserDocument

    db_session = db.get_session()
    user_doc = db_session.query(UserDocument).filter_by(id=doc_id).first()

    if not user_doc:
        db_session.close()
        return jsonify({"success": False, "error": "Dokument nicht gefunden"}), 404

    doc_filter = models.Filter(
        must=[
            models.FieldCondition(
                key="file_group_id", match=models.MatchValue(value=user_doc.document_id)
            )
        ]
    )

    client = current_app.extensions.get("client")
    payload = None
    if client:
        try:
            points, _ = client.scroll(
                collection_name=COLLECTION_NAME,
                scroll_filter=doc_filter,
                limit=1,
                with_payload=True,
                with_vectors=False,
            )
            if points:
                payload = points[0].payload
        except Exception as e:
            logger.error(f"Fehler beim Holen des Dokuments für Datei-Löschung: {e}")

    if client:
        try:
            client.delete(
                collection_name=COLLECTION_NAME,
                points_selector=models.FilterSelector(filter=doc_filter),
            )
        except Exception as e:
            db_session.close()
            return jsonify({"success": False, "error": f"Qdrant Fehler: {e!s}"}), 500

    if payload:
        from app.utils.file_manager import delete_associated_file

        deleted = delete_associated_file(payload)
        if deleted:
            logger.info(f"Zugehörige Datei zu Dokument {doc_id} gelöscht")

    db_session.delete(user_doc)
    db_session.commit()
    db_session.close()

    return jsonify({"success": True})


@user_bp.route("/documents/ingest", methods=["POST"])
@auth_required
def trigger_ingestion():
    """Ingestion der hochgeladenen Dateien starten"""
    from app import wait_for_resources
    from app.vector import DocumentIngestion

    try:
        if not wait_for_resources(timeout=180):
            return jsonify(
                {
                    "success": False,
                    "error": "RAG-System wird noch initialisiert (Embedding-Modell "
                    "lädt). Bitte in wenigen Sekunden erneut versuchen.",
                }
            ), 503
    except RuntimeError as e:
        return jsonify({"success": False, "error": str(e)}), 503

    status = current_app.extensions["ingestion_status"]
    if status["is_ingesting"]:
        return jsonify({"success": False, "error": "Ingestion läuft bereits"}), 409

    status["is_ingesting"] = True
    try:
        ingest = DocumentIngestion(
            embeddings=current_app.extensions.get("dense_embeddings"),
            sparse_embeddings=current_app.extensions.get("sparse_embeddings"),
        )
        ingest.ingest_documents()

        return jsonify({"success": True, "message": "Ingestion erfolgreich"})
    except Exception as e:
        logger.error(f"Fehler bei der Ingestion: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        status["is_ingesting"] = False


# =============================================================================
# VECTOR DATABASE (ex /admin)
# =============================================================================


@user_bp.route("/vectordb")
@auth_required
def vectordb():
    """Chunk-level Dokumentenansicht (ex /admin/documents)"""
    client = current_app.extensions.get("client")
    if not client:
        flash("Qdrant Client nicht initialisiert")
        return redirect(url_for("main.index"))

    limit = request.args.get("limit", 20, type=int)
    offset = request.args.get("offset", None)
    filename_filter = request.args.get("filename", "").strip()
    file_status_filter = request.args.get("file_status", "").strip()

    try:
        scroll_filter = None
        if filename_filter:
            scroll_filter = models.Filter(
                must=[
                    models.FieldCondition(
                        key="filename", match=models.MatchValue(value=filename_filter)
                    )
                ]
            )

        result = client.scroll(
            collection_name=COLLECTION_NAME,
            limit=limit,
            offset=offset,
            with_payload=True,
            with_vectors=False,
            scroll_filter=scroll_filter,
        )

        points, next_offset = result

        documents = []
        for point in points:
            payload = point.payload or {}
            filename = payload.get("filename", "N/A")

            from app.utils.file_manager import check_data_file_exists

            has_data_file = (
                check_data_file_exists(filename) if filename != "N/A" else False
            )

            if file_status_filter:
                if file_status_filter == "has_file" and not has_data_file:
                    continue
                if file_status_filter == "no_file" and has_data_file:
                    continue

            documents.append(
                {
                    "id": str(point.id),
                    "filename": filename,
                    "source": payload.get("source", "N/A"),
                    "content_preview": (
                        payload.get("page_content", "")
                        or payload.get("original_content", "")
                    )[:50]
                    + "...",
                    "has_data_file": has_data_file,
                }
            )

        all_points, _ = client.scroll(
            collection_name=COLLECTION_NAME,
            limit=1000,
            with_payload=True,
            with_vectors=False,
        )
        filenames = sorted(
            set(p.payload.get("filename", "N/A") for p in all_points if p.payload)
        )

    except Exception as e:
        documents = []
        next_offset = None
        filenames = []
        flash(f"Fehler beim Laden der Dokumente: {e!s}")

    return render_template(
        "user/vectordb.html",
        documents=documents,
        next_offset=next_offset,
        filenames=filenames,
        current_filter=filename_filter,
        file_status_filter=file_status_filter,
        limit=limit,
    )


@user_bp.route("/vectordb/<doc_id>")
@auth_required
def vectordb_detail(doc_id):
    """Einzelnes Qdrant-Dokument anzeigen"""
    client = current_app.extensions.get("client")
    if not client:
        flash("Qdrant Client nicht initialisiert")
        return redirect(url_for("user.vectordb"))

    try:
        result = client.retrieve(
            collection_name=COLLECTION_NAME,
            ids=[doc_id],
            with_payload=True,
            with_vectors=False,
        )

        if not result:
            flash("Dokument nicht gefunden")
            return redirect(url_for("user.vectordb"))

        point = result[0]
        payload = point.payload or {}

        document = {
            "id": str(point.id),
            "page_content": payload.get("page_content", ""),
            "original_content": payload.get("original_content", ""),
            "metadata": {
                k: v
                for k, v in payload.items()
                if k not in ["page_content", "original_content"]
            },
        }

    except Exception as e:
        flash(f"Fehler beim Laden des Dokuments: {e!s}")
        return redirect(url_for("user.vectordb"))

    return render_template("user/vectordb_detail.html", document=document)


@user_bp.route("/vectordb/<doc_id>/delete", methods=["POST"])
@auth_required
def delete_vectordb_document(doc_id):
    """Einzelnes Qdrant-Dokument löschen + Datei"""
    client = current_app.extensions.get("client")
    if not client:
        return jsonify(
            {"success": False, "error": "Qdrant Client nicht initialisiert"}
        ), 500

    try:
        result = client.retrieve(
            collection_name=COLLECTION_NAME,
            ids=[doc_id],
            with_payload=True,
            with_vectors=False,
        )

        payload = result[0].payload if result else None

        client.delete(
            collection_name=COLLECTION_NAME,
            points_selector=models.PointIdsList(points=[doc_id]),
        )

        if payload:
            from app.utils.file_manager import delete_associated_file

            delete_associated_file(payload)

        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"Fehler beim Löschen von Dokument {doc_id}: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@user_bp.route("/vectordb/batch-delete", methods=["POST"])
@auth_required
def vectordb_batch_delete():
    """Alle Chunks eines Filenames löschen + Datei"""
    client = current_app.extensions.get("client")
    if not client:
        return jsonify(
            {"success": False, "error": "Qdrant Client nicht initialisiert"}
        ), 500

    data = request.get_json()
    filename = data.get("filename")

    if not filename:
        return jsonify({"success": False, "error": "Filename erforderlich"}), 400

    try:
        from app.utils.file_manager import delete_associated_file

        result = client.scroll(
            collection_name=COLLECTION_NAME,
            filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="filename", match=models.MatchValue(value=filename)
                    )
                ]
            ),
            limit=1000,
            with_payload=True,
            with_vectors=False,
        )

        points, _ = result

        if points:
            payload = points[0].payload
            if payload:
                delete_associated_file(payload)

            # Punkt-IDs sammeln und über PointIdsList löschen (statt
            # FilterSelector). FilterSelector wird erst ab neueren
            # Qdrant-Server-Versionen vom Delete-Endpoint unterstützt —
            # ältere Server melden "unknown arguments ['filter']".
            point_ids = [str(p.id) for p in points]
            client.delete(
                collection_name=COLLECTION_NAME,
                points_selector=models.PointIdsList(points=point_ids),
            )
        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"Fehler beim Batch-Delete: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@user_bp.route("/vectordb/clear", methods=["POST"])
@auth_required
def vectordb_clear_all():
    """Collection komplett leeren und neu anlegen"""
    client = current_app.extensions.get("client")
    if not client:
        return jsonify(
            {"success": False, "error": "Qdrant Client nicht initialisiert"}
        ), 500

    data = request.get_json()
    confirmation = data.get("confirmation", "")
    if confirmation != "DELETE_ALL":
        return jsonify({"success": False, "error": "Bestätigung erforderlich"}), 400

    try:
        client.delete_collection(COLLECTION_NAME)

        embedding_dim = 384
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=models.VectorParams(
                size=embedding_dim, distance=models.Distance.COSINE
            ),
            sparse_vectors_config={"langchain-sparse": models.SparseVectorParams()},
            hnsw_config=models.HnswConfigDiff(
                m=16, ef_construct=100, full_scan_threshold=10000
            ),
        )

        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@user_bp.route("/dashboard")
@auth_required
def dashboard():
    """Dashboard mit Collection-Info (ex /admin/index)"""
    client = current_app.extensions.get("client")
    if not client:
        flash("Qdrant Client nicht initialisiert")
        return redirect(url_for("main.index"))

    try:
        collection = client.get_collection(COLLECTION_NAME)
        stats = {
            "name": COLLECTION_NAME,
            "points_count": collection.points_count,
            "vectors_count": getattr(
                collection, "indexed_vectors_count", collection.points_count
            )
            or 0,
            "status": collection.status.value
            if hasattr(collection.status, "value")
            else str(collection.status),
            "config": {
                "size": collection.config.params.vectors.size
                if hasattr(collection.config.params.vectors, "size")
                else "N/A",
                "distance": collection.config.params.vectors.distance.value
                if hasattr(collection.config.params.vectors, "distance")
                else "N/A",
            },
        }
    except Exception as e:
        stats = None
        flash(f"Fehler beim Laden der Collection: {e!s}")

    return render_template("user/dashboard.html", stats=stats)


@user_bp.route("/api/stats")
@auth_required
def api_stats():
    """API: Collection Stats"""
    client = current_app.extensions.get("client")
    if not client:
        return jsonify({"error": "Qdrant Client nicht initialisiert"}), 500

    try:
        collection = client.get_collection(COLLECTION_NAME)
        return jsonify(
            {
                "points_count": collection.points_count,
                "status": collection.status.value
                if hasattr(collection.status, "value")
                else str(collection.status),
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# =============================================================================
# SETTINGS (ex /admin/settings)
# =============================================================================

SELECT_OPTIONS = {
    "EMBEDDING_SOURCE": [("local", "Lokal"), ("endpoint", "Remote Endpoint")],
    "UI_THEME": [
        ("system", "System (OS-Präferenz folgen)"),
        ("light", "Hell"),
        ("dark", "Dunkel"),
    ],
    "CHAT_THINKING": [
        ("none", "Aus (kein Thinking)"),
        ("low", "Niedrig"),
        ("medium", "Mittel"),
        ("high", "Hoch"),
        ("max", "Maximal"),
    ],
}

DEPENDENT_FIELDS = {
    "EMBEDDING_SOURCE": {"show_when": "endpoint", "fields": ["EMBEDDING_ENDPOINT"]}
}

TOGGLE_KEYS = {"SEARCH_SEARXNG_ENABLED", "PII_FILTER_ENABLED"}


@user_bp.route("/settings")
@auth_required
def settings():
    """Settings-Panel anzeigen"""
    db = get_db_service()
    settings_svc = SettingsService(db.get_session())

    settings_by_category = settings_svc.get_all_by_category()
    category_names = {
        cat: settings_svc.get_category_display_name(cat)
        for cat in settings_by_category.keys()
    }

    return render_template(
        "user/settings.html",
        settings_by_category=settings_by_category,
        category_names=category_names,
        select_options=SELECT_OPTIONS,
        dependent_fields=DEPENDENT_FIELDS,
        toggle_keys=TOGGLE_KEYS,
        testable_categories=TESTABLE_CATEGORIES,
    )


@user_bp.route("/settings", methods=["POST"])
@auth_required
def update_settings():
    """Settings speichern"""
    data = request.get_json()
    settings_dict = data.get("settings", {})

    if not settings_dict:
        return jsonify({"success": False, "error": "Keine Settings übergeben"}), 400

    db = get_db_service()
    settings_svc = SettingsService(db.get_session())

    try:
        settings_svc.set_batch(settings_dict)
        return jsonify({"success": True, "updated": len(settings_dict)})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@user_bp.route("/settings/reset", methods=["POST"])
@auth_required
def reset_setting():
    """Einzelnes Setting auf Default zurücksetzen"""
    data = request.get_json()
    key = data.get("key")

    if not key:
        return jsonify({"success": False, "error": "Key erforderlich"}), 400

    db = get_db_service()
    settings_svc = SettingsService(db.get_session())

    success = settings_svc.reset_to_default(key)
    if success:
        return jsonify({"success": True})
    return jsonify({"success": False, "error": "Setting nicht gefunden"}), 404


@user_bp.route("/settings/reset-category", methods=["POST"])
@auth_required
def reset_category():
    """Alle Settings einer Kategorie zurücksetzen"""
    data = request.get_json()
    category = data.get("category")

    if not category:
        return jsonify({"success": False, "error": "Kategorie erforderlich"}), 400

    db = get_db_service()
    settings_svc = SettingsService(db.get_session())

    count = settings_svc.reset_category(category)
    return jsonify({"success": True, "reset_count": count})


@user_bp.route("/settings/import-env", methods=["POST"])
@auth_required
def import_env_settings():
    """Aktuelle .env-Werte in DB importieren"""
    data = request.get_json()
    overwrite = data.get("overwrite", False)

    db = get_db_service()
    settings_svc = SettingsService(db.get_session())

    count = settings_svc.import_from_env(overwrite=overwrite)
    return jsonify({"success": True, "imported": count})


@user_bp.route("/settings/change-password", methods=["POST"])
@auth_required
def change_password():
    """App-Passwort ändern"""
    data = request.get_json()
    old_password = data.get("old_password", "")
    new_password = data.get("new_password", "")

    if not new_password or len(new_password) < 4:
        return jsonify(
            {"success": False, "error": "Passwort muss mindestens 4 Zeichen haben"}
        ), 400

    db = get_db_service()
    settings_svc = SettingsService(db.get_session())

    current_hash = settings_svc.get("APP_PASSWORD_HASH")
    if current_hash and not check_password_hash(current_hash, old_password):
        return jsonify({"success": False, "error": "Altes Passwort ist falsch"}), 403

    settings_svc.set("APP_PASSWORD_HASH", generate_password_hash(new_password))
    return jsonify({"success": True})


# =============================================================================
# SERVICE TEST
# =============================================================================

# Welche Kategorien getestet werden können und wie (Service -> Kategorie-Mapping)
TESTABLE_CATEGORIES = {
    "llm",
    "stt",
    "embedding",
    "qdrant",
    "search",
    "pii_filter",
}


@user_bp.route("/settings/test", methods=["POST"])
@auth_required
def test_service():
    """Diensteverbindung testen (anhand der aktuell gespeicherten Settings).

    Body: { "category": "<llm|stt|embedding|qdrant|search|pii_filter>" }
    Liefert: { "success": bool, "message": str, "details": str }
    """
    data = request.get_json() or {}
    category = data.get("category")

    if not category or category not in TESTABLE_CATEGORIES:
        return (
            jsonify(
                {
                    "success": False,
                    "error": (
                        f"Unbekannte Kategorie '{category}'. "
                        f"Testbar: {', '.join(sorted(TESTABLE_CATEGORIES))}"
                    )
                }
            ),
            400,
        )

    db = get_db_service()
    settings_svc = SettingsService(db.get_session())

    try:
        if category == "llm":
            return jsonify(_test_llm(settings_svc))
        if category == "stt":
            return jsonify(_test_stt(settings_svc))
        if category == "embedding":
            return jsonify(_test_embedding(settings_svc))
        if category == "qdrant":
            return jsonify(_test_qdrant(settings_svc))
        if category == "search":
            return jsonify(_test_search(settings_svc))
        if category == "pii_filter":
            return jsonify(_test_pii_filter(settings_svc))
    except Exception as e:
        logger.exception(f"Service-Test '{category}' fehlgeschlagen")
        return jsonify({"success": False, "error": f"Unerwarteter Fehler: {e}"}), 500


def _test_llm(settings: SettingsService) -> dict:
    """Chat-LLM testen: erst /v1/models prüfen, dann eine echte
    Chat-Completion-Anfrage an das konfigurierte Modell senden."""
    base_url = (settings.get("CHAT_BASEURL") or "").rstrip("/")
    api_key = settings.get("API_KEY") or "ollama"
    model = settings.get("CHAT_MODEL") or ""

    if not base_url:
        return {"success": False, "error": "CHAT_BASEURL ist nicht gesetzt"}
    if not model:
        return {"success": False, "error": "CHAT_MODEL ist nicht gesetzt"}

    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

    # 1. /v1/models prüfen (Server erreichbar + Modell geladen?)
    models_url = base_url.rstrip("/").rstrip("v1").rstrip("/") + "/v1/models"
    try:
        resp = requests.get(models_url, headers=headers, timeout=10)
        if resp.status_code != 200:
            return {
                "success": False,
                "error": f"HTTP {resp.status_code} von {models_url}",
                "details": resp.text[:300],
            }
        data = resp.json()
        models = [m.get("id", "?") for m in data.get("data", [])]
        if models and model not in models:
            return {
                "success": False,
                "error": (
                    f"Modell '{model}' nicht in der Modellliste gefunden. "
                    f"Verfügbar: {', '.join(models[:15])}"
                ),
                "details": ", ".join(models[:15]),
            }
    except requests.exceptions.Timeout:
        return {"success": False, "error": f"Timeout (10s) bei {models_url}"}
    except requests.exceptions.RequestException as e:
        return {"success": False, "error": f"Verbindung fehlgeschlagen: {e}"}

    # 2. Echte Chat-Completion-Anfrage ans Modell senden (echter Test,
    #    ob das Modell antwortet — /v1/models sagt nur, dass es geladen ist).
    chat_url = base_url.rstrip("/").rstrip("v1").rstrip("/") + "/v1/chat/completions"
    try:
        resp = requests.post(
            chat_url,
            headers={**headers, "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": "Antworte mit 'OK'."}],
                "max_tokens": 16,
                "stream": False,
            },
            timeout=30,
        )
        if resp.status_code != 200:
            return {
                "success": False,
                "error": f"HTTP {resp.status_code} von {chat_url}",
                "details": resp.text[:300],
            }
        data = resp.json()
        choices = data.get("choices", [])
        answer = choices[0]["message"]["content"] if choices else ""
        return {
            "success": True,
            "message": f"Modell '{model}' antwortet.",
            "details": f"Antwort: {answer[:100]}",
        }
    except requests.exceptions.Timeout:
        return {"success": False, "error": f"Timeout (30s) bei {chat_url}"}
    except requests.exceptions.RequestException as e:
        return {"success": False, "error": f"Chat-Anfrage fehlgeschlagen: {e}"}


def _test_stt(settings: SettingsService) -> dict:
    """STT Endpunkt testen (OpenAI-compatible /v1/models oder /v1/audio/speech)."""
    base_url = (settings.get("STT_BASEURL") or "").rstrip("/")
    api_key = settings.get("STT_API_KEY") or ""
    model = settings.get("STT_MODEL") or ""

    if not base_url:
        return {"success": False, "error": "STT_BASEURL ist nicht gesetzt"}

    models_url = base_url.rstrip("/").rstrip("v1").rstrip("/") + "/v1/models"
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

    try:
        resp = requests.get(models_url, headers=headers, timeout=10)
        if resp.status_code != 200:
            return {
                "success": False,
                "error": f"HTTP {resp.status_code} von {models_url}",
                "details": resp.text[:300],
            }
        data = resp.json()
        models = [m.get("id", "?") for m in data.get("data", [])]
        ok = True
        message = f"Verbindung OK. {len(models)} Modell(e) verfügbar."
        details = ", ".join(models[:15])
        if model and models and model not in models:
            ok = False
            message = (
                f"Verbindung OK, aber das konfigurierte Modell '{model}' "
                "wurde nicht in der Modellliste gefunden."
            )
        return {"success": ok, "message": message, "details": details}
    except requests.exceptions.Timeout:
        return {"success": False, "error": f"Timeout (10s) bei {models_url}"}
    except requests.exceptions.RequestException as e:
        return {"success": False, "error": f"Verbindung fehlgeschlagen: {e}"}


def _test_embedding(settings: SettingsService) -> dict:
    """Embedding-Service testen. Lokal (fastembed) wird nur gemeldet, nicht geprüft."""
    source = settings.get("EMBEDDING_SOURCE") or "local"
    if source != "endpoint":
        return {
            "success": True,
            "message": (
                "Lokale Embeddings (ONNX/fastembed) sind aktiviert — "
                "kein Remote-Service zu testen."
            ),
        }

    endpoint = settings.get("EMBEDDING_ENDPOINT") or ""
    api_key = settings.get("API_KEY") or ""
    if not endpoint:
        return {"success": False, "error": "EMBEDDING_ENDPOINT ist nicht gesetzt"}

    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    # /v1/models als Standard-Endpoint
    models_url = endpoint.rstrip("/").rstrip("v1").rstrip("/") + "/v1/models"

    try:
        resp = requests.get(models_url, headers=headers, timeout=10)
        if resp.status_code != 200:
            return {
                "success": False,
                "error": f"HTTP {resp.status_code} von {models_url}",
                "details": resp.text[:300],
            }
        data = resp.json()
        models = [m.get("id", "?") for m in data.get("data", [])]
        return {
            "success": True,
            "message": f"Verbindung OK. {len(models)} Modell(e) verfügbar.",
            "details": ", ".join(models[:15]),
        }
    except requests.exceptions.Timeout:
        return {"success": False, "error": f"Timeout (10s) bei {models_url}"}
    except requests.exceptions.RequestException as e:
        return {"success": False, "error": f"Verbindung fehlgeschlagen: {e}"}


def _test_qdrant(settings: SettingsService) -> dict:
    """Qdrant-Verbindung testen (über die bestehende Client-Factory)."""
    from app.utils.qdrant_client import get_qdrant_client, test_connection

    host = settings.get("QDRANT_HOST", "localhost")
    port = settings.get_int("QDRANT_PORT", 6333)
    api_key = settings.get("QDRANT_API_KEY") or None

    try:
        client = get_qdrant_client(
            custom_host=host, custom_port=port, api_key=api_key
        )
        ok, msg = test_connection(client, timeout=5)
        return {"success": ok, "message": msg if ok else None, "error": None if ok else msg}
    except Exception as e:
        return {"success": False, "error": f"Qdrant-Verbindung fehlgeschlagen: {e}"}


def _test_search(settings: SettingsService) -> dict:
    """SearXNG Metasuchmaschine testen."""
    url = settings.get("SEARCH_SEARXNG_URL") or ""
    if not url:
        return {"success": False, "error": "SEARCH_SEARXNG_URL ist nicht gesetzt"}

    # health-Endpoint oder /search mit leerer Query probieren
    candidates = [
        url.rstrip("/") + "/healthz",
        url.rstrip("/") + "/search?q=test&format=json",
    ]

    last_error = ""
    for test_url in candidates:
        try:
            resp = requests.get(test_url, timeout=10)
            if resp.status_code == 200:
                # Bei /search prüfen ob JSON zurückkommt
                if test_url.endswith("format=json"):
                    try:
                        data = resp.json()
                        results = data.get("results", [])
                        return {
                            "success": True,
                            "message": (
                                f"SearXNG erreichbar. "
                                f"{len(results)} Test-Ergebnis(se) zurückgegeben."
                            ),
                        }
                    except ValueError:
                        last_error = "Antwort ist kein valides JSON"
                        continue
                return {"success": True, "message": "SearXNG erreichbar."}
            else:
                last_error = f"HTTP {resp.status_code} von {test_url}"
        except requests.exceptions.Timeout:
            last_error = f"Timeout (10s) bei {test_url}"
        except requests.exceptions.RequestException as e:
            last_error = f"Verbindung fehlgeschlagen: {e}"

    return {"success": False, "error": last_error or "SearXNG nicht erreichbar"}


def _test_pii_filter(settings: SettingsService) -> dict:
    """PII-Filter Service testen (mit Test-Text)."""
    url = settings.get("PII_FILTER_URL") or ""
    api_key = settings.get("PII_FILTER_API_KEY") or ""

    if not url:
        return {"success": False, "error": "PII_FILTER_URL ist nicht gesetzt"}

    test_text = "Test-Text ohne PII für Verbindungsprüfung."
    json_body = {"text": test_text}
    if api_key:
        json_body["api_key"] = api_key

    try:
        resp = requests.post(
            url,
            json=json_body,
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        if resp.status_code != 200:
            return {
                "success": False,
                "error": f"HTTP {resp.status_code} von {url}",
                "details": resp.text[:300],
            }
        # Wenn der Service antwortet, ist die Verbindung OK
        return {
            "success": True,
            "message": "PII-Filter Service erreichbar.",
            "details": f"Status: {resp.status_code}",
        }
    except requests.exceptions.Timeout:
        return {"success": False, "error": f"Timeout (10s) bei {url}"}
    except requests.exceptions.RequestException as e:
        return {"success": False, "error": f"Verbindung fehlgeschlagen: {e}"}


# =============================================================================
# SUMMARIES MANAGEMENT
# =============================================================================


@user_bp.route("/summaries")
@auth_required
def my_summaries():
    """Alle Summary-Dateien anzeigen"""
    db = get_db_service()
    settings = SettingsService(db.get_session())
    summaries_dir = Path(settings.get("SUMMARIES_DIR", "./data/summaries"))

    md_files = []
    if summaries_dir.exists():
        for file_path in sorted(summaries_dir.glob("*.md")):
            stat = file_path.stat()

            md_files.append(
                {
                    "filename": file_path.name,
                    "size": stat.st_size,
                    "size_human": _format_file_size(stat.st_size),
                    "modified": stat.st_mtime,
                    "created_at": datetime.fromtimestamp(stat.st_ctime),
                }
            )

    return render_template("user/summaries.html", summaries=md_files)


@user_bp.route("/summaries/<path:filename>/edit")
@auth_required
def edit_my_summary(filename):
    """Summary-Datei bearbeiten"""
    from pathlib import Path

    db = get_db_service()
    settings = SettingsService(db.get_session())
    summaries_dir = Path(settings.get("SUMMARIES_DIR", "./data/summaries"))

    file_path = summaries_dir / filename

    if (
        not file_path.exists()
        or not file_path.suffix == ".md"
        or not str(file_path).startswith(str(summaries_dir))
    ):
        flash("Datei nicht gefunden")
        return redirect(url_for("user.my_summaries"))

    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception as e:
        flash(f"Fehler beim Lesen: {e!s}")
        content = ""

    return render_template("user/edit_summary.html", filename=filename, content=content)


@user_bp.route("/summaries/<path:filename>/save", methods=["POST"])
@auth_required
def save_my_summary(filename):
    """Summary-Datei speichern"""
    from pathlib import Path

    db = get_db_service()
    settings = SettingsService(db.get_session())
    summaries_dir = Path(settings.get("SUMMARIES_DIR", "./data/summaries"))

    file_path = summaries_dir / filename

    if (
        not str(file_path).startswith(str(summaries_dir))
        or not file_path.suffix == ".md"
    ):
        return jsonify({"success": False, "error": "Ungültige Datei"}), 400

    data = request.get_json()
    content = data.get("content", "")

    try:
        file_path.write_text(content, encoding="utf-8")
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@user_bp.route("/summaries/<path:filename>/delete", methods=["POST"])
@auth_required
def delete_my_summary(filename):
    """Summary-Datei löschen"""
    from pathlib import Path

    db = get_db_service()
    settings = SettingsService(db.get_session())
    summaries_dir = Path(settings.get("SUMMARIES_DIR", "./data/summaries"))

    file_path = summaries_dir / filename

    if (
        not str(file_path).startswith(str(summaries_dir))
        or not file_path.suffix == ".md"
    ):
        return jsonify({"success": False, "error": "Ungültige Datei"}), 400

    try:
        if file_path.exists():
            file_path.unlink()
            logger.info(f"Summary-Datei gelöscht: {filename}")

        db.delete_summary_by_filename(filename)

        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"Fehler beim Löschen von {filename}: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@user_bp.route("/summaries/<path:filename>/download-md", methods=["GET"])
@auth_required
def download_summary_as_md(filename):
    """Download Summary als Markdown-Datei."""
    db = get_db_service()
    settings = SettingsService(db.get_session())
    summaries_dir = Path(settings.get("SUMMARIES_DIR", "./data/summaries")).resolve()

    file_path = (summaries_dir / filename).resolve()

    if not str(file_path).startswith(str(summaries_dir)) or file_path.suffix != ".md":
        return jsonify({"success": False, "error": "Ungültige Datei"}), 400

    if not file_path.exists():
        flash("Datei nicht gefunden")
        return redirect(url_for("user.my_summaries"))

    return send_file(
        str(file_path),
        as_attachment=True,
        download_name=filename,
        mimetype="text/markdown",
    )


@user_bp.route("/summaries/<path:filename>/download-docx", methods=["GET"])
@auth_required
def download_summary_as_docx(filename):
    """Download Summary als DOCX mit Formatierung, das Markdown wie die
    EasyMDE-Vorschau rendert (Tabellen, Code-Blöcke, Listen, Links, Strike, ...).

    Verwendet markdown-it-py (gleiche CommonMark/GFM-Spec wie marked in der
    Vorschau), damit das DOCX optisch der Markdown-Vorschau entspricht."""
    import tempfile

    from bs4 import BeautifulSoup, NavigableString, Tag
    from docx import Document
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.shared import Pt, RGBColor
    from markdown_it import MarkdownIt

    db = get_db_service()
    settings = SettingsService(db.get_session())
    summaries_dir = Path(settings.get("SUMMARIES_DIR", "./data/summaries"))

    file_path = summaries_dir / filename

    if (
        not str(file_path).startswith(str(summaries_dir))
        or not file_path.suffix == ".md"
    ):
        return send_file(
            "/static/images/error.png",
            mimetype="image/png",
        ), 404

    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception as e:
        logger.error(f"Fehler beim Lesen von {filename}: {e}")
        flash(f"Fehler beim Lesen: {e!s}")
        return redirect(url_for("user.my_summaries"))

    # Markdown -> HTML via markdown-it-py (gfm-commonmark + table + strikethrough),
    # dieselbe Spec wie marked in der EasyMDE-Vorschau.
    md = MarkdownIt("commonmark", {"linkify": False, "html": False}).enable(
        ["table", "strikethrough"]
    )
    # GFM-Zeilenumbrüche: einzelner \n wird <br> (wie marked breaks:true).
    md.options["breaks"] = True
    html_body = md.render(content)

    # HTML -> DOCX via python-docx + BeautifulSoup
    doc = Document()

    # Basis-Stil etwas an Vorschau anpassen
    style = doc.styles["Normal"]
    style.font.size = Pt(11)
    style.font.name = "Calibri"

    soup = BeautifulSoup(html_body, "html.parser")

    def _add_runs_from_inline(paragraph, node, bold=False, italic=False, strike=False):
        """Rekursiv Inline-Knoten (strong/em/del/code/a/br/span/text) in Runs
        umwandeln, sodass Verschachtelung wie **_fett+kursiv_** erhalten bleibt."""
        if isinstance(node, NavigableString):
            text = str(node)
            if text:
                run = paragraph.add_run(text)
                run.bold = bold or None
                run.italic = italic or None
                run.font.strike = strike or None
            return
        if not isinstance(node, Tag):
            return
        name = node.name
        if name == "br":
            paragraph.add_run().add_break()
            return
        if name in ("strong", "b"):
            bold = True
        elif name in ("em", "i"):
            italic = True
        elif name in ("del", "s", "strike"):
            strike = True
        elif name == "code":
            for child in node.children:
                if isinstance(child, NavigableString):
                    run = paragraph.add_run(str(child))
                    run.bold = bold or None
                    run.italic = italic or None
                    run.font.strike = strike or None
                    run.font.name = "Consolas"
                    run.font.size = Pt(10)
                else:
                    _add_runs_from_inline(paragraph, child, bold, italic, strike)
            return
        elif name == "a":
            text = node.get_text()
            run = paragraph.add_run(text)
            run.bold = bold or None
            run.italic = italic or None
            run.font.strike = strike or None
            run.font.color.rgb = RGBColor(0x33, 0x41, 0x55)
            run.underline = True
            return
        for child in node.children:
            _add_runs_from_inline(paragraph, child, bold, italic, strike)

    def _render_list(list_el, doc, depth=0):
        """Rendert eine <ul>/<ol> inkl. verschachtelter Listen."""
        is_ordered = list_el.name == "ol"
        for li in list_el.find_all("li", recursive=False):
            style_name = "List Number" if is_ordered else "List Bullet"
            para = doc.add_paragraph(style=style_name)
            for child in li.children:
                if isinstance(child, Tag) and child.name in ("ul", "ol"):
                    _render_list(child, doc, depth + 1)
                else:
                    _add_runs_from_inline(para, child)

    def _render_block(element, doc):
        """Rendert einen Block-Level-Knoten rekursiv."""
        if isinstance(element, NavigableString):
            if str(element).strip():
                para = doc.add_paragraph()
                _add_runs_from_inline(para, element)
            return
        if not isinstance(element, Tag):
            return

        if element.name in ("h1", "h2", "h3", "h4", "h5", "h6"):
            level = int(element.name[1])
            para = doc.add_heading(level=level)
            _add_runs_from_inline(para, element)

        elif element.name == "p":
            para = doc.add_paragraph()
            _add_runs_from_inline(para, element)

        elif element.name in ("ul", "ol"):
            _render_list(element, doc)

        elif element.name == "pre":
            code = element.find("code")
            text = code.get_text() if code else element.get_text()
            para = doc.add_paragraph()
            run = para.add_run(text.rstrip("\n"))
            run.font.name = "Consolas"
            run.font.size = Pt(10)
            # Leichte Hintergrundschattierung über Absatz-Eigenschaften ist
            # in python-docx aufwendig; wir belassen es bei der Schriftart.

        elif element.name == "blockquote":
            para = doc.add_paragraph(style="Intense Quote")
            for child in element.children:
                if isinstance(child, Tag) and child.name == "p":
                    _add_runs_from_inline(para, child)
                elif isinstance(child, NavigableString) and str(child).strip():
                    _add_runs_from_inline(para, child)
            # Weitere Block-Typen innerhalb von blockquote (Listen etc.)
            # rekursiv anhängen.
            for child in element.children:
                if isinstance(child, Tag) and child.name not in ("p",):
                    _render_block(child, doc)

        elif element.name == "hr":
            doc.add_page_break()

        elif element.name == "table":
            rows = element.find_all("tr", recursive=False)
            if not rows:
                # markdown-it packt <thead>/<tbody> um die <tr>
                thead = element.find("thead")
                tbody = element.find("tbody")
                rows = []
                if thead:
                    rows += thead.find_all("tr", recursive=False)
                if tbody:
                    rows += tbody.find_all("tr", recursive=False)
            if not rows:
                return
            num_cols = max(
                len(tr.find_all(["th", "td"], recursive=False)) for tr in rows
            )
            table = doc.add_table(rows=0, cols=num_cols, style="Table Grid")
            for tr in rows:
                row = table.add_row()
                cells = tr.find_all(["th", "td"], recursive=False)
                for cell_idx, cell in enumerate(cells):
                    if cell_idx >= num_cols:
                        break
                    cell_el = row.cells[cell_idx]
                    # Zelleninhalt als eigener Absatz mit Inline-Formatierung
                    cell_el.text = ""
                    para = cell_el.paragraphs[0]
                    _add_runs_from_inline(para, cell)
                    if cell.name == "th":
                        for paragraph in cell_el.paragraphs:
                            for run in paragraph.runs:
                                run.bold = True
            table.alignment = WD_TABLE_ALIGNMENT.CENTER

        elif element.name in ("div", "section", "article", "main", "thead", "tbody"):
            # Block-Container: Kinder rekursiv rendern (vorher wurde Inhalt
            # verworfen, was zu fehlenden Abschnitten im DOCX führte).
            for child in element.children:
                _render_block(child, doc)

        else:
            para = doc.add_paragraph()
            _add_runs_from_inline(para, element)

    for element in soup.children:
        _render_block(element, doc)

    # Temporäre Datei erstellen
    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
        doc.save(tmp.name)
        filepath = tmp.name

    try:
        return send_file(
            filepath,
            as_attachment=True,
            download_name=filename.replace(".md", ".docx"),
            mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    finally:
        try:
            os.unlink(filepath)
        except Exception:
            pass


def _format_file_size(size_bytes):
    """Hilfsfunktion für Dateigrößen-Formatierung"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
