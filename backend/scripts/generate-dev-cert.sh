#!/usr/bin/env sh
#
# Generate a self-signed TLS certificate for LOCAL DEVELOPMENT ONLY.
#
# Run this once before starting the HTTPS backend:
#
#   sh backend/scripts/generate-dev-cert.sh
#
# Works in three places, deliberately: Git Bash / WSL / macOS on the host,
# and inside the backend container (`docker compose exec backend sh
# /app/scripts/generate-dev-cert.sh`). Because docker-compose bind-mounts
# ./backend to /app, a certificate generated inside the container lands in
# backend/certs/ on the host either way.
#
# The output is gitignored. Never commit a private key, not even a
# throwaway development one — committed keys get copied into real
# deployments far more often than anyone expects.
#
# This certificate is signed by nobody, so browsers will warn on first
# visit. That is expected; see the TLS section of docs/api-contract.md.
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
CERT_DIR="${CERT_DIR:-$SCRIPT_DIR/../certs}"
CERT_FILE="$CERT_DIR/dev-cert.pem"
KEY_FILE="$CERT_DIR/dev-key.pem"
DAYS="${CERT_DAYS:-365}"

FORCE=0
if [ "${1:-}" = "--force" ]; then
    FORCE=1
fi

if ! command -v openssl >/dev/null 2>&1; then
    echo "ERROR: openssl not found on PATH." >&2
    echo "Either install it, or generate the certificate inside the container:" >&2
    echo "  docker compose exec backend sh /app/scripts/generate-dev-cert.sh" >&2
    exit 1
fi

mkdir -p "$CERT_DIR"

if [ -f "$CERT_FILE" ] && [ "$FORCE" -eq 0 ]; then
    echo "Certificate already exists: $CERT_FILE"
    echo "Nothing to do. Re-run with --force to replace it."
    exit 0
fi

# Everything is driven from a generated OpenSSL config rather than -subj
# and -addext flags. That is not stylistic: under Git Bash on Windows, the
# MSYS runtime rewrites any argument that looks like a POSIX path, so
# -subj "/CN=localhost/..." silently becomes a C:\ path and corrupts the
# subject. Disabling that conversion (MSYS_NO_PATHCONV) fixes -subj but then
# breaks -keyout/-out, which genuinely do need converting. A config file
# needs no flag that looks like a path, so both problems disappear and the
# same script works unchanged on Linux inside the container.
CONFIG_FILE=$(mktemp)
trap 'rm -f "$CONFIG_FILE"' EXIT INT TERM

# subjectAltName is not optional: browsers have ignored the legacy CN field
# for hostname matching for years, so a cert without SANs is rejected
# outright regardless of its CN. "backend" and "backend-https" are the
# compose service names, so the cert also validates for container-to-
# container calls, not just from the host.
cat > "$CONFIG_FILE" <<'OPENSSL_CONFIG'
[req]
default_bits       = 2048
default_md         = sha256
prompt             = no
distinguished_name = dn
x509_extensions    = v3_req

[dn]
CN = localhost
O  = Carbon Emissions Tracking Platform (dev)

[v3_req]
basicConstraints = critical, CA:FALSE
keyUsage         = digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth
subjectAltName   = @alt_names

[alt_names]
DNS.1 = localhost
DNS.2 = backend
DNS.3 = backend-https
IP.1  = 127.0.0.1
IP.2  = ::1
OPENSSL_CONFIG

openssl req -x509 -nodes -newkey rsa:2048 \
    -days "$DAYS" \
    -config "$CONFIG_FILE" \
    -keyout "$KEY_FILE" \
    -out "$CERT_FILE"

# Best effort: no-op on filesystems that don't carry POSIX modes, which
# includes the Windows host directory this often runs against.
chmod 600 "$KEY_FILE" 2>/dev/null || true

echo "Generated a self-signed development certificate, valid $DAYS days:"
echo "  certificate: $CERT_FILE"
echo "  private key: $KEY_FILE"
echo
echo "Start the HTTPS backend with:"
echo "  docker compose --profile tls up -d backend-https"
echo "then open https://localhost:8443/health and accept the browser warning."
