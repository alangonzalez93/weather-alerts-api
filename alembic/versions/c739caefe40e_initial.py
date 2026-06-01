"""initial

Revision ID: c739caefe40e
Revises:
Create Date: 2026-06-01 11:09:26.351623

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c739caefe40e"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "weather_forecasts",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("zone", sa.String(100), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("probability", sa.Float(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "probability >= 0.0 AND probability <= 1.0",
            name="ck_weather_forecasts_probability",
        ),
        sa.UniqueConstraint(
            "zone", "date", "event_type", name="uq_weather_forecasts_zone_date_event"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    # Column order matches the evaluator query pattern: zone → event_type → date range
    op.create_index(
        "ix_weather_forecasts_zone_event_date", "weather_forecasts", ["zone", "event_type", "date"]
    )


def downgrade() -> None:
    op.drop_index("ix_weather_forecasts_zone_event_date", table_name="weather_forecasts")
    op.drop_table("weather_forecasts")
