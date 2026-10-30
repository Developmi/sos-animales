# SOS Animales — Perimeter Caddy WAF Proxy

Hardened perimeter reverse proxy for SOS Animales based on the official [Developmi Caddy WAF distribution (`ghcr.io/developmi/caddy-waf`)](https://github.com/Developmi/caddy-waf).

## Features

- **OWASP Coraza WAF & CRS v4:** Pre-configured in `DetectionOnly` mode for zero-impact deployment and threat profiling.
- **Multipart Photo Uploads:** Supports animal rescue and profile photo uploads up to 10 MB without body truncation or false positives.
- **Content Security Policy (CSP):** Strictly configured for SOS Animales frontend components:
  - HTMX (`cdn.jsdelivr.net`)
  - Leaflet maps and OpenStreetMap tiles (`*.tile.openstreetmap.org`, `unpkg.com`)
  - Google Fonts / Self-hosted assets
- **Defensive Perimeter:** Automatically drops attempts to read `.env`, `.git`, `.aws`, database dumps, and configuration files.
- **Adaptive Rate Limiting:** Enforces perimeter burst control per IP (120 req/min).

---

## Quick Start with Docker Compose

Add the proxy service to your `docker-compose.yml` or run alongside:

```yaml
services:
  proxy:
    build:
      context: ./proxy
    image: sos-animales-proxy:local
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    environment:
      - UPSTREAM_HOST=web:8000
    depends_on:
      web:
        condition: service_healthy
    networks:
      - sos_internal

networks:
  sos_internal:
    driver: bridge
```

---

## Environment Variables

| Variable | Default | Description |
| :--- | :--- | :--- |
| `UPSTREAM_HOST` | `web:8000` | Target FastAPI application host and port within the internal network. |

---

## Tailscale & Private VPS Integration

When deploying behind Tailscale on a private VPS:
1. Ensure `ports: - "127.0.0.1:80:80"` (or your Tailscale interface IP) is bound to prevent unwanted public access.
2. Caddy automatically passes the client IP through `X-Forwarded-For`, which FastAPI uses for its daily-salted HMAC privacy hashing and voting rate limiting.
