"""Pruebas de integración: servidor real en localhost + clientes falsos."""
import asyncio
import json

import pytest

from helpers import fixed_deck
from src.match import Match
from src.protocol import (
    PHASE_LOBBY, PHASE_PLAYING, PHASE_ROUND_END,
    decode, encode, parse_address,
)
from src.server import SigloServer


class FakeClient:
    """Habla el protocolo por un socket real, como haría el cliente pygame."""

    def __init__(self, reader, writer):
        self.reader = reader
        self.writer = writer
        self.id = None
        self.state = None

    @classmethod
    async def connect(cls, port, name):
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        client = cls(reader, writer)
        client.send(type="join", name=name)
        return client

    def send(self, **message):
        self.writer.write(encode(message))

    def send_raw(self, data: bytes):
        self.writer.write(data)

    async def recv(self, timeout=2.0):
        line = await asyncio.wait_for(self.reader.readline(), timeout)
        if not line:
            return None
        message = decode(line)
        if message["type"] == "welcome":
            self.id = message["id"]
        elif message["type"] == "state":
            self.state = message
        return message

    async def recv_until(self, predicate, timeout=2.0):
        """Lee mensajes hasta que predicate(mensaje) sea verdadero."""
        while True:
            message = await self.recv(timeout)
            if message is None:
                raise AssertionError("conexión cerrada antes de lo esperado")
            if predicate(message):
                return message

    async def wait_state(self, predicate, timeout=2.0):
        return await self.recv_until(
            lambda m: m["type"] == "state" and predicate(m), timeout
        )

    async def wait_closed(self, timeout=2.0):
        while True:
            line = await asyncio.wait_for(self.reader.readline(), timeout)
            if not line:
                return

    def close(self):
        self.writer.close()


def run(scenario, *deck_values, turn_seconds=30.0):
    """Levanta un servidor en un puerto libre y ejecuta scenario(server)."""
    async def main():
        match = Match(deck_factory=fixed_deck(*deck_values), turn_seconds=turn_seconds)
        server = SigloServer("127.0.0.1", 0, match)
        await server.start()
        try:
            await asyncio.wait_for(scenario(server), timeout=10)
        finally:
            await server.stop()
    asyncio.run(main())


async def join_two(server, names=("Ana", "Luis")):
    a = await FakeClient.connect(server.port, names[0])
    await a.recv_until(lambda m: m["type"] == "welcome")
    b = await FakeClient.connect(server.port, names[1])
    await b.recv_until(lambda m: m["type"] == "welcome")
    await a.wait_state(lambda s: len(s["players"]) == 2)
    await b.wait_state(lambda s: len(s["players"]) == 2)
    return a, b


# ---------------------------------------------------------------- pruebas

def test_join_welcome_and_lobby_state_reaches_everyone():
    async def scenario(server):
        a, b = await join_two(server)
        assert a.id != b.id
        assert a.state["phase"] == PHASE_LOBBY
        assert a.state["host_id"] == a.id
        assert [p["name"] for p in b.state["players"]] == ["Ana", "Luis"]
        a.close(); b.close()
    run(scenario)


def test_accented_names_survive_the_wire():
    async def scenario(server):
        a = await FakeClient.connect(server.port, "Ñandú")
        state = await a.wait_state(lambda s: len(s["players"]) == 1)
        assert state["players"][0]["name"] == "Ñandú"
        a.close()
    run(scenario)


def test_full_round_over_the_network():
    # Viras: Ana 50, Luis 60. Ana saca 49 -> 99 (SIGLO). Luis se planta con 60.
    async def scenario(server):
        a, b = await join_two(server)

        a.send(type="start")
        s = await a.wait_state(lambda s: s["phase"] == PHASE_PLAYING)
        assert s["turn_id"] == a.id
        assert [p["balls"] for p in s["players"]] == [[50], [60]]

        a.send(type="draw")
        s = await b.wait_state(lambda s: s["players"][0]["status"] == "SIGLO")
        assert s["turn_id"] == b.id
        assert s["players"][0]["score"] == 99

        b.send(type="stay")
        s = await a.wait_state(lambda s: s["phase"] == PHASE_ROUND_END)
        assert s["winner_ids"] == [a.id]
        assert s["players"][0]["wins"] == 1
        a.close(); b.close()
    run(scenario, 50, 60, 49)


def test_out_of_turn_action_only_errors_the_offender():
    async def scenario(server):
        a, b = await join_two(server)
        a.send(type="start")
        await b.wait_state(lambda s: s["phase"] == PHASE_PLAYING)

        b.send(type="draw")  # no es su turno
        err = await b.recv_until(lambda m: m["type"] == "error")
        assert "turno" in err["message"]

        # A no recibió ningún error; sigue siendo su turno y puede jugar.
        a.send(type="stay")
        s = await a.wait_state(lambda s: s["turn_id"] == b.id)
        assert s["players"][0]["status"] == "ME_QUEDO"
        a.close(); b.close()
    run(scenario, 10, 20)


def test_only_host_can_start():
    async def scenario(server):
        a, b = await join_two(server)
        b.send(type="start")
        err = await b.recv_until(lambda m: m["type"] == "error")
        assert "anfitrión" in err["message"]
        a.close(); b.close()
    run(scenario)


def test_join_is_refused_during_a_round_with_a_reason():
    async def scenario(server):
        a, b = await join_two(server)
        a.send(type="start")
        await b.wait_state(lambda s: s["phase"] == PHASE_PLAYING)

        late = await FakeClient.connect(server.port, "Tarde")
        err = await late.recv_until(lambda m: m["type"] == "error")
        assert "en curso" in err["message"]
        await late.wait_closed()

        # La mesa no se alteró.
        assert len(server.match.seats) == 2
        a.close(); b.close()
    run(scenario, 10, 20)


def test_turn_timeout_is_enforced_by_the_server():
    async def scenario(server):
        a, b = await join_two(server)
        a.send(type="start")
        await a.wait_state(lambda s: s["phase"] == PHASE_PLAYING)
        # Ana no hace nada: a los 0.3 s el servidor la planta y pasa el turno.
        s = await b.wait_state(lambda s: s["turn_id"] == b.id, timeout=3)
        assert s["players"][0]["status"] == "ME_QUEDO"
        a.close(); b.close()
    run(scenario, 10, 20, turn_seconds=0.3)


def test_playing_in_time_cancels_the_old_timeout():
    async def scenario(server):
        a, b = await join_two(server)
        a.send(type="start")
        await a.wait_state(lambda s: s["phase"] == PHASE_PLAYING)
        await asyncio.sleep(0.2)
        a.send(type="draw")                     # actúa antes del plazo (0.5 s)
        await a.wait_state(lambda s: s["players"][0]["score"] == 15)
        await asyncio.sleep(0.4)                # pasó el plazo original, no el nuevo
        assert server.match.current_seat().id == a.id
        assert server.match.current_seat().player.status == "PLAYING"
        a.close(); b.close()
    run(scenario, 10, 20, 5, turn_seconds=0.5)


def test_disconnect_mid_turn_is_seen_by_the_others():
    async def scenario(server):
        a, b = await join_two(server)
        a.send(type="start")
        await b.wait_state(lambda s: s["phase"] == PHASE_PLAYING)

        a.close()  # Ana se cae en su turno
        s = await b.wait_state(lambda s: s["turn_id"] == b.id)
        ana = s["players"][0]
        assert ana["connected"] is False
        assert ana["status"] == "ME_QUEDO"
        assert s["host_id"] == b.id
        b.close()
    run(scenario, 10, 20)


def test_garbage_disconnects_only_the_offender():
    async def scenario(server):
        a, b = await join_two(server)
        b.send_raw(b"esto no es json\n")
        await b.wait_closed()
        s = await a.wait_state(lambda s: len(s["players"]) == 1)
        assert s["players"][0]["name"] == "Ana"
        a.close()
    run(scenario)


def test_oversized_line_disconnects():
    async def scenario(server):
        a = await FakeClient.connect(server.port, "Ana")
        await a.recv_until(lambda m: m["type"] == "welcome")
        a.send_raw(b"x" * 20000 + b"\n")
        await a.wait_closed()
    run(scenario)


def test_first_message_must_be_join():
    async def scenario(server):
        reader, writer = await asyncio.open_connection("127.0.0.1", server.port)
        writer.write(encode({"type": "draw"}))
        client = FakeClient(reader, writer)
        await client.wait_closed()
        assert server.match.seats == []
    run(scenario)


def test_unknown_message_type_gets_an_error_but_keeps_connection():
    async def scenario(server):
        a, b = await join_two(server)
        a.send(type="hackear")
        err = await a.recv_until(lambda m: m["type"] == "error")
        assert "reconocido" in err["message"]
        a.send(type="start")  # la conexión sigue viva
        await a.wait_state(lambda s: s["phase"] == PHASE_PLAYING)
        a.close(); b.close()
    run(scenario, 10, 20)


# ---------------------------------------------------------------- protocolo

def test_parse_address():
    assert parse_address("") == ("127.0.0.1", 5555)
    assert parse_address("   ") == ("127.0.0.1", 5555)
    assert parse_address("192.168.1.20") == ("192.168.1.20", 5555)
    assert parse_address("192.168.1.20:6000") == ("192.168.1.20", 6000)
    assert parse_address("mi.servidor.com:80") == ("mi.servidor.com", 80)
    for bad in (":5555", "host:abc", "host:0", "host:70000", "host:"):
        with pytest.raises(ValueError):
            parse_address(bad)


def test_decode_rejects_malformed_messages():
    for bad in (b"no json", b"[1, 2]", b'{"sin_tipo": 1}', b"\xff\xfe"):
        with pytest.raises(ValueError):
            decode(bad)
    assert json.loads(encode({"type": "x"})) == {"type": "x"}
