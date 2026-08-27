"""async report generation: PENDING/PROCESSING statuses, stored totals

Revision ID: 0004_async_reports
Revises: 0003_add_barcode
Create Date: 2026-08-27
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0004_async_reports"
down_revision: Union[str, None] = "0003_add_barcode"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # New enum values. NOTE: the DB enum's existing members are "DRAFT"/
    # "FINAL" (uppercase) — SQLAlchemy's Enum column type stores by Python
    # enum *member name*, not `.value` (see app/models/report.py's
    # ReportStatusEnum, whose .value strings are lowercase for the JSON API
    # but whose .name — what actually gets persisted — is uppercase). New
    # values must match that existing convention, not the lowercase JSON
    # value, or every insert of a PENDING/PROCESSING report fails outright.
    #
    # Postgres 12+ allows ALTER TYPE ... ADD VALUE inside a transaction, but
    # the new value can't be used in that same transaction — fine here,
    # this migration only alters schema, never inserts rows.
    op.execute("ALTER TYPE report_status_enum ADD VALUE IF NOT EXISTS 'PENDING'")
    op.execute("ALTER TYPE report_status_enum ADD VALUE IF NOT EXISTS 'PROCESSING'")

    # Both null until the Celery task reaches FINAL (see app/tasks.py) —
    # stored so a generated report is a stable snapshot rather than
    # something recomputed (and able to silently change) on every read.
    # scale=2 matches SUMMARY_QUANT in app/services/reports.py ("708.20").
    op.add_column(
        "reports",
        sa.Column("total_emissions_kg_co2e", sa.Numeric(precision=14, scale=2), nullable=True),
    )
    op.add_column(
        "reports",
        sa.Column("facilities_breakdown", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("reports", "facilities_breakdown")
    op.drop_column("reports", "total_emissions_kg_co2e")

    # Postgres has no ALTER TYPE ... DROP VALUE. Rebuild the enum without
    # pending/processing: rename the old type aside, create the restricted
    # type, cast the column across, drop the renamed-aside type. Any row
    # actually using pending/processing would fail this cast — acceptable
    # for downgrading a dev-only feature; report generation is the only
    # writer of this column.
    op.execute("ALTER TYPE report_status_enum RENAME TO report_status_enum_old")
    restricted_enum = sa.Enum("DRAFT", "FINAL", name="report_status_enum")
    restricted_enum.create(op.get_bind())
    op.execute(
        "ALTER TABLE reports ALTER COLUMN status TYPE report_status_enum "
        "USING status::text::report_status_enum"
    )
    op.execute("DROP TYPE report_status_enum_old")
