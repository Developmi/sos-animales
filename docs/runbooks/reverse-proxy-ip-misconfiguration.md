# Runbook: Reverse Proxy IP Misconfiguration & Rate Limit Lockout

**Alert ID:** `AUTH_RATELIMIT_SPIKE`  
**Severity:** HIGH  
**Domain:** AppSec / Networking  

---

## 1. Description & Symptoms
Legitimate admin logins or multiple users are getting blocked with HTTP 429 (`Too Many Requests`) simultaneously across distinct client sessions.

## 2. Root Cause
The reverse proxy (Nginx, Caddy, Cloudflare Tunnel, or Traefik) is not properly forwarding the `X-Forwarded-For` header, or `ProxyHeadersMiddleware` in `app/main.py` is not trusting the proxy host. Consequently, all incoming requests appear originating from `127.0.0.1` or the reverse proxy IP.

## 3. Diagnostic Steps
1. Inspect request client IP logged in FastAPI stdout:
   ```bash
   docker compose logs web --tail 50 | grep "check_login_rate_limit"
   ```
2. Verify if the client IP appears repeatedly as `127.0.0.1` for external users.
3. Verify proxy forwarding headers:
   - For Caddy: Ensure `header_up X-Forwarded-For {remote_host}` or default proxy directives are active.
   - For Nginx: Ensure `proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;` is configured in the `location /` block.

## 4. Remediation Actions
1. Ensure the reverse proxy host is listed in `trusted_hosts` in `app/main.py`:
   ```python
   app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=["127.0.0.1", "::1", "100.*"])
   ```
2. Flush the temporary lockout key in Valkey if admin is locked out:
   ```bash
   docker exec -it sos_animales_valkey valkey-cli KEYS "ratelimit:login:*" | xargs -r docker exec -i sos_animales_valkey valkey-cli DEL
   ```
