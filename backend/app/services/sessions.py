"""Access-token revocation.

Access tokens are stateless JWTs, so signing out has to record the token's
identifier (``jti``) until its own expiry. Rows are small, indexed by primary
key, and pruned opportunistically whenever a token is revoked.
"""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.user import RevokedToken
from app.security.tokens import TokenError, decode_token
from app.utils.dates import utc_now


def is_revoked(db: Session, jti: str) -> bool:
    return db.execute(select(RevokedToken.jti).where(RevokedToken.jti == jti)).first() is not None


def revoke_token(db: Session, token: str) -> bool:
    """Revoke a single access token. Returns True when a row was written."""
    try:
        claims = decode_token(token)
    except TokenError:
        return False

    if is_revoked(db, claims.jti):
        return False

    db.add(
        RevokedToken(
            jti=claims.jti,
            user_id=claims.user_id,
            expires_at=claims.expires_at,
        )
    )
    # Keep the table from growing without bound: expired tokens are rejected by
    # signature checks anyway, so their rows carry no information.
    db.execute(delete(RevokedToken).where(RevokedToken.expires_at < utc_now()))
    db.commit()
    return True
