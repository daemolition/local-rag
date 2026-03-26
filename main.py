import streamlit as st
from langchain_qdrant import QdrantVectorStore, FastEmbedSparse, RetrievalMode
from langchain_huggingface import HuggingFaceEmbeddings
from qdrant_client import QdrantClient
from src.llm.local_llm import VisionLLM # Dein vorhandenes Modell
import os

# --- KONFIGURATION ---
st.set_page_config(page_title="Local RAG", layout="centered")
st.title("Local Document Chat")

# Einmalige Initialisierung (Caching spart Zeit beim Neuladen)
@st.cache_resource
def init_resources():
    # 1. Verbindung zu Qdrant
    client = QdrantClient(path="./local_qdrant.db")
    
    # 2. Embedding Modelle (MÜSSEN identisch zum Ingest sein!)
    dense_embeddings = HuggingFaceEmbeddings(
        model_name=os.getenv("EMBEDDING_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
    )
    sparse_embeddings = FastEmbedSparse(model_name="Qdrant/bm25")
    
    # 3. Vector Store
    vectorstore = QdrantVectorStore(
        client=client,
        collection_name="local_rag",
        embedding=dense_embeddings,
        sparse_embedding=sparse_embeddings,
        retrieval_mode=RetrievalMode.HYBRID
    )
    
    # 4. Lokales LLM
    llm = VisionLLM()
    
    return vectorstore, llm

vectorstore, llm = init_resources()

# --- CHAT HISTORY ---
if "messages" not in st.session_state:
    st.session_state.messages = []

# Verlauf anzeigen
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])


if prompt := st.chat_input("Frag mich was zu deinen Dokumenten..."):
    # User Nachricht anzeigen
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # RAG: Relevante Chunks suchen
    with st.spinner("Suche in Dokumenten..."):
        docs = vectorstore.similarity_search(prompt, k=4)
        context = "\n\n---\n\n".join([doc.page_content for doc in docs])
        sources = list(set([doc.metadata.get("filename", "Unbekannt") for doc in docs]))

    # Antwort generieren
    with st.chat_message("assistant"):
        # System Prompt für saubere Antworten
        full_prompt = f"""
        Nutze NUR den folgenden Kontext, um die Frage zu beantworten. 
        Falls du es nicht weißt, sag es einfach. Erfinde nichts.
        
        KONTEXT:
        {context}
        
        FRAGE:
        {prompt}
        
        ANTWORT:
        """
        
        # Hier nutzen wir dein VisionLLM.generate
        response = llm.generate(full_prompt)
        
        # Falls dein Modell ein Objekt zurückgibt, den Content extrahieren
        answer = response.content if hasattr(response, 'content') else str(response)
        
        # Quellen unter die Antwort hängen
        if sources:
            answer += f"\n\n**Quellen:** {', '.join(sources)}"
            
        st.markdown(answer)
        st.session_state.messages.append({"role": "assistant", "content": answer})
        
        
with st.expander("🔍 Qdrant Daten-Browser (Rohdaten)"):
    # Wir holen uns die letzten 20 Einträge
    try:
        records, _ = vectorstore.client.scroll(
            collection_name="local_rag",
            limit=20,
            with_payload=True,
            with_vectors=False # Vektoren sind für Menschen eh nur Zahlenmüll
        )
        
        for rec in records:
            st.json({
                "ID": rec.id,
                "Titel": rec.payload.get("title"),
                "Quelle": rec.payload.get("filename"),
                "Inhalt": rec.payload.get("page_content")[:200] + "..."
            })
    except Exception as e:
        st.error(f"Konnte Daten nicht laden: {e}")