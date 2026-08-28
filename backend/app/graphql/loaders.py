"""DataLoaders for the N+1-prone nested Facility fields.

organization(id) { facilities { emissionsSummary(...) / emissionSources } }
resolves each of these once per facility. Without batching, an organization
with 20 facilities would fire 20 separate queries for either field.
Strawberry's DataLoader collects every .load(...) call made within the same
event-loop tick (i.e. every sibling facility's resolver call in one query
execution) into a single batch_load_fn call, so each loader below turns
"one query per facility" into one query for the whole batch.
"""

from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session
from strawberry.dataloader import DataLoader

from app.graphql.types import EmissionSourceType, EmissionsSummaryType
from app.models.emission_source import EmissionSource as EmissionSourceModel
from app.services.reports import ZERO, organization_emissions_by_source_type

EmissionsSummaryKey = tuple[int, date, date]  # (facility_id, start_date, end_date)


def make_emissions_summary_loader(db: Session) -> DataLoader[EmissionsSummaryKey, EmissionsSummaryType]:
    """Batches Facility.emissionsSummary(startDate, endDate) calls, grouped
    by (start_date, end_date) — the normal case where every facility in a
    request shares the same period — into one grouped SQL query per
    distinct period via organization_emissions_by_source_type. The
    realistic case (a client asking for the same period across every
    facility) collapses to exactly one query; even an atypical mixed-period
    request only costs one query per distinct period, never one per
    facility."""

    async def batch_load(keys: list[EmissionsSummaryKey]) -> list[EmissionsSummaryType]:
        facility_ids_by_period: dict[tuple[date, date], list[int]] = defaultdict(list)
        for facility_id, start_date, end_date in keys:
            facility_ids_by_period[(start_date, end_date)].append(facility_id)

        totals_by_period: dict[tuple[date, date], dict[int, dict[str, Decimal]]] = {
            period: organization_emissions_by_source_type(db, facility_ids, *period)
            for period, facility_ids in facility_ids_by_period.items()
        }

        results: list[EmissionsSummaryType] = []
        for facility_id, start_date, end_date in keys:
            by_source_type = totals_by_period[(start_date, end_date)][facility_id]
            total = sum(by_source_type.values(), ZERO)
            results.append(
                EmissionsSummaryType(
                    facility_id=facility_id,
                    period_start=start_date,
                    period_end=end_date,
                    total_emissions_kg_co2e=total,
                    # by_source_type is a generic JSON scalar (see
                    # EmissionsSummaryType) rather than Strawberry's typed
                    # Decimal scalar, so stringify values explicitly here —
                    # same "12045.30"-style string REST already returns,
                    # not left to whatever the JSON scalar's own encoder
                    # would otherwise do with a raw Decimal.
                    by_source_type={k: str(v) for k, v in by_source_type.items()},
                )
            )
        return results

    return DataLoader(load_fn=batch_load)


def make_emission_sources_loader(db: Session) -> DataLoader[int, list[EmissionSourceType]]:
    """Batches Facility.emissionSources calls: one query with
    facility_id IN (...) for every facility requested in the batch, instead
    of one GET-/emission-sources-equivalent query per facility."""

    async def batch_load(facility_ids: list[int]) -> list[list[EmissionSourceType]]:
        rows = (
            db.query(EmissionSourceModel)
            .filter(EmissionSourceModel.facility_id.in_(facility_ids))
            .all()
        )
        by_facility: dict[int, list[EmissionSourceType]] = defaultdict(list)
        for source in rows:
            by_facility[source.facility_id].append(
                EmissionSourceType(
                    id=source.id,
                    facility_id=source.facility_id,
                    source_type=source.source_type,
                    source_name=source.source_name,
                    unit_of_measurement=source.unit_of_measurement,
                    barcode_value=source.barcode_value,
                    created_at=source.created_at,
                    updated_at=source.updated_at,
                )
            )
        return [by_facility[facility_id] for facility_id in facility_ids]

    return DataLoader(load_fn=batch_load)
