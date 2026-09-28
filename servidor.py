"""Servidor multijugador de Siglo.

Uso:
    python servidor.py                  # TCP :5555 + web (navegador) :8080
    python servidor.py --puerto 6000 --web-puerto 9000
    python servidor.py --tiempo-turno 45
    python servidor.py --sin-web         # solo el cliente de escritorio
    python servidor.py --sin-tcp         # solo el navegador (nada de cliente.py)

Un jugador con cliente.py (TCP) y otro desde el navegador (WebSocket)
pueden sentarse en la misma mesa: los dos hablan con el mismo Match.

No necesita pygame: puede correr en una máquina sin pantalla.
"""
import argparse
import asyncio
import logging
import os
import socket
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "siglo_game"))

from src.match import Match          # noqa: E402
from src.protocol import DEFAULT_PORT, TURN_TIMEOUT  # noqa: E402
from src.server import SigloServer   # noqa: E402

# Los hostings (Render, Railway, Fly, Heroku...) indican el puerto en la variable PORT.
DEFAULT_WEB_PORT = int(os.environ.get("PORT", 8080))


def local_ip():
    """IP de esta máquina en la red local (para decirle a los demás a dónde conectarse)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))  # UDP: no envía nada, solo elige la interfaz
            return s.getsockname()[0]
    except OSError:
        return None


async def run(args):
    server = SigloServer(args.host, args.puerto, Match(turn_seconds=args.tiempo_turno))
    runner = None

    if not args.sin_tcp:
        try:
            await server.start()
        except OSError as err:
            print(f"No se pudo abrir el puerto TCP {args.puerto}: {err}")
            print("¿Ya hay otro servidor corriendo? Prueba con --puerto 5556")
            sys.exit(1)

    if not args.sin_web:
        from src.webapp import run_web  # import perezoso: no exige aiohttp con --sin-web
        try:
            runner = await run_web(server, args.host, args.web_puerto)
        except OSError as err:
            print(f"No se pudo abrir el puerto web {args.web_puerto}: {err}")
            print("¿Ya hay otro servidor corriendo? Prueba con --web-puerto 8081")
            sys.exit(1)

    ip = local_ip() or "127.0.0.1"
    print("=" * 56)
    print("          SERVIDOR DE SIGLO")
    print("=" * 56)
    print(f"Tiempo por decisión: {args.tiempo_turno:g} s")
    if not args.sin_tcp:
        print(f"Escritorio (cliente.py):  {ip}:{args.puerto}   (este equipo: 127.0.0.1:{args.puerto})")
    if not args.sin_web:
        print(f"Navegador:                http://{ip}:{args.web_puerto}   (este equipo: http://127.0.0.1:{args.web_puerto})")
    print("Ctrl+C para detener.\n")

    try:
        if args.sin_tcp:
            # Sin TCP no hay nada que "serve_forever": solo esperamos a que
            # nos maten (Ctrl+C) mientras el runner web sigue vivo.
            await asyncio.Event().wait()
        else:
            await server.serve_forever()
    finally:
        if runner is not None:
            await runner.cleanup()


def main():
    parser = argparse.ArgumentParser(description="Servidor multijugador de Siglo")
    parser.add_argument("--host", default="0.0.0.0", help="interfaz donde escuchar (por defecto todas)")
    parser.add_argument("--puerto", type=int, default=DEFAULT_PORT, help="puerto TCP para cliente.py")
    parser.add_argument("--web-puerto", type=int, default=DEFAULT_WEB_PORT, help="puerto HTTP/WebSocket para el navegador")
    parser.add_argument("--tiempo-turno", type=float, default=TURN_TIMEOUT,
                        help="segundos para decidir antes de plantarse solo (por defecto %(default)s)")
    parser.add_argument("--sin-web", action="store_true", help="no levantar el servidor web (solo cliente.py)")
    parser.add_argument("--sin-tcp", action="store_true", help="no levantar el TCP crudo (solo navegador)")
    args = parser.parse_args()

    if args.sin_web and args.sin_tcp:
        print("--sin-web y --sin-tcp juntos apagan todo. Usa como mucho uno de los dos.")
        sys.exit(1)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")

    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        print("\nServidor detenido.")


if __name__ == "__main__":
    main()
