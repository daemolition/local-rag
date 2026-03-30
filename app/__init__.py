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
from qdrant_client import QdrantClient, models

from src.llm.local_llm import VisionLLM
from src.tools.custom_tools import CustomTools
from src.agent.document_agent import DocumentAgent
from src.utils.qdrant_client import get_qdrant_client
from app.database import init_db

logger = logging.getLogger(__name__)

USERS = {
    "admin": "secret123",
    "user": "password123"
}

_qdrant_client = None


def _remove_lock():
    qdrant_local = os.getenv("QDRANT_LOCAL", "true").lower() == "true"
    if qdrant_local:
        lock_file = Path("./local_qdrant.db") / ".lock"
        if lock_file.exists():
            try:
                lock_file.unlink()
                logger.debug("Qdrant lock file removed")
            except Exception:
                pass


def _cleanup():
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
    global _qdrant_client
    
    _remove_lock()
    
    collection_name = "local_rag"
    _qdrant_client = get_qdrant_client(collection_name=collection_name)
    
    embedding_dim = int(os.getenv("EMBEDDING_DIMENSION", 384))
    
    dense_embeddings = HuggingFaceEmbeddings(
        model_name=os.getenv("EMBEDDING_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"),
        model_kwargs={"device": "cpu"},
        encode_kwargs={"device": "cpu"}
    )
    sparse_embeddings = FastEmbedSparse(model_name="Qdrant/bm25")
    
    if not _qdrant_client.collection_exists(collection_name):
        logger.info(f"Creating Qdrant Collection: {collection_name}")
        _qdrant_client.create_collection(
            collection_name=collection_name,
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
    
    retriever = vectorstore.as_retriever(
        search_type="mmr",
        search_kwargs={
            "k": 5,
            "fetch_k": 30,
            "lambda_mult": 0.5,
            "score_threshold": 0.2
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


def ensure_directories():
    """Stellt sicher, dass alle benötigten Verzeichnisse existieren."""
    directories = [
        os.getenv("DATA_DIR", "./analytics"),
        os.getenv("SUMMARIES_DIR", "./summaries"),
        "./flask_session",
    ]
    for d in directories:
        Path(d).mkdir(parents=True, exist_ok=True)
        logger.info(f"Verzeichnis sichergestellt: {d}")


def create_app():
    app = Flask(__name__)
    
    ensure_directories()

    # Initialize chat history database
    init_db()

    app.config['SECRET_KEY'] = os.urandom(24)
    app.config['SESSION_TYPE'] = 'filesystem'
    app.config['SESSION_FILE_DIR'] = './flask_session/'
    
    app.extensions = {}
    
    Session(app)
    
    init_resources(app)
    
    from app.routes import bp
    app.register_blueprint(bp)

    from app.admin_routes import admin_bp
    app.register_blueprint(admin_bp)

    return app