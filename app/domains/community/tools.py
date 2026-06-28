"""Funciones puras de negocio del dominio community.

- generate_pin: genera PIN de 4 dígitos, lo asocia a campaña/perfil,
  retorna el PIN en texto plano para enviar por correo (nunca se guarda así).
- verify_pin: verifica PIN contra hash almacenado (passlib bcrypt).
- register_update: crea un reporte comunitario.
- count_votes: cuenta votos actuales de un update.
- resolve_conflict: decide si comunidad sobreescribe estado oficial
  (si votos >= COMMUNITY_VOTE_THRESHOLD).
"""
