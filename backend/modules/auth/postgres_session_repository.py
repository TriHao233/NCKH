"""Demo session revocation without persisting raw bearer tokens."""

from __future__ import annotations

import hashlib

from core.demo_auth import is_demo_session_token
from core.postgres import postgres_connection


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class PostgresFirebaseSessionRepository:
    def upsert(self, uid: str, token: str | None) -> dict:
        # Firebase ID tokens are verified on every request by Firebase Admin.
        # Only demo sessions need an application-side revocation record.
        if token and not is_demo_session_token(token):
            return self.find_by_uid(uid) or {"firebase_uid": uid, "demo_token_hash": None, "revoked_at": None}
        digest = token_hash(token) if token and is_demo_session_token(token) else None
        with postgres_connection() as conn:
            row = conn.execute(
                """INSERT INTO user_sessions (firebase_uid, demo_token_hash, revoked_at)
                   VALUES (%s, %s, CASE WHEN %s::text IS NULL THEN now() ELSE NULL END)
                   ON CONFLICT (firebase_uid) DO UPDATE
                   SET demo_token_hash = EXCLUDED.demo_token_hash,
                       revoked_at = EXCLUDED.revoked_at,
                       updated_at = now()
                   RETURNING firebase_uid, demo_token_hash, revoked_at""",
                (uid, digest, digest),
            ).fetchone()
        return dict(row)

    def find_by_uid(self, uid: str) -> dict | None:
        with postgres_connection() as conn:
            row = conn.execute(
                "SELECT firebase_uid, demo_token_hash, revoked_at FROM user_sessions WHERE firebase_uid = %s",
                (uid,),
            ).fetchone()
        return dict(row) if row else None
