"""
Admin Routes für Qdrant Vektor-DB Verwaltung
"""
import os
from pathlib import Path
from flask import Blueprint, render_template, request, jsonify, session, current_app, redirect, url_for, flash
from functools import wraps
from qdrant_client import models

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
    """Decorator: Nur admin-User erlaubt"""
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get('user') != 'admin':
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
    """Dokumente listen mit Pagination"""
    client = current_app.extensions.get("client")
    if not client:
        flash('Qdrant Client nicht initialisiert')
        return redirect(url_for('admin.index'))

    # Pagination
    limit = request.args.get('limit', 20, type=int)
    offset = request.args.get('offset', None)
    filename_filter = request.args.get('filename', '').strip()

    try:
        # Build filter if filename provided
        scroll_filter = None
        if filename_filter:
            scroll_filter = models.Filter(
                must=[
                    models.FieldCondition(
                        key="filename",
                        match=models.MatchValue(value=filename_filter)
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
            documents.append({
                'id': str(point.id),
                'filename': payload.get('filename', 'N/A'),
                'source': payload.get('source', 'N/A'),
                'content_preview': (payload.get('page_content', '') or payload.get('original_content', ''))[:50] + '...',
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
    """Dokument löschen"""
    client = current_app.extensions.get("client")
    if not client:
        return jsonify({'success': False, 'error': 'Qdrant Client nicht initialisiert'}), 500

    try:
        client.delete(
            collection_name=COLLECTION_NAME,
            points_selector=models.PointIdsList(points=[doc_id])
        )
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/documents/batch-delete', methods=['POST'])
@admin_required
def batch_delete():
    """Alle Dokumente eines Filenames löschen"""
    client = current_app.extensions.get("client")
    if not client:
        return jsonify({'success': False, 'error': 'Qdrant Client nicht initialisiert'}), 500

    data = request.get_json()
    filename = data.get('filename')

    if not filename:
        return jsonify({'success': False, 'error': 'Filename erforderlich'}), 400

    try:
        client.delete(
            collection_name=COLLECTION_NAME,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="filename",
                            match=models.MatchValue(value=filename)
                        )
                    ]
                )
            )
        )
        return jsonify({'success': True})
    except Exception as e:
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
            vectors_config=models.VectorParams(
                size=embedding_dim,
                distance=models.Distance.COSINE
            ),
            sparse_vectors_config={
                "langchain-sparse": models.SparseVectorParams()
            },
            hnsw_config=models.HnswConfigDiff(
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
        # XLSX/XLS/CSV → DATA_DIR (sofort verfügbar für Pandas)
        elif ext in ['.xlsx', '.xls', '.csv']:
            data_dir = os.getenv('DATA_DIR', './data')
            # Absoluter Pfad falls relativ
            if not Path(data_dir).is_absolute():
                target_dir = project_root / data_dir
            else:
                target_dir = Path(data_dir)
            target_dir.mkdir(parents=True, exist_ok=True)
            filepath = target_dir / file.filename
            file.save(filepath)
            saved_files['data'].append(file.filename)

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