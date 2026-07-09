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
User Routes für Dokumentenverwaltung (nur eigene Dokumente)
Normale User können hier ihre Dokumente hochladen und verwalten
"""
import os
from logging import getLogger
from pathlib import Path
from flask import Blueprint, render_template, request, jsonify, session, current_app, redirect, url_for, flash
from functools import wraps
from werkzeug.security import check_password_hash
from qdrant_client import models

from app.database_service import get_db_service

logger = getLogger(__name__)

user_bp = Blueprint('user', __name__, url_prefix='/user')


def login_required(f):
    """Decorator: Login erforderlich"""
    @wraps(f)
    def decorated(*args, **kwargs):
        username = session.get('user')
        if not username:
            flash('Bitte zuerst anmelden')
            return redirect(url_for('main.login'))
        
        # User in DB prüfen
        db = get_db_service()
        user = db.get_user_by_username(username)
        if not user:
            session.clear()
            flash('Session ungültig')
            return redirect(url_for('main.login'))
        
        return f(*args, **kwargs)
    return decorated


COLLECTION_NAME = "local_rag"


@user_bp.route('/documents')
@login_required
def my_documents():
    """User sieht nur seine eigenen Dokumente"""
    db = get_db_service()
    username = session.get('user')
    user = db.get_user_by_username(username)
    
    if not user:
        flash('User nicht gefunden')
        return redirect(url_for('main.login'))
    
    # Dokumente aus DB holen
    user_docs = db.get_user_documents(user.id)
    
    # Metadaten aus Qdrant ergänzen
    client = current_app.extensions.get("client")
    documents = []
    
    if client:
        for user_doc in user_docs:
            try:
                # Eine Datei erzeugt mehrere Qdrant-Punkte (Chunks); document_id
                # ist die gemeinsame file_group_id, daher Filter statt Punkt-ID.
                points, _ = client.scroll(
                    collection_name=COLLECTION_NAME,
                    scroll_filter=models.Filter(
                        must=[models.FieldCondition(
                            key="file_group_id",
                            match=models.MatchValue(value=user_doc.document_id)
                        )]
                    ),
                    limit=1,
                    with_payload=True,
                    with_vectors=False
                )
                if points:
                    payload = points[0].payload or {}

                    # Prüfen ob zugehörige Datei existiert
                    from app.utils.file_manager import check_data_file_exists
                    has_data_file = check_data_file_exists(user_doc.filename)
                    
                    documents.append({
                        'id': user_doc.id,  # UserDocument ID
                        'document_id': user_doc.document_id,  # Qdrant ID
                        'filename': user_doc.filename,
                        'uploaded_at': user_doc.uploaded_at,
                        'content_preview': (payload.get('page_content', '') or payload.get('original_content', ''))[:100] + '...',
                        'source': payload.get('source', 'N/A'),
                        'has_data_file': has_data_file
                    })
                else:
                    # Dokument in Qdrant nicht mehr vorhanden
                    documents.append({
                        'id': user_doc.id,
                        'document_id': user_doc.document_id,
                        'filename': user_doc.filename,
                        'uploaded_at': user_doc.uploaded_at,
                        'content_preview': '[Nicht mehr in Qdrant]',
                        'source': 'N/A'
                    })
            except Exception as e:
                documents.append({
                    'id': user_doc.id,
                    'document_id': user_doc.document_id,
                    'filename': user_doc.filename,
                    'uploaded_at': user_doc.uploaded_at,
                    'content_preview': f'[Fehler: {str(e)}]',
                    'source': 'N/A'
                })
    
    return render_template('user/documents.html', 
                         documents=documents, 
                         username=username)


@user_bp.route('/documents/upload', methods=['GET', 'POST'])
@login_required
def upload_document():
    """User lädt Dokument hoch - wird für alle verfügbar"""
    if request.method == 'GET':
        return render_template('user/upload.html', username=session.get('user'))
    
    # POST: Datei verarbeiten
    db = get_db_service()
    username = session.get('user')
    user = db.get_user_by_username(username)
    
    if not user:
        return jsonify({'success': False, 'error': 'User nicht gefunden'}), 401
    
    project_root = Path(current_app.root_path).parent
    files = request.files.getlist('files')
    
    saved_files = []
    
    for file in files:
        if file.filename == '':
            continue

        ext = Path(file.filename).suffix.lower()

        # Nur PDF/DOCX/DOC/XLSX/XLS/CSV erlauben
        allowed_exts = ['.pdf', '.docx', '.doc', '.xlsx', '.xls', '.csv']
        if ext not in allowed_exts:
            continue

        # Pro-Nutzer-Unterverzeichnis (im app-data-Volume), damit Uploads
        # verschiedener Nutzer mit gleichem Dateinamen sich nicht in die Quere
        # kommen (fruehere Ursache fuer faelschliche "existiert bereits"-Fehler).
        target_dir = project_root / 'data' / 'files' / str(user.id)
        target_dir.mkdir(parents=True, exist_ok=True)
        filepath = target_dir / file.filename

        # Bereits ingestierte (verarbeitete) Dokumente dieses Nutzers liegen im
        # Archiv unter demselben relativen Pfad - nur dort wirklich blocken,
        # da das ein committetes Dokument in der Wissensbasis ist.
        processed_path = project_root / 'data' / 'processed_files' / str(user.id) / file.filename
        if processed_path.exists():
            return jsonify({
                'success': False,
                'error': f'Datei "{file.filename}" wurde bereits hochgeladen und verarbeitet. '
                         f'Bitte zuerst das bestehende Dokument löschen, um es zu ersetzen.'
            }), 409

        # Eine noch nicht ingestierte eigene Datei mit demselben Namen darf
        # anstandslos ueberschrieben werden - es wurde noch nichts in die
        # Wissensbasis uebernommen.
        file.save(filepath)
        saved_files.append(file.filename)

    if saved_files:
        return jsonify({
            'success': True, 
            'files': saved_files,
            'message': f'{len(saved_files)} Datei(en) hochgeladen. Bitte Ingestion starten.'
        })
    
    return jsonify({'success': False, 'error': 'Keine gültigen Dateien'}), 400


@user_bp.route('/documents/<int:doc_id>/delete', methods=['POST'])
@login_required
def delete_my_document(doc_id):
    """User löscht eigenes Dokument + zugehörige Datei automatisch"""
    from logging import getLogger
    logger = getLogger(__name__)
    
    db = get_db_service()
    username = session.get('user')
    user = db.get_user_by_username(username)
    
    if not user:
        return jsonify({'success': False, 'error': 'User nicht gefunden'}), 401
    
    # UserDocument holen
    from app.models import UserDocument
    db_session = db.get_session()
    user_doc = db_session.query(UserDocument).filter_by(
        id=doc_id, 
        user_id=user.id
    ).first()
    
    if not user_doc:
        db_session.close()
        return jsonify({'success': False, 'error': 'Dokument nicht gefunden oder keine Berechtigung'}), 404
    
    # document_id ist die file_group_id, die alle Chunks dieser Datei teilen -
    # eine Datei erzeugt mehrere Qdrant-Punkte, daher Filter statt Punkt-ID.
    doc_filter = models.Filter(
        must=[models.FieldCondition(
            key="file_group_id",
            match=models.MatchValue(value=user_doc.document_id)
        )]
    )

    # Payload aus Qdrant holen für Datei-Löschung
    client = current_app.extensions.get("client")
    payload = None
    if client:
        try:
            points, _ = client.scroll(
                collection_name=COLLECTION_NAME,
                scroll_filter=doc_filter,
                limit=1,
                with_payload=True,
                with_vectors=False
            )
            if points:
                payload = points[0].payload
        except Exception as e:
            logger.error(f"Fehler beim Holen des Dokuments für Datei-Löschung: {e}")

    # Aus Qdrant löschen (alle Chunks dieser Datei)
    if client:
        try:
            client.delete(
                collection_name=COLLECTION_NAME,
                points_selector=models.FilterSelector(filter=doc_filter)
            )
        except Exception as e:
            db_session.close()
            return jsonify({'success': False, 'error': f'Qdrant Fehler: {str(e)}'}), 500
    
    # Zugehörige Datei automatisch löschen
    if payload:
        from app.utils.file_manager import delete_associated_file
        deleted = delete_associated_file(payload)
        if deleted:
            logger.info(f"Zugehörige Datei zu User-Dokument {doc_id} gelöscht")
    
    # Aus DB löschen
    db_session.delete(user_doc)
    db_session.commit()
    db_session.close()
    
    return jsonify({'success': True})


@user_bp.route('/documents/ingest', methods=['POST'])
@login_required
def trigger_ingestion():
    """User startet Ingestion der hochgeladenen Dateien"""
    from app.vector import DocumentIngestion
    from app import wait_for_resources

    # Ressourcen (Embedding-Modell) muessen bereit sein, bevor Ingestion laeuft.
    try:
        if not wait_for_resources(timeout=180):
            return jsonify({
                'success': False,
                'error': 'RAG-System wird noch initialisiert (Embedding-Modell '
                         'lädt). Bitte in wenigen Sekunden erneut versuchen.'
            }), 503
    except RuntimeError as e:
        return jsonify({'success': False, 'error': str(e)}), 503

    try:
        ingest = DocumentIngestion(
            embeddings=current_app.extensions.get("dense_embeddings"),
            sparse_embeddings=current_app.extensions.get("sparse_embeddings"),
        )
        ingest.ingest_documents()

        return jsonify({
            'success': True,
            'message': 'Ingestion erfolgreich'
        })
    except Exception as e:
        logger = getLogger(__name__)
        logger.error(f"Fehler bei der User-Ingestion: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# =============================================================================
# USER SUMMARIES MANAGEMENT
# =============================================================================

@user_bp.route('/summaries')
@login_required
def my_summaries():
    """Eigene Summary-Dateien anzeigen"""
    from pathlib import Path

    db = get_db_service()
    username = session.get('user')
    user = db.get_user_by_username(username)

    if not user:
        flash('User nicht gefunden')
        return redirect(url_for('main.login'))

    # Settings holen
    from app.settings_service import SettingsService
    settings = SettingsService(db.get_session())
    summaries_dir = Path(settings.get('SUMMARIES_DIR', './data/summaries'))

    # Eigene Summaries aus DB holen
    user_summaries = db.get_user_summaries(user.id)

    # Datei-Infos ergänzen
    md_files = []
    for summary in user_summaries:
        file_path = summaries_dir / summary.filename
        if file_path.exists():
            stat = file_path.stat()
            md_files.append({
                'filename': summary.filename,
                'size': stat.st_size,
                'size_human': _format_file_size(stat.st_size),
                'modified': stat.st_mtime,
                'created_at': summary.created_at
            })

    return render_template('user/summaries.html',
                         summaries=md_files,
                         username=username)


@user_bp.route('/summaries/<path:filename>/edit')
@login_required
def edit_my_summary(filename):
    """Eigene Summary-Datei bearbeiten"""
    from pathlib import Path

    db = get_db_service()
    username = session.get('user')
    user = db.get_user_by_username(username)

    if not user:
        flash('User nicht gefunden')
        return redirect(url_for('main.login'))

    # Berechtigung prüfen: User darf nur eigene Dateien bearbeiten
    db_summary = db.get_summary_by_filename(filename)
    if not db_summary or db_summary.user_id != user.id:
        flash('Keine Berechtigung für diese Datei')
        return redirect(url_for('user.my_summaries'))

    # Settings holen
    from app.settings_service import SettingsService
    settings = SettingsService(db.get_session())
    summaries_dir = Path(settings.get('SUMMARIES_DIR', './data/summaries'))

    file_path = summaries_dir / filename

    # Sicherheitscheck
    if not file_path.exists() or not file_path.suffix == '.md' or not str(file_path).startswith(str(summaries_dir)):
        flash('Datei nicht gefunden')
        return redirect(url_for('user.my_summaries'))

    try:
        content = file_path.read_text(encoding='utf-8')
    except Exception as e:
        flash(f'Fehler beim Lesen: {str(e)}')
        content = ''

    return render_template('user/edit_summary.html',
                         filename=filename,
                         content=content,
                         username=username)


@user_bp.route('/summaries/<path:filename>/save', methods=['POST'])
@login_required
def save_my_summary(filename):
    """Eigene Summary-Datei speichern"""
    from pathlib import Path

    db = get_db_service()
    username = session.get('user')
    user = db.get_user_by_username(username)

    if not user:
        return jsonify({'success': False, 'error': 'User nicht gefunden'}), 401

    # Berechtigung prüfen
    db_summary = db.get_summary_by_filename(filename)
    if not db_summary or db_summary.user_id != user.id:
        return jsonify({'success': False, 'error': 'Keine Berechtigung'}), 403

    # Settings holen
    from app.settings_service import SettingsService
    settings = SettingsService(db.get_session())
    summaries_dir = Path(settings.get('SUMMARIES_DIR', './data/summaries'))

    file_path = summaries_dir / filename

    # Sicherheitscheck
    if not str(file_path).startswith(str(summaries_dir)) or not file_path.suffix == '.md':
        return jsonify({'success': False, 'error': 'Ungültige Datei'}), 400

    data = request.get_json()
    content = data.get('content', '')

    try:
        file_path.write_text(content, encoding='utf-8')
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@user_bp.route('/summaries/<path:filename>/delete', methods=['POST'])
@login_required
def delete_my_summary(filename):
    """Eigene Summary-Datei löschen"""
    from pathlib import Path
    from logging import getLogger
    logger = getLogger(__name__)

    db = get_db_service()
    username = session.get('user')
    user = db.get_user_by_username(username)

    if not user:
        return jsonify({'success': False, 'error': 'User nicht gefunden'}), 401

    # Berechtigung prüfen: User darf nur eigene Dateien löschen
    db_summary = db.get_summary_by_filename(filename)
    if not db_summary or db_summary.user_id != user.id:
        return jsonify({'success': False, 'error': 'Keine Berechtigung'}), 403

    # Settings holen
    from app.settings_service import SettingsService
    settings = SettingsService(db.get_session())
    summaries_dir = Path(settings.get('SUMMARIES_DIR', './data/summaries'))

    file_path = summaries_dir / filename

    # Sicherheitscheck
    if not str(file_path).startswith(str(summaries_dir)) or not file_path.suffix == '.md':
        return jsonify({'success': False, 'error': 'Ungültige Datei'}), 400

    try:
        # Datei löschen
        if file_path.exists():
            file_path.unlink()
            logger.info(f"Eigene Summary-Datei gelöscht: {filename} (User: {username})")

        # DB-Eintrag löschen
        db.delete_summary_by_filename(filename, user_id=user.id)

        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Fehler beim Löschen von {filename}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


def _format_file_size(size_bytes):
    """Hilfsfunktion für Dateigrößen-Formatierung"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
