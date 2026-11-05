"""ステップ 2b：付箋（Note）

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-05
"""
from alembic import op
import sqlalchemy as sa


revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('notes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('board_id', sa.Integer(), nullable=False),
    sa.Column('author_id', sa.Integer(), nullable=False),
    sa.Column('zone_key', sa.String(length=50), nullable=True),
    sa.Column('x', sa.Float(), nullable=False),
    sa.Column('y', sa.Float(), nullable=False),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('cluster_id', sa.Integer(), nullable=True),
    sa.Column('source_note_id', sa.Integer(), nullable=True),
    sa.Column('source_cluster_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['author_id'], ['users.id'], name=op.f('fk_notes_author_id_users')),
    sa.ForeignKeyConstraint(['board_id'], ['boards.id'], name=op.f('fk_notes_board_id_boards')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_notes'))
    )


def downgrade() -> None:
    op.drop_table('notes')
