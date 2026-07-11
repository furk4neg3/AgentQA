"""durable asynchronous batches

Revision ID: 0003_async_batches
Revises: 0002_production_platform
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_async_batches"
down_revision = "0002_production_platform"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("batch_runs") as batch:
        batch.add_column(sa.Column("cancelled_runs", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("queued_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("worker_id", sa.String(length=120), nullable=True))
        batch.add_column(sa.Column("failure_reason", sa.Text(), nullable=True))
        batch.add_column(sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"))
        batch.create_index("ix_batch_runs_heartbeat", ["status", "last_heartbeat_at"], unique=False)
    op.execute("UPDATE batch_runs SET queued_at = created_at WHERE queued_at IS NULL")


def downgrade() -> None:
    with op.batch_alter_table("batch_runs") as batch:
        batch.drop_index("ix_batch_runs_heartbeat")
        for name in ["retry_count", "failure_reason", "worker_id", "last_heartbeat_at", "queued_at", "cancelled_runs"]:
            batch.drop_column(name)
