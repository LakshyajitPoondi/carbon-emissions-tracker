"""The JWT signing secret must be real, or the app must refuse to run.

The hole this closes: app/auth.py used to fall back to a hardcoded string
when JWT_SECRET_KEY was missing. A deployment that forgot to set it came up
looking perfectly healthy while accepting tokens forged with a secret
published in this repository.

Two layers are tested here — the validation function itself, and the fact
that importing the module actually applies it. The second matters: a
validator nothing calls is worth nothing, so the subprocess tests prove the
process genuinely dies rather than trusting that the call site exists.
"""

import os
import subprocess
import sys

import pytest

from app.auth import (
    DEV_ESCAPE_HATCH_ENV,
    INSECURE_DEFAULT_SECRET,
    KNOWN_PLACEHOLDER_SECRETS,
    MIN_JWT_SECRET_LENGTH,
    InsecureJWTSecretError,
    load_jwt_secret,
    validate_jwt_secret,
)

STRONG_SECRET = "Qk3n8vZp2rTxW9sLdF7hJmB4cY6aE1gU0iO5yN2tRvX"


class TestValidation:
    def test_accepts_a_strong_secret(self):
        assert validate_jwt_secret(STRONG_SECRET) == STRONG_SECRET
        assert len(STRONG_SECRET) >= MIN_JWT_SECRET_LENGTH

    def test_rejects_a_missing_secret(self):
        with pytest.raises(InsecureJWTSecretError) as exc:
            validate_jwt_secret(None)
        # The message has to tell you how to fix it, or it just becomes a
        # thing people work around by setting the escape hatch.
        assert "token_urlsafe" in str(exc.value)

    def test_rejects_an_empty_secret(self):
        with pytest.raises(InsecureJWTSecretError):
            validate_jwt_secret("")

    def test_rejects_the_historical_default(self):
        with pytest.raises(InsecureJWTSecretError):
            validate_jwt_secret(INSECURE_DEFAULT_SECRET)

    @pytest.mark.parametrize("placeholder", sorted(KNOWN_PLACEHOLDER_SECRETS))
    def test_rejects_every_shipped_placeholder(self, placeholder):
        """Including ones long enough to pass the length check — a template
        value copied verbatim must never become a live signing key."""
        with pytest.raises(InsecureJWTSecretError):
            validate_jwt_secret(placeholder)

    def test_rejects_a_short_secret_even_when_unguessable(self):
        short = "x7Qm2Lp9Rt4Vz"
        assert len(short) < MIN_JWT_SECRET_LENGTH
        with pytest.raises(InsecureJWTSecretError) as exc:
            validate_jwt_secret(short)
        assert str(len(short)) in str(exc.value)

    def test_accepts_a_secret_of_exactly_the_minimum_length(self):
        boundary = "a" * MIN_JWT_SECRET_LENGTH
        assert validate_jwt_secret(boundary) == boundary


class TestDevEscapeHatch:
    def test_allows_a_missing_secret_when_explicitly_opted_in(self):
        assert validate_jwt_secret(None, allow_insecure=True) == INSECURE_DEFAULT_SECRET

    def test_is_off_unless_asked_for(self):
        """The whole point: the unsafe path is reachable only on purpose,
        never by omission."""
        with pytest.raises(InsecureJWTSecretError):
            validate_jwt_secret(None, allow_insecure=False)


class TestEnvironmentLoading:
    def test_reads_the_secret_from_the_environment(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET_KEY", STRONG_SECRET)
        monkeypatch.delenv(DEV_ESCAPE_HATCH_ENV, raising=False)
        assert load_jwt_secret() == STRONG_SECRET

    def test_raises_when_the_environment_has_no_secret(self, monkeypatch):
        monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
        monkeypatch.delenv(DEV_ESCAPE_HATCH_ENV, raising=False)
        with pytest.raises(InsecureJWTSecretError):
            load_jwt_secret()

    def test_escape_hatch_flag_is_read_from_the_environment(self, monkeypatch):
        monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
        monkeypatch.setenv(DEV_ESCAPE_HATCH_ENV, "true")
        assert load_jwt_secret() == INSECURE_DEFAULT_SECRET


def _import_auth_with(env_overrides: dict[str, str | None]) -> subprocess.CompletedProcess:
    """Import app.auth in a fresh process with a doctored environment.

    A subprocess rather than importlib.reload: reloading would leave the
    already-imported routers holding references to the old module, so it
    would prove nothing about what happens at real startup. This is exactly
    what uvicorn does when it boots.
    """
    env = os.environ.copy()
    for key, value in env_overrides.items():
        if value is None:
            env.pop(key, None)
        else:
            env[key] = value
    return subprocess.run(
        [sys.executable, "-c", "import app.auth"],
        env=env,
        capture_output=True,
        text=True,
        cwd="/app",
        timeout=60,
    )


class TestStartupActuallyFails:
    """Import-time enforcement — the part that makes this a security control
    rather than a helper function nobody calls."""

    def test_process_dies_with_no_secret_and_no_flag(self):
        result = _import_auth_with({"JWT_SECRET_KEY": None, DEV_ESCAPE_HATCH_ENV: None})
        assert result.returncode != 0
        assert "InsecureJWTSecretError" in result.stderr

    def test_process_dies_with_the_default_secret(self):
        result = _import_auth_with(
            {"JWT_SECRET_KEY": INSECURE_DEFAULT_SECRET, DEV_ESCAPE_HATCH_ENV: None}
        )
        assert result.returncode != 0
        assert "InsecureJWTSecretError" in result.stderr

    def test_process_dies_with_a_short_secret(self):
        result = _import_auth_with({"JWT_SECRET_KEY": "tooshort", DEV_ESCAPE_HATCH_ENV: None})
        assert result.returncode != 0
        assert "InsecureJWTSecretError" in result.stderr

    def test_process_starts_with_a_strong_secret(self):
        result = _import_auth_with({"JWT_SECRET_KEY": STRONG_SECRET, DEV_ESCAPE_HATCH_ENV: None})
        assert result.returncode == 0, result.stderr

    def test_process_starts_with_the_dev_flag_and_no_secret(self):
        result = _import_auth_with({"JWT_SECRET_KEY": None, DEV_ESCAPE_HATCH_ENV: "true"})
        assert result.returncode == 0, result.stderr
