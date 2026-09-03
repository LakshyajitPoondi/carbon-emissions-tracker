"""Pydantic schemas for the organization-scoped Product Library."""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.emission_source import SourceTypeEnum
from app.services.product_configuration import validate_product_configuration


class ProductCreate(BaseModel):
    organization_id: int
    name: str = Field(max_length=255)
    barcode: Optional[str] = Field(default=None, max_length=255)
    composition: str
    emissions_value: Decimal = Field(ge=0, max_digits=18, decimal_places=6)
    emissions_unit: str = Field(max_length=100)
    consumption_unit: Optional[str] = Field(default=None, max_length=50)
    consumption_source_type: Optional[SourceTypeEnum] = None
    emissions_description: str
    source_reference: str

    @field_validator(
        "name",
        "composition",
        "emissions_unit",
        "emissions_description",
        "source_reference",
    )
    @classmethod
    def required_text_not_blank(cls, value: str, info) -> str:
        if not value or not value.strip():
            raise ValueError(f"{info.field_name} must not be empty")
        return value.strip()

    @field_validator("barcode")
    @classmethod
    def normalize_barcode(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return value.strip() or None

    @field_validator("consumption_unit")
    @classmethod
    def normalize_consumption_unit(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and not value.strip():
            raise ValueError("consumption_unit must not be blank")
        return value.strip() if value is not None else None

    @model_validator(mode="after")
    def validate_configuration(self):
        validate_product_configuration(
            self.consumption_unit, self.consumption_source_type, self.emissions_unit
        )
        return self


class ProductUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=255)
    barcode: Optional[str] = Field(default=None, max_length=255)
    composition: Optional[str] = None
    emissions_value: Optional[Decimal] = Field(
        default=None, ge=0, max_digits=18, decimal_places=6
    )
    emissions_unit: Optional[str] = Field(default=None, max_length=100)
    consumption_unit: Optional[str] = Field(default=None, max_length=50)
    consumption_source_type: Optional[SourceTypeEnum] = None
    emissions_description: Optional[str] = None
    source_reference: Optional[str] = None

    @field_validator(
        "name",
        "composition",
        "emissions_unit",
        "emissions_description",
        "source_reference",
        "consumption_unit",
    )
    @classmethod
    def updated_text_not_blank(cls, value: Optional[str], info) -> Optional[str]:
        if value is None:
            return None
        if not value.strip():
            raise ValueError(f"{info.field_name} must not be empty")
        return value.strip()

    @field_validator("barcode")
    @classmethod
    def normalize_barcode(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return value.strip() or None

    @model_validator(mode="after")
    def validate_patch(self):
        if not self.model_fields_set:
            raise ValueError("at least one product field must be provided")

        nullable_fields = {"barcode", "consumption_unit", "consumption_source_type"}
        for field_name in self.model_fields_set - nullable_fields:
            if getattr(self, field_name) is None:
                raise ValueError(f"{field_name} may not be null")
        return self


class ProductResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    organization_id: int
    name: str
    barcode: Optional[str]
    composition: str
    emissions_value: Decimal
    emissions_unit: str
    consumption_unit: Optional[str]
    consumption_source_type: Optional[SourceTypeEnum]
    emissions_description: str
    source_reference: str
    created_at: datetime
    updated_at: datetime
