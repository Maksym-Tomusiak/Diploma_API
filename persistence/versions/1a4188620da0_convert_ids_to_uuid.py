"""convert_ids_to_uuid_fixed

Revision ID: 1a4188620da0
Revises: 1cf5b422573d
Create Date: 2026-01-03 15:26:42.530815

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision: str = '1a4188620da0'
down_revision: Union[str, None] = '1cf5b422573d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Підключаємо розширення для UUID
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')

    # ---------------------------------------------------------
    # КРОК 1: Видалення ВСІХ старих зв'язків (Foreign Keys)
    # ---------------------------------------------------------
    # Ми мусимо "відв'язати" всі таблиці від Users та Documents перед зміною типів.
    
    # Видаляємо зв'язок logs -> users (ЦЬОГО НЕ ВИСТАЧАЛО МИНУЛОГО РАЗУ)
    op.drop_constraint('user_action_logs_user_id_fkey', 'user_action_logs', type_='foreignkey')
    
    op.drop_constraint('check_results_document_id_fkey', 'check_results', type_='foreignkey')
    op.drop_constraint('documents_user_id_fkey', 'documents', type_='foreignkey')

    # ---------------------------------------------------------
    # КРОК 2: Зміна Users
    # ---------------------------------------------------------
    op.alter_column('users', 'id', server_default=None)
    op.alter_column('users', 'id',
                    type_=sa.UUID(),
                    postgresql_using='gen_random_uuid()',
                    server_default=sa.text('gen_random_uuid()'))

    # ---------------------------------------------------------
    # КРОК 3: Зміна User Action Logs (Тільки user_id!)
    # ---------------------------------------------------------
    # PK (id) залишається Integer, але FK (user_id) стає UUID
    op.alter_column('user_action_logs', 'user_id',
                    type_=sa.UUID(),
                    # Оскільки база пуста, заповнюємо NULL або конвертуємо
                    postgresql_using='NULL') 

    # ---------------------------------------------------------
    # КРОК 4: Зміна Documents
    # ---------------------------------------------------------
    op.alter_column('documents', 'id', server_default=None)
    op.alter_column('documents', 'id',
                    type_=sa.UUID(),
                    postgresql_using='gen_random_uuid()',
                    server_default=sa.text('gen_random_uuid()'))
                    
    op.alter_column('documents', 'user_id',
                    type_=sa.UUID(),
                    postgresql_using='NULL')

    # ---------------------------------------------------------
    # КРОК 5: Зміна Check Results
    # ---------------------------------------------------------
    op.alter_column('check_results', 'id', server_default=None)
    op.alter_column('check_results', 'id',
                    type_=sa.UUID(),
                    postgresql_using='gen_random_uuid()',
                    server_default=sa.text('gen_random_uuid()'))
                    
    op.alter_column('check_results', 'document_id',
                    type_=sa.UUID(),
                    postgresql_using='NULL')

    # ---------------------------------------------------------
    # КРОК 6: Відновлення зв'язків (Foreign Keys)
    # ---------------------------------------------------------
    op.create_foreign_key('documents_user_id_fkey', 'documents', 'users', ['user_id'], ['id'])
    op.create_foreign_key('check_results_document_id_fkey', 'check_results', 'documents', ['document_id'], ['id'])
    
    # Відновлюємо зв'язок для логів
    op.create_foreign_key('user_action_logs_user_id_fkey', 'user_action_logs', 'users', ['user_id'], ['id'])


def downgrade() -> None:
    pass