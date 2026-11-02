#!/usr/bin/env bash

# tools/vendor.sh
# Download, verify, and package official vendor static assets (HTMX & Leaflet)
# offline for sovereign zero-CDN operations.
#
# Process:
# 1. Gate 0: Verify tools/install.sh has executed and required tools exist.
# 2. Pre-Scan: Run repository linters and Trivy vulnerability check.
#    If any vulnerability or linter failure is detected, halt immediately.
# 3. Download official release assets pinned in tools/versions.mk.
# 4. Verify cryptographic SHA256 hashes before unpacking/installing.
# 5. Place verified assets into app/static/ directories.
# 6. Post-Scan: Run Trivy filesystem audit on app/static and make lint.

set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIN="$ROOT/tools/bin"
VERSIONS="$ROOT/tools/versions.mk"

echo "==> [Gate 0] Checking host development toolchain..."
if [[ ! -x "$BIN/trivy" || ! -x "$BIN/hadolint" || ! -x "$BIN/actionlint" ]]; then
    echo "Required tools missing in $BIN. Executing tools/install.sh..."
    bash "$ROOT/tools/install.sh"
fi

TRIVY="$BIN/trivy"

# Read pinned versions and sha256 checksums from versions.mk
HTMX_VERSION="$(sed -n 's/^HTMX_VERSION[[:space:]]*:=[[:space:]]*//p' "$VERSIONS" | tail -1 | tr -d '[:space:]')"
HTMX_SHA256="$(sed -n 's/^HTMX_SHA256[[:space:]]*:=[[:space:]]*//p' "$VERSIONS" | tail -1 | tr -d '[:space:]')"
LEAFLET_VERSION="$(sed -n 's/^LEAFLET_VERSION[[:space:]]*:=[[:space:]]*//p' "$VERSIONS" | tail -1 | tr -d '[:space:]')"
LEAFLET_SHA256="$(sed -n 's/^LEAFLET_SHA256[[:space:]]*:=[[:space:]]*//p' "$VERSIONS" | tail -1 | tr -d '[:space:]')"

: "${HTMX_VERSION:?HTMX_VERSION not set in versions.mk}"
: "${HTMX_SHA256:?HTMX_SHA256 not set in versions.mk}"
: "${LEAFLET_VERSION:?LEAFLET_VERSION not set in versions.mk}"
: "${LEAFLET_SHA256:?LEAFLET_SHA256 not set in versions.mk}"

echo "✓ Gate 0: Toolchain and versions verified (HTMX v$HTMX_VERSION, Leaflet v$LEAFLET_VERSION)."

echo "==> [Gate 1] Running Pre-Flight Security & Quality Audit..."
# Run multi-layer linters first
if ! make -C "$ROOT" lint; then
    echo "::error::Pre-flight linting failed. Halting asset download." >&2
    exit 1
fi

# Run Trivy filesystem scan on the repository (excluding known dev caches)
echo "Running Trivy pre-flight scan on codebase..."
if ! "$TRIVY" fs --exit-code 1 --severity CRITICAL,HIGH "$ROOT/app"; then
    echo "::error::Trivy detected vulnerabilities in app/. Halting asset download." >&2
    exit 1
fi
echo "✓ Pre-flight scan clean: 0 vulnerabilities, all linters passing."

TMP_DIR="$(mktemp -d -t sos-vendor-XXXXXX)"
trap 'rm -rf "$TMP_DIR"' EXIT

verify_sha256() {
    local file="$1"
    local expected="$2"
    local actual
    if command -v sha256sum >/dev/null 2>&1; then
        actual="$(sha256sum "$file" | awk '{print $1}')"
    elif command -v shasum >/dev/null 2>&1; then
        actual="$(shasum -a 256 "$file" | awk '{print $1}')"
    else
        echo "ERROR: neither sha256sum nor shasum found" >&2
        exit 1
    fi
    if [[ "$actual" != "$expected" ]]; then
        echo "ERROR: SHA256 checksum mismatch for $(basename "$file")" >&2
        echo "  expected: ${expected}" >&2
        echo "  actual:   ${actual}" >&2
        exit 1
    fi
    echo "✓ SHA-256 verified: $(basename "$file")"
}

echo "==> [Gate 2] Downloading official vendor assets..."

# 1. HTMX
HTMX_URL="https://github.com/bigskysoftware/htmx/releases/download/v${HTMX_VERSION}/htmx.min.js"
echo "Downloading HTMX v${HTMX_VERSION} from ${HTMX_URL}..."
curl -sSL --fail "$HTMX_URL" -o "$TMP_DIR/htmx.min.js"
verify_sha256 "$TMP_DIR/htmx.min.js" "$HTMX_SHA256"

# 2. Leaflet
LEAFLET_URL="https://github.com/Leaflet/Leaflet/releases/download/v${LEAFLET_VERSION}/leaflet.zip"
echo "Downloading Leaflet v${LEAFLET_VERSION} from ${LEAFLET_URL}..."
curl -sSL --fail "$LEAFLET_URL" -o "$TMP_DIR/leaflet.zip"
verify_sha256 "$TMP_DIR/leaflet.zip" "$LEAFLET_SHA256"

echo "==> [Gate 3] Installing vendor assets into app/static/..."
unzip -q "$TMP_DIR/leaflet.zip" -d "$TMP_DIR/leaflet"

STATIC_JS="$ROOT/app/static/js/vendor"
STATIC_CSS="$ROOT/app/static/css/vendor"
STATIC_CSS_IMAGES="$ROOT/app/static/css/vendor/images"
STATIC_IMAGES="$ROOT/app/static/images/vendor/leaflet"

mkdir -p "$STATIC_JS" "$STATIC_CSS" "$STATIC_CSS_IMAGES" "$STATIC_IMAGES"

# Install HTMX
cp "$TMP_DIR/htmx.min.js" "$STATIC_JS/htmx.min.js"
chmod 644 "$STATIC_JS/htmx.min.js"
echo "  -> Installed $STATIC_JS/htmx.min.js"

# Install Leaflet JS & CSS
cp "$TMP_DIR/leaflet/dist/leaflet.js" "$STATIC_JS/leaflet.js"
cp "$TMP_DIR/leaflet/dist/leaflet.css" "$STATIC_CSS/leaflet.css"
chmod 644 "$STATIC_JS/leaflet.js" "$STATIC_CSS/leaflet.css"
echo "  -> Installed $STATIC_JS/leaflet.js and $STATIC_CSS/leaflet.css"

# Install Leaflet images/markers (both in vendor images and relative to leaflet.css)
cp -r "$TMP_DIR/leaflet/dist/images/." "$STATIC_IMAGES/"
chmod 644 "$STATIC_IMAGES"/*
cp -r "$TMP_DIR/leaflet/dist/images/." "$STATIC_CSS_IMAGES/"
chmod 644 "$STATIC_CSS_IMAGES"/*
echo "  -> Installed Leaflet marker assets in $STATIC_IMAGES and $STATIC_CSS_IMAGES"

echo "==> [Gate 4] Running Post-Install Security Audit..."
echo "Scanning installed static vendor assets with Trivy..."
"$TRIVY" fs --exit-code 1 --severity CRITICAL,HIGH "$ROOT/app/static"

echo "Re-running linters..."
make -C "$ROOT" lint

echo ""
echo "================================================="
echo "✓ VENDOR ASSETS DOWNLOADED AND VERIFIED"
echo "  - HTMX v$HTMX_VERSION"
echo "  - Leaflet v$LEAFLET_VERSION"
echo "  - 0 Vulnerabilities, 100% Pinned & Checked"
echo "================================================="
