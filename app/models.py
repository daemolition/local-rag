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
    Column, Integer, String, Text, Boolean,
    DateTime, ForeignKey
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class ChatSession(Base):
    """Chat-Sessions"""
    __tablename__ = 'sessions'

    id = Column(String(36), primary_key=True)
    title = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    messages = relationship("Message", back_populates="session", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<ChatSession(id='{self.id}', title='{self.title}')>"


class Message(Base):
    """Chat-Nachrichten"""
    __tablename__ = 'messages'

    id = Column(Integer, primary_key=True)
    session_id = Column(String(36), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(20), nullable=False)  # 'user' oder 'assistant'
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    session = relationship("ChatSession", back_populates="messages")

    def __repr__(self):
        return f"<Message(id={self.id}, session_id='{self.session_id}', role='{self.role}')>"


class UserDocument(Base):
    """Dokument-Tracking (eine Datei → mehrere Qdrant Chunks)"""
    __tablename__ = 'user_documents'

    id = Column(Integer, primary_key=True)
    document_id = Column(String(100), nullable=False, index=True)  # Qdrant file_group_id
    filename = Column(String(255), nullable=False)
    uploaded_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<UserDocument(id={self.id}, filename='{self.filename}')>"


class Setting(Base):
    """Key-Value Settings mit Metadaten"""
    __tablename__ = 'settings'

    key = Column(String(100), primary_key=True)
    value = Column(Text)
    default_value = Column(Text)
    category = Column(String(50), index=True)  # 'llm', 'embedding', 'retriever', 'storage', 'qdrant', 'auth'
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
    """Summary Markdown-Datei-Tracking"""
    __tablename__ = 'user_summary_files'

    id = Column(Integer, primary_key=True)
    filename = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<UserSummaryFile(id={self.id}, filename='{self.filename}')>"
