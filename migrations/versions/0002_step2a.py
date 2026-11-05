"""ステップ 2a：授業の流れ（CourseFramework）・ボード・チャット・授業の設定

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-05
"""
from alembic import op
import sqlalchemy as sa


revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('chat_messages',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('course_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('role', sa.String(length=10), nullable=False),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['course_id'], ['courses.id'], name=op.f('fk_chat_messages_course_id_courses')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_chat_messages'))
    )
    op.create_table('course_frameworks',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('course_id', sa.Integer(), nullable=False),
    sa.Column('framework_key', sa.String(length=50), nullable=False),
    sa.Column('phases', sa.JSON(), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=10), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_by', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['course_id'], ['courses.id'], name=op.f('fk_course_frameworks_course_id_courses')),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_course_frameworks_created_by_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_course_frameworks')),
    sa.UniqueConstraint('course_id', 'framework_key', name=op.f('uq_course_frameworks_course_id_framework_key'))
    )
    op.create_table('boards',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('team_id', sa.Integer(), nullable=False),
    sa.Column('course_framework_id', sa.Integer(), nullable=False),
    sa.Column('framework_key', sa.String(length=50), nullable=False),
    sa.Column('chosen_by', sa.String(length=10), nullable=False),
    sa.Column('created_by', sa.Integer(), nullable=False),
    sa.Column('phase', sa.String(length=20), nullable=False),
    sa.Column('phase_ends_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('conclusion', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['course_framework_id'], ['course_frameworks.id'], name=op.f('fk_boards_course_framework_id_course_frameworks')),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_boards_created_by_users')),
    sa.ForeignKeyConstraint(['team_id'], ['teams.id'], name=op.f('fk_boards_team_id_teams')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_boards')),
    sa.UniqueConstraint('team_id', 'course_framework_id', name=op.f('uq_boards_team_id_course_framework_id'))
    )
    with op.batch_alter_table('courses', schema=None) as batch_op:
        batch_op.add_column(sa.Column('settings', sa.JSON(), nullable=False, server_default='{}'))



def downgrade() -> None:
    with op.batch_alter_table('courses', schema=None) as batch_op:
        batch_op.drop_column('settings')

    op.drop_table('boards')
    op.drop_table('course_frameworks')
    op.drop_table('chat_messages')
