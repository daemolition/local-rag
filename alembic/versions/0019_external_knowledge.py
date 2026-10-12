"""Externe Quellen als Knowledge

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-12

knowledge.kind ('local' | 'external') und knowledge.source_config (JSON: URL, Key, Collection,
Vektornamen, Feldzuordnung eines fremden Vektorspeichers). Bestehende Knowledge bleiben 'local'.

Idempotent (siehe Migration 0008).
"""

import sqlalchemy as sa

from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    cols = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("knowledge")}
    with op.batch_alter_table("knowledge") as batch_op:
        if "kind" not in cols:
            batch_op.add_column(
                sa.Column("kind", sa.String(20), nullable=False, server_default="local")
            )
        if "source_config" not in cols:
            batch_op.add_column(sa.Column("source_config", sa.Text, nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("knowledge") as batch_op:
        batch_op.drop_column("source_config")
        batch_op.drop_column("kind")
