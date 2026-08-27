"""Pydantic schemas for the Auth resource.

Matches docs/api-contract.md — Auth section.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, field_validator


class UserCreate(BaseModel):
    """POST /auth/register request body."""
    email: EmailStr
    password: str

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("password must be at least 8 characters")
        return v


class UserResponse(BaseModel):
    """POST /auth/register response."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    created_at: datetime


class Token(BaseModel):
    """POST /auth/token response."""
    access_token: str
    token_type: str = "bearer"
