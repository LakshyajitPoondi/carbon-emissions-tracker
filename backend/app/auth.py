"""Password hashing, JWT issuance/verification, and the current-user dependency.

Every router except app.routers.auth depends on get_current_user (wired at the
APIRouter level via `dependencies=[Depends(get_current_user)]`) so a missing or
invalid bearer token returns 401 before the endpoint body ever runs.
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "insecure-dev-secret-change-me")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "60"))

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token", auto_error=False)

CREDENTIALS_EXCEPTION = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail={"code": "UNAUTHORIZED", "message": "Could not validate credentials"},
    headers={"WWW-Authenticate": "Bearer"},
)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(subject: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE_MINUTES)
    payload = {"sub": subject, "exp": expire}
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def _decode_subject(token: str) -> Optional[str]:
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except JWTError:
        return None
    return payload.get("sub")


def get_user_from_token(token: str, db: Session) -> Optional[User]:
    """Like get_current_user, but callable directly with an explicit token
    string rather than via the OAuth2PasswordBearer/Authorization-header
    dependency flow. Used by the WebSocket endpoint, whose token arrives as
    a query param — a browser WebSocket handshake can't carry custom headers
    the way an HTTP request can."""
    email = _decode_subject(token)
    if email is None:
        return None
    return db.query(User).filter(User.email == email).first()


def get_current_user(
    request: Request,
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    if token is None:
        raise CREDENTIALS_EXCEPTION
    user = get_user_from_token(token, db)
    if user is None:
        raise CREDENTIALS_EXCEPTION

    # Hand the resolved identity to the audit middleware, which runs
    # outside the dependency system and so can't depend on this itself.
    # Stashing it here means the middleware records a user only when this
    # dependency actually validated the token — it never re-decodes one.
    request.state.audit_user_id = user.id
    return user
