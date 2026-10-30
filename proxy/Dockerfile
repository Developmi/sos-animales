# syntax=docker/dockerfile:1.7
# Production Caddy WAF Reverse Proxy for SOS Animales
# Based on hardened Developmi Caddy WAF distribution
FROM ghcr.io/developmi/caddy-waf:v3.6.2@sha256:572968506168150bed96e293c9461578d911a980ecb8ef91d6672f381dda2cbb

LABEL org.opencontainers.image.title="sos-animales-proxy" \
      org.opencontainers.image.description="Hardened perimeter Caddy WAF reverse proxy for SOS Animales" \
      org.opencontainers.image.version="1.0.2" \
      org.opencontainers.image.source="https://github.com/Developmi/sos-animales" \
      org.opencontainers.image.licenses="AGPL" \
      org.opencontainers.image.authors="Miguel Lozano <miguel@developmi.com>"

# Copy custom Caddyfile configured for SOS Animales
COPY --chown=1337:1337 Caddyfile /etc/caddy/Caddyfile

USER 1337:1337

EXPOSE 80 443 443/udp

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD ["curl", "-fs", "http://127.0.0.1:2019/metrics"]

CMD ["caddy", "run", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"]
