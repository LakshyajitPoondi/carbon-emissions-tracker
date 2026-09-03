"""Create Product consumption using a validated, snapshotted Product factor."""

from datetime import datetime, timezone
from decimal import Decimal, localcontext

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.authorization import OrganizationAction, require_facility, require_product
from app.models.consumption_record import ConsumptionRecord
from app.models.emission_calculation import EmissionCalculation
from app.models.product import Product
from app.models.user import User
from app.schemas.consumption_record import ConsumptionRecordCreate, ProductConsumptionSnapshot
from app.services.emissions import calculate_emissions
from app.services.product_configuration import validate_product_configuration


def create_product_consumption(
    db: Session, user: User, body: ConsumptionRecordCreate
) -> ConsumptionRecord:
    assert body.product_id is not None
    facility = require_facility(db, user, body.facility_id, OrganizationAction.ENTRY)
    require_product(db, user, body.product_id, OrganizationAction.ENTRY)
    # Serialize against Product edits/deletion so the factor and snapshot
    # come from the same version, and cannot lose their FK during insertion.
    product = (
        db.query(Product)
        .filter(Product.id == body.product_id, Product.organization_id == facility.organization_id)
        .populate_existing().with_for_update().first()
    )
    if product is None:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": f"Product {body.product_id} does not exist"})
    if product.consumption_unit is None or product.consumption_source_type is None:
        raise HTTPException(422, detail={
            "code": "PRODUCT_NOT_CONFIGURED",
            "message": "An OWNER or ADMIN must configure this Product's consumption unit and scope in Product Library first",
        })
    try:
        validate_product_configuration(product.consumption_unit, product.consumption_source_type, product.emissions_unit)
    except ValueError as exc:
        raise HTTPException(422, detail={"code": "PRODUCT_NOT_CONFIGURED", "message": str(exc)}) from exc
    if body.unit != product.consumption_unit:
        raise HTTPException(422, detail={
            "code": "PRODUCT_UNIT_MISMATCH",
            "message": f"This Product must be logged in {product.consumption_unit}",
        })
    with localcontext() as context:
        context.prec = 40
        emissions = calculate_emissions(body.quantity_consumed, product.emissions_value)
    if emissions > Decimal("9999999999.9999"):
        raise HTTPException(422, detail={"code": "VALIDATION_ERROR", "message": "Calculated Product emissions exceed the supported range"})
    snapshot = ProductConsumptionSnapshot.model_validate(product, from_attributes=True)
    record = ConsumptionRecord(
        product_id=product.id,
        product_organization_id=product.organization_id,
        product_snapshot=snapshot.model_dump(mode="json"),
        product_source_type=product.consumption_source_type,
        facility_id=facility.id,
        quantity_consumed=body.quantity_consumed,
        unit=body.unit,
        recorded_at=body.recorded_at,
        recorded_by=str(user.id),
    )
    db.add(record)
    db.flush()
    db.add(EmissionCalculation(
        consumption_record_id=record.id,
        emission_factor_id=None,
        calculated_emissions_kg_co2e=emissions,
        calculation_date=datetime.now(timezone.utc).date(),
    ))
    return record
