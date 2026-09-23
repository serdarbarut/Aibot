"""Oturumlara refresh token rotasyonu için sütunlar ekle

Revision ID: 004_session_rotation
Revises: 003_add_automation_tables
Create Date: 2026-09-24

Refresh token yenilenirken bir önceki token kısa süre (30 sn) geçerli kalır;
iki sekme aynı anda yenileme yaparsa kullanıcı oturumdan atılmaz.

- sessions.previous_refresh_token_jti: yenilemeden önceki token'ın jti değeri
- sessions.rotated_at: son yenileme zamanı (toleransın başlangıcı)
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '004_session_rotation'
down_revision: Union[str, None] = '003_add_automation_tables'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('sessions', sa.Column('previous_refresh_token_jti', sa.String(length=100), nullable=True))
    op.add_column('sessions', sa.Column('rotated_at', sa.DateTime(timezone=True), nullable=True))
    op.create_index(
        'ix_sessions_previous_refresh_token_jti',
        'sessions',
        ['previous_refresh_token_jti'],
    )


def downgrade() -> None:
    op.drop_index('ix_sessions_previous_refresh_token_jti', table_name='sessions')
    op.drop_column('sessions', 'rotated_at')
    op.drop_column('sessions', 'previous_refresh_token_jti')
