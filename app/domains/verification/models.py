"""Modelos SQLAlchemy del dominio verification (separado de sources).

- VerificationRequest: solicitud de verificación para una source.
  Estados: pending, scheduled (visita agendada), done, rejected.
- ChecklistResult: resultado de la visita veterinaria (criterios evaluados).
- Visit: registro de la visita — presencial (radio ≤ 2h Bogotá) o remota
  (aliado local o reunión virtual, mismo checklist).

Dominio separado para reutilización en post-MVP (ej: verificación de campañas).
"""
