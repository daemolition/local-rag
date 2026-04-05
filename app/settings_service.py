"""
Settings Service für zentrale Konfiguration
Liest aus DB mit Fallback auf Environment
"""
import os
from typing import Optional, Dict, List, Any
from sqlalchemy.orm import Session as SQLAlchemySession

from app.models import Setting


class SettingsService:
    """Zentraler Service für Settings Management"""
    
    CATEGORIES = {
        'llm': [
            'CHAT_MODEL', 'CHAT_BASEURL', 'CHAT_TEMPERATURE', 'CHAT_TOP_P',
            'VISION_MODEL', 'VISION_BASEURL', 'API_KEY',
            'MODEL', 'BASEURL', 'TEMPERATURE', 'TOP_P'
        ],
        'embedding': [
            'EMBEDDING_SOURCE', 'EMBEDDING_MODEL', 'EMBEDDING_ENDPOINT', 'EMBEDDING_DIMENSION'
        ],
        'retriever': [
            'RETRIEVER_K', 'RETRIEVER_FETCH_K', 'RETRIEVER_LAMBDA', 'RETRIEVER_SCORE_THRESHOLD'
        ],
        'storage': [
            'DATA_DIR', 'SUMMARIES_DIR', 'CHAT_DB_PATH'
        ],
        'qdrant': [
            'QDRANT_LOCAL', 'QDRANT_HOST', 'QDRANT_PORT', 'QDRANT_API_KEY'
        ]
    }
    
    SENSITIVE_KEYS = {'API_KEY', 'QDRANT_API_KEY'}
    
    DESCRIPTIONS = {
        'CHAT_MODEL': 'Modell für Chat-Interaktionen (z.B. qwen3:8b, buddy)',
        'CHAT_BASEURL': 'Ollama/OpenAI-Compatible API URL',
        'CHAT_TEMPERATURE': 'Kreativität des Modells (0.0 = deterministisch, 1.0 = kreativ)',
        'CHAT_TOP_P': 'Nucleus Sampling (0.0-1.0)',
        'VISION_MODEL': 'Vision-Modell für Bildverarbeitung in PDFs',
        'VISION_BASEURL': 'Vision API URL (falls anders als Chat)',
        'API_KEY': 'API Key für Authentifizierung',
        'MODEL': 'Legacy: Fallback wenn CHAT_MODEL nicht gesetzt',
        'BASEURL': 'Legacy: Fallback wenn CHAT_BASEURL nicht gesetzt',
        'TEMPERATURE': 'Legacy: Fallback für CHAT_TEMPERATURE',
        'TOP_P': 'Legacy: Fallback für CHAT_TOP_P',
        'EMBEDDING_SOURCE': 'Quelle: "local" (HuggingFace) oder "endpoint"',
        'EMBEDDING_MODEL': 'Embedding Modell Name',
        'EMBEDDING_ENDPOINT': 'URL für externen Embedding-Service',
        'EMBEDDING_DIMENSION': 'Vektor-Dimension (muss zum Modell passen)',
        'RETRIEVER_K': 'Anzahl Ergebnisse für RAG',
        'RETRIEVER_FETCH_K': 'Anzahl Dokumente zum Fetchen (vor MMR)',
        'RETRIEVER_LAMBDA': 'MMR Balance: 0.0 = divers, 1.0 = relevant',
        'RETRIEVER_SCORE_THRESHOLD': 'Mindest-Ähnlichkeitsscore',
        'DATA_DIR': 'Verzeichnis für Excel/CSV Dateien',
        'SUMMARIES_DIR': 'Verzeichnis für gespeicherte Analysen',
        'CHAT_DB_PATH': 'Pfad zur SQLite Chat-Datenbank (Legacy)',
        'QDRANT_LOCAL': 'Lokale .db Datei (true) oder Remote Server (false)',
        'QDRANT_HOST': 'Qdrant Server Host (nur bei QDRANT_LOCAL=false)',
        'QDRANT_PORT': 'Qdrant Server Port',
    }
    
    def __init__(self, db: SQLAlchemySession):
        self.db = db
    
    def get(self, key: str, default: Any = None) -> Optional[str]:
        """
        Setting-Wert holen (Reihenfolge: DB → Env → Default)
        """
        # 1. Aus DB lesen
        setting = self.db.query(Setting).filter_by(key=key).first()
        if setting and setting.value is not None:
            return setting.value
        
        # 2. Fallback auf Environment
        env_value = os.getenv(key)
        if env_value is not None:
            return env_value
        
        # 3. Default
        return default
    
    def get_int(self, key: str, default: int = 0) -> int:
        """Setting als Integer"""
        val = self.get(key, default)
        if val is None:
            return default
        try:
            return int(val)
        except (ValueError, TypeError):
            return default
    
    def get_float(self, key: str, default: float = 0.0) -> float:
        """Setting als Float"""
        val = self.get(key, default)
        if val is None:
            return default
        try:
            return float(val)
        except (ValueError, TypeError):
            return default
    
    def get_bool(self, key: str, default: bool = False) -> bool:
        """Setting als Boolean"""
        val = self.get(key, str(default).lower())
        if val is None:
            return default
        return str(val).lower() in ('true', '1', 'yes', 'on', 'enabled')
    
    def set(self, key: str, value: str) -> None:
        """Setting in DB speichern"""
        setting = self.db.query(Setting).filter_by(key=key).first()
        if setting:
            setting.value = value
        else:
            # Neue Setting anlegen
            category = self._get_category(key)
            is_sensitive = key in self.SENSITIVE_KEYS
            description = self.DESCRIPTIONS.get(key, '')
            default_value = os.getenv(key, '')
            
            setting = Setting(
                key=key,
                value=value,
                default_value=default_value,
                category=category,
                is_sensitive=is_sensitive,
                description=description
            )
            self.db.add(setting)
        
        self.db.commit()
    
    def set_batch(self, settings_dict: Dict[str, str]) -> None:
        """Mehrere Settings auf einmal speichern"""
        for key, value in settings_dict.items():
            self.set(key, value)
    
    def get_all_by_category(self) -> Dict[str, List[Setting]]:
        """Alle Settings gruppiert nach Kategorie (für Admin-Panel)"""
        settings = self.db.query(Setting).order_by(Setting.key).all()
        result = {cat: [] for cat in self.CATEGORIES.keys()}
        result['other'] = []  # Für Settings ohne Kategorie
        
        for setting in settings:
            cat = setting.category if setting.category in result else 'other'
            result[cat].append(setting)
        
        return result
    
    def reset_to_default(self, key: str) -> bool:
        """Ein Setting auf Default zurücksetzen"""
        setting = self.db.query(Setting).filter_by(key=key).first()
        if setting:
            setting.value = setting.default_value
            self.db.commit()
            return True
        return False
    
    def reset_category(self, category: str) -> int:
        """Alle Settings einer Kategorie zurücksetzen"""
        settings = self.db.query(Setting).filter_by(category=category).all()
        count = 0
        for setting in settings:
            setting.value = setting.default_value
            count += 1
        if count > 0:
            self.db.commit()
        return count
    
    def get_category_display_name(self, category: str) -> str:
        """Deutsche Anzeigenamen für Kategorien"""
        names = {
            'llm': 'LLM Einstellungen',
            'embedding': 'Embedding Einstellungen',
            'retriever': 'Retriever Einstellungen',
            'storage': 'Speicher Einstellungen',
            'qdrant': 'Qdrant Einstellungen',
            'other': 'Sonstige Einstellungen'
        }
        return names.get(category, category.capitalize())
    
    def get_missing_from_env(self) -> List[str]:
        """Settings die in .env existieren aber nicht in DB"""
        existing_keys = {s.key for s in self.db.query(Setting.key).all()}
        env_keys = set(os.environ.keys())
        return sorted(env_keys - existing_keys)
    
    def import_from_env(self, overwrite: bool = False) -> int:
        """Alle aktuellen .env-Werte in DB importieren"""
        count = 0
        for key in os.environ:
            if key.startswith('_'):  # Interne Vars überspringen
                continue
            
            existing = self.db.query(Setting).filter_by(key=key).first()
            if existing and not overwrite:
                continue
            
            value = os.getenv(key)
            if existing:
                existing.value = value
            else:
                category = self._get_category(key)
                is_sensitive = key in self.SENSITIVE_KEYS
                description = self.DESCRIPTIONS.get(key, '')
                
                setting = Setting(
                    key=key,
                    value=value,
                    default_value=value,
                    category=category,
                    is_sensitive=is_sensitive,
                    description=description
                )
                self.db.add(setting)
            count += 1
        
        if count > 0:
            self.db.commit()
        return count
    
    def _get_category(self, key: str) -> str:
        """Kategorie für einen Key bestimmen"""
        for cat, keys in self.CATEGORIES.items():
            if key in keys:
                return cat
        return 'other'
    
    # === Convenience Methods für häufige Settings ===
    
    def get_chat_model(self) -> str:
        """Chat Modell (mit Legacy Fallback)"""
        return self.get('CHAT_MODEL') or self.get('MODEL', 'qwen3:8b')
    
    def get_chat_baseurl(self) -> str:
        """Chat BaseURL (mit Legacy Fallback)"""
        return self.get('CHAT_BASEURL') or self.get('BASEURL', 'http://localhost:11434/v1')
    
    def get_chat_temperature(self) -> float:
        """Chat Temperatur (mit Legacy Fallback)"""
        temp = self.get('CHAT_TEMPERATURE') or self.get('TEMPERATURE', '0.1')
        try:
            return float(temp)
        except (ValueError, TypeError):
            return 0.1
    
    def get_chat_top_p(self) -> float:
        """Chat Top-P (mit Legacy Fallback)"""
        top_p = self.get('CHAT_TOP_P') or self.get('TOP_P', '0.2')
        try:
            return float(top_p)
        except (ValueError, TypeError):
            return 0.2
    
    def get_data_dir(self) -> str:
        """Daten-Verzeichnis"""
        return self.get('DATA_DIR', './data')
    
    def get_summaries_dir(self) -> str:
        """Summaries-Verzeichnis"""
        return self.get('SUMMARIES_DIR', './summaries')
    
    def get_embedding_dimension(self) -> int:
        """Embedding Dimension"""
        return self.get_int('EMBEDDING_DIMENSION', 384)
    
    def is_qdrant_local(self) -> bool:
        """Qdrant lokal oder remote?"""
        return self.get_bool('QDRANT_LOCAL', True)
