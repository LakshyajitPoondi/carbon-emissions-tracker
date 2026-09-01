"""Organization-scoped Product Library CRUD endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.authorization import (
    OrganizationAction,
    require_organization,
    require_product,
)
from app.database import get_db
from app.models.organization import Organization
from app.models.product import Product
from app.models.user import User
from app.schemas.product import ProductCreate, ProductResponse, ProductUpdate
from app.services.barcodes import (
    ean13_from_sequence,
    internal_ean13_sequence,
    is_valid_ean13,
    render_ean13_png,
)

router = APIRouter(
    prefix="/products",
    tags=["Products"],
    dependencies=[Depends(get_current_user)],
)

BARCODE_CONSTRAINT = "uq_products_organization_barcode"


def _barcode_conflict(barcode: str, organization_id: int) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={
            "code": "BARCODE_ALREADY_ASSIGNED",
            "message": (
                f"Barcode '{barcode}' is already assigned to another product "
                f"in organization {organization_id}"
            ),
        },
    )


def _barcode_is_taken(
    db: Session,
    organization_id: int,
    barcode: str | None,
    *,
    excluding_product_id: int | None = None,
) -> bool:
    if barcode is None:
        return False
    query = db.query(Product.id).filter(
        Product.organization_id == organization_id,
        Product.barcode == barcode,
    )
    if excluding_product_id is not None:
        query = query.filter(Product.id != excluding_product_id)
    return query.first() is not None


def _commit_product(db: Session, product: Product) -> None:
    """Commit with race-safe translation of the barcode unique constraint."""
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        constraint_name = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
        if constraint_name == BARCODE_CONSTRAINT and product.barcode is not None:
            raise _barcode_conflict(product.barcode, product.organization_id) from exc
        raise


def _next_generated_barcode(db: Session, organization_id: int) -> str:
    """Return the next restricted-circulation EAN for one organization.

    Locking the organization row serializes concurrent auto-generation for
    that organization, while the existing unique constraint remains the
    database-level final guard.
    """
    (
        db.query(Organization.id)
        .filter(Organization.id == organization_id)
        .with_for_update()
        .one()
    )
    sequences = [
        sequence
        for (barcode,) in db.query(Product.barcode)
        .filter(Product.organization_id == organization_id)
        .all()
        if barcode is not None
        for sequence in [internal_ean13_sequence(barcode)]
        if sequence is not None
    ]
    return ean13_from_sequence(max(sequences, default=0) + 1)


@router.post("", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
def create_product(
    body: ProductCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_organization(
        db, current_user, body.organization_id, OrganizationAction.WRITE
    )
    product_data = body.model_dump()
    barcode = body.barcode
    if barcode is None:
        barcode = _next_generated_barcode(db, body.organization_id)
        product_data["barcode"] = barcode
    elif _barcode_is_taken(db, body.organization_id, barcode):
        raise _barcode_conflict(barcode, body.organization_id)

    product = Product(
        **product_data,
        barcode_image=render_ean13_png(barcode) if is_valid_ean13(barcode) else None,
    )
    db.add(product)
    _commit_product(db, product)
    db.refresh(product)
    return product


@router.get("", response_model=list[ProductResponse])
def list_products(
    organization_id: int = Query(..., description="Filter by organization ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_organization(db, current_user, organization_id, OrganizationAction.VIEW)
    return (
        db.query(Product)
        .filter(Product.organization_id == organization_id)
        .order_by(Product.name.asc(), Product.id.asc())
        .all()
    )


@router.get("/{product_id}", response_model=ProductResponse)
def get_product(
    product_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return require_product(db, current_user, product_id, OrganizationAction.VIEW)


@router.get(
    "/{product_id}/barcode-image",
    response_class=Response,
    responses={200: {"content": {"image/png": {}}}},
)
def get_product_barcode_image(
    product_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    product = require_product(
        db, current_user, product_id, OrganizationAction.VIEW
    )
    if product.barcode_image is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "NOT_FOUND",
                "message": f"Barcode image for product {product_id} does not exist",
            },
        )
    return Response(
        content=product.barcode_image,
        media_type="image/png",
        headers={
            "Content-Disposition": (
                f'inline; filename="product-{product.id}-barcode.png"'
            )
        },
    )


@router.patch("/{product_id}", response_model=ProductResponse)
def update_product(
    product_id: int,
    body: ProductUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    product = require_product(
        db, current_user, product_id, OrganizationAction.WRITE
    )
    updates = body.model_dump(exclude_unset=True)
    next_barcode = updates.get("barcode", product.barcode)
    if _barcode_is_taken(
        db,
        product.organization_id,
        next_barcode,
        excluding_product_id=product.id,
    ):
        assert isinstance(next_barcode, str)
        raise _barcode_conflict(next_barcode, product.organization_id)

    for field_name, value in updates.items():
        setattr(product, field_name, value)
    if "barcode" in updates:
        product.barcode_image = (
            render_ean13_png(next_barcode)
            if isinstance(next_barcode, str) and is_valid_ean13(next_barcode)
            else None
        )
    _commit_product(db, product)
    db.refresh(product)
    return product


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(
    product_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    product = require_product(
        db, current_user, product_id, OrganizationAction.WRITE
    )
    db.delete(product)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
