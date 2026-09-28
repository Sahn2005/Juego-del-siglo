"use strict";
/*
 * Cliente web de Siglo.
 *
 * Habla el mismo protocolo que el cliente de escritorio (src/online.py),
 * pero sobre WebSocket en vez de un socket TCP crudo: cada mensaje es un
 * objeto JSON completo por frame (no hace falta el "\n" que separa líneas
 * en TCP, porque un WebSocket ya entrega los mensajes completos).
 *
 * El dibujo (fichas, tarjetas, mesa) reproduce a propósito los mismos
 * colores y proporciones que src/board_ui.py, para que el juego se vea
 * igual sin importar por dónde entre cada quien.
 */

// ============================================================ protocolo / constantes

const MIN_PLAYERS = 2;
const MAX_NAME_LEN = 10;
const LEAVE_CONFIRM_SECONDS = 3.0;
const NOTICE_SECONDS = 3.0;

const PHASE_LOBBY = "LOBBY";
const PHASE_PLAYING = "PLAYING";
const PHASE_ROUND_END = "ROUND_END";

// ============================================================ paleta (igual que board_ui.py)

const COLOR = {
  feltDark: "#0c3629",
  feltLight: "#175c44",
  gold: [216, 178, 63],
  cream: [250, 246, 234],
  creamDim: [232, 227, 206],
  ink: [40, 33, 26],
  inkSoft: [95, 85, 72],
  creamText: [240, 235, 220],
};

const DECILE_COLORS = [
  [206, 62, 62], [214, 118, 40], [221, 173, 42], [121, 168, 62],
  [52, 138, 86], [37, 140, 138], [46, 108, 189], [105, 78, 178], [191, 59, 120],
];

const AVATAR_COLORS = [
  [176, 58, 58], [188, 108, 37], [168, 140, 40], [74, 128, 74],
  [43, 120, 130], [58, 92, 158], [108, 74, 158], [163, 60, 110],
];

const STATUS_STYLE = {
  WAITING: { bg: [146, 152, 146], label: "Esperando" },
  PLAYING: { bg: [41, 130, 90], label: "Jugando" },
  ME_QUEDO: { bg: [77, 96, 145], label: "Me quedo" },
  ME_FUI: { bg: [176, 48, 48], label: "Me fui" },
  SIGLO: { bg: COLOR.gold, label: "¡SIGLO!" },
};

function rgb(c, a) { return a === undefined ? `rgb(${c[0]},${c[1]},${c[2]})` : `rgba(${c[0]},${c[1]},${c[2]},${a})`; }
function mix(c1, c2, t) { return [0, 1, 2].map(i => Math.round(c1[i] + (c2[i] - c1[i]) * t)); }
function lighten(c, a) { return mix(c, [255, 255, 255], a); }
function darken(c, a) { return mix(c, [0, 0, 0], a); }
function luminance(c) { return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]; }
function decileColor(v) { return DECILE_COLORS[Math.max(0, Math.min(8, Math.floor((v - 1) / 10)))]; }
function hashName(s) {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0;
  return Math.abs(h);
}

// ============================================================ dibujo: fichas y tarjetas

function drawBall(ctx, value, x, y, r, vira) {
  const base = decileColor(value);
  if (vira) {
    ctx.beginPath(); ctx.arc(x, y, r + 4, 0, Math.PI * 2);
    ctx.fillStyle = rgb(COLOR.gold); ctx.fill();
    ctx.lineWidth = 1; ctx.strokeStyle = rgb(darken(COLOR.gold, 0.3)); ctx.stroke();
  }
  // sombra
  ctx.beginPath(); ctx.arc(x + 2, y + 3, r, 0, Math.PI * 2);
  ctx.fillStyle = "rgba(0,0,0,0.28)"; ctx.fill();
  // cuerpo
  ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2);
  ctx.fillStyle = rgb(base); ctx.fill();
  ctx.lineWidth = Math.max(1, r / 10); ctx.strokeStyle = rgb(darken(base, 0.45)); ctx.stroke();
  // brillo
  const grad = ctx.createRadialGradient(x - r * 0.35, y - r * 0.4, 1, x - r * 0.35, y - r * 0.4, r * 0.9);
  grad.addColorStop(0, "rgba(255,255,255,0.55)");
  grad.addColorStop(1, "rgba(255,255,255,0)");
  ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fillStyle = grad; ctx.fill();
  // número
  ctx.fillStyle = luminance(base) < 150 ? rgb(COLOR.cream) : rgb(COLOR.ink);
  ctx.font = `700 ${Math.round(r * 0.85)}px "Segoe UI", Arial, sans-serif`;
  ctx.textAlign = "center"; ctx.textBaseline = "middle";
  ctx.fillText(String(value), x, y + 1);
}

function ballRowHeight(count, radius, maxWidth) {
  if (!count) return 0;
  const step = radius * 2 + 6;
  const cols = Math.max(1, Math.min(count, Math.floor(maxWidth / step)));
  return Math.ceil(count / cols) * step;
}

function drawBallRow(ctx, values, centerX, topY, maxWidth, radius) {
  if (!values.length) return;
  const step = radius * 2 + 6;
  const cols = Math.max(1, Math.min(values.length, Math.floor(maxWidth / step)));
  values.forEach((v, i) => {
    const row = Math.floor(i / cols), col = i % cols;
    const inRow = Math.min(cols, values.length - row * cols);
    const bx = centerX - (inRow * step) / 2 + step / 2 + col * step;
    const by = topY + radius + row * step;
    drawBall(ctx, v, bx, by, radius, i === 0);
  });
}

function drawAvatar(ctx, name, x, y, r) {
  const color = AVATAR_COLORS[hashName(name) % AVATAR_COLORS.length];
  ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2);
  ctx.fillStyle = rgb(color); ctx.fill();
  ctx.lineWidth = 2; ctx.strokeStyle = rgb(darken(color, 0.4)); ctx.stroke();
  ctx.fillStyle = rgb(COLOR.cream);
  ctx.font = `700 ${Math.round(r * 0.95)}px "Segoe UI", Arial, sans-serif`;
  ctx.textAlign = "center"; ctx.textBaseline = "middle";
  ctx.fillText((name.trim()[0] || "?").toUpperCase(), x, y + 1);
}

function fitText(ctx, text, font, fallbackFont, color, x, y, maxWidth) {
  ctx.font = font;
  if (ctx.measureText(text).width > maxWidth) ctx.font = fallbackFont;
  let t = text;
  while (t.length > 1 && ctx.measureText(t + "…").width > maxWidth) t = t.slice(0, -1);
  if (t !== text) t += "…";
  ctx.fillStyle = color; ctx.textAlign = "center"; ctx.textBaseline = "middle";
  ctx.fillText(t, x, y);
}

function drawPill(ctx, text, x, y, bg) {
  const textColor = luminance(bg) < 150 ? rgb(COLOR.cream) : rgb(COLOR.ink);
  ctx.font = "600 14px 'Segoe UI', Arial, sans-serif";
  const w = ctx.measureText(text).width;
  const rectW = w + 28, rectH = 26;
  roundRect(ctx, x - rectW / 2, y - rectH / 2, rectW, rectH, rectH / 2);
  ctx.fillStyle = rgb(bg); ctx.fill();
  ctx.fillStyle = textColor; ctx.textAlign = "center"; ctx.textBaseline = "middle";
  ctx.fillText(text, x, y + 1);
}

function drawProgressBar(ctx, x, y, w, h, ratio, color) {
  ratio = Math.max(0, Math.min(1, ratio));
  roundRect(ctx, x, y, w, h, h / 2); ctx.fillStyle = rgb(darken(COLOR.creamDim, 0.25)); ctx.fill();
  if (ratio > 0) {
    const fw = Math.max(h, w * ratio);
    roundRect(ctx, x, y, fw, h, h / 2); ctx.fillStyle = rgb(color); ctx.fill();
  }
  roundRect(ctx, x, y, w, h, h / 2); ctx.lineWidth = 1; ctx.strokeStyle = rgb(darken(COLOR.creamDim, 0.45)); ctx.stroke();
}

function roundRect(ctx, x, y, w, h, r) {
  r = Math.min(r, w / 2, h / 2);
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

const CARD_W = 172, CARD_H_MAX = 452, CARD_H_MIN = 340, CARD_GAP = 10, CARD_TOP = 32, CARD_BOTTOM = 24, SCROLLBAR_RESERVE = 16;

function layoutCards(n, wrapWidth, wrapHeight) {
  // La altura de las tarjetas se adapta al espacio libre (celular en vertical, ventana baja...).
  const cardH = Math.max(CARD_H_MIN, Math.min(CARD_H_MAX, wrapHeight - CARD_TOP - CARD_BOTTOM));
  const totalW = Math.max(wrapWidth, n * (CARD_W + CARD_GAP) + CARD_GAP);
  const rects = [];
  const startX = totalW > wrapWidth ? CARD_GAP : (wrapWidth - (n * (CARD_W + CARD_GAP) - CARD_GAP)) / 2;
  for (let i = 0; i < n; i++) {
    rects.push({ x: startX + i * (CARD_W + CARD_GAP), y: CARD_TOP, w: CARD_W, h: cardH });
  }
  return { rects, totalW, totalH: CARD_TOP + cardH + CARD_BOTTOM };
}

function drawPlayerCard(ctx, rect, p, opts) {
  const { x, y, w, h } = rect;
  const cx = x + w / 2;
  const alpha = p.connected === false ? 0.65 : 1;
  const pad = 12;

  ctx.save();
  ctx.globalAlpha = alpha;
  ctx.shadowColor = "rgba(0,0,0,0.35)"; ctx.shadowBlur = 8; ctx.shadowOffsetY = 5;
  roundRect(ctx, x, y, w, h, 16); ctx.fillStyle = rgb(COLOR.cream); ctx.fill();
  ctx.shadowColor = "transparent"; ctx.shadowBlur = 0; ctx.shadowOffsetY = 0;
  roundRect(ctx, x + 3, y + 3, w - 6, h - 6, 13); ctx.lineWidth = 1; ctx.strokeStyle = rgb(COLOR.creamDim); ctx.stroke();

  drawAvatar(ctx, p.name, cx, y + pad + 24, 24);
  if (opts.isMe) { ctx.beginPath(); ctx.arc(cx, y + pad + 24, 27, 0, Math.PI * 2); ctx.lineWidth = 2; ctx.strokeStyle = rgb(COLOR.gold); ctx.stroke(); }

  fitText(ctx, p.name, "700 20px 'Segoe UI', Arial, sans-serif", "600 15px 'Segoe UI', Arial, sans-serif",
         rgb(p.connected === false ? COLOR.inkSoft : COLOR.ink), cx, y + pad + 62, w - 2 * pad);

  const tagY = y + pad + 84;
  if (p.connected === false) {
    ctx.font = "15px 'Segoe UI', Arial, sans-serif"; ctx.fillStyle = rgb(COLOR.inkSoft);
    ctx.textAlign = "center"; ctx.fillText("Desconectado", cx, tagY);
  } else if (opts.isMe) {
    ctx.font = "15px 'Segoe UI', Arial, sans-serif"; ctx.fillStyle = rgb(darken(COLOR.gold, 0.35));
    ctx.textAlign = "center"; ctx.fillText("Tú", cx, tagY);
  }

  ctx.font = "700 38px 'Segoe UI', Arial, sans-serif"; ctx.fillStyle = rgb(p.connected === false ? COLOR.inkSoft : COLOR.ink);
  ctx.textAlign = "center"; ctx.textBaseline = "middle";
  ctx.fillText(String(p.score), cx, y + pad + 118);
  ctx.font = "15px 'Segoe UI', Arial, sans-serif"; ctx.fillStyle = rgb(COLOR.inkSoft);
  ctx.fillText("puntos", cx, y + pad + 144);

  const st = STATUS_STYLE[p.status] || { bg: [150, 150, 150], label: p.status };
  drawPill(ctx, st.label, cx, y + pad + 172, st.bg);
  if (p.wins !== undefined && p.wins !== null) {
    ctx.font = "15px 'Segoe UI', Arial, sans-serif"; ctx.fillStyle = rgb(COLOR.inkSoft);
    ctx.textAlign = "center";
    ctx.fillText(`★ ${p.wins} victoria${p.wins !== 1 ? "s" : ""}`, cx, y + pad + 198);
  }

  const barY = y + pad + 220;
  let ratio = Math.min(p.score, 100) / 100, barColor = [60, 140, 90];
  if (p.status === "ME_FUI") { barColor = [176, 48, 48]; ratio = 1; }
  else if (p.status === "SIGLO") barColor = COLOR.gold;
  else if (p.score >= 90) barColor = [196, 130, 40];
  drawProgressBar(ctx, x + pad, barY, w - 2 * pad, 10, ratio, barColor);

  const trayTop = barY + 22;
  const tray = { x: x + pad, y: trayTop, w: w - 2 * pad, h: y + h - pad - trayTop };
  roundRect(ctx, tray.x, tray.y, tray.w, tray.h, 10); ctx.fillStyle = rgb(darken(COLOR.creamDim, 0.12)); ctx.fill();
  if (p.balls && p.balls.length) {
    let radius = p.balls.length <= 12 ? 18 : 15;
    // si la bandeja es baja, las fichas se achican hasta que quepan
    while (radius > 9 && ballRowHeight(p.balls.length, radius, tray.w - 8) > tray.h - 10) radius--;
    drawBallRow(ctx, p.balls, tray.x + tray.w / 2, tray.y + 6, tray.w - 8, radius);
  }

  if (opts.isTurn) {
    const pulse = 2.5 + 1.5 * Math.sin(performance.now() / 220);
    roundRect(ctx, x, y, w, h, 16); ctx.lineWidth = 4 + pulse; ctx.strokeStyle = rgb(COLOR.gold); ctx.stroke();
  } else if (opts.isWinner) {
    roundRect(ctx, x, y, w, h, 16); ctx.lineWidth = 4; ctx.strokeStyle = rgb(COLOR.gold); ctx.stroke();
  }
  ctx.restore();

  if (opts.isTurn) {
    ctx.beginPath(); ctx.moveTo(cx - 12, y - 14); ctx.lineTo(cx + 12, y - 14); ctx.lineTo(cx, y);
    ctx.closePath(); ctx.fillStyle = rgb(COLOR.gold); ctx.fill();
  }
  if (opts.isWinner) {
    drawStar(ctx, cx, y - 16, 14, 5);
  }
}

function drawStar(ctx, cx, cy, r, points) {
  ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2);
  ctx.fillStyle = rgb(COLOR.gold); ctx.fill();
  ctx.lineWidth = 2; ctx.strokeStyle = rgb(darken(COLOR.gold, 0.3)); ctx.stroke();
  ctx.beginPath();
  for (let i = 0; i < points * 2; i++) {
    const ang = Math.PI / 2 + (i * Math.PI) / points;
    const rad = i % 2 === 0 ? r * 0.78 : r * 0.34;
    const px = cx + rad * Math.cos(ang), py = cy - rad * Math.sin(ang);
    i === 0 ? ctx.moveTo(px, py) : ctx.lineTo(px, py);
  }
  ctx.closePath(); ctx.fillStyle = rgb(COLOR.cream); ctx.fill();
}

// ============================================================ conexión

class GameConnection {
  constructor(url, name, handlers) {
    this.handlers = handlers;
    this._closedByUs = false;
    try {
      this.ws = new WebSocket(url);
    } catch (err) {
      handlers.onFailed("No se pudo conectar con el servidor.");
      return;
    }
    this.ws.onopen = () => { this._everOpen = true; this.send({ type: "join", name }); };
    this.ws.onmessage = (ev) => {
      let msg;
      try { msg = JSON.parse(ev.data); } catch (e) { return; }
      handlers.onMessage(msg);
    };
    this.ws.onerror = () => { /* el evento 'close' que sigue trae el detalle */ };
    this.ws.onclose = (ev) => {
      if (this._closedByUs) return;
      // Si nunca llegó a abrirse, no se pudo conectar; si se abrió y luego se cortó, se perdió.
      if (!this._everOpen) handlers.onFailed("No se pudo conectar con el servidor. ¿Está encendido?");
      else handlers.onClosed("Se perdió la conexión con el servidor.");
    };
  }
  send(message) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify(message));
  }
  close() {
    this._closedByUs = true;
    if (this.ws) this.ws.close();
  }
}

function buildWsUrl(serverField) {
  const raw = (serverField || "").trim();
  if (!raw) {
    const scheme = location.protocol === "https:" ? "wss" : "ws";
    return `${scheme}://${location.host}/ws`;
  }
  if (raw.startsWith("ws://") || raw.startsWith("wss://")) return raw;
  return `ws://${raw}/ws`;
}

// ============================================================ estado de la app

const el = (id) => document.getElementById(id);

const screens = { form: el("screen-form"), connecting: el("screen-connecting"), table: el("screen-table") };
const canvas = el("table-canvas");
const ctx = canvas.getContext("2d");

const state = {
  stage: "FORM",       // FORM | CONNECTING | ONLINE
  conn: null,
  myId: null,
  snapshot: null,
  snapshotAt: 0,
  waitingReply: false,
  leaveArmedUntil: 0,
  notice: "",
  noticeUntil: 0,
};

function showScreen(name) {
  Object.entries(screens).forEach(([k, s]) => s.classList.toggle("hidden", k !== name));
}

function myPlayer() { return findPlayer(state.myId); }
function findPlayer(id) {
  if (!state.snapshot) return null;
  return state.snapshot.players.find((p) => p.id === id) || null;
}
function isHost() { return state.snapshot && state.snapshot.host_id === state.myId; }
function isMyTurn() { return state.snapshot && state.snapshot.phase === PHASE_PLAYING && state.snapshot.turn_id === state.myId; }
function canStart() { return isHost() && state.snapshot.players.length >= MIN_PLAYERS; }

function notify(text) {
  state.notice = text;
  state.noticeUntil = performance.now() + NOTICE_SECONDS * 1000;
}

// ------------------------------------------------------------ conectar / salir

function connect(name, serverField) {
  el("form-message").textContent = "";
  showScreen("connecting");
  el("connecting-text").textContent = `Conectando…`;
  state.stage = "CONNECTING";
  state.conn = new GameConnection(buildWsUrl(serverField), name || "Jugador", {
    onMessage: onServerMessage,
    onFailed: backToForm,
    onClosed: backToForm,
  });
}

function backToForm(message) {
  if (state.conn) { state.conn.close(); state.conn = null; }
  state.stage = "FORM";
  state.snapshot = null;
  state.myId = null;
  state.waitingReply = false;
  state.leaveArmedUntil = 0;
  showScreen("form");
  el("form-message").textContent = message || "";
}

function onServerMessage(msg) {
  if (msg.type === "welcome") {
    state.myId = msg.id;
    state.stage = "ONLINE";
    showScreen("table");
  } else if (msg.type === "state") {
    state.snapshot = msg;
    state.snapshotAt = performance.now();
    state.waitingReply = false;
    if (msg.phase !== PHASE_PLAYING) state.leaveArmedUntil = 0;
    render();
  } else if (msg.type === "error") {
    state.waitingReply = false;
    if (state.stage === "ONLINE") notify(msg.message);
    else backToForm(msg.message);
  }
}

function send(message) {
  if (state.conn) { state.conn.send(message); state.waitingReply = true; }
}

function onLeaveClick() {
  const now = performance.now();
  if (state.snapshot && state.snapshot.phase === PHASE_PLAYING && now > state.leaveArmedUntil) {
    state.leaveArmedUntil = now + LEAVE_CONFIRM_SECONDS * 1000;
    render();
    return;
  }
  backToForm("");
}

// ------------------------------------------------------------ formulario

el("form-connect").addEventListener("submit", (ev) => {
  ev.preventDefault();
  const name = el("input-name").value.trim().slice(0, MAX_NAME_LEN) || "Jugador";
  connect(name, el("input-server").value);
});
el("btn-toggle-advanced").addEventListener("click", () => {
  el("advanced").classList.toggle("hidden");
});
el("btn-cancel-connect").addEventListener("click", () => backToForm(""));
el("btn-leave").addEventListener("click", onLeaveClick);
el("btn-start").addEventListener("click", () => { if (canStart() && !state.waitingReply) send({ type: "start" }); });
el("btn-bola").addEventListener("click", () => { if (isMyTurn() && !state.waitingReply) send({ type: "draw" }); });
el("btn-me-quedo").addEventListener("click", () => { if (isMyTurn() && !state.waitingReply) send({ type: "stay" }); });
el("btn-next").addEventListener("click", () => { if (isHost() && !state.waitingReply) send({ type: "start" }); });

// ============================================================ dibujo de la pantalla completa

function resizeCanvas(neededWidth, neededHeight) {
  const dpr = window.devicePixelRatio || 1;
  const w = Math.round(neededWidth * dpr), h = Math.round(neededHeight * dpr);
  // Asignar width/height reasigna el bitmap entero: solo se hace si cambió.
  if (canvas.width !== w) canvas.width = w;
  if (canvas.height !== h) canvas.height = h;
  canvas.style.width = neededWidth + "px";
  canvas.style.height = neededHeight + "px";
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
}

function render() {
  if (state.stage !== "ONLINE" || !state.snapshot) return;
  const snap = state.snapshot;
  const wrap = el("canvas-wrap");
  // getBoundingClientRect incluye las barras de scroll, así que el tamaño medido no
  // cambia según aparezcan o no (clientWidth/Height sí, y eso causaba un bucle).
  const box = wrap.getBoundingClientRect();
  const wrapWidth = Math.floor(box.width) || 320;
  let wrapHeight = Math.floor(box.height) || 560;
  // si hará falta scroll horizontal, se reserva su franja para que no tape las tarjetas
  if (snap.players.length * (CARD_W + CARD_GAP) + CARD_GAP > wrapWidth) wrapHeight -= SCROLLBAR_RESERVE;

  const { rects, totalW, totalH } = layoutCards(snap.players.length, wrapWidth, wrapHeight);
  resizeCanvas(totalW, totalH);
  ctx.clearRect(0, 0, totalW, totalH);

  const winnerIds = new Set(snap.winner_ids || []);
  snap.players.forEach((p, i) => {
    drawPlayerCard(ctx, rects[i], p, {
      isTurn: snap.phase === PHASE_PLAYING && p.id === snap.turn_id,
      isWinner: snap.phase === PHASE_ROUND_END && winnerIds.has(p.id),
      isMe: p.id === state.myId,
    });
  });

  renderChrome();
}

function renderChrome() {
  const snap = state.snapshot;
  const subtitle = el("table-subtitle"), corner = el("table-corner");
  const statusLine = el("status-line"), notice = el("notice");
  const leaveBtn = el("btn-leave");

  if (snap.phase === PHASE_LOBBY) {
    subtitle.textContent = "Sala de espera";
    corner.textContent = `${snap.players.length}/${snap.max_players}`;
  } else {
    subtitle.textContent = "";
    corner.textContent = `Ronda ${snap.round}`;
  }

  el("btn-start").classList.toggle("hidden", snap.phase !== PHASE_LOBBY || !isHost());
  el("btn-start").disabled = !canStart() || state.waitingReply;
  el("btn-bola").classList.toggle("hidden", !(snap.phase === PHASE_PLAYING && isMyTurn()));
  el("btn-me-quedo").classList.toggle("hidden", !(snap.phase === PHASE_PLAYING && isMyTurn()));
  el("btn-bola").disabled = state.waitingReply;
  el("btn-me-quedo").disabled = state.waitingReply;
  el("btn-next").classList.toggle("hidden", !(snap.phase === PHASE_ROUND_END && isHost()));
  el("btn-next").disabled = state.waitingReply;

  const armed = performance.now() < state.leaveArmedUntil;
  leaveBtn.textContent = armed ? "¿SEGURO?" : "SALIR";

  if (snap.phase === PHASE_LOBBY) {
    if (isHost()) {
      statusLine.textContent = canStart() ? "" : `Se necesitan al menos ${MIN_PLAYERS} jugadores`;
    } else {
      const host = findPlayer(snap.host_id);
      statusLine.textContent = `Esperando a que ${host ? host.name : "el anfitrión"} inicie la partida…`;
    }
  } else if (snap.phase === PHASE_PLAYING) {
    let html;
    if (isMyTurn()) html = "¡ES TU TURNO!";
    else { const cur = findPlayer(snap.turn_id); html = `Turno de ${cur ? cur.name : "…"}`; }
    const left = snap.time_left == null ? null
      : Math.max(0, Math.ceil(snap.time_left - (performance.now() - state.snapshotAt) / 1000));
    const full = html + (left == null ? "" : `<span class="timer ${left <= 5 ? "low" : ""}">Tiempo: ${left} s</span>`);
    if (statusLine.innerHTML !== full) statusLine.innerHTML = full;
  } else if (snap.phase === PHASE_ROUND_END) {
    const winnerIds = new Set(snap.winner_ids || []);
    const names = snap.players.filter((p) => winnerIds.has(p.id)).map((p) => p.name);
    statusLine.textContent = names.length ? `Ganador(es): ${names.join(", ")}` : "Todos se pasaron de 100. Sin ganadores.";
    if (!isHost()) {
      const host = findPlayer(snap.host_id);
      statusLine.textContent += ` · Esperando a ${host ? host.name : "el anfitrión"}…`;
    }
  }

  if (state.notice && performance.now() < state.noticeUntil) {
    notice.textContent = state.notice; notice.classList.remove("hidden");
  } else {
    notice.classList.add("hidden");
  }
}

// bucle para el pulso dorado del turno y el conteo del tiempo, sin recalcular el layout
function tick() {
  if (state.stage === "ONLINE" && state.snapshot) {
    if (state.snapshot.phase === PHASE_PLAYING) {
      render();                 // hay pulso dorado y cuenta regresiva
    } else if (state.leaveArmedUntil || state.notice) {
      renderChrome();           // solo textos (aviso, "¿SEGURO?" que caduca)
    }
  }
  requestAnimationFrame(tick);
}
requestAnimationFrame(tick);

window.addEventListener("resize", () => { if (state.stage === "ONLINE") render(); });
window.addEventListener("orientationchange", () => { if (state.stage === "ONLINE") render(); });

// nombre de servidor precargado por query string (?server=host:puerto), para compartir enlaces directos
const params = new URLSearchParams(location.search);
if (params.get("server")) {
  el("input-server").value = params.get("server");
  el("advanced").classList.remove("hidden");
}

// Punto de apoyo para depurar desde la consola del navegador (no afecta el
// juego). window.__siglo.state.snapshot trae la última foto de la mesa.
window.__siglo = { state, isHost, isMyTurn, canStart, findPlayer, buildWsUrl, render };
