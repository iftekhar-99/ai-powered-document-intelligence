"""add_invoice_correction_audit

Revision ID: d4e2f61a8b90
Revises: c3a1e5094d21
Create Date: 2026-11-19 01:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4e2f61a8b90'
down_revision: Union[str, Sequence[str], None] = 'c3a1e5094d21'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 1. Add is_manually_corrected column to invoices
    with op.batch_alter_table('invoices', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('is_manually_corrected', sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch_op.create_index(
            batch_op.f('ix_invoices_is_manually_corrected'), ['is_manually_corrected'], unique=False
        )

    # 2. Create invoice_correction_audits table
    op.create_table(
        'invoice_correction_audits',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('invoice_id', sa.Uuid(), nullable=False),
        sa.Column('correction_type', sa.String(length=64), nullable=False),
        sa.Column('changed_fields', sa.JSON(), nullable=False),
        sa.Column('previous_values', sa.JSON(), nullable=False),
        sa.Column('new_values', sa.JSON(), nullable=False),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('corrected_by', sa.String(length=128), nullable=True),
        sa.Column('corrected_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['invoice_id'], ['invoices.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('invoice_correction_audits', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_invoice_correction_audits_invoice_id'), ['invoice_id'], unique=False
        )
        batch_op.create_index(
            batch_op.f('ix_invoice_correction_audits_corrected_at'), ['corrected_at'], unique=False
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('invoice_correction_audits', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_invoice_correction_audits_corrected_at'))
        batch_op.drop_index(batch_op.f('ix_invoice_correction_audits_invoice_id'))

    op.drop_table('invoice_correction_audits')

    with op.batch_alter_table('invoices', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_invoices_is_manually_corrected'))
        batch_op.drop_column('is_manually_corrected')
