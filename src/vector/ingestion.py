"""
Document igenstion
"""

# Standard library
import os
import glob
import uuid
import shutil
import time
from pathlib import Path
from logging import getLogger
from tqdm import tqdm

# Third party imports
from langchain_community.document_loaders import (
    CSVLoader,
    UnstructuredExcelLoader,
    UnstructuredWordDocumentLoader,
)
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_qdrant import FastEmbedSparse
from langchain_huggingface import HuggingFaceEmbeddings
from qdrant_client import models
from langchain_openai import OpenAIEmbeddings

# Custom imports
from src.components import CustomPDFLoader
from src.llm.local_llm import VisionLLM
from src.utils.phase_logger import phase_logger, Phase
from src.utils.qdrant_client import get_qdrant_client

logger = getLogger(__name__)


class DocumentIngestion:
    """Document ingestion class"""

    def __init__(self):

        embedding_source = os.getenv("EMBEDDING_SOURCE", "local")
        embedding_endpoint = os.getenv(
            "EMBEDDING_ENDPOINT", "http://192.168.1.35:8080/v1"
        )
        model_name = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
        embedding_dim = os.getenv("EMBEDDING_DIMENSION", 384)

        # Collectoin Settings
        self.collection_name = "local_rag"
        self.dimensions = embedding_dim

        if embedding_source == "local":
            self.embeddings = HuggingFaceEmbeddings(model_name=model_name)
        else:
            self.embeddings = OpenAIEmbeddings(
                base_url=embedding_endpoint,
                api_key="loc-123",
                model=model_name,
                dimensions=self.dimensions,
                chunk_size=32,
            )

        # Document loaders
        self.loaders = {
            ".pdf": CustomPDFLoader,
            ".csv": CSVLoader,
            ".xlsx": UnstructuredExcelLoader,
            ".xls": UnstructuredExcelLoader,
            ".docx": UnstructuredWordDocumentLoader,
            ".doc": UnstructuredWordDocumentLoader,
        }

        # Qdrant client wird erst bei Bedarf geöffnet
        self._client = None

        # Setup model
        self.model = VisionLLM()

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
                vectors_config=models.VectorParams(
                    size=int(self.dimensions),  # Sicherstellen, dass es ein Int ist
                    distance=models.Distance.COSINE,
                ),
                # 2. WICHTIG: Konfiguration für BM25 (Sparse)
                sparse_vectors_config={
                    "langchain-sparse": models.SparseVectorParams()  # Standardname für LangChain Hybrid
                },
                hnsw_config=models.HnswConfigDiff(
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
        processed_dir = "./processed_files"

        if not os.path.exists(processed_dir):
            os.makedirs(processed_dir)

        unique_files = set()
        for doc in documents:
            source = doc.metadata.get("source")
            if source:
                unique_files.add(source)

        for file_path in unique_files:
            if os.path.exists(file_path):
                rel_path = os.path.relpath(file_path, "./files")
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

    def _create_directory_loader(self, files_extensions, loader_cls):
        """Directory Loader"""

        if not os.path.exists("./files"):
            os.mkdir("./files")

        return DirectoryLoader(
            path="./files",
            glob=f"**/*{files_extensions}",
            loader_cls=loader_cls,
            recursive=True,
        )

    def _enrich_with_context(self, full_document_text: str, chunk_text: str) -> str:
        """Enrich the chunks for contextual RAG"""
        start_time = time.time()
        
        phase_logger.log_phase(Phase.CONTEXT_ENRICHMENT, f"Context-Anreicherung gestartet | Chunk-Text: {len(chunk_text)} Zeichen")

        prompt = f"""
            Hier ist ein kurzes Dokument-Segment: {chunk_text}
            Ordne diesen Ausschnitt in maximal 2 Sätzen in den Kontext des Gesamtdokuments ein:
            {full_document_text[:2000]}
        """

        context = self.model.generate(prompt)
        
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
        
        # 1. Datei laden (PDF mit Bildern, andere ohne)
        try:
            if extension == '.pdf':
                loader = CustomPDFLoader(file_path)
                chunks = list(loader.lazy_load())
            elif extension == '.csv':
                loader = CSVLoader(file_path)
                chunks = loader.load()
            elif extension in ['.xlsx', '.xls']:
                loader = UnstructuredExcelLoader(file_path)
                chunks = loader.load()
            elif extension in ['.docx', '.doc']:
                loader = UnstructuredWordDocumentLoader(file_path)
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
        
        # 2. Chunks splitten (nur bei Nicht-PDFs)
        if extension != '.pdf':
            text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=1000, 
                chunk_overlap=200
            )
            chunks = text_splitter.split_documents(chunks)
        
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
            metadatas.append(meta)
        
        # 4. Vektoren berechnen
        phase_logger.log_phase(Phase.RETRIEVAL, f"Embeddings berechnen | Datei: {filename} | Vektoren: {len(texts_to_embed)}")
        
        dense_vectors = self.embeddings.embed_documents(texts_to_embed)
        sparse_vectors = sparse_model.embed_documents(texts_to_embed)
        
        # 5. Upload Qdrant
        points = []
        for i in range(len(texts_to_embed)):
            sv = sparse_vectors[i]
            qdrant_sparse = models.SparseVector(
                indices=sv.indices if hasattr(sv, "indices") else sv["indices"],
                values=sv.values if hasattr(sv, "values") else sv["values"],
            )
            
            points.append(
                models.PointStruct(
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
        client.upsert(collection_name=self.collection_name, points=points)
        
        # 6. Datei verschieben
        self._move_processed_files(chunks)
        
        duration = time.time() - start_time
        phase_logger.log_phase(Phase.DOCUMENT_PROCESSING, f"Datei fertig: {filename} | Dauer: {duration:.2f}s")
        
        return True

    def ingest_documents(self):
        """Sequentielle Ingestion pro Datei"""
        phase_logger.log_phase(Phase.DOCUMENT_PROCESSING, "Dokument-Ingestion gestartet")
        
        # Dateien sammeln
        all_files = []
        for extension in self.loaders.keys():
            pattern = os.path.join("./files", f"**/*{extension}")
            files = glob.glob(pattern, recursive=True)
            all_files.extend(files)
        
        if not all_files:
            logger.info("Keine Dateien gefunden.")
            phase_logger.log_phase(Phase.DOCUMENT_PROCESSING, "Keine Dateien gefunden", duration=0.0)
            return
        
        sparse_model = FastEmbedSparse(model_name="Qdrant/bm25")
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
