"""Password hashing, JWT issuance/verification, and the current-user dependency.

Every router except app.routers.auth depends on get_current_user (wired at the
APIRouter level via `dependencies=[Depends(get_current_user)]`) so a missing or
invalid bearer token returns 401 before the endpoint body ever runs.
"""

import logging
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

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# JWT secret configuration
#
# This value signs every token, so anyone who knows it can mint a valid token
# for any user. It used to fall back to a hardcoded string when the
# environment variable was missing, which meant a deployment that simply
# forgot to set JWT_SECRET_KEY came up looking healthy while accepting
# forged tokens signed with a secret published in this repository.
#
# There is now no silent fallback. A missing, known, or weak secret stops the
# process at import time, which is the loudest and earliest failure available:
# uvicorn exits rather than serving traffic with a worthless signature.
# ---------------------------------------------------------------------------

# The historical fallback. Kept only so it can be recognised and rejected.
INSECURE_DEFAULT_SECRET = "insecure-dev-secret-change-me"

# Placeholders shipped in .env.example and k8s/secret.example.yaml. They are
# rejected by name as well as by length, so a config copied verbatim from a
# template fails immediately instead of quietly becoming a production secret.
KNOWN_PLACEHOLDER_SECRETS = frozenset(
    {
        INSECURE_DEFAULT_SECRET,
        "change_me_to_a_long_random_secret",
        "replace-with-a-long-random-secret",
        "REPLACE_ME_WITH_A_GENERATED_SECRET",
    }
)

# 32 characters is the floor for an HS256 signing key: the algorithm's
# security rests on the key having at least as much entropy as the 256-bit
# digest it produces. Anything shorter is brute-forceable regardless of how
# unguessable it looks.
MIN_JWT_SECRET_LENGTH = 32

DEV_ESCAPE_HATCH_ENV = "ALLOW_INSECURE_DEV_SECRET"


class InsecureJWTSecretError(RuntimeError):
    """Raised at import time when JWT_SECRET_KEY is missing, known, or weak.

    Deliberately fatal: an application that cannot sign tokens safely should
    not start at all.
    """


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def validate_jwt_secret(secret: Optional[str], *, allow_insecure: bool = False) -> str:
    """Return *secret* if it is fit to sign tokens with, else raise.

    `allow_insecure` is the opt-in developer escape hatch. It is off unless
    ALLOW_INSECURE_DEV_SECRET is explicitly set, so the unsafe path can only
    ever be reached on purpose — never by omission, which is the failure mode
    this whole function exists to prevent.
    """
    if allow_insecure:
        logger.warning(
            "%s is set: using an insecure development JWT secret. Tokens signed "
            "with it are forgeable by anyone with this source code. Never set "
            "this outside local development.",
            DEV_ESCAPE_HATCH_ENV,
        )
        return secret or INSECURE_DEFAULT_SECRET

    if not secret:
        raise InsecureJWTSecretError(
            "JWT_SECRET_KEY is not set. Generate one with:\n"
            '  python -c "import secrets; print(secrets.token_urlsafe(32))"\n'
            f"and set it in your environment, or set {DEV_ESCAPE_HATCH_ENV}=true "
            "to run with a known-insecure development secret."
        )

    if secret in KNOWN_PLACEHOLDER_SECRETS:
        raise InsecureJWTSecretError(
            "JWT_SECRET_KEY is still the placeholder value shipped in this "
            "repository, which is public knowledge and would let anyone forge "
            "tokens. Generate a real one with:\n"
            '  python -c "import secrets; print(secrets.token_urlsafe(32))"'
        )

    if len(secret) < MIN_JWT_SECRET_LENGTH:
        raise InsecureJWTSecretError(
            f"JWT_SECRET_KEY is {len(secret)} characters; at least "
            f"{MIN_JWT_SECRET_LENGTH} are required to sign HS256 tokens safely. "
            "Generate one with:\n"
            '  python -c "import secrets; print(secrets.token_urlsafe(32))"'
        )

    return secret


def load_jwt_secret() -> str:
    """Read and validate the secret from the environment. Called at import."""
    return validate_jwt_secret(
        os.getenv("JWT_SECRET_KEY"),
        allow_insecure=_env_flag(DEV_ESCAPE_HATCH_ENV),
    )


JWT_SECRET_KEY = load_jwt_secret()
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


def get_current_user_for_graphql(
    request: Request,
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> Optional[User]:
    """Like get_current_user, but lets an unauthenticated GET through.

    GraphiQL is served by a plain GET /graphql, and a browser navigating to
    a URL cannot attach an Authorization header — so gating GET on a bearer
    token makes the console unreachable: you need the page to supply the
    token, and the token to load the page. Exempting GET breaks that
    deadlock, and GET can then serve exactly one thing, the static GraphiQL
    HTML shell.

    That exemption is only safe because the router is built with
    allow_queries_via_get=False (see app/graphql/schema.py). Strawberry
    otherwise executes queries from GET query strings, which would turn
    this into unauthenticated read access to the entire schema. The two
    settings have to move together; neither is correct alone.

    Every actual query is a POST, and POST is authenticated exactly as
    before.
    """
    if request.method.upper() == "GET":
        return None
    return get_current_user(request=request, token=token, db=db)
