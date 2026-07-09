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
SQLite Database for Chat Sessions and Messages
"""
import sqlite3
import os
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any

# Chat-History-DB. Default liegt im app-data-Volume (./data/chat_history.db
# -> Docker /app/data/chat_history.db). CHAT_DB_PATH-Env bleibt als Override.
DB_PATH = os.getenv("CHAT_DB_PATH", "./data/chat_history.db")


def get_db() -> sqlite3.Connection:
    """Get database connection with row factory"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Initialize database tables"""
    conn = get_db()
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            title TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
        CREATE INDEX IF NOT EXISTS idx_sessions_updated ON sessions(updated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
    ''')
    conn.commit()
    conn.close()


def create_session(user_id: str, title: Optional[str] = None) -> Dict[str, Any]:
    """Create a new chat session"""
    session_id = str(uuid.uuid4())
    conn = get_db()
    conn.execute(
        'INSERT INTO sessions (id, user_id, title) VALUES (?, ?, ?)',
        (session_id, user_id, title)
    )
    conn.commit()
    conn.close()
    return get_session(session_id)


def get_session(session_id: str) -> Optional[Dict[str, Any]]:
    """Get a session by ID"""
    conn = get_db()
    row = conn.execute(
        'SELECT * FROM sessions WHERE id = ?',
        (session_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def list_sessions(user_id: str) -> List[Dict[str, Any]]:
    """List all sessions for a user, newest first"""
    conn = get_db()
    rows = conn.execute(
        'SELECT * FROM sessions WHERE user_id = ? ORDER BY updated_at DESC',
        (user_id,)
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def delete_session(session_id: str, user_id: str) -> bool:
    """Delete a session (only if it belongs to the user)"""
    conn = get_db()
    cursor = conn.execute(
        'DELETE FROM sessions WHERE id = ? AND user_id = ?',
        (session_id, user_id)
    )
    conn.commit()
    deleted = cursor.rowcount > 0
    conn.close()
    return deleted


def update_session_title(session_id: str, title: str) -> bool:
    """Update session title"""
    conn = get_db()
    cursor = conn.execute(
        'UPDATE sessions SET title = ?, updated_at = ? WHERE id = ?',
        (title, datetime.now().isoformat(), session_id)
    )
    conn.commit()
    conn.close()
    return cursor.rowcount > 0


def save_message(session_id: str, role: str, content: str) -> None:
    """Save a message to a session"""
    conn = get_db()
    conn.execute(
        'INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)',
        (session_id, role, content)
    )
    # Update session's updated_at timestamp
    conn.execute(
        'UPDATE sessions SET updated_at = ? WHERE id = ?',
        (datetime.now().isoformat(), session_id)
    )
    conn.commit()
    conn.close()


def get_messages(session_id: str, limit: int = 100) -> List[Dict[str, Any]]:
    """Get all messages for a session"""
    conn = get_db()
    rows = conn.execute(
        'SELECT role, content, created_at FROM messages WHERE session_id = ? ORDER BY created_at ASC LIMIT ?',
        (session_id, limit)
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_last_session(user_id: str) -> Optional[Dict[str, Any]]:
    """Get the most recently updated session for a user"""
    conn = get_db()
    row = conn.execute(
        'SELECT * FROM sessions WHERE user_id = ? ORDER BY updated_at DESC LIMIT 1',
        (user_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None