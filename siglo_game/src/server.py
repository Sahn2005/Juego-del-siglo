"""Servidor de red de Siglo.

Usa asyncio: todo el estado vive en un solo hilo, así que no hacen falta
locks y dos mensajes nunca se mezclan en el mismo socket. El servidor es
autoritativo: los clientes solo piden acciones ("draw", "stay", "start") y
el servidor las valida con Match antes de aplicarlas.

Soporta dos transportes al mismo tiempo, sobre la misma mesa (Match):
  - TCP crudo, línea por línea (para cliente.py, el cliente de escritorio).
  - WebSocket (para el cliente web, ver webapp.py). Cada mensaje es un
    frame de texto con un JSON, sin el "\n" que usa el TCP.
Un jugador desde el navegador y otro desde cliente.py pueden sentarse en
la misma mesa sin problema: a la lógica (Match) no le importa por dónde
entró cada quien.

No depende de pygame, así que puede correr en una máquina sin pantalla.
"""
import asyncio
import json
import logging
from typing import Dict, Optional, Protocol

from src.match import Match, MatchError
from src.protocol import DEFAULT_PORT, PHASE_PLAYING, decode, encode

log = logging.getLogger("siglo.server")

JOIN_TIMEOUT = 10.0     # segundos que se espera el primer mensaje "join"
MAX_LINE_BYTES = 4096   # una línea/mensaje más largo se considera basura


class Connection(Protocol):
    """Lo mínimo que el servidor necesita de una conexión, sin importar
    si por debajo hay un socket TCP o un WebSocket."""

    def send(self, message: dict) -> None: ...
    def close(self) -> None: ...
    async def wait_idle(self) -> None: ...


class _TcpConnection:
    """Envuelve un StreamWriter de asyncio."""

    def __init__(self, writer: asyncio.StreamWriter):
        self._writer = writer

    def send(self, message: dict) -> None:
        if not self._writer.is_closing():
            self._writer.write(encode(message))

    def close(self) -> None:
        self._writer.close()

    async def wait_idle(self) -> None:
        return  # writer.write() ya deja el mensaje en el buffer del SO


class _WsConnection:
    """Envuelve un WebSocketResponse de aiohttp.

    aiohttp exige 'await' para enviar, pero el resto del servidor llama a
    send() de forma síncrona (igual que writer.write()). La solución es una
    cola: send() solo encola, y una tarea de fondo hace los await en orden,
    así nunca se mezclan dos envíos a la vez por la misma conexión.
    """

    def __init__(self, ws):
        self._ws = ws
        self._queue: "asyncio.Queue[Optional[dict]]" = asyncio.Queue()
        self._task = asyncio.ensure_future(self._pump())

    async def _pump(self) -> None:
        while True:
            message = await self._queue.get()
            try:
                if message is None:
                    return
                try:
                    await self._ws.send_str(json.dumps(message, separators=(",", ":")))
                except (ConnectionError, RuntimeError):
                    return
            finally:
                self._queue.task_done()

    def send(self, message: dict) -> None:
        self._queue.put_nowait(message)

    def close(self) -> None:
        self._queue.put_nowait(None)

    async def wait_idle(self) -> None:
        # Espera a que la cola de envíos pendientes (p. ej. un "error" justo
        # antes de cortar la conexión) realmente salga por el socket, para
        # no cerrar el WebSocket antes de que el mensaje alcance a viajar.
        await self._queue.join()


class SigloServer:
    def __init__(self, host: str = "0.0.0.0", port: int = DEFAULT_PORT,
                 match: Optional[Match] = None):
        self.host = host
        self.port = port
        self.match = match if match is not None else Match()
        self._connections: Dict[int, Connection] = {}  # id de asiento -> conexión
        self._timer: Optional[asyncio.TimerHandle] = None
        self._server: Optional[asyncio.AbstractServer] = None

    # ------------------------------------------------------------------
    # Ciclo de vida (transporte TCP)
    # ------------------------------------------------------------------
    async def start(self) -> None:
        self._server = await asyncio.start_server(
            self._handle_tcp_client, self.host, self.port, limit=MAX_LINE_BYTES
        )
        # Con port=0 el sistema elige uno libre (lo usan las pruebas).
        self.port = self._server.sockets[0].getsockname()[1]
        log.info("TCP escuchando en %s:%s", self.host, self.port)

    async def serve_forever(self) -> None:
        if self._server is None:
            await self.start()
        async with self._server:
            await self._server.serve_forever()

    async def stop(self) -> None:
        if self._timer:
            self._timer.cancel()
            self._timer = None
        for conn in list(self._connections.values()):
            conn.close()
        if self._server:
            self._server.close()
            await self._server.wait_closed()

    # ------------------------------------------------------------------
    # Una conexión TCP
    # ------------------------------------------------------------------
    async def _handle_tcp_client(self, reader: asyncio.StreamReader,
                                 writer: asyncio.StreamWriter) -> None:
        conn = _TcpConnection(writer)
        seat_id = None
        try:
            first = await asyncio.wait_for(self._read_tcp(reader), JOIN_TIMEOUT)
            seat_id = self._join(conn, first)
            while True:
                message = await self._read_tcp(reader)
                if message is None:  # el cliente cerró la conexión
                    break
                self._on_message(seat_id, message)
        except (ConnectionError, asyncio.TimeoutError, ValueError):
            # Conexión caída, no mandó "join" a tiempo, o mandó basura
            # (JSON inválido, línea demasiado larga...): se le desconecta.
            pass
        finally:
            await self._finish(conn, seat_id)

    async def _read_tcp(self, reader: asyncio.StreamReader) -> Optional[dict]:
        line = await reader.readline()
        if not line:
            return None
        return decode(line)

    # ------------------------------------------------------------------
    # Una conexión WebSocket (aiohttp la abre y nos pasa el `ws`)
    # ------------------------------------------------------------------
    async def handle_websocket(self, ws) -> None:
        from aiohttp import WSMsgType  # import perezoso: aiohttp es opcional para el TCP puro

        conn = _WsConnection(ws)
        seat_id = None
        try:
            first = await asyncio.wait_for(self._read_ws(ws, WSMsgType), JOIN_TIMEOUT)
            seat_id = self._join(conn, first)
            while True:
                message = await self._read_ws(ws, WSMsgType)
                if message is None:
                    break
                self._on_message(seat_id, message)
        except (ConnectionError, asyncio.TimeoutError, ValueError):
            pass
        finally:
            await self._finish(conn, seat_id)

    async def _read_ws(self, ws, WSMsgType) -> Optional[dict]:
        msg = await ws.receive()
        if msg.type in (WSMsgType.CLOSE, WSMsgType.CLOSING, WSMsgType.CLOSED, WSMsgType.ERROR):
            return None
        if msg.type != WSMsgType.TEXT:
            raise ValueError("se esperaba texto")
        if len(msg.data) > MAX_LINE_BYTES:
            raise ValueError("mensaje demasiado largo")
        return decode(msg.data.encode("utf-8"))

    # ------------------------------------------------------------------
    # Compartido por los dos transportes
    # ------------------------------------------------------------------
    def _join(self, conn: Connection, first: Optional[dict]) -> int:
        if first is None or first.get("type") != "join":
            raise ValueError("se esperaba 'join'")
        try:
            seat_id = self.match.join(first.get("name"))
        except MatchError as err:
            conn.send({"type": "error", "message": str(err)})
            raise ValueError(str(err))  # el finally de quien llama limpia la conexión

        self._connections[seat_id] = conn
        log.info("Jugador %s (%s) se unió", seat_id, self._player_name(seat_id))
        conn.send({"type": "welcome", "id": seat_id})
        self._changed()
        return seat_id

    async def _finish(self, conn: Connection, seat_id: Optional[int]) -> None:
        """Cierra una conexión de forma prolija: primero saca al jugador de la
        mesa y avisa a los demás, y solo al final corta el transporte, dando
        tiempo a que un último mensaje en camino (p. ej. un error) se envíe."""
        self._disconnect(seat_id)
        await conn.wait_idle()
        conn.close()

    def _disconnect(self, seat_id: Optional[int]) -> None:
        if seat_id is None:
            return
        self._connections.pop(seat_id, None)
        self.match.leave(seat_id)
        log.info("Jugador %s se fue", seat_id)
        self._changed()

    def _player_name(self, seat_id: int) -> str:
        for seat in self.match.seats:
            if seat.id == seat_id:
                return seat.player.name
        return "?"

    def _on_message(self, seat_id: int, message: dict) -> None:
        kind = message.get("type")
        try:
            if kind == "start":
                self.match.start_round(seat_id)
            elif kind == "draw":
                self.match.draw(seat_id)
            elif kind == "stay":
                self.match.stay(seat_id)
            else:
                raise MatchError("Mensaje no reconocido.")
        except MatchError as err:
            self._send_to(seat_id, {"type": "error", "message": str(err)})
        self._changed()

    # ------------------------------------------------------------------
    # Envío y temporizador
    # ------------------------------------------------------------------
    def _changed(self) -> None:
        """Llamar después de cualquier cambio: reprograma el plazo y avisa a todos."""
        self._arm_timer()
        self._broadcast(self.match.snapshot())

    def _arm_timer(self) -> None:
        if self._timer:
            self._timer.cancel()
            self._timer = None
        m = self.match
        if m.phase == PHASE_PLAYING and m.deadline is not None:
            delay = max(0.0, m.deadline - m.now())
            loop = asyncio.get_running_loop()
            self._timer = loop.call_later(delay, self._on_timeout, m.turn_seq)

    def _on_timeout(self, seq: int) -> None:
        self._timer = None
        if self.match.timeout(seq):
            log.info("Plazo agotado: el jugador en turno se planta")
            self._changed()

    def _send_to(self, seat_id: int, message: dict) -> None:
        conn = self._connections.get(seat_id)
        if conn:
            conn.send(message)

    def _broadcast(self, message: dict) -> None:
        for conn in list(self._connections.values()):
            conn.send(message)
