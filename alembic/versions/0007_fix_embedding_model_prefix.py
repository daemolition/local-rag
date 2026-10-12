"""Fix bare EMBEDDING_MODEL name for existing databases

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-04

Migration 0003 lief fuer frische Installationen ins Leere: Migration 0001 legt
die settings-Tabelle leer an, die EMBEDDING_MODEL-Zeile entsteht erst danach
zur Laufzeit via DatabaseService._init_settings(). Dadurch blieb der nackte
Modellname (ohne 'sentence-transformers/'-Prefix) in der DB stehen, den
fastembed/TextEmbedding nicht kennt ("Model ... is not supported").

Diese Migration normalisiert sowohl value als auch default_value bestehender
Zeilen auf den HF-org-prefixed Namen.
"""

import sqlalchemy as sa

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

_BARE = "paraphrase-multilingual-MiniLM-L12-v2"
_PREFIXED = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "UPDATE settings SET value = :new "
            "WHERE key = 'EMBEDDING_MODEL' AND value = :old"
        ),
        {"new": _PREFIXED, "old": _BARE},
    )
    conn.execute(
        sa.text(
            "UPDATE settings SET default_value = :new "
            "WHERE key = 'EMBEDDING_MODEL' AND default_value = :old"
        ),
        {"new": _PREFIXED, "old": _BARE},
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "UPDATE settings SET value = :old "
            "WHERE key = 'EMBEDDING_MODEL' AND value = :new"
        ),
        {"old": _BARE, "new": _PREFIXED},
    )
    conn.execute(
        sa.text(
            "UPDATE settings SET default_value = :old "
            "WHERE key = 'EMBEDDING_MODEL' AND default_value = :new"
        ),
        {"old": _BARE, "new": _PREFIXED},
    )
