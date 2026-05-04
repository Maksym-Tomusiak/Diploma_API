"""add is_banned column to users

Revision ID: b1a2c3d4e5f6
Revises: 3d45c21f4062
Create Date: 2025-12-12 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'b1a2c3d4e5f6'
down_revision = '3d45c21f4062'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('is_banned', sa.Boolean(), nullable=False, server_default=sa.text('false')))
    op.create_index(op.f('ix_users_is_banned'), 'users', ['is_banned'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_users_is_banned'), table_name='users')
    op.drop_column('users', 'is_banned')
