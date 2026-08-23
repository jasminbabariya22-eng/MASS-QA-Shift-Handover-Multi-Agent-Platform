"""create_shift_handover_tables

Revision ID: e4f7a2b9101c
Revises: c1d5c37bd8cb
Create Date: 2026-08-22 16:25:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'e4f7a2b9101c'
down_revision: Union[str, Sequence[str], None] = 'c1d5c37bd8cb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create shift_handovers table
    op.create_table(
        'shift_handovers',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('handover_number', sa.String(length=50), nullable=False),
        sa.Column('workflow_code', sa.String(length=50), nullable=False, server_default='SHIFT_HANDOVER'),
        sa.Column('workflow_version', sa.String(length=20), nullable=False, server_default='1.0.0'),
        sa.Column('state', sa.String(length=50), nullable=False, server_default='DRAFT'),
        sa.Column('unit_id', sa.String(length=50), nullable=False),
        sa.Column('unit_name', sa.String(length=150), nullable=True),
        sa.Column('shift_type', sa.String(length=20), nullable=False, server_default='DAY'),
        sa.Column('shift_date', sa.String(length=20), nullable=False),
        sa.Column('outgoing_operator_id', sa.String(length=100), nullable=False),
        sa.Column('outgoing_operator_name', sa.String(length=150), nullable=True),
        sa.Column('incoming_operator_id', sa.String(length=100), nullable=True),
        sa.Column('incoming_operator_name', sa.String(length=150), nullable=True),
        sa.Column('supervisor_id', sa.String(length=100), nullable=True),
        sa.Column('operational_summary', sa.Text(), nullable=False, server_default=''),
        sa.Column('equipment_abnormalities', postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'), nullable=False),
        sa.Column('open_permits', postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'), nullable=False),
        sa.Column('loto_isolations', postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'), nullable=False),
        sa.Column('carry_forward_actions', postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'), nullable=False),
        sa.Column('all_safety_items_acknowledged', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False, server_default=sa.text('1')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('rejected_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_shift_handovers_handover_number'), 'shift_handovers', ['handover_number'], unique=True)
    op.create_index(op.f('ix_shift_handovers_state'), 'shift_handovers', ['state'], unique=False)
    op.create_index(op.f('ix_shift_handovers_unit_id'), 'shift_handovers', ['unit_id'], unique=False)
    op.create_index(op.f('ix_shift_handovers_shift_date'), 'shift_handovers', ['shift_date'], unique=False)
    op.create_index(op.f('ix_shift_handovers_outgoing_operator_id'), 'shift_handovers', ['outgoing_operator_id'], unique=False)
    op.create_index(op.f('ix_shift_handovers_incoming_operator_id'), 'shift_handovers', ['incoming_operator_id'], unique=False)
    op.create_index(op.f('ix_shift_handovers_supervisor_id'), 'shift_handovers', ['supervisor_id'], unique=False)
    op.create_index(op.f('ix_shift_handovers_created_at'), 'shift_handovers', ['created_at'], unique=False)

    # 2. Create shift_safety_critical_items table
    op.create_table(
        'shift_safety_critical_items',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('handover_id', sa.String(length=36), nullable=False),
        sa.Column('category', sa.String(length=50), nullable=False),
        sa.Column('equipment_tag', sa.String(length=100), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('acknowledged_by_incoming', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('acknowledged_by', sa.String(length=100), nullable=True),
        sa.Column('acknowledged_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['handover_id'], ['shift_handovers.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_shift_safety_critical_items_handover_id'), 'shift_safety_critical_items', ['handover_id'], unique=False)
    op.create_index(op.f('ix_shift_safety_critical_items_equipment_tag'), 'shift_safety_critical_items', ['equipment_tag'], unique=False)

    # 3. Create shift_handover_audits table
    op.create_table(
        'shift_handover_audits',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('handover_id', sa.String(length=36), nullable=False),
        sa.Column('from_state', sa.String(length=50), nullable=False),
        sa.Column('to_state', sa.String(length=50), nullable=False),
        sa.Column('action', sa.String(length=50), nullable=False),
        sa.Column('actor_id', sa.String(length=100), nullable=False),
        sa.Column('actor_role', sa.String(length=50), nullable=False),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('request_id', sa.String(length=100), nullable=True),
        sa.Column('session_id', sa.String(length=100), nullable=True),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['handover_id'], ['shift_handovers.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_shift_handover_audits_handover_id'), 'shift_handover_audits', ['handover_id'], unique=False)
    op.create_index(op.f('ix_shift_handover_audits_actor_id'), 'shift_handover_audits', ['actor_id'], unique=False)
    op.create_index(op.f('ix_shift_handover_audits_request_id'), 'shift_handover_audits', ['request_id'], unique=False)
    op.create_index(op.f('ix_shift_handover_audits_created_at'), 'shift_handover_audits', ['created_at'], unique=False)


def downgrade() -> None:
    op.drop_table('shift_handover_audits')
    op.drop_table('shift_safety_critical_items')
    op.drop_table('shift_handovers')
