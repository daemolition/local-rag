"""
Document igenstion
"""

# Standard library
import os
from logging import getLogger

# Third party imports
from langchain_qdrant import QdrantVectorStore, RetrievalMode, FastEmbedSparse
from langchain_huggingface import HuggingFaceEmbeddings, HuggingFaceEndpointEmbeddings
from qdrant_client import QdrantClient

# Custom imports
from src.utils.qdrant_client import get_qdrant_client

logger = getLogger(__name__)

class DocumentRetriever:
    """Retriever ingestion class"""
    def __init__(self):
        
        # Retriever Options
        self.k = int(os.getenv("RETRIEVER_K", 5))
        self.fetch_k = int(os.getenv("RETRIEVER_FETCH_K", 30))
        self.lambda_mult = float(os.getenv("RETRIEVER_LAMBDA", 0.5))
        self.score_threshold = float(os.getenv("RETRIEVER_SCORE_THRESHOLD", 0.2))
        
        embedding_source = os.getenv("EMBEDDING_SOURCE", "local")
        huggingface_enpoint_token = os.getenv("HUGGINGFACEHUB_API_TOKEN", "")
        embedding_endpoint = os.getenv("EMBEDDING_ENDPOINT", "http://192.168.1.35:8080/v1")
        model_name = os.getenv("EMBEDDINGS_MODEL", "all-MiniLM-L6-v2")
        
        
        if embedding_source == "local":
            self.embeddings = HuggingFaceEmbeddings(
                model_name=model_name
            )
        else:
            self.embeddings = HuggingFaceEndpointEmbeddings(
                client=embedding_endpoint,
                model=model_name,
                huggingfacehub_api_token=huggingface_enpoint_token
            )
        
        # Sparse Embeddings
        self.sparse_embeddings = FastEmbedSparse(model_name="Qdrant/bm25")
        
        # Collection Settings
        self.collection_name = "local_rag"
        self.dimenions = "1024"        
        
        # Qdrant client
        self.client = get_qdrant_client(collection_name=self.collection_name)
        
    def retriever(self):
        """Retriever for the documents"""
        
        vectorstore = QdrantVectorStore(
            client=self.client,
            collection_name=self.collection_name,
            embedding=self.embeddings,
            sparse_embedding=self.sparse_embeddings,
            retrieval_mode=RetrievalMode.HYBRID
        )
        
        # Returns the retriever
        return vectorstore.as_retriever(
            search_type="mmr",
            search_kwargs={
                "k": self.k,
                "fetch_k": self.fetch_k,
                "lambda_mult": self.lambda_mult,
                "score_threshold": self.score_threshold
            }
        )
        