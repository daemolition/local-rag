"""
Database Service mit SQLAlchemy
Ersetzt die bestehende database.py
"""
import os
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any
from werkzeug.security import generate_password_hash

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session as SQLAlchemySession

from app.models import Base, User, ChatSession, Message, UserDocument, Setting


class DatabaseService:
    """Zentraler Database Service für SQLAlchemy"""
    
    def __init__(self, db_path: str = "./app.db"):
        self.engine = create_engine(
            f'sqlite:///{db_path}',
            echo=False,  # True für Debugging
            connect_args={"check_same_thread": False}
        )
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
    
    def get_session(self) -> SQLAlchemySession:
        """Neue Session erstellen"""
        return self.Session()
    
    def init_default_data(self):
        """Erst-Setup: Default Users und Settings"""
        db = self.get_session()
        try:
            # Prüfen ob Users existieren
            if not db.query(User).first():
                self._create_default_users(db)
            
            # Settings initialisieren
            self._init_settings(db)
            
            db.commit()
        except Exception as e:
            db.rollback()
            raise e
        finally:
            db.close()
    
    def _create_default_users(self, db: SQLAlchemySession):
        """Initiale Users aus .env oder Defaults erstellen"""
        # Admin
        admin_pass = os.getenv("ADMIN_PASSWORD", "secret123")
        admin = User(
            username="admin",
            password_hash=generate_password_hash(admin_pass),
            is_admin=True
        )
        
        # Normaler User
        user_pass = os.getenv("USER_PASSWORD", "password123")
        user = User(
            username="user",
            password_hash=generate_password_hash(user_pass),
            is_admin=False
        )
        
        db.add_all([admin, user])
        print(f"Default Users erstellt: admin/{admin_pass}, user/{user_pass}")
    
    def _init_settings(self, db: SQLAlchemySession):
        """Settings mit .env-Werten initialisieren"""
        from app.settings_service import SettingsService
        
        settings_service = SettingsService(db)
        
        # Alle möglichen Settings definieren
        all_settings = {
            # LLM Settings
            'CHAT_MODEL': ('llm', 'qwen3:8b', 'Modell für Chat-Interaktionen'),
            'CHAT_BASEURL': ('llm', 'http://localhost:11434/v1', 'Ollama/OpenAI API URL'),
            'CHAT_TEMPERATURE': ('llm', '0.1', 'Temperatur für Chat (0.0-1.0)'),
            'CHAT_TOP_P': ('llm', '0.2', 'Top-P Sampling'),
            'VISION_MODEL': ('llm', 'qwen3-vl:8b', 'Vision-Modell für Bilder'),
            'VISION_BASEURL': ('llm', 'http://localhost:11434/v1', 'Vision API URL'),
            'API_KEY': ('llm', 'loc-123', 'API Key', True),
            
            # Legacy Fallback
            'MODEL': ('llm', '', 'Legacy: Model (wenn CHAT_MODEL nicht gesetzt)'),
            'BASEURL': ('llm', '', 'Legacy: BaseURL (wenn CHAT_BASEURL nicht gesetzt)'),
            'TEMPERATURE': ('llm', '0.1', 'Legacy: Temperature'),
            'TOP_P': ('llm', '0.2', 'Legacy: Top-P'),
            
            # Embedding Settings
            'EMBEDDING_SOURCE': ('embedding', 'local', 'Quelle: local oder endpoint'),
            'EMBEDDING_MODEL': ('embedding', 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2', 'Embedding Modell'),
            'EMBEDDING_ENDPOINT': ('embedding', 'http://localhost:8080/v1', 'Embedding Endpoint URL'),
            'EMBEDDING_DIMENSION': ('embedding', '384', 'Vektor-Dimension'),
            
            # Retriever Settings
            'RETRIEVER_K': ('retriever', '5', 'Anzahl Ergebnisse'),
            'RETRIEVER_FETCH_K': ('retriever', '30', 'Anzahl zum Fetchen'),
            'RETRIEVER_LAMBDA': ('retriever', '0.5', 'MMR Lambda (0.0-1.0)'),
            'RETRIEVER_SCORE_THRESHOLD': ('retriever', '0.2', 'Mindest-Score'),
            
            # Storage Settings
            'DATA_DIR': ('storage', './data', 'Daten-Verzeichnis'),
            'SUMMARIES_DIR': ('storage', './summaries', 'Summaries-Verzeichnis'),
            
            # Qdrant Settings
            'QDRANT_LOCAL': ('qdrant', 'true', 'Lokale DB (true) oder Remote (false)'),
            'QDRANT_HOST': ('qdrant', 'localhost', 'Qdrant Host'),
            'QDRANT_PORT': ('qdrant', '6333', 'Qdrant Port'),
            
            # Chat DB
            'CHAT_DB_PATH': ('storage', './chat_history.db', 'Pfad zur Chat DB (Legacy)'),
        }
        
        for key, config in all_settings.items():
            if len(config) == 4:
                category, default, description, is_sensitive = config
            else:
                category, default, description = config
                is_sensitive = False
            
            # Prüfen ob Setting bereits existiert
            existing = db.query(Setting).filter_by(key=key).first()
            if not existing:
                # Wert aus .env nehmen oder Default
                env_value = os.getenv(key)
                value = env_value if env_value is not None else default
                
                setting = Setting(
                    key=key,
                    value=value,
                    default_value=default,
                    category=category,
                    is_sensitive=is_sensitive,
                    description=description
                )
                db.add(setting)
    
    # === User Methods ===
    
    def get_user_by_username(self, username: str) -> Optional[User]:
        """User nach Username finden"""
        db = self.get_session()
        try:
            return db.query(User).filter_by(username=username).first()
        finally:
            db.close()
    
    def get_user_by_id(self, user_id: int) -> Optional[User]:
        """User nach ID finden"""
        db = self.get_session()
        try:
            return db.query(User).filter_by(id=user_id).first()
        finally:
            db.close()
    
    def create_user(self, username: str, password: str, is_admin: bool = False) -> User:
        """Neuen User erstellen"""
        db = self.get_session()
        try:
            user = User(
                username=username,
                password_hash=generate_password_hash(password),
                is_admin=is_admin
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            return user
        except Exception as e:
            db.rollback()
            raise e
        finally:
            db.close()
    
    def delete_user(self, user_id: int, transfer_to_admin: bool = True) -> bool:
        """User löschen, Dokumente dem Admin übertragen"""
        db = self.get_session()
        try:
            user = db.query(User).filter_by(id=user_id).first()
            if not user:
                return False
            
            if transfer_to_admin:
                # Admin finden
                admin = db.query(User).filter_by(is_admin=True).first()
                if admin:
                    # Dokumente übertragen
                    for doc in user.documents:
                        doc.user_id = admin.id
                    db.flush()
            
            db.delete(user)
            db.commit()
            return True
        except Exception as e:
            db.rollback()
            raise e
        finally:
            db.close()
    
    def toggle_admin(self, user_id: int) -> Optional[User]:
        """Admin-Status toggeln"""
        db = self.get_session()
        try:
            user = db.query(User).filter_by(id=user_id).first()
            if user:
                user.is_admin = not user.is_admin
                db.commit()
                db.refresh(user)
            return user
        except Exception as e:
            db.rollback()
            raise e
        finally:
            db.close()
    
    def list_users(self) -> List[User]:
        """Alle Users auflisten"""
        db = self.get_session()
        try:
            return db.query(User).order_by(User.username).all()
        finally:
            db.close()
    
    # === ChatSession Methods ===
    
    def create_session(self, user_id: int, title: Optional[str] = None) -> ChatSession:
        """Neue Session erstellen"""
        db = self.get_session()
        try:
            session = ChatSession(
                id=str(uuid.uuid4()),
                user_id=user_id,
                title=title
            )
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
    
    def list_sessions(self, user_id: int) -> List[ChatSession]:
        """Alle Sessions eines Users"""
        db = self.get_session()
        try:
            return db.query(ChatSession).filter_by(user_id=user_id).order_by(
                ChatSession.updated_at.desc()
            ).all()
        finally:
            db.close()
    
    def delete_session(self, session_id: str, user_id: int) -> bool:
        """Session löschen (nur wenn sie dem User gehört)"""
        db = self.get_session()
        try:
            session = db.query(ChatSession).filter_by(id=session_id, user_id=user_id).first()
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
            message = Message(
                session_id=session_id,
                role=role,
                content=content
            )
            db.add(message)
            
            # Session updated_at aktualisieren
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
            return db.query(Message).filter_by(session_id=session_id).order_by(
                Message.created_at.asc()
            ).limit(limit).all()
        finally:
            db.close()
    
    def get_last_session(self, user_id: int) -> Optional[ChatSession]:
        """Letzte Session eines Users"""
        db = self.get_session()
        try:
            return db.query(ChatSession).filter_by(user_id=user_id).order_by(
                ChatSession.updated_at.desc()
            ).first()
        finally:
            db.close()
    
    # === UserDocument Methods ===
    
    def add_document(self, user_id: int, document_id: str, filename: str) -> UserDocument:
        """Dokument-Zuordnung erstellen"""
        db = self.get_session()
        try:
            doc = UserDocument(
                user_id=user_id,
                document_id=document_id,
                filename=filename
            )
            db.add(doc)
            db.commit()
            db.refresh(doc)
            return doc
        except Exception as e:
            db.rollback()
            raise e
        finally:
            db.close()
    
    def get_user_documents(self, user_id: int) -> List[UserDocument]:
        """Dokumente eines Users"""
        db = self.get_session()
        try:
            return db.query(UserDocument).filter_by(user_id=user_id).order_by(
                UserDocument.uploaded_at.desc()
            ).all()
        finally:
            db.close()
    
    def get_all_documents(self) -> List[UserDocument]:
        """Alle Dokumente (für Admin)"""
        db = self.get_session()
        try:
            return db.query(UserDocument).order_by(UserDocument.uploaded_at.desc()).all()
        finally:
            db.close()
    
    def delete_user_document(self, doc_id: int, user_id: int = None) -> bool:
        """Dokument-Zuordnung löschen (optional: nur wenn User übereinstimmt)"""
        db = self.get_session()
        try:
            query = db.query(UserDocument).filter_by(id=doc_id)
            if user_id:
                query = query.filter_by(user_id=user_id)
            
            doc = query.first()
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
    
    def transfer_documents_to_user(self, from_user_id: int, to_user_id: int) -> int:
        """Alle Dokumente eines Users auf einen anderen übertragen"""
        db = self.get_session()
        try:
            count = db.query(UserDocument).filter_by(user_id=from_user_id).update(
                {UserDocument.user_id: to_user_id}
            )
            db.commit()
            return count
        except Exception as e:
            db.rollback()
            raise e
        finally:
            db.close()

    # === UserSummaryFile Methods ===

    def create_summary_file(self, user_id: int, filename: str) -> "UserSummaryFile":
        """Neue Summary-Datei-Eintrag erstellen"""
        db = self.get_session()
        try:
            from app.models import UserSummaryFile
            summary = UserSummaryFile(
                user_id=user_id,
                filename=filename
            )
            db.add(summary)
            db.commit()
            db.refresh(summary)
            return summary
        except Exception as e:
            db.rollback()
            raise e
        finally:
            db.close()

    def get_user_summaries(self, user_id: int) -> list:
        """Alle Summary-Dateien eines Users"""
        db = self.get_session()
        try:
            from app.models import UserSummaryFile
            return db.query(UserSummaryFile).filter_by(user_id=user_id).order_by(
                UserSummaryFile.created_at.desc()
            ).all()
        finally:
            db.close()

    def get_all_summaries(self) -> list:
        """Alle Summary-Dateien (für Admin)"""
        db = self.get_session()
        try:
            from app.models import UserSummaryFile
            return db.query(UserSummaryFile).order_by(
                UserSummaryFile.created_at.desc()
            ).all()
        finally:
            db.close()

    def get_summary_by_filename(self, filename: str) -> "UserSummaryFile | None":
        """Summary-Datei nach Filename finden"""
        db = self.get_session()
        try:
            from app.models import UserSummaryFile
            return db.query(UserSummaryFile).filter_by(filename=filename).first()
        finally:
            db.close()

    def delete_summary_file(self, file_id: int, user_id: int = None) -> bool:
        """Summary-Datei-Eintrag löschen (optional: nur wenn User übereinstimmt)"""
        db = self.get_session()
        try:
            from app.models import UserSummaryFile
            query = db.query(UserSummaryFile).filter_by(id=file_id)
            if user_id:
                query = query.filter_by(user_id=user_id)

            summary = query.first()
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

    def delete_summary_by_filename(self, filename: str, user_id: int = None) -> bool:
        """Summary-Datei-Eintrag nach Filename löschen"""
        db = self.get_session()
        try:
            from app.models import UserSummaryFile
            query = db.query(UserSummaryFile).filter_by(filename=filename)
            if user_id:
                query = query.filter_by(user_id=user_id)

            summary = query.first()
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

def init_db_service(db_path: str = "./app.db") -> DatabaseService:
    """Database Service initialisieren (Singleton)"""
    global db_service
    if db_service is None:
        db_service = DatabaseService(db_path)
    return db_service

def get_db_service() -> DatabaseService:
    """Bestehenden Database Service zurückgeben"""
    global db_service
    if db_service is None:
        raise RuntimeError("Database Service nicht initialisiert. Zuerst init_db_service() aufrufen.")
    return db_service
