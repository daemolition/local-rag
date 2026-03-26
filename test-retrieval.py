import logging
from langchain_qdrant import QdrantVectorStore, FastEmbedSparse, RetrievalMode
from langchain_huggingface import HuggingFaceEmbeddings
from qdrant_client import QdrantClient

# Optional: Logging aktivieren, falls es knallt
logging.basicConfig(level=logging.INFO, format='%(message)s')

def test_retrieval():
    print("Verbinde mit lokaler Datenbank...")
    client = QdrantClient(path="./local_qdrant.db")
    
    # Prüfen ob die Collection überhaupt existiert
    if not client.collection_exists("local_rag"):
        print("Fehler: Collection 'local_rag' existiert nicht. Die DB ist leer.")
        return

    print("Lade Embedding-Modelle (das kann ein paar Sekunden dauern)...")
    # Hier exakt das Modell eintragen, das du beim Ingest genutzt hast
    dense_embeddings = HuggingFaceEmbeddings(
        model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    )
    sparse_embeddings = FastEmbedSparse(model_name="Qdrant/bm25")

    print("Initialisiere Hybrid-VectorStore...")
    vectorstore = QdrantVectorStore(
        client=client,
        collection_name="local_rag",
        embedding=dense_embeddings,
        sparse_embedding=sparse_embeddings,
        retrieval_mode=RetrievalMode.HYBRID
    )

    # Hier deinen Suchbegriff eintragen
    query = "EVV Zeugnis" 
    
    print(f"\nSuche nach: '{query}'\n")
    
    # k=3 holt die besten 3 Ergebnisse
    results = vectorstore.similarity_search(query, k=3)

    if not results:
        print("Keine Ergebnisse gefunden. Entweder ist der Suchbegriff falsch oder die Chunks sind leer.")
        return

    for i, doc in enumerate(results):
        print(f"--- Treffer {i+1} ---")
        print(f"Metadaten: {doc.metadata}")
        # Zeigt die ersten 300 Zeichen des Chunks an
        print(f"Inhalt: {doc.page_content[:300]}...\n")

if __name__ == "__main__":
    test_retrieval()