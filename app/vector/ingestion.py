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
Document ingestion
"""

# Standard library
import os
import glob
import uuid
import shutil
import time
import chardet
import pandas as pd
from pathlib import Path
from logging import getLogger
from datetime import datetime
from tqdm import tqdm

# Third party imports
from langchain_core.documents import Document
from langchain_community.document_loaders import (
    DirectoryLoader,
    UnstructuredMarkdownLoader
)
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_qdrant import FastEmbedSparse
from langchain_community.embeddings import FastEmbedEmbeddings
from qdrant_client import models as qdrant_models
from langchain_openai import OpenAIEmbeddings

# Custom imports
from app.components import CustomPDFLoader, CustomDOCXLoader
from app.llm.local_llm import VisionLLM
from app.utils.phase_logger import phase_logger, Phase
from app.utils.qdrant_client import get_qdrant_client
from app.database_service import get_db_service
from app.settings_service import SettingsService

logger = getLogger(__name__)


class DocumentIngestion:
    """Document ingestion class"""

    def __init__(self, embeddings=None, sparse_embeddings=None):

        # Defaults (Standalone-Fallback, falls kein DB-Kontext)
        embedding_source = "local"
        embedding_endpoint = "http://localhost:8080/v1"
        model_name = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
        embedding_dim = 384
        data_dir = "./data"
        api_key = "ollama"

        try:
            # Settings aus DB lesen (UI = Source of Truth); eigene Session,
            # thread-safe via Engine.
            db = get_db_service()
            session = db.get_session()
            settings = SettingsService(session)
            embedding_source = settings.get("EMBEDDING_SOURCE", embedding_source) or embedding_source
            embedding_endpoint = settings.get("EMBEDDING_ENDPOINT", embedding_endpoint) or embedding_endpoint
            model_name = settings.get("EMBEDDING_MODEL", model_name) or model_name
            embedding_dim = settings.get_int("EMBEDDING_DIMENSION", embedding_dim)
            data_dir = settings.get("DATA_DIR", data_dir) or data_dir
            api_key = settings.get("API_KEY", api_key) or api_key
            session.close()
        except Exception:
            # Standalone-Fallback: env
            embedding_source = os.getenv("EMBEDDING_SOURCE", embedding_source)
            embedding_endpoint = os.getenv("EMBEDDING_ENDPOINT", embedding_endpoint)
            model_name = os.getenv("EMBEDDING_MODEL", model_name)
            try:
                embedding_dim = int(os.getenv("EMBEDDING_DIMENSION", embedding_dim))
            except (ValueError, TypeError):
                pass
            data_dir = os.getenv("DATA_DIR", data_dir)
            api_key = os.getenv("API_KEY", api_key)

        # Collectoin Settings
        self.collection_name = "local_rag"
        self.dimensions = embedding_dim

        # Geteilte Sparse-Instanz aus app.extensions (optional); Fallback, falls
        # DocumentIngestion standalone (ohne uebergebene Instanz) genutzt wird.
        self._shared_sparse = sparse_embeddings

        if embedding_source == "local":
            # Geteilte Dense-Instanz aus app.extensions wiederverwenden, falls
            # vorhanden (kein Reload/Download pro Ingestion-Request).
            if embeddings is not None:
                self.embeddings = embeddings
            else:
                self.embeddings = FastEmbedEmbeddings(model_name=model_name)
        else:
            self.embeddings = OpenAIEmbeddings(
                base_url=embedding_endpoint,
                api_key=api_key,
                model=model_name,
                dimensions=self.dimensions,
                chunk_size=32,
            )

        # Supported file extensions (CSV/Excel werden ohne Loader verarbeitet)
        self.loaders = {
            ".pdf": CustomPDFLoader,
            ".csv": None,  # Wird in _process_file direkt verarbeitet
            ".xlsx": None,  # Wird in _process_file direkt verarbeitet
            ".xls": None,  # Wird in _process_file direkt verarbeitet
            ".docx": CustomDOCXLoader,
            ".doc": CustomDOCXLoader,
            ".odt": CustomDOCXLoader,
            ".md": UnstructuredMarkdownLoader,
        }

        # Qdrant client wird erst bei Bedarf geöffnet
        self._client = None

        # Setup model
        self.model = VisionLLM()

        # DATA_DIR für CSV/Excel nach Ingestion
        self.DATA_DIR = data_dir

        # TextSplitter einmalig erstellen
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000, chunk_overlap=200
        )

        # Setup the collection (öffnet Client temporär)
        self._setup_collection()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._close_client()
        return False

    def __del__(self):
        self._close_client()

    def _get_client(self):
        """Öffnet Qdrant Client bei Bedarf (Windows-sicher)"""
        if self._client is None:
            self._client = get_qdrant_client(collection_name=self.collection_name)
        return self._client

    def _close_client(self):
        """Schließt den Client sauber (wichtig für Windows Locks)"""
        if self._client is not None:
            self._client.close()
            self._client = None

    def _setup_collection(self):
        """Setting up the collection"""
        client = self._get_client()

        if not client.collection_exists(self.collection_name):
            logger.info(f"Erstelle Qdrant Collection: {self.collection_name}")

            client.create_collection(
                collection_name=self.collection_name,
                # 1. Konfiguration für normale Embeddings (Dense)
                vectors_config=qdrant_models.VectorParams(
                    size=int(self.dimensions),  # Sicherstellen, dass es ein Int ist
                    distance=qdrant_models.Distance.COSINE,
                ),
                # 2. WICHTIG: Konfiguration für BM25 (Sparse)
                sparse_vectors_config={
                    "langchain-sparse": qdrant_models.SparseVectorParams()  # Standardname für LangChain Hybrid
                },
                hnsw_config=qdrant_models.HnswConfigDiff(
                    m=16,
                    ef_construct=100,
                    full_scan_threshold=10000,
                ),
            )
        else:
            logger.info(f"Qdrant Collection '{self.collection_name}' existiert bereits")

        self._close_client()

    def _move_processed_files(self, documents):
        """Verschiebt verarbeitete Dateien in einen Archiv-Ordner (behält Unterordner-Struktur)"""
        processed_dir = "./data/processed_files"

        if not os.path.exists(processed_dir):
            os.makedirs(processed_dir)

        unique_files = set()
        for doc in documents:
            source = doc.metadata.get("source")
            if source:
                unique_files.add(source)

        for file_path in unique_files:
            if os.path.exists(file_path):
                rel_path = os.path.relpath(file_path, "./data/files")
                target_path = os.path.join(processed_dir, rel_path)

                target_dir = os.path.dirname(target_path)
                os.makedirs(target_dir, exist_ok=True)

                try:
                    if os.path.exists(target_path):
                        os.remove(target_path)
                    shutil.move(file_path, target_path)
                    logger.info(f"Verschoben in Archiv: {rel_path}")
                except Exception as e:
                    logger.error(f"Konnte Datei nicht verschieben {rel_path}: {e}")

    def _move_to_data_dir(self, file_path: str):
        """Verschiebt CSV/Excel nach DATA_DIR nach erfolgreicher Ingestion"""
        filename = os.path.basename(file_path)
        target_path = os.path.join(self.DATA_DIR, filename)

        if not os.path.exists(self.DATA_DIR):
            os.makedirs(self.DATA_DIR)

        # Konflikt lösen: Timestamp anhängen wenn Datei existiert
        if os.path.exists(target_path):
            base, ext = os.path.splitext(filename)
            timestamp = datetime.now().strftime("_%Y%m%d_%H%M%S")
            target_path = os.path.join(self.DATA_DIR, f"{base}{timestamp}{ext}")

        try:
            shutil.move(file_path, target_path)
            logger.info(f"Verschoben nach DATA_DIR: {filename}")
        except Exception as e:
            logger.error(f"Konnte Datei nicht nach DATA_DIR verschieben {filename}: {e}")

    def _generate_content_description(self, df: pd.DataFrame, filename: str) -> str:
        """Generiert eine LLM-basierte Inhaltsbeschreibung für Tabellendaten."""
        from langchain_core.messages import HumanMessage

        start_time = time.time()
        phase_logger.log_phase(Phase.LLM_CALL, f"Content-Beschreibung gestartet | Datei: {filename}")

        # Daten für LLM aufbereiten (limitiert um Token zu sparen)
        columns_info = ", ".join([f"{col} ({df[col].dtype})" for col in df.columns[:10]])
        sample_rows = df.head(5).to_string(index=False)

        prompt = f"""Du bist ein Datenanalyst. Analysiere die folgende Tabelle und erstelle eine kurze Inhaltsbeschreibung.

### Datei: {filename}
### Spalten: {columns_info}
### Anzahl Zeilen: {len(df)}
### Beispieldaten:
{sample_rows}

### Aufgabe:
Erstelle eine kurze Beschreibung (max. 150 Woerter) die folgende Punkte enthaelt:
1. Was stellen die Daten dar? (Thema/Zweck)
2. Was bedeuten die wichtigsten Spalten?
3. Welcher Zeitraum oder Umfang ist abgedeckt?
4. Welche Suchbegriffe waeren nuetzlich, um diese Daten zu finden?

### Beschreibung:"""

        try:
            message = HumanMessage(content=prompt)
            description = self.model.generate(message)

            duration = time.time() - start_time
            phase_logger.log_phase(Phase.LLM_CALL, f"Content-Beschreibung abgeschlossen | Datei: {filename}", duration=duration)

            return description.strip()
        except Exception as e:
            logger.warning(f"LLM-Beschreibung fehlgeschlagen fuer {filename}: {e}")
            duration = time.time() - start_time
            phase_logger.log_phase(Phase.LLM_CALL, f"Content-Beschreibung fehlgeschlagen | Datei: {filename}", duration=duration)
            return ""

    def _get_tabular_overview(self, file_path: str) -> str:
        """
        Generiert eine Markdown-Übersicht für CSV/Excel-Dateien.
        Enthält strukturelle Infos und LLM-generierte Inhaltsbeschreibung.
        """
        filename = os.path.basename(file_path)
        extension = Path(file_path).suffix.lower()

        # Helper für Encoding-Erkennung (wird unten definiert)
        def detect_encoding(fp: str) -> str:
            try:
                with open(fp, 'rb') as f:
                    raw_data = f.read(10000)
                    result = chardet.detect(raw_data)
                    encoding = result.get('encoding', 'cp1252')
                    confidence = result.get('confidence', 0)
                    if confidence < 0.7:
                        encoding = 'cp1252'
                    return encoding
            except Exception:
                return 'cp1252'

        try:
            if extension == '.csv':
                encoding = detect_encoding(file_path)
                df = pd.read_csv(file_path, encoding=encoding)
            else:  # xlsx, xls
                df = pd.read_excel(file_path)

            if df.empty:
                return f"## Datei: {filename}\n\nDie Datei ist leer."

            columns_str = ", ".join([f"`{col}`" for col in df.columns])
            preview_str = df.head(4).to_markdown(index=False)

            # LLM-Inhaltsbeschreibung generieren
            content_description = self._generate_content_description(df, filename)
            description_section = f"\n\n### Inhaltsbeschreibung:\n{content_description}" if content_description else ""

            overview = f"""## Datei: {filename}

**Spalten ({len(df.columns)}):** {columns_str}
**Zeilen:** {len(df)}

### Vorschau:
{preview_str}{description_section}"""
            return overview

        except Exception as e:
            logger.warning(f"Preview fehlgeschlagen für {file_path}: {e}")
            return f"## Datei: {filename}\n\nDatei konnte nicht gelesen werden."

    def _create_directory_loader(self, files_extensions, loader_cls):
        """Directory Loader"""

        if not os.path.exists("./data/files"):
            os.mkdir("./data/files")

        return DirectoryLoader(
            path="./data/files",
            glob=f"**/*{files_extensions}",
            loader_cls=loader_cls,
            recursive=True,
        )

    def _enrich_with_context(self, full_document_text: str, chunk_text: str) -> str:
        """Enrich the chunks for contextual RAG"""
        from langchain_core.messages import HumanMessage
        
        start_time = time.time()
        phase_logger.log_phase(Phase.CONTEXT_ENRICHMENT, f"Context-Anreicherung gestartet | Chunk-Text: {len(chunk_text)} Zeichen")

        prompt = (
            "Du bist ein Dokumenten-Indexierer. "
            "Gib NUR 1-2 kurze Sätze zurück, die den Abschnitt im Gesamtdokument verorten.\n\n"
            f"### Gesamtdokument (Auszug):\n{full_document_text[:2000]}\n\n"
            f"### Abschnitt:\n{chunk_text}\n\n"
            "### Kontext-Einordnung:"
        )

        message = HumanMessage(content=prompt)
        context = self.model.generate(message)
        
        duration = time.time() - start_time
        phase_logger.log_phase(Phase.CONTEXT_ENRICHMENT, f"Context angereichert | Result: {len(context)} Zeichen", duration=duration)

        return f"Kontext: {context}\n\nInhalt: {chunk_text}"

    def _process_file(self, file_path: str, sparse_model) -> bool:
        """
        Verarbeitet eine einzelne Datei komplett (sequentiell).
        
        Args:
            file_path: Pfad zur Datei
            sparse_model: BM25 Sparse Embedding Model
            
        Returns:
            bool: True wenn erfolgreich, False bei Fehler/leer
        """
        filename = os.path.basename(file_path)
        extension = Path(file_path).suffix.lower()
        start_time = time.time()
        phase_logger.log_phase(Phase.DOCUMENT_PROCESSING, f"Datei verarbeiten: {filename}")

        # Gruppen-ID fuer alle Chunks dieser einen Datei (eine Datei erzeugt
        # i.d.R. mehrere Qdrant-Punkte/Chunks). Wird als UserDocument.document_id
        # gespeichert, damit Liste/Loeschen alle zugehoerigen Punkte ueber einen
        # Payload-Filter statt einer einzelnen Punkt-ID finden.
        file_group_id = str(uuid.uuid4())

        # 1. Datei laden
        # PDF, DOCX, DOC, ODT nutzen Custom Loader mit Bildextraktion (VisionLLM).
        # CSV/XLSX/XLS werden als tabellarische Übersicht verarbeitet.
        # MD nutzt UnstructuredMarkdownLoader (keine eingebetteten Bilder).
        try:
            if extension == '.pdf':
                loader = CustomPDFLoader(file_path, model=self.model)
                chunks = list(loader.lazy_load())
            elif extension in ['.docx', '.doc', '.odt']:
                loader = CustomDOCXLoader(file_path, model=self.model)
                chunks = list(loader.lazy_load())
            elif extension == '.csv':
                # Nur Übersichts-Chunk, keine Zeilen-Chunks
                overview = self._get_tabular_overview(file_path)
                overview_chunk = Document(
                    page_content=overview,
                    metadata={"source": file_path, "filename": filename, "type": "tabular_overview"}
                )
                chunks = [overview_chunk]
            elif extension in ['.xlsx', '.xls']:
                # Nur Übersichts-Chunk, keine Zeilen-Chunks
                overview = self._get_tabular_overview(file_path)
                overview_chunk = Document(
                    page_content=overview,
                    metadata={"source": file_path, "filename": filename, "type": "tabular_overview"}
                )
                chunks = [overview_chunk]
            elif extension == '.md':
                loader = UnstructuredMarkdownLoader(file_path)
                chunks = loader.load()
            else:
                logger.warning(f"Unbekannter Dateityp: {extension}")
                return False
        except Exception as e:
            logger.error(f"Fehler beim Laden von {filename}: {e}")
            return False
        
        if not chunks:
            logger.info(f"Keine Chunks für {filename}")
            return False
        
        # 2. Chunks splitten (nur bei Formaten ohne Custom Loader)
        # PDF, DOCX, DOC, ODT werden bereits vom Custom Loader gechunkt
        if extension not in ['.pdf', '.docx', '.doc', '.odt']:
            chunks = self.text_splitter.split_documents(chunks)
        
        # 3. Context anreichern
        full_text_context = " ".join([c.page_content for c in chunks])[:2500]
        
        texts_to_embed = []
        metadatas = []
        
        total_chunks = len(chunks)
        for i, chunk in enumerate(chunks, 1):
            logger.info(f"  [{i}/{total_chunks}] Context anreichern: {filename}")
            
            enriched_text = self._enrich_with_context(full_text_context, chunk.page_content)
            
            if "[Bild-BESCHREIBUNG:" in chunk.page_content or "[Bildbeschreibung:" in chunk.page_content:
                phase_logger.log_phase(Phase.VISION_PROCESSING, f"Bild-Kontext extrahiert | Datei: {filename}")
                logger.info(f"  Bild-Kontext verarbeitet für: {filename}")
            
            texts_to_embed.append(enriched_text)
            meta = chunk.metadata.copy()
            meta["filename"] = filename
            meta["file_group_id"] = file_group_id
            metadatas.append(meta)
        
        # 4. Vektoren berechnen
        phase_logger.log_phase(Phase.RETRIEVAL, f"Embeddings berechnen | Datei: {filename} | Vektoren: {len(texts_to_embed)}")
        
        dense_vectors = self.embeddings.embed_documents(texts_to_embed)
        sparse_vectors = sparse_model.embed_documents(texts_to_embed)
        
        # 5. Upload Qdrant
        points = []
        for i in range(len(texts_to_embed)):
            sv = sparse_vectors[i]
            qdrant_sparse = qdrant_models.SparseVector(
                indices=sv.indices if hasattr(sv, "indices") else sv["indices"],
                values=sv.values if hasattr(sv, "values") else sv["values"],
            )
            
            points.append(
                qdrant_models.PointStruct(
                    id=str(uuid.uuid4()),
                    vector={
                        "": dense_vectors[i],
                        "langchain-sparse": qdrant_sparse,
                    },
                    payload={
                        "page_content": texts_to_embed[i],
                        "original_content": chunks[i].page_content,
                        **metadatas[i],
                    },
                )
            )
        
        client = self._get_client()
        
        # Batch-Upsert (max 100 Punkte pro Batch)
        BATCH_SIZE = 500
        for i in range(0, len(points), BATCH_SIZE):
            batch = points[i:i + BATCH_SIZE]
            client.upsert(collection_name=self.collection_name, points=batch)
        
        # 6. Datei verschieben
        if extension in ['.csv', '.xlsx', '.xls']:
            self._move_to_data_dir(file_path)
        else:
            self._move_processed_files(chunks)

        # 7. Dokument-Zuordnung anlegen, damit die Datei-Liste das ingestierte
        # Dokument findet und es per file_group_id gelöscht werden kann.
        try:
            from app.database_service import get_db_service
            get_db_service().add_document(
                document_id=file_group_id, filename=filename
            )
        except Exception as e:
            logger.error(f"Fehler beim Anlegen des UserDocument-Eintrags fuer {filename}: {e}")

        duration = time.time() - start_time
        phase_logger.log_phase(Phase.DOCUMENT_PROCESSING, f"Datei fertig: {filename} | Dauer: {duration:.2f}s")
        
        return True

    def ingest_documents(self):
        """Sequentielle Ingestion pro Datei"""
        phase_logger.log_phase(Phase.DOCUMENT_PROCESSING, "Dokument-Ingestion gestartet")
        
        # Dateien sammeln
        all_files = []
        for extension in self.loaders.keys():
            pattern = os.path.join("./data/files", f"**/*{extension}")
            files = glob.glob(pattern, recursive=True)
            all_files.extend(files)
        
        if not all_files:
            logger.info("Keine Dateien gefunden.")
            phase_logger.log_phase(Phase.DOCUMENT_PROCESSING, "Keine Dateien gefunden", duration=0.0)
            return
        
        sparse_model = self._shared_sparse or FastEmbedSparse(model_name="Qdrant/bm25")
        pbar = tqdm(all_files, desc="Processing Files", unit="file")
        
        success_count = 0
        error_count = 0
        
        for file_path in pbar:
            filename = os.path.basename(file_path)
            pbar.set_description(f"Processing: {filename}")
            
            try:
                success = self._process_file(file_path, sparse_model)
                if success:
                    success_count += 1
                    pbar.write(f"✓ {filename} verarbeitet")
                else:
                    error_count += 1
                    pbar.write(f"✗ {filename} fehlgeschlagen (keine Chunks)")
            except Exception as e:
                error_count += 1
                logger.error(f"Fehler bei {filename}: {e}")
                pbar.write(f"✗ {filename} fehlgeschlagen: {str(e)[:50]}")
                continue
        
        self._close_client()
        phase_logger.log_phase(Phase.DOCUMENT_PROCESSING, f"Dokument-Ingestion abgeschlossen | Erfolgreich: {success_count} | Fehler: {error_count}")
        logger.info(f"Fertig! {success_count} Dateien erfolgreich verarbeitet, {error_count} Fehler.")
