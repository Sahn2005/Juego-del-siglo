"""Protocolo de red de Siglo (compartido por el cliente y el servidor).

Cada mensaje es un objeto JSON en una sola línea terminada en "\\n" (igual que
el prototipo original), enviado por TCP.

Cliente -> servidor
    {"type": "join", "name": "Ana"}   primer mensaje obligatorio
    {"type": "start"}                 solo el anfitrión (sala de espera / fin de ronda)
    {"type": "draw"}                  BOLA (solo en tu turno)
    {"type": "stay"}                  ME QUEDO (solo en tu turno)

Servidor -> cliente
    {"type": "welcome", "id": 3}      tu identificador de asiento
    {"type": "state", ...}            foto completa de la mesa (ver Match.snapshot)
    {"type": "error", "message": ""}  una acción no fue válida
"""
import json
from typing import Tuple

DEFAULT_PORT = 5555

# Fases de la mesa
PHASE_LOBBY = "LOBBY"          # sala de espera
PHASE_PLAYING = "PLAYING"      # ronda en curso
PHASE_ROUND_END = "ROUND_END"  # ronda terminada, se ve el resultado

MIN_PLAYERS = 2
MAX_PLAYERS = 6
MAX_NAME_LEN = 10
TURN_TIMEOUT = 30.0  # segundos para decidir (BOLA / ME QUEDO) antes de plantarse solo


def encode(message: dict) -> bytes:
    """Convierte un mensaje en una línea JSON lista para enviar."""
    return (json.dumps(message, separators=(",", ":")) + "\n").encode("utf-8")


def decode(line: bytes) -> dict:
    """Convierte una línea recibida en un mensaje.

    Lanza ValueError si no es JSON válido o no tiene el formato esperado.
    """
    message = json.loads(line.decode("utf-8"))
    if not isinstance(message, dict) or "type" not in message:
        raise ValueError("mensaje inválido")
    return message


def parse_address(text: str) -> Tuple[str, int]:
    """Interpreta 'host', 'host:puerto' o vacío (= esta misma máquina).

    Lanza ValueError con un mensaje apto para mostrar al usuario.
    """
    text = (text or "").strip()
    if not text:
        return "127.0.0.1", DEFAULT_PORT

    host, sep, port_text = text.rpartition(":")
    if not sep:  # solo se escribió el host
        return text, DEFAULT_PORT
    if not host:
        raise ValueError("Escribe la IP antes de los dos puntos.")
    try:
        port = int(port_text)
    except ValueError:
        raise ValueError("El puerto debe ser un número.") from None
    if not 1 <= port <= 65535:
        raise ValueError("El puerto debe estar entre 1 y 65535.")
    return host, port
