"""Cliente 3D de Siglo (Ursina) — prototipo.

Uso:
    pip install ursina
    python cliente_3d.py
    python cliente_3d.py --auto 127.0.0.1:5555 --nombre Ana     # entra solo como invitado

Habla con el mismo servidor TCP que cliente.py (servidor.py, puerto 5555),
así que puede jugar en la misma mesa que los clientes de pygame y navegador.
No decide nada: manda "draw" / "request_draw" / "stay" / "start" y dibuja el estado recibido.
Los oponentes se ven ocultos mientras juegan porque el servidor ya no manda
sus fichas (no hay forma de verlas desde aquí).
"""
import argparse
import math
import os
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
_JUEGO = os.path.join(_AQUI, "siglo_game")
if not os.path.isdir(os.path.join(_JUEGO, "src")):
    sys.exit("No encuentro la carpeta siglo_game/src junto a este archivo.\n"
             "Copia cliente_3d.py a la carpeta raíz del proyecto (donde están cliente.py y servidor.py).")
sys.path.insert(0, _JUEGO)

from ursina import (  # noqa: E402
    Ursina, Entity, Text, Cylinder, Button, InputField, Vec3, color, camera, window,
    scene, application, time, curve, destroy, held_keys,
)

from src.net_client import NetworkClient  # noqa: E402
from src.protocol import (  # noqa: E402
    DEFAULT_PORT, PHASE_LOBBY, PHASE_PLAYING, PHASE_ROUND_END, MIN_PLAYERS, parse_address,
)

# Un color por decena (1-10, 11-20, ...), como las balotas de lotería.
DECILES = [(206, 62, 62), (232, 130, 40), (222, 190, 50), (52, 138, 86), (40, 150, 170),
           (60, 100, 190), (110, 80, 180), (191, 59, 120), (90, 90, 100)]
FELT = color.rgb32(22, 96, 64)
WOOD = color.rgb32(92, 56, 32)
GOLD = color.rgb32(240, 200, 80)
WOOD_FACE = color.rgb32(238, 214, 168)
WOOD_EDGE = color.rgb32(196, 160, 106)
CHIP_RED = color.rgb32(200, 50, 38)
CREAM = color.rgb32(245, 236, 210)


def rgb(c):
    return color.rgb32(*c)


def ball_color(v):
    return rgb(DECILES[max(0, min(8, (v - 1) // 10))])


def seat_positions(n, me_index):
    """Posición en la mesa de cada jugador; yo siempre abajo (cerca de la cámara)."""
    out = []
    for i in range(n):
        k = (i - me_index) % n
        ang = -math.pi / 2 + k * 2 * math.pi / n
        out.append(Vec3(6.6 * math.cos(ang), 0, 3.9 * math.sin(ang) + 0.9))
    return out


class Game3D(Entity):
    def __init__(self, args):
        super().__init__()
        self.args = args
        self.net = None
        self.stage = "FORM"
        self.snap = None
        self.my_id = None
        self.stats = None
        self.mode = "GUEST"
        self.waiting = False
        self.items = []                 # entidades de la mesa (se rehacen en cada estado)
        self.counts = {}                # id -> fichas ya dibujadas (para animar solo las nuevas)
        self.plates = {}
        self.t = 0.0
        self.shot_at = None
        self._build_scene()
        self._build_hud()
        self._build_form()
        if args.auto:
            self.addr.text = args.auto
            self.user.text = args.nombre
            self._connect()

    # ------------------------------------------------------------ escena fija
    def _build_scene(self):
        window.color = color.rgb32(14, 22, 20)
        application.base.setBackgroundColor(14 / 255, 22 / 255, 20 / 255)
        Entity(model='circle', color=WOOD, rotation_x=90, scale=(23, 17), y=-0.06, z=0.8)
        Entity(model='circle', color=FELT, rotation_x=90, scale=(21, 15), y=-0.02, z=0.8)
        Entity(model='circle', color=color.rgb32(30, 120, 80), rotation_x=90, scale=(11, 7.5), y=-0.01, z=0.8)
        camera.position = (0, 16, -16)
        camera.rotation_x = 46
        camera.fov = 52

    # ------------------------------------------------------------ interfaz 2D
    def _build_hud(self):
        self.title = Text("SIGLO", parent=camera.ui, position=(0, 0.47), origin=(0, 0), scale=2.4, color=GOLD)
        self.status = Text("", parent=camera.ui, position=(0, -0.375), origin=(0, 0), scale=1.4, color=CREAM)
        self.timer = Text("", parent=camera.ui, position=(0, -0.415), origin=(0, 0), scale=0.9, color=CREAM)
        self.stats_text = Text("", parent=camera.ui, position=(0, -0.49), origin=(0, 0), scale=0.8,
                               color=color.rgba32(245, 236, 210, 190))
        self.notice = Text("", parent=camera.ui, position=(0, 0.40), origin=(0, 0), scale=1.2, color=color.rgb32(255, 120, 110))
        self.btn_start = self._button("INICIAR PARTIDA", (0.0, -0.455), lambda: self._send("start"), color.azure, 0.30, 0.05)
        self.btn_deal = self._button("BOLA", (-0.15, -0.455), self._deal_click, color.azure, 0.22, 0.05)
        self.btn_stay = self._button("ME QUEDO", (0.15, -0.455), lambda: self._send("stay"), color.red, 0.22, 0.05)
        self.btn_next = self._button("NUEVA RONDA", (0, -0.455), lambda: self._send("start"), color.azure, 0.30, 0.05)
        self.btn_leave = self._button("SALIR", (-0.78, 0.45), self._leave, color.red, 0.12, 0.05)
        for b in (self.btn_start, self.btn_deal, self.btn_stay, self.btn_next, self.btn_leave):
            b.enabled = False

    def _button(self, label, pos, fn, col, w, h=0.07):
        b = Button(text=label, parent=camera.ui, position=pos, scale=(w, h), color=col, on_click=fn)
        b.text_color = color.white
        return b

    def _build_form(self):
        self.form = Entity(parent=camera.ui)
        Text("Multijugador 3D", parent=self.form, position=(0, 0.36), origin=(0, 0), scale=1.6, color=CREAM)
        self.tabs = []
        for i, (mode, label) in enumerate([("GUEST", "Invitado"), ("LOGIN", "Entrar"), ("REGISTER", "Registrarme")]):
            b = self._button(label, (-0.22 + i * 0.22, 0.27), lambda m=mode: self._set_mode(m), color.gray, 0.20, 0.06)
            b.parent = self.form
            self.tabs.append((mode, b))
        self.addr = self._field("Servidor (IP:puerto)", 0.15, "127.0.0.1")
        self.user = self._field("Tu nombre", 0.03, "")
        self.pw = self._field("Contraseña", -0.09, "")
        self.pw.hide_content = True
        self.go = self._button("JUGAR", (0, -0.24), self._connect, color.azure, 0.30)
        self.go.parent = self.form
        self.form_msg = Text("", parent=self.form, position=(0, -0.33), origin=(0, 0), scale=1.1, color=color.rgb32(255, 120, 110))
        self._set_mode("GUEST")

    def _field(self, label, y, default):
        Text(label, parent=self.form, position=(-0.2, y + 0.045), origin=(-0.5, 0), scale=0.85, color=CREAM)
        f = InputField(default_value=default, parent=self.form, position=(0, y), scale=(0.4, 0.045), character_limit=40)
        return f

    def _set_mode(self, mode):
        self.mode = mode
        for m, b in self.tabs:
            b.color = color.azure if m == mode else color.gray
        self.pw.enabled = mode != "GUEST"
        self.go.text = {"GUEST": "JUGAR", "LOGIN": "ENTRAR", "REGISTER": "CREAR CUENTA"}[mode]
        self.form_msg.text = ""

    # ------------------------------------------------------------ red
    def _connect(self):
        try:
            host, port = parse_address(self.addr.text)
        except ValueError as err:
            self.form_msg.text = str(err)
            return
        name = (self.user.text or "Jugador").strip()[:10] or "Jugador"
        auth = None
        if self.mode != "GUEST":
            if not self.user.text.strip() or not self.pw.text:
                self.form_msg.text = "Escribe tu usuario y contraseña."
                return
            auth = {"type": "login" if self.mode == "LOGIN" else "register",
                    "username": self.user.text.strip(), "password": self.pw.text}
        self.net = NetworkClient()
        self.net.connect(host, port, name, auth)
        self.stage = "CONNECTING"
        self.form_msg.text = "Conectando..."

    def _send(self, kind):
        if self.net and self.net.send({"type": kind}):
            self.waiting = True

    def _deal_click(self):
        self._send(getattr(self, "_deal_action", "draw"))

    def _leave(self):
        if self.net:
            self.net.close()
        self.net = None
        self.snap = None
        self.stats = None
        self.stage = "FORM"
        self._clear()
        self.form.enabled = True
        for b in (self.btn_start, self.btn_deal, self.btn_stay, self.btn_next, self.btn_leave):
            b.enabled = False
        self.status.text = self.timer.text = self.stats_text.text = ""

    def _on(self, m):
        k = m.get("type")
        if k == "welcome":
            self.my_id = m["id"]
            self.stats = m.get("stats")
            self.stage = "ONLINE"
            self.form.enabled = False
        elif k == "stats":
            self.stats = {"games_played": m["games_played"], "games_won": m["games_won"]}
        elif k == "state":
            self.snap, self.waiting, self._snap_t = m, False, self.t
            if self.args.captura:
                print("FASE", m["phase"], round(self.t, 1), flush=True)
            self._rebuild()
        elif k == "error":
            self.waiting = False
            if self.stage == "ONLINE":
                self.notice.text = m["message"]
                self.notice_until = self.t + 3
            else:
                self._leave()
                self.form_msg.text = m["message"]
        elif k in ("_failed", "_closed"):
            msg = m.get("message", "Se perdió la conexión.")
            self._leave()
            self.form_msg.text = msg

    # ------------------------------------------------------------ dibujo de la mesa
    def _clear(self):
        for e in self.items:
            destroy(e)
        self.items = []
        self.plates = {}
        self.counts = {}

    def _add(self, e):
        self.items.append(e)
        return e

    def _label(self, text, pos, scale=14, col=CREAM):
        t = Text(text, parent=scene, position=pos, origin=(0, 0), scale=scale, color=col, billboard=True)
        return self._add(t)

    def _chip(self, v, pos, r=0.8, fall=False, blank=False):
        """Ficha de lotería: disco de madera, aro rojo y número rojo.
        `pos` es el centro de la base; el disco mide 0.2 de alto."""
        h = 0.22
        root = self._add(Entity(position=pos))
        Entity(parent=root, model=Cylinder(resolution=40, height=1), color=WOOD_EDGE,
               scale=(r * 2, h, r * 2), y=0)
        top = h + 0.002
        if blank:
            Entity(parent=root, model='circle', color=WOOD_FACE, rotation_x=90, scale=r * 1.96, y=top + 0.01)
            Entity(parent=root, model='circle', color=color.rgb32(222, 196, 146), rotation_x=90, scale=r * 1.3, y=top + 0.02)
            return root
        Entity(parent=root, model='circle', color=CHIP_RED, rotation_x=90, scale=r * 1.98, y=top + 0.01)
        Entity(parent=root, model='circle', color=WOOD_FACE, rotation_x=90, scale=r * 1.5, y=top + 0.02)
        Text(str(v), parent=root, position=(0, top + 0.04, 0), rotation_x=90, origin=(0, 0),
             scale=(24 if v < 100 else 19), color=CHIP_RED)
        if fall:
            root.y = pos.y + 7
            root.animate_y(pos.y, duration=0.55, curve=curve.out_bounce)
        return root

    def _rebuild(self):
        snap = self.snap
        players = snap["players"]
        old = dict(self.counts)
        self._clear()
        self.counts = {}
        me_i = next((i for i, p in enumerate(players) if p["id"] == self.my_id), 0)
        spots = seat_positions(len(players), me_i)
        winners = set(snap.get("winner_ids", []))
        playing = snap["phase"] == PHASE_PLAYING

        for p, pos in zip(players, spots):
            mine = p["id"] == self.my_id
            turn = playing and p["id"] == snap["turn_id"]
            plate_col = color.rgb32(40, 30, 24) if not turn else color.rgb32(86, 64, 22)
            plate = self._add(Entity(model='cube', color=plate_col, position=pos + Vec3(0, 0.05, 0),
                                     scale=(5.4, 0.1, 2.9)))
            rim = GOLD if (p["id"] in winners or turn) else (color.rgb32(210, 190, 140) if mine else color.rgb32(110, 90, 70))
            self._add(Entity(model='cube', color=rim, position=pos + Vec3(0, 0.03, 0), scale=(5.55, 0.08, 3.05)))
            self.plates[p["id"]] = plate
            name = p["name"] + ("  (tú)" if mine else "") + ("  (anfitrión)" if p["id"] == snap["host_id"] else "")
            self._label(name, pos + Vec3(0, 0.4, 2.0), 15, GOLD if mine else CREAM)

            if p.get("hidden"):
                self._label("oculto", pos + Vec3(1.6, 0.8, -0.2), 13, color.rgba32(245, 236, 210, 160))
                # dorso de la ficha: madera lisa, sin número ni cantidad
                self._chip(0, pos + Vec3(0, 0.08, -0.25), blank=True)
                continue

            balls = p["balls"]
            n = len(balls)
            span = min(4.2, 1.7 * n)
            step = span / max(1, n - 1) if n > 1 else 0
            for i, v in enumerate(balls):
                x = -span / 2 + i * step
                fresh = i >= old.get(p["id"], 0) and playing
                self._chip(v, pos + Vec3(x, 0.08, -0.25), fall=fresh)
            self.counts[p["id"]] = n
            if p["score"] is not None:
                self._label(f"{p['score']}", pos + Vec3(3.7, 1.0, 0.2), 26, GOLD)
                self._label(p["status"].replace("_", " "), pos + Vec3(3.7, 0.5, -0.7), 11, CREAM)

        self._refresh_hud()

    def _refresh_hud(self):
        snap = self.snap
        if not snap:
            return
        host = snap["host_id"] == self.my_id
        my_turn = snap["phase"] == PHASE_PLAYING and snap["turn_id"] == self.my_id
        deals = bool(snap.get("host_deals"))
        req = snap.get("draw_request")
        can_request = deals and not host and my_turn and req is None
        can_deal = (my_turn if not deals else
                    host and (my_turn or (req is not None and req["player_id"] == snap["turn_id"])))
        self._deal_action = "request_draw" if can_request else "draw"
        ph = snap["phase"]
        self.btn_leave.enabled = True
        self.btn_start.enabled = ph == PHASE_LOBBY and host
        self.btn_start.color = color.azure if len(snap["players"]) >= MIN_PLAYERS else color.gray
        self.btn_deal.enabled = ph == PHASE_PLAYING and (can_deal or can_request)
        self.btn_deal.text = ("REPARTIR" if host else "PEDIR BOLA") if deals else "BOLA"
        self.btn_stay.enabled = ph == PHASE_PLAYING and my_turn
        self.btn_next.enabled = ph == PHASE_ROUND_END and host
        # con los dos botones a la vista se separan; con uno solo va al centro
        both = self.btn_deal.enabled and self.btn_stay.enabled
        self.btn_deal.x = -0.15 if both else 0
        self.btn_stay.x = 0.15 if both else 0
        if ph == PHASE_LOBBY:
            self.status.text = "Sala de espera  ·  " + f"{len(snap['players'])}/{snap['max_players']}"
        elif ph == PHASE_PLAYING:
            cur = next((p for p in snap["players"] if p["id"] == snap["turn_id"]), None)
            self.status.text = "¡ES TU TURNO!" if my_turn else f"Turno de {cur['name'] if cur else '...'}"
        else:
            names = [p["name"] for p in snap["players"] if p["id"] in set(snap["winner_ids"])]
            self.status.text = ("Ganador(es): " + ", ".join(names)) if names else "Todos se pasaron. Sin ganadores."
        if self.stats:
            self.stats_text.text = f"Tu cuenta · Partidas: {self.stats['games_played']} · Ganadas: {self.stats['games_won']}"
        self.title.text = f"SIGLO · Ronda {snap['round']}" if snap["round"] else "SIGLO"

    # ------------------------------------------------------------ bucle
    notice_until = 0.0

    def update(self):
        self.t += time.dt
        if self.net:
            for m in self.net.poll():
                self._on(m)
                if self.net is None:
                    break
        if self.notice.text and self.t > self.notice_until:
            self.notice.text = ""
        if self.snap and self.snap["phase"] == PHASE_PLAYING:
            left = self.snap.get("time_left")
            if left is not None:
                self.timer.text = f"Tiempo: {max(0, math.ceil(left - (self.t - getattr(self, '_snap_t', self.t))))} s"
        else:
            self.timer.text = ""
        # pulso dorado del turno
        for pid, plate in self.plates.items():
            if self.snap and self.snap["phase"] == PHASE_PLAYING and pid == self.snap["turn_id"]:
                k = 0.5 + 0.5 * math.sin(self.t * 5)
                plate.color = color.rgb32(int(70 + 50 * k), int(52 + 36 * k), 20)
        # automatización para demos/capturas
        if self.args.captura:
            if self.shot_at is None and self.snap and self.snap["phase"] == self.args.fase:
                self.shot_at = self.t + 1.6
            if self.shot_at is not None and self.t >= self.shot_at:
                for _ in range(3):
                    application.base.graphicsEngine.renderFrame()
                application.base.win.saveScreenshot(self.args.captura)
                application.quit()
            if self.t > 40:
                print("sin captura: fase", self.snap and self.snap["phase"])
                application.quit()
        if self.args.auto and self.snap:
            self._autoplay()

    def _autoplay(self):
        s = self.snap
        if s["phase"] == PHASE_LOBBY and s["host_id"] == self.my_id and len(s["players"]) >= self.args.jugadores \
                and not self.waiting:
            self._send("start")
        elif s["phase"] == PHASE_PLAYING and not self.waiting and self.t > getattr(self, "_next_act", 0):
            me = next(p for p in s["players"] if p["id"] == self.my_id)
            deals, host = bool(s.get("host_deals")), s["host_id"] == self.my_id
            req = s.get("draw_request")
            mine = s["turn_id"] == self.my_id
            self._next_act = self.t + 1.2
            if deals and host and req and not mine:
                self._send("draw")                      # el anfitrión reparte a quien la pidió
            elif mine and len(me["balls"]) >= 2:
                self._send("stay")
            elif mine and deals and not host:
                if req is None:
                    self._send("request_draw")
            elif mine:
                self._send("draw")

    def input(self, key):
        if key == 'escape' and self.stage == "ONLINE":
            self._leave()


def main():
    ap = argparse.ArgumentParser(description="Cliente 3D de Siglo (Ursina)")
    ap.add_argument("--auto", help="host:puerto: conecta solo como invitado")
    ap.add_argument("--nombre", default="Jugador")
    ap.add_argument("--jugadores", type=int, default=3, help="con --auto: inicia al haber tantos jugadores")
    ap.add_argument("--captura", help="guarda una captura PNG y sale (para pruebas)")
    ap.add_argument("--fase", default=PHASE_PLAYING, help="fase en la que tomar la captura")
    args = ap.parse_args()

    app = Ursina(title="Siglo 3D", borderless=False, development_mode=False, vsync=False)
    window.size = (1280, 720)
    window.fps_counter.enabled = False
    window.exit_button.visible = False
    Game3D(args)
    app.run()


if __name__ == "__main__":
    main()
