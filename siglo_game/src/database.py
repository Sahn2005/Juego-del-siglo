"""Persistent accounts, sessions, and completed-round history for Siglo."""
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Iterator, List, Optional

USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_]{3,10}$")
PASSWORD_ITERATIONS = 260_000
SESSION_SECONDS = 60 * 60 * 24 * 30


class AccountError(ValueError):
    """An account request has invalid input or credentials."""


class AccountDatabase:
    def __init__(self, path: Optional[str] = None):
        if path is None:
            path = os.environ.get(
                "SIGLO_DATABASE",
                str(Path(__file__).resolve().parents[1] / "data" / "siglo.db"),
            )
        self._uri = path == ":memory:"
        self.path = (
            f"file:siglo-{secrets.token_hex(12)}?mode=memory&cache=shared"
            if self._uri
            else path
        )
        self._keeper = sqlite3.connect(self.path, uri=True) if self._uri else None
        if not self._uri:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=10, uri=self._uri)
        try:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY,
                    username TEXT NOT NULL COLLATE NOCASE UNIQUE,
                    password_hash BLOB NOT NULL,
                    password_salt BLOB NOT NULL,
                    created_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    expires_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS games (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    match_id TEXT NOT NULL,
                    round_number INTEGER NOT NULL,
                    score INTEGER NOT NULL,
                    player_status TEXT NOT NULL,
                    result TEXT NOT NULL,
                    opponents TEXT NOT NULL,
                    played_at INTEGER NOT NULL,
                    UNIQUE(user_id, match_id, round_number)
                );
                CREATE INDEX IF NOT EXISTS games_user_played
                    ON games(user_id, played_at DESC);
                """
            )

    @staticmethod
    def _account(row: sqlite3.Row) -> Dict[str, object]:
        return {"id": row["id"], "username": row["username"]}

    @staticmethod
    def _password_hash(password: str, salt: bytes) -> bytes:
        return hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS
        )

    def register(self, username: str, password: str) -> Dict[str, object]:
        username = username.strip()
        if not USERNAME_PATTERN.fullmatch(username):
            raise AccountError("El usuario debe tener de 3 a 10 letras, números o guiones bajos.")
        if len(password) < 8 or len(password) > 128:
            raise AccountError("La contraseña debe tener entre 8 y 128 caracteres.")

        salt = secrets.token_bytes(16)
        password_hash = self._password_hash(password, salt)
        try:
            with self._connect() as connection:
                cursor = connection.execute(
                    "INSERT INTO users(username, password_hash, password_salt, created_at) "
                    "VALUES (?, ?, ?, ?)",
                    (username, password_hash, salt, int(time.time())),
                )
                row = connection.execute(
                    "SELECT id, username FROM users WHERE id = ?", (cursor.lastrowid,)
                ).fetchone()
        except sqlite3.IntegrityError:
            raise AccountError("Ese nombre de usuario ya está registrado.") from None
        return self._account(row)

    def authenticate(self, username: str, password: str) -> Dict[str, object]:
        if len(password) > 128:
            raise AccountError("Usuario o contraseña incorrectos.")
        with self._connect() as connection:
            row = connection.execute(
                "SELECT id, username, password_hash, password_salt FROM users "
                "WHERE username = ? COLLATE NOCASE",
                (username.strip(),),
            ).fetchone()
        if row is None or not hmac.compare_digest(
            self._password_hash(password, row["password_salt"]), row["password_hash"]
        ):
            raise AccountError("Usuario o contraseña incorrectos.")
        return self._account(row)

    def create_session(self, user_id: int) -> str:
        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        expires_at = int(time.time()) + SESSION_SECONDS
        with self._connect() as connection:
            connection.execute("DELETE FROM sessions WHERE expires_at <= ?", (int(time.time()),))
            connection.execute(
                "INSERT INTO sessions(token_hash, user_id, expires_at) VALUES (?, ?, ?)",
                (token_hash, user_id, expires_at),
            )
        return token

    def get_session_account(self, token: Optional[str]) -> Optional[Dict[str, object]]:
        if not token:
            return None
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT users.id, users.username FROM sessions "
                "JOIN users ON users.id = sessions.user_id "
                "WHERE sessions.token_hash = ? AND sessions.expires_at > ?",
                (token_hash, int(time.time())),
            ).fetchone()
        return self._account(row) if row else None

    def delete_session(self, token: Optional[str]) -> None:
        if not token:
            return
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        with self._connect() as connection:
            connection.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))

    def record_round(
        self,
        match_id: str,
        round_number: int,
        participants: List[Dict[str, object]],
        winner_ids: List[int],
    ) -> None:
        played_at = int(time.time())
        with self._connect() as connection:
            for participant in participants:
                user_id = participant.get("user_id")
                if user_id is None:
                    continue
                opponents = [
                    person["name"] for person in participants
                    if person["id"] != participant["id"]
                ]
                connection.execute(
                    "INSERT OR IGNORE INTO games "
                    "(user_id, match_id, round_number, score, player_status, result, opponents, played_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        user_id,
                        match_id,
                        round_number,
                        participant["score"],
                        participant["status"],
                        "Victoria" if participant["id"] in winner_ids else "Derrota",
                        json.dumps(opponents, ensure_ascii=False),
                        played_at,
                    ),
                )

    def get_history(self, user_id: int) -> Dict[str, object]:
        with self._connect() as connection:
            account = connection.execute(
                "SELECT id, username FROM users WHERE id = ?", (user_id,)
            ).fetchone()
            rows = connection.execute(
                "SELECT round_number, score, player_status, result, opponents, played_at "
                "FROM games WHERE user_id = ? ORDER BY played_at DESC, id DESC LIMIT 100",
                (user_id,),
            ).fetchall()
            totals = connection.execute(
                "SELECT COUNT(*) AS played, "
                "SUM(CASE WHEN result = 'Victoria' THEN 1 ELSE 0 END) AS wins "
                "FROM games WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        return {
            "account": self._account(account),
            "stats": {
                "played": totals["played"],
                "wins": totals["wins"] or 0,
                "losses": totals["played"] - (totals["wins"] or 0),
            },
            "games": [
                {
                    "round": row["round_number"],
                    "score": row["score"],
                    "status": row["player_status"],
                    "result": row["result"],
                    "opponents": json.loads(row["opponents"]),
                    "played_at": row["played_at"],
                }
                for row in rows
            ],
        }
