import jwt
from fastapi import Request, HTTPException

from app.config import settings


async def require_auth(request: Request) -> None:
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="No autenticado")
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Sesión expirada")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token inválido")
    if payload.get("sub") != "admin":
        raise HTTPException(status_code=401, detail="Token inválido")


async def get_current_admin(request: Request) -> bool:
    token = request.cookies.get("access_token")
    if not token:
        return False
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
        return payload.get("sub") == "admin"
    except jwt.InvalidTokenError:
        return False
