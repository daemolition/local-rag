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
Laden von Embedding-Modellen, Vectorstore, Retriever und Agent.

``load_resources()`` ist eine reine Funktion — sie laedt alle KI-Ressourcen
und speichert sie in ``app.extensions``. Bei Fehlern wird eine Exception
ausgeloest; der Aufrufer (``__init__.py``) entscheidet ueber Sync/Async,
Event-Handling und Fehler-Logging.
"""

import logging

from langchain_qdrant import QdrantVectorStore, FastEmbedSparse, RetrievalMode
from langchain_community.embeddings import FastEmbedEmbeddings

from app.llm.local_llm import VisionLLM
from app.tools.custom_tools import CustomTools
from app.agent.document_agent import DocumentAgent

logger = logging.getLogger(__name__)


def load_resources(
    app,
    qdrant_client,
    collection_name,
    embedding_model,
    retriever_k,
    retriever_fetch_k,
    retriever_lambda,
    retriever_threshold,
    data_dir,
    summaries_dir,
    searxng_url=None,
    searxng_categories=None,
    pii_filter_client=None,
):
    """Laedt Embedding-Modelle, Vectorstore, Retriever und Agent.

    Alle Ressourcen werden in ``app.extensions`` abgelegt. Bei Fehlern
    (z.B. Modell-Download gescheitert) wird eine Exception ausgeloest.

    Args:
        app: Flask-Applikation (fuer ``app.extensions``).
        qdrant_client: Bereits verbundener Qdrant-Client.
        collection_name: Name der Qdrant-Collection.
        embedding_model: FastEmbed-Modellname (z.B.
            ``sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2``).
        retriever_k: Anzahl MMR-Ergebnisse.
        retriever_fetch_k: Anzahl Dokumente zum Abrufen (vor MMR).
        retriever_lambda: MMR-Balance (0=divers, 1=relevant).
        retriever_threshold: Mindest-Ähnlichkeitsscore.
        data_dir: Verzeichnis fuer CSV-/Excel-Dateien.
        summaries_dir: Verzeichnis fuer Markdown-Analysen.
        searxng_url: Optional — SearXNG-Metasuchmaschinen-URL.
        searxng_categories: Optional — Durchsuchbare Kategorien.
        pii_filter_client: Optional — PII-Filter-Client.
    """
    logger.info(f"Lade Embedding-Modell: {embedding_model}")
    dense_embeddings = FastEmbedEmbeddings(
        model_name=embedding_model,
    )
    sparse_embeddings = FastEmbedSparse(model_name="Qdrant/bm25")

    vectorstore = QdrantVectorStore(
        client=qdrant_client,
        collection_name=collection_name,
        embedding=dense_embeddings,
        sparse_embedding=sparse_embeddings,
        retrieval_mode=RetrievalMode.HYBRID,
    )

    retriever = vectorstore.as_retriever(
        search_type="mmr",
        search_kwargs={
            "k": retriever_k,
            "fetch_k": retriever_fetch_k,
            "lambda_mult": retriever_lambda,
            "score_threshold": retriever_threshold,
        },
    )

    llm = VisionLLM()
    custom_tools = CustomTools(
        llm=llm,
        retriever=retriever,
        data_dir=data_dir,
        summaries_dir=summaries_dir,
        searxng_url=searxng_url,
        searxng_categories=searxng_categories,
        pii_filter_client=pii_filter_client,
    )
    tools = custom_tools.get_tools()
    agent = DocumentAgent(llm=llm.llm_stream, tools=tools)

    app.extensions["dense_embeddings"] = dense_embeddings
    app.extensions["sparse_embeddings"] = sparse_embeddings
    app.extensions["vectorstore"] = vectorstore
    app.extensions["llm"] = llm
    app.extensions["agent"] = agent

    logger.info("Ressourcen bereit (Embedding-Modell + Agent).")
