"""Membership lifecycle helpers shared by organization and member routes."""

import secrets

from sqlalchemy.orm import Session

from app.models.organization import Organization

# Crockford-style alphabet: ambiguous I/L/O/U characters are omitted so a
# code copied from chat or read aloud remains straightforward to enter.
JOIN_CODE_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
JOIN_CODE_GROUPS = 6
JOIN_CODE_GROUP_LENGTH = 4


def _random_join_code() -> str:
    groups = [
        "".join(secrets.choice(JOIN_CODE_ALPHABET) for _ in range(JOIN_CODE_GROUP_LENGTH))
        for _ in range(JOIN_CODE_GROUPS)
    ]
    return "ORG-" + "-".join(groups)


def generate_unique_join_code(db: Session) -> str:
    """Generate a 120-bit code, retrying the astronomically unlikely collision."""
    while True:
        candidate = _random_join_code()
        exists = db.query(Organization.id).filter(Organization.join_code == candidate).first()
        if exists is None:
            return candidate


def normalize_join_code(value: str) -> str:
    """Codes are case-insensitive; internal punctuation remains significant."""
    return value.strip().upper()

