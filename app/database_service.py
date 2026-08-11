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
Database Service mit SQLAlchemy (Single-User)
"""

import os
import uuid
from datetime import datetime
from typing import Optional, List
from werkzeug.security import generate_password_hash

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session as SQLAlchemySession

from app.models import (
    Base,
    ChatSession,
    Message,
    UserDocument,
    UserSummaryFile,
    Setting,
)


class DatabaseService:
    """Zentraler Database Service für SQLAlchemy (Single-User)"""

    def __init__(self, db_path: str = "./data/app.db"):
        self.engine = create_engine(
            f"sqlite:///{db_path}",
            echo=False,
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def get_session(self) -> SQLAlchemySession:
        """Neue Session erstellen"""
        return self.Session()

    def init_default_data(self):
        """Erst-Setup: Settings und App-Passwort initialisieren"""
        db = self.get_session()
        try:
            self._init_settings(db)
            self._init_app_password(db)
            db.commit()
        except Exception as e:
            db.rollback()
            raise e
        finally:
            db.close()

    def _init_settings(self, db: SQLAlchemySession):
        """Settings mit .env-Werten initialisieren"""

        all_settings = {
            "CHAT_MODEL": ("llm", "qwen3:8b", "Modell für Chat-Interaktionen"),
            "CHAT_BASEURL": (
                "llm",
                "http://localhost:11434/v1",
                "Ollama/OpenAI API URL",
            ),
            "CHAT_TEMPERATURE": ("llm", "0.1", "Temperatur für Chat (0.0-1.0)"),
            "CHAT_TOP_P": ("llm", "0.2", "Top-P Sampling"),
            "VISION_MODEL": ("llm", "qwen3-vl:8b", "Vision-Modell für Bilder"),
            "VISION_BASEURL": ("llm", "http://localhost:11434/v1", "Vision API URL"),
            "API_KEY": ("llm", "ollama", "API Key", True),
            "STT_MODEL": ("stt", "nemo-parakeet-tdt-0.6b-v3", "STT Modell"),
            "STT_BASEURL": ("stt", "http://parakeet:5001/v1", "STT API URL"),
            "STT_API_KEY": ("stt", "ollama", "STT API Key", True),
            "EMBEDDING_SOURCE": ("embedding", "local", "Quelle: local oder endpoint"),
            "EMBEDDING_MODEL": (
                "embedding",
                "paraphrase-multilingual-MiniLM-L12-v2",
                "Embedding Modell",
            ),
            "EMBEDDING_ENDPOINT": (
                "embedding",
                "http://localhost:8080/v1",
                "Embedding Endpoint URL",
            ),
            "EMBEDDING_DIMENSION": ("embedding", "384", "Vektor-Dimension"),
            "RETRIEVER_K": ("retriever", "5", "Anzahl Ergebnisse"),
            "RETRIEVER_FETCH_K": ("retriever", "30", "Anzahl zum Fetchen"),
            "RETRIEVER_LAMBDA": ("retriever", "0.5", "MMR Lambda (0.0-1.0)"),
            "RETRIEVER_SCORE_THRESHOLD": ("retriever", "0.2", "Mindest-Score"),
            "SECRET_KEY": (
                "auth",
                "",
                "Flask Secret Key (wird bei leerem Wert automatisch erzeugt)",
            ),
            "DATA_DIR": ("storage", "./data", "Daten-Verzeichnis"),
            "SUMMARIES_DIR": ("storage", "./data/summaries", "Summaries-Verzeichnis"),
            "QDRANT_HOST": ("qdrant", "localhost", "Qdrant Host"),
            "QDRANT_PORT": ("qdrant", "6333", "Qdrant Port"),
            "UI_THEME": ("ui", "system", "Oberflaeche: light, dark oder system"),
        }

        for key, config in all_settings.items():
            if len(config) == 4:
                category, default, description, is_sensitive = config
            else:
                category, default, description = config
                is_sensitive = False

            existing = db.query(Setting).filter_by(key=key).first()
            if not existing:
                env_value = os.getenv(key)
                value = env_value if env_value is not None else default

                setting = Setting(
                    key=key,
                    value=value,
                    default_value=default,
                    category=category,
                    is_sensitive=is_sensitive,
                    description=description,
                )
                db.add(setting)

        deprecated_keys = {"MODEL", "BASEURL", "TEMPERATURE", "TOP_P", "CHAT_DB_PATH"}
        db.query(Setting).filter(Setting.key.in_(deprecated_keys)).delete(
            synchronize_session=False
        )

        old_summaries = db.query(Setting).filter_by(key="SUMMARIES_DIR").first()
        if old_summaries and old_summaries.value == "./summaries":
            old_summaries.value = "./data/summaries"

    def _init_app_password(self, db: SQLAlchemySession):
        """APP_PASSWORD_HASH sicherstellen (Default aus .env oder 'admin')."""
        from app.settings_service import SettingsService

        settings_service = SettingsService(db)
        if not settings_service.get("APP_PASSWORD_HASH"):
            default_password = os.getenv("ADMIN_PASSWORD", "admin")
            settings_service.set(
                "APP_PASSWORD_HASH", generate_password_hash(default_password)
            )

    # === ChatSession Methods ===

    def create_session(self, title: Optional[str] = None) -> ChatSession:
        """Neue Session erstellen"""
        db = self.get_session()
        try:
            session = ChatSession(id=str(uuid.uuid4()), title=title)
            db.add(session)
            db.commit()
            db.refresh(session)
            return session
        except Exception as e:
            db.rollback()
            raise e
        finally:
            db.close()

    def get_chat_session(self, session_id: str) -> Optional[ChatSession]:
        """Chat-Session nach ID finden"""
        db = self.get_session()
        try:
            return db.query(ChatSession).filter_by(id=session_id).first()
        finally:
            db.close()

    def list_sessions(self) -> List[ChatSession]:
        """Alle Sessions auflisten"""
        db = self.get_session()
        try:
            return db.query(ChatSession).order_by(ChatSession.updated_at.desc()).all()
        finally:
            db.close()

    def delete_session(self, session_id: str) -> bool:
        """Session löschen"""
        db = self.get_session()
        try:
            session = db.query(ChatSession).filter_by(id=session_id).first()
            if session:
                db.delete(session)
                db.commit()
                return True
            return False
        except Exception as e:
            db.rollback()
            raise e
        finally:
            db.close()

    def update_session_title(self, session_id: str, title: str) -> bool:
        """Session-Titel aktualisieren"""
        db = self.get_session()
        try:
            session = db.query(ChatSession).filter_by(id=session_id).first()
            if session:
                session.title = title
                session.updated_at = datetime.utcnow()
                db.commit()
                return True
            return False
        except Exception as e:
            db.rollback()
            raise e
        finally:
            db.close()

    # === Message Methods ===

    def save_message(self, session_id: str, role: str, content: str) -> Message:
        """Nachricht speichern"""
        db = self.get_session()
        try:
            message = Message(session_id=session_id, role=role, content=content)
            db.add(message)

            session = db.query(ChatSession).filter_by(id=session_id).first()
            if session:
                session.updated_at = datetime.utcnow()

            db.commit()
            db.refresh(message)
            return message
        except Exception as e:
            db.rollback()
            raise e
        finally:
            db.close()

    def get_messages(self, session_id: str, limit: int = 100) -> List[Message]:
        """Nachrichten einer Session"""
        db = self.get_session()
        try:
            return (
                db.query(Message)
                .filter_by(session_id=session_id)
                .order_by(Message.created_at.asc())
                .limit(limit)
                .all()
            )
        finally:
            db.close()

    def get_last_session(self) -> Optional[ChatSession]:
        """Letzte Session"""
        db = self.get_session()
        try:
            return db.query(ChatSession).order_by(ChatSession.updated_at.desc()).first()
        finally:
            db.close()

    # === UserDocument Methods ===

    def add_document(self, document_id: str, filename: str) -> UserDocument:
        """Dokument-Zuordnung erstellen"""
        db = self.get_session()
        try:
            doc = UserDocument(document_id=document_id, filename=filename)
            db.add(doc)
            db.commit()
            db.refresh(doc)
            return doc
        except Exception as e:
            db.rollback()
            raise e
        finally:
            db.close()

    def get_all_documents(self) -> List[UserDocument]:
        """Alle Dokumente auflisten"""
        db = self.get_session()
        try:
            return (
                db.query(UserDocument).order_by(UserDocument.uploaded_at.desc()).all()
            )
        finally:
            db.close()

    def get_document_by_id(self, doc_id: int) -> Optional[UserDocument]:
        """Dokument nach ID finden"""
        db = self.get_session()
        try:
            return db.query(UserDocument).filter_by(id=doc_id).first()
        finally:
            db.close()

    def delete_user_document(self, doc_id: int) -> bool:
        """Dokument-Zuordnung löschen"""
        db = self.get_session()
        try:
            doc = db.query(UserDocument).filter_by(id=doc_id).first()
            if doc:
                db.delete(doc)
                db.commit()
                return True
            return False
        except Exception as e:
            db.rollback()
            raise e
        finally:
            db.close()

    # === UserSummaryFile Methods ===

    def create_summary_file(self, filename: str) -> UserSummaryFile:
        """Neue Summary-Datei-Eintrag erstellen"""
        db = self.get_session()
        try:
            summary = UserSummaryFile(filename=filename)
            db.add(summary)
            db.commit()
            db.refresh(summary)
            return summary
        except Exception as e:
            db.rollback()
            raise e
        finally:
            db.close()

    def get_all_summaries(self) -> list:
        """Alle Summary-Dateien auflisten"""
        db = self.get_session()
        try:
            from app.models import UserSummaryFile

            return (
                db.query(UserSummaryFile)
                .order_by(UserSummaryFile.created_at.desc())
                .all()
            )
        finally:
            db.close()

    def get_summary_by_filename(self, filename: str) -> UserSummaryFile | None:
        """Summary-Datei nach Filename finden"""
        db = self.get_session()
        try:
            return db.query(UserSummaryFile).filter_by(filename=filename).first()
        finally:
            db.close()

    def delete_summary_file(self, file_id: int) -> bool:
        """Summary-Datei-Eintrag löschen"""
        db = self.get_session()
        try:
            summary = db.query(UserSummaryFile).filter_by(id=file_id).first()
            if summary:
                db.delete(summary)
                db.commit()
                return True
            return False
        except Exception as e:
            db.rollback()
            raise e
        finally:
            db.close()

    def delete_summary_by_filename(self, filename: str) -> bool:
        """Summary-Datei-Eintrag nach Filename löschen"""
        db = self.get_session()
        try:
            from app.models import UserSummaryFile

            summary = db.query(UserSummaryFile).filter_by(filename=filename).first()
            if summary:
                db.delete(summary)
                db.commit()
                return True
            return False
        except Exception as e:
            db.rollback()
            raise e
        finally:
            db.close()


# Singleton für App-Context
db_service = None


def init_db_service(db_path: str = "./data/app.db") -> DatabaseService:
    """Database Service initialisieren (Singleton)"""
    global db_service
    if db_service is None:
        db_service = DatabaseService(db_path)
    return db_service


def get_db_service() -> DatabaseService:
    """Bestehenden Database Service zurückgeben"""
    global db_service
    if db_service is None:
        raise RuntimeError(
            "Database Service nicht initialisiert. Zuerst init_db_service() aufrufen."
        )
    return db_service
