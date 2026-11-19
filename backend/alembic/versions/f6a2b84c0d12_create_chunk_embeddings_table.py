"""create_chunk_embeddings_table

Revision ID: f6a2b84c0d12
Revises: e5f3a72b9c01
Create Date: 2026-11-19 11:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f6a2b84c0d12'
down_revision: Union[str, Sequence[str], None] = 'e5f3a72b9c01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create chunk_embeddings table and indexes."""
    op.create_table(
        'chunk_embeddings',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('chunk_id', sa.Uuid(), nullable=False),
        sa.Column('document_id', sa.Uuid(), nullable=False),
        sa.Column('provider', sa.String(length=64), nullable=False),
        sa.Column('model_name', sa.String(length=128), nullable=False),
        sa.Column('dimension', sa.Integer(), nullable=False),
        sa.Column('embedding', sa.JSON(), nullable=False),
        sa.Column('chunk_hash', sa.String(length=64), nullable=False),
        sa.Column('status', sa.String(length=32), server_default='completed', nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['chunk_id'], ['document_chunks.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )

    with op.batch_alter_table('chunk_embeddings', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_chunk_embeddings_chunk_id'), ['chunk_id'], unique=True)
        batch_op.create_index(batch_op.f('ix_chunk_embeddings_document_id'), ['document_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_chunk_embeddings_chunk_hash'), ['chunk_hash'], unique=False)
        batch_op.create_index(batch_op.f('ix_chunk_embeddings_status'), ['status'], unique=False)


def downgrade() -> None:
    """Drop chunk_embeddings table and indexes."""
    with op.batch_alter_table('chunk_embeddings', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_chunk_embeddings_status'))
        batch_op.drop_index(batch_op.f('ix_chunk_embeddings_chunk_hash'))
        batch_op.drop_index(batch_op.f('ix_chunk_embeddings_document_id'))
        batch_op.drop_index(batch_op.f('ix_chunk_embeddings_chunk_id'))

    op.drop_table('chunk_embeddings')
