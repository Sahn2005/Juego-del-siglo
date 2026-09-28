"""Servidor web de Siglo: sirve el cliente (HTML/CSS/JS) y el WebSocket.

Es lo que se sube a un hosting/VPS para que la gente juegue desde el
navegador, sin instalar nada. Usa la misma mesa (Match, vía SigloServer)
que el cliente de escritorio, así que da igual por dónde entre cada quien.
"""
from pathlib import Path

from aiohttp import web

from src.server import SigloServer

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
SERVER_KEY = web.AppKey("server", SigloServer)


@web.middleware
async def no_cache(request: web.Request, handler):
    """Que el navegador revalide siempre los archivos del juego.

    Sin esto, tras actualizar app.js o style.css el navegador puede seguir
    mostrando la versión vieja guardada. Con "no-cache" sigue pudiendo usar
    su copia, pero primero pregunta al servidor si cambió (barato: 304).
    """
    response = await handler(request)
    if request.path != "/ws":
        response.headers["Cache-Control"] = "no-cache"
    return response


def build_app(server: SigloServer) -> web.Application:
    app = web.Application(middlewares=[no_cache])
    app[SERVER_KEY] = server

    async def ws_handler(request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse(heartbeat=25)
        await ws.prepare(request)
        await server.handle_websocket(ws)
        return ws

    async def health(request: web.Request) -> web.Response:
        # Para que el proveedor de hosting (o vos) pueda comprobar que
        # sigue vivo sin tener que abrir un WebSocket.
        m = server.match
        return web.json_response({"ok": True, "jugadores": len(m.seats), "fase": m.phase})

    async def index(request: web.Request) -> web.FileResponse:
        return web.FileResponse(WEB_DIR / "index.html")

    app.router.add_get("/ws", ws_handler)
    app.router.add_get("/health", health)
    app.router.add_get("/", index)
    app.router.add_static("/", WEB_DIR, show_index=False, name="static")
    return app


async def run_web(server: SigloServer, host: str, port: int) -> web.AppRunner:
    """Arranca el servidor web y devuelve el runner (para poder detenerlo)."""
    app = build_app(server)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    return runner
