"""
Admin Routes für Qdrant Vektor-DB Verwaltung
"""
from flask import Blueprint, render_template, request, jsonify, session, current_app, redirect, url_for, flash
from functools import wraps
from qdrant_client import models

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


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
            'vectors_count': collection.vectors_count,
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
                'content_preview': (payload.get('page_content', '') or payload.get('original_content', ''))[:200] + '...',
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