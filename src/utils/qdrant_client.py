"""
Qdrant Client Factory mit Unterstützung für lokale und remote Verbindungen
"""
import os
import time
from typing import Optional, Union
from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse


def get_qdrant_client(
    collection_name: str = "local_rag",
    force_local: bool = False,
    force_remote: bool = False,
    custom_host: Optional[str] = None,
    custom_port: Optional[int] = None,
    api_key: Optional[str] = None
) -> "QdrantClient":
    """
    Erstellt einen Qdrant-Client basierend auf Settings oder Parametern.
    
    Args:
        collection_name: Name der Collection (default: "local_rag")
        force_local: True = immer lokale DB verwenden (ignoriert Settings)
        force_remote: True = immer remote verwenden (ignoriert Settings)
        custom_host: Optionaler custom Host (überschreibt Settings)
        custom_port: Optionaler custom Port (überschreibt Settings)
        api_key: Optionaler API-Key für gesicherte Remote-Qdrant
    
    Returns:
        QdrantClient: Konfigurierter Client
    """
    # Priorität: force_local/force_remote > Settings > Environment > Default
    if force_local:
        return QdrantClient(path="./local_qdrant.db")
    
    if force_remote:
        host = custom_host or os.getenv("QDRANT_HOST", "localhost")
        port = custom_port or int(os.getenv("QDRANT_PORT", 6333))
        key = api_key or os.getenv("QDRANT_API_KEY")
        
        if key:
            return QdrantClient(host=host, port=port, api_key=key)
        return QdrantClient(host=host, port=port)
    
    # Versuche Settings aus DB zu laden (für App-Context)
    try:
        from app.database_service import get_db_service
        from app.settings_service import SettingsService
        
        db = get_db_service()
        db_session = db.get_session()
        settings = SettingsService(db_session)
        
        is_local = settings.get_bool('QDRANT_LOCAL', True)
        host = custom_host or settings.get('QDRANT_HOST', 'localhost')
        port = custom_port or settings.get_int('QDRANT_PORT', 6333)
        key = api_key or settings.get('QDRANT_API_KEY')
        
        db_session.close()
        
        if is_local:
            return QdrantClient(path="./local_qdrant.db")
        else:
            if key:
                return QdrantClient(host=host, port=port, api_key=key)
            return QdrantClient(host=host, port=port)
            
    except Exception:
        # Fallback auf Environment
        pass
    
    # Environment/Defaults
    qdrant_local = os.getenv("QDRANT_LOCAL", "true").lower() == "true"
    
    if qdrant_local:
        return QdrantClient(path="./local_qdrant.db")
    else:
        host = custom_host or os.getenv("QDRANT_HOST", "localhost")
        port = custom_port or int(os.getenv("QDRANT_PORT", 6333))
        key = api_key or os.getenv("QDRANT_API_KEY")
        
        if key:
            return QdrantClient(host=host, port=port, api_key=key)
        return QdrantClient(host=host, port=port)


def test_connection(client: QdrantClient, timeout: int = 5) -> tuple[bool, str]:
    """
    Testet die Qdrant-Verbindung.
    
    Args:
        client: QdrantClient Instanz
        timeout: Timeout in Sekunden
    
    Returns:
        tuple: (success: bool, message: str)
    """
    try:
        # Health check
        collections = client.get_collections()
        return True, f"Verbunden. {len(collections.collections)} Collection(s) gefunden."
    except Exception as e:
        return False, f"Verbindungsfehler: {str(e)}"


def get_collection_info(client: QdrantClient, collection_name: str = "local_rag") -> Optional[dict]:
    """
    Holt Informationen über eine Collection.
    
    Args:
        client: QdrantClient Instanz
        collection_name: Name der Collection
    
    Returns:
        dict mit Collection-Info oder None
    """
    try:
        collection = client.get_collection(collection_name)
        
        # Zusätzliche Stats
        try:
            count = client.count(collection_name)
            points_count = count.count
        except:
            points_count = collection.points_count
        
        return {
            'name': collection_name,
            'points_count': points_count,
            'vectors_count': getattr(collection, 'indexed_vectors_count', collection.points_count),
            'status': str(collection.status),
            'vector_size': collection.config.params.vectors.size if hasattr(collection.config.params, 'vectors') else None,
            'distance': str(collection.config.params.vectors.distance) if hasattr(collection.config.params, 'vectors') else None,
        }
    except UnexpectedResponse:
        return None
    except Exception as e:
        return {'error': str(e)}
