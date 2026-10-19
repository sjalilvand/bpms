"""فاز ۵ — جدول‌های API بیرونی: کلید سرویس، idempotency، Webhook و تحویل رویداد

Revision ID: b7c2f91e4d05
Revises: 4518a7ff2128
Create Date: 2026-10-19

"""
from alembic import op
import sqlalchemy as sa

revision = 'b7c2f91e4d05'
down_revision = '4518a7ff2128'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'external_clients',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('key_id', sa.String(length=64), nullable=False),
        sa.Column('key_secret', sa.String(length=128), nullable=False),
        sa.Column('scopes', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('require_signature', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('rate_limit_per_min', sa.Integer(), nullable=False, server_default='60'),
        sa.Column('actor_username', sa.String(length=50), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_by_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('last_used_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_external_clients_key_id', 'external_clients', ['key_id'], unique=True)

    op.create_table(
        'external_idempotency',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('client_id', sa.Integer(), sa.ForeignKey('external_clients.id'), nullable=False),
        sa.Column('idempotency_key', sa.String(length=200), nullable=False),
        sa.Column('endpoint', sa.String(length=200), nullable=False),
        sa.Column('request_fingerprint', sa.String(length=64), nullable=False),
        sa.Column('response_status', sa.Integer(), nullable=False),
        sa.Column('response_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('client_id', 'idempotency_key', name='uq_external_idem'),
    )

    op.create_table(
        'webhook_endpoints',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('url', sa.String(length=500), nullable=False),
        sa.Column('secret', sa.String(length=128), nullable=False),
        sa.Column('events', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_by_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )

    op.create_table(
        'webhook_deliveries',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('endpoint_id', sa.Integer(), sa.ForeignKey('webhook_endpoints.id'), nullable=False),
        sa.Column('event_type', sa.String(length=80), nullable=False),
        sa.Column('payload_json', sa.JSON(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_status_code', sa.Integer(), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('delivered_at', sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table('webhook_deliveries')
    op.drop_table('webhook_endpoints')
    op.drop_table('external_idempotency')
    op.drop_index('ix_external_clients_key_id', table_name='external_clients')
    op.drop_table('external_clients')
