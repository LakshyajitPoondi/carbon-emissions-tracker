"""Security response headers, chiefly HSTS.

Why HSTS is sent unconditionally
--------------------------------
RFC 6797 says a user agent MUST ignore a Strict-Transport-Security header
received over a non-secure transport, so sending it on plain HTTP is inert
rather than harmful. That matters because the alternative — only sending it
when the request looks secure — gets it wrong in exactly the deployment
that needs it most: behind a TLS-terminating platform (Render, Vercel,
an ingress controller), the client speaks HTTPS but this app sees plain
HTTP from the proxy. Conditioning on ``request.url.scheme`` would suppress
the header precisely there. So it is always sent, and the browser decides
whether to honour it.

The header is what tells a browser "never speak plain HTTP to this origin
again" — which is the part a hosting platform's own TLS does *not* do on
the app's behalf unless explicitly configured to.

Why there is no Content-Security-Policy here
--------------------------------------------
A strict CSP (``default-src 'none'``) is the obvious next hardening step
for a JSON API, but this app also serves Swagger UI at /docs and GraphiQL
at /graphql, both of which pull scripts and styles from a CDN. A blanket
CSP would silently break both of the interactive consoles this project is
demonstrated with. Adding one would mean scoping it per-route, which is
more machinery than a college-project API warrants — noted here so the
omission reads as a decision rather than an oversight.
"""

import os

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

# One year, the conventional value and the minimum any preload list accepts.
DEFAULT_HSTS_MAX_AGE = 31_536_000

STATIC_SECURITY_HEADERS = {
    # Stop browsers from MIME-sniffing a response into something executable.
    "X-Content-Type-Options": "nosniff",
    # No page here is ever meant to be framed.
    "X-Frame-Options": "DENY",
    # API URLs can carry record ids; don't leak them to third parties.
    "Referrer-Policy": "no-referrer",
}


def _env_flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def build_hsts_header() -> str | None:
    """The Strict-Transport-Security value, or None when disabled.

    Read from the environment at call time rather than at import, so the
    setting is testable and can be flipped without a rebuild.
    """
    if not _env_flag("HSTS_ENABLED", True):
        return None

    try:
        max_age = int(os.getenv("HSTS_MAX_AGE", str(DEFAULT_HSTS_MAX_AGE)))
    except ValueError:
        max_age = DEFAULT_HSTS_MAX_AGE
    if max_age <= 0:
        return None

    directives = [f"max-age={max_age}"]
    if _env_flag("HSTS_INCLUDE_SUBDOMAINS", True):
        directives.append("includeSubDomains")
    # Off by default on purpose: submitting an origin to the browser preload
    # list is effectively irreversible on a useful timescale, which is not a
    # commitment to make silently from a default.
    if _env_flag("HSTS_PRELOAD", False):
        directives.append("preload")
    return "; ".join(directives)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Adds HSTS and companion hardening headers to every response.

    Uses setdefault so a route that deliberately sets one of these keeps its
    own value, and applies to error responses too — a 401 is exactly the
    kind of response an attacker sees most of.
    """

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        hsts = build_hsts_header()
        if hsts is not None:
            response.headers.setdefault("Strict-Transport-Security", hsts)

        for name, value in STATIC_SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)

        return response
