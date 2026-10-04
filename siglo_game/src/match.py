"""Lógica de una mesa multijugador de Siglo.

Esta clase no sabe nada de sockets ni de pygame: solo aplica las reglas
(reutilizando Deck, Player y Rules del juego original) y guarda el estado.
El servidor (src/server.py) la usa como árbitro, y por eso se puede probar
sin abrir puertos.
"""
import time
from typing import Callable, List, Optional

from src.deck import Deck
from src.player import Player
from src.rules import Rules
from src.protocol import (
    PHASE_LOBBY, PHASE_PLAYING, PHASE_ROUND_END,
    MIN_PLAYERS, MAX_PLAYERS, MAX_NAME_LEN, TURN_TIMEOUT,
)


class MatchError(Exception):
    """Acción no permitida. El mensaje está pensado para mostrarse al jugador."""


class Seat:
    """Un asiento de la mesa: el Player de las reglas + datos de la sesión."""

    def __init__(self, seat_id: int, player: Player):
        self.id = seat_id
        self.player = player
        self.connected = True
        self.wins = 0


class Match:
    def __init__(
        self,
        max_players: int = MAX_PLAYERS,
        turn_seconds: float = TURN_TIMEOUT,
        deck_factory: Callable[[], Deck] = Deck,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.max_players = max_players
        self.turn_seconds = turn_seconds
        self._deck_factory = deck_factory
        self._clock = clock

        self.seats: List[Seat] = []
        self.deck: Optional[Deck] = None
        self.phase = PHASE_LOBBY
        self.host_id: Optional[int] = None
        self.turn_idx = 0
        self.round_number = 0
        self.winner_ids: List[int] = []

        # Cada vez que empieza una "ventana de decisión" (un turno nuevo, o una
        # bola más del mismo jugador) sube turn_seq y se fija un nuevo plazo.
        # Así el servidor puede ignorar temporizadores que ya no corresponden.
        self.turn_seq = 0
        self.deadline: Optional[float] = None
        self._next_id = 1

    # ------------------------------------------------------------------
    # Consultas
    # ------------------------------------------------------------------
    def now(self) -> float:
        return self._clock()

    def current_seat(self) -> Optional[Seat]:
        if self.phase != PHASE_PLAYING:
            return None
        return self.seats[self.turn_idx]

    def _find(self, seat_id: int) -> Optional[Seat]:
        for seat in self.seats:
            if seat.id == seat_id:
                return seat
        return None

    # ------------------------------------------------------------------
    # Entrar y salir
    # ------------------------------------------------------------------
    def join(self, raw_name) -> int:
        """Sienta a un jugador nuevo y devuelve su id."""
        if self.phase == PHASE_PLAYING:
            raise MatchError("Hay una ronda en curso. Entra cuando termine.")
        if len(self.seats) >= self.max_players:
            self._purge_disconnected()  # los desconectados de la ronda anterior liberan sitio
            if len(self.seats) >= self.max_players:
                raise MatchError("La mesa está llena.")

        seat = Seat(self._next_id, Player(self._unique_name(raw_name)))
        self._next_id += 1
        self.seats.append(seat)
        self._ensure_host()
        return seat.id

    def leave(self, seat_id: int) -> None:
        """Un jugador se va (o se le cae la conexión)."""
        seat = self._find(seat_id)
        if seat is None:
            return

        if self.phase == PHASE_LOBBY:
            self.seats.remove(seat)
        else:
            # Durante o justo después de una ronda su asiento se conserva
            # (marcado como desconectado) para que el resultado siga siendo
            # coherente. Se plantea con lo que tenga.
            was_current = self.current_seat() is seat
            seat.connected = False
            if seat.player.status == "PLAYING":
                seat.player.status = "ME_QUEDO"
            if was_current:
                self._advance()

        if any(s.connected for s in self.seats):
            self._ensure_host()
        else:
            self._reset()

    def _unique_name(self, raw_name) -> str:
        cleaned = "".join(ch for ch in str(raw_name or "") if ch.isprintable())
        name = " ".join(cleaned.split())[:MAX_NAME_LEN].strip() or "Jugador"

        taken = {s.player.name.lower() for s in self.seats}
        base, n = name, 2
        while name.lower() in taken:
            suffix = f" {n}"
            name = base[:MAX_NAME_LEN - len(suffix)] + suffix
            n += 1
        return name

    def _ensure_host(self) -> None:
        """El anfitrión siempre es un jugador conectado (el más antiguo)."""
        for seat in self.seats:
            if seat.id == self.host_id and seat.connected:
                return
        connected = [s for s in self.seats if s.connected]
        self.host_id = connected[0].id if connected else None

    def _purge_disconnected(self) -> None:
        self.seats = [s for s in self.seats if s.connected]

    def _reset(self) -> None:
        """Mesa vacía: vuelve al estado inicial."""
        self.seats = []
        self.deck = None
        self.phase = PHASE_LOBBY
        self.host_id = None
        self.turn_idx = 0
        self.round_number = 0
        self.winner_ids = []
        self.deadline = None
        self.turn_seq += 1

    # ------------------------------------------------------------------
    # Jugadas
    # ------------------------------------------------------------------
    def start_round(self, seat_id: int) -> None:
        """Reparte la vira a todos y empieza una ronda nueva (solo el anfitrión)."""
        if seat_id != self.host_id:
            raise MatchError("Solo el anfitrión puede iniciar la ronda.")
        if self.phase == PHASE_PLAYING:
            raise MatchError("La ronda ya está en curso.")

        self._purge_disconnected()
        if len(self.seats) < MIN_PLAYERS:
            self.phase = PHASE_LOBBY
            self.deadline = None
            self.turn_seq += 1
            raise MatchError(f"Se necesitan al menos {MIN_PLAYERS} jugadores.")

        self.deck = self._deck_factory()
        for seat in self.seats:
            seat.player.reset_round()
            seat.player.add_ball(self.deck.draw())  # la vira
            seat.player.status = "PLAYING"

        self.round_number += 1
        self.winner_ids = []
        self.phase = PHASE_PLAYING
        # La salida rota entre rondas para que no siempre empiece el mismo.
        self.turn_idx = (self.round_number - 1) % len(self.seats)
        self._open_decision_window()

    def draw(self, seat_id: int) -> None:
        """REPARTIR: el repartidor (anfitrión) le da una ficha a quien tenga el turno."""
        if self.phase != PHASE_PLAYING:
            raise MatchError("No hay una ronda en curso.")
        if seat_id != self.host_id:
            raise MatchError("Solo el repartidor puede repartir fichas.")
        seat = self.seats[self.turn_idx]
        ball = self.deck.draw()
        if ball is None:  # imposible con 90 fichas y 6 jugadores, pero por si acaso
            seat.player.status = "ME_QUEDO"
            self._advance()
            return

        seat.player.add_ball(ball)
        Rules.evaluate_player_status(seat.player)
        if seat.player.status != "PLAYING":  # SIGLO o ME_FUI: termina su turno
            self._advance()
        else:                                # sigue jugando: nuevo plazo
            self._open_decision_window()

    def stay(self, seat_id: int) -> None:
        """ME QUEDO: el jugador se planta."""
        seat = self._require_turn(seat_id)
        seat.player.status = "ME_QUEDO"
        self._advance()

    def timeout(self, seq: int) -> bool:
        """Se acabó el plazo: el jugador en turno se planta.

        Devuelve True si hubo cambios. Se ignora si seq ya no corresponde
        (el jugador alcanzó a jugar antes de que venciera el plazo).
        """
        if self.phase != PHASE_PLAYING or seq != self.turn_seq:
            return False
        self.current_seat().player.status = "ME_QUEDO"
        self._advance()
        return True

    def _require_turn(self, seat_id: int) -> Seat:
        if self.phase != PHASE_PLAYING:
            raise MatchError("No hay una ronda en curso.")
        seat = self.seats[self.turn_idx]
        if seat.id != seat_id:
            raise MatchError("No es tu turno.")
        return seat

    def _advance(self) -> None:
        """Pasa al siguiente jugador que siga en juego; si no hay, cierra la ronda."""
        n = len(self.seats)
        for step in range(1, n + 1):
            idx = (self.turn_idx + step) % n
            if self.seats[idx].player.status == "PLAYING":
                self.turn_idx = idx
                self._open_decision_window()
                return
        self._end_round()

    def _open_decision_window(self) -> None:
        self.turn_seq += 1
        self.deadline = self._clock() + self.turn_seconds

    def _end_round(self) -> None:
        winners = Rules.determine_round_winners([s.player for s in self.seats])
        self.winner_ids = [s.id for s in self.seats if s.player in winners]
        for seat in self.seats:
            if seat.id in self.winner_ids:
                seat.wins += 1
        self.phase = PHASE_ROUND_END
        self.deadline = None
        self.turn_seq += 1

    # ------------------------------------------------------------------
    # Foto del estado (lo que ven los clientes)
    # ------------------------------------------------------------------
    def snapshot(self, viewer_id: Optional[int] = None) -> dict:
        current = self.current_seat()
        time_left = None
        if self.deadline is not None:
            time_left = round(max(0.0, self.deadline - self._clock()), 1)

        def _player_view(s: Seat) -> dict:
            status = s.player.status
            hide = (
                viewer_id is not None
                and s.id != viewer_id
                and self.phase == PHASE_PLAYING
                and status in ("PLAYING", "ME_QUEDO", "SIGLO")
            )
            if hide:
                shown_status = "ME_QUEDO" if status == "SIGLO" else status
                return {
                    "id": s.id,
                    "name": s.player.name,
                    "score": None,
                    "status": shown_status,
                    "balls": [],
                    "hidden": True,
                    "wins": s.wins,
                    "connected": s.connected,
                }
            return {
                "id": s.id,
                "name": s.player.name,
                "score": s.player.score,
                "status": status,
                "balls": [b.value for b in s.player.hand],
                "hidden": False,
                "wins": s.wins,
                "connected": s.connected,
            }

        return {
            "type": "state",
            "phase": self.phase,
            "round": self.round_number,
            "host_id": self.host_id,
            "turn_id": current.id if current else None,
            "time_left": time_left,
            "winner_ids": list(self.winner_ids),
            "max_players": self.max_players,
            "players": [_player_view(s) for s in self.seats],
        }
