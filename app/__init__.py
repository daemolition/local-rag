import os
import sys
import logging
import atexit
import signal
import shutil
from pathlib import Path
from flask import Flask
from flask_session import Session
from langchain_qdrant import QdrantVectorStore, FastEmbedSparse, RetrievalMode
from langchain_huggingface import HuggingFaceEmbeddings
from qdrant_client import QdrantClient, models as qdrant_models

from src.llm.local_llm import VisionLLM
from src.tools.custom_tools import CustomTools
from src.agent.document_agent import DocumentAgent
from src.utils.qdrant_client import get_qdrant_client
from app.database_service import init_db_service
from app.settings_service import SettingsService

logger = logging.getLogger(__name__)

_qdrant_client = None
_db_service = None


def _remove_lock():
    """Qdrant Lock-Datei entfernen"""
    lock_file = Path("./local_qdrant.db") / ".lock"
    if lock_file.exists():
        try:
            lock_file.unlink()
            logger.debug("Qdrant lock file removed")
        except Exception:
            pass


def _cleanup():
    """Cleanup beim Beenden"""
    global _qdrant_client
    if _qdrant_client is not None:
        try:
            _qdrant_client.close()
        except Exception:
            pass
    _remove_lock()


def _signal_handler(signum, frame):
    _cleanup()
    sys.exit(0)


atexit.register(_cleanup)
signal.signal(signal.SIGTERM, _signal_handler)
signal.signal(signal.SIGINT, _signal_handler)


def init_resources(app):
    """Initialisiert Ressourcen mit Settings aus DB"""
    global _qdrant_client
    
    # Settings Service holen
    settings = app.extensions.get('settings')
    if not settings:
        logger.error("Settings Service nicht verfügbar!")
        return
    
    _remove_lock()
    
    collection_name = "local_rag"
    _qdrant_client = get_qdrant_client(collection_name=collection_name)
    
    # Embedding Dimension aus Settings
    embedding_dim = settings.get_int('EMBEDDING_DIMENSION', 384)
    
    # Embedding Modell aus Settings
    embedding_model = settings.get('EMBEDDING_MODEL', 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')
    
    dense_embeddings = HuggingFaceEmbeddings(
        model_name=embedding_model,
        model_kwargs={"device": "cpu"},
        encode_kwargs={"device": "cpu"}
    )
    sparse_embeddings = FastEmbedSparse(model_name="Qdrant/bm25")
    
    if not _qdrant_client.collection_exists(collection_name):
        logger.info(f"Creating Qdrant Collection: {collection_name}")
        _qdrant_client.create_collection(
            collection_name=collection_name,
            vectors_config=qdrant_models.VectorParams(
                size=embedding_dim,
                distance=qdrant_models.Distance.COSINE
            ),
            sparse_vectors_config={
                "langchain-sparse": qdrant_models.SparseVectorParams()
            },
            hnsw_config=qdrant_models.HnswConfigDiff(
                m=16,
                ef_construct=100,
                full_scan_threshold=10000,
            )
        )
        logger.info(f"Collection '{collection_name}' created.")
    else:
        logger.info(f"Collection '{collection_name}' already exists")
    
    vectorstore = QdrantVectorStore(
        client=_qdrant_client,
        collection_name=collection_name,
        embedding=dense_embeddings,
        sparse_embedding=sparse_embeddings,
        retrieval_mode=RetrievalMode.HYBRID
    )
    
    # Retriever Settings aus DB
    retriever_k = settings.get_int('RETRIEVER_K', 5)
    retriever_fetch_k = settings.get_int('RETRIEVER_FETCH_K', 30)
    retriever_lambda = settings.get_float('RETRIEVER_LAMBDA', 0.5)
    retriever_threshold = settings.get_float('RETRIEVER_SCORE_THRESHOLD', 0.2)
    
    retriever = vectorstore.as_retriever(
        search_type="mmr",
        search_kwargs={
            "k": retriever_k,
            "fetch_k": retriever_fetch_k,
            "lambda_mult": retriever_lambda,
            "score_threshold": retriever_threshold
        }
    )
    
    llm = VisionLLM()
    
    custom_tools = CustomTools(llm=llm, retriever=retriever)
    tools = custom_tools.get_tools()
    
    agent = DocumentAgent(llm=llm.llm_stream, tools=tools)
    
    app.extensions["vectorstore"] = vectorstore
    app.extensions["llm"] = llm
    app.extensions["agent"] = agent
    app.extensions["client"] = _qdrant_client


def ensure_directories(settings):
    """Stellt sicher, dass alle benötigten Verzeichnisse existieren."""
    data_dir = settings.get('DATA_DIR', './data')
    summaries_dir = settings.get('SUMMARIES_DIR', './summaries')
    
    directories = [
        data_dir,
        summaries_dir,
        "./flask_session",
    ]
    for d in directories:
        Path(d).mkdir(parents=True, exist_ok=True)
        logger.info(f"Verzeichnis sichergestellt: {d}")


def create_app():
    app = Flask(__name__)
    
    # Database Service initialisieren
    global _db_service
    _db_service = init_db_service()
    _db_service.init_default_data()
    
    # Settings Service erstellen
    db_session = _db_service.get_session()
    settings = SettingsService(db_session)
    
    # Verzeichnisse mit Settings erstellen
    ensure_directories(settings)
    
    # Flask Konfiguration
    app.config['SECRET_KEY'] = os.urandom(24)
    app.config['SESSION_TYPE'] = 'filesystem'
    app.config['SESSION_FILE_DIR'] = './flask_session/'
    
    app.extensions = {}
    app.extensions['db'] = _db_service
    app.extensions['settings'] = settings
    
    Session(app)
    
    init_resources(app)
    
    # Blueprints registrieren
    from app.routes import bp
    app.register_blueprint(bp)

    from app.admin_routes import admin_bp
    app.register_blueprint(admin_bp)
    
    # User Routes (für normale User - Dokumentenverwaltung)
    from app.user_routes import user_bp
    app.register_blueprint(user_bp)
    
    # Legacy database.py init_db() aufrufen für Migration
    # (wird in Phase 2 entfernt)
    from app.database import init_db as legacy_init_db
    try:
        legacy_init_db()
    except Exception as e:
        logger.warning(f"Legacy DB Init (für Migration): {e}")

    return app
