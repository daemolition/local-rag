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
SQLAlchemy Models für Local Document RAG (Single-User)
"""

from datetime import datetime
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class User(Base):
    """Benutzer mit fester Rolle (admin, editor, user)."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String(80), nullable=False, unique=True)
    display_name = Column(String(120))
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, default="user")
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<User(id={self.id}, username='{self.username}', role='{self.role}')>"


class ChatSession(Base):
    """Chat-Sessions"""

    __tablename__ = "sessions"

    id = Column(String(36), primary_key=True)
    # Besitzer des Chats; NULL nur bei Altbestand vor dem Nutzermodell.
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    title = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    messages = relationship(
        "Message", back_populates="session", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<ChatSession(id='{self.id}', title='{self.title}')>"


class Message(Base):
    """Chat-Nachrichten"""

    __tablename__ = "messages"

    id = Column(Integer, primary_key=True)
    session_id = Column(
        String(36),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role = Column(String(20), nullable=False)  # 'user' oder 'assistant'
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    session = relationship("ChatSession", back_populates="messages")

    def __repr__(self):
        return f"<Message(id={self.id}, session_id='{self.session_id}', role='{self.role}')>"


class Knowledge(Base):
    """Knowledge-Bereich: eigene Qdrant-Collection mit eigener Ingestion-Konfiguration.

    Der Standard-Bereich (``is_default``) nutzt die urspruengliche Collection
    ``local_rag`` und die urspruenglichen Datei-Ordner.
    """

    __tablename__ = "knowledge"

    id = Column(Integer, primary_key=True)
    name = Column(String(120), nullable=False)
    description = Column(Text)
    collection_name = Column(String(100), nullable=False, unique=True)
    is_default = Column(Boolean, nullable=False, default=False)
    embedding_model = Column(String(255))
    embedding_dimension = Column(Integer)
    # Modell, mit dem die Vektoren entstanden (JSON, siehe app/rag/models_runtime.py), und
    # Signatur aus Modell + Chunk-Einstellungen + Parser/Splitter-Version.
    embedding_spec = Column(Text)
    index_signature = Column(String(32))
    last_reindex_error = Column(Text)
    # Fuer jeden angemeldeten Nutzer lesbar (ohne Freigabe).
    is_public = Column(Boolean, nullable=False, default=False)
    # Retrieval-Profil; NULL = Standardprofil.
    retrieval_profile_id = Column(
        Integer, ForeignKey("retrieval_profiles.id"), nullable=True
    )
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Knowledge(id={self.id}, name='{self.name}')>"


class Connection(Base):
    """LLM-Verbindung (OpenAI-kompatibel: LiteLLM, vLLM, Ollama, OpenAI, ...)."""

    __tablename__ = "connections"

    id = Column(Integer, primary_key=True)
    name = Column(String(120), nullable=False)
    base_url = Column(String(500), nullable=False)
    api_key = Column(Text)
    enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Connection(id={self.id}, name='{self.name}')>"


class ModelConfig(Base):
    """Konfiguration eines Modells einer Connection.

    ``is_clone=False``: Anpassung des Basismodells (Prompt, Parameter, Knowledge),
    hoechstens eine pro (connection_id, base_model). ``is_clone=True``: eigener
    Eintrag mit Namen, der wie ein weiteres Modell im Chat erscheint.
    """

    __tablename__ = "model_configs"

    id = Column(Integer, primary_key=True)
    connection_id = Column(
        Integer, ForeignKey("connections.id", ondelete="CASCADE"), nullable=False, index=True
    )
    base_model = Column(String(255), nullable=False)
    name = Column(String(120))
    is_clone = Column(Boolean, nullable=False, default=False)
    visible = Column(Boolean, nullable=False, default=True)
    system_prompt = Column(Text)
    replace_prompt = Column(Boolean, nullable=False, default=False)
    params = Column(Text)  # JSON-Objekt
    knowledge_ids = Column(Text)  # JSON-Liste oder NULL
    # Websuche (SearXNG) als Werkzeug; standardmaessig aus
    web_search = Column(Boolean, nullable=False, default=False)
    # Fuer jeden angemeldeten Nutzer nutzbar (ohne Freigabe).
    is_public = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<ModelConfig(id={self.id}, base_model='{self.base_model}')>"


class Group(Base):
    """Benutzergruppe fuer Freigaben."""

    __tablename__ = "groups"

    id = Column(Integer, primary_key=True)
    name = Column(String(80), nullable=False, unique=True)
    description = Column(Text)

    def __repr__(self):
        return f"<Group(id={self.id}, name='{self.name}')>"


class GroupMember(Base):
    __tablename__ = "group_members"

    group_id = Column(
        Integer, ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True
    )
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )


class ResourceGrant(Base):
    """Freigabe einer Ressource (knowledge | model) an einen Nutzer oder eine Gruppe."""

    __tablename__ = "resource_grants"
    __table_args__ = (
        UniqueConstraint(
            "resource_type", "resource_id", "principal_type", "principal_id",
            name="uq_resource_grant",
        ),
    )

    id = Column(Integer, primary_key=True)
    resource_type = Column(String(20), nullable=False, index=True)
    resource_id = Column(Integer, nullable=False, index=True)
    principal_type = Column(String(10), nullable=False)  # user | group
    principal_id = Column(Integer, nullable=False)
    access = Column(String(10), nullable=False, default="read")  # read | write


class RetrievalProfile(Base):
    """Benannte Abruf-Konfiguration (Suche, Reranking, Query-Enhancement, Kontext)."""

    __tablename__ = "retrieval_profiles"

    id = Column(Integer, primary_key=True)
    name = Column(String(80), nullable=False, unique=True)
    description = Column(Text)
    config = Column(Text, nullable=False)  # JSON (siehe app/rag/profiles.py)
    is_default = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<RetrievalProfile(id={self.id}, name='{self.name}')>"


class ChatAttachment(Base):
    """Im Chat hochgeladene Datei (gebunden an die Chat-Session)."""

    __tablename__ = "chat_attachments"

    id = Column(String(36), primary_key=True)
    session_id = Column(String(36), nullable=False, index=True)
    filename = Column(String(255), nullable=False)
    status = Column(String(20), nullable=False, default="processing")
    error = Column(Text)
    # Eigentuemer und gespeichertes Markdown (Anzeige/Loeschen unter "Meine Uploads")
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    markdown_path = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<ChatAttachment(id='{self.id}', filename='{self.filename}')>"


class UserDocument(Base):
    """Dokument-Tracking (eine Datei → mehrere Qdrant Chunks)"""

    __tablename__ = "user_documents"

    id = Column(Integer, primary_key=True)
    document_id = Column(
        String(100), nullable=False, index=True
    )  # Qdrant file_group_id
    filename = Column(String(255), nullable=False)
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    knowledge_id = Column(
        Integer, ForeignKey("knowledge.id"), nullable=True, index=True
    )
    # Gespeichertes Markdown des Dokuments (Basis fuer Neu-Indexieren und Ansicht).
    markdown_path = Column(String(500), nullable=True)
    parser_version = Column(Integer, nullable=True)
    # Wer die Datei hochgeladen hat (NULL = Altbestand/Skript)
    uploaded_by = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)

    def __repr__(self):
        return f"<UserDocument(id={self.id}, filename='{self.filename}')>"


class Setting(Base):
    """Key-Value Settings mit Metadaten"""

    __tablename__ = "settings"

    key = Column(String(100), primary_key=True)
    value = Column(Text)
    default_value = Column(Text)
    category = Column(
        String(50), index=True
    )  # 'llm', 'embedding', 'retriever', 'storage', 'qdrant', 'auth'
    is_sensitive = Column(Boolean, default=False)  # Für API_KEY Maskierung
    description = Column(Text)

    def __repr__(self):
        return f"<Setting(key='{self.key}', category='{self.category}')>"

    def get_display_value(self):
        """Maskierte Anzeige für sensitive Werte"""
        if self.is_sensitive and self.value:
            return "*" * min(len(self.value), 20)
        return self.value


class UserSummaryFile(Base):
    """Summary Markdown-Datei-Tracking"""

    __tablename__ = "user_summary_files"

    id = Column(Integer, primary_key=True)
    filename = Column(String(255), nullable=False)
    # Eigentuemer der Analyse (jeder Nutzer hat einen eigenen Ordner, siehe app/summaries.py)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<UserSummaryFile(id={self.id}, filename='{self.filename}')>"
