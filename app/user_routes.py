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

from logging import getLogger
from pathlib import Path
from flask import (
    Blueprint,
    render_template,
    request,
    jsonify,
    current_app,
    redirect,
    url_for,
    flash,
)
from werkzeug.security import generate_password_hash, check_password_hash
from qdrant_client import models

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
                        "content_preview": f"[Fehler: {str(e)}]",
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
            return jsonify({"success": False, "error": f"Qdrant Fehler: {str(e)}"}), 500

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
    from app.vector import DocumentIngestion
    from app import wait_for_resources

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
        flash(f"Fehler beim Laden der Dokumente: {str(e)}")

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
        flash(f"Fehler beim Laden des Dokuments: {str(e)}")
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

        client.delete(
            collection_name=COLLECTION_NAME,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="filename", match=models.MatchValue(value=filename)
                        )
                    ]
                )
            ),
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
        flash(f"Fehler beim Laden der Collection: {str(e)}")

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
    "EMBEDDING_SOURCE": [("local", "Lokal"), ("endpoint", "Remote Endpoint")]
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
# SUMMARIES MANAGEMENT
# =============================================================================


@user_bp.route("/summaries")
@auth_required
def my_summaries():
    """Alle Summary-Dateien anzeigen"""
    from pathlib import Path

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
        flash(f"Fehler beim Lesen: {str(e)}")
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


def _format_file_size(size_bytes):
    """Hilfsfunktion für Dateigrößen-Formatierung"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
