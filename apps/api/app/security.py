from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import Membership, Role
from app.schemas import Actor

password_hash = PasswordHash.recommended()
bearer = HTTPBearer()


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, encoded: str) -> bool:
    return password_hash.verify(password, encoded)


def create_token(user_id: str, organization_id: str, role: Role) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": user_id,
        "org": organization_id,
        "role": role.value,
        "iat": now,
        "exp": now + timedelta(hours=8),
    }
    return jwt.encode(payload, get_settings().app_secret, algorithm="HS256")


def current_actor(
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
    db: Session = Depends(get_db),
) -> Actor:
    try:
        payload = jwt.decode(
            credentials.credentials, get_settings().app_secret, algorithms=["HS256"]
        )
        actor = Actor(
            user_id=payload["sub"],
            organization_id=payload["org"],
            role=Role(payload["role"]),
        )
    except (jwt.PyJWTError, KeyError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        ) from exc

    membership = db.scalar(
        select(Membership).where(
            Membership.user_id == actor.user_id,
            Membership.organization_id == actor.organization_id,
            Membership.role == actor.role,
        )
    )
    if membership is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Membership revoked")
    return actor


def require_roles(*roles: Role):
    def dependency(actor: Actor = Depends(current_actor)) -> Actor:
        if actor.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return actor

    return dependency
