"""فاز ۸ — بانک سازمانی: فیلدهای سازمانی، بانک فرم‌ها و بانک فرایندها

Revision ID: a8f1c2d4e6b9
Revises: c3d8e5a71f20
Create Date: 2026-10-21

"""
from alembic import op
import sqlalchemy as sa

revision = 'a8f1c2d4e6b9'
down_revision = 'c3d8e5a71f20'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'org_fields',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('key', sa.String(length=80), nullable=False),
        sa.Column('label', sa.String(length=200), nullable=False),
        sa.Column('type', sa.String(length=40), nullable=False),
        sa.Column('category', sa.String(length=80), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('config_json', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('created_by_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_org_fields_key', 'org_fields', ['key'], unique=True)
    op.create_index('ix_org_fields_type', 'org_fields', ['type'])

    op.create_table(
        'form_templates',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('key', sa.String(length=80), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('category', sa.String(length=80), nullable=True),
        sa.Column('schema_json', sa.JSON(), nullable=False),
        sa.Column('created_by_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_form_templates_key', 'form_templates', ['key'], unique=True)
    op.create_index('ix_form_templates_category', 'form_templates', ['category'])

    op.create_table(
        'process_templates',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('key', sa.String(length=80), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('category', sa.String(length=80), nullable=True),
        sa.Column('bpmn_xml', sa.Text(), nullable=False),
        sa.Column('main_process_id', sa.String(length=120), nullable=True),
        sa.Column('config_json', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('created_by_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_process_templates_key', 'process_templates', ['key'], unique=True)
    op.create_index('ix_process_templates_category', 'process_templates', ['category'])


def downgrade() -> None:
    op.drop_table('process_templates')
    op.drop_table('form_templates')
    op.drop_table('org_fields')
