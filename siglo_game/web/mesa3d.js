// Vista 3D de la mesa (three.js). Dibuja el mismo estado que la vista 2D:
// no decide nada, solo muestra lo que manda el servidor. Los oponentes se ven
// con una ficha de madera lisa mientras sus datos estén ocultos.
(function () {
  "use strict";
  const WOOD = 0x5c3820, FELT = 0x16603f, FELT_IN = 0x1e7850;
  const CHIP_RED = "#c83226", CHIP_FACE = "#eed6a8";
  const GOLD = 0xf0c850;

  let THREE_ = window.THREE;
  let renderer, scene, camera, host, running = false, ready = false;
  let group = null, turnPlate = null;
  let avatarColor = () => "#2f7a86";
  let labelK = 1, wood, felt, inner;
  let counts = {}, lastSnap = null, lastMyId = null, t0 = performance.now();
  const texCache = {}, spriteCache = {};
  const drops = [];   // animaciones de caída de fichas nuevas

  function chipTexture(value, blank) {
    const key = blank ? "blank" : String(value);
    if (texCache[key]) return texCache[key];
    const c = document.createElement("canvas"); c.width = c.height = 256;
    const g = c.getContext("2d");
    g.fillStyle = CHIP_FACE; g.fillRect(0, 0, 256, 256);
    if (!blank) {
      g.fillStyle = CHIP_RED; g.beginPath(); g.arc(128, 128, 126, 0, Math.PI * 2); g.fill();
      g.fillStyle = CHIP_FACE; g.beginPath(); g.arc(128, 128, 96, 0, Math.PI * 2); g.fill();
      g.fillStyle = CHIP_RED; g.textAlign = "center"; g.textBaseline = "middle";
      g.font = `700 ${value < 100 ? 120 : 98}px Georgia, "Times New Roman", serif`;
      g.fillText(String(value), 128, 136);
    } else {
      g.strokeStyle = "rgba(150,114,66,.5)"; g.lineWidth = 3;
      g.beginPath(); g.arc(128, 128, 90, 0, Math.PI * 2); g.stroke();
    }
    const t = new THREE_.CanvasTexture(c);
    t.anisotropy = 4;
    t.center.set(0.5, 0.5); t.rotation = Math.PI / 2;   // la tapa del cilindro viene girada 90°
    texCache[key] = t;
    return t;
  }

  // Avatar redondo con la inicial (el mismo color que en la vista 2D).
  function avatarSprite(name) {
    const key = "avatar|" + name;
    if (!spriteCache[key]) {
      const c = document.createElement("canvas"); c.width = c.height = 128;
      const g = c.getContext("2d");
      g.fillStyle = avatarColor(name); g.beginPath(); g.arc(64, 64, 58, 0, Math.PI * 2); g.fill();
      g.lineWidth = 6; g.strokeStyle = "rgba(255,255,255,.55)"; g.stroke();
      g.fillStyle = "#faf6ea"; g.font = "800 62px 'Segoe UI', Arial, sans-serif";
      g.textAlign = "center"; g.textBaseline = "middle";
      const initials = name.trim().split(/\s+/).slice(0, 2).map((w) => w[0]).join("").toUpperCase();
      g.fillText(initials, 64, 68);
      const sp = new THREE_.Sprite(new THREE_.SpriteMaterial({ map: new THREE_.CanvasTexture(c), transparent: true, depthTest: false }));
      sp.renderOrder = 11;
      spriteCache[key] = sp;
    }
    const out = spriteCache[key].clone();
    out.scale.set(1.25 * labelK, 1.25 * labelK, 1);
    return out;
  }

  function textSprite(text, color, px, bold) {
    const key = text + "|" + color + "|" + px + "|" + bold;
    if (spriteCache[key]) { const c = spriteCache[key].clone(); c.scale.multiplyScalar(labelK); return c; }
    const c = document.createElement("canvas");
    const g = c.getContext("2d");
    const font = `${bold ? "700 " : ""}${px}px "Segoe UI", Arial, sans-serif`;
    g.font = font;
    const w = Math.ceil(g.measureText(text).width) + 16, h = Math.ceil(px * 1.4);
    c.width = w; c.height = h;
    g.font = font; g.fillStyle = color; g.textAlign = "center"; g.textBaseline = "middle";
    g.shadowColor = "rgba(0,0,0,.6)"; g.shadowBlur = 4;
    g.fillText(text, w / 2, h / 2 + 1);
    const tex = new THREE_.CanvasTexture(c);
    const mat = new THREE_.SpriteMaterial({ map: tex, transparent: true, depthTest: false });
    const sp = new THREE_.Sprite(mat);
    sp.scale.set(w / 60, h / 60, 1);
    sp.renderOrder = 10;
    spriteCache[key] = sp;
    const out = sp.clone();
    out.scale.multiplyScalar(labelK);
    return out;
  }

  const chipSideMat = () => new THREE_.MeshLambertMaterial({ color: 0xc4a06a });
  let sideMat;
  const geoChips = {};
  let geoChip = null;   // (solo para no liberar geometrías compartidas)

  function makeChip(value, blank, r) {
    if (!sideMat) sideMat = chipSideMat();
    const key = r.toFixed(2);
    if (!geoChips[key]) geoChips[key] = new THREE_.CylinderGeometry(r, r, 0.24, 40);
    const top = new THREE_.MeshLambertMaterial({ map: chipTexture(value, blank) });
    const mesh = new THREE_.Mesh(geoChips[key], [sideMat, top, sideMat]);
    mesh.rotation.y = 0;   // el número queda de frente a quien juega
    return mesh;
  }

  // Medidas según cuántos se sientan: con más jugadores, tapetes y fichas más chicos.
  let portraitMode = false;
  function sizes(n) {
    if (portraitMode) {   // celular en vertical: la mesa se alarga hacia arriba y los tapetes se angostan
      return { rx: 4.3, rz: n <= 2 ? 6.2 : 9.2, pw: 4.0, ph: 2.4, chip: 0.62, gap: 1.25 };
    }
    if (n <= 3) return { rx: 6.6, rz: 3.9, pw: 5.4, ph: 2.9, chip: 0.8, gap: 1.75 };
    if (n === 4) return { rx: 7.3, rz: 4.3, pw: 4.5, ph: 2.5, chip: 0.66, gap: 1.45 };
    return { rx: 7.6, rz: 4.5, pw: 3.9, ph: 2.3, chip: 0.56, gap: 1.2 };
  }

  function seatPositions(n, meIndex) {
    const z = sizes(n), out = [];
    for (let i = 0; i < n; i++) {
      const k = ((i - meIndex) % n + n) % n;
      const ang = -Math.PI / 2 + k * 2 * Math.PI / n;
      out.push({ x: z.rx * Math.cos(ang), z: -(z.rz * Math.sin(ang) + 0.9) });
    }
    return out;
  }

  function init(container) {
    host = container;
    if (ready) return true;
    if (!THREE_) return false;
    try {
      renderer = new THREE_.WebGLRenderer({ antialias: true, alpha: false, preserveDrawingBuffer: true });
    } catch (e) { return false; }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.setClearColor(0x0e1614);
    host.appendChild(renderer.domElement);
    renderer.domElement.style.cssText = "display:block;width:100%;height:100%";

    scene = new THREE_.Scene();
    camera = new THREE_.PerspectiveCamera(48, 1, 0.1, 100);
    scene.add(new THREE_.AmbientLight(0xffffff, 0.65));
    const sun = new THREE_.DirectionalLight(0xfff2e0, 0.9);
    sun.position.set(-6, 14, 8);
    scene.add(sun);

    wood = new THREE_.Mesh(new THREE_.CylinderGeometry(11.6, 11.6, 0.3, 64), new THREE_.MeshLambertMaterial({ color: WOOD }));
    wood.scale.z = 0.74; wood.position.set(0, -0.2, -0.8);
    felt = new THREE_.Mesh(new THREE_.CylinderGeometry(10.5, 10.5, 0.1, 64), new THREE_.MeshLambertMaterial({ color: FELT }));
    felt.scale.z = 0.72; felt.position.set(0, -0.02, -0.8);
    inner = new THREE_.Mesh(new THREE_.CylinderGeometry(5.5, 5.5, 0.02, 48), new THREE_.MeshLambertMaterial({ color: FELT_IN }));
    inner.scale.z = 0.68; inner.position.set(0, 0.05, -0.8);
    scene.add(wood, felt, inner);

    ready = true;
    resize();
    return true;
  }

  function resize() {
    if (!ready || !host) return;
    const w = host.clientWidth || 640, h = host.clientHeight || 420;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    // La cámara se coloca a la distancia justa para que quepa toda la mesa (ancho y fondo),
    // y se inclina más hacia arriba cuando la pantalla es angosta (celular en vertical).
    const vf = camera.fov * Math.PI / 180;
    const hf = 2 * Math.atan(Math.tan(vf / 2) * camera.aspect);
    const portrait = camera.aspect < 1;
    if (portrait !== portraitMode) {
      portraitMode = portrait;
      // la misma mesa, pero alargada hacia arriba en vertical
      const sx = portrait ? 0.6 : 1, sz = portrait ? 1.22 : 0.74;
      wood.scale.set(sx, 1, sz); felt.scale.set(sx, 1, sz * 0.97); inner.scale.set(sx, 1, sz * 0.92);
    }
    const elev = (portrait ? 64 : 50) * Math.PI / 180;
    const halfW = portrait ? 7.3 : 12.2, halfD = portrait ? 14.6 : 7.8;
    // el fondo se ve acortado por la inclinación: se compensa con sin(elev)
    const dist = Math.max(halfW / Math.tan(hf / 2), (halfD * Math.sin(elev) + 0.7) / Math.tan(vf / 2)) * (portrait ? 1.04 : 1.14);
    const tz = portrait ? -0.8 : 1.2;   // en horizontal se mira un poco más cerca para que no se corte el borde de abajo
    camera.position.set(0, dist * Math.sin(elev), tz + dist * Math.cos(elev));
    camera.lookAt(0, 0, tz);
    camera.updateProjectionMatrix();
    labelK = Math.min(1.9, Math.max(1, dist / 20));
    if (lastSnap) build(lastSnap, lastMyId);
  }

  function clearGroup() {
    if (!group) return;
    scene.remove(group);
    group.traverse((o) => { if (o.isMesh && o.geometry && !o.userData.shared && !Object.values(geoChips).includes(o.geometry)) o.geometry.dispose(); });
    group = null; turnPlate = null;
  }

  function build(snap, myId) {
    clearGroup();
    group = new THREE_.Group();
    const players = snap.players;
    const meIndex = Math.max(0, players.findIndex((p) => p.id === myId));
    const spots = seatPositions(players.length, meIndex);
    const winners = new Set(snap.winner_ids || []);
    const playing = snap.phase === "PLAYING";
    const old = counts; counts = {};
    const z = sizes(players.length);
    const plateGeo = new THREE_.BoxGeometry(z.pw, 0.12, z.ph);
    const rimGeo = new THREE_.BoxGeometry(z.pw + 0.16, 0.1, z.ph + 0.16);

    players.forEach((p, i) => {
      const s = spots[i], mine = p.id === myId;
      const turn = playing && p.id === snap.turn_id;
      const plate = new THREE_.Mesh(plateGeo, new THREE_.MeshLambertMaterial({ color: turn ? 0x56401a : 0x281e18 }));
      plate.position.set(s.x, 0.08, s.z);
      plate.userData.shared = true;
      const rimColor = (winners.has(p.id) || turn) ? GOLD : (mine ? 0xd2be8c : 0x6e5a46);
      const rim = new THREE_.Mesh(rimGeo, new THREE_.MeshLambertMaterial({ color: rimColor }));
      rim.position.set(s.x, 0.05, s.z); rim.userData.shared = true;
      group.add(rim, plate);
      if (turn) turnPlate = plate;

      // nombre detrás del tapete; puntaje y estado delante, para que nada se pise con el vecino
      const label = p.name + (mine ? " (tú)" : "") + (p.id === snap.host_id ? " · anfitrión" : "");
      const nm = textSprite(label, mine ? "#f0c850" : "#f0ebdc", 34, true);
      nm.position.set(s.x, 0.9, s.z - z.ph / 2 - 0.55); group.add(nm);
      const av = avatarSprite(p.name);
      av.position.set(s.x, 0.9 + 1.5 * labelK, s.z - z.ph / 2 - 1.3); group.add(av);

      if (p.hidden) {
        const chip = makeChip(0, true, z.chip); chip.position.set(s.x, 0.14, s.z); group.add(chip);
        const tag = textSprite("oculto", "rgba(240,235,220,.75)", 28, false);
        tag.position.set(s.x, 0.7, s.z + z.ph / 2 + 0.55); group.add(tag);
        return;
      }
      const n = p.balls.length;
      const span = Math.min(z.pw - 1.0, z.gap * n), step = n > 1 ? span / (n - 1) : 0;
      p.balls.forEach((v, j) => {
        const chip = makeChip(v, false, z.chip);
        const x = s.x - span / 2 + j * step, y = 0.14;
        chip.position.set(x, y, s.z);
        if (playing && j >= (old[p.id] || 0)) {
          chip.position.y = y + 7;
          drops.push({ mesh: chip, y0: y + 7, y1: y, t: performance.now() });
        }
        group.add(chip);
      });
      counts[p.id] = n;
      if (p.score !== null && p.score !== undefined) {
        const status = { ME_QUEDO: "me quedo", ME_FUI: "me fui", SIGLO: "¡SIGLO!", PLAYING: "jugando" }[p.status] || p.status;
        const sc = textSprite(`${p.score}  ·  ${status}`, "#f0c850", 32, true);
        sc.position.set(s.x, 0.7, s.z + z.ph / 2 + 0.6); group.add(sc);
      }
    });
    scene.add(group);
  }

  // rebote al caer (misma sensación que la vista de escritorio)
  function bounce(t) {
    const n1 = 7.5625, d1 = 2.75;
    if (t < 1 / d1) return n1 * t * t;
    if (t < 2 / d1) return n1 * (t -= 1.5 / d1) * t + 0.75;
    if (t < 2.5 / d1) return n1 * (t -= 2.25 / d1) * t + 0.9375;
    return n1 * (t -= 2.625 / d1) * t + 0.984375;
  }

  function frame(now) {
    if (!running) return;
    for (let i = drops.length - 1; i >= 0; i--) {
      const d = drops[i], k = Math.min(1, (now - d.t) / 600);
      d.mesh.position.y = d.y0 + (d.y1 - d.y0) * bounce(k);
      if (k >= 1) drops.splice(i, 1);
    }
    if (turnPlate) {
      const k = 0.5 + 0.5 * Math.sin((now - t0) / 200);
      turnPlate.material.color.setRGB((70 + 50 * k) / 255, (52 + 36 * k) / 255, 20 / 255);
    }
    renderer.render(scene, camera);
    requestAnimationFrame(frame);
  }

  window.Mesa3D = {
    available() { return !!window.THREE; },
    init,
    resize,
    start() { if (!ready || running) return; running = true; resize(); requestAnimationFrame(frame); },
    stop() { running = false; },
    update(snap, myId) {
      if (!ready) return;
      lastSnap = snap; lastMyId = myId;
      build(snap, myId);
    },
    setAvatarColor(fn) { avatarColor = fn; },
    reset() { counts = {}; drops.length = 0; clearGroup(); },
    debug() { return { portraitMode, aspect: camera.aspect, w: host.clientWidth, h: host.clientHeight, labelK }; },
  };
})();
