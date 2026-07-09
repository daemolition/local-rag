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
File Manager Utilities für Qdrant-zugehörige Dateien
"""
import os
from pathlib import Path
from typing import Optional, Dict, Any


def extract_filename_from_payload(payload: Dict[str, Any]) -> Optional[str]:
    """
    Extrahiert den Dateinamen aus Qdrant-Dokument-Payload.
    Prüft 'filename' und 'source' Felder.
    
    Args:
        payload: Qdrant Dokument Payload (dict)
    
    Returns:
        Dateiname oder None
    """
    if not payload:
        return None
    
    # Versuche filename zuerst
    filename = payload.get('filename')
    if filename:
        return filename
    
    # Fallback auf source
    source = payload.get('source')
    if source:
        # Source ist oft ein Pfad, extrahiere nur den Dateinamen
        return Path(source).name
    
    return None


def check_data_file_exists(filename: str) -> bool:
    """
    Prüft ob eine Datei im DATA_DIR existiert.
    
    Args:
        filename: Name der Datei
    
    Returns:
        True wenn Datei existiert, sonst False
    """
    from flask import current_app
    
    try:
        settings = current_app.extensions.get('settings')
        if settings:
            data_dir = settings.get('DATA_DIR', './data')
        else:
            data_dir = os.getenv('DATA_DIR', './data')
    except:
        data_dir = os.getenv('DATA_DIR', './data')
    
    file_path = Path(data_dir) / filename
    return file_path.exists() and file_path.is_file()


def delete_associated_file(payload: Dict[str, Any]) -> bool:
    """
    Löscht zugehörige Datei basierend auf Qdrant-Metadaten.

    Args:
        payload: Qdrant Dokument Payload (dict)

    Returns:
        True wenn Datei gelöscht wurde oder nicht existierte,
        False bei Fehler
    """
    filename = extract_filename_from_payload(payload)
    if not filename:
        return False

    ext = Path(filename).suffix.lower()

    if ext in ['.csv', '.xlsx', '.xls']:
        # CSV/Excel werden nach erfolgreicher Ingestion nach DATA_DIR verschoben
        try:
            from flask import current_app
            settings = current_app.extensions.get('settings')
            if settings:
                data_dir = settings.get('DATA_DIR', './data')
            else:
                data_dir = os.getenv('DATA_DIR', './data')
        except:
            data_dir = os.getenv('DATA_DIR', './data')

        candidates = [Path(data_dir) / filename]
    elif ext in ['.pdf', '.docx', '.doc']:
        # PDF/DOCX/DOC werden nach erfolgreicher Ingestion von data/files/<rel>
        # nach data/processed_files/<rel> verschoben (rel enthaelt die
        # Nutzer-Unterordner-Struktur). 'source' im Payload zeigt noch auf den
        # urspruenglichen data/files-Pfad zur Ingestion-Zeit.
        source = payload.get('source')
        candidates = []
        if source:
            try:
                rel_path = os.path.relpath(source, "./data/files")
                candidates.append(Path("./data/processed_files") / rel_path)
            except ValueError:
                pass
            candidates.append(Path(source))
        if not candidates:
            candidates = [Path("./data/processed_files") / filename]
    else:
        return False

    try:
        for file_path in candidates:
            if file_path.exists() and file_path.is_file():
                file_path.unlink()
                return True
    except Exception as e:
        # Fehler beim Löschen loggen aber nicht blockieren
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Fehler beim Löschen der Datei {filename}: {e}")
        return False

    return False


def get_data_file_info(filename: str) -> Optional[Dict[str, Any]]:
    """
    Holt Informationen über eine Datei im DATA_DIR.
    
    Args:
        filename: Name der Datei
    
    Returns:
        Dict mit file_info oder None
    """
    from flask import current_app
    
    try:
        settings = current_app.extensions.get('settings')
        if settings:
            data_dir = settings.get('DATA_DIR', './data')
        else:
            data_dir = os.getenv('DATA_DIR', './data')
    except:
        data_dir = os.getenv('DATA_DIR', './data')
    
    file_path = Path(data_dir) / filename
    
    if not file_path.exists() or not file_path.is_file():
        return None
    
    try:
        stat = file_path.stat()
        return {
            'filename': filename,
            'path': str(file_path),
            'size': stat.st_size,
            'size_human': _format_size(stat.st_size),
            'modified': stat.st_mtime
        }
    except Exception:
        return None


def _format_size(size_bytes: int) -> str:
    """Formatiert Bytes in menschenlesbare Größe."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
