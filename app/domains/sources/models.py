"""Modelo SQLAlchemy del dominio sources.

- Source: fundación o refugio con estado pending/verified.
  Almacena nombre, tipo (official/verified_shelter/community),
  municipio (select controlado), departamento, contacto, URL,
  y evidencia de verificación.

El estado verified se alcanza tras el proceso de verificación de dos niveles
(presencial o remoto con veterinario). Mientras está pending, los usuarios
ven una advertencia de "no verificado".
"""
