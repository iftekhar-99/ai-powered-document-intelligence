"""add_extraction_runs_and_invoice_fields

Revision ID: c3a1e5094d21
Revises: ae7cf57c8c76
Create Date: 2026-11-19 00:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3a1e5094d21'
down_revision: Union[str, Sequence[str], None] = 'ae7cf57c8c76'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 1. Create extraction_runs table
    op.create_table(
        'extraction_runs',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('document_id', sa.Uuid(), nullable=False),
        sa.Column('provider', sa.String(length=64), nullable=False),
        sa.Column('model_name', sa.String(length=128), nullable=False),
        sa.Column('prompt_version', sa.String(length=64), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('processing_time_ms', sa.Integer(), nullable=True),
        sa.Column('input_token_count', sa.Integer(), nullable=True),
        sa.Column('output_token_count', sa.Integer(), nullable=True),
        sa.Column('total_contexts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('successful_contexts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('skipped_contexts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('failed_contexts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('extraction_runs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_extraction_runs_document_id'), ['document_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_extraction_runs_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_extraction_runs_created_at'), ['created_at'], unique=False)

    # 2. Alter invoices table
    # Drop unique constraint/index on document_id and add new provenance and metadata columns
    with op.batch_alter_table('invoices', schema=None) as batch_op:
        batch_op.drop_index('ix_invoices_document_id')
        batch_op.create_index(batch_op.f('ix_invoices_document_id'), ['document_id'], unique=False)

        batch_op.add_column(sa.Column('extraction_run_id', sa.Uuid(), nullable=True))
        batch_op.add_column(sa.Column('source_context_id', sa.Uuid(), nullable=True))
        batch_op.add_column(sa.Column('field_evidence', sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column('field_confidence', sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column('extraction_metadata', sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column('needs_manual_review', sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column('document_page_start', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('document_page_end', sa.Integer(), nullable=True))

        batch_op.create_foreign_key(
            'fk_invoices_extraction_run_id',
            'extraction_runs',
            ['extraction_run_id'],
            ['id'],
            ondelete='CASCADE',
        )
        batch_op.create_index(batch_op.f('ix_invoices_extraction_run_id'), ['extraction_run_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_invoices_source_context_id'), ['source_context_id'], unique=False)
        batch_op.create_unique_constraint(
            'uq_invoice_run_context',
            ['extraction_run_id', 'source_context_id'],
        )

    # 3. Alter invoice_line_items table
    with op.batch_alter_table('invoice_line_items', schema=None) as batch_op:
        batch_op.add_column(sa.Column('field_evidence', sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column('field_confidence', sa.JSON(), nullable=True))
        batch_op.add_column(
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('invoice_line_items', schema=None) as batch_op:
        batch_op.drop_column('created_at')
        batch_op.drop_column('field_confidence')
        batch_op.drop_column('field_evidence')

    with op.batch_alter_table('invoices', schema=None) as batch_op:
        batch_op.drop_constraint('uq_invoice_run_context', type_='unique')
        batch_op.drop_constraint('fk_invoices_extraction_run_id', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_invoices_source_context_id'))
        batch_op.drop_index(batch_op.f('ix_invoices_extraction_run_id'))
        batch_op.drop_column('document_page_end')
        batch_op.drop_column('document_page_start')
        batch_op.drop_column('needs_manual_review')
        batch_op.drop_column('extraction_metadata')
        batch_op.drop_column('field_confidence')
        batch_op.drop_column('field_evidence')
        batch_op.drop_column('source_context_id')
        batch_op.drop_column('extraction_run_id')

        batch_op.drop_index('ix_invoices_document_id')
        batch_op.create_index(batch_op.f('ix_invoices_document_id'), ['document_id'], unique=True)

    with op.batch_alter_table('extraction_runs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_extraction_runs_created_at'))
        batch_op.drop_index(batch_op.f('ix_extraction_runs_status'))
        batch_op.drop_index(batch_op.f('ix_extraction_runs_document_id'))

    op.drop_table('extraction_runs')
