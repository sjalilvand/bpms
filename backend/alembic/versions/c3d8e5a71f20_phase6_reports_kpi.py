"""فاز ۶ — گزارش‌ساز/KPI: جدول گزارش‌های ذخیره‌شده

Revision ID: c3d8e5a71f20
Revises: b7c2f91e4d05
Create Date: 2026-10-19

"""
from alembic import op
import sqlalchemy as sa

revision = 'c3d8e5a71f20'
down_revision = 'b7c2f91e4d05'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'saved_reports',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(length=150), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('dataset', sa.String(length=40), nullable=False),
        sa.Column('definition', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('created_by_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('saved_reports')
