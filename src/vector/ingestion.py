"""
Document igenstion
"""

# Standard library
import os
from logging import getLogger
import uuid
import shutil
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed

# Third party imports
from langchain_community.document_loaders import (
    DirectoryLoader,
    PyPDFLoader,
    CSVLoader,
    UnstructuredExcelLoader,
    Docx2txtLoader,
    UnstructuredWordDocumentLoader,
)
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_qdrant import FastEmbedSparse
from langchain_huggingface import HuggingFaceEmbeddings
from qdrant_client import QdrantClient, models
from langchain_openai import OpenAIEmbeddings

# Custom imports
from src.components import CustomPDFLoader
from src.llm.local_llm import VisionLLM
from src.utils.phase_logger import phase_logger, Phase

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
            self._client = QdrantClient(
                path="./local_qdrant.db", collection_name="local_rag"
            )
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

    def _enrich_with_context(self, full_document_text, chunk_text):
        """Enrich the chunks for contextual RAG"""
        import time
        
        start_time = time.time()
        
        phase_logger.log_phase(Phase.CONTEXT_ENRICHMENT, f"Context-Anreicherung gestartet | Chunk-Text: {len(chunk_text)} Zeichen")

        prompt = f"""
            Hier ist ein kurzes Dokument-Segment: {chunk_text}
            Ordne diesen Ausschnitt in maximal 2 Sätzen in den Kontext des Gesamtdokuments ein:
            {full_document_text[:2000]}
        """

        # Using the vision model
        context = self.model.generate(prompt)
        
        duration = time.time() - start_time
        phase_logger.log_phase(Phase.CONTEXT_ENRICHMENT, f"Context angereichert | Result: {len(context)} Zeichen", duration=duration)

        return f"Kontext: {context}\n\nInhalt: {chunk_text}"

    def _process_single_file(self, source, chunks, sparse_model):
        """Worker-Funktion für einen einzelnen Thread"""
        import time
        from src.utils.phase_logger import Phase
        
        try:
            start_time = time.time()
            filename = os.path.basename(source)
            phase_logger.log_phase(Phase.DOCUMENT_PROCESSING, f"Datei verarbeiten: {filename} | Chunks: {len(chunks)}")
            
            # Globaler Kontext
            full_text_context = " ".join([c.page_content for c in chunks])[:2500]

            file_points = []
            texts_to_embed = []
            metadatas = []

            total_chunks = len(chunks)
            for i, chunk in enumerate(chunks, 1):
                logger.info(f"  [{i}/{total_chunks}] Verarbeite Chunk für: {filename}")

                enriched_text = self._enrich_with_context(
                    full_text_context, chunk.page_content
                )

                if "[Bildbeschreibung:" in chunk.page_content:
                    phase_logger.log_phase(Phase.VISION_PROCESSING, f"Bild-Kontext extrahiert | Datei: {filename}")
                    logger.info(f"  Bild-Kontext verarbeitet für: {filename}")

                texts_to_embed.append(enriched_text)
                meta = chunk.metadata.copy()
                meta["filename"] = filename
                metadatas.append(meta)

            # Vektoren berechnen
            phase_logger.log_phase(Phase.RETRIEVAL, f"Embeddings berechnen | Datei: {filename} | Vektoren: {len(texts_to_embed)}")
            dense_vectors = self.embeddings.embed_documents(texts_to_embed)
            sparse_vectors = sparse_model.embed_documents(texts_to_embed)

            for i in range(len(texts_to_embed)):
                sv = sparse_vectors[i]
                qdrant_sparse = models.SparseVector(
                    indices=sv.indices if hasattr(sv, "indices") else sv["indices"],
                    values=sv.values if hasattr(sv, "values") else sv["values"],
                )

                file_points.append(
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
            
            duration = time.time() - start_time
            phase_logger.log_phase(Phase.DOCUMENT_PROCESSING, f"Datei fertig: {filename} | Dauer: {duration:.2f}s")
            
            return file_points, chunks, source
        except Exception as e:
            logger.error(f"Fehler bei {source}: {e}")
            return None

    def chunk_documents(self):
        """Ingest Documents"""

        # Splitting the texts
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000, chunk_overlap=200
        )

        # Final chunked documents
        final_chunks = []

        for extension, loader_cls in self.loaders.items():
            loader = self._create_directory_loader(extension, loader_cls)
            loaded_docs = loader.load()

            if not loaded_docs:
                continue

            if extension == ".pdf":
                # If PDF skip spillting
                final_chunks.extend(loaded_docs)
            else:
                # If not pdf split
                split_docs = text_splitter.split_documents(loaded_docs)
                final_chunks.extend(split_docs)

        return final_chunks

    def ingest_documents(self):
        """Parallele Ingestion mit korrektem Fortschrittsbalken"""
        phase_logger.log_phase(Phase.DOCUMENT_PROCESSING, "Dokument-Ingestion gestartet")
        
        documents = self.chunk_documents()
        if not documents:
            logger.info("Nichts zu tun.")
            phase_logger.log_phase(Phase.DOCUMENT_PROCESSING, "Keine Dokumente gefunden", duration=0.0)
            return

        # Gruppierung
        docs_by_source = {}
        for doc in documents:
            source = doc.metadata.get("source", "unknown")
            docs_by_source.setdefault(source, []).append(doc)

        sparse_model = FastEmbedSparse(model_name="Qdrant/bm25")

        # Threads: Da das LLM remote ist, können wir locker 4-8 Threads nehmen
        max_threads = 5

        # Der Balken bleibt jetzt unten stehen
        pbar = tqdm(total=len(docs_by_source), desc="Ingesting Files", unit="file")

        with ThreadPoolExecutor(max_workers=max_threads) as executor:
            # Aufgaben verteilen
            future_to_file = {
                executor.submit(self._process_single_file, src, chks, sparse_model): src
                for src, chks in docs_by_source.items()
            }

            for future in as_completed(future_to_file):
                result = future.result()
                if result:
                    points, original_chunks, source_path = result

                    # SEQUENTIELLER UPLOAD (Wichtig für lokale .db Datei)
                    client = self._get_client()
                    client.upsert(collection_name=self.collection_name, points=points)

                    # Datei erst jetzt verschieben
                    self._move_processed_files(original_chunks)

                pbar.update(1)  # Balken eins weiter schieben

        pbar.close()
        self._close_client()
        phase_logger.log_phase(Phase.DOCUMENT_PROCESSING, "Dokument-Ingestion abgeschlossen")
        logger.info("Fertig! Alle Dateien sind im Archiv.")
