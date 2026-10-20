# Runbook: Database Connection Pool Exhausted

**Alert ID:** `DB_POOL_EXHAUSTED`  
**Severity:** HIGH  
**Domain:** SRE / Data Layer  

---

## 1. Description & Symptoms
The SQLAlchemy connection pool has reached its hard limit (`pool_size=10, max_overflow=20`), and new HTTP requests fail with `TimeoutError: QueuePool limit of size 10 overflow 20 reached, connection timed out, timeout 10.00`.

## 2. Immediate Diagnostic Steps
1. Connect to PostgreSQL inside the database container:
   ```bash
   docker exec -it sos_animales_db psql -U user -d sos_animales
   ```
2. Inspect active queries and connection count:
   ```sql
   SELECT count(*), state FROM pg_stat_activity GROUP BY state;
   ```
3. Identify long-running transactions:
   ```sql
   SELECT pid, now() - query_start AS duration, query, state
   FROM pg_stat_activity
   WHERE state != 'idle'
   ORDER BY duration DESC
   LIMIT 5;
   ```

## 3. Remediation Actions
1. Terminate hanging backend processes:
   ```sql
   SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE duration > interval '30 seconds' AND state != 'idle';
   ```
2. If connection leak persists, restart the FastAPI web application to reset asyncpg connection pool:
   ```bash
   docker compose restart web
   ```
3. Check `app/database.py` for endpoints leaving sessions unclosed without context manager (`async with get_db() as session`).
