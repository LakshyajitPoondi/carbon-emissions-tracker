<#
.SYNOPSIS
    Generate a self-signed TLS certificate for LOCAL DEVELOPMENT ONLY.

.DESCRIPTION
    Windows-native counterpart to generate-dev-cert.sh. Run once before
    starting the HTTPS backend:

        powershell -ExecutionPolicy Bypass -File backend\scripts\generate-dev-cert.ps1

    Uses openssl from PATH when it is available (Git for Windows ships one).
    When it is not, it falls back to running the shell script inside the
    backend container, which needs no local openssl at all — because
    docker-compose bind-mounts ./backend to /app, the certificate written
    inside the container appears in backend\certs\ on the host either way.

    The output is gitignored. Never commit a private key, not even a
    throwaway development one.

.PARAMETER Force
    Replace an existing certificate instead of leaving it alone.
#>
param([switch]$Force)

$ErrorActionPreference = "Stop"

$backendDir = Split-Path -Parent $PSScriptRoot
$repoRoot = Split-Path -Parent $backendDir
$certDir = Join-Path $backendDir "certs"
$certFile = Join-Path $certDir "dev-cert.pem"
$keyFile = Join-Path $certDir "dev-key.pem"
$days = 365

if ((Test-Path $certFile) -and (-not $Force)) {
    Write-Host "Certificate already exists: $certFile"
    Write-Host "Nothing to do. Re-run with -Force to replace it."
    exit 0
}

if (-not (Test-Path $certDir)) {
    New-Item -ItemType Directory -Path $certDir | Out-Null
}

$openssl = Get-Command openssl -ErrorAction SilentlyContinue

if ($null -ne $openssl) {
    Write-Host "Using openssl at $($openssl.Source)"

    # Driven from a generated config file rather than -subj/-addext flags,
    # to stay byte-identical with generate-dev-cert.sh — one definition of
    # what the certificate contains, so the two scripts cannot drift.
    #
    # subjectAltName is not optional: browsers ignore the legacy CN field
    # for hostname matching, so a cert without SANs is rejected outright.
    # "backend"/"backend-https" are the compose service names, so the cert
    # also validates container-to-container, not just from the host.
    $configFile = [System.IO.Path]::GetTempFileName()
    $config = @'
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
'@

    try {
        # ASCII, not the default: openssl will not parse a config file that
        # begins with a UTF-8 byte-order mark.
        Set-Content -Path $configFile -Value $config -Encoding ASCII

        & $openssl.Source req -x509 -nodes -newkey rsa:2048 `
            -days $days `
            -config $configFile `
            -keyout $keyFile `
            -out $certFile

        if ($LASTEXITCODE -ne 0) {
            throw "openssl exited with code $LASTEXITCODE"
        }
    }
    finally {
        if (Test-Path $configFile) { Remove-Item $configFile -Force }
    }
}
else {
    Write-Host "openssl not found on PATH; generating inside the backend container instead."

    $docker = Get-Command docker -ErrorAction SilentlyContinue
    if ($null -eq $docker) {
        throw "Neither openssl nor docker is available. Install Git for Windows (which bundles openssl), or start Docker Desktop."
    }

    Push-Location $repoRoot
    try {
        $shArgs = @("compose", "exec", "-T", "backend", "sh", "/app/scripts/generate-dev-cert.sh")
        if ($Force) { $shArgs += "--force" }
        & $docker.Source @shArgs
        if ($LASTEXITCODE -ne 0) {
            throw "Certificate generation inside the container failed with code $LASTEXITCODE. Is the backend container running (docker compose up -d)?"
        }
    }
    finally {
        Pop-Location
    }

    # The shell script already printed the summary (with container-side
    # paths). Repeating it here would just say the same thing twice.
    exit 0
}

Write-Host ""
Write-Host "Generated a self-signed development certificate, valid $days days:"
Write-Host "  certificate: $certFile"
Write-Host "  private key: $keyFile"
Write-Host ""
Write-Host "Start the HTTPS backend with:"
Write-Host "  docker compose --profile tls up -d backend-https"
Write-Host "then open https://localhost:8443/health and accept the browser warning."
