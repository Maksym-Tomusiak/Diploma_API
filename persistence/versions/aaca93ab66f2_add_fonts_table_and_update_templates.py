"""add_fonts_table_and_update_templates

Revision ID: aaca93ab66f2
Revises: b1a2c3d4e5f6
Create Date: 2025-12-19 19:57:02.548498

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'aaca93ab66f2'
down_revision: Union[str, None] = 'b1a2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create fonts table
    op.create_table('fonts',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('family', sa.String(length=255), nullable=False),
        sa.Column('category', sa.String(length=50), nullable=True),
        sa.Column('variants', sa.Text(), nullable=True),
        sa.Column('subsets', sa.Text(), nullable=True),
        sa.Column('version', sa.String(length=50), nullable=True),
        sa.Column('last_modified', sa.String(length=50), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('family')
    )
    op.create_index(op.f('ix_fonts_id'), 'fonts', ['id'], unique=False)
    op.create_index(op.f('ix_fonts_family'), 'fonts', ['family'], unique=True)
    
    # Add font_id column to templates table
    op.add_column('templates', sa.Column('font_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_templates_font_id'), 'templates', ['font_id'], unique=False)
    op.create_foreign_key('fk_templates_font_id', 'templates', 'fonts', ['font_id'], ['id'])


def downgrade() -> None:
    # Remove foreign key and font_id from templates
    op.drop_constraint('fk_templates_font_id', 'templates', type_='foreignkey')
    op.drop_index(op.f('ix_templates_font_id'), table_name='templates')
    op.drop_column('templates', 'font_id')
    
    # Drop fonts table
    op.drop_index(op.f('ix_fonts_family'), table_name='fonts')
    op.drop_index(op.f('ix_fonts_id'), table_name='fonts')
    op.drop_table('fonts')