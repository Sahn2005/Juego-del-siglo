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

// Ficha de lotería: disco de madera con aro rojo y el número en rojo.
const CHIP = {
  face: [238, 214, 168], edge: [196, 160, 106], edgeDark: [150, 114, 66], red: [200, 50, 38],
};

function drawBall(ctx, value, x, y, r, vira, blank) {
  const t = Math.max(3, Math.round(r * 0.24));   // grosor del disco

  if (vira) {
    ctx.beginPath(); ctx.arc(x, y + t / 2, r + 4, 0, Math.PI * 2);
    ctx.fillStyle = rgb(COLOR.gold); ctx.fill();
    ctx.lineWidth = 1; ctx.strokeStyle = rgb(darken(COLOR.gold, 0.3)); ctx.stroke();
  }

  // Sombra sobre el paño
  ctx.beginPath(); ctx.ellipse(x + 2, y + t + 4, r, r * 0.95, 0, 0, Math.PI * 2);
  ctx.fillStyle = "rgba(0,0,0,0.30)"; ctx.fill();

  // Canto de madera: disco inferior + rectángulo
  ctx.fillStyle = rgb(CHIP.edgeDark);
  ctx.beginPath(); ctx.arc(x, y + t, r, 0, Math.PI * 2); ctx.fill();
  ctx.fillStyle = rgb(CHIP.edge);
  ctx.fillRect(x - r, y, r * 2, t);
  ctx.strokeStyle = rgb(CHIP.edgeDark); ctx.lineWidth = 1;
  ctx.beginPath(); ctx.moveTo(x - r, y); ctx.lineTo(x - r, y + t);
  ctx.moveTo(x + r, y); ctx.lineTo(x + r, y + t); ctx.stroke();

  // Cara de madera
  ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2);
  ctx.fillStyle = rgb(CHIP.face); ctx.fill();
  if (blank) {
    ctx.strokeStyle = rgb(CHIP.edge); ctx.stroke();
    ctx.beginPath(); ctx.arc(x, y, r * 0.7, 0, Math.PI * 2);
    ctx.strokeStyle = rgb(darken(CHIP.face, 0.06)); ctx.stroke();
    return;
  }

  // Aro rojo y centro claro
  ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2);
  ctx.fillStyle = rgb(CHIP.red); ctx.fill();
  ctx.strokeStyle = rgb(darken(CHIP.red, 0.25)); ctx.stroke();
  ctx.beginPath(); ctx.arc(x, y, r * 0.76, 0, Math.PI * 2);
  ctx.fillStyle = rgb(CHIP.face); ctx.fill();

  // Número con serifa, como en las fichas reales
  ctx.fillStyle = rgb(CHIP.red);
  ctx.font = `700 ${Math.round(r * (value < 100 ? 0.95 : 0.8))}px Georgia, "Times New Roman", serif`;
  ctx.textAlign = "center"; ctx.textBaseline = "middle";
  ctx.fillText(String(value), x, y + 1);

  // Reflejo suave
  const grad = ctx.createRadialGradient(x - r * 0.3, y - r * 0.4, 1, x - r * 0.3, y - r * 0.4, r * 0.9);
  grad.addColorStop(0, "rgba(255,255,255,0.35)");
  grad.addColorStop(1, "rgba(255,255,255,0)");
  ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fillStyle = grad; ctx.fill();
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
  const pad = 12;
  const hidden = !!p.hidden;

  // ── Oponente en partida: no se dibuja nada ───────────────────────────
  if (hidden) return;

  ctx.save();

  // ── Fondo de la tarjeta ──────────────────────────────────────────────
  ctx.globalAlpha = p.connected === false ? 0.65 : 1;
  ctx.shadowColor = "rgba(0,0,0,0.35)"; ctx.shadowBlur = 8; ctx.shadowOffsetY = 5;
  roundRect(ctx, x, y, w, h, 16); ctx.fillStyle = rgb(COLOR.cream); ctx.fill();
  ctx.shadowColor = "transparent"; ctx.shadowBlur = 0; ctx.shadowOffsetY = 0;
  roundRect(ctx, x + 3, y + 3, w - 6, h - 6, 13); ctx.lineWidth = 1; ctx.strokeStyle = rgb(COLOR.creamDim); ctx.stroke();

  // ── Tarjeta normal (mi jugador, desconectado, o fin de ronda) ────────
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
  const ratio = Math.min(p.score, 100) / 100;
  let barColor = [60, 140, 90];
  if (p.status === "ME_FUI") { barColor = [176, 48, 48]; }
  else if (p.status === "SIGLO") barColor = COLOR.gold;
  else if (p.score >= 90) barColor = [196, 130, 40];
  drawProgressBar(ctx, x + pad, barY, w - 2 * pad, 10, ratio, barColor);

  const trayTop = barY + 22;
  const tray = { x: x + pad, y: trayTop, w: w - 2 * pad, h: y + h - pad - trayTop };
  roundRect(ctx, tray.x, tray.y, tray.w, tray.h, 10); ctx.fillStyle = rgb(darken(COLOR.creamDim, 0.12)); ctx.fill();
  if (p.balls && p.balls.length) {
    let radius = p.balls.length <= 4 ? 30 : p.balls.length <= 8 ? 24 : p.balls.length <= 12 ? 19 : 15;
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

function buildWsUrl() {
  const scheme = location.protocol === "https:" ? "wss" : "ws";
  return `${scheme}://${location.host}/ws`;
}

// ============================================================ estado de la app

const el = (id) => document.getElementById(id);

const screens = {
  form: el("screen-form"),
  account: el("screen-account"),
  connecting: el("screen-connecting"),
  table: el("screen-table"),
};
const MUSIC_KEY = "siglo-music-enabled";
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
  modalShownForRound: -1,
  account: null,
  authMode: "login",
  lastStatusEventId: 0,
  musicEnabled: loadMusicPreference(),
};

const MUSIC_TRACKS = {
  ambient: {
    melody: [523.25, 659.25, 783.99, 659.25, 587.33, 523.25, 392, null,
      440, 587.33, 698.46, 587.33, 523.25, 440, 392, null],
    chords: [[130.81, 164.81, 196], [110, 130.81, 164.81],
      [87.31, 110, 130.81], [98, 123.47, 146.83]],
    interval: 650,
  },
  arcade: {
    melody: [392, null, 523.25, 659.25, null, 587.33, 523.25, null,
      698.46, 659.25, 523.25, null, 440, 523.25, 587.33, 659.25,
      null, 783.99, 698.46, 659.25, 523.25, null, 587.33, 659.25,
      440, null, 523.25, 392, null, 440, 587.33, 523.25],
    bass: [130.81, 164.81, 146.83, 196, 110, 146.83, 130.81, 164.81],
    interval: 190,
  },
};
let musicContext = null;
let musicMaster = null;
let musicBuses = null;
let musicTimer = null;
let musicStep = 0;
let musicMode = "ambient";

function loadMusicPreference() {
  try {
    return localStorage.getItem(MUSIC_KEY) !== "false";
  } catch (error) {
    console.warn("No se pudo leer la preferencia de música.", error);
    return true;
  }
}

function updateMusicButton() {
  const button = el("btn-music");
  const trackName = musicMode === "arcade" ? "Arcade" : "Ambiental";
  const label = state.musicEnabled ? `♫ ${trackName}` : "♫ Música: apagada";
  const action = state.musicEnabled ? `Silenciar música ${trackName.toLowerCase()}` : "Activar música";
  button.textContent = label;
  button.title = action;
  button.setAttribute("aria-label", action);
  button.setAttribute("aria-pressed", String(state.musicEnabled));
}

function playMusicTone(frequency, duration, volume, waveform) {
  const now = musicContext.currentTime;
  const oscillator = musicContext.createOscillator();
  const envelope = musicContext.createGain();
  oscillator.type = waveform;
  oscillator.frequency.value = frequency;
  envelope.gain.setValueAtTime(0.0001, now);
  envelope.gain.exponentialRampToValueAtTime(volume, now + 0.06);
  envelope.gain.exponentialRampToValueAtTime(0.0001, now + duration);
  oscillator.connect(envelope);
  envelope.connect(musicBuses[musicMode]);
  oscillator.start(now);
  oscillator.stop(now + duration + 0.02);
}

function playMusicStep() {
  musicTimer = null;
  if (!state.musicEnabled || !musicContext || musicContext.state !== "running") return;
  const track = MUSIC_TRACKS[musicMode];
  const note = track.melody[musicStep % track.melody.length];
  if (musicMode === "ambient") {
    if (note) playMusicTone(note, 0.55, 0.035, "sine");
    if (musicStep % 8 === 0) {
      const chord = track.chords[Math.floor(musicStep / 8) % track.chords.length];
      chord.forEach((frequency) => playMusicTone(frequency, 4.8, 0.009, "sine"));
    }
  } else {
    if (note) playMusicTone(note, 0.15, 0.012, "square");
    if (musicStep % 4 === 0) {
      const bass = track.bass[Math.floor(musicStep / 4) % track.bass.length];
      playMusicTone(bass, 0.48, 0.016, "triangle");
    }
  }
  musicStep += 1;
  musicTimer = window.setTimeout(playMusicStep, track.interval);
}

function syncMusicMode() {
  const nextMode = state.snapshot && state.snapshot.phase === PHASE_PLAYING ? "arcade" : "ambient";
  if (nextMode === musicMode) return;
  musicMode = nextMode;
  musicStep = 0;
  updateMusicButton();
  if (musicContext && musicBuses) {
    Object.entries(musicBuses).forEach(([name, bus]) => {
      bus.gain.cancelScheduledValues(musicContext.currentTime);
      bus.gain.setTargetAtTime(name === musicMode && state.musicEnabled ? 1 : 0,
        musicContext.currentTime, 0.12);
    });
    if (state.musicEnabled && musicContext.state === "running") {
      if (musicTimer !== null) window.clearTimeout(musicTimer);
      musicTimer = null;
      playMusicStep();
    }
  }
}

function announceSiglo() {
  if (!("speechSynthesis" in window) || !("SpeechSynthesisUtterance" in window)) {
    console.warn("Este navegador no admite el anuncio de voz de SIGLO.");
    return;
  }

  const announcement = new SpeechSynthesisUtterance("¡SIGLO!");
  announcement.lang = "es-CO";
  announcement.pitch = 1.6;
  announcement.rate = 1.15;
  announcement.volume = 1;

  const spanishVoice = window.speechSynthesis.getVoices().find((voice) =>
    voice.lang.toLowerCase().startsWith("es-co"));
  if (spanishVoice) announcement.voice = spanishVoice;

  let restoreMusicTimer = null;
  const restoreMusic = () => {
    if (restoreMusicTimer !== null) window.clearTimeout(restoreMusicTimer);
    if (musicBuses) {
      Object.entries(musicBuses).forEach(([name, bus]) => {
        bus.gain.cancelScheduledValues(musicContext.currentTime);
        bus.gain.setTargetAtTime(
          state.musicEnabled && name === musicMode ? 1 : 0,
          musicContext.currentTime,
          0.2,
        );
      });
    }
  };

  if (musicContext && musicBuses && state.musicEnabled) {
    Object.values(musicBuses).forEach((bus) => {
      bus.gain.cancelScheduledValues(musicContext.currentTime);
      bus.gain.setTargetAtTime(0.2, musicContext.currentTime, 0.08);
    });
    restoreMusicTimer = window.setTimeout(restoreMusic, 2600);
  }
  announcement.onend = restoreMusic;
  announcement.onerror = (event) => {
    restoreMusic();
    console.error("No se pudo reproducir el anuncio de SIGLO.", event.error);
  };
  window.speechSynthesis.speak(announcement);
}

async function startMusic() {
  if (!state.musicEnabled || musicTimer !== null) return;
  try {
    const AudioContext = window.AudioContext || window.webkitAudioContext;
    if (!AudioContext) throw new Error("Este navegador no admite Web Audio.");
    if (!musicContext) {
      musicContext = new AudioContext();
      musicMaster = musicContext.createGain();
      musicMaster.gain.value = 0;
      musicMaster.connect(musicContext.destination);
      musicBuses = Object.fromEntries(Object.keys(MUSIC_TRACKS).map((name) => {
        const bus = musicContext.createGain();
        bus.gain.value = name === musicMode ? 1 : 0;
        bus.connect(musicMaster);
        return [name, bus];
      }));
    }
    await musicContext.resume();
    if (state.musicEnabled) {
      Object.entries(musicBuses).forEach(([name, bus]) => {
        bus.gain.cancelScheduledValues(musicContext.currentTime);
        bus.gain.setTargetAtTime(name === musicMode ? 1 : 0, musicContext.currentTime, 0.12);
      });
      musicMaster.gain.cancelScheduledValues(musicContext.currentTime);
      musicMaster.gain.setTargetAtTime(0.8, musicContext.currentTime, 0.12);
      syncMusicMode();
      if (musicTimer === null) playMusicStep();
    }
  } catch (error) {
    state.musicEnabled = false;
    updateMusicButton();
    console.error("No se pudo iniciar la música.", error);
  }
}

function stopMusic() {
  if (musicTimer !== null) {
    window.clearTimeout(musicTimer);
    musicTimer = null;
  }
  musicStep = 0;
  if (musicContext && musicBuses) {
    Object.values(musicBuses).forEach((bus) => {
      bus.gain.cancelScheduledValues(musicContext.currentTime);
      bus.gain.setTargetAtTime(0, musicContext.currentTime, 0.04);
    });
  }
  if (musicContext && musicMaster) {
    musicMaster.gain.cancelScheduledValues(musicContext.currentTime);
    musicMaster.gain.setTargetAtTime(0, musicContext.currentTime, 0.04);
  }
}

el("btn-music").addEventListener("click", () => {
  state.musicEnabled = !state.musicEnabled;
  try {
    localStorage.setItem(MUSIC_KEY, String(state.musicEnabled));
  } catch (error) {
    console.warn("No se pudo guardar la preferencia de música.", error);
  }
  updateMusicButton();
  if (state.musicEnabled) startMusic();
  else stopMusic();
});
document.addEventListener("pointerdown", startMusic, { once: true });
document.addEventListener("keydown", startMusic, { once: true });
document.addEventListener("visibilitychange", () => {
  if (!document.hidden && state.musicEnabled) startMusic();
});
updateMusicButton();

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
function shouldShowTurnTimer() {
  if (!isHost()) return true;
  const host = myPlayer();
  return !host || host.status === "PLAYING";
}
// Con 3+ jugadores el anfitrión reparte (REPARTIR); con 2, cada quien se sirve (BOLA).
function hostDeals() { return !!(state.snapshot && state.snapshot.host_deals); }
function canDeal() {
  if (!hostDeals()) return isMyTurn();
  if (!isHost()) return false;
  return isMyTurn() || state.snapshot.draw_request?.player_id === state.snapshot.turn_id;
}

function notify(text) {
  state.notice = text;
  state.noticeUntil = performance.now() + NOTICE_SECONDS * 1000;
}

// ------------------------------------------------------------ conectar / salir

function connect(name) {
  el("form-message").textContent = "";
  showScreen("connecting");
  el("connecting-text").textContent = `Conectando…`;
  state.stage = "CONNECTING";
  state.conn = new GameConnection(buildWsUrl(), name || "Jugador", {
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
  if (window.Mesa3D) Mesa3D.reset();
  syncMusicMode();
  state.waitingReply = false;
  state.leaveArmedUntil = 0;
  if (state.account) {
    showScreen("account");
    refreshAccountView().catch((err) => { el("history-message").textContent = err.message; });
    el("history-message").textContent = message || "";
  } else {
    showScreen("form");
    el("form-message").textContent = message || "";
  }
}

function onServerMessage(msg) {
  if (msg.type === "welcome") {
    state.myId = msg.id;
    state.stage = "ONLINE";
    showScreen("table");
    let saved = null;
    try { saved = localStorage.getItem("siglo-vista"); } catch (e) { /* sin almacenamiento */ }
    if (saved === "3d" && !state.view3d) setView3d(true);
  } else if (msg.type === "state") {
    showStatusAnimation(msg.last_action);
    state.snapshot = msg;
    syncMusicMode();
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

function showStatusAnimation(action) {
  if (!action || action.event_id <= state.lastStatusEventId) return;
  state.lastStatusEventId = action.event_id;
  if (action.status === "SIGLO") announceSiglo();
  const presentations = {
    ME_QUEDO: { text: `${action.name} — ¡ME QUEDO!`, className: "me-quedo" },
    ME_FUI: { text: `${action.name} — ¡ME FUI!`, className: "me-fui" },
    SIGLO: { text: `${action.name} — ¡SIGLO!`, className: "siglo" },
  };
  const presentation = presentations[action.status];
  if (!presentation) return;

  const animation = el("status-animation");
  animation.textContent = presentation.text;
  animation.className = `status-animation ${presentation.className}`;
  void animation.offsetWidth;
  animation.classList.add("play");
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

async function apiRequest(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  const responseText = await response.text();
  let body = {};
  try { body = JSON.parse(responseText); } catch (_) { body.message = responseText; }
  if (!response.ok) {
    throw new Error(body.message || body.error || "No se pudo completar la solicitud.");
  }
  return body;
}

function setAuthMode(mode) {
  state.authMode = mode;
  const registering = mode === "register";
  el("auth-title").textContent = registering ? "Crear cuenta" : "Inicia sesión";
  el("btn-auth-submit").textContent = registering ? "REGISTRARME" : "INICIAR SESIÓN";
  el("btn-auth-toggle").textContent = registering ? "Ya tengo una cuenta" : "Crear una cuenta";
  el("auth-password").autocomplete = registering ? "new-password" : "current-password";
  el("auth-message").textContent = registering
    ? "Usuario: 3–10 letras, números o guion bajo. Contraseña: mínimo 8 caracteres."
    : "";
}

async function refreshAccountView() {
  const data = await apiRequest("/api/history");
  state.account = data.account;
  el("account-name").textContent = data.account.username;
  el("stat-played").textContent = data.stats.played;
  el("stat-wins").textContent = data.stats.wins;
  el("stat-losses").textContent = data.stats.losses;
  const list = el("history-list");
  list.replaceChildren();
  if (!data.games.length) {
    const empty = document.createElement("li");
    empty.textContent = "Aún no has terminado partidas. ¡Juega tu primera ronda!";
    list.appendChild(empty);
    return;
  }
  data.games.forEach((game) => {
    const item = document.createElement("li");
    const result = document.createElement("span");
    result.className = `history-result ${game.result === "Victoria" ? "win" : "loss"}`;
    result.textContent = `${game.result} · Ronda ${game.round}`;
    const detail = document.createElement("span");
    detail.className = "history-detail";
    const date = new Date(game.played_at * 1000).toLocaleString();
    const opponents = game.opponents.length ? ` contra ${game.opponents.join(", ")}` : "";
    detail.textContent = `${date} · Puntaje ${game.score} · Estado: ${game.status}${opponents}`;
    item.append(result, detail);
    list.appendChild(item);
  });
}

el("form-auth").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const message = el("auth-message");
  message.textContent = "";
  const payload = {
    username: el("auth-username").value.trim(),
    password: el("auth-password").value,
  };
  try {
    const endpoint = state.authMode === "register" ? "/api/register" : "/api/login";
    const data = await apiRequest(endpoint, { method: "POST", body: JSON.stringify(payload) });
    state.account = data.account;
    await refreshAccountView();
    showScreen("account");
  } catch (err) {
    message.textContent = err.message;
  }
});
el("btn-auth-toggle").addEventListener("click", () => {
  setAuthMode(state.authMode === "login" ? "register" : "login");
});
el("btn-guest-toggle").addEventListener("click", () => {
  el("guest-panel").classList.toggle("hidden");
  if (!el("guest-panel").classList.contains("hidden")) el("input-name").focus();
});
el("btn-account-play").addEventListener("click", () => {
  if (state.account) connect(state.account.username);
});
el("btn-account-logout").addEventListener("click", async () => {
  try {
    await apiRequest("/api/logout", { method: "POST", body: "{}" });
    state.account = null;
    el("auth-password").value = "";
    showScreen("form");
  } catch (err) {
    el("history-message").textContent = err.message;
  }
});
el("btn-how-to-play").addEventListener("click", () => {
  el("how-to-play-modal").classList.remove("hidden");
  el("btn-close-how-to-play").focus();
});
el("btn-close-how-to-play").addEventListener("click", () => {
  el("how-to-play-modal").classList.add("hidden");
  el("btn-how-to-play").focus();
});
el("how-to-play-modal").addEventListener("click", (event) => {
  if (event.target === el("how-to-play-modal")) {
    el("how-to-play-modal").classList.add("hidden");
    el("btn-how-to-play").focus();
  }
});
document.addEventListener("keydown", (event) => {
  const modal = el("how-to-play-modal");
  if (event.key === "Escape" && !modal.classList.contains("hidden")) {
    modal.classList.add("hidden");
    el("btn-how-to-play").focus();
  }
});

el("form-connect").addEventListener("submit", (ev) => {
  ev.preventDefault();
  const name = el("input-name").value.trim().slice(0, MAX_NAME_LEN) || "Jugador";
  connect(name);
});
el("btn-cancel-connect").addEventListener("click", () => backToForm(""));
el("btn-leave").addEventListener("click", onLeaveClick);
el("btn-start").addEventListener("click", () => { if (canStart() && !state.waitingReply) send({ type: "start" }); });
el("btn-repartir").addEventListener("click", () => {
  if (state.waitingReply) return;
  if (hostDeals() && !isHost() && isMyTurn()) send({ type: "request_draw" });
  else if (canDeal()) send({ type: "draw" });
});
el("btn-me-quedo").addEventListener("click", () => { if (isMyTurn() && !state.waitingReply) send({ type: "stay" }); });
el("btn-next").addEventListener("click", () => { if (isHost() && !state.waitingReply) send({ type: "start" }); });
el("btn-close-modal").addEventListener("click", () => { el("results-modal").classList.add("hidden"); });

// ============================================================ dibujo de la pantalla completa

function resizeCanvas(neededWidth, neededHeight, fit = 1) {
  const dpr = window.devicePixelRatio || 1;
  const w = Math.round(neededWidth * dpr), h = Math.round(neededHeight * dpr);
  // Asignar width/height reasigna el bitmap entero: solo se hace si cambió.
  if (canvas.width !== w) canvas.width = w;
  if (canvas.height !== h) canvas.height = h;
  // fit < 1: pantalla muy baja (celular en horizontal): se dibuja igual pero se muestra reducido.
  canvas.style.width = Math.floor(neededWidth * fit) + "px";
  canvas.style.height = Math.floor(neededHeight * fit) + "px";
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
}

// ------------------------------------------------------------ vista 2D / 3D

state.view3d = false;
function setView3d(on) {
  if (on && !(window.Mesa3D && Mesa3D.available() && Mesa3D.init(el("three-wrap")))) {
    notify("Tu navegador no puede mostrar la vista 3D.");
    on = false;
  }
  state.view3d = on;
  state.built3d = null;
  try { localStorage.setItem("siglo-vista", on ? "3d" : "2d"); } catch (e) { /* sin almacenamiento */ }
  el("three-wrap").classList.toggle("hidden", !on);
  el("canvas-wrap").classList.toggle("hidden", on);
  el("btn-view").textContent = on ? "VISTA 2D" : "VISTA 3D";
  document.body.classList.toggle("view3d", on);
  if (on) { Mesa3D.start(); Mesa3D.resize(); } else if (window.Mesa3D) Mesa3D.stop();
  if (state.snapshot) render();
}
el("btn-view").addEventListener("click", () => setView3d(!state.view3d));
if (window.Mesa3D) Mesa3D.setAvatarColor((name) => rgb(AVATAR_COLORS[hashName(name) % AVATAR_COLORS.length]));
window.addEventListener("resize", () => { if (state.view3d) Mesa3D.resize(); });

function render() {
  if (state.stage !== "ONLINE" || !state.snapshot) return;
  const snap = state.snapshot;
  if (state.view3d) {
    if (state.built3d !== snap) { Mesa3D.update(snap, state.myId); state.built3d = snap; }
    renderChrome();
    return;
  }
  const wrap = el("canvas-wrap");
  // getBoundingClientRect incluye las barras de scroll, así que el tamaño medido no
  // cambia según aparezcan o no (clientWidth/Height sí, y eso causaba un bucle).
  const box = wrap.getBoundingClientRect();
  const wrapWidth = Math.floor(box.width) || 320;
  let wrapHeight = Math.floor(box.height) || 560;
  // Solo mostramos la tarjeta del propio jugador en la mesa (los oponentes nunca se renderizan aquí)
  const visiblePlayers = snap.players.filter(p => p.id === state.myId);
  // si hará falta scroll horizontal, se reserva su franja para que no tape las tarjetas
  if (visiblePlayers.length * (CARD_W + CARD_GAP) + CARD_GAP > wrapWidth) wrapHeight -= SCROLLBAR_RESERVE;

  const { rects, totalW, totalH } = layoutCards(visiblePlayers.length, wrapWidth, wrapHeight);
  const fit = Math.max(0.4, Math.min(1, (wrapHeight - 2) / totalH));
  resizeCanvas(totalW, totalH, fit);
  ctx.clearRect(0, 0, totalW, totalH);

  const winnerIds = new Set(snap.winner_ids || []);
  visiblePlayers.forEach((p, i) => {
    drawPlayerCard(ctx, rects[i], p, {
      isTurn: snap.phase === PHASE_PLAYING && p.id === snap.turn_id,
      isWinner: snap.phase === PHASE_ROUND_END && winnerIds.has(p.id),
      isMe: p.id === state.myId,
    });
  });

  renderChrome();
}

function opponentActivity(snap, player) {
  const lastAction = snap.last_action;
  if (snap.draw_request && snap.draw_request.player_id === player.id) return { text: "Pide una bola", active: true };
  if (snap.phase === PHASE_PLAYING && snap.turn_id === player.id) return { text: "Está jugando", active: true };
  if (lastAction && lastAction.name === player.name) {
    const labels = { ME_QUEDO: "Se quedó", ME_FUI: "Se pasó", SIGLO: "¡SIGLO!" };
    return { text: labels[lastAction.status] || "Jugó", active: false };
  }
  if (snap.phase === PHASE_ROUND_END) return { text: "Ronda terminada", active: false };
  return { text: snap.phase === PHASE_PLAYING ? "Esperando su turno" : "Esperando la partida", active: false };
}

// Un recuadro por cada oponente conectado (con 2 jugadores hay uno; con 3 o más, varios).
function renderOpponentPanel(snap) {
  const panel = el("opponent-panel");
  const opponents = snap.players.filter((player) =>
    player.id !== state.myId && player.connected !== false);
  if (!opponents.length) {
    panel.classList.add("hidden");
    panel.textContent = "";
    return;
  }
  panel.classList.toggle("multi", opponents.length > 1);
  panel.dataset.count = String(opponents.length);

  // Se reutilizan los recuadros existentes para no recrear el DOM en cada actualización.
  while (panel.children.length > opponents.length) panel.lastChild.remove();
  while (panel.children.length < opponents.length) {
    const card = document.createElement("div");
    card.className = "opponent-card";
    card.innerHTML = '<span class="opponent-panel-label">OPONENTE</span>' +
      '<div class="opponent-avatar" aria-hidden="true"></div>' +
      '<strong class="opponent-name"></strong><span class="opponent-activity"></span>';
    panel.appendChild(card);
  }
  opponents.forEach((player, i) => {
    const card = panel.children[i];
    const { text, active } = opponentActivity(snap, player);
    const avatar = card.querySelector(".opponent-avatar");
    const initials = player.name.trim().split(/\s+/).slice(0, 2).map((part) => part[0]).join("");
    if (avatar.textContent !== initials) avatar.textContent = initials;
    avatar.style.backgroundColor = rgb(AVATAR_COLORS[hashName(player.name) % AVATAR_COLORS.length]);
    const name = card.querySelector(".opponent-name");
    if (name.textContent !== player.name) name.textContent = player.name;
    const act = card.querySelector(".opponent-activity");
    if (act.textContent !== text) act.textContent = text;
    card.classList.toggle("is-active", active);
  });
  panel.classList.remove("hidden");
}

function renderChrome() {
  const snap = state.snapshot;
  const subtitle = el("table-subtitle"), corner = el("table-corner");
  const statusLine = el("status-line"), notice = el("notice");
  const lastActionLine = el("last-action-line");
  const drawRequestLine = el("draw-request-line");
  const leaveBtn = el("btn-leave");

  renderOpponentPanel(snap);
  if (snap.last_action) {
    const labels = { ME_QUEDO: "Me quedo" };
    const status = labels[snap.last_action.status] || snap.last_action.status;
    lastActionLine.textContent = `${snap.last_action.name} — Estado: ${status}`;
  } else {
    lastActionLine.textContent = "";
  }
  if (snap.draw_request) {
    const { name, player_id: playerId } = snap.draw_request;
    if (isHost()) {
      drawRequestLine.textContent = `${name} pide una bola. Presiona REPARTIR para entregársela.`;
    } else if (playerId === state.myId) {
      drawRequestLine.textContent = `Solicitud enviada al anfitrión: ${name} pide una bola.`;
    } else {
      drawRequestLine.textContent = `${name} pidió una bola al anfitrión.`;
    }
  } else {
    drawRequestLine.textContent = "";
  }

  if (snap.phase === PHASE_LOBBY) {
    subtitle.textContent = "Sala de espera";
    corner.textContent = `${snap.players.length}/${snap.max_players}`;
  } else {
    subtitle.textContent = "";
    corner.textContent = `Ronda ${snap.round}`;
  }

  el("btn-start").classList.toggle("hidden", snap.phase !== PHASE_LOBBY || !isHost());
  el("btn-start").disabled = !canStart() || state.waitingReply;
  const shouldRequestDraw = hostDeals() && !isHost() && isMyTurn();
  const hasPendingRequest = !!snap.draw_request;
  el("btn-repartir").textContent = hostDeals()
    ? (isHost() ? "REPARTIR" : "PEDIR BOLA")
    : "BOLA";
  el("btn-repartir").classList.toggle(
    "hidden",
    !(snap.phase === PHASE_PLAYING && (canDeal() || (shouldRequestDraw && !hasPendingRequest)))
  );
  el("btn-me-quedo").classList.toggle("hidden", !(snap.phase === PHASE_PLAYING && isMyTurn()));
  el("btn-repartir").disabled = state.waitingReply || (shouldRequestDraw && hasPendingRequest);
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
    const left = snap.time_left == null || !shouldShowTurnTimer() ? null
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
    
    // Show results modal
    if (state.modalShownForRound !== snap.round) {
      const modal = el("results-modal");
      const resultsList = el("results-list");
      resultsList.innerHTML = "";
      
      // Sort players by score (closest to 100 without going over, then others)
      const sortedPlayers = [...snap.players].sort((a, b) => {
        const aValid = a.score <= 100 ? a.score : -1;
        const bValid = b.score <= 100 ? b.score : -1;
        if (aValid !== bValid) return bValid - aValid;
        return (b.score || 0) - (a.score || 0); // Both over 100 or disconnected
      });
      
      sortedPlayers.forEach(p => {
        const li = document.createElement("li");
        const nameSpan = document.createElement("span");
        nameSpan.textContent = p.name + (winnerIds.has(p.id) ? " 👑" : "");
        if (winnerIds.has(p.id)) nameSpan.style.fontWeight = "bold";
        
        const scoreSpan = document.createElement("span");
        if (p.connected === false) {
          scoreSpan.textContent = "Desconectado";
        } else if (p.score > 100) {
          scoreSpan.textContent = p.score + " (Se pasó)";
          scoreSpan.style.color = "var(--red)";
        } else if (p.score === 100 || p.score === 99) {
          scoreSpan.textContent = p.score + " (SIGLO)";
          scoreSpan.style.color = "var(--gold-dim)";
          scoreSpan.style.fontWeight = "bold";
        } else {
          scoreSpan.textContent = p.score;
        }
        
        li.appendChild(nameSpan);
        li.appendChild(scoreSpan);
        resultsList.appendChild(li);
      });
      
      modal.classList.remove("hidden");
      state.modalShownForRound = snap.round;
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

apiRequest("/api/me")
  .then(async (data) => {
    state.account = data.account;
    await refreshAccountView();
    showScreen("account");
  })
  .catch((err) => {
    if (err.message !== "Inicia sesión para continuar.") {
      el("auth-message").textContent = err.message;
    }
  });

// Punto de apoyo para depurar desde la consola del navegador (no afecta el
// juego). window.__siglo.state.snapshot trae la última foto de la mesa.
window.__siglo = { state, setView3d, isHost, isMyTurn, canStart, hostDeals, canDeal, findPlayer, buildWsUrl, render };
