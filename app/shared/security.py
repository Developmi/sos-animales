"""Utilidades de seguridad compartidas.

- generate_pin: genera PIN numérico de 4 dígitos seguros (secrets.randbelow).
- hash_pin: hashea PIN con passlib[bcrypt] (nunca se guarda texto plano).
- verify_pin: verifica PIN contra hash almacenado.
- rate_limit_check: helper para verificar límites por IP (usado en
  endpoints de community para evitar spam).

Reutilizable desde cualquier dominio.
"""
