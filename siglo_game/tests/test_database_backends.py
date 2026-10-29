"""El mismo contrato para SQLite y PostgreSQL (Postgres se omite si no hay servidor)."""
import os

import pytest

from src.database import AccountDatabase, AccountError

PG_DSN = os.environ.get("SIGLO_TEST_DATABASE_URL", "postgresql://postgres:postgres@localhost/siglo_test")


def _postgres():
    pytest.importorskip("psycopg2")
    from src.database_postgres import PostgresAccountDatabase
    try:
        db = PostgresAccountDatabase(PG_DSN)
    except Exception as err:
        pytest.skip(f"sin PostgreSQL de pruebas: {err}")
    with db._connect() as cur:
        cur.execute("TRUNCATE acct_games, acct_sessions, acct_users RESTART IDENTITY CASCADE")
    return db


@pytest.fixture(params=["sqlite", "postgres"])
def db(request):
    database = AccountDatabase(":memory:") if request.param == "sqlite" else _postgres()
    yield database
    database.close()


def test_register_login_and_duplicates(db):
    acc = db.register("Ana", "secreto123")
    with pytest.raises(AccountError):
        db.register("ana", "otraclave1")
    assert db.authenticate("ANA", "secreto123")["id"] == acc["id"]
    with pytest.raises(AccountError):
        db.authenticate("Ana", "incorrecta")
    with pytest.raises(AccountError):
        db.authenticate("Nadie", "secreto123")
    with pytest.raises(AccountError):
        db.register("Bo", "secreto123")
    with pytest.raises(AccountError):
        db.register("Carlos", "corta")


def test_sessions(db):
    acc = db.register("Ana", "secreto123")
    token = db.create_session(acc["id"])
    assert db.get_session_account(token)["username"] == "Ana"
    db.delete_session(token)
    assert db.get_session_account(token) is None


def test_rounds_stats_and_history(db):
    a = db.register("Ana", "secreto123")["id"]
    b = db.register("Luis", "secreto123")["id"]
    people = [
        {"id": 1, "name": "Ana", "score": 88, "status": "ME_QUEDO", "user_id": a},
        {"id": 2, "name": "Luis", "score": 40, "status": "ME_QUEDO", "user_id": b},
        {"id": 3, "name": "Invitado", "score": 20, "status": "ME_QUEDO", "user_id": None},
    ]
    db.record_round("m1", 1, people, [1])
    db.record_round("m1", 1, people, [1])      # repetido: no se duplica
    db.record_round("m1", 2, people, [2])
    assert db.get_stats(a) == {"games_played": 2, "games_won": 1}
    assert db.get_stats(b) == {"games_played": 2, "games_won": 1}
    hist = db.get_history(a)
    assert hist["stats"] == {"played": 2, "wins": 1, "losses": 1}
    assert len(hist["games"]) == 2 and "Invitado" in hist["games"][0]["opponents"]


def test_passwords_not_stored_in_clear(db):
    db.register("Ana", "secreto123")
    if hasattr(db, "_pool"):
        with db._connect() as cur:
            cur.execute("SELECT * FROM acct_users")
            assert "secreto123" not in str(cur.fetchall())
