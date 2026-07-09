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

import os
import sys
import logging
import atexit
import signal
import threading
from pathlib import Path
from flask import Flask
from flask_session import Session
from langchain_qdrant import QdrantVectorStore, FastEmbedSparse, RetrievalMode
from langchain_huggingface import HuggingFaceEmbeddings
from qdrant_client import models as qdrant_models

from app.llm.local_llm import VisionLLM
from app.tools.custom_tools import CustomTools
from app.agent.document_agent import DocumentAgent
from app.utils.qdrant_client import get_qdrant_client
from app.database_service import init_db_service
from app.settings_service import SettingsService

logger = logging.getLogger(__name__)

_qdrant_client = None
_db_service = None

# Hintergrund-Initialisierung der Embedding-Modelle (s. init_resources).
# _resources_ready wird gesetzt, sobald der Hintergrund-Thread fertig ist
# (egal ob Erfolg oder Fehler). _resources_error haelt eine evt. Exception.
_resources_ready = threading.Event()
_resources_error = None


def resources_ready():
    """True, sobald die Hintergrund-Initialisierung erfolgreich abgeschlossen ist."""
    return _resources_ready.is_set() and _resources_error is None


def wait_for_resources(timeout=None):
    """Blockiert bis die Hintergrund-Initialisierung fertig ist oder der Timeout
    ablaeuft. Gibt True zurueck, wenn die Ressourcen bereit sind, False bei Timeout.
    Loest RuntimeError aus, falls die Initialisierung im Hintergrund fehlschlug."""
    if not _resources_ready.wait(timeout):
        return False
    if _resources_error is not None:
        raise RuntimeError(
            "Ressourcen-Initialisierung fehlgeschlagen"
        ) from _resources_error
    return True


def _cleanup():
    """Cleanup beim Beenden"""
    global _qdrant_client
    if _qdrant_client is not None:
        try:
            _qdrant_client.close()
        except Exception:
            pass


def _signal_handler(signum, frame):
    _cleanup()
    sys.exit(0)


atexit.register(_cleanup)
signal.signal(signal.SIGTERM, _signal_handler)
signal.signal(signal.SIGINT, _signal_handler)


def init_resources(app):
    """Initialisiert Ressourcen mit Settings aus DB.

    Qdrant-Client und Collection werden sofort (synchron) angelegt, da viele
    Dokument-Endpunkte darauf zugreifen. Das Laden der Embedding-Modelle und der
    Aufbau der darauf aufbauenden Kette (Vectorstore -> Retriever -> Agent) laufen
    in einem Hintergrund-Thread, damit ein Modell-Download den App-Start nicht
    blockiert (Docker-Start-Timeout). Siehe wait_for_resources()/resources_ready().
    """
    global _qdrant_client

    # Settings Service holen
    settings = app.extensions.get('settings')
    if not settings:
        logger.error("Settings Service nicht verfügbar!")
        _resources_ready.set()
        return

    collection_name = "local_rag"
    _qdrant_client = get_qdrant_client(collection_name=collection_name)

    # Embedding Dimension aus Settings
    embedding_dim = settings.get_int('EMBEDDING_DIMENSION', 384)

    # Collection anlegen (schnell, Qdrant ist via depends_on bereit)
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

    # Payload-Index fuer file_group_id: alle Chunks einer Datei teilen diesen
    # Wert, damit "Meine Dokumente"/Loeschen effizient per Filter statt
    # Vollscan darauf zugreifen koennen. Idempotent, falls Index bereits existiert.
    try:
        _qdrant_client.create_payload_index(
            collection_name=collection_name,
            field_name="file_group_id",
            field_schema=qdrant_models.PayloadSchemaType.KEYWORD,
        )
    except Exception as e:
        logger.debug(f"Payload-Index file_group_id bereits vorhanden oder fehlgeschlagen: {e}")

    # Qdrant-Client sofort fuer Dokument-Endpunkte bereithalten
    app.extensions["client"] = _qdrant_client

    # Alle Settings im Main-Thread vorlesen (SQLAlchemy-Session ist nicht
    # thread-safe) und als Captures in den Hintergrund-Thread reichen.
    embedding_model = settings.get(
        'EMBEDDING_MODEL',
        'paraphrase-multilingual-MiniLM-L12-v2'
    )
    retriever_k = settings.get_int('RETRIEVER_K', 5)
    retriever_fetch_k = settings.get_int('RETRIEVER_FETCH_K', 30)
    retriever_lambda = settings.get_float('RETRIEVER_LAMBDA', 0.5)
    retriever_threshold = settings.get_float('RETRIEVER_SCORE_THRESHOLD', 0.2)
    data_dir = settings.get('DATA_DIR', './data')
    summaries_dir = settings.get('SUMMARIES_DIR', './data/summaries')

    # Schwere Initialisierung (Modell-Load/-Download + Agent-Kette) im Hintergrund
    def _load_resources():
        global _resources_error
        try:
            logger.info(f"Lade Embedding-Modell im Hintergrund: {embedding_model}")
            dense_embeddings = HuggingFaceEmbeddings(
                model_name=embedding_model,
                model_kwargs={"device": "cpu"},
                encode_kwargs={"device": "cpu"}
            )
            sparse_embeddings = FastEmbedSparse(model_name="Qdrant/bm25")

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
                    "k": retriever_k,
                    "fetch_k": retriever_fetch_k,
                    "lambda_mult": retriever_lambda,
                    "score_threshold": retriever_threshold
                }
            )

            llm = VisionLLM()
            custom_tools = CustomTools(
                llm=llm, retriever=retriever,
                data_dir=data_dir, summaries_dir=summaries_dir,
            )
            tools = custom_tools.get_tools()
            agent = DocumentAgent(llm=llm.llm_stream, tools=tools)

            app.extensions["dense_embeddings"] = dense_embeddings
            app.extensions["sparse_embeddings"] = sparse_embeddings
            app.extensions["vectorstore"] = vectorstore
            app.extensions["llm"] = llm
            app.extensions["agent"] = agent
            logger.info("Ressourcen bereit (Embedding-Modell + Agent).")
        except Exception as e:
            _resources_error = e
            logger.exception("Ressourcen-Initialisierung im Hintergrund fehlgeschlagen")
        finally:
            _resources_ready.set()

    threading.Thread(
        target=_load_resources, name="init-resources", daemon=True
    ).start()


def ensure_directories(settings):
    """Stellt sicher, dass alle benötigten Verzeichnisse existieren."""
    data_dir = settings.get('DATA_DIR', './data')
    summaries_dir = settings.get('SUMMARIES_DIR', './data/summaries')

    # Alle Arbeits-Verzeichnisse liegen als Subdirs unter data_dir (dem
    # app-data-Volume-Mountpoint /app/data). Nur /app/data selbst ist ein
    # Mountpoint; diese Subdirs sind normale Verzeichnisse.
    directories = [
        data_dir,
        summaries_dir,
        os.path.join(data_dir, "files"),
        os.path.join(data_dir, "processed_files"),
        os.path.join(data_dir, "images"),
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
