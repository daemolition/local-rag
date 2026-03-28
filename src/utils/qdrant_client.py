"""
Qdrant Client Factory
"""
import os
from qdrant_client import QdrantClient


def get_qdrant_client(collection_name: str = "local_rag") -> QdrantClient:
    """
    Erstellt einen Qdrant-Client basierend auf der Environment-Variable QDRANT_LOCAL.
    
    Args:
        collection_name (str): Name der Collection (default: "local_rag")
    
    Returns:
        QdrantClient: Lokaler oder Remote Client
    
    Environment:
        QDRANT_LOCAL (str): 
            - "true" (default): Lokale .db Datei
            - "false": Remote Server (http://qdrant:6333)
    """
    qdrant_local = os.getenv("QDRANT_LOCAL", "true").lower() == "true"
    
    if qdrant_local:
        return QdrantClient(path="./local_qdrant.db")
    else:
        qdrant_host = os.getenv("QDRANT_HOST", "qdrant")
        qdrant_port = int(os.getenv("QDRANT_PORT", 6333))
        return QdrantClient(host=qdrant_host, port=qdrant_port)