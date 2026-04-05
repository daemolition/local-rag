"""
SQLAlchemy Models für Local Document RAG
"""
from datetime import datetime
from sqlalchemy import (
    create_engine, Column, Integer, String, Text, Boolean, 
    DateTime, ForeignKey, Index, Float
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

Base = declarative_base()


class User(Base):
    """Benutzer mit Rollen"""
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    sessions = relationship("ChatSession", back_populates="user", cascade="all, delete-orphan")
    documents = relationship("UserDocument", back_populates="user", cascade="all, delete-orphan")
    summaries = relationship("UserSummaryFile", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User(id={self.id}, username='{self.username}', is_admin={self.is_admin})>"


class ChatSession(Base):
    """Chat-Sessions mit User-Relation"""
    __tablename__ = 'sessions'
    
    id = Column(String(36), primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, index=True)
    title = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="sessions")
    messages = relationship("Message", back_populates="session", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<ChatSession(id='{self.id}', user_id={self.user_id}, title='{self.title}')>"


class Message(Base):
    """Chat-Nachrichten"""
    __tablename__ = 'messages'
    
    id = Column(Integer, primary_key=True)
    session_id = Column(String(36), ForeignKey('sessions.id'), nullable=False, index=True)
    role = Column(String(20), nullable=False)  # 'user' oder 'assistant'
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    session = relationship("ChatSession", back_populates="messages")
    
    def __repr__(self):
        return f"<Message(id={self.id}, session_id='{self.session_id}', role='{self.role}')>"


class UserDocument(Base):
    """Zuordnung User ↔ Dokument (Qdrant)"""
    __tablename__ = 'user_documents'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, index=True)
    document_id = Column(String(100), nullable=False, index=True)  # Qdrant Point ID
    filename = Column(String(255), nullable=False)
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="documents")
    
    def __repr__(self):
        return f"<UserDocument(id={self.id}, user_id={self.user_id}, filename='{self.filename}')>"


class Setting(Base):
    """Key-Value Settings mit Metadaten"""
    __tablename__ = 'settings'
    
    key = Column(String(100), primary_key=True)
    value = Column(Text)
    default_value = Column(Text)
    category = Column(String(50), index=True)  # 'llm', 'embedding', 'storage', 'qdrant'
    is_sensitive = Column(Boolean, default=False)  # Für API_KEY Maskierung
    description = Column(Text)
    
    def __repr__(self):
        return f"<Setting(key='{self.key}', category='{self.category}')>"
    
    def get_display_value(self):
        """Maskierte Anzeige für sensitive Werte"""
        if self.is_sensitive and self.value:
            return '*' * min(len(self.value), 20)
        return self.value


class UserSummaryFile(Base):
    """Zuordnung User ↔ Summary Markdown-Datei"""
    __tablename__ = 'user_summary_files'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, index=True)
    filename = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="summaries")
    
    def __repr__(self):
        return f"<UserSummaryFile(id={self.id}, user_id={self.user_id}, filename='{self.filename}')>"
