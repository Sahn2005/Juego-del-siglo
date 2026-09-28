"""Piezas visuales compartidas por el modo solitario y el multijugador.

Todo lo que tiene que ver con "cómo se ve la mesa" vive aquí: el fondo de
paño verde, las fichas estilo balota de lotería y la tarjeta de cada
jugador. Tanto src/ui.py (solitario) como src/online.py (multijugador)
llaman a estas mismas funciones, así que ambos modos se ven igual.

No depende de Match ni de Player: recibe solo tipos simples (dict, str,
int), para poder usarse igual con un Player local o con el snapshot que
manda el servidor.
"""
import math

import pygame

from src.utils import WINDOW_WIDTH

# ---------------------------------------------------------------- paleta

FELT_DARK = (12, 54, 41)
FELT_LIGHT = (23, 92, 68)
RAIL_WOOD = (69, 42, 27)
RAIL_WOOD_LIGHT = (110, 71, 43)
GOLD = (216, 178, 63)
GOLD_DIM = (150, 122, 45)
CREAM = (250, 246, 234)
CREAM_DIM = (234, 227, 206)
INK = (40, 33, 26)
INK_SOFT = (95, 85, 72)
CREAM_TEXT = (240, 235, 220)
CREAM_TEXT_DIM = (191, 201, 190)

# Un color por decena (1-10, 11-20, ... 81-90), como las balotas de una
# lotería de verdad, que suelen venir en varios colores según el número.
DECILE_COLORS = [
    (206, 62, 62),    # 1-10
    (214, 118, 40),   # 11-20
    (221, 173, 42),   # 21-30
    (121, 168, 62),   # 31-40
    (52, 138, 86),    # 41-50
    (37, 140, 138),   # 51-60
    (46, 108, 189),   # 61-70
    (105, 78, 178),   # 71-80
    (191, 59, 120),   # 81-90
]

AVATAR_COLORS = [
    (176, 58, 58), (188, 108, 37), (168, 140, 40), (74, 128, 74),
    (43, 120, 130), (58, 92, 158), (108, 74, 158), (163, 60, 110),
]

STATUS_STYLE = {
    # clave: (color de fondo del badge, texto)
    "WAITING": ((146, 152, 146), "Esperando"),
    "PLAYING": ((41, 130, 90), "Jugando"),
    "ME_QUEDO": ((77, 96, 145), "Me quedo"),
    "ME_FUI": ((176, 48, 48), "Me fui"),
    "SIGLO": ((int(GOLD[0]), int(GOLD[1]), int(GOLD[2])), "¡SIGLO!"),
}


def _clamp(v, lo=0, hi=255):
    return max(lo, min(hi, int(v)))


def _mix(c1, c2, t):
    return tuple(_clamp(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))


def lighten(color, amount):
    return _mix(color, (255, 255, 255), amount)


def darken(color, amount):
    return _mix(color, (0, 0, 0), amount)


def _luminance(color):
    r, g, b = color
    return 0.299 * r + 0.587 * g + 0.114 * b


def decile_color(value: int):
    idx = max(0, min(8, (int(value) - 1) // 10))
    return DECILE_COLORS[idx]


# ---------------------------------------------------------------- fondo

def draw_felt_background(surface):
    """Paño verde con degradado suave y una baranda de madera con filo dorado."""
    w, h = surface.get_size()
    for y in range(h):
        color = _mix(FELT_LIGHT, FELT_DARK, y / max(h - 1, 1))
        pygame.draw.line(surface, color, (0, y), (w, y))

    # Viñeta: las esquinas un poco más oscuras para dar profundidad.
    vignette = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.rect(vignette, (0, 0, 0, 70), (0, 0, w, h), border_radius=0)
    inner = pygame.Rect(int(w * 0.06), int(h * 0.06), int(w * 0.88), int(h * 0.88))
    pygame.draw.rect(vignette, (0, 0, 0, 0), inner, border_radius=60)
    # Recortar el centro: se dibuja el rectángulo interior "borrando" con
    # blend especial no disponible directo, así que en su lugar difuminamos
    # con varias capas del borde hacia adentro.
    surface.blit(vignette, (0, 0))

    # Baranda de madera + filo dorado, como el borde de una mesa de juego.
    pygame.draw.rect(surface, RAIL_WOOD, (0, 0, w, h), width=16)
    pygame.draw.rect(surface, RAIL_WOOD_LIGHT, (8, 8, w - 16, h - 16), width=3)
    pygame.draw.rect(surface, GOLD_DIM, (18, 18, w - 36, h - 36), width=2, border_radius=6)


def draw_table_header(surface, ui, title, subtitle=None, corner_text=None, y=44):
    """Título dorado con relieve, para las pantallas dentro de la mesa."""
    cx = WINDOW_WIDTH // 2
    shadow = ui.title_font.render(title, True, darken(GOLD, 0.75))
    surface.blit(shadow, shadow.get_rect(center=(cx + 2, y + 3)))
    main = ui.title_font.render(title, True, GOLD)
    surface.blit(main, main.get_rect(center=(cx, y)))

    if subtitle:
        _text(surface, ui.small_font, subtitle, CREAM_TEXT_DIM, cx, y + 34)
    if corner_text:
        surf = ui.small_font.render(corner_text, True, GOLD)
        surface.blit(surf, surf.get_rect(topright=(WINDOW_WIDTH - 26, 22)))


# ---------------------------------------------------------------- fichas

def draw_ball(surface, font, value, center, radius=20, vira=False):
    """Una ficha numerada con volumen, como una balota de lotería.

    vira=True le pone un anillo dorado (la primera ficha que recibe cada
    jugador, la que define el punto de partida de la ronda).
    """
    x, y = center
    r = radius
    base = decile_color(value)

    if vira:
        pygame.draw.circle(surface, GOLD, (x, y), r + 4)
        pygame.draw.circle(surface, darken(GOLD, 0.3), (x, y), r + 4, 1)

    # Sombra proyectada.
    shadow = pygame.Surface((r * 2 + 8, r * 2 + 8), pygame.SRCALPHA)
    pygame.draw.circle(shadow, (0, 0, 0, 80), (r + 4, r + 6), r)
    surface.blit(shadow, (x - r - 4, y - r - 4))

    pygame.draw.circle(surface, base, (x, y), r)
    pygame.draw.circle(surface, darken(base, 0.45), (x, y), r, max(1, r // 10))

    # Brillo: una elipse blanca translúcida arriba a la izquierda.
    gloss = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
    gloss_rect = pygame.Rect(0, 0, int(r * 1.15), int(r * 0.8))
    gloss_rect.center = (int(r * 0.72), int(r * 0.62))
    pygame.draw.ellipse(gloss, (255, 255, 255, 95), gloss_rect)
    surface.blit(gloss, (x - r, y - r))

    text_color = CREAM if _luminance(base) < 150 else INK
    label = str(value)
    surf = font.render(label, True, text_color)
    surface.blit(surf, surf.get_rect(center=(x, y)))


def draw_ball_row(surface, font, values, center_x, top_y, max_width,
                  radius=18, vira_first=True):
    """Reparte fichas en una cuadrícula centrada dentro de max_width.

    Devuelve el alto usado, por si el que llama necesita saber dónde sigue
    el resto del contenido.
    """
    if not values:
        return 0
    step = radius * 2 + 6
    cols = max(1, min(len(values), int(max_width // step)))
    rows = math.ceil(len(values) / cols)
    for i, value in enumerate(values):
        row, col = divmod(i, cols)
        in_row = min(cols, len(values) - row * cols)
        bx = center_x - (in_row * step) // 2 + step // 2 + col * step
        by = top_y + radius + row * step
        draw_ball(surface, font, value, (bx, by), radius, vira=(vira_first and i == 0))
    return rows * step


def card_rects(n, top=118, bottom=560, margin=8):
    """Reparte n tarjetas iguales a lo ancho, con el mismo alto para todas.

    Usado tanto por el modo solitario como por el multijugador para que las
    tarjetas queden en el mismo sitio en los dos modos.
    """
    n = max(1, n)
    col_w = WINDOW_WIDTH // n
    return [
        pygame.Rect(i * col_w + margin, top, col_w - margin * 2, bottom - top)
        for i in range(n)
    ]


# ---------------------------------------------------------------- tarjeta

def _text(surface, font, text, color, x, y):
    surf = font.render(text, True, color)
    surface.blit(surf, surf.get_rect(center=(x, y)))


def _fit_text(surface, primary_font, fallback_font, text, color, x, y, max_width):
    font = primary_font
    if font.size(text)[0] > max_width:
        font = fallback_font
    if font.size(text)[0] > max_width:
        while len(text) > 1 and font.size(text + "…")[0] > max_width:
            text = text[:-1]
        text = text + "…"
    surf = font.render(text, True, color)
    surface.blit(surf, surf.get_rect(center=(x, y)))


def draw_avatar(surface, font, name, center, radius=24):
    color = AVATAR_COLORS[hash(name) % len(AVATAR_COLORS)]
    pygame.draw.circle(surface, color, center, radius)
    pygame.draw.circle(surface, darken(color, 0.4), center, radius, 2)
    initial = (name.strip()[:1] or "?").upper()
    surf = font.render(initial, True, CREAM)
    surface.blit(surf, surf.get_rect(center=center))


def draw_pill(surface, font, text, center, bg_color, text_color=None, pad_x=14, pad_y=5):
    if text_color is None:
        text_color = CREAM if _luminance(bg_color) < 150 else INK
    surf = font.render(text, True, text_color)
    rect = surf.get_rect(center=center).inflate(pad_x * 2, pad_y * 2)
    pygame.draw.rect(surface, bg_color, rect, border_radius=rect.height // 2)
    surface.blit(surf, surf.get_rect(center=center))
    return rect


def draw_progress_bar(surface, rect, ratio, color):
    ratio = max(0.0, min(1.0, ratio))
    pygame.draw.rect(surface, darken(CREAM_DIM, 0.25), rect, border_radius=rect.height // 2)
    if ratio > 0:
        filled = rect.copy()
        filled.width = max(rect.height, int(rect.width * ratio))
        pygame.draw.rect(surface, color, filled, border_radius=rect.height // 2)
    pygame.draw.rect(surface, darken(CREAM_DIM, 0.45), rect, width=1, border_radius=rect.height // 2)


def draw_player_card(surface, ui, rect, *, name, score, status, balls,
                     is_turn=False, is_winner=False, is_me=False,
                     connected=True, wins=None, seconds_left=None):
    """Dibuja la tarjeta completa de un jugador dentro de `rect`.

    `status` es uno de los strings de Player.status (PLAYING, ME_QUEDO...).
    `wins` es None en el modo solitario (no aplica) o un entero en línea.
    """
    alpha = 255 if connected else 160
    card = pygame.Surface(rect.size, pygame.SRCALPHA)
    local = card.get_rect()

    # Sombra + cuerpo de la tarjeta.
    shadow_rect = local.copy()
    pygame.draw.rect(card, (0, 0, 0, 60), shadow_rect.inflate(-2, -2).move(0, 5), border_radius=16)
    pygame.draw.rect(card, (*CREAM, alpha), local, border_radius=16)
    pygame.draw.rect(card, (*CREAM_DIM, alpha), local.inflate(-6, -6), width=1, border_radius=13)

    cx = local.centerx
    pad = 12

    draw_avatar(card, ui.small_font, name, (cx, pad + 24), radius=24)
    if is_me:
        pygame.draw.circle(card, GOLD, (cx, pad + 24), 27, 2)

    _fit_text(card, ui.font, ui.small_font, name, INK if connected else INK_SOFT,
              cx, pad + 62, local.width - 2 * pad)

    tag_y = pad + 84
    if not connected:
        _text(card, ui.small_font, "Desconectado", INK_SOFT, cx, tag_y)
    elif is_me:
        _text(card, ui.small_font, "Tú", darken(GOLD, 0.35), cx, tag_y)

    score_font = getattr(ui, "score_font", ui.font)
    score_color = INK if connected else INK_SOFT
    surf = score_font.render(str(score), True, score_color)
    card.blit(surf, surf.get_rect(center=(cx, pad + 118)))
    _text(card, ui.small_font, "puntos", INK_SOFT, cx, pad + 144)

    bg, label = STATUS_STYLE.get(status, ((150, 150, 150), status))
    draw_pill(card, ui.small_font, label, (cx, pad + 172), bg)
    if wins is not None:
        _text(card, ui.small_font, f"★ {wins} victoria{'s' if wins != 1 else ''}",
              INK_SOFT, cx, pad + 198)

    bar_y = pad + 220
    ratio = min(score, 100) / 100
    if status == "ME_FUI":
        bar_color, ratio = darken((176, 48, 48), 0.0), 1.0
    elif status == "SIGLO":
        bar_color = GOLD
    elif score >= 90:
        bar_color = (196, 130, 40)
    else:
        bar_color = (60, 140, 90)
    draw_progress_bar(card, pygame.Rect(pad, bar_y, local.width - 2 * pad, 10), ratio, bar_color)

    tray_top = bar_y + 22
    tray = pygame.Rect(pad, tray_top, local.width - 2 * pad, local.height - tray_top - pad)
    pygame.draw.rect(card, darken(CREAM_DIM, 0.12), tray, border_radius=10)
    if balls:
        radius = 18 if len(balls) <= 12 else 15
        draw_ball_row(card, ui.small_font, balls, tray.centerx, tray.top + 6,
                     tray.width - 8, radius=radius)

    # Marco: dorado pulsante si es su turno, dorado fijo si ganó.
    if is_turn:
        pulse = 2.5 + 1.5 * math.sin(pygame.time.get_ticks() / 220)
        pygame.draw.rect(card, GOLD, local, width=int(4 + pulse), border_radius=16)
    elif is_winner:
        pygame.draw.rect(card, GOLD, local, width=4, border_radius=16)
    else:
        pygame.draw.rect(card, darken(CREAM_DIM, 0.3), local, width=1, border_radius=16)

    surface.blit(card, rect.topleft)

    if is_turn:
        _draw_turn_flag(surface, rect)
    if is_winner:
        _draw_winner_flag(surface, rect)


def _draw_turn_flag(surface, rect):
    cx = rect.centerx
    top = rect.top - 14
    points = [(cx - 12, top), (cx + 12, top), (cx, top + 14)]
    pygame.draw.polygon(surface, GOLD, points)
    pygame.draw.polygon(surface, darken(GOLD, 0.3), points, 1)


def _draw_winner_flag(surface, rect):
    cx = rect.centerx
    cy = rect.top - 16
    pygame.draw.circle(surface, GOLD, (cx, cy), 14)
    pygame.draw.circle(surface, darken(GOLD, 0.3), (cx, cy), 14, 2)
    # una estrella simple de 5 puntas
    pts = []
    for i in range(10):
        ang = math.pi / 2 + i * math.pi / 5
        rad = 11 if i % 2 == 0 else 5
        pts.append((cx + rad * math.cos(ang), cy - rad * math.sin(ang)))
    pygame.draw.polygon(surface, CREAM, pts)
