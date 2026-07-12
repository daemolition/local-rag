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
Document igenstion
"""

# Standard library
import os
from logging import getLogger

# Third party imports
from langchain_qdrant import QdrantVectorStore, RetrievalMode, FastEmbedSparse
from langchain_community.embeddings import FastEmbedEmbeddings
from langchain_openai import OpenAIEmbeddings

# Custom imports
from app.utils.qdrant_client import get_qdrant_client

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
        embedding_endpoint = os.getenv("EMBEDDING_ENDPOINT", "http://localhost:8080/v1")
        model_name = os.getenv("EMBEDDINGS_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
        api_key = os.getenv("API_KEY", "ollama")
        
        if embedding_source == "local":
            self.embeddings = FastEmbedEmbeddings(
                model_name=model_name
            )
        else:
            self.embeddings = OpenAIEmbeddings(
                base_url=embedding_endpoint,
                api_key=api_key,
                model=model_name,
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
            # sparse_embedding=self.sparse_embeddings,  # BM25 deaktiviert - nicht für Deutsch optimiert
            retrieval_mode=RetrievalMode.DENSE
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
        