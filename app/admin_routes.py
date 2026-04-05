"""
Admin Routes für Qdrant Vektor-DB Verwaltung, User Management und Settings
"""
import os
from pathlib import Path
from flask import Blueprint, render_template, request, jsonify, session, current_app, redirect, url_for, flash
from functools import wraps
from werkzeug.security import generate_password_hash
from qdrant_client import models as qdrant_models

from app.database_service import get_db_service
from app.settings_service import SettingsService

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

# Upload-Status-Tracking (global für asynchrone Ingestion)
_upload_status = {
    'is_ingesting': False,
    'pending_files': [],      # Dateien im ./files/ Ordner (warten auf Ingestion)
    'data_files': [],         # Dateien in DATA_DIR (sofort verfügbar)
    'error': None,
    'current_file': None,
    'processed_count': 0,
    'total_count': 0
}


def admin_required(f):
    """Decorator: Nur admin-User erlaubt - prüft anhand DB, nicht nur Session-Username"""
    @wraps(f)
    def decorated(*args, **kwargs):
        username = session.get('user')
        if not username:
            flash('Bitte zuerst anmelden')
            return redirect(url_for('main.login'))
        
        # User aus DB prüfen (nicht nur Session-Name)
        db = get_db_service()
        user = db.get_user_by_username(username)
        if not user or not user.is_admin:
            flash('Admin-Zugriff erforderlich')
            return redirect(url_for('main.login'))
        
        return f(*args, **kwargs)
    return decorated


COLLECTION_NAME = "local_rag"


@admin_bp.route('/')
@admin_required
def index():
    """Dashboard mit Collection-Info"""
    client = current_app.extensions.get("client")
    if not client:
        flash('Qdrant Client nicht initialisiert')
        return redirect(url_for('main.index'))

    try:
        collection = client.get_collection(COLLECTION_NAME)
        stats = {
            'name': COLLECTION_NAME,
            'points_count': collection.points_count,
            'vectors_count': getattr(collection, 'indexed_vectors_count', collection.points_count) or 0,
            'status': collection.status.value if hasattr(collection.status, 'value') else str(collection.status),
            'config': {
                'size': collection.config.params.vectors.size if hasattr(collection.config.params.vectors, 'size') else 'N/A',
                'distance': collection.config.params.vectors.distance.value if hasattr(collection.config.params.vectors, 'distance') else 'N/A'
            }
        }
    except Exception as e:
        stats = None
        flash(f'Fehler beim Laden der Collection: {str(e)}')

    return render_template('admin/index.html', stats=stats, username=session.get('user'))


@admin_bp.route('/documents')
@admin_required
def documents():
    """Dokumente listen mit Pagination und Datei-Status"""
    client = current_app.extensions.get("client")
    if not client:
        flash('Qdrant Client nicht initialisiert')
        return redirect(url_for('admin.index'))

    # Pagination
    limit = request.args.get('limit', 20, type=int)
    offset = request.args.get('offset', None)
    filename_filter = request.args.get('filename', '').strip()
    
    # Filter nach Datei-Status
    file_status_filter = request.args.get('file_status', '').strip()

    try:
        # Build filter if filename provided
        scroll_filter = None
        if filename_filter:
            scroll_filter = qdrant_models.Filter(
                must=[
                    qdrant_models.FieldCondition(
                        key="filename",
                        match=qdrant_models.MatchValue(value=filename_filter)
                    )
                ]
            )

        # Scroll through collection
        result = client.scroll(
            collection_name=COLLECTION_NAME,
            limit=limit,
            offset=offset,
            with_payload=True,
            with_vectors=False,
            scroll_filter=scroll_filter
        )

        points, next_offset = result

        documents = []
        for point in points:
            payload = point.payload or {}
            filename = payload.get('filename', 'N/A')
            
            # Prüfen ob zugehörige Datei existiert
            from app.utils.file_manager import check_data_file_exists
            has_data_file = check_data_file_exists(filename) if filename != 'N/A' else False
            
            # Filter nach Datei-Status
            if file_status_filter:
                if file_status_filter == 'has_file' and not has_data_file:
                    continue
                if file_status_filter == 'no_file' and has_data_file:
                    continue
            
            documents.append({
                'id': str(point.id),
                'filename': filename,
                'source': payload.get('source', 'N/A'),
                'content_preview': (payload.get('page_content', '') or payload.get('original_content', ''))[:50] + '...',
                'has_data_file': has_data_file
            })

        # Get unique filenames for filter dropdown
        all_points, _ = client.scroll(
            collection_name=COLLECTION_NAME,
            limit=1000,
            with_payload=True,
            with_vectors=False
        )
        filenames = sorted(set(
            p.payload.get('filename', 'N/A') for p in all_points if p.payload
        ))

    except Exception as e:
        documents = []
        next_offset = None
        filenames = []
        flash(f'Fehler beim Laden der Dokumente: {str(e)}')

    return render_template(
        'admin/documents.html',
        documents=documents,
        next_offset=next_offset,
        filenames=filenames,
        current_filter=filename_filter,
        file_status_filter=file_status_filter,
        limit=limit,
        username=session.get('user')
    )


@admin_bp.route('/documents/<doc_id>')
@admin_required
def document_detail(doc_id):
    """Einzelnes Dokument anzeigen"""
    client = current_app.extensions.get("client")
    if not client:
        flash('Qdrant Client nicht initialisiert')
        return redirect(url_for('admin.index'))

    try:
        result = client.retrieve(
            collection_name=COLLECTION_NAME,
            ids=[doc_id],
            with_payload=True,
            with_vectors=False
        )

        if not result:
            flash('Dokument nicht gefunden')
            return redirect(url_for('admin.documents'))

        point = result[0]
        payload = point.payload or {}

        document = {
            'id': str(point.id),
            'page_content': payload.get('page_content', ''),
            'original_content': payload.get('original_content', ''),
            'metadata': {k: v for k, v in payload.items() if k not in ['page_content', 'original_content']}
        }

    except Exception as e:
        flash(f'Fehler beim Laden des Dokuments: {str(e)}')
        return redirect(url_for('admin.documents'))

    return render_template('admin/document.html', document=document, username=session.get('user'))


@admin_bp.route('/documents/<doc_id>/delete', methods=['POST'])
@admin_required
def delete_document(doc_id):
    """Dokument löschen + zugehörige Datei automatisch mitlöschen"""
    client = current_app.extensions.get("client")
    if not client:
        return jsonify({'success': False, 'error': 'Qdrant Client nicht initialisiert'}), 500

    try:
        # Dokument vor dem Löschen holen für Datei-Löschung
        result = client.retrieve(
            collection_name=COLLECTION_NAME,
            ids=[doc_id],
            with_payload=True,
            with_vectors=False
        )
        
        payload = result[0].payload if result else None
        
        # Qdrant Dokument löschen
        client.delete(
            collection_name=COLLECTION_NAME,
            points_selector=qdrant_models.PointIdsList(points=[doc_id])
        )
        
        # Zugehörige Datei automatisch löschen
        if payload:
            from app.utils.file_manager import delete_associated_file
            deleted_file = delete_associated_file(payload)
            if deleted_file:
                logger.info(f"Zugehörige Datei zu Dokument {doc_id} gelöscht")
        
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Fehler beim Löschen von Dokument {doc_id}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/documents/batch-delete', methods=['POST'])
@admin_required
def batch_delete():
    """Alle Dokumente eines Filenames löschen + zugehörige Datei automatisch"""
    from logging import getLogger
    logger = getLogger(__name__)
    
    client = current_app.extensions.get("client")
    if not client:
        return jsonify({'success': False, 'error': 'Qdrant Client nicht initialisiert'}), 500

    data = request.get_json()
    filename = data.get('filename')

    if not filename:
        return jsonify({'success': False, 'error': 'Filename erforderlich'}), 400

    try:
        # Alle Dokumente mit diesem Filename holen für Datei-Löschung
        from app.utils.file_manager import delete_associated_file
        
        result = client.scroll(
            collection_name=COLLECTION_NAME,
            filter=qdrant_models.Filter(
                must=[
                    qdrant_models.FieldCondition(
                        key="filename",
                        match=qdrant_models.MatchValue(value=filename)
                    )
                ]
            ),
            limit=1000,
            with_payload=True,
            with_vectors=False
        )
        
        points, _ = result
        
        # Zugehörige Datei löschen (nur einmal, da alle denselben Filename haben)
        if points:
            payload = points[0].payload
            if payload:
                deleted = delete_associated_file(payload)
                if deleted:
                    logger.info(f"Zugehörige Datei zu Batch-Delete {filename} gelöscht")
        
        # Alle Dokumente aus Qdrant löschen
        client.delete(
            collection_name=COLLECTION_NAME,
            points_selector=qdrant_models.FilterSelector(
                filter=qdrant_models.Filter(
                    must=[
                        qdrant_models.FieldCondition(
                            key="filename",
                            match=qdrant_models.MatchValue(value=filename)
                        )
                    ]
                )
            )
        )
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Fehler beim Batch-Delete: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/clear', methods=['POST'])
@admin_required
def clear_all():
    """Alle Dokumente löschen (Collection leeren)"""
    client = current_app.extensions.get("client")
    if not client:
        return jsonify({'success': False, 'error': 'Qdrant Client nicht initialisiert'}), 500

    # Verify confirmation
    data = request.get_json()
    confirmation = data.get('confirmation', '')
    if confirmation != 'DELETE_ALL':
        return jsonify({'success': False, 'error': 'Bestätigung erforderlich'}), 400

    try:
        # Delete and recreate collection
        client.delete_collection(COLLECTION_NAME)

        # Recreate with same config
        embedding_dim = 384  # Default from app
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=qdrant_qdrant_models.VectorParams(
                size=embedding_dim,
                distance=qdrant_qdrant_models.Distance.COSINE
            ),
            sparse_vectors_config={
                "langchain-sparse": qdrant_qdrant_models.SparseVectorParams()
            },
            hnsw_config=qdrant_qdrant_models.HnswConfigDiff(            
m=16,
                ef_construct=100,
                full_scan_threshold=10000
            )
        )

        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/api/stats')
@admin_required
def api_stats():
    """API: Collection Stats"""
    client = current_app.extensions.get("client")
    if not client:
        return jsonify({'error': 'Qdrant Client nicht initialisiert'}), 500

    try:
        collection = client.get_collection(COLLECTION_NAME)
        return jsonify({
            'points_count': collection.points_count,
            'status': collection.status.value if hasattr(collection.status, 'value') else str(collection.status)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@admin_bp.route('/upload', methods=['GET', 'POST'])
@admin_required
def upload_files():
    """Dateien hochladen - GET zeigt Formular, POST verarbeitet Upload"""
    global _upload_status

    if request.method == 'GET':
        return render_template('admin/upload.html', status=_upload_status, username=session.get('user'))

    # POST: Dateien verarbeiten
    if _upload_status['is_ingesting']:
        return jsonify({'error': 'Ingestion läuft bereits, bitte warten'}), 409

    # Projekt-Root bestimmen (dort wo run.py liegt)
    project_root = Path(current_app.root_path).parent

    files = request.files.getlist('files')
    saved_files = {'pending': [], 'data': []}

    for file in files:
        if file.filename == '':
            continue

        ext = Path(file.filename).suffix.lower()

        # PDF/DOCX/DOC → ./files/ (werden ingested)
        if ext in ['.pdf', '.docx', '.doc']:
            target_dir = project_root / 'files'
            target_dir.mkdir(parents=True, exist_ok=True)
            filepath = target_dir / file.filename
            file.save(filepath)
            saved_files['pending'].append(file.filename)
        # XLSX/XLS/CSV → ./files/ (für Ingestion mit Beschreibung)
        elif ext in ['.xlsx', '.xls', '.csv']:
            target_dir = project_root / 'files'
            target_dir.mkdir(parents=True, exist_ok=True)
            filepath = target_dir / file.filename
            file.save(filepath)
            saved_files['pending'].append(file.filename)

    _upload_status['pending_files'].extend(saved_files['pending'])
    _upload_status['data_files'].extend(saved_files['data'])

    return jsonify({'success': True, 'files': saved_files})


def _run_ingestion():
    """Ingestion ausführen (synchron)"""
    global _upload_status
    try:
        from src.vector import DocumentIngestion
        ingest = DocumentIngestion()
        ingest.ingest_documents()
        _upload_status['pending_files'] = []
        _upload_status['error'] = None
    except Exception as e:
        _upload_status['error'] = str(e)
    finally:
        _upload_status['is_ingesting'] = False
        _upload_status['current_file'] = None


@admin_bp.route('/ingest', methods=['POST'])
@admin_required
def trigger_ingestion():
    """Ingestion synchron starten (blockiert bis Fertig)"""
    global _upload_status

    if _upload_status['is_ingesting']:
        return jsonify({'error': 'Ingestion läuft bereits'}), 409

    if not _upload_status['pending_files']:
        return jsonify({'error': 'Keine Dateien zum Verarbeiten'}), 400

    _upload_status['is_ingesting'] = True
    _upload_status['error'] = None
    _upload_status['processed_count'] = 0
    _upload_status['total_count'] = len(_upload_status['pending_files'])

    # Synchron ausführen (blockiert bis fertig)
    _run_ingestion()

    if _upload_status.get('error'):
        return jsonify({'success': False, 'error': _upload_status['error']}), 500

    return jsonify({'success': True, 'message': 'Ingestion abgeschlossen'})


@admin_bp.route('/upload/status')
@admin_required
def upload_status_api():
    """Current upload status für Polling"""
    return jsonify(_upload_status)


@admin_bp.route('/upload/clear', methods=['POST'])
@admin_required
def clear_pending():
    """Leert die Liste der wartenden Dateien (ohne Ingestion)"""
    global _upload_status
    _upload_status['pending_files'] = []
    _upload_status['data_files'] = []
    return jsonify({'success': True})


# =============================================================================
# USER MANAGEMENT
# =============================================================================

@admin_bp.route('/users')
@admin_required
def users():
    """User-Liste anzeigen"""
    db = get_db_service()
    users = db.list_users()
    return render_template('admin/users.html', users=users, username=session.get('user'))


@admin_bp.route('/users', methods=['POST'])
@admin_required
def create_user():
    """Neuen User anlegen"""
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '')
    is_admin = data.get('is_admin', False)
    
    if not username or not password:
        return jsonify({'success': False, 'error': 'Username und Passwort erforderlich'}), 400
    
    db = get_db_service()
    
    # Prüfen ob User bereits existiert
    existing = db.get_user_by_username(username)
    if existing:
        return jsonify({'success': False, 'error': 'Username bereits vergeben'}), 400
    
    try:
        user = db.create_user(username, password, is_admin)
        return jsonify({
            'success': True,
            'user': {
                'id': user.id,
                'username': user.username,
                'is_admin': user.is_admin,
                'created_at': user.created_at.isoformat() if user.created_at else None
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/users/<int:user_id>', methods=['DELETE'])
@admin_required
def delete_user(user_id):
    """User löschen - Dokumente werden dem Admin übertragen"""
    db = get_db_service()
    
    # Prüfen dass man sich nicht selbst löscht
    current_username = session.get('user')
    current_user = db.get_user_by_username(current_username)
    if current_user and current_user.id == user_id:
        return jsonify({'success': False, 'error': 'Sie können sich nicht selbst löschen'}), 400
    
    success = db.delete_user(user_id, transfer_to_admin=True)
    if success:
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'User nicht gefunden'}), 404


@admin_bp.route('/users/<int:user_id>/toggle-admin', methods=['POST'])
@admin_required
def toggle_admin(user_id):
    """Admin-Status toggeln"""
    db = get_db_service()
    
    # Prüfen dass man sich nicht selbst entadministriert
    current_username = session.get('user')
    current_user = db.get_user_by_username(current_username)
    if current_user and current_user.id == user_id:
        return jsonify({'success': False, 'error': 'Sie können Ihren eigenen Admin-Status nicht ändern'}), 400
    
    user = db.toggle_admin(user_id)
    if user:
        return jsonify({
            'success': True,
            'is_admin': user.is_admin
        })
    return jsonify({'success': False, 'error': 'User nicht gefunden'}), 404


@admin_bp.route('/users/<int:user_id>/reset-password', methods=['POST'])
@admin_required
def reset_user_password(user_id):
    """User-Passwort zurücksetzen"""
    data = request.get_json()
    new_password = data.get('password', '')
    
    if not new_password or len(new_password) < 4:
        return jsonify({'success': False, 'error': 'Passwort muss mindestens 4 Zeichen haben'}), 400
    
    db = get_db_service()
    
    try:
        # User holen
        user = db.get_user_by_id(user_id)
        if not user:
            return jsonify({'success': False, 'error': 'User nicht gefunden'}), 404
        
        # Passwort aktualisieren
        db_session = db.get_session()
        from app.models import User
        user_obj = db_session.query(User).filter_by(id=user_id).first()
        if user_obj:
            user_obj.password_hash = generate_password_hash(new_password)
            db_session.commit()
            db_session.close()
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': 'User nicht gefunden'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# =============================================================================
# SETTINGS PANEL
# =============================================================================

SELECT_OPTIONS = {
    'EMBEDDING_SOURCE': [
        ('local', 'Lokal (HuggingFace)'),
        ('endpoint', 'Remote Endpoint')
    ],
    'QDRANT_LOCAL': [
        ('true', 'Lokal (.db Datei)'),
        ('false', 'Remote Server')
    ]
}

DEPENDENT_FIELDS = {
    'EMBEDDING_SOURCE': {
        'show_when': 'endpoint',
        'fields': ['EMBEDDING_ENDPOINT']
    },
    'QDRANT_LOCAL': {
        'show_when': 'false',
        'fields': ['QDRANT_HOST', 'QDRANT_PORT', 'QDRANT_API_KEY']
    }
}


@admin_bp.route('/settings', methods=['GET'])
@admin_required
def settings():
    """Settings-Panel anzeigen"""
    db = get_db_service()
    settings_svc = SettingsService(db.get_session())
    
    settings_by_category = settings_svc.get_all_by_category()
    category_names = {cat: settings_svc.get_category_display_name(cat) 
                      for cat in settings_by_category.keys()}
    
    return render_template(
        'admin/settings.html',
        settings_by_category=settings_by_category,
        category_names=category_names,
        select_options=SELECT_OPTIONS,
        dependent_fields=DEPENDENT_FIELDS,
        username=session.get('user')
    )


@admin_bp.route('/settings', methods=['POST'])
@admin_required
def update_settings():
    """Settings speichern"""
    data = request.get_json()
    settings_dict = data.get('settings', {})
    
    if not settings_dict:
        return jsonify({'success': False, 'error': 'Keine Settings übergeben'}), 400
    
    db = get_db_service()
    settings_svc = SettingsService(db.get_session())
    
    try:
        settings_svc.set_batch(settings_dict)
        return jsonify({'success': True, 'updated': len(settings_dict)})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/settings/reset', methods=['POST'])
@admin_required
def reset_setting():
    """Einzelnes Setting auf Default zurücksetzen"""
    data = request.get_json()
    key = data.get('key')
    
    if not key:
        return jsonify({'success': False, 'error': 'Key erforderlich'}), 400
    
    db = get_db_service()
    settings_svc = SettingsService(db.get_session())
    
    success = settings_svc.reset_to_default(key)
    if success:
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Setting nicht gefunden'}), 404


@admin_bp.route('/settings/reset-category', methods=['POST'])
@admin_required
def reset_category():
    """Alle Settings einer Kategorie zurücksetzen"""
    data = request.get_json()
    category = data.get('category')

    if not category:
        return jsonify({'success': False, 'error': 'Kategorie erforderlich'}), 400

    db = get_db_service()
    settings_svc = SettingsService(db.get_session())

    count = settings_svc.reset_category(category)
    return jsonify({'success': True, 'reset_count': count})


@admin_bp.route('/settings/import-env', methods=['POST'])
@admin_required
def import_env_settings():
    """Aktuelle .env-Werte in DB importieren"""
    data = request.get_json()
    overwrite = data.get('overwrite', False)

    db = get_db_service()
    settings_svc = SettingsService(db.get_session())

    count = settings_svc.import_from_env(overwrite=overwrite)
    return jsonify({'success': True, 'imported': count})


# =============================================================================
# SUMMARIES MANAGEMENT
# =============================================================================

@admin_bp.route('/summaries')
@admin_required
def summaries():
    """Alle Summary-Dateien anzeigen (Admin)"""
    from pathlib import Path
    from app.utils.file_manager import get_data_file_info

    db = get_db_service()
    settings = SettingsService(db.get_session())
    summaries_dir = Path(settings.get('SUMMARIES_DIR', './summaries'))

    # Alle .md Dateien holen
    md_files = []
    if summaries_dir.exists():
        for file_path in sorted(summaries_dir.glob('*.md')):
            stat = file_path.stat()
            # DB-Eintrag suchen für User-Info
            db_summary = db.get_summary_by_filename(file_path.name)

            md_files.append({
                'filename': file_path.name,
                'size': stat.st_size,
                'size_human': _format_file_size(stat.st_size),
                'modified': stat.st_mtime,
                'user': db_summary.user.username if db_summary else 'Unbekannt',
                'user_id': db_summary.user_id if db_summary else None
            })

    return render_template('admin/summaries.html',
                         summaries=md_files,
                         username=session.get('user'))


@admin_bp.route('/summaries/<path:filename>/edit')
@admin_required
def edit_summary(filename):
    """Summary-Datei bearbeiten (Admin)"""
    from pathlib import Path

    db = get_db_service()
    settings = SettingsService(db.get_session())
    summaries_dir = Path(settings.get('SUMMARIES_DIR', './summaries'))

    file_path = summaries_dir / filename

    # Sicherheitscheck: Nur .md Dateien im summaries_dir
    if not file_path.exists() or not file_path.suffix == '.md' or not str(file_path).startswith(str(summaries_dir)):
        flash('Datei nicht gefunden')
        return redirect(url_for('admin.summaries'))

    try:
        content = file_path.read_text(encoding='utf-8')
    except Exception as e:
        flash(f'Fehler beim Lesen: {str(e)}')
        content = ''

    # DB-Eintrag für User-Info
    db_summary = db.get_summary_by_filename(filename)

    return render_template('admin/edit_summary.html',
                         filename=filename,
                         content=content,
                         user=db_summary.user.username if db_summary else 'Unbekannt',
                         username=session.get('user'))


@admin_bp.route('/summaries/<path:filename>/save', methods=['POST'])
@admin_required
def save_summary(filename):
    """Summary-Datei speichern (Admin)"""
    from pathlib import Path

    db = get_db_service()
    settings = SettingsService(db.get_session())
    summaries_dir = Path(settings.get('SUMMARIES_DIR', './summaries'))

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


@admin_bp.route('/summaries/<path:filename>/delete', methods=['POST'])
@admin_required
def delete_summary(filename):
    """Summary-Datei löschen (Admin)"""
    from pathlib import Path
    from logging import getLogger
    logger = getLogger(__name__)

    db = get_db_service()
    settings = SettingsService(db.get_session())
    summaries_dir = Path(settings.get('SUMMARIES_DIR', './summaries'))

    file_path = summaries_dir / filename

    # Sicherheitscheck
    if not str(file_path).startswith(str(summaries_dir)) or not file_path.suffix == '.md':
        return jsonify({'success': False, 'error': 'Ungültige Datei'}), 400

    try:
        # Datei löschen
        if file_path.exists():
            file_path.unlink()
            logger.info(f"Summary-Datei gelöscht: {filename}")

        # DB-Eintrag löschen
        db.delete_summary_by_filename(filename)

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