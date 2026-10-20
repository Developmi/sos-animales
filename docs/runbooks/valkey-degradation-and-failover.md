# Runbook: Valkey Degradation and Failover

**Alert ID:** `VALKEY_DEGRADED`  
**Severity:** MEDIUM / HIGH  
**Domain:** SRE / Caching & Rate Limiting  

---

## 1. Description & Symptoms
The Valkey service is unresponsive or experiencing socket connection timeouts (`redis.exceptions.ConnectionError`). FastAPI logs warnings: `Valkey not reachable, caching degraded`.

## 2. Impact Analysis
- Public search continues operating (cache miss falls back to PostgreSQL and Nominatim).
- Geocoding responses may take longer due to cache miss.
- Rate limiting automatically falls back to in-memory TTL dictionary `_vote_fallback` in `app/shared/security.py`.

## 3. Diagnostic Steps
1. Verify Valkey container status:
   ```bash
   docker ps -a --filter "name=sos_animales_valkey"
   ```
2. Test Valkey ping directly:
   ```bash
   docker exec -it sos_animales_valkey valkey-cli ping
   ```
3. Inspect container memory consumption:
   ```bash
   docker stats sos_animales_valkey --no-stream
   ```

## 4. Remediation Actions
1. If the container crashed due to memory exhaustion, restart the container:
   ```bash
   docker compose restart valkey
   ```
2. Test readiness endpoint after restart:
   ```bash
   curl -i http://localhost:8000/health/ready
   ```
3. Check `checks.valkey` returns `"ok"` in the JSON response.
