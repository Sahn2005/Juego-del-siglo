"""Servidor web de Siglo: sirve el cliente (HTML/CSS/JS) y el WebSocket.

Es lo que se sube a un hosting/VPS para que la gente juegue desde el
navegador, sin instalar nada. Usa la misma mesa (Match, vía SigloServer)
que el cliente de escritorio, así que da igual por dónde entre cada quien.
"""
from pathlib import Path

from aiohttp import web

from src.database import AccountDatabase, AccountError, SESSION_SECONDS
from src.server import SigloServer

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
SERVER_KEY = web.AppKey("server", SigloServer)


@web.middleware
async def no_cache(request: web.Request, handler):
    """Que el navegador revalide siempre los archivos del juego.

    Sin esto, tras actualizar app.js o style.css el navegador puede seguir
    mostrando la versión vieja guardada. Con "no-cache" sigue pudiendo usar
    su copia, pero primero pregunta al servidor si cambió (barato: 304).

    La ruta /ws es un WebSocket: sus headers ya se envían dentro del handler
    (ws.prepare), así que hay que saltarla ANTES de llamar al handler para
    no intentar modificar una respuesta que ya salió por el socket.
    """
    if request.path == "/ws":
        return await handler(request)
    response = await handler(request)
    response.headers["Cache-Control"] = "no-cache"
    return response


def build_app(server: SigloServer) -> web.Application:
    app = web.Application(middlewares=[no_cache])
    app[SERVER_KEY] = server
    if server.database is None:
        server.database = AccountDatabase()
    database = server.database
    session_cookie = "siglo_session"

    def account_for(request: web.Request):
        return database.get_session_account(request.cookies.get(session_cookie))

    async def read_json(request: web.Request) -> dict:
        try:
            data = await request.json()
        except (ValueError, web.HTTPException):
            raise web.HTTPBadRequest(text="El cuerpo debe ser JSON válido.") from None
        if not isinstance(data, dict):
            raise web.HTTPBadRequest(text="El cuerpo debe ser un objeto JSON.")
        return data

    def set_session(response: web.Response, token: str, request: web.Request) -> None:
        response.set_cookie(
            session_cookie,
            token,
            max_age=SESSION_SECONDS,
            httponly=True,
            secure=request.secure,
            samesite="Strict",
            path="/",
        )

    async def register(request: web.Request) -> web.Response:
        data = await read_json(request)
        try:
            account = database.register(
                str(data.get("username", "")), str(data.get("password", ""))
            )
        except AccountError as err:
            raise web.HTTPBadRequest(text=str(err)) from None
        token = database.create_session(account["id"])
        response = web.json_response({"account": account})
        set_session(response, token, request)
        return response

    async def login(request: web.Request) -> web.Response:
        data = await read_json(request)
        try:
            account = database.authenticate(
                str(data.get("username", "")), str(data.get("password", ""))
            )
        except AccountError as err:
            raise web.HTTPUnauthorized(text=str(err)) from None
        token = database.create_session(account["id"])
        response = web.json_response({"account": account})
        set_session(response, token, request)
        return response

    async def logout(request: web.Request) -> web.Response:
        database.delete_session(request.cookies.get(session_cookie))
        response = web.json_response({"ok": True})
        response.del_cookie(session_cookie, path="/", samesite="Strict")
        return response

    async def me(request: web.Request) -> web.Response:
        account = account_for(request)
        if account is None:
            raise web.HTTPUnauthorized(text="Inicia sesión para continuar.")
        return web.json_response({"account": account})

    async def history(request: web.Request) -> web.Response:
        account = account_for(request)
        if account is None:
            raise web.HTTPUnauthorized(text="Inicia sesión para ver tu historial.")
        return web.json_response(database.get_history(account["id"]))

    async def ws_handler(request: web.Request) -> web.WebSocketResponse:
        token = request.cookies.get(session_cookie)
        account = account_for(request)
        if token and account is None:
            raise web.HTTPUnauthorized(text="Tu sesión venció. Inicia sesión nuevamente.")
        ws = web.WebSocketResponse(heartbeat=25)
        await ws.prepare(request)
        await server.handle_websocket(ws, account)
        return ws

    async def health(request: web.Request) -> web.Response:
        # Para que el proveedor de hosting (o vos) pueda comprobar que
        # sigue vivo sin tener que abrir un WebSocket.
        m = server.match
        db = getattr(server, "database", None)
        backend = "postgresql" if db.__class__.__name__.startswith("Postgres") else "sqlite"
        return web.json_response({"ok": True, "jugadores": len(m.seats), "fase": m.phase,
                                  "cuentas": backend, "cuentas_persistentes": backend == "postgresql"})

    async def index(request: web.Request) -> web.FileResponse:
        return web.FileResponse(WEB_DIR / "index.html")

    app.router.add_get("/ws", ws_handler)
    app.router.add_post("/api/register", register)
    app.router.add_post("/api/login", login)
    app.router.add_post("/api/logout", logout)
    app.router.add_get("/api/me", me)
    app.router.add_get("/api/history", history)
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
