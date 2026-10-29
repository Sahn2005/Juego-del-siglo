"""Cuentas e historial en PostgreSQL (misma interfaz que AccountDatabase de SQLite).

Se usa cuando existe la variable DATABASE_URL (Render, Railway, Fly...). En un
hosting con disco efímero, SQLite se pierde al reiniciar; PostgreSQL no.
Las tablas se crean solas (CREATE TABLE IF NOT EXISTS).
"""
import hashlib
import hmac
import json
import secrets
import time
from contextlib import contextmanager
from typing import Dict, Iterator, List, Optional

import psycopg2
import psycopg2.errors
import psycopg2.extras
from psycopg2.pool import ThreadedConnectionPool

from src.database import (
    AccountError, PASSWORD_ITERATIONS, SESSION_SECONDS, USERNAME_PATTERN,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS acct_users (
    id            SERIAL PRIMARY KEY,
    username      TEXT NOT NULL,
    password_hash BYTEA NOT NULL,
    password_salt BYTEA NOT NULL,
    created_at    BIGINT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS acct_users_username_ci ON acct_users (lower(username));
CREATE TABLE IF NOT EXISTS acct_sessions (
    token_hash TEXT PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES acct_users(id) ON DELETE CASCADE,
    expires_at BIGINT NOT NULL
);
CREATE TABLE IF NOT EXISTS acct_games (
    id            SERIAL PRIMARY KEY,
    user_id       INTEGER NOT NULL REFERENCES acct_users(id) ON DELETE CASCADE,
    match_id      TEXT NOT NULL,
    round_number  INTEGER NOT NULL,
    score         INTEGER NOT NULL,
    player_status TEXT NOT NULL,
    result        TEXT NOT NULL,
    opponents     TEXT NOT NULL,
    played_at     BIGINT NOT NULL,
    UNIQUE (user_id, match_id, round_number)
);
CREATE INDEX IF NOT EXISTS acct_games_user_played ON acct_games (user_id, played_at DESC);
"""


class PostgresAccountDatabase:
    def __init__(self, dsn: str):
        self._pool = ThreadedConnectionPool(1, 5, dsn)
        with self._connect() as cur:
            cur.execute(_SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator["psycopg2.extensions.cursor"]:
        conn = self._pool.getconn()
        try:
            with conn:  # confirma al salir, o revierte si hubo error
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    yield cur
        finally:
            self._pool.putconn(conn)

    @staticmethod
    def _account(row) -> Dict[str, object]:
        return {"id": row["id"], "username": row["username"]}

    @staticmethod
    def _password_hash(password: str, salt: bytes) -> bytes:
        return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS)

    def register(self, username: str, password: str) -> Dict[str, object]:
        username = username.strip()
        if not USERNAME_PATTERN.fullmatch(username):
            raise AccountError("El usuario debe tener de 3 a 10 letras, números o guiones bajos.")
        if len(password) < 8 or len(password) > 128:
            raise AccountError("La contraseña debe tener entre 8 y 128 caracteres.")
        salt = secrets.token_bytes(16)
        try:
            with self._connect() as cur:
                cur.execute(
                    "INSERT INTO acct_users (username, password_hash, password_salt, created_at) "
                    "VALUES (%s, %s, %s, %s) RETURNING id, username",
                    (username, self._password_hash(password, salt), salt, int(time.time())),
                )
                row = cur.fetchone()
        except psycopg2.errors.UniqueViolation:
            raise AccountError("Ese nombre de usuario ya está registrado.") from None
        return self._account(row)

    def authenticate(self, username: str, password: str) -> Dict[str, object]:
        if len(password) > 128:
            raise AccountError("Usuario o contraseña incorrectos.")
        with self._connect() as cur:
            cur.execute(
                "SELECT id, username, password_hash, password_salt FROM acct_users "
                "WHERE lower(username) = lower(%s)", (username.strip(),))
            row = cur.fetchone()
        if row is None or not hmac.compare_digest(
            self._password_hash(password, bytes(row["password_salt"])), bytes(row["password_hash"])
        ):
            raise AccountError("Usuario o contraseña incorrectos.")
        return self._account(row)

    def create_session(self, user_id: int) -> str:
        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        now = int(time.time())
        with self._connect() as cur:
            cur.execute("DELETE FROM acct_sessions WHERE expires_at <= %s", (now,))
            cur.execute(
                "INSERT INTO acct_sessions (token_hash, user_id, expires_at) VALUES (%s, %s, %s)",
                (token_hash, user_id, now + SESSION_SECONDS))
        return token

    def get_session_account(self, token: Optional[str]) -> Optional[Dict[str, object]]:
        if not token:
            return None
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        with self._connect() as cur:
            cur.execute(
                "SELECT u.id, u.username FROM acct_sessions s JOIN acct_users u ON u.id = s.user_id "
                "WHERE s.token_hash = %s AND s.expires_at > %s", (token_hash, int(time.time())))
            row = cur.fetchone()
        return self._account(row) if row else None

    def delete_session(self, token: Optional[str]) -> None:
        if not token:
            return
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        with self._connect() as cur:
            cur.execute("DELETE FROM acct_sessions WHERE token_hash = %s", (token_hash,))

    def record_round(self, match_id: str, round_number: int,
                     participants: List[Dict[str, object]], winner_ids: List[int]) -> None:
        played_at = int(time.time())
        with self._connect() as cur:
            for person in participants:
                if person.get("user_id") is None:
                    continue
                opponents = [o["name"] for o in participants if o["id"] != person["id"]]
                cur.execute(
                    "INSERT INTO acct_games (user_id, match_id, round_number, score, player_status, "
                    "result, opponents, played_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) "
                    "ON CONFLICT (user_id, match_id, round_number) DO NOTHING",
                    (person["user_id"], match_id, round_number, person["score"], person["status"],
                     "Victoria" if person["id"] in winner_ids else "Derrota",
                     json.dumps(opponents, ensure_ascii=False), played_at))

    def get_stats(self, user_id: int) -> Dict[str, int]:
        with self._connect() as cur:
            cur.execute(
                "SELECT COUNT(*) AS played, COALESCE(SUM(CASE WHEN result = 'Victoria' THEN 1 ELSE 0 END), 0) AS wins "
                "FROM acct_games WHERE user_id = %s", (user_id,))
            row = cur.fetchone()
        return {"games_played": int(row["played"]), "games_won": int(row["wins"])}

    def get_history(self, user_id: int) -> Dict[str, object]:
        with self._connect() as cur:
            cur.execute("SELECT id, username FROM acct_users WHERE id = %s", (user_id,))
            account = cur.fetchone()
            cur.execute(
                "SELECT round_number, score, player_status, result, opponents, played_at "
                "FROM acct_games WHERE user_id = %s ORDER BY played_at DESC, id DESC LIMIT 100",
                (user_id,))
            rows = cur.fetchall()
        stats = self.get_stats(user_id)
        return {
            "account": self._account(account),
            "stats": {"played": stats["games_played"], "wins": stats["games_won"],
                      "losses": stats["games_played"] - stats["games_won"]},
            "games": [{"round": r["round_number"], "score": r["score"], "status": r["player_status"],
                       "result": r["result"], "opponents": json.loads(r["opponents"]),
                       "played_at": r["played_at"]} for r in rows],
        }

    def close(self) -> None:
        self._pool.closeall()
