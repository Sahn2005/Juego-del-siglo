"""Conexión del cliente con el servidor.

Un hilo en segundo plano conecta y lee del socket; el bucle de pygame recoge
los mensajes con poll() sin bloquearse. Además de los mensajes del servidor,
el hilo puede dejar dos mensajes propios en la cola:

    {"type": "_failed", "message": "..."}   no se pudo conectar
    {"type": "_closed"}                     se perdió la conexión
"""
import queue
import socket
import threading
from typing import List

from src.protocol import decode, encode

CONNECT_TIMEOUT = 5.0


def _friendly_error(err: OSError, host: str) -> str:
    if isinstance(err, ConnectionRefusedError):
        return "El servidor rechazó la conexión. ¿Está encendido?"
    if isinstance(err, socket.gaierror):
        return f"No se encontró el servidor «{host}»."
    if isinstance(err, (socket.timeout, TimeoutError)):
        return "El servidor no respondió (tiempo agotado)."
    return "No se pudo conectar con el servidor."


class NetworkClient:
    """Una conexión = una instancia. Para reconectar se crea otra."""

    def __init__(self):
        self._sock = None
        self._inbox: "queue.Queue[dict]" = queue.Queue()
        self._send_lock = threading.Lock()
        self._closed = False

    def connect(self, host: str, port: int, name: str) -> None:
        """Empieza a conectar en segundo plano y, al lograrlo, envía 'join'."""
        thread = threading.Thread(
            target=self._run, args=(host, port, name), daemon=True
        )
        thread.start()

    def poll(self) -> List[dict]:
        """Devuelve (sin esperar) los mensajes que hayan llegado."""
        messages = []
        while True:
            try:
                messages.append(self._inbox.get_nowait())
            except queue.Empty:
                return messages

    def send(self, message: dict) -> bool:
        sock = self._sock
        if sock is None or self._closed:
            return False
        try:
            with self._send_lock:
                sock.sendall(encode(message))
            return True
        except OSError:
            return False  # el hilo lector avisará con "_closed"

    def close(self) -> None:
        """Cierra la conexión. Después de esto ya no llegan mensajes."""
        self._closed = True
        sock = self._sock
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            sock.close()

    # ------------------------------------------------------------------
    def _run(self, host: str, port: int, name: str) -> None:
        try:
            sock = socket.create_connection((host, port), timeout=CONNECT_TIMEOUT)
        except OSError as err:
            if not self._closed:
                self._inbox.put({"type": "_failed", "message": _friendly_error(err, host)})
            return

        if self._closed:  # el usuario canceló mientras se conectaba
            sock.close()
            return
        sock.settimeout(None)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self._sock = sock
        self.send({"type": "join", "name": name})

        buffer = b""
        try:
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                buffer += chunk
                # Se separa por bytes y se decodifica línea completa: un
                # carácter con tilde puede llegar partido entre dos recv().
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    if not line.strip():
                        continue
                    try:
                        self._inbox.put(decode(line))
                    except ValueError:
                        continue  # línea corrupta: se ignora
        except OSError:
            pass
        finally:
            sock.close()
            if not self._closed:
                self._inbox.put({"type": "_closed"})
