"""extend_validation_issue_fields

Revision ID: e5f3a72b9c01
Revises: d4e2f61a8b90
Create Date: 2026-11-19 01:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5f3a72b9c01'
down_revision: Union[str, Sequence[str], None] = 'd4e2f61a8b90'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('validation_issues', schema=None) as batch_op:
        batch_op.add_column(sa.Column('line_item_id', sa.Uuid(), nullable=True))
        batch_op.add_column(sa.Column('expected_value', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('observed_value', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('resolved_by', sa.String(length=128), nullable=True))
        batch_op.add_column(sa.Column('resolution_notes', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('related_invoice_id', sa.Uuid(), nullable=True))
        batch_op.add_column(sa.Column('related_document_id', sa.Uuid(), nullable=True))

        batch_op.create_foreign_key(
            'fk_validation_issues_line_item_id',
            'invoice_line_items',
            ['line_item_id'],
            ['id'],
            ondelete='SET NULL',
        )
        batch_op.create_foreign_key(
            'fk_validation_issues_related_invoice_id',
            'invoices',
            ['related_invoice_id'],
            ['id'],
            ondelete='SET NULL',
        )
        batch_op.create_foreign_key(
            'fk_validation_issues_related_document_id',
            'documents',
            ['related_document_id'],
            ['id'],
            ondelete='SET NULL',
        )

        batch_op.create_index(
            batch_op.f('ix_validation_issues_line_item_id'), ['line_item_id'], unique=False
        )
        batch_op.create_index(
            batch_op.f('ix_validation_issues_related_invoice_id'), ['related_invoice_id'], unique=False
        )
        batch_op.create_index(
            batch_op.f('ix_validation_issues_related_document_id'), ['related_document_id'], unique=False
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('validation_issues', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_validation_issues_related_document_id'))
        batch_op.drop_index(batch_op.f('ix_validation_issues_related_invoice_id'))
        batch_op.drop_index(batch_op.f('ix_validation_issues_line_item_id'))

        batch_op.drop_constraint('fk_validation_issues_related_document_id', type_='foreignkey')
        batch_op.drop_constraint('fk_validation_issues_related_invoice_id', type_='foreignkey')
        batch_op.drop_constraint('fk_validation_issues_line_item_id', type_='foreignkey')

        batch_op.drop_column('related_document_id')
        batch_op.drop_column('related_invoice_id')
        batch_op.drop_column('resolution_notes')
        batch_op.drop_column('resolved_by')
        batch_op.drop_column('resolved_at')
        batch_op.drop_column('observed_value')
        batch_op.drop_column('expected_value')
        batch_op.drop_column('line_item_id')
