"""Gruppen und Freigaben

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-12

- groups, group_members, resource_grants: Freigaben von Knowledge und Modellen
  an Gruppen oder einzelne Nutzer.
- knowledge.is_public / model_configs.is_public: fuer alle angemeldeten Nutzer
  nutzbar. Bestehende Knowledge-Bereiche werden oeffentlich gesetzt, damit sich
  fuer vorhandene Installationen nichts aendert; neue sind privat.

Idempotent (siehe Migration 0008).
"""

import sqlalchemy as sa

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = set(insp.get_table_names())

    if "groups" not in tables:
        op.create_table(
            "groups",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("name", sa.String(80), nullable=False, unique=True),
            sa.Column("description", sa.Text),
        )
    if "group_members" not in tables:
        op.create_table(
            "group_members",
            sa.Column(
                "group_id",
                sa.Integer,
                sa.ForeignKey("groups.id", ondelete="CASCADE"),
                primary_key=True,
            ),
            sa.Column(
                "user_id",
                sa.Integer,
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                primary_key=True,
            ),
        )
    if "resource_grants" not in tables:
        op.create_table(
            "resource_grants",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("resource_type", sa.String(20), nullable=False, index=True),
            sa.Column("resource_id", sa.Integer, nullable=False, index=True),
            sa.Column("principal_type", sa.String(10), nullable=False),
            sa.Column("principal_id", sa.Integer, nullable=False),
            sa.Column("access", sa.String(10), nullable=False),
            sa.UniqueConstraint(
                "resource_type",
                "resource_id",
                "principal_type",
                "principal_id",
                name="uq_resource_grant",
            ),
        )

    if "is_public" not in {c["name"] for c in insp.get_columns("knowledge")}:
        with op.batch_alter_table("knowledge") as batch_op:
            batch_op.add_column(
                sa.Column(
                    "is_public", sa.Boolean, nullable=False, server_default=sa.false()
                )
            )
        # Bestand bleibt fuer alle sichtbar wie bisher.
        conn.execute(sa.text("UPDATE knowledge SET is_public = :t"), {"t": True})

    if "is_public" not in {c["name"] for c in insp.get_columns("model_configs")}:
        with op.batch_alter_table("model_configs") as batch_op:
            batch_op.add_column(
                sa.Column(
                    "is_public", sa.Boolean, nullable=False, server_default=sa.true()
                )
            )


def downgrade() -> None:
    with op.batch_alter_table("model_configs") as batch_op:
        batch_op.drop_column("is_public")
    with op.batch_alter_table("knowledge") as batch_op:
        batch_op.drop_column("is_public")
    op.drop_table("resource_grants")
    op.drop_table("group_members")
    op.drop_table("groups")
