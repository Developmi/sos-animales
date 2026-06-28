"""Modelo SQLAlchemy CommunityUpdate.

- campaign_id / animal_id: FK opcional a la entidad reportada.
- pin_hash: str — hash bcrypt del PIN de 4 dígitos (nunca texto plano).
- update_type: str — 'confirmed' | 'full' | 'cancelled' | 'wrong_info'.
- votes: int — contador de votos de la comunidad.
- created_at: timestamp.

El PIN lo genera el sistema al crear la campaña/perfil y se envía al
correo del source vía Google SMTP. El umbral de votación es configurable
desde .env (COMMUNITY_VOTE_THRESHOLD, default 5).
"""
