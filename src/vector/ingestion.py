"""
Document igenstion
"""

# Standard library
import os
from logging import getLogger
import uuid
import shutil
from tqdm import tqdm

# Third party imports
from langchain_community.document_loaders import (
    DirectoryLoader,
    PyPDFLoader,
    CSVLoader,
    UnstructuredExcelLoader
)
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_qdrant import FastEmbedSparse
from langchain_huggingface import HuggingFaceEmbeddings
from qdrant_client import QdrantClient, models
from langchain_openai import OpenAIEmbeddings

# Custom imports
from src.components import CustomPDFLoader
from src.llm.local_llm import VisionLLM

logger = getLogger(__name__)

class DocumentIngestion:
    """Document ingestion class"""
    def __init__(self):
        
        embedding_source = os.getenv("EMBEDDING_SOURCE", "local")
        embedding_endpoint = os.getenv("EMBEDDING_ENDPOINT", "http://192.168.1.35:8080/v1")
        model_name = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
        embedding_dim = os.getenv("EMBEDDING_DIMENSION", 384)
        
        # Collectoin Settings
        self.collection_name = "local_rag"
        self.dimensions = embedding_dim     
                
        if embedding_source == "local":
            self.embeddings = HuggingFaceEmbeddings(
                model_name=model_name
            )
        else:
            self.embeddings = OpenAIEmbeddings(
                base_url=embedding_endpoint,
                api_key="loc-123",
                model=model_name,
                dimensions=self.dimensions,
                chunk_size=32
            )       


        # Document loaders
        self.loaders = {      
            ".pdf": CustomPDFLoader,
            ".csv": CSVLoader,
            ".xlsx": UnstructuredExcelLoader,
            ".xls": UnstructuredExcelLoader
        }
        
        # Qdrant client
        self.client = QdrantClient(
            path="./local_qdrant.db",
            collection_name="local_rag"
        )
        
        # Setup model
        self.model = VisionLLM()
       
        # Setup the collection
        self._setup_collection()
        
    def _setup_collection(self):
        """Setting up the collection"""
        
        if not self.client.collection_exists(self.collection_name):
            logger.info(f"Erstelle Qdrant Collection: {self.collection_name}")
            
            self.client.create_collection(
                collection_name=self.collection_name,
                # 1. Konfiguration für normale Embeddings (Dense)
                vectors_config=models.VectorParams(
                    size=int(self.dimensions), # Sicherstellen, dass es ein Int ist
                    distance=models.Distance.COSINE
                ),
                # 2. WICHTIG: Konfiguration für BM25 (Sparse)
                sparse_vectors_config={
                    "langchain-sparse": models.SparseVectorParams() # Standardname für LangChain Hybrid
                },
                hnsw_config=models.HnswConfigDiff(
                    m=16,
                    ef_construct=100,
                    full_scan_threshold=10000,
                )
            )
        else:
            logger.info(f"Qdrant Collection '{self.collection_name}' existiert bereits")
            
        
    def _move_processed_files(self, documents):
        """Verschiebt verarbeitete Dateien in einen Archiv-Ordner"""
        processed_dir = "./processed_files"
        
        # Ordner anlegen, falls er nicht existiert
        if not os.path.exists(processed_dir):
            os.makedirs(processed_dir)
            
        # Einzigartige Dateipfade aus den Metadaten extrahieren
        unique_files = set()
        for doc in documents:
            source = doc.metadata.get("source")
            if source:
                unique_files.add(source)
                
        # Dateien verschieben
        for file_path in unique_files:
            if os.path.exists(file_path):
                filename = os.path.basename(file_path)
                target_path = os.path.join(processed_dir, filename)
                
                try:
                    # Falls die Datei im Zielordner schon existiert, vorher löschen 
                    # (verhindert Windows-Abstürze beim Überschreiben)
                    if os.path.exists(target_path):
                        os.remove(target_path)
                        
                    shutil.move(file_path, target_path)
                    logger.info(f"Verschoben in Archiv: {filename}")
                except Exception as e:
                    logger.error(f"Konnte Datei nicht verschieben {filename}: {e}")
                    

    def _create_directory_loader(self, files_extensions, loader_cls):
        """Directory Loader"""
        
        if not os.path.exists("./files"):
            os.mkdir("./files")
        
        return DirectoryLoader(
            path="./files",
            glob=f"**/*{files_extensions}",
            loader_cls=loader_cls
        )
        
        
    def _enrich_with_context(self, full_document_text, chunk_text):
        """Enrich the chunks for contextual RAG"""
        
        prompt = f"""
            Hier ist ein kurzes Dokument-Segment: {chunk_text}
            Ordne diesen Ausschnitt in maximal 2 Sätzen in den Kontext des Gesamtdokuments ein:
            {full_document_text[:2000]}
        """
        
        # Using the vision model
        context = self.model.generate(prompt)
        
        return f"Kontext: {context}\n\nInhalt: {chunk_text}"
        
        
    def chunk_documents(self):
        """Ingest Documents"""
        
                # Splitting the texts
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200
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
        """Native Ingestion ohne LangChain Wrapper"""
        documents = self.chunk_documents()     
        
        if not documents:
            logger.info("Keine Dokumente gefunden. Abbruch.")
            return

        docs_by_source = {}
        for doc in documents:
            source = doc.metadata.get("source", "unknown")
            if source not in docs_by_source:
                docs_by_source[source] = []
            docs_by_source[source].append(doc)
            
            
        all_points = []
       
        # 1. Sparse Modell initialisieren
        sparse_model = FastEmbedSparse(model_name="Qdrant/bm25")       
        
        # Progress bar
        pbar = tqdm(docs_by_source.items(), desc="Ingestion Progress", unit="file") 
        
        logger.info(f"Verarbeite {len(docs_by_source)} Dateien...")

        for source, chunks in pbar:
            logger.info(f"Reichere Datei an: {os.path.basename(source)}")
            
            # Globaler Kontext: Die ersten ~2500 Zeichen des Gesamtdokuments
            full_text_context = " ".join([c.page_content for c in chunks])[:2500]
            
            texts_to_embed = []
            metadatas_to_store = []

            for chunk in chunks:
                # Contextual Enrichment: Chunk in den Kontext setzen
                enriched_text = self._enrich_with_context(full_text_context, chunk.page_content)
                texts_to_embed.append(enriched_text)
                
                # Metadaten sicherstellen (Dateiname, Pfad, etc.)
                meta = chunk.metadata.copy()
                meta["filename"] = os.path.basename(source)
                metadatas_to_store.append(meta)

            # Vektoren berechnen
            logger.info(f"Berechne Vektoren für {len(texts_to_embed)} Chunks...")
            dense_vectors = self.embeddings.embed_documents(texts_to_embed)
            sparse_vectors = sparse_model.embed_documents(texts_to_embed)

            # Qdrant Points erstellen
            for i in range(len(texts_to_embed)):
                sv = sparse_vectors[i]
                qdrant_sparse = models.SparseVector(
                    indices=sv.indices if hasattr(sv, 'indices') else sv["indices"],
                    values=sv.values if hasattr(sv, 'values') else sv["values"]
                )

                all_points.append(models.PointStruct(
                    id=str(uuid.uuid4()),
                    vector={
                        "": dense_vectors[i],
                        "langchain-sparse": qdrant_sparse
                    },
                    payload={
                        "page_content": texts_to_embed[i], # Enriched Text in DB
                        "original_content": chunks[i].page_content, # Backup des Originals
                        **metadatas_to_store[i]
                    }
                ))

            # 2. Sammel-Upload für bessere Performance
            logger.info(f"Schreibe {len(all_points)} Punkte in Qdrant...")
            self.client.upsert(
                collection_name=self.collection_name,
                points=all_points
            )
            
            # Move it directly
            self._move_processed_files(documents)
            logger.info(f"Erfolgreich abgeshlossen und archiviert: {os.path.basename(source)}")                    

        # 3. Aufräumen
        self.client.close()
        logger.info("Ingestion abgeschlossen.")
        
        